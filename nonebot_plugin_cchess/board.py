import re
from typing import List, Optional, Iterator

from .move import Move, Pos
from .piece import Piece, PieceType

INIT_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


class Board:
    def __init__(self, start_fen: str = INIT_FEN):
        self._board: List[List[Optional[Piece]]] = [
            [None for j in range(9)] for i in range(10)
        ]
        self.moveside: bool = True
        """当前行动方，`True`为红方，`False`为黑方"""
        self.halfmove: int = 0
        """双方没有吃子的走棋步数(半回合数)"""
        self.fullmove: int = 1
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

        self.moveside = not (moveside == "b")
        self.halfmove = int(halfmove)
        self.fullmove = int(fullmove)

    def fen(self) -> str:
        """返回当前局面的FEN字符串"""
        moveside = "w" if self.moveside else "b"
        return f"{self.board_fen()} {moveside} - - {self.halfmove} {self.fullmove}"

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

    def get_piece_at(self, pos: Pos, sameside: bool = True) -> Optional[Piece]:
        """获取指定位置的棋子"""
        piece = self._board[pos.x][pos.y]
        if piece and (
            (self.moveside == piece.color)
            if sameside
            else (self.moveside != piece.color)
        ):
            return piece

    def get_piece_pos(
        self, piece_type: Optional[PieceType] = None, sameside: bool = True
    ) -> Iterator[Pos]:
        """获取指定类型的棋子，`piece_type`为空表示所有类型"""
        for row, line in enumerate(self._board):
            for col, piece in enumerate(line):
                if (
                    piece
                    and (piece_type is None or piece.piece_type == piece_type)
                    and (
                        (self.moveside == piece.color)
                        if sameside
                        else (self.moveside != piece.color)
                    )
                ):
                    yield Pos(row, col)
