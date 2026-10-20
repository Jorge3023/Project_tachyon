"""Creación y migración de tablas, y usuarios iniciales. Se ejecuta al arrancar (idempotente)."""
import bcrypt
import os
import warnings
from core import db
from core.db import get_db

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute(db.ddl("""CREATE TABLE IF NOT EXISTS usuarios (
        id {PK},
        nombre TEXT NOT NULL, correo TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, rol TEXT DEFAULT 'operador',
        activo INTEGER DEFAULT 1, creado_en {TS})"""))
    cur.execute(db.ddl("""CREATE TABLE IF NOT EXISTS archivos (
        id {PK},
        nombre TEXT NOT NULL, linea TEXT, equipo TEXT,
        filas INTEGER DEFAULT 0, estado TEXT DEFAULT 'pendiente',
        subido_por INTEGER, subido_en {TS},
        reporte_json TEXT, resumen_json TEXT)"""))

    # Migraciones (bases creadas con versiones anteriores)
    if "username" not in db.columnas(conn, "usuarios"):
        cur.execute("ALTER TABLE usuarios ADD COLUMN username TEXT")
    # Dashboard que cada usuario ve al entrar: {"archivo_id": n, "vista_id": n|null}
    if "dashboard_principal" not in db.columnas(conn, "usuarios"):
        cur.execute("ALTER TABLE usuarios ADD COLUMN dashboard_principal TEXT")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_username "
                "ON usuarios(lower(username)) WHERE username IS NOT NULL")
    # Archivos genéricos (cualquier Excel/CSV): tipo, esquema de columnas confirmado y huella de columnas
    cols_a = db.columnas(conn, "archivos")
    for nueva, ddl in (("tipo", "TEXT DEFAULT 'produccion'"), ("esquema_json", "TEXT"), ("huella", "TEXT"),
                       ("proyecto_id", "INTEGER")):
        if nueva not in cols_a:
            cur.execute(f"ALTER TABLE archivos ADD COLUMN {nueva} {ddl}")
    cur.execute(db.ddl("""CREATE TABLE IF NOT EXISTS plantillas (
        id {PK},
        owner_id INTEGER NOT NULL, nombre TEXT NOT NULL, huella TEXT NOT NULL,
        config_json TEXT NOT NULL, creado_en {TS},
        UNIQUE(owner_id, huella))"""))
    # Proyectos: carpetas personales para agrupar archivos (cada quien ve solo los suyos)
    cur.execute(db.ddl("""CREATE TABLE IF NOT EXISTS proyectos (
        id {PK},
        owner_id INTEGER NOT NULL, nombre TEXT NOT NULL, creado_en {TS})"""))
    cur.execute("CREATE INDEX IF NOT EXISTS idx_proyectos_owner ON proyectos(owner_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_archivos_proyecto ON archivos(proyecto_id)")
    # Vistas de dashboard: configuración (gráficas + filtros) guardada por archivo; la edita solo el dueño
    cur.execute(db.ddl("""CREATE TABLE IF NOT EXISTS dashboards (
        id {PK},
        archivo_id INTEGER NOT NULL, owner_id INTEGER NOT NULL, nombre TEXT NOT NULL, config_json TEXT NOT NULL,
        creado_en {TS}, actualizado_en {TS})"""))
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dashboards_archivo ON dashboards(archivo_id)")
    # Archivos compartidos con otras personas por correo (solo lectura)
    cur.execute(db.ddl("""CREATE TABLE IF NOT EXISTS comparticiones (
        id {PK},
        archivo_id INTEGER NOT NULL, correo TEXT NOT NULL,
        compartido_por INTEGER, creado_en {TS},
        UNIQUE(archivo_id, correo))"""))
    cur.execute("CREATE INDEX IF NOT EXISTS idx_archivos_subido_por ON archivos(subido_por)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comparticiones_correo ON comparticiones(correo)")
    db.asegurar_seguridad(conn)

    # Usuarios por defecto
    usuarios_default = [
        ("Administrador",  "admin@empresa.com",      "admin123",      "admin"),
        ("Juan López",     "jlopez@empresa.com",     "supervisor123", "admin"),
        ("María Rodríguez","mrodriguez@empresa.com", "operador123",   "operador"),
        ("Carlos Méndez",  "cmendez@empresa.com",    "operador123",   "operador"),
    ]
    # Cuentas de demostración: SOLO para desarrollo local (SEED_DEMO_USERS=1). Sus contraseñas son públicas
    # (están en este repositorio), así que nunca deben existir en producción. Por defecto NO se crean.
    # Para crear tu administrador define ADMIN_EMAIL + ADMIN_PASSWORD (mínimo 8 caracteres).
    if os.getenv("SEED_DEMO_USERS", "0") == "1":
        warnings.warn("SEED_DEMO_USERS=1: se crean cuentas de demostración con contraseñas públicas. No usar en producción.")
        for nombre, correo, pw, rol in usuarios_default:
            ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
            cur.execute("INSERT OR IGNORE INTO usuarios (nombre,correo,password_hash,rol) VALUES (?,?,?,?)",
                        (nombre, correo, ph, rol))
    if os.getenv("ADMIN_EMAIL") and os.getenv("ADMIN_PASSWORD"):
        if len(os.environ["ADMIN_PASSWORD"]) < 8:
            warnings.warn("ADMIN_PASSWORD tiene menos de 8 caracteres: no se creó el administrador.")
        else:
            ph = bcrypt.hashpw(os.environ["ADMIN_PASSWORD"].encode(), bcrypt.gensalt()).decode()
            cur.execute("INSERT OR IGNORE INTO usuarios (nombre,correo,password_hash,rol) VALUES (?,?,?,?)",
                        ("Administrador", os.environ["ADMIN_EMAIL"].strip().lower(), ph, "admin"))
    if cur.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        warnings.warn("No hay ningún usuario: define ADMIN_EMAIL y ADMIN_PASSWORD para crear el administrador inicial.")
    conn.commit(); conn.close()
