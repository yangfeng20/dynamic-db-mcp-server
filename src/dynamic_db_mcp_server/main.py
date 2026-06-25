"""FastMCP server entry point for dynamic-db-mcp-server.

Exposes 6 tools:
- register_instance: register a database connection at runtime
- list_instances: list all registered instances
- execute_sql: execute SQL with safety validation
- list_databases: show databases on an instance
- list_tables: list tables in a database
- get_table_detail: get column info and DDL
"""

import json
import traceback

import pymysql
from mcp.server.fastmcp import FastMCP

from .connection import ConnectionManager
from .executor import DbExecutor
from .validator import SqlCategory, validate_sql

mcp = FastMCP("dynamic-db-mcp-server")

_manager = ConnectionManager()
_executor = DbExecutor(_manager)


@mcp.tool()
def register_instance(
    name: str,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str | None = None,
    charset: str = "utf8mb4",
) -> str:
    """Register a MySQL-compatible database connection at runtime.

    Tests the connection with SELECT 1 before caching. If a connection with
    the same name already exists, it is closed and replaced.

    Args:
        name: A human-readable identifier for this instance (used as instance_id).
        host: Database host or IP address.
        port: Database port (e.g. 3306).
        user: Database username.
        password: Database password.
        database: Optional default database/schema.
        charset: Connection charset, defaults to utf8mb4.

    Returns:
        JSON string with instance_id and status, or error details.
    """
    try:
        info = _manager.register(
            name=name,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset=charset,
        )
        return json.dumps(
            {
                "instance_id": info.instance_id,
                "host": info.host,
                "port": info.port,
                "user": info.user,
                "database": info.database or "(default)",
                "status": "connected",
            }
        )
    except pymysql.Error as e:
        return json.dumps({"error": f"Connection failed: {e}", "code": e.args[0]})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


@mcp.tool()
def list_instances() -> str:
    """List all registered database instances.

    Returns:
        JSON array of instances. Passwords are never included.
    """
    instances = _manager.list_instances()
    return json.dumps(instances)


@mcp.tool()
def execute_sql(
    instance_id: str,
    sql: str,
    database: str | None = None,
    confirm_destructive: bool = False,
) -> str:
    """Execute a SQL statement on a registered instance.

    SQL is classified before execution:
    - Read-only (SELECT/SHOW/WITH/EXPLAIN/DESC): executes directly.
    - Destructive (DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE/CREATE/...):
      requires confirm_destructive=true.
    - Blocked (OUTFILE/DUMPFILE/LOAD_FILE/SHUTDOWN/KILL): always rejected.

    Args:
        instance_id: The instance name from register_instance.
        sql: The SQL statement to execute.
        database: Optional database to switch to before executing.
        confirm_destructive: Set to true to allow destructive operations.

    Returns:
        JSON string with query results (columns/rows/row_count) or
        affected_rows for DML, or error/safety rejection details.
    """
    category, message = validate_sql(sql, confirm_destructive)

    if category is None:
        return json.dumps({"error": "SQL rejected", "detail": message})

    if category == SqlCategory.BLOCKED:
        return json.dumps(
            {
                "error": "SQL blocked",
                "sql_type": "BLOCKED",
                "detail": message,
            }
        )

    if category == SqlCategory.DESTRUCTIVE and not confirm_destructive:
        keyword = message.split("(")[1].split(")")[0] if "(" in message else "UNKNOWN"
        return json.dumps(
            {
                "error": "Destructive operation requires confirmation",
                "sql_type": "DESTRUCTIVE",
                "statement": keyword,
                "detail": message,
            }
        )

    try:
        result = _executor.execute_sql(
            instance_id=instance_id,
            sql=sql,
            database=database,
            confirm_destructive=confirm_destructive,
        )
        return json.dumps(result, default=str, ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except pymysql.Error as e:
        return json.dumps(
            {
                "error": f"SQL execution failed: {e}",
                "code": e.args[0],
                "message": e.args[1] if len(e.args) > 1 else str(e),
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "error": f"Unexpected error: {e}",
                "traceback": traceback.format_exc(),
            }
        )


@mcp.tool()
def list_databases(instance_id: str) -> str:
    """List all databases on a registered instance.

    Args:
        instance_id: The instance name from register_instance.

    Returns:
        JSON array of database names, or error details.
    """
    try:
        dbs = _executor.list_databases(instance_id)
        return json.dumps(dbs)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except pymysql.Error as e:
        return json.dumps({"error": f"Database error: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


@mcp.tool()
def list_tables(instance_id: str, database: str) -> str:
    """List tables in a database with row count and size.

    Args:
        instance_id: The instance name from register_instance.
        database: The database name to list tables from.

    Returns:
        JSON array of {table, rows, size_mb, engine, comment}, or error.
    """
    try:
        tables = _executor.list_tables(instance_id, database)
        return json.dumps(tables, default=str, ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except pymysql.Error as e:
        return json.dumps({"error": f"Database error: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


@mcp.tool()
def get_table_detail(
    instance_id: str,
    database: str,
    table_name: str,
) -> str:
    """Get column info and CREATE TABLE DDL for a specific table.

    Args:
        instance_id: The instance name from register_instance.
        database: The database name.
        table_name: The table name.

    Returns:
        JSON with {columns: [...], ddl: "..."}, or error details.
    """
    try:
        detail = _executor.get_table_detail(instance_id, database, table_name)
        return json.dumps(detail, default=str, ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except pymysql.Error as e:
        return json.dumps({"error": f"Database error: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
