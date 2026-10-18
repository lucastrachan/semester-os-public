#!/usr/bin/env python3
"""
Create a staff admin: python scripts/create_admin_user.py someone@example.com [--print-password]

Creates the user in the STAFF Cognito pool and adds them to the `admins` group. Cognito emails an
invitation with a temporary password (default). At first sign-in the person sets their own password
and enrols an authenticator app (TOTP). Run by Luca with his own AWS credentials; reads pool id
from cdk-outputs.json. Never run by agents.

  --print-password   do not email; print a generated temporary password instead (share it privately)
"""
import json
import re
import secrets
import string
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent


def temp_password() -> str:
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^*-_"]
    chars = [secrets.choice(p) for p in pools] + [secrets.choice("".join(pools)) for _ in range(12)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    print_pw = "--print-password" in sys.argv
    if len(args) != 1 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args[0]):
        print(__doc__)
        sys.exit(2)
    email = args[0].strip().lower()

    outputs = json.loads((ROOT / "cdk-outputs.json").read_text()).get("SemesterOS", {})
    pool_id = outputs.get("AdminUserPoolId")
    if not pool_id:
        print("ERROR: AdminUserPoolId not in cdk-outputs.json. Deploy the stack with AdminSite first.")
        sys.exit(1)
    region = pool_id.split("_")[0]
    idp = boto3.client("cognito-idp", region_name=region)

    kwargs = dict(
        UserPoolId=pool_id,
        Username=email,
        UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
        DesiredDeliveryMediums=["EMAIL"],
    )
    pw = None
    if print_pw:
        pw = temp_password()
        kwargs.update(TemporaryPassword=pw, MessageAction="SUPPRESS")
    idp.admin_create_user(**kwargs)
    idp.admin_add_user_to_group(UserPoolId=pool_id, Username=email, GroupName="admins")

    print(f"Created {email} and added to the admins group.")
    if pw:
        print(f"Temporary password (valid 3 days, share privately): {pw}")
    else:
        print("An invitation email with a temporary password was sent.")
    print("At first sign-in they choose a new password and set up an authenticator app.")


if __name__ == "__main__":
    main()
