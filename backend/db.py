"""
Acceso a la base de datos con dos motores y el mismo código de la aplicación:

  - SQLite (por defecto, solo desarrollo local): archivo `produccion.db` en el directorio actual.
  - PostgreSQL (producción, p. ej. Supabase): se activa definiendo la variable DATABASE_URL.

La aplicación escribe SQL con marcadores `?` y accede a las filas por nombre o por índice;
este módulo adapta esas consultas a PostgreSQL.
"""
import os
import re
import sqlite3
import warnings

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
ES_POSTGRES = bool(DATABASE_URL)
SQLITE_PATH = os.getenv("SQLITE_PATH", "produccion.db")

# Tablas de la aplicación (se usa para activar la seguridad por filas en Postgres)
TABLAS = ("usuarios", "archivos", "comparticiones", "plantillas", "proyectos", "dashboards")


class Fila(dict):
    """Fila de resultados: se lee por nombre (fila["id"]) o por posición (fila[0]), como sqlite3.Row."""
    def __getitem__(self, clave):
        if isinstance(clave, int):
            return list(self.values())[clave]
        return super().__getitem__(clave)


class Resultado:
    """Resultado de una consulta (parecido a un cursor)."""
    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


_RE_INSERT_OR_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE)
_RE_INSERT = re.compile(r"^\s*INSERT\s+", re.IGNORECASE)


def _a_postgres(sql: str) -> str:
    """Convierte una consulta escrita para SQLite a PostgreSQL."""
    sql = sql.replace("%", "%%").replace("?", "%s")
    if _RE_INSERT_OR_IGNORE.match(sql):
        sql = _RE_INSERT_OR_IGNORE.sub("INSERT INTO", sql, count=1).rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql


class Conexion:
    """Conexión con la misma interfaz sobre SQLite o PostgreSQL."""

    def __init__(self, raw, pool=None):
        self._raw = raw
        self._pool = pool
        self._cerrada = False

    # compatibilidad con código que usa conn.cursor().execute(...)
    def cursor(self):
        return self

    def execute(self, sql, params=()):
        params = tuple(params)
        if not ES_POSTGRES:
            cur = self._raw.execute(sql, params)
            return Resultado(cur, cur.lastrowid)
        sql = _a_postgres(sql)
        lastrowid = None
        devolver_id = bool(_RE_INSERT.match(sql)) and "RETURNING" not in sql.upper()
        if devolver_id:
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        cur = self._raw.execute(sql, params)
        if devolver_id:
            fila = cur.fetchone()
            lastrowid = fila["id"] if fila else None
        return Resultado(cur, lastrowid)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self._cerrada:
            return
        self._cerrada = True
        if self._pool is not None:
            try:
                self._raw.rollback()      # no devolver conexiones con transacciones abiertas
            except Exception:
                pass
            self._pool.putconn(self._raw)
        else:
            self._raw.close()

    def __del__(self):
        # red de seguridad: si algún camino de error olvidó cerrar, no se agota el pool
        try:
            self.close()
        except Exception:
            pass


_pool = None


def _obtener_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool

        def _fila_factory(cursor):
            columnas = [c.name for c in cursor.description] if cursor.description else []
            return lambda valores: Fila(zip(columnas, valores))

        _pool = ConnectionPool(
            DATABASE_URL, open=False,
            min_size=1, max_size=int(os.getenv("DB_POOL_MAX", "5")),
            max_idle=240, timeout=30,
            check=ConnectionPool.check_connection,
            # prepare_threshold=None: compatible con el pooler en modo transacción de Supabase
            kwargs={"row_factory": _fila_factory, "prepare_threshold": None, "client_encoding": "UTF8"},
        )
        _pool.open(wait=False)
    return _pool


def get_db() -> Conexion:
    if ES_POSTGRES:
        pool = _obtener_pool()
        return Conexion(pool.getconn(), pool)
    raw = sqlite3.connect(SQLITE_PATH)
    raw.row_factory = sqlite3.Row
    return Conexion(raw)


def motor() -> str:
    return "postgres" if ES_POSTGRES else "sqlite"


def columnas(conn: Conexion, tabla: str) -> list:
    if ES_POSTGRES:
        filas = conn.execute("SELECT column_name FROM information_schema.columns "
                             "WHERE table_name=? AND table_schema=current_schema()", (tabla,)).fetchall()
        return [f["column_name"] for f in filas]
    return [f[1] for f in conn.execute(f"PRAGMA table_info({tabla})").fetchall()]


def ddl(plantilla: str) -> str:
    """Rellena {PK} y {TS} según el motor."""
    if ES_POSTGRES:
        pk = "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
        ts = "TIMESTAMP DEFAULT (now() at time zone 'utc')"
    else:
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
        ts = "TEXT DEFAULT CURRENT_TIMESTAMP"
    return plantilla.replace("{PK}", pk).replace("{TS}", ts)


def asegurar_seguridad(conn: Conexion):
    """
    Supabase expone por defecto las tablas del esquema `public` a través de su API pública.
    Esta aplicación accede solo desde su servidor (con el rol dueño de la base), así que se activa la
    seguridad por filas SIN políticas (nadie más puede leer ni escribir) y se quitan los permisos
    de los roles públicos `anon` y `authenticated`.
    """
    if not ES_POSTGRES:
        return
    for t in TABLAS:
        conn.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    lista = ", ".join(TABLAS)
    conn.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN "
        f"EXECUTE 'REVOKE ALL ON TABLE {lista} FROM anon'; END IF; "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN "
        f"EXECUTE 'REVOKE ALL ON TABLE {lista} FROM authenticated'; END IF; "
        "END $$")


def hace_dias(dias: int) -> str:
    """Marca de tiempo UTC (texto) de hace N días, comparable con las columnas de fecha."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")


def cerrar():
    """Cierra el pool de conexiones (al apagar el servidor)."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        finally:
            _pool = None
