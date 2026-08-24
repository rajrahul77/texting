from typing import Any

from .validator import (
    require_identifier,
    validate_aggregate,
    validate_join_type,
    validate_transform,
)


class SQLGenerator:
    """Generates Snowflake SQL from structured JSON manifest definitions."""

    def __init__(self, target_database: str, target_schema: str, default_source_schema: str):
        self.target_database = require_identifier(target_database, "target_database")
        self.target_schema = require_identifier(target_schema, "target_schema")
        self.default_source_schema = require_identifier(default_source_schema, "default_source_schema")

    def build_column_expression(self, column: dict[str, Any]) -> str:
        output_name = require_identifier(column.get("output_name", ""), "output_name")
        expression_override = column.get("expression_override")
        source_column = column.get("source_column")

        if expression_override:
            expression = str(expression_override).strip()
        elif source_column:
            expression = str(source_column).strip()
        else:
            raise ValueError(f"Column '{output_name}' requires source_column or expression_override.")

        default_value = column.get("default_value")
        if default_value is not None:
            expression = f"COALESCE({expression}, {default_value})"

        aggregate = column.get("aggregate_function")
        if aggregate:
            aggregate = validate_aggregate(aggregate, output_name)
            if aggregate == "COUNT_DISTINCT":
                expression = f"COUNT(DISTINCT {expression})"
            else:
                expression = f"{aggregate}({expression})"

        transform = column.get("transform_function")
        if transform:
            transform = validate_transform(transform, output_name)
            parameter = column.get("transform_parameter")

            if transform in {"ROUND", "CAST", "COALESCE"} and parameter is None:
                raise ValueError(
                    f"Transform {transform} for '{output_name}' requires transform_parameter."
                )

            if transform == "ROUND":
                expression = f"ROUND({expression}, {parameter})"
            elif transform == "CAST":
                expression = f"CAST({expression} AS {parameter})"
            elif transform == "COALESCE":
                expression = f"COALESCE({expression}, {parameter})"
            elif transform == "TO_DATE":
                expression = f"TO_DATE({expression})" if not parameter else f"TO_DATE({expression}, '{parameter}')"
            elif transform == "TO_TIMESTAMP":
                expression = f"TO_TIMESTAMP({expression})" if not parameter else f"TO_TIMESTAMP({expression}, '{parameter}')"
            else:
                expression = f"{transform}({expression})"

        return f"{expression} AS {output_name}"

    def build_from_clause(self, sources: list[dict[str, Any]], view_name: str) -> str:
        if not sources:
            raise ValueError(f"View '{view_name}' requires at least one source.")

        ordered = sorted(
            sources,
            key=lambda s: (int(s.get("execution_order", 0)), int(s.get("sequence_number", 0))),
        )

        from_clause = ""
        for index, source in enumerate(ordered):
            source_db = source.get("source_database") or self.target_database
            source_schema = source.get("source_schema") or self.default_source_schema
            source_view = require_identifier(source.get("source_view", ""), "source_view")
            source_alias = require_identifier(source.get("source_alias", ""), "source_alias")

            qualified = f"{source_db}.{source_schema}.{source_view} {source_alias}"

            if index == 0:
                from_clause = qualified
                continue

            join_type = validate_join_type(
                source.get("join_type") or "INNER", view_name
            )

            if join_type == "CROSS":
                from_clause += f"\n  CROSS JOIN {qualified}"
                continue

            join_condition = source.get("join_condition")
            if not join_condition:
                raise ValueError(
                    f"{join_type} JOIN for '{source_view}' in view '{view_name}' requires join_condition."
                )
            from_clause += f"\n  {join_type} JOIN {qualified}\n    ON {join_condition.strip()}"

        return from_clause

    def generate_metadata_view(self, view: dict[str, Any]) -> str:
        view_name = require_identifier(view.get("name", ""), "view name")

        columns = view.get("columns")
        if not isinstance(columns, list) or not columns:
            raise ValueError(f"View '{view_name}' requires a non-empty columns array.")

        ordered_columns = sorted(
            columns,
            key=lambda c: (int(c.get("execution_order", 0)), int(c.get("sequence_number", 0))),
        )

        select_list = ",\n    ".join(
            self.build_column_expression(col) for col in ordered_columns
        )

        sources = view.get("sources")
        if not isinstance(sources, list):
            raise ValueError(f"View '{view_name}' requires a sources array.")

        from_clause = self.build_from_clause(sources, view_name)

        sql = (
            f"CREATE OR REPLACE VIEW {self.target_database}.{self.target_schema}.{view_name}\n"
            f"AS\n"
            f"SELECT\n"
            f"    {select_list}\n"
            f"FROM {from_clause}"
        )

        where_condition = view.get("where_condition")
        if where_condition:
            sql += f"\nWHERE {where_condition.strip()}"

        group_by_columns = view.get("group_by_columns")
        if group_by_columns:
            if isinstance(group_by_columns, list):
                group_text = ",\n    ".join(str(c).strip() for c in group_by_columns if str(c).strip())
            else:
                group_text = str(group_by_columns).strip()
            if group_text:
                sql += f"\nGROUP BY\n    {group_text}"

        having_condition = view.get("having_condition")
        if having_condition:
            sql += f"\nHAVING {having_condition.strip()}"

        return sql

    def generate_custom_sql_view(self, view: dict[str, Any]) -> str:
        view_name = require_identifier(view.get("name", ""), "view name")
        sql_override = view.get("sql_override")

        if not isinstance(sql_override, str) or not sql_override.strip():
            raise ValueError(f"CUSTOM_SQL view '{view_name}' requires a non-empty sql_override.")

        select_sql = sql_override.strip().rstrip(";")
        if not select_sql.upper().startswith("SELECT"):
            raise ValueError(f"sql_override for '{view_name}' must begin with SELECT.")

        return (
            f"CREATE OR REPLACE VIEW {self.target_database}.{self.target_schema}.{view_name}\n"
            f"AS\n"
            f"{select_sql}"
        )

    def generate_view_sql(self, view: dict[str, Any]) -> tuple[str, list[str]]:
        """Returns (view_name, [sql_statements]) — may include COMMENT as second statement."""
        view_name = str(view.get("name", "")).strip()
        mode = str(view.get("generation_mode", "METADATA")).strip().upper()

        if mode == "METADATA":
            sql = self.generate_metadata_view(view)
        elif mode == "CUSTOM_SQL":
            sql = self.generate_custom_sql_view(view)
        else:
            raise ValueError(f"View '{view_name}' has unsupported generation_mode '{mode}'.")

        statements = [sql]
        comment = view.get("comment")
        if comment:
            escaped_comment = comment.replace("'", "''")
            statements.append(
                f"COMMENT ON VIEW {self.target_database}.{self.target_schema}.{view_name} IS '{escaped_comment}'"
            )

        return view_name, statements

    def generate_all(self, views: list[dict[str, Any]]) -> list[tuple[str, str]]:
        results = []
        for view in views:
            if not view.get("enabled", True):
                continue
            results.append(self.generate_view_sql(view))
        if not results:
            raise ValueError("No enabled views found in manifest.")
        return results
