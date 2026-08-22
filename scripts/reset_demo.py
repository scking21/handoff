"""Reset the live demo: clears all tickets/messages from the shared table.

Usage: .venv/bin/python -m scripts.reset_demo [--yes]
"""

from __future__ import annotations

import argparse
import os

import boto3
from boto3.dynamodb.conditions import Key


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="skip confirmation")
    ap.add_argument("--table", default=os.getenv("HANDOFF_DDB_TABLE", "handoff"))
    args = ap.parse_args()

    if not args.yes:
        answer = input(f"Delete ALL rows in DynamoDB table '{args.table}'? [y/N] ")
        if answer.lower() != "y":
            print("aborted")
            return

    c = boto3.Session(profile_name=os.getenv("AWS_PROFILE")).client(
        "dynamodb", region_name=os.getenv("AWS_REGION", "us-east-2")
    )
    # Preserve the synthetic world (vendors/tenants/properties) — only clear
    # workflow artifacts so the board starts clean but the demo still runs.

    deleted = 0
    paginator = c.get_paginator("scan")
    for page in paginator.paginate(TableName=args.table):
        keys = [
            {"pk": it["pk"], "sk": it["sk"]}
            for it in page.get("Items", [])
            if it["pk"] in ("ticket", "message")
        ]
        for i in range(0, len(keys), 25):  # batch_write_item caps at 25
            chunk = [{"DeleteRequest": {"Key": k}} for k in keys[i:i + 25]]
            c.batch_write_item(RequestItems={args.table: chunk})
            deleted += len(chunk)
    print(f"deleted {deleted} rows from {args.table} — fresh demo world on next request")


if __name__ == "__main__":
    main()
