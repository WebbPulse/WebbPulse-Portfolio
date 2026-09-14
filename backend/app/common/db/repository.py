"""The generic DynamoDB repository every entity is stored through.

Ids come from a counter item in the `meta` table and uniqueness from pointer
items beside it, both written in the same transaction as the row itself."""

from boto3.dynamodb.conditions import Attr, Key
from webbpulse.dynamodb import Repository as SharedRepository
from webbpulse.dynamodb import TransactionCanceled, transact_write

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


def shared_repository(entity):
    """A `webbpulse.dynamodb.Repository` over one entity, for its shared helpers.

    Built per call rather than held, so a test that moves the table prefix or the
    DynamoDB endpoint underneath the settings is read rather than a stale one.
    """
    return SharedRepository(
        logical_name=entity,
        prefix=settings.DYNAMODB_TABLE_PREFIX,
        endpoint_url=settings.DYNAMODB_ENDPOINT_URL,
    )


class UniqueViolation(Exception):
    """A unique field already holds this value on another row."""

    def __init__(self, field, value):
        """Record which field and value collided."""
        super().__init__(f"{field} '{value}' already exists")
        self.field = field
        self.value = value


class Repository:
    """CRUD over one entity's table, with ids, uniqueness and soft delete.

    Scans rather than queries, because the tables carry no sort key and every
    collection here is small enough to read whole."""

    def __init__(self, entity, unique_fields=(), soft_delete=False, defaults=None):
        """Configure the entity name, unique fields, soft delete and defaults."""
        self.entity = entity
        self.unique_fields = tuple(unique_fields)
        self.soft_delete_enabled = soft_delete
        self.defaults = dict(defaults or {})

    @property
    def table(self):
        """The boto3 Table for this entity."""
        return client.table(self.entity)

    @property
    def shared(self):
        """The shared repository over this entity's table."""
        return shared_repository(self.entity)

    @property
    def shared_meta(self):
        """The shared repository over the `meta` table."""
        return shared_repository(META)

    @property
    def meta(self):
        """The shared `meta` table holding counters and uniqueness pointers."""
        return client.table(META)

    @property
    def table_name(self):
        """This entity's table name under the configured prefix."""
        return table_name(settings.DYNAMODB_TABLE_PREFIX, self.entity)

    @property
    def meta_table_name(self):
        """The `meta` table's name under the configured prefix."""
        return table_name(settings.DYNAMODB_TABLE_PREFIX, META)

    def derive(self, item):
        """Attributes computed from the item itself; none by default."""
        return {}

    def counter_key(self):
        """The `meta` partition key holding this entity's id counter."""
        return f"{COUNTER_PREFIX}{self.entity}"

    def next_id(self):
        """Atomically increment and return the next id for this entity."""
        response = self.meta.update_item(
            Key={"pk": self.counter_key()},
            UpdateExpression="ADD seq :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["seq"])

    def set_counter(self, value):
        """Force the id counter to `value`, used after an import."""
        self.meta.put_item(Item={"pk": self.counter_key(), "seq": int(value)})

    def current_counter(self):
        """The id counter's current value, or 0 when it has never been set."""
        response = self.meta.get_item(Key={"pk": self.counter_key()})
        item = response.get("Item")
        return int(item["seq"]) if item else 0

    def unique_key(self, field, value):
        """The `meta` partition key reserving one value of one unique field."""
        return f"{UNIQUE_PREFIX}{self.entity}#{field}#{value}"

    def _unique_put(self, field, value, ref_id):
        """A transaction action claiming a unique value, failing if already held."""
        return self.shared_meta.put_action(
            {"pk": self.unique_key(field, value), "ref_id": ref_id},
            condition=Attr("pk").not_exists(),
        )

    def _unique_delete(self, field, value):
        """A transaction action releasing a unique value."""
        return self.shared_meta.delete_action({"pk": self.unique_key(field, value)})

    def _transact(self, actions, unique_claims):
        """Run a write transaction, translating a cancellation into a violation."""
        try:
            transact_write(
                actions,
                endpoint_url=settings.DYNAMODB_ENDPOINT_URL,
            )
        except TransactionCanceled as error:
            self._raise_unique_violation(error, actions, unique_claims)
            raise

    def _raise_unique_violation(self, error, actions, unique_claims):
        """Raise `UniqueViolation` for whichever claim the transaction refused."""
        for index, reason in enumerate(error.reasons):
            if reason.get("Code") == "ConditionalCheckFailed" and index in unique_claims:
                field, value = unique_claims[index]
                raise UniqueViolation(field, value)
        for field, value in unique_claims.values():
            if self.find_by_unique(field, value) is not None:
                raise UniqueViolation(field, value)

    def _unique_claims(self, actions, changes, item_id, previous=None):
        """Append claim and release actions for every changed unique field.

        Returns the action index of each claim so a cancellation can be
        attributed to the field that caused it."""
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
        """Fill in configured defaults and `is_active` on a soft deleting entity."""
        for key, value in self.defaults.items():
            if item.get(key) is None:
                item[key] = value() if callable(value) else value
        if self.soft_delete_enabled:
            item.setdefault("is_active", True)
        return item

    def create(self, data, item_id=None):
        """Insert a new row with a fresh id, claiming its unique values."""
        item = self._apply_defaults(to_item(data))
        item["id"] = int(item_id) if item_id is not None else self.next_id()
        item.setdefault("created_at", encode_datetime(utcnow()))
        item.update(to_item(self.derive(item)))
        actions = [self.shared.put_action(item, condition=Attr("id").not_exists())]
        claims = self._unique_claims(actions, item, item["id"])
        self._transact(actions, claims)
        return from_item(item)

    def import_item(self, data):
        """Write a row and its pointers without a transaction, for migrations."""
        item = self._apply_defaults(to_item(data))
        item.update(to_item(self.derive(item)))
        self.table.put_item(Item=item)
        for field in self.unique_fields:
            value = item.get(field)
            if value is not None:
                self.meta.put_item(Item={"pk": self.unique_key(field, value), "ref_id": item["id"]})
        return from_item(item)

    def purge(self):
        """Delete every row, its uniqueness pointers and the id counter."""
        removed = 0
        with self.table.batch_writer() as batch:
            for item in self.list_all(include_inactive=True):
                batch.delete_item(Key={"id": item["id"]})
                removed += 1
        prefix = f"{UNIQUE_PREFIX}{self.entity}#"
        pointers = self.shared_meta.iter_scan(
            filter_expression=Attr("pk").begins_with(prefix),
            projection="pk",
        )
        with self.meta.batch_writer() as batch:
            for pointer in pointers:
                batch.delete_item(Key={"pk": pointer["pk"]})
        self.meta.delete_item(Key={"pk": self.counter_key()})
        return removed

    def _visible(self, item, include_inactive):
        """The item, or `None` when soft deleted and inactive rows are excluded."""
        if item is None:
            return None
        if self.soft_delete_enabled and not include_inactive and not item.get("is_active", True):
            return None
        return item

    def get(self, item_id, include_inactive=False):
        """One row by id, or `None` when it is absent or soft deleted."""
        response = self.table.get_item(Key={"id": int(item_id)})
        return self._visible(from_item(response.get("Item")), include_inactive)

    def get_many(self, ids, include_inactive=False):
        """Several rows by id as a dict, batching and retrying unprocessed keys."""
        wanted = sorted({int(i) for i in ids if i is not None})
        found = {}
        for raw in self.shared.batch_get([{"id": i} for i in wanted]):
            item = self._visible(from_item(raw), include_inactive)
            if item is not None:
                found[item["id"]] = item
        return found

    def list_all(self, include_inactive=False):
        """Every row, paging through the scan."""
        items = []
        for raw in self.shared.iter_scan():
            item = self._visible(from_item(raw), include_inactive)
            if item is not None:
                items.append(item)
        return items

    def count(self, include_inactive=False):
        """How many rows are visible."""
        return len(self.list_all(include_inactive))

    def find_by_unique(self, field, value):
        """The row holding `value` for a unique field, through its pointer."""
        if value is None:
            return None
        response = self.meta.get_item(Key={"pk": self.unique_key(field, value)})
        pointer = response.get("Item")
        if not pointer:
            return None
        return self.get(int(pointer["ref_id"]), include_inactive=True)

    def update(self, item_id, changes):
        """Apply `changes` to one row, returning it or `None` when absent.

        Unchanged fields are dropped, `None` becomes a REMOVE, and a changed
        unique value is reclaimed in the same transaction as the update."""
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
        actions.insert(
            0,
            self.shared.update_action(
                {"id": int(item_id)},
                update_expression=expression,
                expression_names=names,
                expression_values=values or None,
                condition=Attr("id").exists(),
            ),
        )
        claims = {index + 1: claim for index, claim in claims.items()}
        self._transact(actions, claims)
        return self.get(item_id, include_inactive=True)

    def soft_delete(self, item_id):
        """Mark a row inactive, returning whether it existed."""
        return self.update(item_id, {"is_active": False}) is not None

    def hard_delete(self, item_id):
        """Delete a row and release its unique values, returning whether it existed."""
        current = self.get(item_id, include_inactive=True)
        if current is None:
            return False
        actions = [self.shared.delete_action({"id": int(item_id)})]
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
    """Posts, with the published flag and the two secondary indexes."""

    def derive(self, item):
        """The GSI partition key marking a post as published."""
        return {"published_flag": "1" if item.get("published_at") else None}

    def list_published(self, category_id=None):
        """Published posts newest first, optionally filtered to one category."""
        items = [
            from_item(raw)
            for raw in self.shared.iter_query(
                Key("published_flag").eq("1"),
                index_name=POSTS_PUBLISHED_INDEX,
                ascending=False,
            )
        ]
        if category_id is not None:
            items = [item for item in items if item.get("category_id") == category_id]
        return items

    def has_posts_in_category(self, category_id):
        """Whether any post references this category, used to refuse a delete."""
        response = self.table.query(
            IndexName=POSTS_CATEGORY_INDEX,
            KeyConditionExpression=Key("category_id").eq(int(category_id)),
            Select="COUNT",
            Limit=1,
        )
        return response.get("Count", 0) > 0
