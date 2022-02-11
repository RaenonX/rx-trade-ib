import asyncio
import time
from dataclasses import dataclass, field
from typing import ParamSpec, TypeVar

from ibapi.client import EClient
from ibapi.common import BarData, TickAttrib, TickerId
from ibapi.contract import Contract, ContractDetails
from ibapi.ticktype import TickType, TickTypeEnum
from ibapi.wrapper import EWrapper

from trade_ibkr.enums import PxDataCol
from trade_ibkr.model import (
    BarDataDict, OnPxDataUpdatedEventNoAccount, OnPxDataUpdatedNoAccount, PxData, to_bar_data_dict,
    OnMarketDataReceived, OnMarketDataReceivedEvent,
)

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(kw_only=True)
class PxDataCacheEntry:
    data: dict[int, BarDataDict]
    contract: ContractDetails | None
    on_update: OnPxDataUpdatedNoAccount
    on_update_market: OnMarketDataReceived

    last_historical_sent: float = field(init=False)

    def __post_init__(self):
        self.last_historical_sent = time.time()

    @property
    def is_ready(self) -> bool:
        return self.contract is not None and self.data

    @property
    def is_send_px_data_ok(self) -> bool:
        # Debounce the data because `priceTick` and historical data update frequently
        return time.time() - self.last_historical_sent > 5

    def to_px_data(self) -> PxData:
        self.last_historical_sent = time.time()

        return PxData(contract=self.contract, bars=[self.data[key] for key in sorted(self.data.keys())])


class IBapiInfo(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)

        self._px_data_cache: dict[int, PxDataCacheEntry] = {}
        self._px_data_complete: set[int] = set()
        self._px_req_id_to_contract_req_id: dict[int, int] = {}
        self._px_market_to_px_data: dict[int, int] = {}

        self._contract_data: dict[int, ContractDetails | None] = {}

        self._order_id = 0
        self._request_id = -1

    @property
    def next_valid_request_id(self) -> int:
        self._request_id += 1

        return self._request_id

    # region Contract

    def request_contract_data(self, contract: Contract) -> int:
        request_id = self.next_valid_request_id

        self.reqContractDetails(request_id, contract)

        return request_id

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        self._contract_data[reqId] = contractDetails

    # endregion

    # region Historical Data

    def _on_historical_data_return(self, reqId: int, bar: BarData, /, remove_old: bool) -> bool:
        # If `bar.barCount` is -1, the data is incorrect
        if bar.barCount == -1:
            return False

        bar_data_dict = to_bar_data_dict(bar)
        epoch = bar_data_dict[PxDataCol.EPOCH_SEC]

        cache_entry = self._px_data_cache[reqId]
        cache_entry.data[bar_data_dict[PxDataCol.EPOCH_SEC]] = bar_data_dict

        is_new_bar = epoch not in cache_entry.data

        if is_new_bar and remove_old:
            # Keep price data in a fixed size
            cache_entry.data.pop(min(cache_entry.data.keys()))

        if contract_req_id := self._px_req_id_to_contract_req_id.get(reqId):
            # Add contract detail to PxData object
            cache_entry.contract = self._contract_data[contract_req_id]

        return is_new_bar

    def historicalData(self, reqId: int, bar: BarData):
        self._on_historical_data_return(reqId, bar, remove_old=False)

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        _time = time.time()
        self._on_historical_data_return(reqId, bar, remove_old=True)

        px_data_cache_entry = self._px_data_cache[reqId]

        if px_data_cache_entry.is_ready and px_data_cache_entry.is_send_px_data_ok:
            async def execute_on_update():
                await px_data_cache_entry.on_update(OnPxDataUpdatedEventNoAccount(
                    contract=px_data_cache_entry.contract,
                    px_data=px_data_cache_entry.to_px_data(),
                    proc_sec=time.time() - _time,
                ))

            asyncio.run(execute_on_update())

    # endregion

    # region Market Data

    def tickPrice(self, reqId: TickerId, tickType: TickType, price: float, attrib: TickAttrib):
        name = TickTypeEnum.idx2name[tickType]

        if name != "LAST":
            return

        px_data_cache_entry = self._px_data_cache[self._px_market_to_px_data[reqId]]

        if not px_data_cache_entry.contract:
            return

        async def execute_on_update():
            await px_data_cache_entry.on_update_market(OnMarketDataReceivedEvent(
                contract=px_data_cache_entry.contract,
                px=price,
            ))

        asyncio.run(execute_on_update())

    # endregion

    def request_px_data(self, *, contract: Contract, duration: str, bar_size: str, keep_update: bool) -> int:
        request_id = self.next_valid_request_id

        self.reqHistoricalData(request_id, contract, "", duration, bar_size, "TRADES", 0, 2, keep_update, [])

        return request_id

    def request_px_data_market(self, contract: Contract) -> int:
        request_id = self.next_valid_request_id

        self.reqMktData(request_id, contract, "", False, False, [])

        return request_id

    def get_px_data_keep_update(
            self, *,
            contract: Contract, duration: str, bar_size: str,
            on_px_data_updated: OnPxDataUpdatedNoAccount,
            on_market_data_received: OnMarketDataReceived,
    ) -> None:
        req_px = self.request_px_data(contract=contract, duration=duration, bar_size=bar_size, keep_update=True)
        req_contract = self.request_contract_data(contract)
        req_market = self.request_px_data_market(contract)
        self._px_req_id_to_contract_req_id[req_px] = req_contract
        self._px_market_to_px_data[req_market] = req_px

        self._px_data_cache[req_px] = PxDataCacheEntry(
            contract=None,
            data={},
            on_update=on_px_data_updated,
            on_update_market=on_market_data_received,
        )
