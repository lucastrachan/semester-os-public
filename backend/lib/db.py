import boto3
import os
from boto3.dynamodb.conditions import Key

_table = None


def table():
    global _table
    if _table is None:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("REGION", "us-east-1"))
        _table = dynamodb.Table(os.environ["TABLE_NAME"])
    return _table


def query_pk(pk_value: str, sk_prefix: str = None) -> list:
    kwargs = {"KeyConditionExpression": Key("pk").eq(pk_value)}
    if sk_prefix:
        kwargs["KeyConditionExpression"] &= Key("sk").begins_with(sk_prefix)
    items = []
    while True:  # follow pagination so lists past 1MB aren't silently truncated
        resp = table().query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def get_item(pk: str, sk: str) -> dict | None:
    resp = table().get_item(Key={"pk": pk, "sk": sk})
    return resp.get("Item")


def put_item(item: dict) -> None:
    table().put_item(Item=item)


def update_item(pk: str, sk: str, updates: dict) -> dict:
    expr_parts = []
    attr_names = {}
    attr_values = {}
    for i, (k, v) in enumerate(updates.items()):
        alias = f"#f{i}"
        val_alias = f":v{i}"
        expr_parts.append(f"{alias} = {val_alias}")
        attr_names[alias] = k
        attr_values[val_alias] = v
    resp = table().update_item(
        Key={"pk": pk, "sk": sk},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes", {})


def delete_item(pk: str, sk: str) -> None:
    table().delete_item(Key={"pk": pk, "sk": sk})


def incr_counter(pk: str, sk: str, ttl_epoch: int) -> int:
    """Atomically add 1 to a counter item and return the new value. The item expires at ttl_epoch."""
    resp = table().update_item(
        Key={"pk": pk, "sk": sk},
        UpdateExpression="ADD #n :one SET #t = if_not_exists(#t, :ttl)",
        ExpressionAttributeNames={"#n": "n", "#t": "ttl"},
        ExpressionAttributeValues={":one": 1, ":ttl": ttl_epoch},
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["n"])


def delete_prefix(pk: str, sk_prefix: str) -> int:
    """Delete every item under pk whose sort key starts with sk_prefix. Returns how many were deleted."""
    items = query_pk(pk, sk_prefix)
    with table().batch_writer() as batch:
        for it in items:
            batch.delete_item(Key={"pk": it["pk"], "sk": it["sk"]})
    return len(items)


def transact_put_items(items_with_conditions: list) -> None:
    """Write items atomically. items_with_conditions: list of (item_dict, condition_or_None).
    Raises ClientError (TransactionCanceledException) if any condition fails."""
    from lib import util
    tbl = table()
    transact_items = []
    for item, condition in items_with_conditions:
        put = {
            "TableName": tbl.name,
            "Item": util.to_dynamo(item),
        }
        if condition:
            put["ConditionExpression"] = condition
        transact_items.append({"Put": put})
    tbl.meta.client.transact_write_items(TransactItems=transact_items)


def claim_upload(pk: str, sk: str) -> bool:
    """Atomically flip a course's awaitingUpload flag from true to false. True only for the first caller,
    so a duplicate S3 event can't build the same class twice."""
    from botocore.exceptions import ClientError
    try:
        table().update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression="SET awaitingUpload = :f",
            ConditionExpression="awaitingUpload = :t",
            ExpressionAttributeValues={":f": False, ":t": True},
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
