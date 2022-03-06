import threading
import time
from typing import Callable, TypeVar, Union

from .api import IBapiBotSpread, IBapiInfo
from ..model import CommodityPair, OnMarketPxUpdatedOfBotSpread

T = TypeVar("T", bound=Union[IBapiInfo | IBapiBotSpread])


def init_app(app_callable: Callable[[], T], is_demo: bool = False) -> tuple[T, threading.Thread]:
    app = app_callable()
    app.connect("localhost", 8384 if is_demo else 8383, 87)

    def run_loop():
        try:
            app.run()
        except Exception as ex:
            app.disconnect()
            raise ex

    api_thread = threading.Thread(target=run_loop)
    api_thread.start()

    while not app.isConnected():
        time.sleep(0.1)

    return app, api_thread


def start_app_bot_spread(
        *, commodity_pair: CommodityPair, on_px_updated: OnMarketPxUpdatedOfBotSpread,
        is_demo: bool = False,
) -> tuple[IBapiBotSpread, threading.Thread]:
    return init_app(lambda: IBapiBotSpread(commodity_pair=commodity_pair, on_px_updated=on_px_updated), is_demo)


def start_app_info(*, is_demo: bool = False) -> tuple[IBapiInfo, threading.Thread]:
    return init_app(IBapiInfo, is_demo)
