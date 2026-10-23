from django.contrib import admin

from applications.models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("identity_number", "last_name", "first_name", "date_of_birth")
    search_fields = ("identity_number", "last_name", "first_name")
