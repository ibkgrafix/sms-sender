"""SMS provider adapters. Add a class, register it, done."""
import os
import httpx


class SendResult:
    __slots__ = ("phone", "ok", "provider_id", "status", "error")

    def __init__(self, phone, ok, provider_id="", status="queued", error=""):
        self.phone, self.ok = phone, ok
        self.provider_id, self.status, self.error = provider_id, status, error


class Provider:
    name = "base"
    label = "Base"
    per_sms = 0.0
    currency = "USD"

    def send(self, phone, body) -> SendResult:
        raise NotImplementedError

    def status(self, provider_id) -> str:
        return ""

    def balance(self):
        return None


class Pingram(Provider):
    name, label, per_sms, currency = "pingram", "Pingram", 0.0100, "USD"
    URL = "https://api.pingram.io/sms"
    TYPE = "bulk_sms"

    def __init__(self, key, sender=""):
        self.key, self.sender = key, sender

    def send(self, phone, body):
        payload = {"type": self.TYPE, "to": phone, "message": body}
        if self.sender:
            payload["from"] = self.sender
        try:
            r = httpx.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                json=payload, timeout=30,
            )
            d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except Exception as e:
            return SendResult(phone, False, error=str(e))
        if r.status_code >= 400:
            err = (d.get("error") or {}).get("message") or d.get("message") or f"HTTP {r.status_code}"
            fix = (d.get("error") or {}).get("fix") or ""
            return SendResult(phone, False, error=f"{err} {fix}".strip())
        return SendResult(phone, True, provider_id=d.get("trackingId", ""), status="sent")

    def status(self, tracking_id):
        try:
            r = httpx.get(
                f"https://api.pingram.io/logs/status/{tracking_id}",
                headers={"Authorization": f"Bearer {self.key}"}, timeout=20,
            )
            d = r.json()
            return (d.get("status") or d.get("entries", [{}])[0].get("status") or "").lower()
        except Exception:
            return ""


class Contiguity(Provider):
    name, label, per_sms, currency = "contiguity", "Contiguity", 0.005, "USD"
    BASE = "https://api.contiguity.com/send"

    def __init__(self, key, sender=""):
        self.key, self.sender = key, sender

    def send(self, phone, body):
        payload = {"to": phone, "message": body}
        if self.sender:
            payload["from"] = self.sender
        try:
            r = httpx.post(
                f"{self.BASE}/text",
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                json=payload, timeout=30,
            )
            d = r.json()
        except Exception as e:
            return SendResult(phone, False, error=str(e))
        if r.status_code >= 400:
            return SendResult(phone, False, error=(d.get("data") or {}).get("error") or f"HTTP {r.status_code}")
        return SendResult(phone, True, provider_id=(d.get("data") or {}).get("message_id", ""), status="sent")


class MsgRush(Provider):
    name, label, per_sms, currency = "msgrush", "MsgRush", 0.015, "EUR"
    BASE = "https://msgrush-backend-258291301565.us-central1.run.app/api"

    def __init__(self, key, sender_id="MsgRush"):
        self.key, self.sender_id = key, sender_id

    def _h(self):
        return {"X-API-Key": self.key, "Content-Type": "application/json"}

    def send(self, phone, body):
        try:
            r = httpx.post(
                f"{self.BASE}/sms-api/send", headers=self._h(),
                json={"sender_id": self.sender_id, "recipients": [phone], "message": body},
                timeout=30,
            )
            d = r.json()
        except Exception as e:
            return SendResult(phone, False, error=str(e))
        if not d.get("success"):
            return SendResult(phone, False, error=d.get("error", f"HTTP {r.status_code}"))
        return SendResult(phone, True, status="sent")

    def balance(self):
        for path in ("/balance", "/sms-api/balance"):
            try:
                r = httpx.get(f"{self.BASE}{path}", headers=self._h(), timeout=15)
                if r.status_code < 400:
                    d = r.json()
                    return float(d.get("balance", 0)), d.get("currency", "EUR")
            except Exception:
                pass
        return None


class SMSRoute(Provider):
    name, label, per_sms, currency = "smsroute", "SMSRoute", 0.0125, "USD"
    BASE = "https://api.sendsmsnokyc.com"

    def __init__(self, key, sender="", campaign_id=""):
        self.key, self.sender, self.campaign_id = key, sender, campaign_id

    def _h(self):
        return {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def send(self, phone, body):
        payload = {"to": phone, "body": body}
        if self.sender:
            payload["from"] = self.sender
        if self.campaign_id:
            payload["campaign_id"] = self.campaign_id
        try:
            r = httpx.post(f"{self.BASE}/sms/send", headers=self._h(), json=payload, timeout=30)
            d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except Exception as e:
            return SendResult(phone, False, error=str(e))
        if r.status_code >= 400:
            return SendResult(phone, False, error=d.get("error") or f"HTTP {r.status_code}: {r.text[:160]}")
        return SendResult(phone, True, provider_id=d.get("messageId", ""), status=d.get("status", "queued"))

    def balance(self):
        try:
            r = httpx.get(f"{self.BASE}/account/balance", headers=self._h(), timeout=15)
            d = r.json()
            return float(d.get("balance", 0)), d.get("currency", "EUR")
        except Exception:
            return None


class Textbelt(Provider):
    name, label, per_sms, currency = "textbelt", "Textbelt", 0.025, "USD"
    URL = "https://textbelt.com/text"

    def __init__(self, key):
        self.key = key

    def send(self, phone, body):
        try:
            r = httpx.post(self.URL, data={"phone": phone, "message": body, "key": self.key}, timeout=20)
            d = r.json()
        except Exception as e:
            return SendResult(phone, False, error=str(e))
        if not d.get("success"):
            return SendResult(phone, False, error=d.get("error", "unknown"))
        return SendResult(phone, True, provider_id=str(d.get("textId", "")), status="sent")


def _build(name):
    if name == "pingram":
        return Pingram(os.getenv("PINGRAM_KEY", ""), os.getenv("PINGRAM_FROM", ""))
    if name == "contiguity":
        return Contiguity(os.getenv("CONTIGUITY_KEY", ""), os.getenv("CONTIGUITY_FROM", ""))
    if name == "msgrush":
        return MsgRush(os.getenv("MSGRUSH_KEY", ""), os.getenv("MSGRUSH_SENDER_ID", "MsgRush"))
    if name == "smsroute":
        return SMSRoute(os.getenv("SMSROUTE_KEY", ""), os.getenv("SMSROUTE_FROM", ""), os.getenv("SMSROUTE_CAMPAIGN_ID", ""))
    if name == "textbelt":
        return Textbelt(os.getenv("TEXTBELT_KEY", ""))
    raise ValueError(f"unknown provider {name!r}")


def current() -> Provider:
    return _build(os.getenv("SMS_PROVIDER", "pingram"))


def available():
    return [("pingram", "Pingram"), ("contiguity", "Contiguity"),
            ("msgrush", "MsgRush"), ("smsroute", "SMSRoute"), ("textbelt", "Textbelt")]