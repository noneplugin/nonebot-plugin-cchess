import asyncio
from asyncio import TimerHandle
from typing import Annotated, Any, Optional, Union

from nonebot import on_regex, require
from nonebot.matcher import Matcher
from nonebot.params import Depends, RegexDict
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.rule import to_me
from nonebot.utils import run_sync

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_orm")

from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
    Image,
    Option,
    Query,
    Text,
    UniMessage,
    on_alconna,
    store_true,
)
from nonebot_plugin_uninfo import Uninfo

from .board import MoveResult
from .config import Config
from .engine import EngineError
from .game import AiPlayer, Game, Player
from .move import Move

__plugin_meta__ = PluginMetadata(
    name="象棋",
    description="象棋，支持人机和对战",
    usage=(
        "@我 + “象棋人机”或“象棋对战”开始一局游戏；\n"
        "可使用“lv1~8”指定AI等级，如“象棋人机lv5”，默认为“lv4”；\n"
        "发送 中文纵线格式如“炮二平五” 或 起始坐标格式如“h2e2”下棋；\n"
        "发送“结束下棋”结束当前棋局；发送“显示棋盘”显示当前棋局"
    ),
    type="application",
    homepage="https://github.com/noneplugin/nonebot-plugin-cchess",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna", "nonebot_plugin_uninfo"
    ),
)


games: dict[str, Game] = {}
timers: dict[str, TimerHandle] = {}


def get_user_id(uninfo: Uninfo) -> str:
    return f"{uninfo.scope}_{uninfo.self_id}_{uninfo.scene_path}"


UserId = Annotated[str, Depends(get_user_id)]


def game_is_running(user_id: UserId) -> bool:
    return user_id in games


def game_not_running(user_id: UserId) -> bool:
    return user_id not in games


cchess = on_alconna(
    Alconna(
        "cchess",
        Option("--battle", default=False, action=store_true, help_text="对战模式"),
        Option("--black", default=False, action=store_true, help_text="执黑，即后手"),
        Option("-l|--level", Args["level", int], help_text="人机等级"),
    ),
    rule=to_me() & game_not_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)


def wrapper(slot: Union[int, str], content: Optional[str]) -> str:
    if slot == "mode" and content in ("对战", "双人"):
        return "--battle"
    elif slot == "order" and content in ("后手", "执黑"):
        return "--black"
    elif slot == "level" and content:
        return f"--level {content}"
    return ""


cchess.shortcut(
    r"象棋(?P<mode>对战|双人|人机|单人)?(?P<order>先手|执白|后手|执黑)?(?:[lL][vV](?P<level>[1-8]))?",
    {
        "prefix": True,
        "wrapper": wrapper,
        "args": ["{mode}", "{order}", "{level}"],
    },
)

cchess_show = on_alconna(
    "显示棋盘",
    aliases={"显示棋局", "查看棋盘", "查看棋局"},
    rule=game_is_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)
cchess_stop = on_alconna(
    "结束下棋",
    aliases={"结束游戏", "结束象棋"},
    rule=game_is_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)
cchess_repent = on_alconna(
    "悔棋",
    rule=game_is_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)
cchess_reload = on_alconna(
    "重载象棋棋局",
    aliases={"恢复象棋棋局"},
    rule=game_not_running,
    use_cmd_start=True,
    block=True,
    priority=13,
)
cchess_move = on_regex(
    r"^(?P<move>(?:[a-zA-Z]\d[a-zA-Z]\d)|(?:\S\S[平进退上下][\d一二三四五六七八九]))$",
    rule=game_is_running,
    block=True,
    priority=14,
)


def stop_game(user_id: str):
    if timer := timers.pop(user_id, None):
        timer.cancel()
    if game := games.pop(user_id, None):
        game.close_engine()


async def stop_game_timeout(matcher: Matcher, user_id: str):
    game = games.get(user_id, None)
    stop_game(user_id)
    if game:
        msg = "象棋下棋超时，游戏结束，可发送“重载象棋棋局”继续下棋"
        await matcher.finish(msg)


def set_timeout(matcher: Matcher, user_id: str, timeout: float = 600):
    if timer := timers.get(user_id, None):
        timer.cancel()
    loop = asyncio.get_running_loop()
    timer = loop.call_later(
        timeout, lambda: asyncio.ensure_future(stop_game_timeout(matcher, user_id))
    )
    timers[user_id] = timer


def current_player(uninfo: Uninfo) -> Player:
    user_id = uninfo.user.id
    user_name = (
        (uninfo.member.nick if uninfo.member else None)
        or uninfo.user.nick
        or uninfo.user.name
        or ""
    )
    return Player(user_id, user_name)


CurrentPlayer = Annotated[Player, Depends(current_player)]


@cchess.handle()
async def _(
    matcher: Matcher,
    user_id: UserId,
    uninfo: Uninfo,
    player: CurrentPlayer,
    battle: Query[bool] = AlconnaQuery("battle.value", False),
    black: Query[bool] = AlconnaQuery("black.value", False),
    level: Query[int] = AlconnaQuery("level", 4),
):
    if not battle.result and not 1 <= level.result <= 8:
        await matcher.finish("等级应在 1~8 之间")

    if battle.result and uninfo.scene.is_private:
        await matcher.finish("私聊不支持对战模式")

    game = Game()
    if black.result:
        game.player_black = player
    else:
        game.player_red = player

    msg = (
        f"{player} 发起了游戏 象棋！\n"
        "发送 中文纵线格式如“炮二平五” 或 起始坐标格式如“h2e2” 下棋\n"
    )

    if not battle.result:
        try:
            ai_player = AiPlayer(level.result)
            await ai_player.engine.open()
        except EngineError as e:
            await matcher.finish(f"象棋引擎加载失败：{e.message}")

        if black.result:
            game.player_red = ai_player
        else:
            game.player_black = ai_player

        if black.result:
            try:
                move = await ai_player.get_move(game.position())
            except EngineError as e:
                await matcher.finish(f"象棋引擎出错：{e.message}")

            move_str = move.chinese(game)
            game.push(move)
            msg += f"{ai_player} 下出 {move_str}\n"

    games[user_id] = game
    set_timeout(matcher, user_id)

    await game.save_record(user_id)
    await (Text(msg) + Image(raw=await run_sync(game.draw)())).send()


@cchess_show.handle()
async def _(matcher: Matcher, user_id: UserId):
    game = games[user_id]
    set_timeout(matcher, user_id)

    await UniMessage.image(raw=await run_sync(game.draw)()).send()


@cchess_stop.handle()
async def _(matcher: Matcher, user_id: UserId, player: CurrentPlayer):
    game = games[user_id]

    if (not game.player_red or game.player_red != player) and (
        not game.player_black or game.player_black != player
    ):
        await matcher.finish("只有游戏参与者才能结束游戏")
    stop_game(user_id)
    await matcher.finish("游戏已结束，可发送“重载象棋棋局”继续下棋")


@cchess_repent.handle()
async def _(matcher: Matcher, user_id: UserId, player: CurrentPlayer):
    game = games[user_id]
    set_timeout(matcher, user_id)

    if len(game.history) <= 1 or not game.player_next:
        await matcher.finish("对局尚未开始")

    if game.is_battle:
        if game.player_last and game.player_last != player:
            await matcher.finish("上一手棋不是你所下")
        game.pop()
    else:
        if len(game.history) <= 2 and game.player_last != player:
            await matcher.finish("上一手棋不是你所下")
        game.pop()
        game.pop()
    await game.save_record(user_id)
    msg = f"{player} 进行了悔棋\n"
    await (Text(msg) + Image(raw=await run_sync(game.draw)())).send()


@cchess_reload.handle()
async def _(matcher: Matcher, user_id: UserId):
    try:
        game = await Game.load_record(user_id)
    except EngineError as e:
        await matcher.finish(f"象棋引擎加载失败：{e.message}")

    if not game:
        await matcher.finish("没有找到被中断的游戏")
    games[user_id] = game
    set_timeout(matcher, user_id)

    msg = (
        f"游戏发起时间：{game.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"红方：{game.player_red}\n"
        f"黑方：{game.player_black}\n"
        f"下一手轮到：{game.player_next}\n"
    )
    await (Text(msg) + Image(raw=await run_sync(game.draw)())).send()


@cchess_move.handle()
async def _(
    matcher: Matcher,
    user_id: UserId,
    player: CurrentPlayer,
    matched: dict[str, Any] = RegexDict(),
):
    game = games[user_id]
    set_timeout(matcher, user_id)

    if (
        game.player_red
        and game.player_black
        and game.player_red != player
        and game.player_black != player
    ):
        await matcher.finish("只有游戏参与者才能下棋")

    if (game.player_next and game.player_next != player) or (
        game.player_last and game.player_last == player
    ):
        await matcher.finish("当前不是你的回合")

    move = str(matched["move"])
    try:
        move = Move.from_ucci(move)
    except ValueError:
        try:
            move = Move.from_chinese(game, move)
        except ValueError:
            await matcher.finish("请发送正确的走法，如 “炮二平五” 或 “h2e2”")

    try:
        move_str = move.chinese(game)
    except ValueError:
        await matcher.finish("不正确的走法")

    result = game.push(move)
    if result == MoveResult.ILLEGAL:
        await matcher.finish("不正确的走法")
    elif result == MoveResult.CHECKED:
        await matcher.finish("该走法将导致被将军或白脸将")

    msg = UniMessage()
    if not game.player_last:
        if not game.player_red:
            game.player_red = player
        elif not game.player_black:
            game.player_black = player
        msg += f"{player} 加入了游戏并下出 {move_str}"
    else:
        msg += f"{player} 下出 {move_str}"

    if result:
        stop_game(user_id)
        if result == MoveResult.DRAW:
            msg += "，本局游戏平局\n"
        else:
            winner = (
                game.player_red if result == MoveResult.RED_WIN else game.player_black
            )
            if game.is_battle:
                msg += f"，恭喜 {winner} 获胜！\n"
            else:
                msg += "，恭喜你赢了！\n" if player == winner else "，很遗憾你输了！\n"
    else:
        if game.player_next and game.is_battle:
            msg += f"，下一手轮到 {game.player_next}\n"

    sameside = game.is_battle
    msg += Image(raw=await run_sync(game.draw)(sameside))

    if not game.is_battle and not result:
        ai_player = game.player_next
        assert isinstance(ai_player, AiPlayer)
        try:
            move = await ai_player.get_move(game.position())
        except EngineError as e:
            await matcher.finish(f"象棋引擎出错：{e.message}")

        move_str = move.chinese(game)
        result = game.push(move)
        msg += f"\n{ai_player} 下出 {move_str}"

        if result == MoveResult.ILLEGAL:
            game.pop()
            await matcher.finish("象棋引擎出错，请结束游戏或稍后再试")

        elif result:
            stop_game(user_id)
            if result == MoveResult.CHECKED:
                msg += "，恭喜你赢了！\n"
            elif result == MoveResult.DRAW:
                msg += "，本局游戏平局\n"
            else:
                winner = (
                    game.player_red
                    if result == MoveResult.RED_WIN
                    else game.player_black
                )
                msg += "，恭喜你赢了！\n" if player == winner else "，很遗憾你输了！\n"
        msg += Image(raw=await run_sync(game.draw)())

    await game.save_record(user_id)
    await msg.send()
