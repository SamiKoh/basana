# Basana
#
# Copyright 2022-2023 Gabriel Martin Becedillas Ruiz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
.. moduleauthor:: Gabriel Martin Becedillas Ruiz <gabriel.becedillas@gmail.com>
"""

# Bars can be downloaded using this command:
# python -m basana.external.binance.tools.download_bars -c BTC/USDT -p 1d -s 2017-01-01 -e 2021-12-31 > \
# binance_btcusdt_day.csv

from decimal import Decimal
import asyncio
import logging

from basana.external.binance import csv
import basana as bs
import basana.backtesting.exchange as backtesting_exchange
import bbands


# The strategy is responsible for placing orders in response to trading signals.
class Strategy:
    def __init__(self, exchange: backtesting_exchange.Exchange, position_pct: Decimal):
        assert position_pct > 0 and position_pct <= 1
        self._exchange = exchange
        self._position_pct = position_pct

    async def on_trading_signal(self, trading_signal: bs.TradingSignal):
        logging.info("Trading signal: operation=%s pair=%s", trading_signal.operation, trading_signal.pair)
        try:
            # Calculate the order size.
            if trading_signal.operation == bs.OrderOperation.BUY:
                balance, (_, ask) = await asyncio.gather(
                    self._exchange.get_balance(trading_signal.pair.quote_symbol),
                    self._exchange.get_bid_ask(trading_signal.pair)
                )
                order_size = balance.available * self._position_pct / ask
            else:
                balance = await self._exchange.get_balance(trading_signal.pair.base_symbol)
                order_size = balance.available
            order_size = bs.truncate_decimal(order_size, 8)
            if not order_size:
                return

            logging.info(
                "Creating %s market order for %s: amount=%s", trading_signal.operation, trading_signal.pair, order_size
            )
            await self._exchange.create_market_order(trading_signal.operation, trading_signal.pair, order_size)
        except Exception as e:
            logging.error(e)


async def main():
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s %(levelname)s] %(message)s")

    event_dispatcher = bs.backtesting_dispatcher()
    pair = bs.Pair("BTC", "USDT")
    exchange = backtesting_exchange.Exchange(event_dispatcher, initial_balances={"USDT": Decimal(10000)})
    exchange.set_pair_info(pair, bs.PairInfo(8, 2))

    # Connect the signal source with the bar events from the exchange.
    signal_source = bbands.SignalSource(event_dispatcher, 23, 3.1)
    exchange.subscribe_to_bar_events(pair, signal_source.on_bar_event)

    # Connect the strategy to the trading signal source.
    strategy = Strategy(exchange, Decimal("0.95"))
    signal_source.subscribe_to_trading_signals(strategy.on_trading_signal)

    # Load bars from CSV files.
    exchange.add_bar_source(csv.BarSource(pair, "binance_btcusdt_day.csv", "1d"))

    # Run the backtest.
    await event_dispatcher.run()

    # Log balances.
    balances = await exchange.get_balances()
    for currency, balance in balances.items():
        logging.info("%s balance: %s", currency, balance.available)


if __name__ == "__main__":
    asyncio.run(main())
