from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from typing import Optional, List
import jwt, bcrypt, json, os, io, warnings, re, threading
from collections import OrderedDict
from pydantic import BaseModel
import dashboard as dash
import detector
import db
import storage
from db import get_db

app = FastAPI(title="Tachyon API")

# CORS: en producción define ALLOWED_ORIGINS con la(s) URL(s) del frontend, separadas por coma
# (ej. "https://tachyon.pages.dev"). Sin definirla se permite cualquier origen (solo para desarrollo).
# La autenticación va en el header Authorization (JWT), así que no se necesitan cookies/credenciales.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"estado": "En línea", "mensaje": "API de Tachyon funcionando correctamente",
            "base_de_datos": db.motor(), "archivos": storage.modo()}

@app.on_event("shutdown")
def _al_apagar():
    db.cerrar()

@app.exception_handler(storage.ErrorAlmacenamiento)
def _error_almacenamiento(request, exc):
    print(f"=== Error de almacenamiento: {exc} ===")
    return JSONResponse(status_code=503, content={"detail": "El almacenamiento de archivos no está disponible. Intenta de nuevo en un momento."})

# En hosts con disco efímero (Render) SQLite y el disco local se pierden al reiniciar.
if os.getenv("RENDER") and (not db.ES_POSTGRES or not storage.ES_SUPABASE):
    warnings.warn("Estás en Render sin DATABASE_URL y/o SUPABASE_URL+SUPABASE_SECRET_KEY: los datos se perderán "
                  "cuando el servicio se reinicie. Configura Supabase (ver README).")

# SECRET_KEY: define la variable de entorno SECRET_KEY en producción (>= 32 caracteres).
# Si no existe se usa una clave de desarrollo y se avisa en consola.
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = "clave-solo-para-desarrollo-no-usar-en-produccion-0000"
    warnings.warn("SECRET_KEY no definida: usando clave de desarrollo. Defínela en producción.")
ALGORITHM  = "HS256"
TOKEN_HOURS = 8
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ── DB ────────────────────────────────────────────────────────────────────────
# SQLite en local; PostgreSQL (Supabase) si se define DATABASE_URL. Ver db.py.
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

# ── Auth ───────────────────────────────────────────────────────────────────────
def crear_token(data):
    p = {**data, "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(p, SECRET_KEY, algorithm=ALGORITHM)

def get_usuario_actual(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        correo  = payload.get("sub")
        if not correo: raise HTTPException(status_code=401, detail="Token inválido")
        conn = get_db()
        u = conn.execute("SELECT * FROM usuarios WHERE correo=? AND activo=1", (correo,)).fetchone()
        conn.close()
        if not u: raise HTTPException(status_code=401, detail="Usuario no encontrado")
        return dict(u)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except HTTPException: raise
    except Exception:
        raise HTTPException(status_code=401, detail="No autorizado")

def require_admin(usuario=Depends(get_usuario_actual)):
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden realizar esta acción")
    return usuario

def _usuario_publico(u):
    """Datos del usuario que ve el frontend. 'nombre' = username si ya lo eligió."""
    return {"id": u["id"], "nombre": u["username"] or u["nombre"], "username": u["username"],
            "correo": u["correo"], "rol": u["rol"], "necesita_username": not u["username"]}

@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    u = conn.execute("SELECT * FROM usuarios WHERE lower(correo)=lower(?) AND activo=1",
                     (form.username.strip(),)).fetchone()
    conn.close()
    if not u or not bcrypt.checkpw(form.password.encode(), u["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = crear_token({"sub": u["correo"], "rol": u["rol"]})
    return {"access_token": token, "token_type": "bearer", "usuario": _usuario_publico(u)}

@app.get("/auth/me")
def me(u=Depends(get_usuario_actual)):
    return _usuario_publico(u)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,20}$")

class UsernameIn(BaseModel):
    username: str

@app.post("/auth/username")
def elegir_username(datos: UsernameIn, u=Depends(get_usuario_actual)):
    """Primer ingreso: el usuario elige su nombre de usuario (solo una vez)."""
    if u["username"]:
        raise HTTPException(status_code=409, detail="Ya elegiste tu nombre de usuario")
    nombre = datos.username.strip()
    if not USERNAME_RE.match(nombre):
        raise HTTPException(status_code=422,
            detail="Usa de 3 a 20 caracteres: letras, números, punto o guion bajo")
    conn = get_db()
    try:
        existe = conn.execute("SELECT 1 FROM usuarios WHERE lower(username)=lower(?)", (nombre,)).fetchone()
        if existe:
            raise HTTPException(status_code=409, detail="Ese nombre de usuario ya está en uso")
        conn.execute("UPDATE usuarios SET username=? WHERE id=?", (nombre, u["id"]))
        conn.commit()
        nuevo = conn.execute("SELECT * FROM usuarios WHERE id=?", (u["id"],)).fetchone()
    finally:
        conn.close()
    return _usuario_publico(nuevo)

# ── Archivos ───────────────────────────────────────────────────────────────────
# ── Visibilidad: un archivo es visible para su dueño y para quienes lo compartieron por correo
def _cond_visible(u, alias="a"):
    return (f"({alias}.subido_por=? OR EXISTS (SELECT 1 FROM comparticiones c "
            f"WHERE c.archivo_id={alias}.id AND c.correo=?))", [u["id"], u["correo"].lower()])

def _archivo_con_acceso(conn, archivo_id, u):
    """Devuelve el archivo si el usuario puede verlo; si no, 404 (no revela que exista)."""
    cond, params = _cond_visible(u)
    a = conn.execute(f"SELECT a.* FROM archivos a WHERE a.id=? AND {cond}", [archivo_id, *params]).fetchone()
    if not a:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return a

def _archivo_propio(conn, archivo_id, u):
    a = conn.execute("SELECT * FROM archivos WHERE id=? AND subido_por=?", (archivo_id, u["id"])).fetchone()
    if not a:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return a

@app.get("/archivos")
def listar_archivos(origen: str = "todos", proyecto: Optional[str] = None, u=Depends(get_usuario_actual)):
    """Datasets visibles para el usuario. origen: 'mios' | 'compartidos' | 'todos'.
    proyecto: id de uno de MIS proyectos, o 'sin' para los que no están en ninguno (solo archivos propios)."""
    conn = get_db()
    cond, params = _cond_visible(u)
    q = f"""SELECT a.id, a.nombre, a.filas, a.estado, a.tipo, a.subido_por, a.subido_en, a.proyecto_id,
                   COALESCE(us.username, us.nombre) AS subido_por_nombre,
                   (a.subido_por=?) AS es_mio,
                   (SELECT COUNT(*) FROM comparticiones c2 WHERE c2.archivo_id=a.id) AS num_compartidos
            FROM archivos a LEFT JOIN usuarios us ON a.subido_por=us.id
            WHERE {cond} AND a.estado<>'borrador' AND a.tipo='generico'"""
    params = [u["id"], *params]
    if origen == "mios":
        q += " AND a.subido_por=?"; params.append(u["id"])
    elif origen == "compartidos":
        q += " AND a.subido_por<>?"; params.append(u["id"])
    if proyecto == "sin":
        q += " AND a.subido_por=? AND a.proyecto_id IS NULL"; params.append(u["id"])
    elif proyecto:
        if not proyecto.isdigit():
            raise HTTPException(status_code=422, detail="Proyecto no válido")
        q += " AND a.subido_por=? AND a.proyecto_id=?"; params += [u["id"], int(proyecto)]
    q += " ORDER BY a.subido_en DESC LIMIT 50"
    rows = conn.execute(q, params).fetchall(); conn.close()
    out = []
    for r in rows:
        d = dict(r); d["es_mio"] = bool(d["es_mio"])
        if not d["es_mio"]:
            d["num_compartidos"] = None   # solo el dueño ve con cuántos se comparte
            d["proyecto_id"] = None       # los proyectos son personales de cada quien
        out.append(d)
    return out

# ── Proyectos (carpetas personales de archivos) ─────────────────────────────────
MAX_PROYECTOS = 50

class ProyectoIn(BaseModel):
    nombre: str

class MoverIn(BaseModel):
    proyecto_id: Optional[int] = None

def _nombre_proyecto(texto):
    n = " ".join((texto or "").split())
    if not 1 <= len(n) <= 40:
        raise HTTPException(status_code=422, detail="El nombre del proyecto debe tener entre 1 y 40 caracteres")
    return n

def _proyecto_propio(conn, proyecto_id, u):
    p = conn.execute("SELECT * FROM proyectos WHERE id=? AND owner_id=?", (proyecto_id, u["id"])).fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return p

def _nombre_libre(conn, nombre, u, excepto=None):
    for r in conn.execute("SELECT id, nombre FROM proyectos WHERE owner_id=?", (u["id"],)).fetchall():
        if r["nombre"].lower() == nombre.lower() and r["id"] != excepto:
            raise HTTPException(status_code=409, detail="Ya tienes un proyecto con ese nombre")

@app.get("/proyectos")
def listar_proyectos(u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        rows = conn.execute("""SELECT p.id, p.nombre, p.creado_en,
                   (SELECT COUNT(*) FROM archivos a WHERE a.proyecto_id=p.id AND a.subido_por=p.owner_id
                    AND a.estado='procesado' AND a.tipo='generico') AS num_archivos
                FROM proyectos p WHERE p.owner_id=? ORDER BY lower(p.nombre)""", (u["id"],)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

@app.post("/proyectos")
def crear_proyecto(datos: ProyectoIn, u=Depends(get_usuario_actual)):
    nombre = _nombre_proyecto(datos.nombre)
    conn = get_db()
    try:
        _nombre_libre(conn, nombre, u)
        if conn.execute("SELECT COUNT(*) AS n FROM proyectos WHERE owner_id=?", (u["id"],)).fetchone()["n"] >= MAX_PROYECTOS:
            raise HTTPException(status_code=422, detail=f"Máximo {MAX_PROYECTOS} proyectos")
        cur = conn.execute("INSERT INTO proyectos (owner_id, nombre) VALUES (?,?)", (u["id"], nombre))
        pid = cur.lastrowid; conn.commit()
    finally:
        conn.close()
    return {"id": pid, "nombre": nombre, "num_archivos": 0}

@app.patch("/proyectos/{proyecto_id}")
def renombrar_proyecto(proyecto_id: int, datos: ProyectoIn, u=Depends(get_usuario_actual)):
    nombre = _nombre_proyecto(datos.nombre)
    conn = get_db()
    try:
        _proyecto_propio(conn, proyecto_id, u)
        _nombre_libre(conn, nombre, u, excepto=proyecto_id)
        conn.execute("UPDATE proyectos SET nombre=? WHERE id=?", (nombre, proyecto_id)); conn.commit()
    finally:
        conn.close()
    return {"id": proyecto_id, "nombre": nombre}

@app.delete("/proyectos/{proyecto_id}")
def borrar_proyecto(proyecto_id: int, u=Depends(get_usuario_actual)):
    """Borra el proyecto, NO sus archivos: quedan sin proyecto."""
    conn = get_db()
    try:
        _proyecto_propio(conn, proyecto_id, u)
        conn.execute("UPDATE archivos SET proyecto_id=NULL WHERE proyecto_id=? AND subido_por=?", (proyecto_id, u["id"]))
        conn.execute("DELETE FROM proyectos WHERE id=?", (proyecto_id,)); conn.commit()
    finally:
        conn.close()
    return {"mensaje": "Proyecto eliminado; sus archivos siguen en Mis archivos"}

@app.put("/archivos/{archivo_id}/proyecto")
def mover_a_proyecto(archivo_id: int, datos: MoverIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        _archivo_propio(conn, archivo_id, u)
        if datos.proyecto_id is not None:
            _proyecto_propio(conn, datos.proyecto_id, u)
        conn.execute("UPDATE archivos SET proyecto_id=? WHERE id=?", (datos.proyecto_id, archivo_id)); conn.commit()
    finally:
        conn.close()
    return {"archivo_id": archivo_id, "proyecto_id": datos.proyecto_id}

# ── Compartir por correo (solo el dueño)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class CompartirIn(BaseModel):
    correo: str

@app.get("/archivos/{archivo_id}/comparticiones")
def ver_comparticiones(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        _archivo_propio(conn, archivo_id, u)
        rows = conn.execute("SELECT correo, creado_en FROM comparticiones WHERE archivo_id=? ORDER BY creado_en",
                            (archivo_id,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

@app.post("/archivos/{archivo_id}/comparticiones")
def compartir_archivo(archivo_id: int, datos: CompartirIn, u=Depends(get_usuario_actual)):
    correo = datos.correo.strip().lower()
    if not EMAIL_RE.match(correo):
        raise HTTPException(status_code=422, detail="Correo electrónico no válido")
    if correo == u["correo"].lower():
        raise HTTPException(status_code=422, detail="Ese archivo ya es tuyo")
    conn = get_db()
    try:
        _archivo_propio(conn, archivo_id, u)
        # No se revela si el correo tiene cuenta: quien se registre con él verá el archivo.
        conn.execute("INSERT OR IGNORE INTO comparticiones (archivo_id, correo, compartido_por) VALUES (?,?,?)",
                     (archivo_id, correo, u["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"mensaje": f"Compartido con {correo}", "correo": correo}

@app.delete("/archivos/{archivo_id}/comparticiones/{correo}")
def dejar_de_compartir(archivo_id: int, correo: str, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        _archivo_propio(conn, archivo_id, u)
        conn.execute("DELETE FROM comparticiones WHERE archivo_id=? AND correo=?", (archivo_id, correo.strip().lower()))
        conn.commit()
    finally:
        conn.close()
    return {"mensaje": "Se dejó de compartir"}

@app.delete("/archivos/{archivo_id}")
def eliminar_archivo(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        _archivo_propio(conn, archivo_id, u)
    except HTTPException:
        conn.close(); raise

    conn.execute("DELETE FROM comparticiones WHERE archivo_id=?", (archivo_id,))
    conn.execute("DELETE FROM dashboards WHERE archivo_id=?", (archivo_id,))
    conn.execute("DELETE FROM archivos WHERE id=?", (archivo_id,))
    conn.commit()
    conn.close()
    _olvidar_parquet(archivo_id)

    for ruta in (f"datasets/{archivo_id}.parquet", f"borradores/{archivo_id}.src"):
        storage.delete(ruta)

    return {"mensaje": "Archivo eliminado correctamente", "archivo_id": archivo_id}

# ── Usuarios ───────────────────────────────────────────────────────────────────
@app.get("/admin/diagnostico")
def diagnostico(u=Depends(require_admin)):
    """Comprueba de verdad la base de datos y el almacenamiento (ida y vuelta). Solo administradores."""
    out = {"base_de_datos": {"motor": db.motor(), "ok": False, "detalle": ""},
           "archivos": {"modo": storage.modo(), "ok": False, "detalle": ""},
           "advertencias": []}
    try:
        conn = get_db()
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"]
        finally:
            conn.close()
        out["base_de_datos"].update(ok=True, detalle=f"{n} usuario(s)")
    except Exception as e:
        out["base_de_datos"]["detalle"] = f"{type(e).__name__}: {str(e)[:160]}"
    try:
        marca = f"salud/ping_{u['id']}.txt"
        storage.put(marca, b"ok", "text/plain")
        ok = storage.get(marca) == b"ok"
        storage.delete(marca)
        out["archivos"].update(ok=ok, detalle="escritura, lectura y borrado correctos" if ok else "lectura distinta a lo escrito")
    except Exception as e:
        out["archivos"]["detalle"] = f"{type(e).__name__}: {str(e)[:160]}"
    if not db.ES_POSTGRES:
        out["advertencias"].append("Base de datos SQLite: en un host con disco efímero se pierde al reiniciar. Define DATABASE_URL.")
    if not storage.ES_SUPABASE:
        out["advertencias"].append("Archivos en disco local: se pierden al reiniciar en hosts efímeros. Define SUPABASE_URL y SUPABASE_SECRET_KEY.")
    if os.getenv("SEED_DEMO_USERS") == "1":
        out["advertencias"].append("SEED_DEMO_USERS=1: existen cuentas de demostración con contraseñas públicas.")
    return out

@app.get("/usuarios")
def listar_usuarios(u=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT id,nombre,username,correo,rol,activo,creado_en FROM usuarios ORDER BY id").fetchall()
    conn.close()
    return [{**dict(r), "pendiente_username": not r["username"]} for r in rows]

class UsuarioNuevo(BaseModel):
    correo: str
    password: str
    rol: str = "operador"

@app.post("/usuarios")
def crear_usuario(datos: UsuarioNuevo, u=Depends(require_admin)):
    """El admin crea la cuenta con correo y contraseña; el usuario elegirá su username al entrar."""
    correo = datos.correo.strip().lower()
    if not EMAIL_RE.match(correo):
        raise HTTPException(status_code=422, detail="Correo electrónico no válido")
    if len(datos.password) < 8:
        raise HTTPException(status_code=422, detail="La contraseña debe tener al menos 8 caracteres")
    if datos.rol not in ("admin", "operador"):
        raise HTTPException(status_code=422, detail="Rol no válido")
    ph = bcrypt.hashpw(datos.password.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM usuarios WHERE lower(correo)=?", (correo,)).fetchone():
            raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo")
        cur = conn.execute("INSERT INTO usuarios (nombre,correo,password_hash,rol) VALUES (?,?,?,?)",
                           (correo.split("@")[0], correo, ph, datos.rol))
        conn.commit()
        nuevo_id = cur.lastrowid
    finally:
        conn.close()
    return {"id": nuevo_id, "correo": correo, "rol": datos.rol, "pendiente_username": True}

class ActivoIn(BaseModel):
    activo: bool

@app.patch("/usuarios/{usuario_id}")
def activar_usuario(usuario_id: int, datos: ActivoIn, u=Depends(require_admin)):
    if usuario_id == u["id"] and not datos.activo:
        raise HTTPException(status_code=422, detail="No puedes desactivar tu propia cuenta")
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM usuarios WHERE id=?", (usuario_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        conn.execute("UPDATE usuarios SET activo=? WHERE id=?", (1 if datos.activo else 0, usuario_id))
        conn.commit()
    finally:
        conn.close()
    return {"id": usuario_id, "activo": datos.activo}

init_db()
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Datasets genéricos: cualquier Excel/CSV con detección de columnas y revisión manual
# Flujo: analizar (sube y propone) → [re-analizar con otra hoja/fila] → confirmar (limpia y guarda)
# ═══════════════════════════════════════════════════════════════════════════════
MAX_BYTES_DATASET = 25 * 1024 * 1024
MAX_FILAS_DATASET = 500_000
MAX_COLUMNAS_DATASET = 200

class ColumnaIn(BaseModel):
    nombre: str                       # nombre original en el archivo
    rol: str
    nombre_mostrar: Optional[str] = None

class ConfirmarIn(BaseModel):
    hoja: Optional[str] = None
    fila_encabezado: Optional[int] = None
    columnas: List[ColumnaIn]
    guardar_plantilla: bool = False
    nombre_plantilla: Optional[str] = None
    proyecto_id: Optional[int] = None     # proyecto donde guardar el archivo (opcional)

def _json_seguro(obj):
    """Convierte tipos de numpy/pandas a tipos JSON normales."""
    return json.loads(json.dumps(obj, default=lambda o: o.item() if hasattr(o, "item") else str(o)))

def _borrador_propio(conn, archivo_id, u):
    a = conn.execute("SELECT * FROM archivos WHERE id=? AND subido_por=? AND tipo='generico' AND estado='borrador'",
                     (archivo_id, u["id"])).fetchone()
    if not a:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    return a

def _plantilla_para(conn, u, nombres):
    """Plantilla propia que coincide exacto (misma huella) o, si no, la más parecida (>= 70 %)."""
    filas = conn.execute("SELECT * FROM plantillas WHERE owner_id=?", (u["id"],)).fetchall()
    hf = detector.huella(nombres)
    mejor, mejor_s = None, 0.0
    for p in filas:
        cfg = json.loads(p["config_json"])
        s = 1.0 if p["huella"] == hf else detector.similitud(nombres, [c["nombre_origen"] for c in cfg["columnas"]])
        if s > mejor_s:
            mejor, mejor_s = (p, cfg), s
    if mejor and mejor_s >= 0.7:
        return mejor[0], mejor[1], mejor_s
    return None, None, 0.0

def _analisis(conn, archivo_id, contenido, nombre, u, hoja=None, fila_encabezado=None):
    try:
        r = detector.leer_archivo(contenido, nombre, hoja=hoja, fila_encabezado=fila_encabezado)
    except detector.ArchivoNoSoportado as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo: {e}")
    df = r["df"]
    if df.shape[1] > MAX_COLUMNAS_DATASET:
        raise HTTPException(status_code=422, detail=f"El archivo tiene {df.shape[1]} columnas (máximo {MAX_COLUMNAS_DATASET}).")
    if len(df) > MAX_FILAS_DATASET:
        raise HTTPException(status_code=422, detail=f"El archivo tiene {len(df):,} filas (máximo {MAX_FILAS_DATASET:,}).")
    perfiles = detector.perfilar_columnas(df)
    pl, cfg, sim = _plantilla_para(conn, u, list(df.columns))
    if pl:
        perfiles = detector.aplicar_plantilla(perfiles, cfg["columnas"])
    for p in perfiles:
        p.setdefault("nombre_mostrar", p["nombre"])
        p["revisar"] = p["confianza"] < detector.UMBRAL_REVISAR
    muestra = df.head(8).astype(object).where(df.head(8).notna(), None)
    return _json_seguro({
        "archivo_id": archivo_id, "nombre": nombre,
        "hojas": r["hojas"], "hoja": r["hoja"], "fila_encabezado": r["fila_encabezado"],
        "sin_encabezado": r["sin_encabezado"], "filas": int(len(df)),
        "columnas": perfiles, "roles": detector.ROLES, "umbral_revisar": detector.UMBRAL_REVISAR,
        "vista_previa": {"columnas": [str(c) for c in df.columns],
                         "filas": [[None if v is None else str(v) for v in fila] for fila in muestra.values.tolist()]},
        "plantilla": {"id": pl["id"], "nombre": pl["nombre"], "similitud": round(sim, 2)} if pl else None,
    })

def _leer_borrador(archivo_id: int) -> bytes:
    try:
        return storage.get(f"borradores/{archivo_id}.src")
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="El borrador expiró; vuelve a subir el archivo")

@app.post("/datasets/analizar")
async def analizar_dataset(file: UploadFile = File(...), u=Depends(get_usuario_actual)):
    contenido = await file.read(MAX_BYTES_DATASET + 1)
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo está vacío")
    if len(contenido) > MAX_BYTES_DATASET:
        raise HTTPException(status_code=413, detail=f"El archivo supera {MAX_BYTES_DATASET // (1024*1024)} MB")
    nombre = os.path.basename(file.filename or "archivo")
    conn = get_db()
    try:
        # borradores abandonados del mismo usuario (de más de un día) se limpian
        viejos = conn.execute("""SELECT id FROM archivos WHERE subido_por=? AND estado='borrador'
                                 AND subido_en < ?""", (u["id"], db.hace_dias(1))).fetchall()
        for v in viejos:
            conn.execute("DELETE FROM archivos WHERE id=?", (v["id"],))
            storage.delete(f"borradores/{v['id']}.src")
        cur = conn.execute("""INSERT INTO archivos (nombre,tipo,filas,estado,subido_por)
                              VALUES (?,'generico',0,'borrador',?)""", (nombre, u["id"]))
        aid = cur.lastrowid
        try:
            res = _analisis(conn, aid, contenido, nombre, u)
        except HTTPException:
            conn.execute("DELETE FROM archivos WHERE id=?", (aid,)); conn.commit()
            raise
        storage.put(f"borradores/{aid}.src", contenido)
        conn.commit()
        return res
    finally:
        conn.close()

@app.get("/datasets/{archivo_id}/analisis")
def reanalizar_dataset(archivo_id: int, hoja: Optional[str] = None, fila_encabezado: Optional[int] = None,
                       u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _borrador_propio(conn, archivo_id, u)
        contenido = _leer_borrador(archivo_id)
        return _analisis(conn, archivo_id, contenido, a["nombre"], u, hoja=hoja, fila_encabezado=fila_encabezado)
    finally:
        conn.close()

@app.delete("/datasets/{archivo_id}/borrador")
def cancelar_borrador(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        _borrador_propio(conn, archivo_id, u)
        conn.execute("DELETE FROM archivos WHERE id=?", (archivo_id,)); conn.commit()
    finally:
        conn.close()
    storage.delete(f"borradores/{archivo_id}.src")
    return {"mensaje": "Borrador descartado"}

@app.post("/datasets/{archivo_id}/confirmar")
def confirmar_dataset(archivo_id: int, datos: ConfirmarIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _borrador_propio(conn, archivo_id, u)
        if datos.proyecto_id is not None:
            _proyecto_propio(conn, datos.proyecto_id, u)
        contenido = _leer_borrador(archivo_id)
        for c in datos.columnas:
            if c.rol not in detector.ROLES:
                raise HTTPException(status_code=422, detail=f"Rol no válido: {c.rol}")
        if not any(c.rol != "ignorar" for c in datos.columnas):
            raise HTTPException(status_code=422, detail="Deja al menos una columna sin ignorar")
        try:
            r = detector.leer_archivo(contenido, a["nombre"], hoja=datos.hoja, fila_encabezado=datos.fila_encabezado)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo: {e}")
        df0 = r["df"]
        columnas = [{"nombre": c.nombre, "rol": c.rol, "nombre_mostrar": (c.nombre_mostrar or "").strip() or c.nombre}
                    for c in datos.columnas if c.nombre in df0.columns]
        limpio = detector.aplicar_esquema(df0, columnas)
        if limpio.empty:
            raise HTTPException(status_code=422, detail="Después de limpiar no quedaron datos")
        # esquema final con los nombres ya únicos que quedaron en el DataFrame limpio
        activas = [c for c in columnas if c["rol"] != "ignorar"]
        esquema = [{"nombre": nombre_final, "rol": c["rol"], "origen": c["nombre"]}
                   for nombre_final, c in zip(limpio.columns, activas)]
        buf = io.BytesIO()
        # Grupos de filas de tamaño fijo: así "Ver datos" puede leer solo la página que se pide
        limpio.to_parquet(buf, engine="pyarrow", compression="zstd", index=False, row_group_size=FILAS_POR_GRUPO)
        storage.put(f"datasets/{archivo_id}.parquet", buf.getvalue(), "application/octet-stream")
        try:
            hf = detector.huella([c["nombre"] for c in columnas])
            # El resumen por columna se calcula una sola vez, aquí, y se guarda (es pequeño)
            resumen = _json_seguro(detector.resumen_columnas(
                limpio, [{"nombre": c["nombre"], "rol": c["rol"]} for c in esquema]))
            conn.execute("""UPDATE archivos SET estado='procesado', filas=?, esquema_json=?, huella=?, resumen_json=?,
                            proyecto_id=? WHERE id=?""",
                         (int(len(limpio)), json.dumps({"hoja": r["hoja"], "fila_encabezado": r["fila_encabezado"],
                                                        "columnas": esquema}), hf, json.dumps(resumen), datos.proyecto_id, archivo_id))
            plantilla_guardada = False
            if datos.guardar_plantilla:
                cfg = {"columnas": [{"nombre_origen": c["nombre"], "rol": c["rol"], "nombre_mostrar": c["nombre_mostrar"]}
                                    for c in columnas]}
                nombre_pl = (datos.nombre_plantilla or "").strip() or os.path.splitext(a["nombre"])[0]
                conn.execute("""INSERT INTO plantillas (owner_id,nombre,huella,config_json) VALUES (?,?,?,?)
                                ON CONFLICT(owner_id,huella) DO UPDATE SET nombre=excluded.nombre, config_json=excluded.config_json""",
                             (u["id"], nombre_pl[:80], hf, json.dumps(cfg)))
                plantilla_guardada = True
            conn.commit()
        except Exception:
            storage.delete(f"datasets/{archivo_id}.parquet")   # no dejar archivos huérfanos si falla la base de datos
            raise
    finally:
        conn.close()
    storage.delete(f"borradores/{archivo_id}.src")
    return {"mensaje": f"'{a['nombre']}' guardado: {len(limpio):,} filas, {len(esquema)} columnas.",
            "archivo_id": archivo_id, "filas": int(len(limpio)), "plantilla_guardada": plantilla_guardada}

FILAS_POR_GRUPO = 10_000     # filas por grupo dentro de cada Parquet de datasets

# Caché pequeña de Parquets recientes (un dataset confirmado nunca cambia): evita bajar de Storage el mismo archivo
# en cada gráfica o página. Se llama solo después de comprobar que el usuario puede ver el archivo.
_PARQUET_CACHE: "OrderedDict[int, bytes]" = OrderedDict()
_PARQUET_CACHE_LOCK = threading.Lock()
PARQUET_CACHE_MAX_BYTES = int(os.getenv("PARQUET_CACHE_MAX_MB", "40")) * 1024 * 1024

def _olvidar_parquet(archivo_id):
    with _PARQUET_CACHE_LOCK:
        _PARQUET_CACHE.pop(archivo_id, None)

def _parquet_bytes(archivo_id):
    with _PARQUET_CACHE_LOCK:
        if archivo_id in _PARQUET_CACHE:
            _PARQUET_CACHE.move_to_end(archivo_id)
            return _PARQUET_CACHE[archivo_id]
    datos = storage.get(f"datasets/{archivo_id}.parquet")
    if len(datos) <= PARQUET_CACHE_MAX_BYTES:
        with _PARQUET_CACHE_LOCK:
            _PARQUET_CACHE[archivo_id] = datos
            while sum(len(v) for v in _PARQUET_CACHE.values()) > PARQUET_CACHE_MAX_BYTES:
                _PARQUET_CACHE.popitem(last=False)
    return datos

def _esquema_dataset(a):
    """Esquema (columnas confirmadas) de un dataset procesado; 404 si no está disponible."""
    esquema = json.loads(a["esquema_json"] or "{}").get("columnas", [])
    if a["tipo"] != "generico" or a["estado"] != "procesado" or not esquema:
        raise HTTPException(status_code=404, detail="Datos no disponibles")
    return esquema

def _datos_dataset(a):
    """(esquema, bytes del Parquet comprimido) de un dataset procesado; 404 si no está disponible."""
    esquema = _esquema_dataset(a)
    try:
        return esquema, _parquet_bytes(a["id"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Datos no disponibles")

def _cargar_dataset(a):
    """DataFrame completo del dataset. Cargarlo entero cuesta memoria: úsalo solo cuando haga falta todo."""
    import pandas as pd
    esquema, datos = _datos_dataset(a)
    return pd.read_parquet(io.BytesIO(datos), engine="pyarrow"), esquema

def _pagina_parquet(datos: bytes, ini: int, n: int):
    """(total de filas, DataFrame con las filas [ini, ini+n)) leyendo solo los grupos de filas necesarios."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(io.BytesIO(datos))
    total = pf.metadata.num_rows
    grupos, saltar, acumulado = [], 0, 0
    for i in range(pf.metadata.num_row_groups):
        filas_grupo = pf.metadata.row_group(i).num_rows
        if acumulado + filas_grupo > ini and acumulado < ini + n:
            if not grupos:
                saltar = ini - acumulado
            grupos.append(i)
        acumulado += filas_grupo
        if acumulado >= ini + n:
            break
    if not grupos:
        return total, pf.schema_arrow.empty_table().to_pandas()
    return total, pf.read_row_groups(grupos).slice(saltar, n).to_pandas()

@app.get("/datasets/{archivo_id}/datos")
def ver_dataset(archivo_id: int, pagina: int = Query(1, ge=1), por_pagina: int = Query(50, ge=1, le=200),
                u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    esquema, datos = _datos_dataset(a)
    ini = (pagina - 1) * por_pagina
    total, trozo = _pagina_parquet(datos, ini, por_pagina)
    for c in esquema:
        if c["rol"] == "fecha":
            trozo[c["nombre"]] = trozo[c["nombre"]].dt.strftime("%Y-%m-%d %H:%M").str.replace(" 00:00", "", regex=False)
    trozo = trozo.astype(object).where(trozo.notna(), None)
    if a["resumen_json"]:
        resumen = json.loads(a["resumen_json"])
    else:   # datasets guardados antes de que el resumen se calculara al confirmar
        import pandas as pd
        resumen = _json_seguro(detector.resumen_columnas(
            pd.read_parquet(io.BytesIO(datos), engine="pyarrow"),
            [{"nombre": c["nombre"], "rol": c["rol"]} for c in esquema]))
    return _json_seguro({
        "archivo": {"id": a["id"], "nombre": a["nombre"], "es_mio": a["subido_por"] == u["id"]},
        "columnas": esquema, "total": int(total), "pagina": pagina, "por_pagina": por_pagina,
        "filas": trozo.values.tolist(), "resumen": resumen,
    })

# ── Plantillas guardadas (privadas de cada usuario)
# ── Dashboards (vistas por archivo) ─────────────────────────────────────────────────────────────────
# La configuración (gráficas + filtros) se valida contra el esquema real del archivo y se calcula aquí, en el
# servidor: el navegador solo recibe resultados agregados. Ven las vistas el dueño y con quien se compartió el
# archivo (solo lectura); solo el dueño las crea, edita o borra.
MAX_VISTAS = 10

class ConfigDashIn(BaseModel):
    config: dict

class VistaIn(BaseModel):
    nombre: Optional[str] = None
    config: Optional[dict] = None

def _nombre_vista(texto):
    n = " ".join((texto or "").split())
    if not 1 <= len(n) <= 40:
        raise HTTPException(status_code=422, detail="El nombre de la vista debe tener entre 1 y 40 caracteres")
    return n

def _config_limpia(config, esquema):
    try:
        return dash.limpiar_config(config, esquema)
    except dash.ConfigInvalida as e:
        raise HTTPException(status_code=422, detail=str(e))

def _vista_de(conn, a, vista_id):
    v = conn.execute("SELECT * FROM dashboards WHERE id=? AND archivo_id=?", (vista_id, a["id"])).fetchone()
    if not v:
        raise HTTPException(status_code=404, detail="Vista no encontrada")
    return v

def _lista_vistas(conn, a):
    return [{"id": r["id"], "nombre": r["nombre"]} for r in
            conn.execute("SELECT id, nombre FROM dashboards WHERE archivo_id=? ORDER BY id", (a["id"],)).fetchall()]

@app.get("/datasets/{archivo_id}/dashboard")
def ver_dashboard(archivo_id: int, vista: Optional[int] = None, u=Depends(get_usuario_actual)):
    """Vista guardada (la pedida o la primera) o, si el archivo aún no tiene ninguna, la propuesta automática."""
    conn = get_db()
    try:
        a = _archivo_con_acceso(conn, archivo_id, u)
        esquema = _esquema_dataset(a)
        vistas = _lista_vistas(conn, a)
        config, actual = None, None
        if vista is not None:
            actual = _vista_de(conn, a, vista)
        elif vistas:
            actual = _vista_de(conn, a, vistas[0]["id"])
        if actual is not None:
            try:
                config = dash.limpiar_config(json.loads(actual["config_json"]), esquema)
            except (dash.ConfigInvalida, ValueError):
                config = None                      # configuración dañada: se muestra la propuesta
        guardada = config is not None
        if config is None:
            resumen = json.loads(a["resumen_json"]) if a["resumen_json"] else []
            config = dash.limpiar_config(dash.sugerir(esquema, resumen), esquema)
        return {"archivo": {"id": a["id"], "nombre": a["nombre"], "filas": a["filas"], "es_mio": a["subido_por"] == u["id"]},
                "vistas": vistas,
                "vista": {"id": actual["id"] if guardada else None,
                          "nombre": actual["nombre"] if guardada else "Resumen sugerido", "guardada": guardada},
                "config": config,
                "columnas": [{"nombre": c["nombre"], "rol": c["rol"]} for c in esquema if c["rol"] != "ignorar"]}
    finally:
        conn.close()

@app.post("/datasets/{archivo_id}/dashboard/datos")
def datos_dashboard(archivo_id: int, datos: ConfigDashIn, u=Depends(get_usuario_actual)):
    """Calcula las gráficas de una configuración (guardada o en edición) sobre el archivo, ya filtrado y agregado."""
    import pandas as pd
    import pyarrow.parquet as pq
    conn = get_db()
    try:
        a = _archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    esquema, parquet = _datos_dataset(a)
    config = _config_limpia(datos.config, esquema)
    cols = dash.columnas_usadas(config)
    pf = pq.ParquetFile(io.BytesIO(parquet))
    if cols:
        df = pf.read(columns=cols).to_pandas()
    else:
        df = pd.DataFrame(index=range(pf.metadata.num_rows))
    out = dash.calcular(df, config, esquema)
    out["config"] = config
    return out

@app.get("/datasets/{archivo_id}/valores")
def valores_columna(archivo_id: int, columna: str, u=Depends(get_usuario_actual)):
    """Valores posibles de una columna (para armar filtros): categorías más frecuentes, o mínimo y máximo."""
    import pyarrow.parquet as pq
    conn = get_db()
    try:
        a = _archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    esquema, parquet = _datos_dataset(a)
    roles = {c["nombre"]: c["rol"] for c in esquema if c["rol"] != "ignorar"}
    if columna not in roles:
        raise HTTPException(status_code=404, detail="Columna no encontrada")
    serie = pq.ParquetFile(io.BytesIO(parquet)).read(columns=[columna]).to_pandas()[columna]
    return dash.valores_columna(serie, roles[columna])

@app.post("/datasets/{archivo_id}/dashboard")
def crear_vista(archivo_id: int, datos: VistaIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _archivo_propio(conn, archivo_id, u)
        esquema = _esquema_dataset(a)
        nombre = _nombre_vista(datos.nombre)
        vistas = _lista_vistas(conn, a)
        if len(vistas) >= MAX_VISTAS:
            raise HTTPException(status_code=422, detail=f"Máximo {MAX_VISTAS} vistas por archivo")
        if any(v["nombre"].lower() == nombre.lower() for v in vistas):
            raise HTTPException(status_code=409, detail="Ya hay una vista con ese nombre")
        if datos.config is None:
            resumen = json.loads(a["resumen_json"]) if a["resumen_json"] else []
            datos.config = dash.sugerir(esquema, resumen)
        config = _config_limpia(datos.config, esquema)
        cur = conn.execute("INSERT INTO dashboards (archivo_id, owner_id, nombre, config_json) VALUES (?,?,?,?)",
                           (archivo_id, u["id"], nombre, json.dumps(config)))
        vid = cur.lastrowid; conn.commit()
    finally:
        conn.close()
    return {"id": vid, "nombre": nombre, "config": config}

@app.put("/datasets/{archivo_id}/dashboard/{vista_id}")
def guardar_vista(archivo_id: int, vista_id: int, datos: VistaIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _archivo_propio(conn, archivo_id, u)
        esquema = _esquema_dataset(a)
        v = _vista_de(conn, a, vista_id)
        nombre, config = v["nombre"], None
        if datos.nombre is not None:
            nombre = _nombre_vista(datos.nombre)
            if any(x["nombre"].lower() == nombre.lower() and x["id"] != vista_id for x in _lista_vistas(conn, a)):
                raise HTTPException(status_code=409, detail="Ya hay una vista con ese nombre")
        if datos.config is not None:
            config = _config_limpia(datos.config, esquema)
        conn.execute("UPDATE dashboards SET nombre=?, config_json=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                     (nombre, json.dumps(config) if config is not None else v["config_json"], vista_id))
        conn.commit()
    finally:
        conn.close()
    return {"id": vista_id, "nombre": nombre, **({"config": config} if config is not None else {})}

@app.delete("/datasets/{archivo_id}/dashboard/{vista_id}")
def borrar_vista(archivo_id: int, vista_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _archivo_propio(conn, archivo_id, u)
        _vista_de(conn, a, vista_id)
        conn.execute("DELETE FROM dashboards WHERE id=?", (vista_id,)); conn.commit()
    finally:
        conn.close()
    return {"mensaje": "Vista eliminada"}

@app.get("/plantillas")
def listar_plantillas(u=Depends(get_usuario_actual)):
    conn = get_db()
    rows = conn.execute("SELECT id,nombre,config_json,creado_en FROM plantillas WHERE owner_id=? ORDER BY id DESC",
                        (u["id"],)).fetchall(); conn.close()
    return [{"id": r["id"], "nombre": r["nombre"], "creado_en": r["creado_en"],
             "columnas": [c["nombre_origen"] for c in json.loads(r["config_json"])["columnas"]]} for r in rows]

@app.delete("/plantillas/{plantilla_id}")
def borrar_plantilla(plantilla_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    cur = conn.execute("DELETE FROM plantillas WHERE id=? AND owner_id=?", (plantilla_id, u["id"]))
    conn.commit(); conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"mensaje": "Plantilla eliminada"}
