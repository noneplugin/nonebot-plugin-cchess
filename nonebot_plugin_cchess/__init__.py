import asyncio
import re
import shlex
from asyncio import TimerHandle
from dataclasses import dataclass
from io import BytesIO
from typing import Dict, Iterable, List, NoReturn, Union

from nonebot import on_command, on_message, on_shell_command, require
from nonebot.adapters import Bot, Event, Message
from nonebot.exception import ParserExit
from nonebot.matcher import Matcher
from nonebot.params import (
    CommandArg,
    CommandStart,
    EventPlainText,
    EventToMe,
    ShellCommandArgv,
)
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.rule import ArgumentParser, Rule
from nonebot.typing import T_State

require("nonebot_plugin_saa")
require("nonebot_plugin_session")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_orm")

from nonebot_plugin_saa import Image, MessageFactory
from nonebot_plugin_session import SessionIdType, SessionLevel, extract_session
from nonebot_plugin_userinfo import get_user_info

from . import migrations
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
        "nonebot_plugin_saa", "nonebot_plugin_session", "nonebot_plugin_userinfo"
    ),
    extra={
        "unique_name": "cchess",
        "example": "@小Q 象棋人机lv5\n炮二平五\n结束下棋",
        "author": "meetwq <meetwq@gmail.com>",
        "version": "0.3.2",
        "orm_version_location": migrations,
    },
)


parser = ArgumentParser("cchess", description="象棋")
group = parser.add_mutually_exclusive_group()
group.add_argument("-e", "--stop", "--end", action="store_true", help="停止下棋")
group.add_argument("-v", "--show", "--view", action="store_true", help="显示棋盘")
group.add_argument("--repent", action="store_true", help="悔棋")
group.add_argument("--battle", action="store_true", help="对战模式")
group.add_argument("--reload", action="store_true", help="重新加载已停止的游戏")
parser.add_argument("--black", action="store_true", help="执黑，即后手")
parser.add_argument("-l", "--level", type=int, default=4, help="人机等级")
parser.add_argument("move", nargs="?", help="走法")


@dataclass
class Options:
    stop: bool = False
    show: bool = False
    repent: bool = False
    battle: bool = False
    reload: bool = False
    black: bool = False
    level: int = 4
    move: str = ""


games: Dict[str, Game] = {}
timers: Dict[str, TimerHandle] = {}


cchess = on_shell_command("cchess", parser=parser, block=True, priority=13)


@cchess.handle()
async def _(
    bot: Bot,
    matcher: Matcher,
    event: Event,
    argv: List[str] = ShellCommandArgv(),
):
    await handle_cchess(bot, matcher, event, argv)


def get_cid(bot: Bot, event: Event):
    return extract_session(bot, event).get_id(SessionIdType.GROUP)


def shortcut(cmd: str, argv: List[str] = [], **kwargs):
    command = on_command(cmd, **kwargs, block=True, priority=13)

    @command.handle()
    async def _(bot: Bot, matcher: Matcher, event: Event, msg: Message = CommandArg()):
        try:
            args = shlex.split(msg.extract_plain_text().strip())
        except:
            args = []
        await handle_cchess(bot, matcher, event, argv + args)


def game_running(bot: Bot, event: Event) -> bool:
    cid = get_cid(bot, event)
    return bool(games.get(cid, None))


# 命令前缀为空则需要to_me，否则不需要
def smart_to_me(command_start: str = CommandStart(), to_me: bool = EventToMe()) -> bool:
    return bool(command_start) or to_me


def not_private(bot: Bot, event: Event) -> bool:
    return extract_session(bot, event).level not in (
        SessionLevel.LEVEL0,
        SessionLevel.LEVEL1,
    )


shortcut("象棋对战", ["--battle"], aliases={"象棋双人"}, rule=Rule(smart_to_me) & not_private)
shortcut("象棋人机", aliases={"象棋单人"}, rule=smart_to_me)
for i in range(1, 9):
    shortcut(
        f"象棋人机lv{i}",
        ["--level", f"{i}"],
        aliases={f"象棋lv{i}", f"象棋人机Lv{i}", f"象棋Lv{i}"},
        rule=smart_to_me,
    )
shortcut("停止下棋", ["--stop"], aliases={"结束下棋", "停止游戏", "结束游戏"}, rule=game_running)
shortcut("查看棋盘", ["--show"], aliases={"查看棋局", "显示棋盘", "显示棋局"}, rule=game_running)
shortcut("悔棋", ["--repent"], rule=game_running)
shortcut("下棋", rule=game_running)
shortcut("重载象棋棋局", ["--reload"], aliases={"重载象棋棋盘", "恢复象棋棋局", "恢复象棋棋盘"})


def match_move(msg: str) -> bool:
    return bool(re.fullmatch(r"^\s*\S\S[a-zA-Z平进退上下][\d一二三四五六七八九]\s*$", msg))


def get_move_input(state: T_State, msg: str = EventPlainText()) -> bool:
    if match_move(msg):
        state["move"] = msg
        return True
    return False


pos_matcher = on_message(Rule(game_running) & get_move_input, block=True, priority=14)


@pos_matcher.handle()
async def _(
    bot: Bot,
    matcher: Matcher,
    event: Event,
    state: T_State,
):
    move: str = state["move"]
    await handle_cchess(bot, matcher, event, [move])


def stop_game(cid: str):
    game = games.pop(cid, None)
    if game:
        game.close_engine()


async def stop_game_timeout(matcher: Matcher, cid: str):
    timers.pop(cid, None)
    if games.get(cid, None):
        stop_game(cid)
        await matcher.finish("象棋下棋超时，游戏结束，可发送“重载象棋棋局”继续下棋")


def set_timeout(matcher: Matcher, cid: str, timeout: float = 600):
    timer = timers.get(cid, None)
    if timer:
        timer.cancel()
    loop = asyncio.get_running_loop()
    timer = loop.call_later(
        timeout, lambda: asyncio.ensure_future(stop_game_timeout(matcher, cid))
    )
    timers[cid] = timer


async def handle_cchess(
    bot: Bot,
    matcher: Matcher,
    event: Event,
    argv: List[str],
):
    async def new_player(event: Event) -> Player:
        user_id = event.get_user_id()
        user_name = ""
        if user_info := await get_user_info(bot, event, user_id=user_id):
            user_name = user_info.user_displayname or user_info.user_name
        return Player(user_id, user_name)

    async def send(msgs: Union[str, Iterable[Union[str, BytesIO]]] = "") -> NoReturn:
        if not msgs:
            await matcher.finish()
        if isinstance(msgs, str):
            await matcher.finish(msgs)

        msg_builder = MessageFactory([])
        for msg in msgs:
            if isinstance(msg, BytesIO):
                msg_builder.append(Image(msg))
            else:
                msg_builder.append(msg)
        await msg_builder.send()
        await matcher.finish()

    try:
        args = parser.parse_args(argv)
    except ParserExit as e:
        if e.status == 0:
            await send(__plugin_meta__.usage)
        await send()

    options = Options(**vars(args))

    cid = get_cid(bot, event)
    if not games.get(cid, None):
        if options.move:
            await send()

        if options.stop or options.show or options.repent:
            await send("没有正在进行的游戏")

        if not options.battle and not 1 <= options.level <= 8:
            await send("等级应在 1~8 之间")

        if options.reload:
            try:
                game = await Game.load_record(cid)
            except EngineError:
                await send("象棋引擎加载失败，请检查设置")
            if not game:
                await send("没有找到被中断的游戏")
            games[cid] = game
            await send(
                (
                    (
                        f"游戏发起时间：{game.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"红方：{game.player_red}\n"
                        f"黑方：{game.player_black}\n"
                        f"下一手轮到：{game.player_next}\n"
                    ),
                    game.draw(),
                )
            )

        game = Game()
        player = await new_player(event)
        if options.black:
            game.player_black = player
        else:
            game.player_red = player

        msg = f"{player} 发起了游戏 象棋！\n发送 中文纵线格式如“炮二平五” 或 起始坐标格式如“h2e2” 下棋"

        if not options.battle:
            try:
                ai_player = AiPlayer(options.level)
                await ai_player.engine.open()

                if options.black:
                    game.player_red = ai_player
                    move = await ai_player.get_move(game.position())
                    move_chi = move.chinese(game)
                    result = game.push(move)
                    if result:
                        await send("象棋引擎返回不正确，请检查设置")
                    msg += f"\n{ai_player} 下出 {move_chi}"
                else:
                    game.player_black = ai_player
            except EngineError:
                await send("象棋引擎加载失败，请检查设置")

        games[cid] = game
        set_timeout(matcher, cid)
        await game.save_record(cid)
        await send((msg + "\n", game.draw()))

    game = games[cid]
    set_timeout(matcher, cid)
    player = await new_player(event)

    if options.stop:
        if (not game.player_red or game.player_red != player) and (
            not game.player_black or game.player_black != player
        ):
            await send("只有游戏参与者才能结束游戏")
        stop_game(cid)
        await send("游戏已结束，可发送“重载象棋棋局”继续下棋")

    if options.show:
        await send((game.draw(),))

    if (
        game.player_red
        and game.player_black
        and game.player_red != player
        and game.player_black != player
    ):
        await send("当前有正在进行的游戏")

    if options.repent:
        if len(game.history) <= 1 or not game.player_next:
            await send("对局尚未开始")
        if game.is_battle:
            if game.player_last and game.player_last != player:
                await send("上一手棋不是你所下")
            game.pop()
        else:
            if len(game.history) <= 2 and game.player_last != player:
                await send("上一手棋不是你所下")
            game.pop()
            game.pop()
        await game.save_record(cid)
        await send((f"{player} 进行了悔棋\n", game.draw()))

    if (game.player_next and game.player_next != player) or (
        game.player_last and game.player_last == player
    ):
        await send("当前不是你的回合")

    move = options.move
    if not match_move(move):
        await send("发送 中文纵线格式如“炮二平五” 或 起始坐标格式如“h2e2” 下棋")

    try:
        move = Move.from_ucci(move)
    except ValueError:
        try:
            move = Move.from_chinese(game, move)
        except ValueError:
            await send("请发送正确的走法，如 “炮二平五” 或 “h2e2”")

    try:
        move_str = move.chinese(game)
    except ValueError:
        await send("不正确的走法")

    result = game.push(move)
    if result == MoveResult.ILLEAGAL:
        await send("不正确的走法")
    elif result == MoveResult.CHECKED:
        await send("该走法将导致被将军或白脸将")

    msgs: List[Union[str, BytesIO]] = []

    if not game.player_last:
        if not game.player_red:
            game.player_red = player
        elif not game.player_black:
            game.player_black = player
        msg = f"{player} 加入了游戏并下出 {move_str}"
    else:
        msg = f"{player} 下出 {move_str}"

    if result == MoveResult.RED_WIN:
        stop_game(cid)
        if game.is_battle:
            msg += f"，恭喜 {game.player_red} 获胜！"
        else:
            msg += "，恭喜你赢了！" if player == game.player_red else "，很遗憾你输了！"
    elif result == MoveResult.BLACK_WIN:
        stop_game(cid)
        if game.is_battle:
            msg += f"，恭喜 {game.player_black} 获胜！"
        else:
            msg += "，恭喜你赢了！" if player == game.player_black else "，很遗憾你输了！"
    elif result == MoveResult.DRAW:
        stop_game(cid)
        msg += f"，本局游戏平局"
    else:
        if game.player_next and game.is_battle:
            msg += f"，下一手轮到 {game.player_next}"

    msgs.append(msg + "\n")

    if game.is_battle:
        msgs.append(game.draw())
    else:
        msgs.append(game.draw(False))
        if not result:
            ai_player = game.player_next
            assert isinstance(ai_player, AiPlayer)
            move = await ai_player.get_move(game.position())
            move_chi = move.chinese(game)
            result = game.push(move)

            msg = f"\n{ai_player} 下出 {move_chi}"
            if result == MoveResult.ILLEAGAL:
                game.pop()
                await send("象棋引擎出错，请结束游戏或稍后再试")
            elif result:
                stop_game(cid)
                if result == MoveResult.CHECKED:
                    msg += "，恭喜你赢了！"
                elif result == MoveResult.RED_WIN:
                    msg += "，恭喜你赢了！" if player == game.player_red else "，很遗憾你输了！"
                elif result == MoveResult.BLACK_WIN:
                    msg += "，恭喜你赢了！" if player == game.player_black else "，很遗憾你输了！"
                elif result == MoveResult.DRAW:
                    msg += f"，本局游戏平局"
            msgs.append(msg + "\n")
            msgs.append(game.draw())

    await game.save_record(cid)
    await send(msgs)
