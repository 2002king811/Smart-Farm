"""Outbound messages for account flows (invitations, login details, codes, reset links).

Phase 6 replaces this with the full notification pipeline (outbox, provider adapters, delivery
status). Until then SMS and WhatsApp use the console adapter: the message is logged, and kept
in ``SENT`` so development tools and tests can read it. Email goes through Django's mail
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


class MessagingNotConfigured(RuntimeError):
    pass


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
    if channel == "email":
        send_mail(subject or "Smart Farm", body, settings.DEFAULT_FROM_EMAIL, [to])
        SENT.append(SentMessage(channel, to, body, subject))
        return
    if settings.MESSAGING_ADAPTER != "console":
        # Real Africa's Talking / WhatsApp Cloud API adapters arrive in phase 6.
        raise MessagingNotConfigured(f"No {channel} adapter configured yet")
    logger.info("[console %s] to=%s %s", channel, to, body)
    SENT.append(SentMessage(channel, to, body, subject))
