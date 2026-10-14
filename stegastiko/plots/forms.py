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


def offerable_plots(communities, cycle=None):
    """9.1 Plots of `communities` an announcement may offer, plus those it already offers.

    Available means not yet given to a holder (no active allocation) and with value and price.
    """
    plots = Plot.objects.filter(community__in=communities).select_related("community", "source_case")
    available = plots.available()
    if cycle is None or not cycle.pk:
        return available
    return plots.filter(
        Q(pk__in=available.values("pk")) | Q(pk__in=cycle.plots.values("pk"))
    ).distinct()


class AnnouncementCommunitiesForm(forms.Form):
    """9.1 Step 1 of the wizard: the communities an announcement covers.

    The announcement is issued by the Έπαρχος of the district (Ενότ. 4), so every chosen
    community belongs to the same district.
    """

    communities = forms.ModelMultipleChoiceField(
        queryset=Community.objects.filter(is_active=True).order_by("district", "name"),
        error_messages={
            "required": "Επιλέξτε τουλάχιστον μία Κοινότητα.",
            "invalid_choice": "Μη έγκυρη Κοινότητα.",
            "invalid_pk_value": "Μη έγκυρη Κοινότητα.",
        },
    )

    def clean_communities(self):
        communities = self.cleaned_data["communities"]
        districts = sorted({community.district for community in communities})
        if len(districts) > 1:
            raise forms.ValidationError(
                "Η ανακοίνωση εκδίδεται από τον Έπαρχο της Επαρχίας (Ενότ. 4)· επιλέξτε Κοινότητες "
                f"μίας Επαρχίας (επιλέχθηκαν: {', '.join(districts)})."
            )
        return communities


class SubmissionCycleForm(StyledFormMixin, forms.ModelForm):
    """9.1 Announcement of the submission period, for the communities chosen in step 1.

    The communities are fixed by the caller (they are chosen first on the create screen)
    and the plots are limited to the available plots of those communities.
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
            "submission_months",
        ]
        widgets = {"announcement_date": IsoDateInput()}

    def __init__(self, *args, communities=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.communities = list(communities if communities is not None else self.instance.communities.all())
        self.fields["plots"].queryset = offerable_plots(self.communities, self.instance)
        if not self.instance.pk and not self.is_bound:
            # New announcements offer every available plot unless the user unticks some.
            self.initial.setdefault("plots", list(self.fields["plots"].queryset))

    def plot_groups(self):
        """The offerable plots grouped by community, for the picker of the form."""
        selected = {str(value) for value in self["plots"].value() or []}
        field = self.fields["plots"]
        groups = {community.pk: {"community": community, "plots": []} for community in self.communities}
        for plot in field.queryset.order_by("community__name", "id"):
            groups[plot.community_id]["plots"].append(
                {"pk": plot.pk, "label": field.label_from_instance(plot), "checked": str(plot.pk) in selected}
            )
        return sorted(groups.values(), key=lambda group: group["community"].name)


class SubmissionCyclePublicationForm(StyledFormMixin, forms.ModelForm):
    """9.2 An «Άλλο» row of the publication table: a date and a comment (the four fixed
    methods are dated inline in the table, see `PublicationDateForm`)."""

    class Meta:
        model = SubmissionCyclePublication
        fields = ["published_on", "notes"]
        widgets = {"published_on": IsoDateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = True
        self.fields["notes"].label = "Σχόλια"


class PublicationDateForm(forms.Form):
    """9.2 The date of a fixed publication method; empty means the method was not used."""

    published_on = forms.DateField(required=False)
