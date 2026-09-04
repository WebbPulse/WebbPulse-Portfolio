import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for name, placeholder in (
    ("SECRET_KEY", "migration"),
    ("ADMIN_USERNAME", "migration"),
    ("ADMIN_PASSWORD", "migration"),
    ("ADMIN_EMAIL", "migration@example.com"),
):
    os.environ.setdefault(name, placeholder)

from app.db.entities import BY_ENTITY  # noqa: E402
from app.db.serializer import from_item, to_item  # noqa: E402

POSTGRES_TABLES = {
    "users": "users",
    "categories": "categories",
    "posts": "posts",
    "projects": "projects",
    "experience": "experience",
    "skills": "skills",
    "education": "education",
    "certifications": "certifications",
    "site_content": "site-content",
}

LIST_FIELDS = {
    "projects": ("technologies",),
    "experience": ("technologies", "achievements"),
    "site-content": ("about_paragraphs", "about_values"),
}

BOOL_DEFAULTS = {
    "users": {"is_admin": False, "is_active": True},
    "projects": {"featured": False, "is_active": True},
    "experience": {"is_active": True},
    "skills": {"is_active": True},
    "education": {"is_active": True},
    "certifications": {"is_active": True},
}


def transform_row(entity, row):
    data = {key: value for key, value in dict(row).items() if value is not None}
    data["id"] = int(data["id"])
    for field in LIST_FIELDS.get(entity, ()):
        data.setdefault(field, [])
    for field, default in BOOL_DEFAULTS.get(entity, {}).items():
        data.setdefault(field, default)
    for key, value in list(data.items()):
        if isinstance(value, (datetime, date)):
            data[key] = value
    return data


def expected_item(entity, row):
    repository = BY_ENTITY[entity]
    item = repository._apply_defaults(to_item(transform_row(entity, row)))
    item.update(to_item(repository.derive(item)))
    return from_item(item)


def fetch_rows(connection, table):
    from psycopg2.extras import RealDictCursor

    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f'SELECT * FROM "{table}" ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]


class TargetNotEmpty(Exception):
    def __init__(self, existing):
        self.existing = existing
        detail = ", ".join(f"{entity}={count}" for entity, count in existing.items())
        super().__init__(f"target tables already hold data ({detail}); use --replace")


def existing_counts():
    return {
        entity: BY_ENTITY[entity].count(include_inactive=True)
        for entity in POSTGRES_TABLES.values()
    }


def migrate(rows_by_table, dry_run=False, replace=False):
    existing = existing_counts()
    occupied = {entity: count for entity, count in existing.items() if count}
    if occupied and not replace and not dry_run:
        raise TargetNotEmpty(occupied)
    summary = {}
    for table, entity in POSTGRES_TABLES.items():
        rows = rows_by_table.get(table, [])
        repository = BY_ENTITY[entity]
        if replace and not dry_run:
            repository.purge()
        max_id = 0
        for row in rows:
            data = transform_row(entity, row)
            max_id = max(max_id, data["id"])
            if not dry_run:
                repository.import_item(data)
        if not dry_run:
            repository.set_counter(max_id)
        summary[entity] = {
            "rows": len(rows),
            "max_id": max_id,
            "existing": existing[entity],
        }
    return summary


def verify(rows_by_table):
    problems = []
    for table, entity in POSTGRES_TABLES.items():
        repository = BY_ENTITY[entity]
        rows = rows_by_table.get(table, [])
        max_id = 0
        for row in rows:
            expected = expected_item(entity, row)
            max_id = max(max_id, expected["id"])
            actual = repository.get(expected["id"], include_inactive=True)
            if actual is None:
                problems.append(f"{entity}#{expected['id']}: missing")
                continue
            for key, value in expected.items():
                if actual.get(key) != value:
                    problems.append(
                        f"{entity}#{expected['id']}.{key}: "
                        f"expected {value!r}, found {actual.get(key)!r}"
                    )
            for field in repository.unique_fields:
                value = expected.get(field)
                found = repository.find_by_unique(field, value) if value else None
                if value is not None and (
                    found is None or found["id"] != expected["id"]
                ):
                    problems.append(
                        f"{entity}#{expected['id']}: {field} lookup missing"
                    )
        stored = repository.count(include_inactive=True)
        if stored != len(rows):
            problems.append(
                f"{entity}: {len(rows)} rows in Postgres, {stored} in DynamoDB"
            )
        if max_id and repository.current_counter() < max_id:
            problems.append(
                f"{entity}: counter {repository.current_counter()} < {max_id}"
            )
    return problems


def parse_args():
    parser = argparse.ArgumentParser(
        description="Copy the Postgres portfolio database into DynamoDB"
    )
    parser.add_argument("dsn", nargs="?", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.dsn:
        sys.exit("Provide a Postgres DSN as the first argument or set DATABASE_URL")
    import psycopg2

    dsn = args.dsn.replace("postgresql+psycopg2://", "postgresql://")
    connection = psycopg2.connect(dsn)
    try:
        rows_by_table = {
            table: fetch_rows(connection, table) for table in POSTGRES_TABLES
        }
    finally:
        connection.close()

    if args.verify:
        problems = verify(rows_by_table)
        for problem in problems:
            print(problem)
        print(f"verify: {len(problems)} problem(s)")
        sys.exit(1 if problems else 0)

    try:
        summary = migrate(rows_by_table, dry_run=args.dry_run, replace=args.replace)
    except TargetNotEmpty as error:
        sys.exit(f"refusing to migrate: {error}")
    label = "would migrate" if args.dry_run else "migrated"
    for entity, stats in summary.items():
        print(
            f"{label} {stats['rows']:>4} {entity} "
            f"(counter -> {stats['max_id']}, target held {stats['existing']})"
        )
    if args.dry_run and any(stats["existing"] for stats in summary.values()):
        action = "will be purged by --replace" if args.replace else "blocks migration"
        print(f"target is not empty: existing data {action}")
    if args.dry_run:
        for table, entity in POSTGRES_TABLES.items():
            rows = rows_by_table.get(table)
            if rows:
                print(f"sample {entity}: {expected_item(entity, rows[0])}")


if __name__ == "__main__":
    main()
