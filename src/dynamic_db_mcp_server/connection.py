"""Connection manager for dynamic-db-mcp-server.

Stores pymysql connections in memory keyed by instance name.
Each instance has its own threading.Lock for concurrent safety.
"""

import threading
from dataclasses import dataclass, field

import pymysql


@dataclass
class InstanceInfo:
    """Metadata for a registered database instance."""

    instance_id: str
    host: str
    port: int
    user: str
    password: str
    database: str | None = None
    charset: str = "utf8mb4"
    connection: pymysql.Connection | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class ConnectionManager:
    """In-memory cache of database connections.

    Connections are keyed by instance_id (the name provided at registration).
    Re-registering an existing name overwrites the old connection.
    """

    def __init__(self) -> None:
        self._instances: dict[str, InstanceInfo] = {}
        self._global_lock = threading.Lock()

    def register(
        self,
        name: str,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str | None = None,
        charset: str = "utf8mb4",
    ) -> InstanceInfo:
        """Register a new instance or overwrite an existing one.

        Tests the connection with SELECT 1 before caching.
        Raises pymysql.Error if connection fails.
        """
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset=charset,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        info = InstanceInfo(
            instance_id=name,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset=charset,
            connection=conn,
        )

        with self._global_lock:
            old = self._instances.get(name)
            if old and old.connection:
                try:
                    old.connection.close()
                except Exception:
                    pass
            self._instances[name] = info

        return info

    def get(self, instance_id: str) -> InstanceInfo | None:
        """Get an instance by ID. Returns None if not found."""
        with self._global_lock:
            return self._instances.get(instance_id)

    def get_connection(self, instance_id: str) -> pymysql.Connection:
        """Get a live pymysql connection for the given instance.

        Pings the connection and reconnects if needed.
        Raises ValueError if instance is not registered.
        """
        info = self.get(instance_id)
        if not info:
            raise ValueError(f"Instance '{instance_id}' not registered. Call register_instance first.")
        assert info.connection is not None
        info.connection.ping(reconnect=True)
        return info.connection

    def list_instances(self) -> list[dict]:
        """List all registered instances (without passwords)."""
        with self._global_lock:
            result = []
            for info in self._instances.values():
                status = "connected"
                try:
                    if info.connection:
                        info.connection.ping(reconnect=True)
                except Exception:
                    status = "disconnected"
                result.append(
                    {
                        "instance_id": info.instance_id,
                        "host": info.host,
                        "port": info.port,
                        "user": info.user,
                        "database": info.database or "(default)",
                        "charset": info.charset,
                        "status": status,
                    }
                )
            return result

    def remove(self, instance_id: str) -> bool:
        """Remove and close a registered instance. Returns True if found."""
        with self._global_lock:
            info = self._instances.pop(instance_id, None)
            if not info:
                return False
            if info.connection:
                try:
                    info.connection.close()
                except Exception:
                    pass
            return True
