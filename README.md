# OSS Economic Calendar

A free, open-source economic calendar — starting with Australian indicators.
No subscriptions, no paywalls: everything the commercial calendars offer, MIT licensed.

Each release records the three data points that matter:

| Actual result | Previous value | Consensus forecast |
| --- | --- | --- |

Plus a **daily email digest** summarising yesterday's results, so nothing slips past you.

## Status

🚧 **Early development.** Foundations are in place (Django project, security-hardened
settings, CI-ready tooling). The calendar itself is next — see the [roadmap](#roadmap).

## Tech stack

- **Backend:** Django 5.2 LTS · Python 3.13
- **Database:** SQLite (persistent-volume friendly — deployable on Fly.io for ~$2–4/month)
- **Frontend:** Django templates, plain HTML/CSS, [htmx](https://htmx.org) (vendored, no build step)
- **Tooling:** [uv](https://docs.astral.sh/uv/) for dependencies, ruff for lint/format
- **Hosting:** Fly.io (primary target)

## Getting started

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.13+.

```bash
uv sync                                   # create .venv and install dependencies
cp .env.example .env                      # optional in development; see comments inside
uv run python manage.py migrate
uv run python manage.py createsuperuser   # for /admin
uv run python manage.py runserver         # http://127.0.0.1:8000
```

Run the checks:

```bash
uv run python manage.py test
uv run ruff check . && uv run ruff format --check .
```

## Environment variables

Development works out of the box with sensible defaults (console email backend,
insecure dev secret key). Production has a fail-fast contract — `DJANGO_SECRET_KEY`
and `DJANGO_ALLOWED_HOSTS` must be set. See [.env.example](.env.example) for the full list.

## Roadmap

1. **Models + admin** — `Indicator` and `Event` models with result / previous / forecast
2. **Calendar UI** — past & upcoming releases, htmx-powered partial updates
3. **Daily email digest** — management command + scheduled job
4. **Fly.io deployment** — persistent volume at `/data` for SQLite, secrets via `fly secrets`
5. **Broader coverage** — beyond Australian indicators once the core is solid

## Why SQLite on Fly?

Fly.io mounts persistent volumes to a VM, so the SQLite file survives restarts and
deploys — no managed database bill, and this project's scale (single-user reads, a
write per release day) is exactly what SQLite is built for. Alternatives considered:
PythonAnywhere's free tier, a small DigitalOcean droplet, and self-hosting behind a
Cloudflare Tunnel.

## Contributing

Issues and PRs welcome. All work happens on feature branches, reviewed via pull
requests before merging into `main`.

## License

[MIT](LICENSE)
