import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.tables import ENTITIES, META, TTL_ATTRIBUTE, table_definition  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Create DynamoDB tables locally")
    parser.add_argument(
        "--prefix",
        default=os.environ.get("DYNAMODB_TABLE_PREFIX", "webbpulse-development"),
    )
    parser.add_argument(
        "--endpoint-url",
        default=os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localhost:8000"),
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
    for entity in ENTITIES + (META,):
        definition = table_definition(prefix, entity)
        try:
            client.create_table(**definition)
            client.get_waiter("table_exists").wait(TableName=definition["TableName"])
            created.append(definition["TableName"])
            print(f"created {definition['TableName']}")
        except ClientError as error:
            if error.response["Error"]["Code"] != "ResourceInUseException":
                raise
            print(f"exists  {definition['TableName']}")
    meta_table = table_definition(prefix, META)["TableName"]
    ttl = client.describe_time_to_live(TableName=meta_table)["TimeToLiveDescription"]
    if ttl.get("TimeToLiveStatus") not in ("ENABLED", "ENABLING"):
        client.update_time_to_live(
            TableName=meta_table,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
        )
        print(f"ttl     {meta_table} ({TTL_ATTRIBUTE})")
    return created


if __name__ == "__main__":
    args = parse_args()
    create_tables(args.prefix, args.endpoint_url, args.region)
