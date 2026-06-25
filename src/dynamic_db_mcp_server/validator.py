"""SQL safety validator for dynamic-db-mcp-server.

Classifies SQL statements into three categories:
- READ_ONLY: execute directly (SELECT, SHOW, WITH, EXPLAIN, DESC, DESCRIBE)
- DESTRUCTIVE: require explicit confirmation (DROP, DELETE, UPDATE, INSERT, ALTER, ...)
- BLOCKED: always rejected (OUTFILE, DUMPFILE, LOAD_FILE, SHUTDOWN, KILL)
"""

import re
from enum import Enum


class SqlCategory(Enum):
    """SQL statement category for safety classification."""

    READ_ONLY = "READ_ONLY"
    DESTRUCTIVE = "DESTRUCTIVE"
    BLOCKED = "BLOCKED"


READ_ONLY_KEYWORDS = frozenset(
    {
        "SELECT",
        "SHOW",
        "WITH",
        "EXPLAIN",
        "DESC",
        "DESCRIBE",
    }
)

DESTRUCTIVE_KEYWORDS = frozenset(
    {
        "DROP",
        "TRUNCATE",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "RENAME",
        "GRANT",
        "REVOKE",
        "CREATE",
    }
)

BLOCKED_PATTERNS = [
    re.compile(r"\bINTO\s+OUTFILE\b", re.IGNORECASE),
    re.compile(r"\bINTO\s+DUMPFILE\b", re.IGNORECASE),
    re.compile(r"\bLOAD_FILE\s*\(", re.IGNORECASE),
    re.compile(r"\bSHUTDOWN\b", re.IGNORECASE),
    re.compile(r"\bKILL\b", re.IGNORECASE),
]


def _extract_first_keyword(sql: str) -> str:
    """Extract the first keyword from a SQL statement.

    Strips leading comments, whitespace, and parentheses,
    then returns the first word uppercased.
    """
    cleaned = sql.strip()
    while cleaned.startswith("--") or cleaned.startswith("/*"):
        if cleaned.startswith("--"):
            newline_idx = cleaned.find("\n")
            if newline_idx == -1:
                return ""
            cleaned = cleaned[newline_idx + 1 :].strip()
        elif cleaned.startswith("/*"):
            end_idx = cleaned.find("*/")
            if end_idx == -1:
                return ""
            cleaned = cleaned[end_idx + 2 :].strip()
    cleaned = cleaned.lstrip("(").strip()
    match = re.match(r"([A-Za-z_]+)", cleaned)
    if not match:
        return ""
    return match.group(1).upper()


def validate_sql(sql: str, confirm_destructive: bool = False) -> tuple[SqlCategory | None, str]:
    """Validate a SQL statement and return its category.

    Args:
        sql: The SQL statement to validate.
        confirm_destructive: Whether the caller has confirmed destructive operations.

    Returns:
        A tuple of (category, message). If category is None, the SQL is rejected
        and message explains why. If category is READ_ONLY or DESTRUCTIVE (with
        confirm), the SQL is allowed.
    """
    if not sql or not sql.strip():
        return None, "Empty SQL statement"

    for pattern in BLOCKED_PATTERNS:
        if pattern.search(sql):
            return (
                SqlCategory.BLOCKED,
                f"Blocked pattern detected. This SQL contains a forbidden keyword: {pattern.pattern}",
            )

    keyword = _extract_first_keyword(sql)
    if not keyword:
        return None, "Unable to parse SQL statement"

    if keyword in READ_ONLY_KEYWORDS:
        return SqlCategory.READ_ONLY, "OK"

    if keyword in DESTRUCTIVE_KEYWORDS:
        if not confirm_destructive:
            return (
                SqlCategory.DESTRUCTIVE,
                f"Destructive operation detected ({keyword}). "
                "Set confirm_destructive=true to execute.",
            )
        return SqlCategory.DESTRUCTIVE, "OK (confirmed)"

    return (
        SqlCategory.DESTRUCTIVE,
        f"Unrecognized statement type ({keyword}). Treated as destructive. "
        "Set confirm_destructive=true to execute.",
    )
