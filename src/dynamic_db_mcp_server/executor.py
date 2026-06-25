"""SQL executor for dynamic-db-mcp-server.

Wraps pymysql cursor operations with structured result formatting.
"""

from typing import Any

import pymysql

from .connection import ConnectionManager


class DbExecutor:
    """Execute SQL and metadata queries against registered instances."""

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager

    def execute_sql(
        self,
        instance_id: str,
        sql: str,
        database: str | None = None,
        confirm_destructive: bool = False,
    ) -> dict[str, Any]:
        """Execute a SQL statement and return structured results.

        For SELECT/SHOW: returns columns + rows + row_count.
        For INSERT/UPDATE/DELETE: returns affected_rows.
        """
        conn = self._manager.get_connection(instance_id)
        info = self._manager.get(instance_id)
        assert info is not None

        lock = info.lock
        with lock:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            try:
                if database:
                    cursor.execute(f"USE `{database}`")

                affected = cursor.execute(sql)

                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    return {
                        "columns": columns,
                        "rows": [list(row.values()) for row in rows],
                        "row_count": len(rows),
                    }
                conn.commit()
                return {"affected_rows": affected}
            except pymysql.Error:
                conn.rollback()
                raise
            finally:
                cursor.close()

    def list_databases(self, instance_id: str) -> list[str]:
        """Return SHOW DATABASES result as a list of names."""
        conn = self._manager.get_connection(instance_id)
        info = self._manager.get(instance_id)
        assert info is not None
        lock = info.lock
        with lock:
            cursor = conn.cursor()
            try:
                cursor.execute("SHOW DATABASES")
                return [row[0] for row in cursor.fetchall()]
            finally:
                cursor.close()

    def list_tables(self, instance_id: str, database: str) -> list[dict[str, Any]]:
        """List tables in a database with row count and size."""
        conn = self._manager.get_connection(instance_id)
        info = self._manager.get(instance_id)
        assert info is not None
        lock = info.lock
        with lock:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            try:
                cursor.execute(
                    """
                    SELECT
                        TABLE_NAME as `table`,
                        TABLE_ROWS as `rows`,
                        ROUND(DATA_LENGTH / 1024 / 1024, 2) as `size_mb`,
                        ENGINE as `engine`,
                        TABLE_COMMENT as `comment`
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s
                    ORDER BY TABLE_NAME
                    """,
                    (database,),
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                cursor.close()

    def get_table_detail(
        self,
        instance_id: str,
        database: str,
        table_name: str,
    ) -> dict[str, Any]:
        """Get column info and SHOW CREATE TABLE DDL."""
        conn = self._manager.get_connection(instance_id)
        info = self._manager.get(instance_id)
        assert info is not None
        lock = info.lock
        with lock:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            try:
                cursor.execute(
                    """
                    SELECT
                        COLUMN_NAME as `field`,
                        COLUMN_TYPE as `type`,
                        IS_NULLABLE as `nullable`,
                        COLUMN_KEY as `key`,
                        COLUMN_DEFAULT as `default`,
                        EXTRA as `extra`,
                        COLUMN_COMMENT as `comment`
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (database, table_name),
                )
                columns = [dict(row) for row in cursor.fetchall()]

                cursor.execute(
                    f"SHOW CREATE TABLE `{database}`.`{table_name}`"
                )
                ddl_row = cursor.fetchone()
                ddl = ddl_row.get("Create Table", "") if ddl_row else ""

                return {"columns": columns, "ddl": ddl}
            finally:
                cursor.close()
