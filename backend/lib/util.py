import json
import secrets
import string
from decimal import Decimal


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj == int(obj) else float(obj)
        return super().default(obj)


def ok(body: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, cls=_Encoder),
    }


def error(status: int, code: str, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": code, "message": message}),
    }


def short_id(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def normalize_domain(domain: str) -> str:
    """Extract root domain: crimson.ua.edu -> ua.edu"""
    parts = domain.lower().strip().rstrip('.').split('.')
    return '.'.join(parts[-2:]) if len(parts) >= 2 else domain.lower().strip()


def get_sub(event: dict) -> str:
    return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]


def get_email(event: dict) -> str:
    return event["requestContext"]["authorizer"]["jwt"]["claims"]["email"]


def to_dynamo(value):
    """DynamoDB rejects floats: convert them (recursively) to Decimal."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dynamo(v) for v in value]
    return value
