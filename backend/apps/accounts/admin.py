from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Farm, FarmMembership, User


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
    """Platform view of farms: profile and status only. Farm records (animals, health…) are
    deliberately not registered here; support access to them needs a logged grant (phase 2)."""

    list_display = ("name", "county", "country", "status", "created_at")
    list_filter = ("status", "country")
    search_fields = ("name", "slug", "county")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MembershipInline]
    actions = ["suspend", "reactivate"]

    @admin.action(description="Suspend selected farms")
    def suspend(self, request, queryset):  # type: ignore[no-untyped-def]
        queryset.update(status="suspended")

    @admin.action(description="Reactivate selected farms")
    def reactivate(self, request, queryset):  # type: ignore[no-untyped-def]
        queryset.update(status="active")
