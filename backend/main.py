from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from typing import Optional, List
import jwt, bcrypt, sqlite3, json, os, io, math, warnings, re
from pydantic import BaseModel
from excel_parser import procesar_excel
import detector

app = FastAPI(title="ProduccionApp API")

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
    return {"estado": "En línea", "mensaje": "API de ProduccionApp funcionando correctamente en Render"}

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
def get_db():
    conn = sqlite3.connect("produccion.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL, correo TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, rol TEXT DEFAULT 'operador',
        activo INTEGER DEFAULT 1, creado_en TEXT DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS archivos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL, linea TEXT, equipo TEXT,
        filas INTEGER DEFAULT 0, estado TEXT DEFAULT 'pendiente',
        subido_por INTEGER, subido_en TEXT DEFAULT CURRENT_TIMESTAMP,
        reporte_json TEXT, resumen_json TEXT)""")

    # Migraciones (bases creadas con versiones anteriores)
    cols = [r[1] for r in cur.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "username" not in cols:
        cur.execute("ALTER TABLE usuarios ADD COLUMN username TEXT")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_username "
                "ON usuarios(lower(username)) WHERE username IS NOT NULL")
    # Archivos genéricos (cualquier Excel/CSV): tipo, esquema de columnas confirmado y huella de columnas
    cols_a = [r[1] for r in cur.execute("PRAGMA table_info(archivos)").fetchall()]
    for nueva, ddl in (("tipo", "TEXT DEFAULT 'produccion'"), ("esquema_json", "TEXT"), ("huella", "TEXT")):
        if nueva not in cols_a:
            cur.execute(f"ALTER TABLE archivos ADD COLUMN {nueva} {ddl}")
    cur.execute("""CREATE TABLE IF NOT EXISTS plantillas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL, nombre TEXT NOT NULL, huella TEXT NOT NULL,
        config_json TEXT NOT NULL, creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(owner_id, huella))""")
    # Archivos compartidos con otras personas por correo (solo lectura)
    cur.execute("""CREATE TABLE IF NOT EXISTS comparticiones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        archivo_id INTEGER NOT NULL, correo TEXT NOT NULL,
        compartido_por INTEGER, creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(archivo_id, correo))""")

    # Usuarios por defecto
    usuarios_default = [
        ("Administrador",  "admin@empresa.com",      "admin123",      "admin"),
        ("Juan López",     "jlopez@empresa.com",     "supervisor123", "admin"),
        ("María Rodríguez","mrodriguez@empresa.com", "operador123",   "operador"),
        ("Carlos Méndez",  "cmendez@empresa.com",    "operador123",   "operador"),
    ]
    # En producción: SEED_DEMO_USERS=0 y define ADMIN_EMAIL + ADMIN_PASSWORD para crear tu administrador.
    if os.getenv("SEED_DEMO_USERS", "1") != "0":
        for nombre, correo, pw, rol in usuarios_default:
            ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
            cur.execute("INSERT OR IGNORE INTO usuarios (nombre,correo,password_hash,rol) VALUES (?,?,?,?)",
                        (nombre, correo, ph, rol))
    if os.getenv("ADMIN_EMAIL") and os.getenv("ADMIN_PASSWORD"):
        ph = bcrypt.hashpw(os.environ["ADMIN_PASSWORD"].encode(), bcrypt.gensalt()).decode()
        cur.execute("INSERT OR IGNORE INTO usuarios (nombre,correo,password_hash,rol) VALUES (?,?,?,?)",
                    ("Administrador", os.environ["ADMIN_EMAIL"], ph, "admin"))
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
def listar_archivos(linea: Optional[str] = None, origen: str = "todos", u=Depends(get_usuario_actual)):
    """origen: 'mios' | 'compartidos' | 'todos'."""
    conn = get_db()
    cond, params = _cond_visible(u)
    q = f"""SELECT a.id, a.nombre, a.linea, a.equipo, a.filas, a.estado, a.tipo, a.subido_por, a.subido_en,
                   COALESCE(us.username, us.nombre) AS subido_por_nombre,
                   (a.subido_por=?) AS es_mio,
                   (SELECT COUNT(*) FROM comparticiones c2 WHERE c2.archivo_id=a.id) AS num_compartidos
            FROM archivos a LEFT JOIN usuarios us ON a.subido_por=us.id
            WHERE {cond} AND a.estado<>'borrador'"""
    params = [u["id"], *params]
    if origen == "mios":
        q += " AND a.subido_por=?"; params.append(u["id"])
    elif origen == "compartidos":
        q += " AND a.subido_por<>?"; params.append(u["id"])
    if linea:
        q += " AND a.linea=?"; params.append(linea)
    q += " ORDER BY a.subido_en DESC LIMIT 50"
    rows = conn.execute(q, params).fetchall(); conn.close()
    out = []
    for r in rows:
        d = dict(r); d["es_mio"] = bool(d["es_mio"])
        if not d["es_mio"]: d["num_compartidos"] = None   # solo el dueño ve con cuántos se comparte
        out.append(d)
    return out

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

@app.post("/archivos/upload")
async def upload_archivo(
    file: UploadFile = File(...),
    linea: str = Query(default="A"),
    password_confirmacion: str = Query(default=""),
    u=Depends(get_usuario_actual)
):
    # Verificar contraseña de confirmación
    conn = get_db()
    usuario_db = conn.execute("SELECT password_hash FROM usuarios WHERE id=?", (u["id"],)).fetchone()
    conn.close()
    if not password_confirmacion:
        raise HTTPException(status_code=401, detail="Debes confirmar tu contraseña")

    if not bcrypt.checkpw(password_confirmacion.encode(), usuario_db["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Contraseña de confirmación incorrecta")

    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo está vacío")

    conn = get_db()
    cur = conn.execute("""INSERT INTO archivos (nombre,linea,filas,estado,subido_por)
                          VALUES (?,?,?,'procesando',?)""",
                       (file.filename, linea, 0, u["id"]))
    archivo_id = cur.lastrowid; conn.commit()

    try:
        print("=== Iniciando procesamiento ===")
        resultado  = procesar_excel(contenido, linea=linea)
        print("=== Parser completado ===")
        reporte    = resultado["reporte"]
        resumen    = resultado["resumen"]
        excel_out  = resultado["excel_out"]
        equipo     = reporte["Equipment"].iloc[0] if "Equipment" in reporte.columns and len(reporte) > 0 else ""

        os.makedirs("reportes", exist_ok=True)
        with open(f"reportes/{archivo_id}_reporte.xlsx", "wb") as f:
            f.write(excel_out)

        conn.execute("""UPDATE archivos
                        SET filas=?,estado='procesado',reporte_json=?,resumen_json=?,equipo=?
                        WHERE id=?""",
                     (resumen["total_registros"],
                      reporte.to_json(orient="records", date_format="iso"),
                      json.dumps(resumen), equipo, archivo_id))
        conn.commit(); conn.close()
        return {"mensaje": f"✓ '{file.filename}' procesado correctamente.",
                "archivo_id": archivo_id, "resumen": resumen}
    except Exception as e:
        import traceback
        print("=== ERROR DETALLADO ===")
        traceback.print_exc()
        print(f"=== Error mensaje: {str(e)} ===")
        conn.execute("UPDATE archivos SET estado='error' WHERE id=?", (archivo_id,))
        conn.commit(); conn.close()
        raise HTTPException(status_code=422, detail=f"Error al procesar: {str(e)}")

@app.get("/archivos/{archivo_id}/descargar")
def descargar(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    ruta = f"reportes/{archivo_id}_reporte.xlsx"
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    nombre = (a["nombre"].rsplit(".", 1)[0] if a else f"reporte_{archivo_id}") + "_analisis.xlsx"
    with open(ruta, "rb") as f: data = f.read()
    return StreamingResponse(io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

@app.get("/archivos/{archivo_id}/reporte")
def ver_reporte(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        row = _archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    if not row["reporte_json"]:
        raise HTTPException(status_code=404, detail="Reporte no disponible")
    return {"reporte": json.loads(row["reporte_json"]),
            "resumen": json.loads(row["resumen_json"]) if row["resumen_json"] else {}}

@app.delete("/archivos/{archivo_id}")
def eliminar_archivo(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        _archivo_propio(conn, archivo_id, u)
    except HTTPException:
        conn.close(); raise

    conn.execute("DELETE FROM comparticiones WHERE archivo_id=?", (archivo_id,))
    conn.execute("DELETE FROM archivos WHERE id=?", (archivo_id,))
    conn.commit()
    conn.close()

    for ruta in (f"reportes/{archivo_id}_reporte.xlsx", f"datasets/{archivo_id}.csv.gz", f"borradores/{archivo_id}.src"):
        if os.path.exists(ruta):
            os.remove(ruta)

    return {"mensaje": "Archivo eliminado correctamente", "archivo_id": archivo_id}

# ── Dashboard — datos reales de archivos procesados ───────────────────────────
def _num(x, nd=None):
    """Convierte a número JSON-seguro: NaN/inf/None -> None (JSON no admite NaN)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd) if nd is not None else x

def _limpiar_registros(registros):
    """Reemplaza NaN/inf por None en una lista de dicts (salida de DataFrame.to_dict)."""
    return [{k: (_num(v) if isinstance(v, float) else v) for k, v in r.items()} for r in registros]

def _get_todos_reportes(linea: Optional[str], u):
    """Carga y une los reportes procesados que el usuario puede ver (suyos + compartidos con él)."""
    import pandas as pd
    conn = get_db()
    cond, params = _cond_visible(u, "archivos")
    q = f"SELECT reporte_json, linea FROM archivos WHERE estado='procesado' AND reporte_json IS NOT NULL AND {cond}"
    if linea:
        q += " AND linea=?"; params.append(linea)
    rows = conn.execute(q, params).fetchall(); conn.close()
    if not rows: return pd.DataFrame()
    dfs = []
    for row in rows:
        try:
            df = pd.read_json(io.StringIO(row["reporte_json"]))
            df["linea"] = row["linea"]
            dfs.append(df)
        except Exception:
            pass
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

@app.get("/dashboard/resumen")
def resumen_dashboard(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea, u)
    if df.empty:
        return {"unidades": 0, "rechazos": 0, "eficiencia": 0,
                "tiempo_paro": 0, "horas_reales": 0, "fuente": "sin_datos"}

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    if   periodo == "dia":    df = df[df["Date"] >= hoy]
    elif periodo == "semana": df = df[df["Date"] >= hoy - timedelta(days=7)]
    else:                     df = df[df["Date"] >= hoy - timedelta(days=30)]

    if df.empty:
        # Devolver todos si no hay del periodo (datos de prueba pueden ser de otro día)
        df = _get_todos_reportes(linea, u)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    return {
        "unidades":     int(df["qty_passed"].sum()),
        "rechazos":     int(df["qty_failed"].sum()),
        "eficiencia":   _num(df["rendimiento_%"].mean(), 1) or 0 if "rendimiento_%" in df else 0,
        "tiempo_paro":  round(float(df["horas_muertas"].sum()), 2),
        "horas_reales": round(float(df["horas_reales"].sum()), 2),
        "fuente":       "real",
    }

@app.get("/dashboard/por-modelo")
def por_modelo(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea, u)
    if df.empty: return []
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    if   periodo == "dia":    mask = df["Date"] >= hoy
    elif periodo == "semana": mask = df["Date"] >= hoy - timedelta(days=7)
    else:                     mask = df["Date"] >= hoy - timedelta(days=30)
    df = df[mask] if mask.any() else df
    res = (df.groupby("ProductID", as_index=False)
             .agg(qty_passed=("qty_passed","sum"),
                  qty_failed=("qty_failed","sum"),
                  horas_reales=("horas_reales","sum"),
                  horas_muertas=("horas_muertas","sum"))
             .sort_values("qty_passed", ascending=False)
             .head(10))
    return _limpiar_registros(res.to_dict(orient="records"))

@app.get("/dashboard/por-linea")
def por_linea(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea, u)
    if df.empty: return []
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    if   periodo == "dia":    mask = df["Date"] >= hoy
    elif periodo == "semana": mask = df["Date"] >= hoy - timedelta(days=7)
    else:                     mask = df["Date"] >= hoy - timedelta(days=30)
    df = df[mask] if mask.any() else df
    res = (df.groupby("linea", as_index=False)
             .agg(qty_passed=("qty_passed","sum"),
                  qty_failed=("qty_failed","sum"),
                  horas_reales=("horas_reales","sum"),
                  horas_muertas=("horas_muertas","sum"),
                  rendimiento=("rendimiento_%","mean"))
             .sort_values("linea"))
    return _limpiar_registros(res.to_dict(orient="records"))

@app.get("/dashboard/tendencia")
def tendencia(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea, u)
    if df.empty: return []
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    if   periodo == "dia":    mask = df["Date"] >= hoy
    elif periodo == "semana": mask = df["Date"] >= hoy - timedelta(days=7)
    else:                     mask = df["Date"] >= hoy - timedelta(days=30)
    df = df[mask] if mask.any() else df
    df["fecha"] = df["Date"].dt.strftime("%Y-%m-%d")
    res = (df.groupby("fecha", as_index=False)
             .agg(qty_passed=("qty_passed","sum"),
                  qty_failed=("qty_failed","sum"),
                  horas_reales=("horas_reales","sum"))
             .sort_values("fecha"))
    return _limpiar_registros(res.to_dict(orient="records"))

@app.get("/dashboard/rendimiento-lineas")
def rendimiento_lineas(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea, u)
    if df.empty: return []
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    if   periodo == "dia":    mask = df["Date"] >= hoy
    elif periodo == "semana": mask = df["Date"] >= hoy - timedelta(days=7)
    else:                     mask = df["Date"] >= hoy - timedelta(days=30)
    df = df[mask] if mask.any() else df
    res = (df.groupby("linea", as_index=False)
             .agg(rendimiento=("rendimiento_%","mean"),
                  horas_muertas=("horas_muertas","sum"),
                  qty_passed=("qty_passed","sum")))
    return [{"linea": r["linea"],
             "rendimiento": _num(r["rendimiento"], 1),
             "horas_muertas": _num(r["horas_muertas"], 2),
             "qty_passed": int(r["qty_passed"])} for _, r in res.iterrows()]

# ── Usuarios ───────────────────────────────────────────────────────────────────
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
                                 AND subido_en < datetime('now','-1 day')""", (u["id"],)).fetchall()
        for v in viejos:
            conn.execute("DELETE FROM archivos WHERE id=?", (v["id"],))
            if os.path.exists(f"borradores/{v['id']}.src"): os.remove(f"borradores/{v['id']}.src")
        cur = conn.execute("""INSERT INTO archivos (nombre,tipo,filas,estado,subido_por)
                              VALUES (?,'generico',0,'borrador',?)""", (nombre, u["id"]))
        aid = cur.lastrowid
        try:
            res = _analisis(conn, aid, contenido, nombre, u)
        except HTTPException:
            conn.execute("DELETE FROM archivos WHERE id=?", (aid,)); conn.commit()
            raise
        os.makedirs("borradores", exist_ok=True)
        with open(f"borradores/{aid}.src", "wb") as f:
            f.write(contenido)
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
        ruta = f"borradores/{archivo_id}.src"
        if not os.path.exists(ruta):
            raise HTTPException(status_code=410, detail="El borrador expiró; vuelve a subir el archivo")
        with open(ruta, "rb") as f:
            contenido = f.read()
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
    if os.path.exists(f"borradores/{archivo_id}.src"): os.remove(f"borradores/{archivo_id}.src")
    return {"mensaje": "Borrador descartado"}

@app.post("/datasets/{archivo_id}/confirmar")
def confirmar_dataset(archivo_id: int, datos: ConfirmarIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _borrador_propio(conn, archivo_id, u)
        ruta = f"borradores/{archivo_id}.src"
        if not os.path.exists(ruta):
            raise HTTPException(status_code=410, detail="El borrador expiró; vuelve a subir el archivo")
        for c in datos.columnas:
            if c.rol not in detector.ROLES:
                raise HTTPException(status_code=422, detail=f"Rol no válido: {c.rol}")
        if not any(c.rol != "ignorar" for c in datos.columnas):
            raise HTTPException(status_code=422, detail="Deja al menos una columna sin ignorar")
        with open(ruta, "rb") as f:
            contenido = f.read()
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
        os.makedirs("datasets", exist_ok=True)
        limpio.to_csv(f"datasets/{archivo_id}.csv.gz", index=False, compression="gzip", date_format="%Y-%m-%d %H:%M:%S")
        hf = detector.huella([c["nombre"] for c in columnas])
        conn.execute("""UPDATE archivos SET estado='procesado', filas=?, esquema_json=?, huella=? WHERE id=?""",
                     (int(len(limpio)), json.dumps({"hoja": r["hoja"], "fila_encabezado": r["fila_encabezado"],
                                                    "columnas": esquema}), hf, archivo_id))
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
    finally:
        conn.close()
    try: os.remove(ruta)
    except OSError: pass
    return {"mensaje": f"'{a['nombre']}' guardado: {len(limpio):,} filas, {len(esquema)} columnas.",
            "archivo_id": archivo_id, "filas": int(len(limpio)), "plantilla_guardada": plantilla_guardada}

def _cargar_dataset(a):
    esquema = json.loads(a["esquema_json"] or "{}").get("columnas", [])
    ruta = f"datasets/{a['id']}.csv.gz"
    if a["tipo"] != "generico" or a["estado"] != "procesado" or not esquema or not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Datos no disponibles")
    import pandas as pd
    fechas = [c["nombre"] for c in esquema if c["rol"] == "fecha"]
    numeros = [c["nombre"] for c in esquema if c["rol"] == "numero"]
    dtypes = {c["nombre"]: str for c in esquema if c["rol"] not in ("fecha", "numero")}
    df = pd.read_csv(ruta, dtype=dtypes, parse_dates=fechas, keep_default_na=False, na_values=[""])
    for c in numeros:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, esquema

@app.get("/datasets/{archivo_id}/datos")
def ver_dataset(archivo_id: int, pagina: int = Query(1, ge=1), por_pagina: int = Query(50, ge=1, le=200),
                u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    df, esquema = _cargar_dataset(a)
    ini = (pagina - 1) * por_pagina
    trozo = df.iloc[ini:ini + por_pagina].copy()
    for c in esquema:
        if c["rol"] == "fecha":
            trozo[c["nombre"]] = trozo[c["nombre"]].dt.strftime("%Y-%m-%d %H:%M").str.replace(" 00:00", "", regex=False)
    trozo = trozo.astype(object).where(trozo.notna(), None)
    return _json_seguro({
        "archivo": {"id": a["id"], "nombre": a["nombre"], "es_mio": a["subido_por"] == u["id"]},
        "columnas": esquema, "total": int(len(df)), "pagina": pagina, "por_pagina": por_pagina,
        "filas": trozo.values.tolist(),
        "resumen": detector.resumen_columnas(df, [{"nombre": c["nombre"], "rol": c["rol"]} for c in esquema]),
    })

# ── Plantillas guardadas (privadas de cada usuario)
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
