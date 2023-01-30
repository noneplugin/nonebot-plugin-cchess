from sqlmodel import Field
from typing import Optional
from datetime import datetime

from nonebot_plugin_datastore import get_plugin_data

Model = get_plugin_data().Model


class GameRecord(Model, table=True):
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: str
    session_id: str = ""
    start_time: datetime = datetime.now()
    """ 游戏开始时间 """
    update_time: datetime = datetime.now()
    """ 游戏更新时间 """
    player_red_id: str = ""
    """ 红方id """
    player_red_name: str = ""
    """ 红方名字 """
    player_red_is_ai: bool = False
    """ 红方是否为AI """
    player_red_level: int = 0
    """ 红方等级 """
    player_black_id: str = ""
    """ 黑方id """
    player_black_name: str = ""
    """ 黑方名字 """
    player_black_is_ai: bool = False
    """ 黑方是否为AI """
    player_black_level: int = 0
    """ 黑方等级 """
    start_fen: str = ""
    """ 起始局面FEN字符串 """
    moves: str = ""
    """ 所有移动，ucci形式，以空格分隔 """
    is_game_over: bool = False
    """ 游戏是否已结束 """
