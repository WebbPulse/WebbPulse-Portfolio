# Backend tests

pytest suite for the portfolio API. DynamoDB and SSM are provided by moto, so
the suite runs anywhere with Python 3.13 and `requirements-dev.txt` installed.

```
tests/
├── conftest.py                 moto tables, TestClient, fixture data
├── test_app.py                 root, health, trailing slashes, CORS
├── test_auth_api.py            login and token flows
├── test_auth_hardening.py      expired/tampered tokens, seeding, login limiter
├── test_core_security.py       hashing and JWT unit tests
├── test_lambda_handler.py      API Gateway v2 events through the Lambda handler
├── test_migration.py           Postgres -> DynamoDB migration script
├── test_repository.py          serializer, repository, ordering
├── test_settings.py            env and SSM configuration
├── test_seo.py                 sitemap and robots
└── test_*_api.py               posts, projects, experience, skills, education,
                                certifications, site content
```

## How the fixtures work

`conftest.py` sets the environment before the app is imported (fake AWS
credentials, `DYNAMODB_TABLE_PREFIX=webbpulse-test`, the CI admin credentials)
and wraps every test in `mock_aws`, creating all tables from
`app.db.tables.table_definition`. Each test therefore starts with empty tables
and a fresh admin-seed state.

Fixtures such as `test_post` or `test_project` create rows through the
repositories and return plain dicts, so tests read `test_post["slug"]`. The
`client` fixture is a FastAPI `TestClient`; `admin_auth_headers` and
`auth_headers` carry tokens for the fixture admin and non-admin users.

## Running

```bash
venv/bin/python -m pytest
venv/bin/python -m pytest -m "api and not slow"
venv/bin/python -m pytest tests/test_auth_hardening.py -k limiter
venv/bin/python -m pytest --no-cov -q
```

Coverage is on by default (`pytest.ini`); reports go to the terminal,
`htmlcov/` and `coverage.xml`.

## Markers

`unit`, `integration`, `api`, `auth`, `admin`, `slow`.
