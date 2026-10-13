from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from typing import Optional, List
import jwt, bcrypt, sqlite3, json, os, io, math, warnings, re
from pydantic import BaseModel
from excel_parser import procesar_excel

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
    q = f"""SELECT a.id, a.nombre, a.linea, a.equipo, a.filas, a.estado, a.subido_por, a.subido_en,
                   COALESCE(us.username, us.nombre) AS subido_por_nombre,
                   (a.subido_por=?) AS es_mio,
                   (SELECT COUNT(*) FROM comparticiones c2 WHERE c2.archivo_id=a.id) AS num_compartidos
            FROM archivos a LEFT JOIN usuarios us ON a.subido_por=us.id
            WHERE {cond}"""
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

    ruta = f"reportes/{archivo_id}_reporte.xlsx"
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
