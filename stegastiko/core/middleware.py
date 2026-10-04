from contextvars import ContextVar
from urllib.parse import urlparse

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware


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
        token = _current_user.set(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)
