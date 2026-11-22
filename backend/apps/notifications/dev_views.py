"""Development outbox: the last messages the console adapter "sent" (invites, codes, links).

Only routed when DEBUG is on and MESSAGING_ADAPTER is "console" (never in staging/production),
so you can open invitation links and read codes without a phone or mail server. Browsers get a
readable page with clickable links; other clients (tests) get JSON.
"""

import re

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.html import escape

from .messaging import SENT

URL = re.compile(r"(https?://[^\s<]+)")
CODE = re.compile(r"\b(\d{6})\b")

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="15"><title>Smart Farm outbox</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;background:#f6f8f6;color:#1a2b1c;margin:0;padding:24px}}
h1{{font-size:22px;margin:0 0 4px}} p.note{{color:#5b6b5d;margin:0 0 20px;font-size:14px}}
.msg{{background:#fff;border:1px solid #e2e8e2;border-radius:12px;padding:16px;margin:0 0 12px;max-width:760px}}
.meta{{font-size:13px;color:#5b6b5d;margin-bottom:8px}} .chan{{font-weight:700;color:#1b5e20;text-transform:uppercase}}
.body{{white-space:pre-wrap;line-height:1.5}} .code{{font-size:22px;font-weight:800;letter-spacing:3px;background:#e8f5e9;padding:2px 8px;border-radius:6px}}
a{{color:#1b5e20;font-weight:600;word-break:break-all}}
</style></head><body><h1>Smart Farm outbox (development only)</h1>
<p class="note">Messages Smart Farm would have sent by email, SMS or WhatsApp. Newest first. Click a link to open it. This page refreshes every 15 seconds.</p>
{items}</body></html>"""


def _render(body: str) -> str:
    html: str = str(escape(body))
    html = URL.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', html)
    return CODE.sub(r'<span class="code">\1</span>', html)


def outbox(request: HttpRequest) -> HttpResponse:
    messages = list(reversed(SENT))
    if "text/html" in request.headers.get("Accept", ""):
        items = (
            "".join(
                f'<div class="msg"><div class="meta"><span class="chan">{escape(m.channel)}</span> to '
                f"{escape(m.to)}{' &middot; ' + escape(m.subject) if m.subject else ''}</div>"
                f'<div class="body">{_render(m.body)}</div></div>'
                for m in messages
            )
            or '<p class="note">No messages yet.</p>'
        )
        return HttpResponse(PAGE.format(items=items))
    return JsonResponse(
        {
            "messages": [
                {"channel": m.channel, "to": m.to, "subject": m.subject, "body": m.body}
                for m in messages
            ]
        }
    )
