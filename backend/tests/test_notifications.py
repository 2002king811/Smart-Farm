"""Phase 6: notifications – recipients, preferences, quiet hours, delivery, retries, allowance,
scheduled reminders, webhooks (status, STOP, quick replies, bounces) and the API."""

import datetime as dt
import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
import requests
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import Role
from apps.calendar import services as cal
from apps.calendar.models import Activity, ActivityStatus
from apps.notifications import adapters, schedules, services
from apps.notifications.adapters import Message, ProviderError
from apps.notifications.messaging import SENT
from apps.notifications.models import (
    ChannelContact,
    DeliveryStatus,
    Notification,
    NotificationSettings,
    OutboundMessage,
)
from tests.factories import ActivityFactory, FeedItemFactory

pytestmark = pytest.mark.django_db
EAT = ZoneInfo("Africa/Kampala")


@pytest.fixture
def farm(farm_a):  # type: ignore[no-untyped-def]
    farm_a.timezone = "Africa/Kampala"
    farm_a.save()
    cal.seed_categories(farm_a)
    return farm_a


def person(
    member, farm, role=Role.FARM_MANAGER, channels=("in_app", "whatsapp", "sms", "email"), n=1
):  # type: ignore[no-untyped-def]
    user = member(farm, role)
    user.phone = f"+25677200{n:04d}"
    user.phone_verified = True
    user.email_verified = True
    user.alert_channels = list(channels)
    user.save()
    NotificationSettings.unscoped.create(farm=farm, user=user, quiet_hours_enabled=False)
    return user


def at(hour: int, minute: int = 0, day: dt.date | None = None) -> dt.datetime:
    day = day or timezone.now().astimezone(EAT).date()
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=EAT)


# --- The phase "done when": an assigned task reaches the right people on the right channels --------


def test_task_assignment_reaches_assignee_on_enabled_channels(farm, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    worker = person(member, farm, Role.LIVESTOCK_ATTENDANT)
    res = client_for(admin_a, farm).post(
        "/api/v1/activities",
        {
            "title": "Dip the herd",
            "date": str(timezone.localdate() + timedelta(days=2)),
            "assigned_to": str(worker.pk),
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    [note] = Notification.objects.filter(recipient=worker)
    assert note.event_type == "task.assigned" and note.title == "New task: Dip the herd"
    assert note.link == f"/activities?activity={res.json()['id']}"
    # Defaults for task.assigned: in-app, WhatsApp, SMS (not email).
    deliveries = {d.channel: d for d in note.deliveries.all()}
    assert set(deliveries) == {"whatsapp", "sms"}
    assert all(d.status == DeliveryStatus.SENT and d.provider_id for d in deliveries.values())
    sms = [m for m in SENT if m.channel == "sms"][-1]
    assert sms.to == worker.phone and "Reply 1 to mark done" in sms.body and len(sms.body) <= 160
    # The person who assigned it gets nothing.
    assert not Notification.objects.filter(recipient=admin_a).exists()

    me = client_for(worker, farm)
    assert me.get("/api/v1/notifications/unread-count").json() == {"unread": 1, "urgent": 0}
    rows = me.get("/api/v1/notifications").json()["results"]
    assert rows[0]["title"] == "New task: Dip the herd"
    assert {d["channel"]: d["status"] for d in rows[0]["deliveries"]} == {
        "whatsapp": "sent",
        "sms": "sent",
    }
    assert me.post(f"/api/v1/notifications/{note.pk}/read").json()["read"] is True
    assert me.get("/api/v1/notifications/unread-count").json()["unread"] == 0
    # Someone else cannot see or read it.
    assert client_for(admin_a, farm).get(f"/api/v1/notifications/{note.pk}").status_code == 404


def test_preferences_switch_channels_off(farm, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    worker = person(member, farm, Role.LIVESTOCK_ATTENDANT)
    me = client_for(worker, farm)
    data = me.get("/api/v1/notification-preferences").json()
    row = next(r for r in data["matrix"] if r["event_type"] == "task.assigned")
    assert row["channels"] == {"in_app": True, "whatsapp": True, "sms": True, "email": False}
    row["channels"]["sms"] = False
    data["settings"]["language"] = "sw"
    res = me.put("/api/v1/notification-preferences", data, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["settings"]["language"] == "sw"

    act = ActivityFactory(farm=farm, title="Kata kwato", assigned_to=worker)
    services.handle_event(
        "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(worker.pk)}
    )
    note = Notification.objects.get(recipient=worker)
    assert note.title == "Kazi mpya: Kata kwato"  # Kiswahili
    assert [d.channel for d in note.deliveries.all()] == ["whatsapp"]


def test_sign_up_channel_choice_sets_defaults(farm, member):  # type: ignore[no-untyped-def]
    only_app = person(member, farm, channels=("in_app",))
    assert services.enabled_channels(only_app, farm, "activity.overdue") == ["in_app"]


def test_missing_or_unconfirmed_contacts_are_recorded_as_failed(farm, member):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    user.phone_verified = False
    user.save()
    act = ActivityFactory(farm=farm, assigned_to=user)
    services.handle_event(
        "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(user.pk)}
    )
    deliveries = {d.channel: d for d in OutboundMessage.unscoped.all()}
    assert (
        deliveries["sms"].status == "failed"
        and deliveries["sms"].error == "Mobile number not confirmed"
    )
    assert not [m for m in SENT if m.channel in ("sms", "whatsapp")]


def test_whatsapp_needs_consent(farm, member, client_for):  # type: ignore[no-untyped-def]
    user = person(member, farm, channels=("in_app", "sms"))
    contacts = {
        c["channel"]: c for c in client_for(user, farm).get("/api/v1/channel-contacts").json()
    }
    assert contacts["whatsapp"]["opted_in"] is False
    assert contacts["whatsapp"]["problem"] == "WhatsApp not switched on"
    res = client_for(user, farm).patch(
        "/api/v1/channel-contacts/whatsapp", {"opted_in": True}, format="json"
    )
    assert res.json()["opted_in"] is True and res.json()["problem"] == ""
    # A new number needs consent again.
    user.phone = "+256772999999"
    user.save()
    assert (
        services.unreachable_reason(services.contact_for(user, "whatsapp"), "whatsapp")
        == "WhatsApp not switched on"
    )


# --- Recipients -------------------------------------------------------------------------------------


def test_health_alert_goes_to_managers_urgently(farm, admin_a, member):  # type: ignore[no-untyped-def]
    manager = person(member, farm, Role.FARM_MANAGER, n=2)
    worker = person(member, farm, Role.LIVESTOCK_ATTENDANT, n=3)
    services.handle_event(
        "health.alert",
        farm.pk,
        {
            "urgent": True,
            "title": "Health alert: YPA-001",
            "message": "Severe – off feed",
            "animal_id": "abc",
        },
    )
    assert set(Notification.objects.values_list("recipient", flat=True)) == {admin_a.pk, manager.pk}
    note = Notification.objects.get(recipient=manager)
    assert note.urgent and note.link == "/livestock/abc"
    assert not Notification.objects.filter(recipient=worker).exists()


def test_overdue_goes_to_assignee_and_managers_once(farm, admin_a, member):  # type: ignore[no-untyped-def]
    worker = person(member, farm, Role.LIVESTOCK_ATTENDANT)
    yesterday = timezone.now().astimezone(EAT).date() - timedelta(days=1)
    act = ActivityFactory(
        farm=farm,
        title="Weigh kids",
        date=yesterday,
        assigned_to=worker,
        status=ActivityStatus.OVERDUE,
    )
    overdue = Notification.objects.filter(event_type="activity.overdue")
    schedules.run_for_farm(farm, at(6, 30))
    assert overdue.count() == 0  # overdue goes out at 07:00
    schedules.run_for_farm(farm, at(7, 5))
    assert overdue.count() == 2
    schedules.run_for_farm(farm, at(8, 0))
    assert overdue.count() == 2  # once
    titles = set(overdue.values_list("recipient", "title"))
    assert titles == {(worker.pk, "Overdue: Weigh kids"), (admin_a.pk, "Overdue: Weigh kids")}
    assert act.pk


def test_unassigned_reminder_goes_to_managers(farm, admin_a, member):  # type: ignore[no-untyped-def]
    worker = person(member, farm, Role.LIVESTOCK_ATTENDANT)
    today = timezone.now().astimezone(EAT).date()
    vacc = cal.category(farm.pk, "vaccination")
    ActivityFactory(
        farm=farm,
        title="PPR vaccine",
        date=today + timedelta(days=3),
        category=vacc,
        reminder_days=[3, 1],
    )
    ActivityFactory(farm=farm, title="Clean pens", date=today, assigned_to=worker)
    assert schedules.run_for_farm(farm, at(5, 0)) == 0
    schedules.run_for_farm(farm, at(6, 1))
    events = set(Notification.objects.values_list("event_type", "recipient", "title"))
    assert ("vaccination.reminder", admin_a.pk, "Vaccination due: PPR vaccine") in events
    assert ("activity.due_today", worker.pk, "Due today: Clean pens") in events
    assert not any(e[1] == worker.pk and e[0] == "vaccination.reminder" for e in events)


def test_daily_digest_at_digest_time(farm, admin_a, member):  # type: ignore[no-untyped-def]
    manager = person(member, farm, Role.FARM_MANAGER, channels=("in_app", "email"))
    ActivityFactory(farm=farm, date=timezone.now().astimezone(EAT).date())
    FeedItemFactory(farm=farm, reorder_level=10)
    schedules.send_digests(farm, at(6, 59))
    assert not Notification.objects.filter(event_type="daily.summary").exists()
    schedules.send_digests(farm, at(7, 0))
    schedules.send_digests(farm, at(9, 0))
    [note] = Notification.objects.filter(event_type="daily.summary", recipient=manager)
    assert "Due today: 1" in note.message and "Feeds running low: 1" in note.message
    assert note.show_in_app is False  # email only by default
    assert [d.channel for d in note.deliveries.all()] == ["email"]
    email = [m for m in SENT if m.channel == "email"][-1]
    assert email.subject == note.title


def test_completed_task_tells_its_creator(farm, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    worker = person(member, farm, Role.LIVESTOCK_ATTENDANT)
    act = ActivityFactory(farm=farm, title="Trim hooves", assigned_to=worker, created_by=admin_a)
    res = client_for(worker, farm).post(f"/api/v1/activities/{act.pk}/complete", {}, format="json")
    assert res.status_code == 200, res.content
    note = Notification.objects.get(recipient=admin_a, event_type="activity.completed")
    assert note.title == "Completed: Trim hooves" and worker.full_name in note.message


# --- Quiet hours, retries, allowance -----------------------------------------------------------------


def test_quiet_hours_hold_sms_and_whatsapp_unless_urgent(farm, member):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    prefs = NotificationSettings.unscoped.get(user=user)
    prefs.quiet_hours_enabled = True
    prefs.save()
    assert services.quiet_until(prefs, farm, at(12, 0)) is None
    assert services.quiet_until(prefs, farm, at(22, 0)) == at(
        6, 0, at(22, 0).date() + timedelta(days=1)
    )
    assert services.quiet_until(prefs, farm, at(5, 0)) == at(6, 0)

    act = ActivityFactory(farm=farm, assigned_to=user)
    with mock.patch.object(
        services, "quiet_until", return_value=timezone.now() + timedelta(hours=3)
    ):
        services.handle_event(
            "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(user.pk)}
        )
        services.handle_event(
            "health.alert", farm.pk, {"urgent": True, "title": "Death", "message": "x"}
        )
    held = OutboundMessage.unscoped.filter(notification__event_type="task.assigned")
    assert {m.status for m in held} == {"queued"} and all(m.send_after for m in held)
    urgent = OutboundMessage.unscoped.filter(notification__event_type="health.alert")
    assert {m.status for m in urgent} == {"sent"}
    assert services.release_due() == 0  # not yet
    OutboundMessage.unscoped.filter(pk__in=held).update(
        send_after=timezone.now() - timedelta(minutes=1)
    )
    assert services.release_due() == 2
    assert {m.status for m in OutboundMessage.unscoped.filter(pk__in=held)} == {"sent"}


def test_failed_send_is_retried_three_times_then_failed(farm, member):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    act = ActivityFactory(farm=farm, assigned_to=user)
    with mock.patch.object(adapters.ConsoleAdapter, "send", side_effect=ProviderError("timeout")):
        services.handle_event(
            "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(user.pk)}
        )
        sms = OutboundMessage.unscoped.get(channel="sms")
        assert sms.status == "queued" and sms.attempts == 1 and sms.error == "timeout"
        for expected in (2, 3, 4):
            OutboundMessage.unscoped.filter(pk=sms.pk).update(send_after=timezone.now())
            services.release_due()
            sms.refresh_from_db()
            assert sms.attempts == expected
    assert sms.status == "failed"


def test_permanent_error_fails_at_once(farm, member):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    act = ActivityFactory(farm=farm, assigned_to=user)
    with mock.patch.object(
        adapters.ConsoleAdapter, "send", side_effect=ProviderError("bad number", retry=False)
    ):
        services.handle_event(
            "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(user.pk)}
        )
    assert {m.status for m in OutboundMessage.unscoped.all()} == {"failed"}


def test_allowance_warning_at_80_percent_and_stop_at_100(farm, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    admin_a.email, admin_a.email_verified = "boss@example.com", True
    admin_a.save()
    farm.sms_monthly_allowance = 5
    farm.save()
    user = person(member, farm, channels=("in_app", "sms"))
    for _ in range(4):
        act = ActivityFactory(farm=farm, assigned_to=user)
        services.handle_event(
            "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(user.pk)}
        )
    warnings = Notification.objects.filter(event_type="usage.warning")
    assert [w.recipient_id for w in warnings] == [admin_a.pk]
    assert warnings[0].title == "SMS allowance 80% used"
    usage = {
        u["channel"]: u for u in client_for(admin_a, farm).get("/api/v1/notifications/usage").json()
    }
    assert usage["sms"]["used"] == 4 and usage["sms"]["allowance"] == 5
    assert client_for(user, farm).get("/api/v1/notifications/usage").status_code == 403
    for _ in range(2):
        act = ActivityFactory(farm=farm, assigned_to=user)
        services.handle_event(
            "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(user.pk)}
        )
    last = OutboundMessage.unscoped.filter(channel="sms").order_by("-created_at").first()
    assert last.status == "failed" and last.error == "Monthly allowance used up"
    assert Notification.objects.filter(event_type="usage.warning").count() == 1  # once a month


def test_send_test_message(farm, member, client_for):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    res = client_for(user, farm).post(
        "/api/v1/notifications/test", {"channel": "sms"}, format="json"
    )
    assert res.status_code == 201, res.content
    assert [d["channel"] for d in res.json()["deliveries"]] == ["sms"]
    assert res.json()["deliveries"][0]["status"] == "sent"


def test_read_all(farm, member, client_for):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    for _ in range(3):
        services.send_test(user, farm, "email")
    me = client_for(user, farm)
    assert me.get("/api/v1/notifications/unread-count").json()["unread"] == 3
    assert me.get("/api/v1/notifications?unread=true").json()["count"] == 3
    me.post("/api/v1/notifications/read-all")
    assert me.get("/api/v1/notifications/unread-count").json()["unread"] == 0


# --- Webhooks ------------------------------------------------------------------------------------------


def signed(body: dict) -> tuple[bytes, str]:  # type: ignore[type-arg]
    raw = json.dumps(body).encode()
    return raw, "sha256=" + hmac.new(b"app-secret", raw, hashlib.sha256).hexdigest()


@override_settings(WHATSAPP_APP_SECRET="app-secret", WHATSAPP_WEBHOOK_VERIFY_TOKEN="verify-me")
def test_whatsapp_webhook_verifies_statuses_and_quick_replies(farm, member, client):  # type: ignore[no-untyped-def]
    ok = client.get(
        "/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=42"
    )
    assert ok.status_code == 200 and ok.content == b"42"
    assert (
        client.get("/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=no").status_code
        == 403
    )

    user = person(member, farm)
    act = ActivityFactory(farm=farm, assigned_to=user, status=ActivityStatus.PENDING)
    services.handle_event(
        "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(user.pk)}
    )
    wa = OutboundMessage.unscoped.get(channel="whatsapp")

    raw, sig = signed(
        {
            "entry": [
                {
                    "changes": [
                        {"value": {"statuses": [{"id": wa.provider_id, "status": "delivered"}]}}
                    ]
                }
            ]
        }
    )
    assert (
        client.post("/api/v1/webhooks/whatsapp", raw, content_type="application/json").status_code
        == 403
    )
    res = client.post(
        "/api/v1/webhooks/whatsapp",
        raw,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
    )
    assert res.status_code == 200
    wa.refresh_from_db()
    assert wa.status == "delivered"

    # "2 Reschedule" button moves it to tomorrow; "1 Mark done" completes it.
    msg = {
        "from": user.phone.lstrip("+"),
        "type": "button",
        "button": {"payload": f"reschedule:{wa.pk}", "text": "2"},
    }
    raw, sig = signed({"entry": [{"changes": [{"value": {"messages": [msg]}}]}]})
    res = client.post(
        "/api/v1/webhooks/whatsapp",
        raw,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
    )
    assert res.json()["results"] == ["rescheduled"]
    old_date = act.date
    act.refresh_from_db()
    assert act.date == max(old_date, cal.farm_today(farm)) + timedelta(days=1)
    msg = {"from": user.phone.lstrip("+"), "type": "text", "text": {"body": "1"}}
    raw, sig = signed({"entry": [{"changes": [{"value": {"messages": [msg]}}]}]})
    res = client.post(
        "/api/v1/webhooks/whatsapp",
        raw,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
    )
    assert res.json()["results"] == ["done"]
    act.refresh_from_db()
    assert act.status == ActivityStatus.COMPLETED and act.completed_by_id == user.pk


@override_settings(WEBHOOK_TOKEN="tok")
def test_sms_delivery_reports_and_stop(farm, member, client):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    services.send_test(user, farm, "sms")
    sms = OutboundMessage.unscoped.get(channel="sms")
    assert (
        client.post(
            "/api/v1/webhooks/sms/delivery", {"id": sms.provider_id, "status": "Success"}
        ).status_code
        == 403
    )
    client.post(
        "/api/v1/webhooks/sms/delivery?token=tok", {"id": sms.provider_id, "status": "Success"}
    )
    sms.refresh_from_db()
    assert sms.status == "delivered"
    client.post(
        "/api/v1/webhooks/sms/delivery?token=tok", {"id": sms.provider_id, "status": "Sent"}
    )
    sms.refresh_from_db()
    assert sms.status == "delivered"  # never goes backwards

    res = client.post(
        "/api/v1/webhooks/sms/inbound?token=tok", {"from": user.phone, "text": "STOP"}
    )
    assert res.json()["result"] == "opted_out"
    assert ChannelContact.objects.get(user=user, channel="sms").opted_out_at is not None
    services.send_test(user, farm, "sms")
    latest = OutboundMessage.unscoped.filter(channel="sms").order_by("-created_at").first()
    assert latest.status == "failed" and latest.error == "Opted out"


@override_settings(WEBHOOK_TOKEN="tok")
def test_sms_reply_1_marks_done(farm, member, client):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    act = ActivityFactory(farm=farm, assigned_to=user)
    services.handle_event(
        "task.assigned", farm.pk, {"activity_id": str(act.pk), "recipient_id": str(user.pk)}
    )
    res = client.post("/api/v1/webhooks/sms/inbound?token=tok", {"from": user.phone, "text": "1"})
    assert res.json()["result"] == "done"
    assert Activity.objects.get(pk=act.pk).status == ActivityStatus.COMPLETED
    res = client.post(
        "/api/v1/webhooks/sms/inbound?token=tok", {"from": "+256700000000", "text": "1"}
    )
    assert res.json()["result"] == "unknown_sender"


@override_settings(WEBHOOK_TOKEN="tok")
def test_email_bounce_stops_email(farm, member, client):  # type: ignore[no-untyped-def]
    user = person(member, farm)
    services.contact_for(user, "email")
    res = client.post(
        "/api/v1/webhooks/email?token=tok",
        [{"email": user.email.upper(), "event": "bounce"}],
        content_type="application/json",
    )
    assert res.json()["stopped"] == 1
    assert (
        services.unreachable_reason(services.contact_for(user, "email"), "email") == "Email bounced"
    )


# --- Adapters (HTTP mocked) ---------------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int, body: dict) -> None:  # type: ignore[type-arg]
        self.status_code, self._body = status, body
        self.text = json.dumps(body)
        self.content = self.text.encode()

    def json(self) -> dict:  # type: ignore[type-arg]
        return self._body


@override_settings(AFRICASTALKING_USERNAME="sandbox", AFRICASTALKING_API_KEY="k")
def test_africastalking_adapter():  # type: ignore[no-untyped-def]
    ok = {
        "SMSMessageData": {
            "Recipients": [
                {"status": "Success", "messageId": "ATX1", "cost": "UGX 35.0000", "statusCode": 101}
            ]
        }
    }
    with mock.patch.object(requests, "post", return_value=FakeResponse(201, ok)) as post:
        result = adapters.AfricasTalkingAdapter().send(
            Message(to="+256772000001", template="x", text="hi")
        )
    assert result.provider_id == "ATX1" and result.cost == "UGX 35.0000"
    assert post.call_args.args[0] == "https://api.sandbox.africastalking.com/version1/messaging"
    assert post.call_args.kwargs["headers"]["apiKey"] == "k"
    bad = {"SMSMessageData": {"Recipients": [{"status": "InvalidPhoneNumber", "statusCode": 403}]}}
    with (
        mock.patch.object(requests, "post", return_value=FakeResponse(201, bad)),
        pytest.raises(ProviderError) as err,
    ):
        adapters.AfricasTalkingAdapter().send(Message(to="+1", template="x", text="hi"))
    assert err.value.retry is False
    with (
        mock.patch.object(requests, "post", return_value=FakeResponse(503, {})),
        pytest.raises(ProviderError) as err,
    ):
        adapters.AfricasTalkingAdapter().send(Message(to="+1", template="x", text="hi"))
    assert err.value.retry is True
    with override_settings(AFRICASTALKING_API_KEY=""), pytest.raises(ProviderError):
        adapters.AfricasTalkingAdapter().send(Message(to="+1", template="x", text="hi"))


@override_settings(WHATSAPP_ACCESS_TOKEN="t", WHATSAPP_PHONE_NUMBER_ID="123")
def test_whatsapp_cloud_adapter_sends_template():  # type: ignore[no-untyped-def]
    with mock.patch.object(
        requests, "post", return_value=FakeResponse(200, {"messages": [{"id": "wamid.1"}]})
    ) as post:
        result = adapters.WhatsAppCloudAdapter().send(
            Message(
                to="+256772000001",
                template="smartfarm_task_assigned",
                language="sw",
                params={"body": ["Kazi mpya", "Leo"], "buttons": ["done:1", "reschedule:1"]},
            )
        )
    assert result.provider_id == "wamid.1"
    sent = post.call_args.kwargs["json"]
    assert sent["to"] == "256772000001" and sent["template"]["name"] == "smartfarm_task_assigned"
    assert sent["template"]["language"]["code"] == "sw"
    assert sent["template"]["components"][0]["parameters"][0]["text"] == "Kazi mpya"
    assert sent["template"]["components"][2]["parameters"][0]["payload"] == "reschedule:1"
    err = FakeResponse(400, {"error": {"message": "Template not approved"}})
    with mock.patch.object(requests, "post", return_value=err), pytest.raises(ProviderError) as e:
        adapters.WhatsAppCloudAdapter().send(Message(to="+256772000001", template="x"))
    assert "Template not approved" in str(e.value) and e.value.retry is False


def test_email_adapter_sends_html(mailoutbox=None):  # type: ignore[no-untyped-def]
    from django.core import mail

    adapters.EmailAdapter().send(
        Message(
            to="a@example.com",
            template="x",
            text="Body",
            subject="Hello",
            params={"farm_name": "YPA FARM", "link": "http://x/activities"},
        )
    )
    [email] = mail.outbox
    assert email.subject == "Hello" and email.body == "Body"
    html = email.alternatives[0][0]
    assert "YPA FARM" in html and "http://x/activities" in html


@override_settings(SMS_ADAPTER="africastalking", WHATSAPP_ADAPTER="whatsapp_cloud")
def test_adapter_selection():  # type: ignore[no-untyped-def]
    assert isinstance(adapters.get_adapter("sms"), adapters.AfricasTalkingAdapter)
    assert isinstance(adapters.get_adapter("whatsapp"), adapters.WhatsAppCloudAdapter)
    assert isinstance(adapters.get_adapter("email"), adapters.EmailAdapter)


# --- Live updates ----------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_websocket_pushes_new_notifications(farm_a, member):  # type: ignore[no-untyped-def]
    from asgiref.sync import async_to_sync, sync_to_async
    from channels.testing import WebsocketCommunicator
    from rest_framework_simplejwt.tokens import AccessToken

    from apps.notifications.consumers import NotificationConsumer

    user = person(member, farm_a)

    async def run() -> None:
        bad = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications?token=nope")
        connected, _code = await bad.connect()
        assert not connected
        token = str(AccessToken.for_user(user))
        ws = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), f"/ws/notifications?token={token}"
        )
        connected, _ = await ws.connect()
        assert connected
        assert (await ws.receive_json_from())["type"] == "hello"
        await ws.send_json_to({"type": "ping"})
        assert (await ws.receive_json_from())["type"] == "pong"
        await sync_to_async(services.send_test)(user, farm_a, "email")
        event = await ws.receive_json_from(timeout=3)
        assert (
            event["type"] == "notification.new" and event["title"] == "Test message from Smart Farm"
        )
        await ws.disconnect()

    async_to_sync(run)()


def test_run_jobs_once(farm, member):  # type: ignore[no-untyped-def]
    from django.core.management import call_command

    person(member, farm)
    call_command("run_jobs", "--once")
