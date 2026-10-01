from django.contrib import admin
from django.utils.html import format_html

from core.models import (
    ActionHistory,
    Attachment,
    Communication,
    Community,
    DocumentCatalogItem,
    SystemSetting,
)


@admin.register(ActionHistory)
class ActionHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "entity_type",
        "entity_id",
        "action",
        "field_name",
        "user_id",
    )
    list_filter = ("entity_type", "action")
    search_fields = ("entity_type", "entity_id", "field_name")
    ordering = ("-timestamp", "-id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "filename",
        "content_type_name",
        "size_bytes",
        "file_sha256_short",
        "section_ref",
        "created_at",
    )
    list_filter = ("content_type_name", "section_ref")
    search_fields = ("filename", "doc_code", "file_sha256")

    @admin.display(description="SHA-256")
    def file_sha256_short(self, obj):
        return format_html("<code>{}</code>", obj.file_sha256[:16])


@admin.register(Communication)
class CommunicationAdmin(admin.ModelAdmin):
    list_display = ("id", "channel", "recipient", "status", "sent_at", "created_at")
    list_filter = ("channel", "status")
    search_fields = ("recipient", "subject")


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "community_folder_code", "contact_email", "is_active")
    list_filter = ("district", "is_active")
    search_fields = ("name", "district", "community_folder_code")


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description", "updated_at")
    search_fields = ("key", "description")


@admin.register(DocumentCatalogItem)
class DocumentCatalogItemAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "is_required_default", "is_active")
    list_filter = ("is_required_default", "is_active")
    search_fields = ("code", "title")
