#!/usr/bin/env python3
"""
Full deploy: CDK → write config.json → npm build → S3 sync → CF invalidation.
Run from the repo root: python scripts/deploy.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INFRA = ROOT / "infra"
WEB = ROOT / "web"
OUTPUTS_FILE = ROOT / "cdk-outputs.json"


def run(cmd: str, cwd: Path = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n$ {cmd}")
    return subprocess.run(cmd, shell=True, cwd=str(cwd or ROOT), check=check)


def main():
    web_only = "--web-only" in sys.argv

    if web_only:
        # Skip CDK; use existing cdk-outputs.json
        if not OUTPUTS_FILE.exists():
            print("ERROR: cdk-outputs.json not found. Run a full deploy first.")
            sys.exit(1)
        with open(OUTPUTS_FILE) as f:
            outputs = json.load(f).get("SemesterOS", {})
        config = {
            "region": "us-east-1",
            "userPoolId": outputs["UserPoolId"],
            "userPoolClientId": outputs["UserPoolClientId"],
            "apiUrl": outputs["ApiUrl"],
        }
        config_path = WEB / "public" / "config.json"
        config_path.parent.mkdir(exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2))
        print(f"Wrote {config_path}")
        run("npm install", cwd=WEB)
        run("npm run build", cwd=WEB)
        bucket = outputs["WebsiteBucketName"]
        run(f'aws s3 sync "{WEB / "dist"}" s3://{bucket}/ --delete')
        run(f'aws cloudfront create-invalidation --distribution-id {outputs["DistributionId"]} --paths "/*"')
        print(f"\nDone!  {outputs['CloudFrontUrl']}")
        return

    # 1. Set up infra venv if needed
    venv = INFRA / ".venv"
    if not venv.exists():
        print("Creating infra virtualenv...")
        run(f"python -m venv {venv}", cwd=INFRA)

    pip = venv / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    run(f'"{pip}" install -q -r requirements.txt', cwd=INFRA)

    # 1b. Vendor the pure-Python libraries the Lambdas import (pypdf). CDK bundles backend/ as-is.
    backend = ROOT / "backend"
    run(f'"{pip}" install -q --upgrade -r "{backend / "requirements.txt"}" -t "{backend / "vendor"}"')

    # 2. CDK deploy
    venv_python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    run(f'npx aws-cdk deploy --app "{venv_python} infra/app.py" --outputs-file "{OUTPUTS_FILE}" --require-approval never', cwd=ROOT)

    # 3. Read outputs
    with open(OUTPUTS_FILE) as f:
        raw = json.load(f)
    outputs = raw.get("SemesterOS", {})

    required = ["WebsiteBucketName", "DistributionId", "UserPoolId", "UserPoolClientId", "ApiUrl", "CloudFrontUrl"]
    missing = [k for k in required if k not in outputs]
    if missing:
        print(f"ERROR: missing CDK outputs: {missing}")
        sys.exit(1)

    # 4. Write config.json for the frontend
    config = {
        "region": "us-east-1",
        "userPoolId": outputs["UserPoolId"],
        "userPoolClientId": outputs["UserPoolClientId"],
        "apiUrl": outputs["ApiUrl"],
    }
    config_path = WEB / "public" / "config.json"
    config_path.parent.mkdir(exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    print(f"Wrote {config_path}")

    # 5. Build frontend
    run("npm install", cwd=WEB)
    run("npm run build", cwd=WEB)

    # 6. Sync to S3
    bucket = outputs["WebsiteBucketName"]
    dist_path = WEB / "dist"
    run(f'aws s3 sync "{dist_path}" s3://{bucket}/ --delete')

    # 7. Invalidate CloudFront
    dist_id = outputs["DistributionId"]
    run(f'aws cloudfront create-invalidation --distribution-id {dist_id} --paths "/*"')

    print(f"\nDone!  {outputs['CloudFrontUrl']}")  # plain ASCII: a checkmark crashes cp1252 consoles


if __name__ == "__main__":
    main()
