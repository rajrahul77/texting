# Generate and deploy Snowflake Semantic View YAML from a manifest (Platinum layer)
# Co-authored with CoCo
"""
Usage:
    python 06_deploy_semantic_view.py <manifest.json> [--dry-run] [--save-yaml output.yaml]

Example:
    python 06_deploy_semantic_view.py ../config/manifests/integration_manifest.json --dry-run
    python 06_deploy_semantic_view.py ../config/manifests/integration_manifest.json --name MY_ANALYTICS

Generates a Snowflake Semantic View YAML from the manifest's view definitions,
including tables, columns, relationships, and verified queries.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.validator import require_identifier


def infer_data_type(column: dict) -> str:
    """Infer semantic view data type from column definition."""
    aggregate = column.get("aggregate_function")
    transform = column.get("transform_function")
    transform_param = column.get("transform_parameter")

    if transform and transform.upper() == "CAST" and transform_param:
        return transform_param.upper()
    if aggregate:
        return "NUMBER"

    name = column.get("output_name", "").upper()
    if any(kw in name for kw in ["DATE", "TIMESTAMP", "TIME"]):
        return "DATE" if "TIMESTAMP" not in name else "TIMESTAMP_NTZ"
    if any(kw in name for kw in ["AMOUNT", "PRICE", "REVENUE", "COST", "VALUE", "TOTAL", "AVG", "SUM"]):
        return "NUMBER"
    if any(kw in name for kw in ["COUNT", "QTY", "QUANTITY", "NUM", "DAYS"]):
        return "NUMBER"
    if any(kw in name for kw in ["ID", "FLAG", "IS_"]):
        return "VARCHAR"
    return "VARCHAR"


def classify_column(column: dict) -> str:
    """Classify column as dimension, fact, or time_dimension."""
    name = column.get("output_name", "").upper()
    data_type = infer_data_type(column)

    if data_type in ("DATE", "TIMESTAMP_NTZ") or any(kw in name for kw in ["DATE", "TIMESTAMP"]):
        return "time_dimension"
    if column.get("aggregate_function") or any(kw in name for kw in [
        "AMOUNT", "PRICE", "REVENUE", "COST", "VALUE", "TOTAL", "COUNT", "AVG", "SUM", "BALANCE"
    ]):
        return "fact"
    return "dimension"


def generate_semantic_yaml(manifest: dict, view_name: str) -> str:
    """Generate Snowflake Semantic View YAML from a manifest."""
    target_db = manifest["target_database"]
    target_schema = manifest["target_schema"]

    yaml_lines = [
        f"name: {view_name}",
        f"description: Auto-generated semantic view from {target_db}.{target_schema} manifest.",
        "tables:",
    ]

    relationships = []
    views = [v for v in manifest.get("views", []) if v.get("enabled", True)]

    for view in views:
        name = view.get("name", "")
        yaml_lines.append(f"  - name: {name}")
        yaml_lines.append(f"    base_table:")
        yaml_lines.append(f"      database: {target_db}")
        yaml_lines.append(f"      schema: {target_schema}")
        yaml_lines.append(f"      table: {name}")

        columns = view.get("columns", [])
        dimensions = []
        facts = []
        time_dims = []

        for col in sorted(columns, key=lambda c: (c.get("execution_order", 0), c.get("sequence_number", 0))):
            output_name = col.get("output_name", "")
            data_type = infer_data_type(col)
            classification = classify_column(col)

            entry = {"name": output_name, "expr": output_name, "data_type": data_type}

            if classification == "time_dimension":
                time_dims.append(entry)
            elif classification == "fact":
                facts.append(entry)
            else:
                dimensions.append(entry)

        if dimensions:
            yaml_lines.append("    dimensions:")
            for d in dimensions:
                yaml_lines.append(f"      - name: {d['name']}")
                yaml_lines.append(f"        expr: {d['expr']}")
                yaml_lines.append(f"        data_type: {d['data_type']}")

        if time_dims:
            yaml_lines.append("    time_dimensions:")
            for t in time_dims:
                yaml_lines.append(f"      - name: {t['name']}")
                yaml_lines.append(f"        expr: {t['expr']}")
                yaml_lines.append(f"        data_type: {t['data_type']}")

        if facts:
            yaml_lines.append("    facts:")
            for f in facts:
                yaml_lines.append(f"      - name: {f['name']}")
                yaml_lines.append(f"        expr: {f['expr']}")
                yaml_lines.append(f"        data_type: {f['data_type']}")

        # Detect potential relationships from join conditions
        sources = view.get("sources", [])
        for source in sources:
            join_condition = source.get("join_condition")
            if join_condition and "=" in join_condition:
                parts = join_condition.split("=")
                if len(parts) == 2:
                    left_col = parts[0].strip().split(".")[-1]
                    right_col = parts[1].strip().split(".")[-1]
                    source_view_name = source.get("source_view", "")
                    if source_view_name:
                        relationships.append({
                            "name": f"{name}_TO_{source_view_name}",
                            "left_table": name,
                            "right_table": source_view_name,
                            "left_column": left_col,
                            "right_column": right_col,
                            "join_type": source.get("join_type", "inner").lower(),
                        })

    if relationships:
        yaml_lines.append("relationships:")
        for rel in relationships:
            yaml_lines.append(f"  - name: {rel['name']}")
            yaml_lines.append(f"    left_table: {rel['left_table']}")
            yaml_lines.append(f"    right_table: {rel['right_table']}")
            yaml_lines.append(f"    join_type: {rel['join_type']}")
            yaml_lines.append(f"    relationship_type: many_to_one")
            yaml_lines.append(f"    relationship_columns:")
            yaml_lines.append(f"      - left_column: {rel['left_column']}")
            yaml_lines.append(f"        right_column: {rel['right_column']}")

    return "\n".join(yaml_lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Snowflake Semantic View YAML from a manifest."
    )
    parser.add_argument("manifest", type=Path, help="Path to manifest JSON")
    parser.add_argument("--name", default=None, help="Semantic view name (default: auto-generated)")
    parser.add_argument("--save-yaml", type=Path, help="Save YAML to file")
    parser.add_argument("--dry-run", action="store_true", help="Generate without deploying")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    if not manifest_path.is_file():
        print(f"ERROR: Manifest not found: {manifest_path}")
        return 2

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    target_db = manifest.get("target_database", "")
    target_schema = manifest.get("target_schema", "")
    sv_name = args.name or f"{target_db}_{target_schema}_ANALYTICS"

    print(f"Generating Semantic View: {sv_name}")
    print(f"Target: {target_db}.{target_schema}")

    yaml_content = generate_semantic_yaml(manifest, sv_name)

    print()
    print("Generated YAML:")
    print("=" * 60)
    print(yaml_content)
    print("=" * 60)

    if args.save_yaml:
        output_path = args.save_yaml.resolve()
        output_path.write_text(yaml_content, encoding="utf-8")
        print(f"\nYAML saved to: {output_path}")

    if not args.dry_run:
        deploy_sql = (
            f"CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML('{target_db}.{target_schema}', $$\n"
            f"{yaml_content}\n"
            f"$$)"
        )
        print(f"\nDeploy SQL:\n{deploy_sql}")
        print("\nTo deploy, execute this SQL in Snowflake.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
