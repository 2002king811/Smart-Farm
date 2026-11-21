from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import FarmOwnedModel


class AuditAction(models.TextChoices):
    CREATE = "create", "Created"
    UPDATE = "update", "Updated"
    DELETE = "delete", "Deleted"
    RESTORE = "restore", "Restored"
    STATUS_CHANGE = "status_change", "Status changed"


class AuditLog(FarmOwnedModel):
    """Append-only record of who changed what, when, and the values before and after."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=20, choices=AuditAction.choices)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name="+")
    object_id = models.CharField(max_length=64)
    object_repr = models.CharField(max_length=200)
    changed_fields = models.JSONField(default=list, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-at",)
        indexes = [
            models.Index(fields=["farm", "at"]),
            models.Index(fields=["farm", "content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.object_repr}"

    def save(self, *args: object, **kwargs: object) -> None:
        if not self._state.adding:
            raise RuntimeError("Audit log entries are append-only")
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        raise RuntimeError("Audit log entries are append-only")
