# dynamic-db-mcp-server

Dynamic MySQL-compatible database MCP server. Register database connections at runtime, execute SQL with built-in destructive statement interception.

## Why this exists

Traditional database MCP servers require all connection configs to be written into environment variables or config files **beforehand**. This is impractical when:

- You have dozens/hundreds of database instances
- Instance IPs change frequently
- You don't want to maintain a static config file
- You need AI to discover and connect to databases dynamically

**dynamic-db-mcp-server** flips the model: connections are registered **at runtime** via a tool call. AI provides host/port/user/password, the server tests the connection, caches it, and returns an `instance_id` for subsequent queries.

## Features

- **Dynamic registration** - No pre-configured connection lists. Register any MySQL-compatible database at runtime.
- **Connection reuse** - Registered connections are cached. No repeated handshakes.
- **SQL safety** - Read-only queries (SELECT/SHOW/WITH/EXPLAIN/DESC) execute directly. Destructive statements (DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE) require explicit confirmation. Dangerous statements (OUTFILE/DUMPFILE/LOAD_FILE/SHUTDOWN) are blocked entirely.
- **MySQL protocol compatible** - Works with MySQL, MariaDB, TDSQL, TDSQL-C, and any database speaking MySQL wire protocol.
- **No sensitive data in config** - No hardcoded credentials. All connections are runtime-provided.
- **Session-free** - Connections live in memory for the MCP process lifetime. Restart = clean slate.

## Quick start

### Install

```bash
pip install -e .
```

Or use with `uv` / `uvx` (once published):

```bash
uvx dynamic-db-mcp-server
```

### Configure in your MCP client

Add to your MCP client config (e.g., `opencode.jsonc`, `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "dynamic-db": {
      "command": "python",
      "args": ["-m", "dynamic_db_mcp_server"],
      "env": {}
    }
  }
}
```

Or using `uvx`:

```json
{
  "mcpServers": {
    "dynamic-db": {
      "command": "uvx",
      "args": ["dynamic-db-mcp-server"]
    }
  }
}
```

### Usage flow

```
1. register_instance(name="my-db", host="10.0.0.5", port=3306, user="root", password="***")
   → {"instance_id": "my-db", "status": "connected"}
   → Connection tested and cached

2. list_instances()
   → [{"instance_id": "my-db", "host": "10.0.0.5", "port": 3306, "user": "root", "status": "connected"}]

3. execute_sql(instance_id="my-db", sql="SELECT 1")
   → {"columns": ["1"], "rows": [[1]], "row_count": 1}

4. execute_sql(instance_id="my-db", sql="DROP TABLE temp_test")
   → {"error": "Destructive operation requires confirmation", "sql_type": "DESTRUCTIVE", "statement": "DROP"}

5. execute_sql(instance_id="my-db", sql="DROP TABLE temp_test", confirm_destructive=true)
   → {"affected_rows": 0}
```

## Tools

| Tool | Description |
|---|---|
| `register_instance` | Register a database connection (tests with `SELECT 1`, caches it) |
| `list_instances` | List all registered instances (password never returned) |
| `execute_sql` | Execute SQL. Read-only passes through. Destructive requires `confirm_destructive=true` |
| `list_databases` | Show databases on an instance |
| `list_tables` | List tables in a database (with row count and size) |
| `get_table_detail` | Get column info and `SHOW CREATE TABLE` DDL |

## SQL safety policy

| Category | Keywords | Behavior |
|---|---|---|
| **Read-only** | SELECT, SHOW, WITH, EXPLAIN, DESC, DESCRIBE | Execute directly |
| **Destructive** | DROP, TRUNCATE, DELETE, UPDATE, INSERT, ALTER, RENAME, GRANT, REVOKE, CREATE | Require `confirm_destructive=true` |
| **Blocked** | OUTFILE, DUMPFILE, LOAD_FILE, SHUTDOWN, KILL | Always rejected |

## Architecture

```
AI Agent
   │
   │  MCP Protocol (stdio)
   ▼
┌──────────────────────────────────────┐
│      dynamic-db-mcp-server           │
│                                      │
│  FastMCP Server ──→ 6 tools          │
│       │                              │
│  ConnectionManager                   │
│   - register / get / list            │
│   - ping + auto_reconnect            │
│   - per-instance threading.Lock      │
│       │                              │
│  SqlValidator                        │
│   - keyword classification           │
│   - read / destructive / blocked     │
│       │                              │
│  DbExecutor (pymysql)                │
│   - execute / list / schema          │
└──────────────────────────────────────┘
               │
               │  TCP 3306
               ▼
   MySQL / MariaDB / TDSQL / TDSQL-C
```

## License

MIT
