from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class StockPrice(BaseModel):
    symbol: str
    price: float
    change: float
    percentChange: float
    ts: datetime


class PriceUpdateMessage(BaseModel):
    type: str = "price_update"
    data: List[StockPrice]


# ===== Alert models =====

class AlertRule(BaseModel):
    """
    A simple alert rule, e.g.:
      AAPL > 200
      TSLA < 180
    """
    id: int
    symbol: str
    operator: str  # one of ">", "<", ">=", "<=", "=="
    threshold: float
    description: str
    enabled: bool = True
    cooldown_seconds: int = 60  # minimum time between triggers
    last_triggered: Optional[datetime] = None


class AlertEvent(BaseModel):
    """
    A concrete alert firing at a specific time.
    """
    rule_id: int
    symbol: str
    price: float
    triggered_at: datetime
    message: str
