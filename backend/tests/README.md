# Backend tests

pytest suite for the portfolio API. DynamoDB and Secrets Manager are provided
by moto, so the suite runs anywhere with Python 3.13 and `uv sync` run.

```
tests/
├── conftest.py                 moto tables, TestClient, fixture data
├── fixtures/                   route_contract.json: the 44 routes and 42
│                               documented operations the API publishes
├── entrypoints/                per-entrypoint route split and wiring
├── domains/                    one directory per deployed domain, each named
│   │                           for its app/entrypoints/<name>.py module
│   ├── content/                posts, site content
│   ├── identity/               auth, tokens, hashing, seeding, migrations
│   ├── public/                 sitemap and robots
│   └── resume/                 projects, experience, skills, education,
│                               certifications
├── test_app.py                 root, health, trailing slashes, CORS
├── test_migration.py           Postgres -> DynamoDB migration script
├── test_repository.py          serializer, repository, ordering
└── test_settings.py            env and Secrets Manager configuration
```

CI derives its per-domain jobs from the `tests/domains` subdirectory names, so
adding a domain means adding a directory, not editing a list.

## How the fixtures work

`conftest.py` sets the environment before the app is imported (fake AWS
credentials, `DYNAMODB_TABLE_PREFIX=webbpulse-test`, the CI admin credentials)
and wraps every test in `mock_aws`, creating all tables from
`app.db.tables.table_definition`. Each test therefore starts with empty tables
and a fresh admin-seed state.

The `client` fixture builds root A, `app.composition.app`, which is every
domain's routers on one application. It used to build `app.main`, the monolith,
which is deleted. Both roots come from the one list in `app.composition.wiring`
that the four deployed entrypoints also read, so a route this client reaches is
a route some domain function serves.

Fixtures such as `test_post` or `test_project` create rows through the
repositories and return plain dicts, so tests read `test_post["slug"]`. The
`client` fixture is a FastAPI `TestClient`; `admin_auth_headers` and
`auth_headers` carry tokens for the fixture admin and non-admin users.

## Running

```bash
uv run python -m pytest
uv run python -m pytest -m "api and not slow"
uv run python -m pytest tests/domains/identity/test_auth_hardening.py -k limiter
uv run python -m pytest tests/domains/content
uv run python -m pytest tests --ignore=tests/domains
uv run python -m pytest --no-cov -q
```

Coverage is on by default (`pytest.ini`); reports go to the terminal,
`htmlcov/` and `coverage.xml`.

## Markers

`unit`, `integration`, `api`, `auth`, `admin`, `slow`.
