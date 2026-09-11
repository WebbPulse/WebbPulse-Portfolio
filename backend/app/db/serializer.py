"""Convert between Python values and the types DynamoDB accepts.

Datetimes become UTC ISO strings, floats become Decimals, and `None` is dropped
rather than stored so a missing attribute and a null are the same thing."""

from datetime import date, datetime, timezone
from decimal import Decimal


def utcnow():
    """The current time as a timezone aware UTC datetime."""
    return datetime.now(timezone.utc)


def encode_datetime(value):
    """A datetime as a UTC ISO string, assuming UTC when it is naive."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def encode_value(value):
    """One value in the form DynamoDB accepts, recursing into containers."""
    if isinstance(value, datetime):
        return encode_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: encode_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_value(v) for v in value]
    return value


def to_item(data):
    """Encode a dict for DynamoDB, dropping every `None` value."""
    return {k: encode_value(v) for k, v in data.items() if v is not None}


def decode_value(value):
    """One value back in Python form, narrowing Decimals to int or float."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: decode_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode_value(v) for v in value]
    return value


def from_item(item):
    """Decode a DynamoDB item, passing `None` through unchanged."""
    if item is None:
        return None
    return {k: decode_value(v) for k, v in item.items()}


def parse_datetime(value):
    """Parse a stored ISO datetime, accepting a trailing `Z`."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_date(value):
    """Parse a stored ISO date, passing a date or `None` through."""
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)
