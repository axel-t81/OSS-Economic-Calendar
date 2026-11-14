"""
Production settings. Used by wsgi.py / asgi.py.

Fail-fast contract — these must be set in the environment before boot:
    DJANGO_SECRET_KEY       (required)
    DJANGO_ALLOWED_HOSTS    (required, comma-separated)
"""

import os

from .base import *  # noqa: F403

DEBUG = False

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
if not ALLOWED_HOSTS:
    raise RuntimeError(
        "DJANGO_ALLOWED_HOSTS is required in production "
        "(comma-separated, e.g. 'your-app.fly.dev,yourdomain.com')"
    )

# Behind Fly's TLS-terminating proxy; X-Forwarded-Proto carries the scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HTTPS / transport security
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000  # one year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookies: secure-only in production
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Sensible default security headers
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # set when the Fly domain is known

# Outbound email over SMTP for the daily digest.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
