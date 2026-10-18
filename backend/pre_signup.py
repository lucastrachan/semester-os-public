"""Cognito pre-signup trigger: gate signups to .edu emails and demo accounts.

Rules (in order):
1. Demo accounts (DEMOACCT#{email}) bypass all checks — the account must exist in the table.
2. Non-.edu emails are rejected with a friendly message.
3. Blocked domains (BLOCKED_DOMAINS / D#{root}) are rejected.
4. Any .edu that passes the above is allowed — the campus is created lazily on first /me call.

The trigger must NOT create any table items: the user is not yet verified.
"""
import os
import boto3
from lib.registry import edu_root


def handler(event, context):
    attrs = event["request"]["userAttributes"]
    email = attrs["email"].lower().strip()
    domain = email.split("@")[-1].strip()

    raw_name = (attrs.get("name") or "").strip()
    if len(raw_name) < 2 or "@" in raw_name:
        raise Exception("Please enter your full name.")

    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("REGION", "us-east-1"))
    table = dynamodb.Table(os.environ["TABLE_NAME"])

    # 1. Demo account: email explicitly whitelisted regardless of domain
    demo = table.get_item(Key={"pk": f"DEMOACCT#{email}", "sk": "MAP"}).get("Item")
    if demo:
        return event

    # 2. Must be a .edu address
    root = edu_root(domain)
    if not root:
        raise Exception("Semester OS supports US colleges (.edu email addresses) for now.")

    # 3. Domain kill switch
    blocked = table.get_item(Key={"pk": "BLOCKED_DOMAINS", "sk": f"D#{root}"}).get("Item")
    if blocked:
        raise Exception(
            f"Signups from {root} are temporarily paused. "
            "Contact support if you think this is an error."
        )

    return event
