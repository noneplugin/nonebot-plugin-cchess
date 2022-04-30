import uuid
from pathlib import Path
from typing import Optional

from .board import Board
from .move import Move
from .engine import UCCIEngine


class Player:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

    def __eq__(self, player: "Player") -> bool:
        return self.id == player.id

    def __str__(self) -> str:
        return self.name


class AiPlayer(Player):
    def __init__(self, engine_path: Path, level: int = 4):
        self.level = level
        self.id = uuid.uuid4().hex
        self.name = f"AI lv.{level}"
        self.engine = UCCIEngine(engine_path)
        time_list = [100, 400, 700, 1000, 1500, 2000, 3000, 5000]
        self.time = time_list[level - 1]
        depth_list = [5, 5, 5, 5, 8, 12, 17, 25]
        self.depth = depth_list[level - 1]

    async def get_move(self, position: str) -> Move:
        return await self.engine.bestmove(position, time=self.time, depth=self.depth)


class Game(Board):
    def __init__(self):
        super().__init__()
        self.player_red: Optional[Player] = None
        self.player_black: Optional[Player] = None

    @property
    def player_next(self) -> Optional[Player]:
        return self.player_red if self.moveside else self.player_black

    @property
    def player_last(self) -> Optional[Player]:
        return self.player_black if self.moveside else self.player_red

    @property
    def is_battle(self) -> bool:
        return not isinstance(self.player_red, AiPlayer) and not isinstance(
            self.player_black, AiPlayer
        )

    def close_engine(self):
        if isinstance(self.player_red, AiPlayer):
            self.player_red.engine.close()
        if isinstance(self.player_black, AiPlayer):
            self.player_black.engine.close()
