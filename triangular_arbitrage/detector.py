import ccxt.async_support as ccxt
from typing import List, Tuple
from dataclasses import dataclass
import networkx as nx
import aiohttp

import octobot_commons.symbols as symbols
import octobot_commons.constants as constants

FEE = 0.001  # 0.1% per trade


@dataclass
class ShortTicker:
    symbol: symbols.Symbol
    last_price: float
    reversed: bool = False

    def __repr__(self):
        return f"ShortTicker(symbol={str(self.symbol)}, last_price={self.last_price}, reversed={self.reversed})"


async def fetch_tickers(exchange):
    return await exchange.fetch_tickers() if exchange.has['fetchTickers'] else {}


def get_symbol_from_key(key_symbol: str):
    try:
        return symbols.parse_symbol(key_symbol)
    except:
        return None


def is_delisted_symbols(exchange_time, ticker,
                        threshold=1 * constants.DAYS_TO_SECONDS * constants.MSECONDS_TO_SECONDS) -> bool:
    ticker_time = ticker['timestamp']
    return ticker_time is not None and not (exchange_time - ticker_time <= threshold)


def get_last_prices(exchange_time, tickers, ignored_symbols, whitelisted_symbols=None):
    result = []

    for key, ticker in tickers.items():
        symbol = get_symbol_from_key(key)

        if symbol is None:
            continue

        if ticker['close'] is None:
            continue

        if is_delisted_symbols(exchange_time, ticker):
            continue

        if str(symbol) in ignored_symbols:
            continue

        if not symbol.is_spot():
            continue

        if whitelisted_symbols and str(symbol) not in whitelisted_symbols:
            continue

        result.append(ShortTicker(symbol=symbol, last_price=ticker['close']))

    return result


def get_best_triangular_opportunity(tickers: List[ShortTicker]) -> Tuple[List[ShortTicker], float]:
    return get_best_opportunity(tickers, 3)


def get_best_opportunity(tickers: List[ShortTicker], max_cycle: int = 10) -> Tuple[List[ShortTicker], float]:
    graph = nx.DiGraph()

    for ticker in tickers:
        if ticker.symbol is not None:
            graph.add_edge(ticker.symbol.base, ticker.symbol.quote, ticker=ticker)

            graph.add_edge(
                ticker.symbol.quote,
                ticker.symbol.base,
                ticker=ShortTicker(
                    symbols.Symbol(f"{ticker.symbol.quote}/{ticker.symbol.base}"),
                    1 / ticker.last_price,
                    reversed=True
                )
            )

    best_profit = 1
    best_cycle = None

    for cycle in nx.simple_cycles(graph):
        if len(cycle) > max_cycle:
            continue

        profit = 1
        tickers_in_cycle = []

        for i, base in enumerate(cycle):
            quote = cycle[(i + 1) % len(cycle)]
            ticker = graph[base][quote]['ticker']

            tickers_in_cycle.append(ticker)

            # ✅ Apply trading fee here
            profit *= ticker.last_price * (1 - FEE)

        if profit > best_profit:
            best_profit = profit
            best_cycle = tickers_in_cycle

    if best_cycle is not None:
        best_cycle = [
            ShortTicker(
                symbols.Symbol(f"{ticker.symbol.quote}/{ticker.symbol.base}"),
                ticker.last_price,
                reversed=True
            ) if ticker.reversed else ticker
            for ticker in best_cycle
        ]

    return best_cycle, best_profit


async def get_exchange_data(exchange_name):
    exchange_class = getattr(ccxt, exchange_name)

    # ✅ FIX DNS issues (no aiodns problems)
    connector = aiohttp.TCPConnector(use_dns_cache=False)
    session = aiohttp.ClientSession(connector=connector)

    exchange = exchange_class({
        'session': session,
        'enableRateLimit': True
    })

    try:
        # ✅ IMPORTANT: load markets first
        await exchange.load_markets()

        tickers = await fetch_tickers(exchange)

        filtered_tickers = {
            symbol: ticker
            for symbol, ticker in tickers.items()
            if exchange.markets.get(symbol, {}).get("active", True)
        }

        exchange_time = exchange.milliseconds()

        return filtered_tickers, exchange_time

    finally:
        await exchange.close()
        await session.close()


async def get_exchange_last_prices(exchange_name, ignored_symbols, whitelisted_symbols=None):
    tickers, exchange_time = await get_exchange_data(exchange_name)
    return get_last_prices(exchange_time, tickers, ignored_symbols, whitelisted_symbols)


async def run_detection(exchange_name, ignored_symbols=None, whitelisted_symbols=None, max_cycle=10):
    last_prices = await get_exchange_last_prices(exchange_name, ignored_symbols or [], whitelisted_symbols)
    best_opportunity, best_profit = get_best_opportunity(last_prices, max_cycle=max_cycle)
    return best_opportunity, best_profit