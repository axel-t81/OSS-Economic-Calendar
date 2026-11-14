"""Local development settings. Used by manage.py by default."""

from .base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Email backend comes from base.py and defaults to the console backend,
# so outbound mail is printed to the runserver terminal during development.
