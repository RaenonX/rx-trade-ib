from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from ...open_order import OpenOrderBook
from ...position import Position


@dataclass(kw_only=True)
class OnPositionFetchedEvent:
    position: Position


OnPositionFetched = Callable[[OnPositionFetchedEvent], Coroutine[Any, Any, None]]


@dataclass(kw_only=True)
class OnOpenOrderFetchedEvent:
    open_order: OpenOrderBook


OnOpenOrderFetched = Callable[[OnOpenOrderFetchedEvent], Coroutine[Any, Any, None]]
