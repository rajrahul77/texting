# Deploy data product views from JSON manifest with live Snowflake execution
# Co-authored with CoCo
"""
Usage:
    python 05_deploy_data_products.py <manifest.json> [--dry-run] [--save-sql output.sql]

Example:
    python 05_deploy_data_products.py ../config/manifests/data_product_manifest.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.connection import SnowflakeConnection
from engine.deployer import Deployer
from engine.sql_generator import SQLGenerator
from engine.validator import require_identifier


def flatten_enabled_views(manifest: dict) -> list[tuple[str, dict]]:
    """Extract all enabled views across all data products."""
    flattened = []
    for product in manifest.get("data_products", []):
        product_name = require_identifier(product.get("data_product", ""), "data_product")
        views = product.get("views", [])
        for view in views:
            if view.get("enabled", True):
                flattened.append((product_name, view))
    if not flattened:
        raise ValueError("No enabled data-product views found in manifest.")
    return flattened


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and deploy Snowflake data product views from a JSON manifest."
    )
    parser.add_argument("manifest", type=Path, help="Path to data product manifest JSON")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--save-sql", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    if not manifest_path.is_file():
        print(f"ERROR: Manifest not found: {manifest_path}")
        return 2

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    target_database = require_identifier(manifest.get("target_database", ""), "target_database")
    target_schema = require_identifier(manifest.get("target_schema", ""), "target_schema")
    default_source_schema = require_identifier(
        manifest.get("default_source_schema", ""), "default_source_schema"
    )

    try:
        enabled_views = flatten_enabled_views(manifest)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 2

    generator = SQLGenerator(
        target_database=target_database,
        target_schema=target_schema,
        default_source_schema=default_source_schema,
    )

    print(f"Target: {target_database}.{target_schema}")
    print(f"Data products: {len(manifest.get('data_products', []))}")
    print(f"Enabled views: {len(enabled_views)}")
    print()

    # Generate SQL
    generated = []
    generation_failures = []

    for product_name, view in enabled_views:
        view_name = view.get("name", "unknown")
        try:
            name, statements = generator.generate_view_sql(view)
            generated.append((name, statements))
            print(f"  GENERATED | {product_name} / {name}")
        except Exception as e:
            generation_failures.append({
                "data_product": product_name,
                "view": view_name,
                "error": str(e),
            })
            print(f"  FAILED    | {product_name} / {view_name} | {e}")

    if not generated:
        print("\nNo data product views were generated.")
        return 2

    deployer = Deployer(
        log_folder=str(Path(__file__).resolve().parent.parent / "logs"),
        dry_run=args.dry_run,
    )

    if args.save_sql:
        deployer.save_vql(generated, str(args.save_sql.resolve()))

    # Deploy: connect and execute
    if args.dry_run:
        result = deployer.deploy_views(generated, connection=None)
    else:
        print("\nConnecting to Snowflake...")
        conn = SnowflakeConnection.from_environment()
        conn.database = target_database
        conn.schema = target_schema
        try:
            conn.connect()
            print("Connected successfully.")
            print()
            result = deployer.deploy_views(generated, connection=conn)
        except Exception as e:
            print(f"ERROR: Connection failed: {e}")
            return 2
        finally:
            conn.close()

    return result


if __name__ == "__main__":
    raise SystemExit(main())
