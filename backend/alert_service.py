from datetime import datetime, timezone, timedelta
from typing import Dict, List

from models import AlertRule, AlertEvent, StockPrice


class AlertManager:
    """
    In-memory alert rule engine.

    - Stores alert rules.
    - On each price snapshot, evaluates rules.
    - Applies cooldown to avoid spamming.
    - Keeps a small history of recent events for inspection / logging.

    Later we can plug WebEx notifications into the events it produces.
    """

    def __init__(self):
        self._rules: Dict[int, AlertRule] = {}
        self._next_id: int = 1
        self._events: List[AlertEvent] = []

    # ----- Rule management -----

    def add_rule(
        self,
        symbol: str,
        operator: str,
        threshold: float,
        description: str,
        enabled: bool = True,
        cooldown_seconds: int = 60,
    ) -> AlertRule:
        rule = AlertRule(
            id=self._next_id,
            symbol=symbol.upper(),
            operator=operator,
            threshold=threshold,
            description=description,
            enabled=enabled,
            cooldown_seconds=cooldown_seconds,
        )
        self._rules[rule.id] = rule
        self._next_id += 1
        return rule

    def list_rules(self) -> List[AlertRule]:
        return list(self._rules.values())

    # ----- Evaluation -----

    def _condition_met(self, rule: AlertRule, price: float) -> bool:
        if rule.operator == ">":
            return price > rule.threshold
        if rule.operator == "<":
            return price < rule.threshold
        if rule.operator == ">=":
            return price >= rule.threshold
        if rule.operator == "<=":
            return price <= rule.threshold
        if rule.operator == "==":
            return price == rule.threshold
        # Unknown operator => never fire
        return False

    def _can_trigger(self, rule: AlertRule, now: datetime) -> bool:
        if rule.last_triggered is None:
            return True
        delta = now - rule.last_triggered
        return delta.total_seconds() >= rule.cooldown_seconds

    def check_alerts(self, prices: List[StockPrice]) -> List[AlertEvent]:
        """
        Evaluate all rules against the given price snapshot.
        Returns a list of newly-fired AlertEvent objects.
        """
        if not self._rules:
            return []

        now = datetime.now(timezone.utc)
        events: List[AlertEvent] = []

        # Index prices by symbol for quick lookup
        price_by_symbol = {p.symbol.upper(): p for p in prices}

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            price_obj = price_by_symbol.get(rule.symbol.upper())
            if price_obj is None:
                continue

            current_price = price_obj.price
            if not self._condition_met(rule, current_price):
                continue

            if not self._can_trigger(rule, now):
                continue

            # Rule fires!
            rule.last_triggered = now

            message = (
                f"Alert {rule.id}: {rule.symbol} {rule.operator} "
                f"{rule.threshold} (current: {current_price:.2f})"
            )

            event = AlertEvent(
                rule_id=rule.id,
                symbol=rule.symbol,
                price=current_price,
                triggered_at=now,
                message=message,
            )
            events.append(event)
            self._events.append(event)

        # Keep only last 50 events
        if len(self._events) > 50:
            self._events = self._events[-50:]

        return events

    def recent_events(self) -> List[AlertEvent]:
        return list(self._events)
