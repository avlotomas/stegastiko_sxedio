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


def offerable_plots(communities=None, cycle=None):
    """9.1 Plots an announcement may offer, plus those it already offers.

    Available means valued and priced, not in any active announcement, and no active allocation.
    """
    plots = Plot.objects.select_related("community", "source_case")
    if communities:
        plots = plots.filter(community__in=communities)
    elif cycle is not None and cycle.pk and cycle.community is not None:
        plots = plots.filter(community=cycle.community)
    else:
        plots = plots.filter(community__is_active=True)
    available = plots.available()
    if cycle is None or not cycle.pk:
        return available
    if cycle.stage == SubmissionCycle.Stage.CLOSED:
        return plots.filter(pk__in=cycle.plots.values("pk")).distinct()
    return plots.filter(
        Q(pk__in=available.values("pk")) | Q(pk__in=cycle.plots.values("pk"))
    ).distinct()


class AnnouncementPlotsSelectionForm(forms.Form):
    """9.1 Step 1 of the wizard: select the offered plots (all belonging to one Community)."""

    plots = AnnouncementPlotsField(
        queryset=Plot.objects.none(),
        error_messages={
            "required": "Επιλέξτε τουλάχιστον ένα διαθέσιμο οικόπεδο.",
            "invalid_choice": "Μη έγκυρο οικόπεδο.",
            "invalid_pk_value": "Μη έγκυρο οικόπεδο.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plots"].queryset = (
            Plot.objects.available()
            .select_related("community", "source_case")
            .order_by("community__district", "community__name", "id")
        )

    def clean_plots(self):
        plots = self.cleaned_data["plots"]
        communities = {plot.community_id for plot in plots}
        if len(communities) > 1:
            raise forms.ValidationError(
                "Όλα τα οικόπεδα μιας γνωστοποίησης πρέπει να ανήκουν στην ίδια Κοινότητα (Ενότ. 4, 6, 7)."
            )
        return plots


class SubmissionCycleForm(StyledFormMixin, forms.ModelForm):
    """9.1 Announcement of the submission period, linked directly to plots of one Community."""

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

    def __init__(self, *args, selected_plots=None, communities=None, **kwargs):
        super().__init__(*args, **kwargs)
        if selected_plots is not None:
            selected_list = list(selected_plots)
            self.communities = list({p.community for p in selected_list})
        elif communities is not None:
            self.communities = list(communities)
            selected_list = None
        elif self.instance.pk and self.instance.community is not None:
            self.communities = [self.instance.community]
            selected_list = None
        else:
            self.communities = list(Community.objects.filter(is_active=True).order_by("name"))
            selected_list = None
        self.fields["plots"].queryset = offerable_plots(self.communities, self.instance)
        if not self.instance.pk and not self.is_bound:
            if selected_list is not None:
                self.initial.setdefault("plots", selected_list)
            else:
                self.initial.setdefault("plots", list(self.fields["plots"].queryset))

    def _allocated_plot_ids(self) -> set[int]:
        if not self.instance.pk:
            return set()
        from allocation.models import Allocation

        return set(
            Allocation.objects.filter(
                parcel__in=self.instance.plots.all(),
                status=Allocation.Status.ACTIVE,
            )
            .filter(
                Q(application__announcement=self.instance) | Q(application__isnull=True)
            )
            .values_list("parcel_id", flat=True)
        )

    def clean_plots(self):
        plots = list(self.cleaned_data.get("plots") or [])
        communities = {plot.community_id for plot in plots}
        if len(communities) > 1:
            raise forms.ValidationError(
                "Όλα τα οικόπεδα μιας γνωστοποίησης πρέπει να ανήκουν στην ίδια Κοινότητα (Ενότ. 4, 6, 7)."
            )
        if self.instance.pk:
            allocated_ids = self._allocated_plot_ids()
            kept_ids = {plot.pk for plot in plots}
            removed_allocated = allocated_ids - kept_ids
            if removed_allocated:
                removed_labels = [
                    plot.row_label
                    for plot in self.instance.plots.filter(pk__in=removed_allocated).order_by("id")
                ]
                raise forms.ValidationError(
                    "Το οικόπεδο "
                    + ", ".join(removed_labels)
                    + " έχει ήδη δοθεί σε αιτητή και δεν μπορεί να αφαιρεθεί."
                )
            if self.instance.is_published and not plots and self.instance.plots.exists():
                raise forms.ValidationError(
                    "Η γνωστοποίηση πρέπει να προσφέρει τουλάχιστον ένα οικόπεδο (9.1)."
                )
        return plots

    def clean(self):
        cleaned_data = super().clean()
        ann_date = cleaned_data.get("announcement_date")
        months = cleaned_data.get("submission_months")
        if self.instance.pk and ann_date and months:
            from cases.models import add_months

            end_date = add_months(ann_date, months)
            sub_dates = list(
                self.instance.applications.exclude(submitted_on__isnull=True).values_list(
                    "submitted_on", flat=True
                )
            )
            if sub_dates:
                earliest = min(sub_dates)
                latest = max(sub_dates)
                if ann_date > earliest or end_date < latest:
                    raise forms.ValidationError(
                        f"Η περίοδος υποβολής ({ann_date:%d/%m/%Y} – {end_date:%d/%m/%Y}) πρέπει να "
                        f"καλύπτει τις ημερομηνίες υποβολής των υπαρχουσών αιτήσεων "
                        f"({earliest:%d/%m/%Y} – {latest:%d/%m/%Y})."
                    )
        return cleaned_data

    def plot_groups(self):
        """The offerable plots grouped by community, for the picker of the form."""
        selected = {str(value) for value in self["plots"].value() or []}
        allocated_ids = self._allocated_plot_ids()
        is_closed = bool(
            self.instance.pk and self.instance.stage == SubmissionCycle.Stage.CLOSED
        )
        field = self.fields["plots"]
        groups = {community.pk: {"community": community, "plots": []} for community in self.communities}
        for plot in field.queryset.order_by("community__name", "id"):
            if plot.community_id not in groups:
                groups[plot.community_id] = {"community": plot.community, "plots": []}
            is_allocated = plot.pk in allocated_ids
            is_selected = str(plot.pk) in selected
            groups[plot.community_id]["plots"].append(
                {
                    "pk": plot.pk,
                    "community_id": plot.community_id,
                    "label": field.label_from_instance(plot),
                    "checked": is_allocated or is_selected,
                    "allocated": is_allocated,
                    "released": is_closed and is_selected and not is_allocated,
                }
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
