"""
Usage:
    python 01_create_database.py <database_name> [--dry-run]

Example:
    python 01_create_database.py RESORT_DB
    python 01_create_database.py RESORT_DB --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.deployer import Deployer


MEDALLION_SCHEMAS = ["BRONZE", "SILVER", "GOLD", "PLATINUM"]


def build_statements(database: str) -> list[tuple[str, str]]:
    statements = []
    statements.append((
        f"Create database {database}",
        f"CREATE DATABASE IF NOT EXISTS {database}",
    ))
    for schema in MEDALLION_SCHEMAS:
        statements.append((
            f"Create schema {database}.{schema}",
            f"CREATE SCHEMA IF NOT EXISTS {database}.{schema}",
        ))
    return statements


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Snowflake database with medallion schemas.")
    parser.add_argument("database", help="Database name to create")
    parser.add_argument("--dry-run", action="store_true", help="Generate SQL without executing")
    args = parser.parse_args()

    database = args.database.strip().upper()
    statements = build_statements(database)

    deployer = Deployer(
        log_folder=str(Path(__file__).resolve().parent.parent / "logs"),
        dry_run=args.dry_run,
    )
    return deployer.deploy_statements(statements)


if __name__ == "__main__":
    raise SystemExit(main())
