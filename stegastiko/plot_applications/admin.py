from django.contrib import admin

from plot_applications.models import (
    ApplicationChild,
    ApplicationParty,
    IncomeDeclaration,
    PlotApplication,
)


class PartyInline(admin.StackedInline):
    model = ApplicationParty
    extra = 0


class ChildInline(admin.TabularInline):
    model = ApplicationChild
    extra = 0


class IncomeInline(admin.TabularInline):
    model = IncomeDeclaration
    extra = 0


@admin.register(PlotApplication)
class PlotApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "protocol_number",
        "community",
        "applicant",
        "spouse",
        "submitted_on",
        "application_stage",
        "completeness_result",
        "documents_completeness",
        "eligibility_result",
        "plot_allocation_status",
    )
    list_filter = (
        "application_stage",
        "completeness_result",
        "documents_completeness",
        "eligibility_result",
        "plot_allocation_status",
        "residence_category",
        "family_status",
    )
    search_fields = ("protocol_number", "applicant__identity_number", "applicant__last_name")
    inlines = (PartyInline, ChildInline, IncomeInline)
