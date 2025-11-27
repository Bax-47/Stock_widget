import json
import os
import random
from datetime import datetime, timezone
from typing import Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from models import StockPrice

# Default symbols our system tracks
DEFAULT_SYMBOLS = ["AAPL", "TSLA", "NVDA", "MSFT"]

# Toggle full mock mode. If True, we never call Finnhub and always
# generate random-walk prices.
USE_MOCK_PRICES = False


class StockPriceProvider:
    """
    Provides current stock prices for a configured list of symbols.

    Behaviour:
      * If USE_MOCK_PRICES is True:
          - Always generate mock data (random walk).
      * If USE_MOCK_PRICES is False:
          - Try Finnhub using an API key.
          - On any error per symbol, fall back to mock for that symbol.

    API key resolution order:
      1. Explicit api_key argument
      2. FINNHUB_TOKEN env var
      3. FINNHUB_API_KEY env var
    """

    def __init__(self, symbols=None, api_key: str = None):
        self.symbols = symbols or DEFAULT_SYMBOLS

        # Resolve API key from explicit arg or environment, supporting both names.
        self.api_key = (
            api_key
            or os.getenv("FINNHUB_TOKEN")
            or os.getenv("FINNHUB_API_KEY")
        )

        # Baseline prices used by the random-walk fallback generator
        self._fallback_state: Dict[str, float] = {
            sym: 100.0 + i * 50 for i, sym in enumerate(self.symbols)
        }

        if USE_MOCK_PRICES:
            print("[stocks_service] USE_MOCK_PRICES=True -> using mock prices only.")
        else:
            if self.api_key:
                print("[stocks_service] Real mode enabled. Finnhub API key detected.")
            else:
                print(
                    "[stocks_service] Real mode requested but no Finnhub API key found; "
                    "falling back to mock prices."
                )

    # ------------------------------------------------------------------
    # Fallback mock generator
    # ------------------------------------------------------------------

    def _fallback_price(self, symbol: str, now: datetime) -> StockPrice:
        """Generate a simple random-walk price for one symbol."""
        prev_price = self._fallback_state.get(symbol, 100.0)
        # +/- up to ~2% each step (roughly)
        delta = (random.random() - 0.5) * 4.0
        new_price = max(1.0, prev_price + delta)

        change = new_price - prev_price
        percent_change = (change / prev_price) * 100 if prev_price else 0.0

        self._fallback_state[symbol] = new_price

        return StockPrice(
            symbol=symbol,
            price=new_price,
            change=change,
            percentChange=percent_change,
            ts=now,
        )

    def _fallback_snapshot(self, now: datetime) -> List[StockPrice]:
        return [self._fallback_price(sym, now) for sym in self.symbols]

    # ------------------------------------------------------------------
    # Finnhub integration
    # ------------------------------------------------------------------

    def _fetch_symbol_from_finnhub(self, symbol: str, now: datetime) -> StockPrice:
        """Fetch the latest quote for a symbol from Finnhub."""
        if not self.api_key:
            raise RuntimeError(
                "Finnhub API key not configured (FINNHUB_TOKEN / FINNHUB_API_KEY)."
            )

        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={self.api_key}"

        with urlopen(url, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)

        # Finnhub returns 'c' as the current price.
        price = data.get("c")
        if price is None or price <= 0:
            raise ValueError(f"Invalid price returned from Finnhub for {symbol}: {data}")

        # Approximate change using our internal baseline state.
        prev_price = self._fallback_state.get(symbol, float(price))
        change = float(price) - prev_price
        percent_change = (change / prev_price) * 100 if prev_price else 0.0

        # Update baseline to real price for next step.
        self._fallback_state[symbol] = float(price)

        return StockPrice(
            symbol=symbol,
            price=float(price),
            change=change,
            percentChange=percent_change,
            ts=now,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_prices(self) -> List[StockPrice]:
        """Return a list of StockPrice objects for all symbols."""
        now = datetime.now(timezone.utc)

        # Full mock mode
        if USE_MOCK_PRICES:
            return self._fallback_snapshot(now)

        # Real mode but no key -> log and return fallback
        if not self.api_key:
            print("[stocks_service] No Finnhub API key set; returning mock prices.")
            return self._fallback_snapshot(now)

        # Try Finnhub symbol-by-symbol, falling back on error.
        prices: List[StockPrice] = []
        for sym in self.symbols:
            try:
                prices.append(self._fetch_symbol_from_finnhub(sym, now))
            except (HTTPError, URLError, RuntimeError, ValueError, Exception) as e:
                print(f"[stocks_service] Finnhub failed for {sym}, using fallback: {e}")
                prices.append(self._fallback_price(sym, now))

        return prices

    # Backwards-compatibility alias for existing code in main.py
    def get_price_snapshot(self) -> List[StockPrice]:
        """Alias so code that calls get_price_snapshot() still works."""
        return self.get_prices()
