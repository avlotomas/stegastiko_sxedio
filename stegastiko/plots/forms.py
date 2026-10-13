from django import forms
from django.db.models import Q

from applications.models import Person
from cases.forms import StyledFormMixin
from cases.models import SubmissionCycle, SubmissionCyclePublication
from core.forms import IsoDateInput
from core.models import Community
from plots.models import Plot


class PlotForm(StyledFormMixin, forms.ModelForm):
    """One completed plot: manual entry, or edits after the case that produced it."""

    owner = forms.ModelChoiceField(
        queryset=Person.objects.all(),
        required=False,
        help_text="8.2 Ιδιοκτήτης οικοπέδου",
    )

    class Meta:
        model = Plot
        fields = [
            "community",
            "numbering_status",
            "design_number",
            "tkx_number",
            "title_deed_number",
            "parcel_number",
            "sheet_plan",
            "lot_number_in_field",
            "kotsiani_number",
            "final_area_sqm",
            "has_separate_title",
            "valuation_amount",
            "owner",
            "comments",
        ]
        widgets = {
            "final_area_sqm": forms.NumberInput(attrs={"step": "0.01"}),
            "valuation_amount": forms.NumberInput(attrs={"step": "0.01"}),
            "comments": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        communities = Community.objects.filter(is_active=True)
        if self.instance.community_id:
            communities = Community.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.community_id)
            )
        self.fields["community"].queryset = communities.order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("numbering_status") == Plot.NumberingStatus.TKX
            and not (cleaned_data.get("tkx_number") or "").strip()
        ):
            self.add_error("tkx_number", "Η Αρίθμηση ΤΚΧ απαιτείται για αυτή την κατάσταση.")
        return cleaned_data


class AnnouncementPlotsField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, plot):
        origin = plot.source_case.case_number if plot.source_case_id else "χειροκίνητη καταχώριση"
        parts = [plot.row_label]
        if plot.final_area_sqm is not None:
            parts.append(f"{plot.final_area_sqm} τ.μ.")
        if plot.disposal_price is not None:
            parts.append(f"τιμή διάθεσης {plot.disposal_price} €")
        parts.append(origin)
        return " · ".join(parts)


def offerable_plots(community, cycle=None):
    """9.1 Plots of `community` an announcement may offer, plus those it already offers."""
    plots = Plot.objects.filter(community=community).select_related("source_case")
    available = plots.available()
    if cycle is None or not cycle.pk:
        return available
    return plots.filter(
        Q(pk__in=available.values("pk")) | Q(pk__in=cycle.plots.values("pk"))
    ).distinct()


class SubmissionCycleForm(StyledFormMixin, forms.ModelForm):
    """9.1 Announcement of the submission period, at community level.

    The community is fixed by the caller (chosen first on the create screen) and the
    plots are limited to the available plots of that community.
    """

    plots = AnnouncementPlotsField(
        queryset=Plot.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        help_text="9.1 Διαθέσιμα οικόπεδα της γνωστοποίησης",
    )

    class Meta:
        model = SubmissionCycle
        fields = [
            "plots",
            "announcement_date",
            "submission_start_date",
            "submission_end_date",
            "comments",
        ]
        widgets = {
            "announcement_date": IsoDateInput(),
            "submission_start_date": IsoDateInput(),
            "submission_end_date": IsoDateInput(),
            "comments": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, community=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.community = community or self.instance.community
        self.instance.community = self.community
        self.fields["plots"].queryset = offerable_plots(self.community, self.instance)
        if not self.instance.pk and not self.is_bound:
            # New announcements offer every available plot unless the user unticks some.
            self.initial.setdefault("plots", list(self.fields["plots"].queryset))

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("submission_start_date")
        end = cleaned_data.get("submission_end_date")
        if start and end and end < start:
            self.add_error(
                "submission_end_date", "Η λήξη υποβολής δεν μπορεί να προηγείται της έναρξης."
            )
        return cleaned_data


class AnnouncementTextForm(StyledFormMixin, forms.ModelForm):
    """9.3 Preview and edit the generated announcement before finalising it."""

    class Meta:
        model = SubmissionCycle
        fields = ["announcement_text"]
        widgets = {"announcement_text": forms.Textarea(attrs={"rows": 18})}


class SubmissionCyclePublicationForm(StyledFormMixin, forms.ModelForm):
    """9.2 One publication method of an announcement (a row of the 9.2 grid)."""

    class Meta:
        model = SubmissionCyclePublication
        fields = ["method", "published_on", "notes"]
        widgets = {"published_on": IsoDateInput()}
