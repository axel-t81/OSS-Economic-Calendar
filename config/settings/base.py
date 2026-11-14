"""
Shared settings for the OSS Economic Calendar.

Environment variables (all optional in development, see .env.example):
    DJANGO_SECRET_KEY       Django secret key (production: required, no default)
    DJANGO_DEBUG            "True"/"False" (base default: False)
    DJANGO_ALLOWED_HOSTS    Comma-separated hostnames
    DJANGO_DB_PATH          SQLite file path (absolute path supported, e.g. /data/db.sqlite3 on Fly)
    DJANGO_EMAIL_BACKEND    Dotted path to email backend (default: console)
    DJANGO_EMAIL_HOST       SMTP host
    DJANGO_EMAIL_PORT       SMTP port
    DJANGO_EMAIL_HOST_USER  SMTP username
    DJANGO_EMAIL_HOST_PASSWORD  SMTP password
    DJANGO_DEFAULT_FROM_EMAIL   Default "from" address for outbound email
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# config/settings/base.py -> config/settings/ -> config/ -> project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Local development convenience: load a .env file if present. Real environment
# variables always take precedence (load_dotenv does not override them).
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable into a list."""
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# SECURITY WARNING: this default is for local development only. Production
# settings require DJANGO_SECRET_KEY to be set in the environment.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-dev-only-key-do-not-use-in-production"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "").lower() in {"true", "1", "yes"}

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "events.apps.EventsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # pathlib handles absolute DJANGO_DB_PATH values (e.g. /data/db.sqlite3 on Fly)
        "NAME": BASE_DIR / os.environ.get("DJANGO_DB_PATH", "db.sqlite3"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Australian economic data is released in AEST/AEDT (Sydney time).
LANGUAGE_CODE = "en-au"
TIME_ZONE = "Australia/Sydney"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Email — the daily "yesterday's results" digest will use these.
# Development defaults to the console backend; production switches to SMTP.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("DJANGO_EMAIL_USE_TLS", "true").lower() in {"true", "1", "yes"}
DEFAULT_FROM_EMAIL = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL", "OSS Economic Calendar <no-reply@example.com>"
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
