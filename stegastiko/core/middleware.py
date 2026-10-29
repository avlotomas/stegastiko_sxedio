from contextvars import ContextVar
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from django.shortcuts import redirect
from django.urls import reverse


_current_user = ContextVar("current_user", default=None)


def get_current_user():
    return _current_user.get()


class DevTunnelCsrfMiddleware(CsrfViewMiddleware):
    """Trust https://*.lhr.life CSRF origins in DEBUG (localhost.run temp URLs)."""

    @staticmethod
    def _is_trusted_lhr_life_url(url: str) -> bool:
        if not settings.DEBUG or not url:
            return False
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return parsed.scheme == "https" and host.endswith(".lhr.life")

    def _origin_verified(self, request):
        origin = request.META.get("HTTP_ORIGIN")
        if self._is_trusted_lhr_life_url(origin):
            return True
        return super()._origin_verified(request)

    def _check_referer(self, request):
        referer = request.META.get("HTTP_REFERER")
        if self._is_trusted_lhr_life_url(referer):
            return
        return super()._check_referer(request)


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        token = _current_user.set(user)
        try:
            if user and user.is_authenticated:
                from core.models import user_must_change_password

                if user_must_change_password(user):
                    account_url = reverse("account")
                    logout_url = reverse("logout")
                    static_url = getattr(settings, "STATIC_URL", "/static/")
                    if request.path not in (account_url, logout_url) and not (
                        static_url and request.path.startswith(static_url)
                    ):
                        return redirect("account")
            return self.get_response(request)
        finally:
            _current_user.reset(token)


EMBED_PARAM = "embed"


def _with_embed_param(location: str) -> str:
    parsed = urlparse(location)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != EMBED_PARAM]
    query.append((EMBED_PARAM, "1"))
    return urlunparse(parsed._replace(query=urlencode(query)))


class EmbedModeMiddleware:
    """Pages opened inside a modal iframe (``?embed=1``) render without the site chrome.

    The flag is carried by GET/POST and re-applied to same-origin redirects so that
    form submissions inside the modal stay in embedded mode.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_embed = request.GET.get(EMBED_PARAM) == "1"
        if not is_embed and request.method == "POST":
            content_type = request.content_type or ""
            if content_type in ("application/x-www-form-urlencoded", "multipart/form-data"):
                is_embed = request.POST.get(EMBED_PARAM) == "1"
        request.is_embed = is_embed
        response = self.get_response(request)
        if is_embed and 300 <= response.status_code < 400 and response.has_header("Location"):
            location = response["Location"]
            parsed = urlparse(location)
            if not parsed.netloc or parsed.netloc == request.get_host():
                response["Location"] = _with_embed_param(location)
        return response
