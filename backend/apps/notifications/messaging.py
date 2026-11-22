"""Outbound messages for account flows (invitations, login details, codes, reset links).

SMS and WhatsApp go through the same provider adapters as notifications (adapters.py); with the
console adapter the message is logged, and kept in ``SENT`` so development tools and tests can
read it. Email goes through Django's mail
backend (Mailpit locally). Messages are sent after the database transaction commits, through
Celery, so no request waits on a provider.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from apps.core.utils import after_commit

logger = logging.getLogger("smartfarm.messages")


@dataclass(frozen=True)
class SentMessage:
    channel: str
    to: str
    body: str
    subject: str = ""


SENT: deque[SentMessage] = deque(maxlen=200)


def queue(channel: str, to: str, body: str, subject: str = "") -> None:
    """Send after commit, in the background."""
    after_commit(lambda: deliver.delay(channel, to, body, subject))


@shared_task(
    name="notifications.deliver_account_message",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    max_retries=3,
)
def deliver(channel: str, to: str, body: str, subject: str = "") -> None:
    from .adapters import Message, get_adapter

    if channel == "email":
        send_mail(subject or "Smart Farm", body, settings.DEFAULT_FROM_EMAIL, [to])
        SENT.append(SentMessage(channel, to, body, subject))
        return
    adapter = get_adapter(channel)
    if (
        channel == "whatsapp"
        and adapter.channel == "whatsapp"
        and not isinstance(adapter, _console())
    ):
        # Outside a conversation WhatsApp only delivers approved templates.
        message = Message(
            to=to, template="smartfarm_account_message", params={"body": [body]}, text=body
        )
    else:
        message = Message(to=to, template="account", text=body, subject=subject)
    adapter.send(message)


def _console() -> type:
    from .adapters import ConsoleAdapter

    return ConsoleAdapter
