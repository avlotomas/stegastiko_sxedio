from django.contrib import admin

from applications.models import (
    Application,
    CommitteeDecision,
    DependentChild,
    EligibilityCheck,
    Objection,
    Person,
    SupportingDocument,
)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("identity_number", "last_name", "first_name", "date_of_birth")
    search_fields = ("identity_number", "last_name", "first_name")


class DependentChildInline(admin.TabularInline):
    model = DependentChild
    extra = 0


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("folder_number", "submitted_on", "submission_cycle", "person", "outcome_104")
    search_fields = ("folder_number", "person__identity_number", "person__last_name")
    list_filter = ("submission_cycle__community", "outcome_104", "family_type")
    inlines = [DependentChildInline]


@admin.register(EligibilityCheck)
class EligibilityCheckAdmin(admin.ModelAdmin):
    list_display = ("application", "criterion", "overall_result")
    list_filter = ("criterion", "overall_result")


admin.site.register(SupportingDocument)
admin.site.register(CommitteeDecision)
admin.site.register(Objection)
