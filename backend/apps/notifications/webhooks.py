"""Provider webhooks: delivery reports, replies (1 = done, 2 = reschedule), STOP and bounces.

* WhatsApp Cloud API: GET verifies the subscription (hub.verify_token); POST is signed with
  the app secret (X-Hub-Signature-256) and is rejected otherwise.
* Africa's Talking (SMS delivery reports and incoming messages) and email (bounce events):
  the URL carries ?token=<WEBHOOK_TOKEN>.

Webhooks always answer 200 once authenticated, so providers do not retry forever.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import services
from .models import Channel, ChannelContact, DeliveryStatus

logger = logging.getLogger("smartfarm.webhooks")

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "acha", "sitisha"}
DONE_WORDS = {"1", "done", "yes", "imekamilika", "ndiyo"}
LATER_WORDS = {"2", "reschedule", "later", "kesho", "baadaye"}

WHATSAPP_STATUS = {
    "sent": DeliveryStatus.SENT,
    "delivered": DeliveryStatus.DELIVERED,
    "read": DeliveryStatus.READ,
    "failed": DeliveryStatus.FAILED,
}
AT_STATUS = {
    "Success": DeliveryStatus.DELIVERED,
    "Sent": DeliveryStatus.SENT,
    "Buffered": DeliveryStatus.SENT,
    "Submitted": DeliveryStatus.SENT,
    "Failed": DeliveryStatus.FAILED,
    "Rejected": DeliveryStatus.FAILED,
}


def _token_ok(request: HttpRequest) -> bool:
    expected = settings.WEBHOOK_TOKEN
    given = request.GET.get("token", "")
    return bool(expected) and hmac.compare_digest(expected, given)


def handle_text(channel: str, sender: str, text: str, out_id: str | None = None) -> str:
    word = text.strip().lower().rstrip(".!")
    if word in STOP_WORDS:
        return "opted_out" if services.opt_out(channel, sender) else "unknown_sender"
    if word in DONE_WORDS or word == "done" or text.startswith("done:"):
        return services.quick_reply(channel, sender, "done", out_id)
    if word in LATER_WORDS or text.startswith("reschedule:"):
        return services.quick_reply(channel, sender, "reschedule", out_id)
    return "ignored"


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        if (
            request.GET.get("hub.mode") == "subscribe"
            and settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
            and hmac.compare_digest(
                request.GET.get("hub.verify_token", ""), settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
            )
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse(status=403)
    secret = settings.WHATSAPP_APP_SECRET.encode()
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret, request.body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(signature, expected):
        return HttpResponse(status=403)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"ok": False}, status=400)
    results: list[str] = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            for st in value.get("statuses", []):
                mapped = WHATSAPP_STATUS.get(st.get("status", ""))
                if mapped:
                    error = "; ".join(e.get("title", "") for e in st.get("errors", []))
                    services.update_status(Channel.WHATSAPP, st.get("id", ""), mapped, error)
            for msg in value.get("messages", []):
                results.append(_whatsapp_message(msg))
    return JsonResponse({"ok": True, "results": results})


def _whatsapp_message(msg: dict[str, Any]) -> str:
    sender = msg.get("from", "")
    kind = msg.get("type")
    payload = ""
    if kind == "button":
        payload = (msg.get("button") or {}).get("payload", "") or (msg.get("button") or {}).get(
            "text", ""
        )
    elif kind == "interactive":
        payload = ((msg.get("interactive") or {}).get("button_reply") or {}).get("id", "")
    elif kind == "text":
        payload = (msg.get("text") or {}).get("body", "")
    if ":" in payload and payload.split(":", 1)[0] in ("done", "reschedule"):
        answer, out_id = payload.split(":", 1)
        return services.quick_reply(Channel.WHATSAPP, sender, answer, out_id)
    return handle_text(Channel.WHATSAPP, sender, payload)


@csrf_exempt
@require_http_methods(["POST"])
def sms_delivery(request: HttpRequest) -> HttpResponse:
    if not _token_ok(request):
        return HttpResponse(status=403)
    data = request.POST
    mapped = AT_STATUS.get(data.get("status", ""))
    if mapped:
        services.update_status(
            Channel.SMS, data.get("id", ""), mapped, data.get("failureReason", "")
        )
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def sms_inbound(request: HttpRequest) -> HttpResponse:
    if not _token_ok(request):
        return HttpResponse(status=403)
    result = handle_text(Channel.SMS, request.POST.get("from", ""), request.POST.get("text", ""))
    return JsonResponse({"ok": True, "result": result})


@csrf_exempt
@require_http_methods(["POST"])
def email_events(request: HttpRequest) -> HttpResponse:
    """Bounce / complaint events. Accepts a list of {"email", "event"} objects (SendGrid style)
    or one object; hard bounces, drops and spam complaints stop email to that address."""
    if not _token_ok(request):
        return HttpResponse(status=403)
    try:
        body = json.loads(request.body or b"[]")
    except ValueError:
        return JsonResponse({"ok": False}, status=400)
    events = body if isinstance(body, list) else [body]
    stopped = 0
    for ev in events:
        kind = str(ev.get("event") or ev.get("type") or "").lower()
        address = str(ev.get("email") or ev.get("recipient") or "").strip()
        if kind in ("bounce", "bounced", "dropped", "spamreport", "complaint") and address:
            stopped += ChannelContact.objects.filter(
                channel=Channel.EMAIL, address__iexact=address
            ).update(bounced_at=timezone.now())
        message_id = ev.get("smtp-id") or ev.get("message_id") or ""
        if message_id and kind in ("delivered", "open", "bounce", "dropped"):
            mapped = {"delivered": DeliveryStatus.DELIVERED, "open": DeliveryStatus.READ}.get(
                kind, DeliveryStatus.FAILED
            )
            services.update_status(Channel.EMAIL, message_id, mapped, kind)
    return JsonResponse({"ok": True, "stopped": stopped})
