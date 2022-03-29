from datetime import datetime
from typing import Iterable

from linenotipy import Line

from trade_ibkr.const import LINE_ENABLE, LINE_REPORT_INTERVAL_SEC, LINE_REPORT_SYMBOLS
from trade_ibkr.model import OnOrderFilledEvent, PxData
from trade_ibkr.utils import print_line_log, print_warning


class LineNotifyClient(Line):
    def __init__(self, *, token: str):
        super().__init__(token=token)

        self._last_px_report_epoch: datetime | None = None

    def send_px_data_message(self, px_data_list: Iterable[PxData]):
        if not self.enabled:
            print_warning("Px data not reported because the reporting service is disabled.")
            return

        now = datetime.now()
        # Px reported in a given interval
        if (
                self._last_px_report_epoch is not None
                and (now.timestamp() - self._last_px_report_epoch.timestamp()) < LINE_REPORT_INTERVAL_SEC
        ):
            return

        self._last_px_report_epoch = now

        px_dict: dict[str, float] = {}

        for px_data in px_data_list:
            symbol = px_data.contract_symbol

            if symbol not in LINE_REPORT_SYMBOLS or symbol in px_dict:
                continue

            px_dict[symbol] = px_data.current_close

        message = "\n" + "\n".join([f"{symbol}: {px}" for symbol, px in px_dict.items()])
        message += now.strftime("\n@ %Y-%m-%d %H:%M:%S")

        self.post(message=message)
        print_line_log("Px data reported")

    def send_order_filled_message(self, event: OnOrderFilledEvent):
        self.post(message=f"\n{event}")
        print_line_log("Order filled reported")

    @property
    def enabled(self) -> bool:
        return LINE_ENABLE
