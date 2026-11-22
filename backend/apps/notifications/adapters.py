"""Provider adapters. One interface: send(to, template, params, language) -> SendResult.

* Console: development and tests. Logs the message; nothing leaves the server.
* Email: Django's mail backend (SMTP, or SendGrid / Mailgun / SES over SMTP).
* Africa's Talking: SMS in Uganda, Kenya, Tanzania and Rwanda (sandbox when the username is
  "sandbox").
* WhatsApp Cloud API: pre-approved templates in English and Kiswahili.

Keys come from environment variables only (see .env.example), never from the database.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger("smartfarm.messages")
TIMEOUT = 15


class ProviderError(Exception):
    """The provider refused or failed. ``retry`` False means trying again will not help."""

    def __init__(self, message: str, retry: bool = True) -> None:
        super().__init__(message)
        self.retry = retry


@dataclass
class SendResult:
    provider_id: str
    cost: str = ""
    status: str = "sent"  # some providers confirm delivery straight away


@dataclass
class Message:
    to: str
    template: str
    params: dict[str, Any] = field(default_factory=dict)
    language: str = "en"
    # Plain text for SMS / email bodies and the console.
    text: str = ""
    subject: str = ""


class Adapter:
    channel: ClassVar[str]

    def send(self, message: Message) -> SendResult:
        raise NotImplementedError


class ConsoleAdapter(Adapter):
    """Prints messages to the log; keeps them in messaging.SENT for the dev outbox and tests."""

    def __init__(self, channel: str) -> None:
        self.channel = channel  # type: ignore[misc]

    def send(self, message: Message) -> SendResult:
        from .messaging import SENT, SentMessage

        logger.info(
            "[console %s] to=%s template=%s %s",
            self.channel,
            message.to,
            message.template,
            message.text,
        )
        SENT.append(SentMessage(self.channel, message.to, message.text, message.subject))
        return SendResult(provider_id=f"console-{uuid.uuid4().hex[:12]}")


class EmailAdapter(Adapter):
    channel = "email"

    def send(self, message: Message) -> SendResult:
        from .messaging import SENT, SentMessage

        message_id = f"<{uuid.uuid4().hex}@smartfarm>"
        html = render_to_string(
            "notifications/email.html",
            {**message.params, "text": message.text, "subject": message.subject},
        )
        email = EmailMultiAlternatives(
            subject=message.subject or "Smart Farm",
            body=message.text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[message.to],
            headers={"Message-ID": message_id},
        )
        email.attach_alternative(html, "text/html")
        try:
            email.send()
        except Exception as exc:
            raise ProviderError(f"Email could not be sent: {exc}") from exc
        SENT.append(SentMessage("email", message.to, message.text, message.subject))
        return SendResult(provider_id=message_id)


class AfricasTalkingAdapter(Adapter):
    channel = "sms"

    @property
    def url(self) -> str:
        host = (
            "api.sandbox.africastalking.com"
            if settings.AFRICASTALKING_USERNAME == "sandbox"
            else "api.africastalking.com"
        )
        return f"https://{host}/version1/messaging"

    def send(self, message: Message) -> SendResult:
        if not settings.AFRICASTALKING_API_KEY:
            raise ProviderError(
                "Africa's Talking is not configured (AFRICASTALKING_API_KEY).", retry=False
            )
        data = {
            "username": settings.AFRICASTALKING_USERNAME,
            "to": message.to,
            "message": message.text,
        }
        if settings.AFRICASTALKING_SENDER_ID and settings.AFRICASTALKING_USERNAME != "sandbox":
            data["from"] = settings.AFRICASTALKING_SENDER_ID
        try:
            res = requests.post(
                self.url,
                data=data,
                timeout=TIMEOUT,
                headers={"apiKey": settings.AFRICASTALKING_API_KEY, "Accept": "application/json"},
            )
        except requests.RequestException as exc:
            raise ProviderError(f"Africa's Talking unreachable: {exc}") from exc
        if res.status_code >= 500:
            raise ProviderError(f"Africa's Talking error {res.status_code}")
        if res.status_code >= 400:
            raise ProviderError(
                f"Africa's Talking refused the message: {res.text[:200]}", retry=False
            )
        recipients = (res.json().get("SMSMessageData") or {}).get("Recipients") or []
        if not recipients:
            raise ProviderError(
                f"Africa's Talking did not accept the message: {res.text[:200]}", retry=False
            )
        r = recipients[0]
        if r.get("status") not in ("Success", "Sent", "Queued", "Buffered"):
            raise ProviderError(
                f"SMS rejected: {r.get('status')}", retry=r.get("statusCode") in (500, 501, 502)
            )
        return SendResult(provider_id=r.get("messageId", ""), cost=r.get("cost", ""))


class WhatsAppCloudAdapter(Adapter):
    channel = "whatsapp"
    API_VERSION = "v21.0"

    def send(self, message: Message) -> SendResult:
        if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
            raise ProviderError(
                "WhatsApp is not configured (WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID).",
                retry=False,
            )
        url = f"https://graph.facebook.com/{self.API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        body_params = [
            {"type": "text", "text": str(v)[:1000]} for v in message.params.get("body", [])
        ]
        components: list[dict[str, Any]] = []
        if body_params:
            components.append({"type": "body", "parameters": body_params})
        for index, payload in enumerate(message.params.get("buttons", [])):
            components.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(index),
                    "parameters": [{"type": "payload", "payload": payload}],
                }
            )
        data: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": message.to.lstrip("+"),
            "type": "template",
            "template": {
                "name": message.template,
                "language": {"code": message.language},
                "components": components,
            },
        }
        try:
            res = requests.post(
                url,
                json=data,
                timeout=TIMEOUT,
                headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            )
        except requests.RequestException as exc:
            raise ProviderError(f"WhatsApp unreachable: {exc}") from exc
        if res.status_code >= 500 or res.status_code == 429:
            raise ProviderError(f"WhatsApp error {res.status_code}")
        if res.status_code >= 400:
            error = (
                (res.json().get("error") or {}).get("message", res.text[:200])
                if res.content
                else res.text
            )
            raise ProviderError(f"WhatsApp refused the message: {error}", retry=False)
        messages = res.json().get("messages") or [{}]
        return SendResult(provider_id=messages[0].get("id", ""))


def get_adapter(channel: str) -> Adapter:
    if channel == "email":
        return EmailAdapter()
    name = {"sms": settings.SMS_ADAPTER, "whatsapp": settings.WHATSAPP_ADAPTER}[channel]
    if name == "console":
        return ConsoleAdapter(channel)
    if name == "africastalking":
        return AfricasTalkingAdapter()
    if name == "whatsapp_cloud":
        return WhatsAppCloudAdapter()
    raise ProviderError(f"Unknown {channel} adapter '{name}'", retry=False)
