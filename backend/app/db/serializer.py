from datetime import date, datetime, timezone
from decimal import Decimal


def utcnow():
    return datetime.now(timezone.utc)


def encode_datetime(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def encode_value(value):
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
    return {k: encode_value(v) for k, v in data.items() if v is not None}


def decode_value(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: decode_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode_value(v) for v in value]
    return value


def from_item(item):
    if item is None:
        return None
    return {k: decode_value(v) for k, v in item.items()}


def parse_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)
