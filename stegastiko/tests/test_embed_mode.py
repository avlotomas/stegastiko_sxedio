"""Embedded (modal iframe) mode used by the announcement workspace."""

import pytest
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory
from django.urls import reverse

from core.middleware import EmbedModeMiddleware
from tests.test_plot_applications import (  # noqa: F401
    available_plot,
    community,
    cycle,
    staff_client,
)


def _run(request, response):
    return EmbedModeMiddleware(lambda req: response)(request)


class TestEmbedModeMiddleware:
    def test_redirect_keeps_embed_flag(self):
        request = RequestFactory().get("/x/?embed=1")
        response = _run(request, HttpResponseRedirect("/plot-applications/5/?tab=a"))
        assert request.is_embed is True
        assert response["Location"] == "/plot-applications/5/?tab=a&embed=1"

    def test_post_flag_is_detected(self):
        request = RequestFactory().post("/x/", {"embed": "1"})
        response = _run(request, HttpResponseRedirect("/y/"))
        assert request.is_embed is True
        assert response["Location"] == "/y/?embed=1"

    def test_external_redirect_and_normal_requests_are_untouched(self):
        request = RequestFactory().get("/x/?embed=1")
        response = _run(request, HttpResponseRedirect("https://example.org/a"))
        assert response["Location"] == "https://example.org/a"

        plain = RequestFactory().get("/x/")
        response = _run(plain, HttpResponse("ok"))
        assert plain.is_embed is False


@pytest.mark.django_db
class TestEmbeddedPages:
    def test_prioritization_embedded_hides_site_header(self, staff_client, cycle):
        url = reverse("plot_applications:prioritization")
        full = staff_client.get(url, {"community_id": cycle.community.pk})
        embedded = staff_client.get(url, {"community_id": cycle.community.pk, "embed": "1"})
        assert full.status_code == embedded.status_code == 200
        assert b'class="site-header"' in full.content
        assert b'class="site-header"' not in embedded.content
        assert b"data-embed-mode" in embedded.content
        assert embedded["X-Frame-Options"] == "SAMEORIGIN"

    def test_announcement_workspace_opens_pages_in_modal(self, staff_client, cycle):
        response = staff_client.get(reverse("announcements:detail", args=[cycle.pk]))
        content = response.content.decode()
        assert "data-embed-dialog" in content
        assert (
            f'data-embed-stay-prefix="{reverse("announcements:detail", args=[cycle.pk])}"' in content
        )
        assert "data-open-prioritization" in content
