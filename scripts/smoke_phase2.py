#!/usr/bin/env python3
"""Live smoke test for Phase 2 (run AFTER a deploy). Uses real DynamoDB, Lambda and Bedrock.

    python scripts/smoke_phase2.py

What it does, using a clearly synthetic user ("smoke-test-planner"):
  1. creates a BUILDING course item,
  2. invokes the deployed process_syllabus Lambda synchronously with a short sample syllabus
     (Exam 1 on 2026-10-29; "Homework 3 is due the Friday after Exam 1" must resolve to 2026-10-30,
     dateSource "resolved"),
  3. prints the course status, pipeline and assignments and checks them,
  4. deletes every item it created, even if a step fails.
It never touches any other user's data: the only partition it deletes is USER#smoke-test-planner.
Needs AWS credentials for the stack's account and cdk-outputs.json (written by scripts/deploy.py).
"""
import json
import os
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

SUB = "smoke-test-planner"
PK = f"USER#{SUB}"
REGION = "us-east-1"
SYLLABUS = """MIS 999 Smoke Test Systems, Fall 2026. Instructor: Dr. Synthetic. Office hours Tuesday 2-4pm.
Meets Monday and Wednesday 9:00-9:50 in Room 101. Required book: Smoke Testing Basics by A. Tester.
Grading: Exams 60%, Homework 40%. Late work loses 10% per day. AI tools are allowed with citation.
Exam 1 is on October 29, 2026. Homework 3 is due the Friday after Exam 1.
Exam 2 is on December 4, 2026."""


def stack_resources():
    cf = boto3.client("cloudformation", region_name=REGION)
    res = {}
    for page in cf.get_paginator("list_stack_resources").paginate(StackName="SemesterOS"):
        for r in page["StackResourceSummaries"]:
            res[r["LogicalResourceId"]] = r["PhysicalResourceId"]
    return res


def main() -> int:
    resources = stack_resources()
    fn = next(v for k, v in resources.items() if k.startswith("ProcessSyllabusFunction") and "ServiceRole" not in k
              and "EventInvokeConfig" not in k and "LogRetention" not in k)
    table_name = next(v for k, v in resources.items() if k.startswith("AppTable") and k[8:].isalnum())
    os.environ["TABLE_NAME"], os.environ["REGION"] = table_name, REGION

    from lib import agents, db  # imported after TABLE_NAME is set

    failures = []
    course_id = None
    try:
        course = agents.create_course(SUB)
        course_id = course["id"]
        print(f"created course {course_id}; invoking {fn} ...")
        resp = boto3.client("lambda", region_name=REGION).invoke(
            FunctionName=fn, InvocationType="RequestResponse",
            Payload=json.dumps({"sub": SUB, "courseId": course_id, "text": SYLLABUS}).encode())
        print("lambda result:", resp["Payload"].read().decode(), "| function error:", resp.get("FunctionError"))

        got = db.get_item(PK, f"COURSE#{course_id}")
        print(f"\nstatus: {got['status']}  courseCode: {got.get('courseCode')!r}  title: {got.get('title')!r}")
        for s in got["pipeline"]:
            print(f"  [{s['state']:7}] {s['label']}: {s['detail']}")
        if got["status"] == "ERROR":
            print("error:", got.get("error"))
        asgs = {a["title"]: a for a in db.query_pk(PK, f"ASG#{course_id}#")}
        print("\nassignments:")
        for a in sorted(asgs.values(), key=lambda a: a.get("dueDate") or "9"):
            print(f"  {a['title']:<14} {a['type']:<9} due {a.get('dueDate')}  source={a.get('dateSource')}  text={a.get('dueText')!r}")

        if got["status"] != "READY":
            failures.append(f"status is {got['status']}, expected READY")
        hw3 = next((a for t, a in asgs.items() if "homework 3" in t.lower()), None)
        exam1 = next((a for t, a in asgs.items() if "exam 1" in t.lower()), None)
        if not exam1 or exam1.get("dueDate") != "2026-10-29":
            failures.append(f"Exam 1 date is {exam1 and exam1.get('dueDate')}, expected 2026-10-29")
        if not hw3 or hw3.get("dueDate") != "2026-10-30" or hw3.get("dateSource") != "resolved":
            failures.append(f"Homework 3 is {hw3 and (hw3.get('dueDate'), hw3.get('dateSource'))}, "
                            "expected ('2026-10-30', 'resolved')")
    finally:
        removed = db.delete_prefix(PK, "")  # only the synthetic user's partition
        left = db.query_pk(PK)
        print(f"\ncleanup: deleted {removed} items; {len(left)} left in {PK}")
        if left:
            failures.append(f"{len(left)} items were not cleaned up")

    print("\nRESULT:", "FAIL - " + "; ".join(failures) if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
