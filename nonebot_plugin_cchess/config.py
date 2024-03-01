from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    cchess_engine_path: Path = Path("data/cchess/fairy-stockfish")


cchess_config = get_plugin_config(Config)
