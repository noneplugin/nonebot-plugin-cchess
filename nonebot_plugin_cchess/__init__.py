import re
import shlex
import asyncio
from asyncio import TimerHandle
from dataclasses import dataclass
from typing import Dict, List, Tuple

from nonebot import get_driver
from nonebot.typing import T_State
from nonebot.matcher import Matcher
from nonebot.exception import ParserExit
from nonebot.rule import Rule, ArgumentParser
from nonebot import on_command, on_shell_command, on_message
from nonebot.params import (
    ShellCommandArgv,
    Command,
    CommandArg,
    RawCommand,
    State,
    EventPlainText,
)
from nonebot.adapters.onebot.v11 import MessageSegment as MS
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Message

from .move import Move
from .config import Config
from .board import MoveResult
from .engine import EngineError
from .game import Game, Player, AiPlayer

cchess_config = Config.parse_obj(get_driver().config.dict())


__help__plugin_name__ = "cchess"
__des__ = "象棋，支持人机和对战"
__cmd__ = """
@我 + “象棋人机”或“象棋对战”开始一局游戏；
可使用“lv1~8”指定AI等级，如“象棋人机lv5”，默认为“lv4”；
发送 中文纵线格式如“炮二平五” 或 起始坐标格式如“h2e2”下棋；
发送“结束下棋”结束当前棋局；发送“显示棋盘”显示当前棋局
""".strip()
__short_cmd__ = "象棋人机、象棋对战"
__example__ = """
@小Q 象棋人机lv5
炮二平五
结束下棋
""".strip()
__usage__ = f"{__des__}\nUsage:\n{__cmd__}\nExample:\n{__example__}"


parser = ArgumentParser("cchess", description="象棋")
group = parser.add_mutually_exclusive_group()
group.add_argument("-e", "--stop", "--end", action="store_true", help="停止下棋")
group.add_argument("-v", "--show", "--view", action="store_true", help="显示棋盘")
group.add_argument("--repent", action="store_true", help="悔棋")
group.add_argument("--battle", action="store_true", help="对战模式")
parser.add_argument("--black", action="store_true", help="执黑，即后手")
parser.add_argument("-l", "--level", type=int, default=4, help="人机等级")
parser.add_argument("move", nargs="?", help="走法")


@dataclass
class Options:
    stop: bool = False
    show: bool = False
    repent: bool = False
    battle: bool = False
    black: bool = False
    level: int = 4
    move: str = ""


games: Dict[str, Game] = {}
timers: Dict[str, TimerHandle] = {}


cchess = on_shell_command("cchess", parser=parser, block=True, priority=13)


@cchess.handle()
async def _(
    matcher: Matcher, event: MessageEvent, argv: List[str] = ShellCommandArgv()
):
    await handle_cchess(matcher, event, argv)


def get_cid(event: MessageEvent):
    return (
        f"group_{event.group_id}"
        if isinstance(event, GroupMessageEvent)
        else f"private_{event.user_id}"
    )


def shortcut(cmd: str, argv: List[str] = [], **kwargs):
    command = on_command(cmd, **kwargs, block=True, priority=13)

    @command.handle()
    async def _(matcher: Matcher, event: MessageEvent, msg: Message = CommandArg()):
        try:
            args = shlex.split(msg.extract_plain_text().strip())
        except:
            args = []
        await handle_cchess(matcher, event, argv + args)


def game_running(event: MessageEvent) -> bool:
    cid = get_cid(event)
    return bool(games.get(cid, None))


# 命令前缀为空则需要to_me，否则不需要
def smart_to_me(
    event: MessageEvent, cmd: Tuple[str, ...] = Command(), raw_cmd: str = RawCommand()
) -> bool:
    return not raw_cmd.startswith(cmd[0]) or event.is_tome()


def is_group(event: MessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent)


shortcut("象棋对战", ["--battle"], aliases={"象棋双人"}, rule=Rule(smart_to_me) & is_group)
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


def match_move(msg: str) -> bool:
    return bool(re.fullmatch(r"^\s*\S\S[a-zA-Z平进退上下][\d一二三四五六七八九]\s*$", msg))


def get_move_input(state: T_State = State(), msg: str = EventPlainText()) -> bool:
    if match_move(msg):
        state["move"] = msg
        return True
    return False


pos_matcher = on_message(Rule(game_running) & get_move_input, block=True, priority=14)


@pos_matcher.handle()
async def _(matcher: Matcher, event: MessageEvent, state: T_State = State()):
    move: str = state["move"]
    await handle_cchess(matcher, event, [move])


async def stop_game(matcher: Matcher, cid: str):
    timers.pop(cid, None)
    if games.get(cid, None):
        games.pop(cid)
        await matcher.finish("象棋下棋超时，游戏结束")


def set_timeout(matcher: Matcher, cid: str, timeout: float = 600):
    timer = timers.get(cid, None)
    if timer:
        timer.cancel()
    loop = asyncio.get_running_loop()
    timer = loop.call_later(
        timeout, lambda: asyncio.ensure_future(stop_game(matcher, cid))
    )
    timers[cid] = timer


def new_player(event: MessageEvent) -> Player:
    return Player(event.user_id, event.sender.card or event.sender.nickname or "")


async def handle_cchess(matcher: Matcher, event: MessageEvent, argv: List[str]):
    try:
        args = parser.parse_args(argv)
    except ParserExit as e:
        if e.status == 0:
            await matcher.finish(__usage__)
        await matcher.finish()

    options = Options(**vars(args))

    cid = get_cid(event)
    if not games.get(cid, None):
        if options.move:
            await matcher.finish()

        if options.stop or options.show or options.repent:
            await matcher.finish("没有正在进行的游戏")

        if not options.battle and not 1 <= options.level <= 8:
            await matcher.finish("等级应在 1~8 之间")

        game = Game()
        player = new_player(event)
        if options.black:
            game.player_black = player
        else:
            game.player_red = player

        msg = f"{player} 发起了游戏 象棋！\n发送 中文纵线格式如“炮二平五” 或 起始坐标格式如“h2e2” 下棋"

        if not options.battle:
            try:
                ai_player = AiPlayer(cchess_config.cchess_engine_path, options.level)
                await ai_player.engine.open()

                if options.black:
                    game.player_red = ai_player
                    move = await ai_player.get_move(game.position())
                    move_chi = move.chinese(game)
                    result = game.push(move)
                    if result:
                        await matcher.finish("象棋引擎返回不正确，请检查设置")
                    msg += f"\n{ai_player} 下出 {move_chi}"
                else:
                    game.player_black = ai_player
            except EngineError:
                await matcher.finish("象棋引擎加载失败，请检查设置")

        games[cid] = game
        set_timeout(matcher, cid)
        await matcher.finish(msg + MS.image(game.draw()))

    if options.stop:
        games.pop(cid)
        await matcher.finish("游戏已结束")

    game = games[cid]
    set_timeout(matcher, cid)

    if options.show:
        await matcher.finish(MS.image(game.draw()))

    player = new_player(event)
    if (
        game.player_red
        and game.player_black
        and game.player_red != player
        and game.player_black != player
    ):
        await matcher.finish("当前有正在进行的游戏")

    if options.repent:
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
        await matcher.finish(f"{player} 进行了悔棋" + MS.image(game.draw()))

    if (game.player_next and game.player_next != player) or (
        game.player_last and game.player_last == player
    ):
        await matcher.finish("当前不是你的回合")

    move = options.move
    if not match_move(move):
        await matcher.finish("发送 中文纵线格式如“炮二平五” 或 起始坐标格式如“h2e2” 下棋")

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
    if result == MoveResult.ILLEAGAL:
        await matcher.finish("不正确的走法")
    elif result == MoveResult.CHECKED:
        await matcher.finish("该走法将导致被将军或白脸将")

    message = Message()

    if not game.player_last:
        if not game.player_red:
            game.player_red = player
        elif not game.player_black:
            game.player_black = player
        msg = f"{player} 加入了游戏并下出 {move_str}"
    else:
        msg = f"{player} 下出 {move_str}"

    if result == MoveResult.RED_WIN:
        games.pop(cid)
        if game.is_battle:
            msg += f"，恭喜 {game.player_red} 获胜！"
        else:
            game.close_engine()
            msg += "，恭喜你赢了！" if player == game.player_red else "，很遗憾你输了！"
    elif result == MoveResult.BLACK_WIN:
        games.pop(cid)
        if game.is_battle:
            msg += f"，恭喜 {game.player_black} 获胜！"
        else:
            game.close_engine()
            msg += "，恭喜你赢了！" if player == game.player_black else "，很遗憾你输了！"
    elif result == MoveResult.DRAW:
        games.pop(cid)
        msg += f"，本局游戏平局"
    else:
        if game.player_next and game.is_battle:
            msg += f"，下一手轮到 {game.player_next}"
    message.append(msg)

    if game.is_battle:
        message.append(MS.image(game.draw()))
    else:
        message.append(MS.image(game.draw(False)))
        if not result:
            ai_player = game.player_next
            assert isinstance(ai_player, AiPlayer)
            move = await ai_player.get_move(game.position())
            move_chi = move.chinese(game)
            result = game.push(move)

            msg = f"{ai_player} 下出 {move_chi}"
            if result == MoveResult.ILLEAGAL:
                game.pop()
                await matcher.finish("象棋引擎出错，请结束游戏或稍后再试")
            elif result:
                games.pop(cid)
                game.close_engine()
                if result == MoveResult.CHECKED:
                    msg += "，恭喜你赢了！"
                elif result == MoveResult.RED_WIN:
                    msg += "，恭喜你赢了！" if player == game.player_red else "，很遗憾你输了！"
                elif result == MoveResult.BLACK_WIN:
                    msg += "，恭喜你赢了！" if player == game.player_black else "，很遗憾你输了！"
                elif result == MoveResult.DRAW:
                    msg += f"，本局游戏平局"
            message.append(msg)
            message.append(MS.image(game.draw()))

    await matcher.finish(message)
