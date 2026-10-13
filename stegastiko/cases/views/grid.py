"""Reusable add / edit / delete endpoints of the case grids opened in modals.

Every grid of the case screens (2.1, 3.1, 4.1, 4.2, 5, 6.7, 7.3, 7.4, 7.6) follows the same
JSON protocol used by static/js/app.js:

* GET  form URL  -> {"ok": true, "html": <modal form>}
* POST form URL  -> 400 {"ok": false, "html": <form with errors>}
                    200 {"ok": true, "message", "grid_html", ...extra}
* POST delete URL -> 200 {"ok": true, "message", "grid_html", ...extra}
                     4xx {"ok": false, "message", ...}

A `GridEndpoint` instance describes one grid; subclasses override the hooks that differ.
"""

from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from cases.services import delete_with_attachments
from cases.views.common import case_for_section, delete_action_for, wants_json
from core.function_catalog import CREATE, EDIT, VIEW


class GridEndpoint:
    section = ""
    model = None
    form_class = None
    section_ref = ""
    grid_template = ""
    form_template = ""
    form_context_name = "form"
    create_action = CREATE
    edit_action = EDIT
    # None: «Διαγραφή» of the section (falls back to «Επεξεργασία» where it has none).
    delete_action = None
    can_create = True
    # Files stored on the row are deleted (and logged) with it.
    delete_attachments = False
    noun_saved = "η εγγραφή"
    noun_deleted = "η εγγραφή"

    # --- hooks -----------------------------------------------------------------------

    def action_for(self, kind, section):
        """Access type needed for `kind` ("view", "create", "edit" or "delete") on `section`."""
        if kind == "view":
            return VIEW
        if kind == "create":
            return self.create_action
        if kind == "edit":
            return self.edit_action
        return self.delete_action or delete_action_for(section)

    def get_case(self, request, pk, kind):
        return case_for_section(request, pk, self.section, self.action_for(kind, self.section))

    def queryset(self, case):
        return self.model.objects.filter(case=case)

    def new_instance(self, case):
        return self.model(case=case)

    def get_instance(self, case, obj_id):
        return get_object_or_404(self.queryset(case), pk=obj_id)

    def build_form(self, request, case, instance, data=None, files=None):
        return self.form_class(data, files, instance=instance)

    def grid_context(self, request, case):
        raise NotImplementedError

    def form_context(self, request, case, form):
        return {self.form_context_name: form}

    def grid_html(self, request, case):
        return render_to_string(
            self.grid_template, {"case": case, **self.grid_context(request, case)}, request=request
        )

    def form_html(self, request, case, form):
        return render_to_string(
            self.form_template, {"case": case, **self.form_context(request, case, form)}, request=request
        )

    def row_ref(self, request, case, instance):
        return self.section_ref

    def saved_message(self, instance, is_new):
        verb = "Προστέθηκε" if is_new else "Ενημερώθηκε"
        return f"{verb} {self.noun_saved} ({instance.row_label})."

    def deleted_message(self, label):
        return f"Διαγράφηκε {self.noun_deleted} {label}."

    def delete_label(self, instance):
        return instance.row_label

    def extra_payload(self, request, case):
        return {}

    def refuse_delete(self, request, case, instance):
        """A JsonResponse that stops the deletion, or None to go ahead."""
        return None

    def perform_delete(self, request, case, instance):
        section_ref = self.row_ref(request, case, instance)
        if self.delete_attachments:
            delete_with_attachments(instance, section_ref)
        else:
            instance._section_ref = section_ref
            instance.delete()

    # --- views -----------------------------------------------------------------------

    def form_view(self, request, pk, obj_id=None):
        if obj_id is None and not self.can_create:
            raise Http404()
        case = self.get_case(request, pk, "create" if obj_id is None else "edit")
        if not wants_json(request):
            raise Http404()
        instance = self.new_instance(case) if obj_id is None else self.get_instance(case, obj_id)

        if request.method == "POST":
            form = self.build_form(request, case, instance, request.POST, request.FILES)
            if not form.is_valid():
                return JsonResponse(
                    {"ok": False, "html": self.form_html(request, case, form)}, status=400
                )
            is_new = instance.pk is None
            instance._section_ref = self.row_ref(request, case, instance)
            with transaction.atomic():
                instance = form.save()
            return JsonResponse(
                {
                    "ok": True,
                    "message": self.saved_message(instance, is_new),
                    "grid_html": self.grid_html(request, case),
                    **self.extra_payload(request, case),
                }
            )
        if request.method != "GET":
            raise Http404()
        form = self.build_form(request, case, instance)
        return JsonResponse({"ok": True, "html": self.form_html(request, case, form)})

    def delete_view(self, request, pk, obj_id):
        case = self.get_case(request, pk, "delete")
        if request.method != "POST" or not wants_json(request):
            raise Http404("Επιτρέπεται μόνο POST.")
        instance = self.get_instance(case, obj_id)
        refusal = self.refuse_delete(request, case, instance)
        if refusal is not None:
            return refusal
        label = self.delete_label(instance)
        result = self.perform_delete(request, case, instance)
        if isinstance(result, JsonResponse):
            return result
        return JsonResponse(
            {
                "ok": True,
                "message": self.deleted_message(label),
                "grid_html": self.grid_html(request, case),
                **self.extra_payload(request, case),
            }
        )
