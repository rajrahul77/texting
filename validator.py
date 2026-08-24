# Input validation utilities for Snowflake identifiers and paths
# Co-authored with CoCo
import re

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPPORTED_JOIN_TYPES = {"INNER", "LEFT", "RIGHT", "FULL", "CROSS"}
SUPPORTED_AGGREGATES = {"SUM", "AVG", "COUNT", "COUNT_DISTINCT", "MIN", "MAX", "MEDIAN"}
SUPPORTED_TRANSFORMS = {"ROUND", "CAST", "COALESCE", "UPPER", "LOWER", "TRIM", "TO_DATE", "TO_TIMESTAMP"}


def require_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(
            f"Invalid {label}: {value!r}. "
            "Use letters, numbers, and underscores; do not start with a number."
        )
    return value


def require_schema_path(database: str, schema: str, label: str) -> str:
    require_identifier(database, f"{label} database")
    require_identifier(schema, f"{label} schema")
    return f"{database}.{schema}"


def validate_join_type(join_type: str, view_name: str) -> str:
    normalized = join_type.strip().upper()
    if normalized not in SUPPORTED_JOIN_TYPES:
        raise ValueError(
            f"Unsupported join_type '{join_type}' in view '{view_name}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_JOIN_TYPES))}"
        )
    return normalized


def validate_aggregate(aggregate: str, column_name: str) -> str:
    normalized = aggregate.strip().upper()
    if normalized not in SUPPORTED_AGGREGATES:
        raise ValueError(
            f"Unsupported aggregate_function '{aggregate}' for column '{column_name}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_AGGREGATES))}"
        )
    return normalized


def validate_transform(transform: str, column_name: str) -> str:
    normalized = transform.strip().upper()
    if normalized not in SUPPORTED_TRANSFORMS:
        raise ValueError(
            f"Unsupported transform_function '{transform}' for column '{column_name}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_TRANSFORMS))}"
        )
    return normalized


def validate_manifest(manifest: dict) -> None:
    if not isinstance(manifest, dict):
        raise ValueError("Manifest root must be a JSON object.")
    require_identifier(manifest.get("target_database", ""), "target_database")
    require_identifier(manifest.get("target_schema", ""), "target_schema")
    require_identifier(manifest.get("default_source_schema", ""), "default_source_schema")
    views = manifest.get("views")
    if not isinstance(views, list) or not views:
        raise ValueError("Manifest must contain a non-empty 'views' array.")
