from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from ..config import settings
from . import client
from .serializer import encode_datetime, encode_value, from_item, to_item, utcnow
from .tables import (
    COUNTER_PREFIX,
    META,
    POSTS_CATEGORY_INDEX,
    POSTS_PUBLISHED_INDEX,
    UNIQUE_PREFIX,
    table_name,
)

_serializer = TypeSerializer()


def marshal(data):
    return {k: _serializer.serialize(v) for k, v in data.items()}


class UniqueViolation(Exception):
    def __init__(self, field, value):
        super().__init__(f"{field} '{value}' already exists")
        self.field = field
        self.value = value


class Repository:
    def __init__(self, entity, unique_fields=(), soft_delete=False, defaults=None):
        self.entity = entity
        self.unique_fields = tuple(unique_fields)
        self.soft_delete_enabled = soft_delete
        self.defaults = dict(defaults or {})

    @property
    def table(self):
        return client.table(self.entity)

    @property
    def meta(self):
        return client.table(META)

    @property
    def table_name(self):
        return table_name(settings.DYNAMODB_TABLE_PREFIX, self.entity)

    @property
    def meta_table_name(self):
        return table_name(settings.DYNAMODB_TABLE_PREFIX, META)

    def derive(self, item):
        return {}

    def counter_key(self):
        return f"{COUNTER_PREFIX}{self.entity}"

    def next_id(self):
        response = self.meta.update_item(
            Key={"pk": self.counter_key()},
            UpdateExpression="ADD seq :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["seq"])

    def raise_counter_to(self, value):
        try:
            self.meta.update_item(
                Key={"pk": self.counter_key()},
                UpdateExpression="SET seq = :value",
                ConditionExpression="attribute_not_exists(seq) OR seq < :value",
                ExpressionAttributeValues={":value": int(value)},
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def current_counter(self):
        response = self.meta.get_item(Key={"pk": self.counter_key()})
        item = response.get("Item")
        return int(item["seq"]) if item else 0

    def unique_key(self, field, value):
        return f"{UNIQUE_PREFIX}{self.entity}#{field}#{value}"

    def _unique_put(self, field, value, ref_id):
        return {
            "Put": {
                "TableName": self.meta_table_name,
                "Item": marshal(
                    {"pk": self.unique_key(field, value), "ref_id": ref_id}
                ),
                "ConditionExpression": "attribute_not_exists(pk)",
            }
        }

    def _unique_delete(self, field, value):
        return {
            "Delete": {
                "TableName": self.meta_table_name,
                "Key": marshal({"pk": self.unique_key(field, value)}),
            }
        }

    def _transact(self, actions, unique_claims):
        try:
            client.dynamodb_client().transact_write_items(TransactItems=actions)
        except ClientError as error:
            if error.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            self._raise_unique_violation(error, actions, unique_claims)
            raise

    def _raise_unique_violation(self, error, actions, unique_claims):
        reasons = error.response.get("CancellationReasons") or []
        for index, reason in enumerate(reasons):
            if (
                reason.get("Code") == "ConditionalCheckFailed"
                and index in unique_claims
            ):
                field, value = unique_claims[index]
                raise UniqueViolation(field, value)
        for field, value in unique_claims.values():
            if self.find_by_unique(field, value) is not None:
                raise UniqueViolation(field, value)

    def _unique_claims(self, actions, changes, item_id, previous=None):
        claims = {}
        for field in self.unique_fields:
            if field not in changes:
                continue
            new_value = changes[field]
            old_value = previous.get(field) if previous else None
            if new_value == old_value:
                continue
            if new_value is not None:
                claims[len(actions)] = (field, new_value)
                actions.append(self._unique_put(field, new_value, item_id))
            if old_value is not None:
                actions.append(self._unique_delete(field, old_value))
        return claims

    def _apply_defaults(self, item):
        for key, value in self.defaults.items():
            if item.get(key) is None:
                item[key] = value() if callable(value) else value
        if self.soft_delete_enabled:
            item.setdefault("is_active", True)
        return item

    def create(self, data, item_id=None):
        item = self._apply_defaults(to_item(data))
        item["id"] = int(item_id) if item_id is not None else self.next_id()
        item.setdefault("created_at", encode_datetime(utcnow()))
        item.update(to_item(self.derive(item)))
        actions = [
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": marshal(item),
                    "ConditionExpression": "attribute_not_exists(id)",
                }
            }
        ]
        claims = self._unique_claims(actions, item, item["id"])
        self._transact(actions, claims)
        return from_item(item)

    def import_item(self, data):
        item = self._apply_defaults(to_item(data))
        item.update(to_item(self.derive(item)))
        self.table.put_item(Item=item)
        for field in self.unique_fields:
            value = item.get(field)
            if value is not None:
                self.meta.put_item(
                    Item={"pk": self.unique_key(field, value), "ref_id": item["id"]}
                )
        return from_item(item)

    def _visible(self, item, include_inactive):
        if item is None:
            return None
        if (
            self.soft_delete_enabled
            and not include_inactive
            and not item.get("is_active", True)
        ):
            return None
        return item

    def get(self, item_id, include_inactive=False):
        response = self.table.get_item(Key={"id": int(item_id)})
        return self._visible(from_item(response.get("Item")), include_inactive)

    def get_many(self, ids, include_inactive=False):
        wanted = sorted({int(i) for i in ids if i is not None})
        found = {}
        for start in range(0, len(wanted), 100):
            request = {
                self.table_name: {
                    "Keys": [{"id": i} for i in wanted[start : start + 100]]
                }
            }
            while request:
                response = client.dynamodb_resource().batch_get_item(
                    RequestItems=request
                )
                for raw in response.get("Responses", {}).get(self.table_name, []):
                    item = self._visible(from_item(raw), include_inactive)
                    if item is not None:
                        found[item["id"]] = item
                request = response.get("UnprocessedKeys") or None
        return found

    def list_all(self, include_inactive=False):
        items = []
        kwargs = {}
        while True:
            response = self.table.scan(**kwargs)
            for raw in response.get("Items", []):
                item = self._visible(from_item(raw), include_inactive)
                if item is not None:
                    items.append(item)
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return items
            kwargs["ExclusiveStartKey"] = last_key

    def count(self, include_inactive=False):
        return len(self.list_all(include_inactive))

    def find_by_unique(self, field, value):
        if value is None:
            return None
        response = self.meta.get_item(Key={"pk": self.unique_key(field, value)})
        pointer = response.get("Item")
        if not pointer:
            return None
        return self.get(int(pointer["ref_id"]), include_inactive=True)

    def update(self, item_id, changes):
        current = self.get(item_id, include_inactive=True)
        if current is None:
            return None
        changes = {k: encode_value(v) for k, v in changes.items() if k != "id"}
        changes = {k: v for k, v in changes.items() if current.get(k) != v}
        derived = to_item(self.derive({**current, **changes}))
        for key in self.derive(current):
            if derived.get(key) != current.get(key):
                changes[key] = derived.get(key)
        if not changes:
            return current
        changes["updated_at"] = encode_datetime(utcnow())
        names = {}
        values = {}
        sets = []
        removes = []
        for key, value in changes.items():
            names[f"#{key}"] = key
            if value is None:
                removes.append(f"#{key}")
            else:
                values[f":{key}"] = value
                sets.append(f"#{key} = :{key}")
        expression = " ".join(
            part
            for part in (
                f"SET {', '.join(sets)}" if sets else "",
                f"REMOVE {', '.join(removes)}" if removes else "",
            )
            if part
        )
        actions = []
        claims = self._unique_claims(actions, changes, int(item_id), current)
        if not actions:
            response = self.table.update_item(
                Key={"id": int(item_id)},
                UpdateExpression=expression,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values or None,
                ConditionExpression="attribute_exists(id)",
                ReturnValues="ALL_NEW",
            )
            return from_item(response["Attributes"])
        update = {
            "TableName": self.table_name,
            "Key": marshal({"id": int(item_id)}),
            "UpdateExpression": expression,
            "ExpressionAttributeNames": names,
            "ConditionExpression": "attribute_exists(id)",
        }
        if values:
            update["ExpressionAttributeValues"] = marshal(values)
        actions.insert(0, {"Update": update})
        claims = {index + 1: claim for index, claim in claims.items()}
        self._transact(actions, claims)
        return self.get(item_id, include_inactive=True)

    def soft_delete(self, item_id):
        return self.update(item_id, {"is_active": False}) is not None

    def hard_delete(self, item_id):
        current = self.get(item_id, include_inactive=True)
        if current is None:
            return False
        actions = [
            {
                "Delete": {
                    "TableName": self.table_name,
                    "Key": marshal({"id": int(item_id)}),
                }
            }
        ]
        for field in self.unique_fields:
            value = current.get(field)
            if value is not None:
                actions.append(self._unique_delete(field, value))
        if len(actions) == 1:
            self.table.delete_item(Key={"id": int(item_id)})
        else:
            self._transact(actions, {})
        return True


class PostRepository(Repository):
    def derive(self, item):
        return {"published_flag": "1" if item.get("published_at") else None}

    def list_published(self, category_id=None):
        items = []
        kwargs = {
            "IndexName": POSTS_PUBLISHED_INDEX,
            "KeyConditionExpression": Key("published_flag").eq("1"),
            "ScanIndexForward": False,
        }
        while True:
            response = self.table.query(**kwargs)
            items.extend(from_item(raw) for raw in response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        if category_id is not None:
            items = [item for item in items if item.get("category_id") == category_id]
        return items

    def has_posts_in_category(self, category_id):
        response = self.table.query(
            IndexName=POSTS_CATEGORY_INDEX,
            KeyConditionExpression=Key("category_id").eq(int(category_id)),
            Select="COUNT",
            Limit=1,
        )
        return response.get("Count", 0) > 0
