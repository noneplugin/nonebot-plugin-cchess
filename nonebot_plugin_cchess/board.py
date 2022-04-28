import re
from typing import List, Optional

from .move import Move, MoveSide
from .piece import Piece

INIT_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


class Board:
    def __init__(self, start_fen: str = INIT_FEN):
        self._board: List[List[Optional[Piece]]] = [
            [None for j in range(9)] for i in range(10)
        ]
        self.moveside = MoveSide.RED
        """当前行动方"""
        self.halfmove = 0
        """双方没有吃子的走棋步数(半回合数)"""
        self.fullmove = 1
        """当前的回合数"""
        self.from_fen(start_fen)

    def __str__(self) -> str:
        return self.fen()

    def from_fen(self, fen: str = ""):
        """从FEN字符串读取当前局面"""
        board_fen, moveside, _, _, halfmove, fullmove = fen.split(" ")

        self._board = [[None for j in range(9)] for i in range(10)]
        for i, line_fen in enumerate(board_fen.split("/")[::-1]):
            j = 0
            for ch in line_fen:
                if ch.isdigit():
                    num = int(ch)
                    if 1 <= num <= 9:
                        j += num
                elif re.fullmatch(r"[kabnrcpKABNRCP]", ch):
                    self._board[i][j] = Piece(ch)
                    j += 1
                else:
                    raise ValueError("Illegal character in fen string!")

        self.moveside = MoveSide.BLACK if moveside == "b" else MoveSide.RED
        self.halfmove = int(halfmove)
        self.fullmove = int(fullmove)

    def fen(self) -> str:
        """返回当前局面的FEN字符串"""
        return f"{self.board_fen()} {self.moveside.value} - - {self.halfmove} {self.fullmove}"

    def board_fen(self) -> str:
        """返回当前棋盘布局的FEN字符串"""
        line_fens = []
        for line in self._board:
            line_fen = ""
            num = 0
            for piece in line:
                if not piece:
                    num += 1
                else:
                    if num:
                        line_fen += str(num)
                    num = 0
                    line_fen += piece.symbol
            if num:
                line_fen += str(num)
            line_fens.append(line_fen)
        return "/".join(line_fens[::-1])

