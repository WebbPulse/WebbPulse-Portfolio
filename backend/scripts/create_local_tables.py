import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.tables import ALL_TABLES, table_definition  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Create DynamoDB tables locally")
    parser.add_argument(
        "--prefix",
        default=os.environ.get("DYNAMODB_TABLE_PREFIX", "webbpulse-development"),
    )
    parser.add_argument(
        "--endpoint-url",
        default=os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localhost:8001"),
    )
    parser.add_argument(
        "--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
    )
    return parser.parse_args()


def create_tables(prefix, endpoint_url, region):
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
    client = boto3.client("dynamodb", endpoint_url=endpoint_url, region_name=region)
    created = []
    # `ALL_TABLES` pairs each table with the TTL attribute it enables, or None.
    # The names are not all the same on purpose: `meta` has always used `ttl`,
    # while `rate-limits` and the two identity tables use the `expires_at` that
    # `webbpulse.ratelimit`, `webbpulse.identity` and the Terraform declarations
    # all name. `credentials` has no TTL at all and must not grow one.
    for entity, ttl_attribute in ALL_TABLES:
        definition = table_definition(prefix, entity)
        table = definition["TableName"]
        try:
            client.create_table(**definition)
            client.get_waiter("table_exists").wait(TableName=table)
            created.append(table)
            print(f"created {table}")
        except ClientError as error:
            if error.response["Error"]["Code"] != "ResourceInUseException":
                raise
            print(f"exists  {table}")
        if ttl_attribute is None:
            continue
        ttl = client.describe_time_to_live(TableName=table)["TimeToLiveDescription"]
        if ttl.get("TimeToLiveStatus") not in ("ENABLED", "ENABLING"):
            client.update_time_to_live(
                TableName=table,
                TimeToLiveSpecification={
                    "Enabled": True,
                    "AttributeName": ttl_attribute,
                },
            )
            print(f"ttl     {table} ({ttl_attribute})")
    return created


if __name__ == "__main__":
    args = parse_args()
    create_tables(args.prefix, args.endpoint_url, args.region)
