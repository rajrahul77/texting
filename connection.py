# Snowflake connection wrapper with auto-detection of workspace token auth
# Co-authored with CoCo
import os
from pathlib import Path
from typing import Any


class SnowflakeConnection:
    """Manages Snowflake connections. Auto-detects workspace token for seamless auth."""

    def __init__(self, account: str = "", user: str = "", role: str = "ACCOUNTADMIN",
                 warehouse: str = "COMPUTE_WH", database: str = "", schema: str = "PUBLIC"):
        self.account = account
        self.user = user
        self.role = role
        self.warehouse = warehouse
        self.database = database
        self.schema = schema
        self._connection = None

    @classmethod
    def from_environment(cls) -> "SnowflakeConnection":
        """Auto-detect connection from Snowflake workspace environment."""
        return cls(
            account=os.environ.get("SNOWFLAKE_ACCOUNT", ""),
            user=os.environ.get("SNOWFLAKE_USER", ""),
            role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
            warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SnowflakeConnection":
        """Create connection from a config dictionary (for external use)."""
        return cls(
            account=config.get("account", ""),
            user=config.get("user", ""),
            role=config.get("role", "ACCOUNTADMIN"),
            warehouse=config.get("warehouse", "COMPUTE_WH"),
            database=config.get("database", ""),
            schema=config.get("schema", "PUBLIC"),
        )

    def _get_token(self) -> str | None:
        """Read OAuth token from Snowflake workspace session file."""
        token_path = os.environ.get("SNOWFLAKE_TOKEN_FILE_PATH", "/snowflake/session/token")
        if Path(token_path).exists():
            return Path(token_path).read_text().strip()
        return None

    def connect(self):
        """Connect to Snowflake. Uses token auth in workspace, password auth externally."""
        import snowflake.connector

        token = self._get_token()
        connect_params = {
            "warehouse": self.warehouse,
            "role": self.role,
        }
        if self.database:
            connect_params["database"] = self.database
        if self.schema:
            connect_params["schema"] = self.schema

        if token:
            connect_params["account"] = self.account or os.environ.get("SNOWFLAKE_ACCOUNT", "")
            connect_params["token"] = token
            connect_params["authenticator"] = "oauth"
            self._connection = snowflake.connector.connect(**connect_params)
        else:
            connect_params["account"] = self.account
            connect_params["user"] = self.user
            self._connection = snowflake.connector.connect(**connect_params)

        return self._connection

    def execute(self, sql: str) -> list[tuple]:
        """Execute a single SQL statement."""
        if not self._connection:
            self.connect()
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql)
            return cursor.fetchall()
        finally:
            cursor.close()

    def close(self):
        """Close the connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
