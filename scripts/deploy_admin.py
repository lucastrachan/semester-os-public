#!/usr/bin/env python3
"""
Deploy the admin site ONLY (the stack must already include AdminSite; run scripts/deploy.py first
for infrastructure changes). Reads CDK outputs -> writes admin/public/config.json -> builds -> syncs
to the admin bucket -> invalidates the admin CloudFront distribution.
Run from the repo root: python scripts/deploy_admin.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADMIN = ROOT / "admin"
OUTPUTS_FILE = ROOT / "cdk-outputs.json"


def run(cmd: str, cwd: Path = None) -> None:
    print(f"\n$ {cmd}")
    subprocess.run(cmd, shell=True, cwd=str(cwd or ROOT), check=True)


def check_csp_pinned(outputs: dict) -> None:
    """Read-only HTTP HEAD of the admin site: warn if the CSP still allows every execute-api host."""
    import urllib.request
    try:
        req = urllib.request.Request(outputs["AdminSiteUrl"], method="HEAD")
        csp = urllib.request.urlopen(req, timeout=15).headers.get("Content-Security-Policy", "")
    except Exception as e:  # not fatal
        print(f"(could not check the live CSP: {e})")
        return
    if "*.execute-api" in csp:
        api = outputs["ApiUrl"].rstrip("/")
        print("\nWARNING: the admin CSP still allows any execute-api host. Pin it:")
        print(f'  add  "adminApiOrigin": "{api}"  to the "context" block in cdk.json,')
        print("  run scripts/deploy.py once more, then scripts/deploy_admin.py is not needed again.")


def main():
    if not OUTPUTS_FILE.exists():
        print("ERROR: cdk-outputs.json not found. Deploy the stack first (scripts/deploy.py).")
        sys.exit(1)
    outputs = json.loads(OUTPUTS_FILE.read_text()).get("SemesterOS", {})

    required = ["AdminUserPoolId", "AdminClientId", "AdminBucketName", "AdminDistributionId",
                "AdminSiteUrl", "ApiUrl"]
    missing = [k for k in required if k not in outputs]
    if missing:
        print(f"ERROR: missing CDK outputs: {missing}. Has the stack been deployed with AdminSite?")
        sys.exit(1)

    # Region is the second part of the pool id (us-east-1_XXXX).
    region = outputs["AdminUserPoolId"].split("_")[0]
    config = {
        "region": region,
        "adminUserPoolId": outputs["AdminUserPoolId"],
        "adminClientId": outputs["AdminClientId"],
        "apiUrl": outputs["ApiUrl"],
    }
    config_path = ADMIN / "public" / "config.json"
    config_path.parent.mkdir(exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    print(f"Wrote {config_path}")

    run("npm install", cwd=ADMIN)
    run("npm run build", cwd=ADMIN)

    bucket = outputs["AdminBucketName"]
    run(f'aws s3 sync "{ADMIN / "dist"}" s3://{bucket}/ --delete')
    run(f'aws cloudfront create-invalidation --distribution-id {outputs["AdminDistributionId"]} --paths "/*"')

    print(f"\nDone. Admin console: {outputs['AdminSiteUrl']}")
    check_csp_pinned(outputs)


if __name__ == "__main__":
    main()
