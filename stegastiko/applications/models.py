from django.core.exceptions import ValidationError
from django.db import models

from core.models import AuditedModel


class Person(AuditedModel):
    """One row per ΑΔΤ, holding only the identity fields that never change over time (10.3.1).

    Everything that can differ between applications of the same person (citizenship,
    refugee ID, residence, income, children, ...) lives on `plot_applications.PlotApplication`.
    """

    identity_number = models.CharField(max_length=32, unique=True)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    date_of_birth = models.DateField(null=True, blank=True)
    birth_place = models.CharField(max_length=128, blank=True)
    birth_country = models.CharField(max_length=128, blank=True)
    parents_birth_place = models.CharField(max_length=128, blank=True)
    parents_birth_country = models.CharField(max_length=128, blank=True)
    document_type = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("last_name", "first_name", "identity_number")

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.identity_number})"

    def clean(self):
        if self.pk:
            previous = Person.objects.filter(pk=self.pk).first()
            if previous and previous.identity_number != self.identity_number:
                raise ValidationError("The identity number cannot be changed.")
