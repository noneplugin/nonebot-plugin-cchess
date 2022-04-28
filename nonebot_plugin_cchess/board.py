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

    def legal_to_pos(self, from_pos: Pos) -> Iterator[Pos]:
        """获取某个位置的棋子所有可能走的位置"""
        piece = self._board[from_pos.x][from_pos.y]
        if not piece:
            return

        self_pos = list(self.get_piece_pos(sameside=True))
        oppo_pos = list(self.get_piece_pos(sameside=False))
        total_pos = self_pos + oppo_pos

        piece_type = piece.piece_type
        if piece_type == PieceType.KING:
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                to_pos = Pos(from_pos.x + dx, from_pos.y + dy)
                if (
                    (0 <= to_pos.x <= 2 or 7 <= to_pos.x <= 9)
                    and 3 <= to_pos.y <= 5
                    and to_pos not in self_pos
                ):
                    yield to_pos
        elif piece_type == PieceType.ADVISOR:
            for dx, dy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
                to_pos = Pos(from_pos.x + dx, from_pos.y + dy)
                if (
                    (0 <= to_pos.x <= 2 or 7 <= to_pos.x <= 9)
                    and 3 <= to_pos.y <= 5
                    and to_pos not in self_pos
                ):
                    yield to_pos
        elif piece_type == PieceType.BISHOP:
            for dx, dy in ((2, 2), (-2, -2), (2, -2), (-2, 2)):
                to_pos = Pos(from_pos.x + dx, from_pos.y + dy)
                mid_pos = Pos(
                    (from_pos.x + to_pos.x) // 2, (from_pos.y + to_pos.y) // 2
                )
                if (
                    to_pos.valid()
                    and mid_pos.x not in [4, 5]
                    and to_pos not in self_pos
                    and mid_pos not in total_pos
                ):
                    yield to_pos
        elif piece_type == PieceType.KNIGHT:
            for dx, dy in (
                (2, 1),
                (-2, -1),
                (-2, 1),
                (2, -1),
                (1, 2),
                (-1, -2),
                (-1, 2),
                (1, -2),
            ):
                to_pos = Pos(from_pos.x + dx, from_pos.y + dy)
                if abs(dx) == 1:
                    mid_pos = Pos(from_pos.x, (from_pos.y + to_pos.y) // 2)
                else:
                    mid_pos = Pos((from_pos.x + to_pos.x) // 2, from_pos.y)
                if (
                    to_pos.valid()
                    and to_pos not in self_pos
                    and mid_pos not in total_pos
                ):
                    yield to_pos
        elif piece_type == PieceType.PAWN:
            if self.moveside:
                if from_pos.x >= 5:
                    moves = ((1, 0), (0, 1), (0, -1))
                else:
                    moves = ((1, 0),)
            else:
                if from_pos.x <= 4:
                    moves = ((-1, 0), (0, 1), (0, -1))
                else:
                    moves = ((-1, 0),)
            for dx, dy in moves:
                to_pos = Pos(from_pos.x + dx, from_pos.y + dy)
                if to_pos.valid() and to_pos not in self_pos:
                    yield to_pos
        elif piece_type == PieceType.ROOK:
            start_x = 0
            end_x = 9
            start_y = 0
            end_y = 8
            for pos in total_pos:
                if pos.x == from_pos.x:
                    if start_y < pos.y < from_pos.y:
                        start_y = pos.y
                    if from_pos.y < pos.y < end_y:
                        end_y = pos.y
                if pos.y == from_pos.y:
                    if start_x < pos.x < from_pos.x:
                        start_x = pos.x
                    if from_pos.x < pos.x < end_x:
                        end_x = pos.x
            for x in range(start_x, end_x + 1):
                to_pos = Pos(x, from_pos.y)
                if to_pos != from_pos and to_pos not in self_pos:
                    yield to_pos
            for y in range(start_y, end_y + 1):
                to_pos = Pos(from_pos.x, y)
                if to_pos != from_pos and to_pos not in self_pos:
                    yield to_pos
        elif piece_type == PieceType.CANNON:
            above_pos = [p for p in total_pos if p.y == from_pos.y and p.x > from_pos.x]
            below_pos = [p for p in total_pos if p.y == from_pos.y and p.x < from_pos.x]
            left_pos = [p for p in total_pos if p.x == from_pos.x and p.y < from_pos.y]
            right_pos = [p for p in total_pos if p.x == from_pos.x and p.y > from_pos.y]
            above_pos.sort(key=lambda p: p.x)
            below_pos.sort(key=lambda p: p.x, reverse=True)
            left_pos.sort(key=lambda p: p.x, reverse=True)
            right_pos.sort(key=lambda p: p.x)
            start_x = below_pos[0].x if below_pos else 0
            end_x = above_pos[0].x if above_pos else 9
            start_y = left_pos[0].y if left_pos else 0
            end_y = right_pos[0].y if right_pos else 8
            for x in range(start_x, end_x + 1):
                to_pos = Pos(x, from_pos.y)
                if to_pos != from_pos and to_pos not in total_pos:
                    yield to_pos
            for y in range(start_y, end_y + 1):
                to_pos = Pos(from_pos.x, y)
                if to_pos != from_pos and to_pos not in total_pos:
                    yield to_pos
            if len(above_pos) > 1 and above_pos[1] not in self_pos:
                yield above_pos[1]
            if len(below_pos) > 1 and below_pos[1] not in self_pos:
                yield below_pos[1]
            if len(left_pos) > 1 and left_pos[1] not in self_pos:
                yield left_pos[1]
            if len(right_pos) > 1 and right_pos[1] not in self_pos:
                yield right_pos[1]
