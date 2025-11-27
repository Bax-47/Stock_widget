import json
import os
from typing import Optional
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from models import AlertEvent


class WebexNotifier:
    """
    Sends alert messages to a WebEx space using a bot token.

    Requires environment variables:
      - WEBEX_BOT_TOKEN : Bot access token
      - WEBEX_ROOM_ID   : Target roomId to post messages into

    If these are not set, sending is silently skipped
    (so your backend still works in environments without WebEx).
    """

    def __init__(self):
        self.token = os.getenv("WEBEX_BOT_TOKEN")
        self.room_id = os.getenv("WEBEX_ROOM_ID")

        if not self.token or not self.room_id:
            print("[webex] WEBEX_BOT_TOKEN or WEBEX_ROOM_ID not set; WebEx alerts disabled.")
            self.enabled = False
        else:
            print("[webex] WebEx notifier enabled (room-based).")
            self.enabled = True

    def _build_message_text(self, event: AlertEvent) -> str:
        return (
            f"🚨 Stock Alert\n"
            f"Rule ID: {event.rule_id}\n"
            f"Symbol: {event.symbol}\n"
            f"Triggered at: {event.triggered_at.isoformat()}\n"
            f"Price: {event.price:.2f}\n"
            f"Details: {event.message}"
        )

    def send_alert(self, event: AlertEvent) -> None:
        if not self.enabled:
            return

        url = "https://webexapis.com/v1/messages"
        text = self._build_message_text(event)

        body = {
            "roomId": self.room_id,
            "text": text,
        }
        data = json.dumps(body).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        req = Request(url, data=data, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=5) as resp:
                # We don't really need the response body; just ensure no exception is raised.
                resp.read()
            print(f"[webex] Alert sent to WebEx for rule {event.rule_id} ({event.symbol}).")
        except HTTPError as e:
            print(f"[webex] HTTP error sending alert to WebEx: {e.code} {e.reason}")
        except URLError as e:
            print(f"[webex] Network error sending alert to WebEx: {e.reason}")
        except Exception as e:
            print(f"[webex] Unexpected error sending alert to WebEx: {e}")
