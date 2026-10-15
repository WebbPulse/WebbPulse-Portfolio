# Backend tests

pytest suite for the portfolio API. DynamoDB is provided by moto, so the suite
runs anywhere with Python 3.13 and `uv sync` run.

```
tests/
├── conftest.py                 moto tables and the TestClient
├── fixtures/                   route_contract.json: the 3 routes and
│                               documented operations the API publishes
├── common/                     root and health, settings, the error envelope,
│                               and the domain boundary and reachability rules
├── entrypoints/                route split, gateway route keys, wiring and the
│                               per-entrypoint import isolation probes
└── domains/                    one directory per deployed domain, each named
    │                           for its app/domains/<name>/entrypoint.py module
    └── public/                 live figures
```

CI derives its per-domain jobs from the `tests/domains` subdirectory names, so
adding a domain means adding a directory, not editing a list.

## How the fixtures work

`conftest.py` sets the environment before the app is imported (fake AWS
credentials, `DYNAMODB_TABLE_PREFIX=webbpulse-test`) and wraps every test in
`mock_aws`, creating every table from `app.common.db.tables.table_definition`.
Each test therefore starts with empty tables.

The `client` fixture builds root A, `app.common.composition.app`, which is every
domain's routers on one application. Both roots come from the one list in
`app.common.composition.wiring` that the deployed entrypoints also read, so a
route this client reaches is a route some domain function serves.

## Running

```bash
uv run python -m pytest
uv run python -m pytest -m "api and not slow"
uv run python -m pytest tests/domains/public
uv run python -m pytest tests --ignore=tests/domains
uv run python -m pytest --no-cov -q
```

Coverage is on by default (`pytest.ini`); reports go to the terminal,
`htmlcov/` and `coverage.xml`.

## Markers

`unit`, `integration`, `api`, `slow`.
