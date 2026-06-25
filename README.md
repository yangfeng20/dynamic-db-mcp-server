# dynamic-db-mcp-server

动态注册的 MySQL 兼容数据库 MCP Server. 运行时注册数据库连接, 执行 SQL 时自带破坏性语句拦截.

## 为什么造这个轮子

传统的数据库 MCP Server 要求把所有连接配置**事先**写进环境变量或配置文件. 这在以下场景不现实:

- 有几十/上百个数据库实例
- 实例 IP 经常变动
- 不想维护一份静态配置文件
- 需要 AI 动态发现并连接数据库

**dynamic-db-mcp-server** 翻转了模型: 连接在**运行时**通过工具调用注册. AI 提供 host/port/user/password, Server 测试连接, 缓存它, 返回 `instance_id` 供后续查询使用.

## 特性

- **动态注册** — 无需预配置连接列表, 运行时注册任意 MySQL 兼容数据库
- **连接复用** — 注册的连接会被缓存, 不重复握手
- **SQL 安全** — 只读查询 (SELECT/SHOW/WITH/EXPLAIN/DESC) 直接执行; 破坏性语句 (DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE) 需显式确认; 危险语句 (OUTFILE/DUMPFILE/LOAD_FILE/SHUTDOWN) 一律拒绝
- **MySQL 协议兼容** — 适用于 MySQL, MariaDB, TDSQL, TDSQL-C 等任何使用 MySQL 线协议的数据库
- **配置无敏感数据** — 无硬编码凭据, 所有连接均为运行时提供
- **无状态** — 连接存在于 MCP 进程内存中, 重启即清空

## 快速开始

### 安装

```bash
pip install dynamic-db-mcp-server
```

或通过 `uv` / `uvx` 运行:

```bash
uvx dynamic-db-mcp-server
```

### 在 MCP 客户端中配置

在你的 MCP 客户端配置中添加 (如 `opencode.jsonc`, `claude_desktop_config.json`):

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

或从源码运行:

```json
{
  "mcpServers": {
    "dynamic-db": {
      "command": "python",
      "args": ["-m", "dynamic_db_mcp_server"]
    }
  }
}
```

### 使用流程

```
1. register_instance(name="my-db", host="10.0.0.5", port=3306, user="root", password="***")
   → {"instance_id": "my-db", "status": "connected"}
   → 连接已测试并缓存

2. list_instances()
   → [{"instance_id": "my-db", "host": "10.0.0.5", "port": 3306, "user": "root", "status": "connected"}]

3. execute_sql(instance_id="my-db", sql="SELECT 1")
   → {"columns": ["1"], "rows": [[1]], "row_count": 1}

4. execute_sql(instance_id="my-db", sql="DROP TABLE temp_test")
   → {"error": "Destructive operation requires confirmation", "sql_type": "DESTRUCTIVE", "statement": "DROP"}

5. execute_sql(instance_id="my-db", sql="DROP TABLE temp_test", confirm_destructive=true)
   → {"affected_rows": 0}
```

## 工具列表

| 工具 | 说明 |
|---|---|
| `register_instance` | 注册数据库连接 (用 `SELECT 1` 测试, 缓存) |
| `list_instances` | 列出所有已注册实例 (不返回密码) |
| `execute_sql` | 执行 SQL. 只读直接通过, 破坏性需 `confirm_destructive=true` |
| `list_databases` | 列出实例上的所有数据库 |
| `list_tables` | 列出指定库的表 (含行数和大小) |
| `get_table_detail` | 查看表结构 (列信息 + `SHOW CREATE TABLE` DDL) |

## SQL 安全策略

| 类别 | 关键字 | 行为 |
|---|---|---|
| **只读** | SELECT, SHOW, WITH, EXPLAIN, DESC, DESCRIBE | 直接执行 |
| **破坏性** | DROP, TRUNCATE, DELETE, UPDATE, INSERT, ALTER, RENAME, GRANT, REVOKE, CREATE | 需 `confirm_destructive=true` |
| **危险** | OUTFILE, DUMPFILE, LOAD_FILE, SHUTDOWN, KILL | 一律拒绝 |

## 架构

```
AI Agent
   │
   │  MCP 协议 (stdio)
   ▼
┌──────────────────────────────────────┐
│      dynamic-db-mcp-server           │
│                                      │
│  FastMCP Server ──→ 6 个工具         │
│       │                              │
│  ConnectionManager                   │
│   - register / get / list            │
│   - ping + 自动重连                   │
│   - per-instance threading.Lock      │
│       │                              │
│  SqlValidator                        │
│   - 关键字分类                        │
│   - 只读 / 破坏性 / 危险              │
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
