import asyncio
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from models import PriceUpdateMessage, StockPrice, AlertEvent
from stocks_service import StockPriceProvider
from cache_service import PriceCache
from alert_service import AlertManager
from webex_service import WebexNotifier

app = FastAPI(title="SmartStock Monitor Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

price_provider = StockPriceProvider()
price_cache = PriceCache()          # Redis or in-memory
alert_manager = AlertManager()      # In-memory alert engine
webex_notifier = WebexNotifier()    # WebEx bot notifier


# ===== DEMO / REAL ALERT RULES SWITCH =====
USE_DEMO_ALERT_RULES = True  # set False for "real" thresholds


def load_alert_rules():
    if USE_DEMO_ALERT_RULES:
        print("[alerts] Loading DEMO alert rules")
        # These are intentionally easy so they trigger quickly (with real or mock prices)
        alert_manager.add_rule(
            symbol="AAPL",
            operator=">",
            threshold=0,
            description="DEMO: AAPL > 0",
            cooldown_seconds=10,
        )
        alert_manager.add_rule(
            symbol="TSLA",
            operator=">",
            threshold=0,
            description="DEMO: TSLA > 0",
            cooldown_seconds=10,
        )
        alert_manager.add_rule(
            symbol="NVDA",
            operator=">",
            threshold=0,
            description="DEMO: NVDA > 0",
            cooldown_seconds=10,
        )
    else:
        print("[alerts] Loading REAL alert rules")
        alert_manager.add_rule(
            symbol="AAPL",
            operator=">",
            threshold=200,
            description="AAPL > 200 (Notify WebEx)",
            cooldown_seconds=60,
        )
        alert_manager.add_rule(
            symbol="TSLA",
            operator="<",
            threshold=180,
            description="TSLA < 180 (Notify WebEx)",
            cooldown_seconds=60,
        )
        alert_manager.add_rule(
            symbol="NVDA",
            operator=">",
            threshold=1000,
            description="NVDA > 1000 (High priority)",
            cooldown_seconds=60,
        )


# Load rules at startup
load_alert_rules()


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "cache_backend": price_cache.backend,
        "alert_rules": [r.dict() for r in alert_manager.list_rules()],
        "webex_enabled": webex_notifier.enabled,
    }


@app.get("/alerts/events")
async def list_alert_events() -> List[AlertEvent]:
    """
    View recent alert events (for debugging/demo).
    """
    return alert_manager.recent_events()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


async def get_fresh_prices() -> List[StockPrice]:
    """
    1. Try cached prices if they are recent.
    2. Otherwise fetch from Finnhub (or mock), cache them.
    3. Evaluate alert rules and log/send events.
    """
    cached = price_cache.load_prices(max_age_seconds=20)
    if cached is not None:
        prices = cached
    else:
        prices = price_provider.get_price_snapshot()
        price_cache.save_prices(prices)

    # Evaluate alert rules
    events = alert_manager.check_alerts(prices)
    for event in events:
        # Log to backend console
        print(f"[alert] {event.message}")
        # Send to WebEx (if configured)
        webex_notifier.send_alert(event)

    return prices


@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            prices = await get_fresh_prices()
            msg = PriceUpdateMessage(data=prices)
            await websocket.send_text(msg.model_dump_json())

            # Thanks to cache, multiple clients share the same snapshot.
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[ws] Unexpected error in websocket_prices: {e}")
        manager.disconnect(websocket)
