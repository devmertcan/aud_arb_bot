from __future__ import annotations
import asyncio
from collections import defaultdict
from typing import Dict, Tuple, Callable
from core.types import BestBook, Quote

class Aggregator:
    def __init__(self):
        self._books: Dict[Tuple[str,str], Quote] = {}
        self._subs: list[Callable[[BestBook], None]] = []

    def on_book(self, book: BestBook):
        self._books[(book.exchange, book.pair)] = book.quote
        for cb in self._subs:
            cb(book)

    def subscribe(self, cb: Callable[[BestBook], None]):
        self._subs.append(cb)

    def snapshot(self) -> Dict[tuple[str,str], Quote]:
        return dict(self._books)
