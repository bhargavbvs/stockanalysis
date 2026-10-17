"""Delivery: WhatsApp, Telegram, Discord, email, generic webhook.

Each channel is used only when its settings are present. Every send returns
True/False and logs failures – a broken channel never stops the scanner.

WhatsApp options
  * CallMeBot (default): free for personal use, messages go to your own number.
    One-time setup: message the CallMeBot WhatsApp number (see callmebot.com)
    with "I allow callmebot to send me messages" and it replies with an API key.
  * Twilio: paid and more robust, but WhatsApp only allows free-form messages
    within 24h of your last message to the Twilio number; outside that window
    you need an approved template. Fine if you reply to it daily.
"""

from __future__ import annotations

import json
import logging
import smtplib
import time
import urllib.parse
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from email.mime.text import MIMEText
from typing import Any, Optional

import requests

from .report import split_message, to_discord, to_plain, to_telegram_html

log = logging.getLogger(__name__)

TIMEOUT = 20


def _json_default(o: Any):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if is_dataclass(o):
        return asdict(o)
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


class Notifier:
    def __init__(self, settings, session: Optional[requests.Session] = None):
        self.s = settings
        self.http = session or requests.Session()
        self._secrets = [x for x in (settings.telegram_token, settings.callmebot_api_key, settings.twilio_auth_token,
                                     settings.email_password, settings.whatsapp_phone) if x and len(x) >= 4]

    def _redact(self, text: str) -> str:
        """Never let a token, API key or phone number reach the logs."""
        for secret in self._secrets:
            text = text.replace(secret, "***").replace(urllib.parse.quote(secret, safe=""), "***")
        return text

    # ------------------------------------------------------------------ #
    @property
    def channels(self) -> list[str]:
        s, out = self.s, []
        if s.whatsapp_phone and (
            (s.whatsapp_provider == "callmebot" and s.callmebot_api_key)
            or (s.whatsapp_provider == "twilio" and s.twilio_account_sid and s.twilio_auth_token)
        ):
            out.append("whatsapp")
        if s.telegram_token and s.telegram_chat_id:
            out.append("telegram")
        if s.discord_webhook_url:
            out.append("discord")
        if s.email_enabled:
            out.append("email")
        if s.webhook_url:
            out.append("webhook")
        return out

    def send(self, text: str, subject: str = "Stock bot", payload: Optional[dict] = None) -> dict[str, bool]:
        results = {}
        for ch in self.channels:
            try:
                if ch == "whatsapp":
                    results[ch] = self.send_whatsapp(text)
                elif ch == "telegram":
                    results[ch] = self.send_telegram(text)
                elif ch == "discord":
                    results[ch] = self.send_discord(text)
                elif ch == "email":
                    results[ch] = self.send_email(subject, text)
                elif ch == "webhook":
                    results[ch] = self.send_webhook({"subject": subject, "text": to_plain(text), **(payload or {})})
            except Exception as exc:
                # exception text from requests contains the full URL (with keys) – log the type only
                log.error("%s send failed: %s", ch, type(exc).__name__)
                results[ch] = False
        if not self.channels:
            log.warning("No notification channel configured – message not sent:\n%s", to_plain(text))
        return results

    # ------------------------------------------------------------------ #
    def send_whatsapp(self, text: str) -> bool:
        s = self.s
        ok = True
        if s.whatsapp_provider == "callmebot":
            # sized by URL-encoded length: emoji / non-Latin text expands a lot
            chunks = split_message(text, 3000, measure=lambda t: len(urllib.parse.quote(t, safe="")))
        else:
            chunks = split_message(text, 1550)
        for i, chunk in enumerate(chunks):
            if i:
                time.sleep(3)  # CallMeBot drops messages sent back-to-back
            if s.whatsapp_provider == "twilio":
                r = self.http.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
                    auth=(s.twilio_account_sid, s.twilio_auth_token),
                    data={"From": s.twilio_whatsapp_from, "To": f"whatsapp:{s.whatsapp_phone}", "Body": chunk},
                    timeout=TIMEOUT,
                )
                good = r.status_code in (200, 201)
            else:
                r = self.http.get(
                    "https://api.callmebot.com/whatsapp.php",
                    params={"phone": s.whatsapp_phone, "text": chunk, "apikey": s.callmebot_api_key},
                    timeout=TIMEOUT,
                )
                good = r.status_code == 200 and "error" not in r.text.lower()
            if not good:
                log.error("WhatsApp (%s) failed: HTTP %s %s", s.whatsapp_provider, r.status_code,
                          self._redact(r.text[:200]))
            ok &= good
        return ok

    def send_telegram(self, text: str) -> bool:
        ok = True
        url = f"https://api.telegram.org/bot{self.s.telegram_token}/sendMessage"
        for chunk in split_message(text, 3500):
            data = {"chat_id": self.s.telegram_chat_id, "text": to_telegram_html(chunk),
                    "parse_mode": "HTML", "disable_web_page_preview": "true"}
            for attempt in range(3):
                r = self.http.post(url, data=data, timeout=TIMEOUT)
                if r.status_code == 429:
                    try:
                        wait = r.json().get("parameters", {}).get("retry_after", 5)
                    except Exception:
                        wait = 5
                    time.sleep(min(int(wait), 30))
                    continue
                if r.status_code == 400 and "parse_mode" in data:
                    # e.g. overlapping *bold _italic* marks -> resend as plain text
                    data = {"chat_id": self.s.telegram_chat_id, "text": to_plain(chunk),
                            "disable_web_page_preview": "true"}
                    continue
                break
            if r.status_code != 200:
                log.error("Telegram failed: HTTP %s %s", r.status_code, self._redact(r.text[:200]))
                ok = False
        return ok

    def send_discord(self, text: str) -> bool:
        ok = True
        for chunk in split_message(text, 1900):
            r = self.http.post(self.s.discord_webhook_url, json={"content": to_discord(chunk)}, timeout=TIMEOUT)
            if r.status_code not in (200, 204):
                log.error("Discord failed: HTTP %s %s", r.status_code, self._redact(r.text[:200]))
                ok = False
        return ok

    def send_email(self, subject: str, text: str) -> bool:
        s = self.s
        msg = MIMEText(to_plain(text), "plain", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subject, s.email_sender, s.email_recipient
        with smtplib.SMTP(s.email_smtp_server, s.email_smtp_port, timeout=TIMEOUT) as server:
            server.starttls()
            server.login(s.email_sender, s.email_password)
            server.send_message(msg)
        return True

    def send_webhook(self, payload: dict) -> bool:
        r = self.http.post(self.s.webhook_url, data=json.dumps(payload, default=_json_default),
                           headers={"Content-Type": "application/json"}, timeout=TIMEOUT)
        if r.status_code >= 300:
            log.error("Webhook failed: HTTP %s %s", r.status_code, self._redact(r.text[:200]))
            return False
        return True
