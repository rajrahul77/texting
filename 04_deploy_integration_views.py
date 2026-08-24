# Deploy integration views from JSON manifest with live Snowflake execution
# Co-authored with CoCo
"""
Usage:
    python 04_deploy_integration_views.py <manifest.json> [--dry-run] [--save-sql output.sql]

Example:
    python 04_deploy_integration_views.py ../config/manifests/integration_manifest.json
    python 04_deploy_integration_views.py ../config/manifests/integration_manifest.json --dry-run
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.connection import SnowflakeConnection
from engine.deployer import Deployer
from engine.sql_generator import SQLGenerator
from engine.validator import validate_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and deploy Snowflake integration views from a JSON manifest."
    )
    parser.add_argument("manifest", type=Path, help="Path to integration manifest JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Generate SQL without deploying")
    parser.add_argument("--save-sql", type=Path, help="Save generated SQL to file")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    if not manifest_path.is_file():
        print(f"ERROR: Manifest not found: {manifest_path}")
        return 2

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    try:
        validate_manifest(manifest)
    except ValueError as e:
        print(f"ERROR: Manifest validation failed: {e}")
        return 2

    generator = SQLGenerator(
        target_database=manifest["target_database"],
        target_schema=manifest["target_schema"],
        default_source_schema=manifest["default_source_schema"],
    )

    print(f"Target: {manifest['target_database']}.{manifest['target_schema']}")
    print(f"Source: {manifest['target_database']}.{manifest['default_source_schema']}")
    print()

    # Generate SQL for all enabled views
    generated = []
    generation_failures = []

    for view in manifest["views"]:
        if not view.get("enabled", True):
            continue
        view_name = view.get("name", "unknown")
        try:
            name, statements = generator.generate_view_sql(view)
            generated.append((name, statements))
            print(f"  GENERATED | {name}")
        except Exception as e:
            generation_failures.append({"view": view_name, "error": str(e)})
            print(f"  FAILED    | {view_name} | {e}")

    if not generated:
        print("\nNo views were generated. Check manifest for errors.")
        return 2

    # Save SQL if requested
    deployer = Deployer(
        log_folder=str(Path(__file__).resolve().parent.parent / "logs"),
        dry_run=args.dry_run,
    )

    if args.save_sql:
        deployer.save_vql(generated, str(args.save_sql.resolve()))

    # Deploy: connect to Snowflake and execute
    if args.dry_run:
        result = deployer.deploy_views(generated, connection=None)
    else:
        print("\nConnecting to Snowflake...")
        conn = SnowflakeConnection.from_environment()
        conn.database = manifest["target_database"]
        conn.schema = manifest["target_schema"]
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

    if generation_failures:
        print(f"\nGeneration failures: {len(generation_failures)}")
        for f in generation_failures:
            print(f"  {f['view']}: {f['error']}")

    return result


if __name__ == "__main__":
    raise SystemExit(main())
