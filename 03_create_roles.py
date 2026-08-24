# Create domain and subdomain roles with tiered permissions (equivalent to Denodo role scripts)
# Co-authored with CoCo
"""
Usage:
    python 03_create_roles.py <domain> <database> [--mode domain|subdomain] [--dry-run]

Example:
    python 03_create_roles.py resort RESORT_DB --mode domain --dry-run
    python 03_create_roles.py resort RESORT_DB --mode subdomain
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.deployer import Deployer
from engine.validator import require_identifier


DOMAIN_ROLES = {
    "owner": {"suffix": "DO", "grants": ["CREATE SCHEMA", "CREATE VIEW", "CREATE TABLE", "USAGE"]},
    "data_engineer": {"suffix": "DE", "grants": ["CREATE VIEW", "CREATE TABLE", "USAGE"]},
    "data_steward": {"suffix": "DS", "grants": ["USAGE", "SELECT"]},
    "business_analyst": {"suffix": "BA", "grants": ["USAGE", "SELECT"]},
}

SUBDOMAIN_ROLES = {
    "data_engineer": {"suffix": "DE", "grants": ["CREATE VIEW", "CREATE TABLE", "USAGE"]},
    "data_analyst": {"suffix": "DA", "grants": ["CREATE VIEW", "USAGE"]},
    "consumer": {"suffix": "CONSUMER", "grants": ["USAGE", "SELECT"]},
}

DATA_PRODUCTS = ["data_products_1", "data_products_2", "data_products_3"]


def build_domain_statements(domain: str, database: str) -> list[tuple[str, str]]:
    statements = []
    for role_key, role_config in DOMAIN_ROLES.items():
        role_name = f"{domain.upper()}_{role_config['suffix']}"

        statements.append((
            f"Create role {role_name}",
            f"CREATE ROLE IF NOT EXISTS {role_name}",
        ))

        for grant in role_config["grants"]:
            if grant in ("CREATE SCHEMA", "CREATE VIEW", "CREATE TABLE"):
                statements.append((
                    f"Grant {grant} on {database} to {role_name}",
                    f"GRANT {grant} ON DATABASE {database} TO ROLE {role_name}",
                ))
            elif grant == "USAGE":
                statements.append((
                    f"Grant USAGE on all schemas in {database} to {role_name}",
                    f"GRANT USAGE ON ALL SCHEMAS IN DATABASE {database} TO ROLE {role_name}",
                ))
            elif grant == "SELECT":
                statements.append((
                    f"Grant SELECT on future views in {database} to {role_name}",
                    f"GRANT SELECT ON FUTURE VIEWS IN DATABASE {database} TO ROLE {role_name}",
                ))
                statements.append((
                    f"Grant SELECT on all views in {database} to {role_name}",
                    f"GRANT SELECT ON ALL VIEWS IN DATABASE {database} TO ROLE {role_name}",
                ))

        statements.append((
            f"Grant warehouse usage to {role_name}",
            f"GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE {role_name}",
        ))

    return statements


def build_subdomain_statements(domain: str, database: str) -> list[tuple[str, str]]:
    statements = []

    for role_key, role_config in SUBDOMAIN_ROLES.items():
        if role_key == "consumer":
            for dp in DATA_PRODUCTS:
                role_name = f"{domain.upper()}_{dp.upper()}_{role_config['suffix']}"
                schema_name = dp.upper()

                statements.append((
                    f"Create consumer role {role_name}",
                    f"CREATE ROLE IF NOT EXISTS {role_name}",
                ))
                statements.append((
                    f"Grant USAGE on {database}.{schema_name} to {role_name}",
                    f"GRANT USAGE ON SCHEMA {database}.{schema_name} TO ROLE {role_name}",
                ))
                statements.append((
                    f"Grant SELECT on views in {database}.{schema_name} to {role_name}",
                    f"GRANT SELECT ON ALL VIEWS IN SCHEMA {database}.{schema_name} TO ROLE {role_name}",
                ))
                statements.append((
                    f"Grant SELECT on future views in {database}.{schema_name} to {role_name}",
                    f"GRANT SELECT ON FUTURE VIEWS IN SCHEMA {database}.{schema_name} TO ROLE {role_name}",
                ))
                statements.append((
                    f"Grant warehouse usage to {role_name}",
                    f"GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE {role_name}",
                ))
        else:
            role_name = f"{domain.upper()}_{role_config['suffix']}"
            statements.append((
                f"Create role {role_name}",
                f"CREATE ROLE IF NOT EXISTS {role_name}",
            ))
            for grant in role_config["grants"]:
                if grant in ("CREATE VIEW", "CREATE TABLE"):
                    statements.append((
                        f"Grant {grant} on {database} to {role_name}",
                        f"GRANT {grant} ON DATABASE {database} TO ROLE {role_name}",
                    ))
                elif grant == "USAGE":
                    statements.append((
                        f"Grant USAGE on all schemas to {role_name}",
                        f"GRANT USAGE ON ALL SCHEMAS IN DATABASE {database} TO ROLE {role_name}",
                    ))
            statements.append((
                f"Grant warehouse usage to {role_name}",
                f"GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE {role_name}",
            ))

    return statements


def main() -> int:
    parser = argparse.ArgumentParser(description="Create domain/subdomain roles with tiered access.")
    parser.add_argument("domain", help="Domain name (e.g., resort, finance)")
    parser.add_argument("database", help="Target database")
    parser.add_argument("--mode", choices=["domain", "subdomain"], default="domain")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    domain = require_identifier(args.domain.strip().lower(), "domain")
    database = args.database.strip().upper()

    if args.mode == "domain":
        statements = build_domain_statements(domain, database)
    else:
        statements = build_subdomain_statements(domain, database)

    deployer = Deployer(
        log_folder=str(Path(__file__).resolve().parent.parent / "logs"),
        dry_run=args.dry_run,
    )
    return deployer.deploy_statements(statements)


if __name__ == "__main__":
    raise SystemExit(main())
