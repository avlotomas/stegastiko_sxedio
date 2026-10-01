from django.contrib import admin

from cases.models import (
    Case,
    CompletenessCheck,
    Consultation,
    Field,
    InfrastructureCheck,
    LandPlot,
    Parcel,
    SubmissionCycle,
    SubmissionCyclePublication,
    UtilityService,
    UtilityServiceType,
    ValuationReferral,
)

admin.site.register(Case)
admin.site.register(CompletenessCheck)
admin.site.register(LandPlot)
admin.site.register(UtilityService)
admin.site.register(UtilityServiceType)
admin.site.register(Consultation)
admin.site.register(InfrastructureCheck)
admin.site.register(Field)
admin.site.register(Parcel)
admin.site.register(ValuationReferral)
admin.site.register(SubmissionCycle)
admin.site.register(SubmissionCyclePublication)
