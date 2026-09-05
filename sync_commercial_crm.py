#!/usr/bin/env python3
"""Synchronize generated commercial opportunity context into CRM state storage."""

import argparse
from pathlib import Path

from procurement_intelligence.commercial_crm import (
    DB_DEFAULT,
    WORKSPACE_DEFAULT,
    load_workspace_csv,
    sync_opportunities,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=WORKSPACE_DEFAULT)
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = parser.parse_args()

    rows = load_workspace_csv(args.workspace)
    count = sync_opportunities(rows, args.db)
    print(f"Synchronized {count} canonical opportunity contexts into {args.db}")


if __name__ == "__main__":
    main()
