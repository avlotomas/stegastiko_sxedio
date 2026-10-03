import hashlib
import json

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from core.middleware import get_current_user


class ActionHistory(models.Model):
    class ActionType(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        CANCEL = "CANCEL", "Cancel"

    entity_type = models.CharField(max_length=128)
    entity_id = models.CharField(max_length=64)
    action = models.CharField(max_length=16, choices=ActionType.choices)
    field_name = models.CharField(max_length=128, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    user_id = models.IntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    section_ref = models.CharField(max_length=32, blank=True)
    case_id = models.IntegerField(null=True, blank=True)
    application_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-timestamp", "-id")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("ActionHistory is append-only and cannot be modified.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("ActionHistory entries cannot be deleted.")


class AuditedModel(models.Model):
    class AuditedQuerySet(models.QuerySet):
        def update(self, **kwargs):
            raise ValueError(
                "QuerySet.update() is blocked for audited models; use save() per instance."
            )

    class AuditedManager(models.Manager):
        def get_queryset(self):
            return AuditedModel.AuditedQuerySet(self.model, using=self._db)

        def bulk_update(self, objs, fields, batch_size=None):
            raise ValueError(
                "bulk_update() is blocked for audited models; use save() per instance."
            )

        def update(self, **kwargs):
            raise ValueError(
                "Manager.update() is blocked for audited models; use save() per instance."
            )

    objects = AuditedManager()
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def _audit_context(self):
        case_id = getattr(self, "case_id", None)
        application_id = getattr(self, "application_id", None)
        section_ref = getattr(self, "_section_ref", "")
        return case_id, application_id, section_ref

    def _audit_value(self, field_name, value):
        """Value written to the history; override to mask secrets."""
        return value


class Attachment(AuditedModel):
    _audit_exclude_fields = {"data"}

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    section_ref = models.CharField(max_length=32, blank=True)
    doc_code = models.CharField(max_length=64, blank=True)
    filename = models.CharField(max_length=255)
    content_type_name = models.CharField(max_length=128)
    size_bytes = models.PositiveBigIntegerField()
    file_sha256 = models.CharField(max_length=64, editable=False)
    data = models.BinaryField()
    uploaded_by_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def save(self, *args, **kwargs):
        self.size_bytes = len(self.data or b"")
        self.file_sha256 = hashlib.sha256(self.data or b"").hexdigest()
        if self.uploaded_by_id is None:
            user = get_current_user()
            if user and user.is_authenticated:
                self.uploaded_by_id = user.id
        return super().save(*args, **kwargs)

    def _audit_context(self):
        # Files on a case child (e.g. a 3.1 land plot) belong to the case folder history.
        owner = self.content_object
        case_id = getattr(owner, "case_id", None)
        application_id = getattr(owner, "application_id", None)
        if (self.content_type.app_label, self.content_type.model) == ("cases", "case"):
            case_id = self.object_id
        return case_id, application_id, getattr(self, "_section_ref", "") or self.section_ref


class Communication(AuditedModel):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    channel = models.CharField(max_length=32, default="email")
    recipient = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=32, default="draft")
    sent_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    created_by_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def save(self, *args, **kwargs):
        if self.created_by_id is None:
            user = get_current_user()
            if user and user.is_authenticated:
                self.created_by_id = user.id
        return super().save(*args, **kwargs)

    def _audit_context(self):
        # Emails about a case belong to its aggregate history (§Β.1.3).
        case_id = None
        model_ref = (self.content_type.app_label, self.content_type.model)
        if model_ref == ("cases", "case"):
            case_id = self.object_id
        elif model_ref == ("cases", "completenesscheck"):
            owner = self.content_object
            case_id = getattr(owner, "case_id", None)
        return case_id, None, getattr(self, "_section_ref", "")


class Community(AuditedModel):
    district = models.CharField(max_length=128)
    municipality_type = models.CharField(max_length=64, blank=True)
    municipality = models.CharField(max_length=128, blank=True)
    name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    community_folder_code = models.CharField(max_length=16, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("district", "name")
        unique_together = ("district", "name")

    def __str__(self):
        return f"{self.name} ({self.district})"


class SystemSetting(AuditedModel):
    SECRET_KEYS = frozenset({"smtpPassword"})

    key = models.CharField(max_length=64, unique=True)
    value = models.CharField(max_length=512)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("key",)

    def __str__(self):
        return self.key

    def _audit_value(self, field_name, value):
        if field_name == "value" and self.key in self.SECRET_KEYS and value:
            return "********"
        return value


class ReminderRead(AuditedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reminder_reads",
    )
    reminder_key = models.CharField(max_length=128)
    reminder_type = models.CharField(max_length=64)
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-read_at", "-id")
        unique_together = ("user", "reminder_key")

    def __str__(self):
        return f"{self.user_id}:{self.reminder_key}"


class Role(AuditedModel):
    """User role (§Β.3): access to functions is granted to roles, roles are given to users."""

    name = models.CharField(max_length=128, unique=True, help_text="Ονομασία ρόλου")
    description = models.TextField(blank=True, help_text="Περιγραφή")
    is_active = models.BooleanField(
        default=True, help_text="Ενεργός (ανενεργός ρόλος δεν δίνει πρόσβαση)"
    )
    # Sorted "function_code:access_type" strings from core.function_catalog.
    grants = models.JSONField(default=list, blank=True)
    # Assignments must change from the role side (role.members.add/remove) so that
    # the m2m audit receiver records them on this audited model.
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="app_roles", blank=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class DocumentCatalogItem(AuditedModel):
    code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=255)
    is_required_default = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} - {self.title}"


def serialize_field_value(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)
