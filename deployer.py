import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any


class Deployer:
    """Handles SQL deployment to Snowflake with logging and dry-run support."""

    def __init__(self, log_folder: str = "logs", dry_run: bool = False):
        self.dry_run = dry_run
        self.log_folder = Path(log_folder)
        self.log_folder.mkdir(parents=True, exist_ok=True)
        self.logger, self.log_file = self._configure_logging()
        self.successes: list[str] = []
        self.failures: list[dict[str, str]] = []

    def _configure_logging(self) -> tuple[logging.Logger, Path]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_folder / f"deployment_{timestamp}.log"

        logger = logging.getLogger(f"snowflake_deployer_{timestamp}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()

        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger, log_file

    def deploy_views(self, generated_views: list[tuple[str, list[str]]], connection=None) -> int:
        """Deploy a list of (view_name, [sql_statements]) tuples."""
        self.logger.info("=" * 60)
        self.logger.info("DEPLOYMENT STARTED")
        self.logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        self.logger.info(f"Views to deploy: {len(generated_views)}")
        self.logger.info("=" * 60)

        for position, (view_name, statements) in enumerate(generated_views, start=1):
            self.logger.info(f"[{position}/{len(generated_views)}] Deploying: {view_name}")
            for sql in statements:
                self.logger.info(f"SQL:\n{sql}")

            if self.dry_run:
                self.successes.append(view_name)
                self.logger.info(f"DRY RUN SUCCESS | {view_name}")
                continue

            try:
                if connection:
                    for sql in statements:
                        connection.execute(sql)
                self.successes.append(view_name)
                self.logger.info(f"VIEW CREATION SUCCESS | {view_name}")
            except Exception as error:
                self.failures.append({
                    "view_name": view_name,
                    "error": str(error),
                    "sql": statements[0],
                })
                self.logger.error(f"VIEW CREATION FAILED | {view_name} | {error}")

        self._print_summary()
        return 0 if not self.failures else 1

    def deploy_statements(self, statements: list[tuple[str, str]], connection=None) -> int:
        """Deploy a list of (description, sql) tuples (for roles, grants, etc.)."""
        self.logger.info("=" * 60)
        self.logger.info("STATEMENT EXECUTION STARTED")
        self.logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        self.logger.info(f"Statements: {len(statements)}")
        self.logger.info("=" * 60)

        for position, (description, sql) in enumerate(statements, start=1):
            self.logger.info(f"[{position}/{len(statements)}] {description}")
            self.logger.info(f"SQL: {sql}")

            if self.dry_run:
                self.successes.append(description)
                self.logger.info(f"DRY RUN SUCCESS | {description}")
                continue

            try:
                if connection:
                    connection.execute(sql)
                self.successes.append(description)
                self.logger.info(f"SUCCESS | {description}")
            except Exception as error:
                self.failures.append({
                    "description": description,
                    "error": str(error),
                    "sql": sql,
                })
                self.logger.error(f"FAILED | {description} | {error}")

        self._print_summary()
        return 0 if not self.failures else 1

    def _print_summary(self):
        self.logger.info("=" * 60)
        self.logger.info("DEPLOYMENT SUMMARY")
        self.logger.info(f"Successes: {len(self.successes)}")
        self.logger.info(f"Failures: {len(self.failures)}")
        if self.failures:
            for f in self.failures:
                name = f.get("view_name") or f.get("description", "unknown")
                self.logger.error(f"  FAILED | {name} | {f['error']}")
        self.logger.info(f"Log file: {self.log_file}")
        self.logger.info("=" * 60)

    def save_vql(self, generated_views: list[tuple[str, list[str]]], output_path: str):
        """Save all generated SQL to a file."""
        combined = "\n\n".join(
            f"-- {view_name}\n" + ";\n".join(stmts) + ";"
            for view_name, stmts in generated_views
        )
        Path(output_path).write_text(combined + "\n", encoding="utf-8")
        self.logger.info(f"Generated SQL saved to: {output_path}")
