from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from applications.models import Person


class PersonLookupAndEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.admin = user_model.objects.create_superuser("pa_super", "pa_super@example.com", "pw")
        cls.plain = user_model.objects.create_user("pa_plain", "pa_plain@example.com", "pw")
        cls.person = Person.objects.create(
            identity_number="1234567",
            first_name="Γιώργος",
            last_name="Παπαδόπουλος",
            date_of_birth=date(1990, 5, 17),
            birth_place="Λευκωσία",
            birth_country="Κύπρος",
            parents_birth_place="Λάρνακα",
            parents_birth_country="Κύπρος",
        )

    def test_lookup_returns_registered_person(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("plot_applications:person_lookup"), {"identity": " 1234567 "})
        data = response.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["person"]["first_name"], "Γιώργος")
        self.assertEqual(data["person"]["date_of_birth"], "1990-05-17")
        self.assertTrue(data["can_edit"])
        self.assertEqual(data["edit_url"], reverse("plot_applications:person_edit", args=[self.person.pk]))

    def test_lookup_unknown_identity_is_not_found(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("plot_applications:person_lookup"), {"identity": "999"})
        self.assertEqual(response.json(), {"found": False})
        response = self.client.get(reverse("plot_applications:person_lookup"))
        self.assertEqual(response.json(), {"found": False})

    def test_lookup_requires_access(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("plot_applications:person_lookup"), {"identity": "1234567"})
        self.assertEqual(response.status_code, 403)

    def test_edit_dialog_locks_identity_number(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("plot_applications:person_edit", args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-person-edit-form")
        self.assertContains(response, "Γιώργος")

    def test_edit_saves_changes_and_keeps_identity_number(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("plot_applications:person_edit", args=[self.person.pk]),
            {
                "identity_number": "TAMPERED",
                "first_name": "Γεώργιος",
                "last_name": "Παπαδόπουλος",
                "date_of_birth": "1990-05-17",
                "birth_place": "Λευκωσία",
                "birth_country": "Κύπρος",
                "parents_birth_place": "Λάρνακα",
                "parents_birth_country": "Κύπρος",
                "document_type": "",
            },
        )
        data = response.json()
        self.assertTrue(data["saved"])
        self.assertEqual(data["person"]["first_name"], "Γεώργιος")
        self.person.refresh_from_db()
        self.assertEqual(self.person.first_name, "Γεώργιος")
        self.assertEqual(self.person.identity_number, "1234567")

    def test_edit_with_errors_returns_form(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("plot_applications:person_edit", args=[self.person.pk]),
            {"first_name": "", "last_name": "Παπαδόπουλος"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "data-person-edit-form", status_code=422)
        self.person.refresh_from_db()
        self.assertEqual(self.person.first_name, "Γιώργος")

    def test_edit_requires_persons_edit_access(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("plot_applications:person_edit", args=[self.person.pk]))
        self.assertEqual(response.status_code, 403)

    def test_application_form_renders_search_button_and_dialog(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("plot_applications:create"))
        self.assertContains(response, "data-person-block=", count=2)
        self.assertContains(response, "data-person-edit-dialog")
        self.assertContains(response, reverse("plot_applications:person_lookup"))
