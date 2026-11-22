"""Development outbox: the last messages the console adapter "sent" (invites, codes, links).

Only routed when DEBUG is on and MESSAGING_ADAPTER is "console" (never in staging/production),
so you can open invitation links and read codes without a phone or mail server.
"""

from django.http import HttpRequest, JsonResponse

from .messaging import SENT


def outbox(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "messages": [
                {"channel": m.channel, "to": m.to, "subject": m.subject, "body": m.body}
                for m in reversed(SENT)
            ]
        }
    )
