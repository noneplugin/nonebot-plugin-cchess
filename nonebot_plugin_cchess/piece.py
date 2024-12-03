from enum import Enum


class PieceType(Enum):
    KING = "k"
    """将"""
    ADVISOR = "a"
    """士"""
    BISHOP = "b"
    """象"""
    KNIGHT = "n"
    """马"""
    ROOK = "r"
    """车"""
    CANNON = "c"
    """炮"""
    PAWN = "p"
    """兵"""


piece_data: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "k": (("帅", "将"), ("\U0001fa00", "\U0001fa07")),
    "a": (("仕", "士"), ("\U0001fa01", "\U0001fa08")),
    "b": (("相", "象"), ("\U0001fa02", "\U0001fa09")),
    "n": (("马", "马"), ("\U0001fa03", "\U0001fa0a")),
    "r": (("车", "车"), ("\U0001fa04", "\U0001fa0b")),
    "c": (("炮", "炮"), ("\U0001fa05", "\U0001fa0c")),
    "p": (("兵", "卒"), ("\U0001fa06", "\U0001fa0d")),
}


class Piece:
    def __init__(self, symbol: str):
        self.symbol: str = symbol
        """棋子字母表示，大写表示红方，小写表示黑方"""
        s = symbol.lower()
        t = 1 if s == symbol else 0
        self.name: str = piece_data[s][0][t]
        """棋子中文名称"""
        self.unicode_symbol: str = piece_data[s][1][t]
        """棋子 Unicode 符号"""
        self.piece_type: PieceType = PieceType(s)
        """棋子类型"""
        self.color: bool = bool(t == 0)
        """棋子颜色，`True`为红色，`False`为黑色"""

    def __str__(self) -> str:
        return self.symbol
