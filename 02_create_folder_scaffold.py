# Create schema scaffold with functional areas (equivalent to Denodo folder scaffold)
# Co-authored with CoCo
"""
Usage:
    python 02_create_folder_scaffold.py <database> <schema> [--dry-run]

Example:
    python 02_create_folder_scaffold.py RESORT_DB GOLD --dry-run

This creates sub-schemas for organizing data products. In Snowflake, schemas
serve the same purpose as Denodo folders for logical organization.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.deployer import Deployer


DOMAIN_SCHEMAS = [
    "INTEGRATION",
    "DATA_PRODUCTS",
    "SEMANTIC",
    "DEPRECATED",
]

SUBDOMAIN_SCHEMAS = [
    "INTEGRATION",
    "DATA_PRODUCTS",
    "REPORT_VIEWS",
    "API_VIEWS",
    "AI_READY_VIEWS",
    "ASSOCIATIONS",
    "DEPRECATED",
]


def build_statements(database: str, mode: str) -> list[tuple[str, str]]:
    schemas = DOMAIN_SCHEMAS if mode == "domain" else SUBDOMAIN_SCHEMAS
    statements = []
    for schema in schemas:
        statements.append((
            f"Create schema {database}.{schema}",
            f"CREATE SCHEMA IF NOT EXISTS {database}.{schema}",
        ))
    return statements


def main() -> int:
    parser = argparse.ArgumentParser(description="Create schema scaffold in a Snowflake database.")
    parser.add_argument("database", help="Target database")
    parser.add_argument("--mode", choices=["domain", "subdomain"], default="domain",
                        help="Scaffold type (default: domain)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    database = args.database.strip().upper()
    statements = build_statements(database, args.mode)

    deployer = Deployer(
        log_folder=str(Path(__file__).resolve().parent.parent / "logs"),
        dry_run=args.dry_run,
    )
    return deployer.deploy_statements(statements)


if __name__ == "__main__":
    raise SystemExit(main())
