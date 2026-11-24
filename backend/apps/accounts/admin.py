from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Farm, FarmMembership, SupportAccessGrant, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "phone",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
    )
    search_fields = ("username", "email", "phone", "first_name", "last_name")
    fieldsets = (
        *BaseUserAdmin.fieldsets,  # type: ignore[misc]
        (
            "Smart Farm",
            {
                "fields": (
                    "phone",
                    "photo",
                    "language",
                    "email_verified",
                    "phone_verified",
                    "must_change_password",
                )
            },
        ),
    )


class MembershipInline(admin.TabularInline):
    model = FarmMembership
    fk_name = "farm"
    extra = 0
    raw_id_fields = ("user", "invited_by")


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    """Platform view of farms: profile, people, message credits and status.

    Farm records (animals, health…) are not registered in the admin. Staff see them only on the
    "Farm records" page, and only during a support-access grant; every look is logged in the
    farm's own audit log."""

    list_display = (
        "name",
        "county",
        "country",
        "status",
        "members",
        "animals",
        "sms_usage",
        "whatsapp_usage",
        "created_at",
    )
    list_filter = ("status", "country")
    search_fields = ("name", "slug", "county")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MembershipInline]
    actions = ["suspend", "reactivate"]
    readonly_fields = ("records_link",)
    fieldsets = (
        (None, {"fields": ("name", "slug", "status", "records_link")}),
        (
            "Profile",
            {
                "fields": (
                    "country",
                    "county",
                    "location",
                    "phone",
                    "email",
                    "timezone",
                    "currency",
                    "language",
                )
            },
        ),
        ("Message credits", {"fields": ("sms_monthly_allowance", "whatsapp_monthly_allowance")}),
    )

    def get_queryset(self, request):  # type: ignore[no-untyped-def]
        from django.db.models import Count, Q

        return (
            super()
            .get_queryset(request)
            .annotate(
                n_members=Count(
                    "memberships", filter=Q(memberships__status="active"), distinct=True
                ),
            )
        )

    @admin.display(description="Members", ordering="n_members")
    def members(self, obj):  # type: ignore[no-untyped-def]
        return obj.n_members

    @admin.display(description="Animals")
    def animals(self, obj):  # type: ignore[no-untyped-def]
        from apps.livestock.models import Animal

        return Animal.unscoped.filter(farm=obj, is_active=True, deleted_at__isnull=True).count()

    def _usage(self, obj, channel):  # type: ignore[no-untyped-def]
        from apps.notifications.services import usage

        u = usage(obj)[channel]
        return f"{u['used']} / {u['allowance']}"

    @admin.display(description="SMS this month")
    def sms_usage(self, obj):  # type: ignore[no-untyped-def]
        return self._usage(obj, "sms")

    @admin.display(description="WhatsApp this month")
    def whatsapp_usage(self, obj):  # type: ignore[no-untyped-def]
        return self._usage(obj, "whatsapp")

    @admin.display(description="Farm records")
    def records_link(self, obj):  # type: ignore[no-untyped-def]
        from django.urls import reverse
        from django.utils.html import format_html

        if not obj.pk:
            return "-"
        return format_html(
            '<a href="{}">Open farm records (needs a support-access grant)</a>',
            reverse("admin:accounts_farm_records", args=[obj.pk]),
        )

    def get_urls(self):  # type: ignore[no-untyped-def]
        from django.urls import path

        return [
            path(
                "<uuid:farm_id>/records/",
                self.admin_site.admin_view(self.records_view),
                name="accounts_farm_records",
            ),
            *super().get_urls(),
        ]

    def records_view(self, request, farm_id):  # type: ignore[no-untyped-def]
        from django.shortcuts import get_object_or_404
        from django.template.response import TemplateResponse
        from django.utils import timezone

        from apps.audit.models import AuditAction
        from apps.audit.services import record_event
        from apps.calendar.models import Activity
        from apps.core.context import farm_context
        from apps.health.models import HealthObservation, Treatment, Vaccination
        from apps.livestock.models import Animal

        farm = get_object_or_404(Farm, pk=farm_id)
        grant = SupportAccessGrant.objects.filter(
            farm=farm, staff=request.user, revoked_at__isnull=True, expires_at__gt=timezone.now()
        ).first()
        context = {
            **self.admin_site.each_context(request),
            "farm": farm,
            "grant": grant,
            "title": f"{farm.name}: farm records",
        }
        if grant is None:
            return TemplateResponse(request, "admin/farm_records.html", context, status=403)
        with farm_context(farm.pk, user_id=request.user.pk):
            record_event(
                farm.pk,
                grant,
                AuditAction.ACCESS,
                None,
                {
                    "staff": request.user.get_username(),
                    "reason": grant.reason,
                    "page": "farm records",
                },
            )
            context.update(
                animals=list(Animal.objects.select_related("location").order_by("animal_id")[:200]),
                activities=list(
                    Activity.objects.select_related("assigned_to").order_by("-date")[:30]
                ),
                vaccinations=list(
                    Vaccination.objects.select_related("animal").order_by("-date")[:20]
                ),
                treatments=list(Treatment.objects.select_related("animal").order_by("-date")[:20]),
                observations=list(
                    HealthObservation.objects.select_related("animal").order_by("-date")[:20]
                ),
            )
        return TemplateResponse(request, "admin/farm_records.html", context)

    @admin.action(description="Suspend selected farms")
    def suspend(self, request, queryset):  # type: ignore[no-untyped-def]
        queryset.update(status="suspended")

    @admin.action(description="Reactivate selected farms")
    def reactivate(self, request, queryset):  # type: ignore[no-untyped-def]
        queryset.update(status="active")


@admin.register(SupportAccessGrant)
class SupportAccessGrantAdmin(admin.ModelAdmin):
    """Time-limited access to one farm's records for support. Logged in the farm's audit log."""

    list_display = ("farm", "staff", "reason", "created_at", "expires_at", "is_active")
    list_filter = ("farm",)
    fields = ("farm", "reason", "hours")
    actions = ["revoke"]

    def get_form(self, request, obj=None, **kwargs):  # type: ignore[no-untyped-def,override]
        from django import forms

        class GrantForm(forms.ModelForm):
            hours = forms.IntegerField(
                min_value=1,
                max_value=SupportAccessGrant.MAX_HOURS,
                initial=4,
                help_text=f"Up to {SupportAccessGrant.MAX_HOURS} hours.",
            )

            class Meta:
                model = SupportAccessGrant
                fields = ("farm", "reason")

        kwargs["form"] = GrantForm
        return super().get_form(request, obj, **kwargs)

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return obj is None  # grants are created and revoked, never edited

    def save_model(self, request, obj, form, change):  # type: ignore[no-untyped-def]
        from datetime import timedelta

        from django.utils import timezone

        from apps.audit.models import AuditAction
        from apps.audit.services import record_event
        from apps.core.context import farm_context

        obj.staff = request.user
        obj.expires_at = timezone.now() + timedelta(hours=form.cleaned_data["hours"])
        super().save_model(request, obj, form, change)
        with farm_context(obj.farm_id, user_id=request.user.pk):
            record_event(
                obj.farm_id,
                obj,
                AuditAction.CREATE,
                None,
                {
                    "staff": request.user.get_username(),
                    "reason": obj.reason,
                    "expires_at": obj.expires_at,
                },
            )

    @admin.display(boolean=True, description="Active")
    def is_active(self, obj):  # type: ignore[no-untyped-def]
        return obj.active

    @admin.action(description="Revoke selected grants")
    def revoke(self, request, queryset):  # type: ignore[no-untyped-def]
        from django.utils import timezone

        queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
