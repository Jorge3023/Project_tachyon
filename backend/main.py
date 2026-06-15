from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from typing import Optional, List
import jwt, bcrypt, sqlite3, json, os, io
from excel_parser import procesar_excel

app = FastAPI(title="ProduccionApp API")
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SECRET_KEY = "produccion-app-secret-2024"
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

    # Usuarios por defecto
    usuarios_default = [
        ("Administrador",  "admin@empresa.com",      "admin123",      "admin"),
        ("Juan López",     "jlopez@empresa.com",     "supervisor123", "admin"),
        ("María Rodríguez","mrodriguez@empresa.com", "operador123",   "operador"),
        ("Carlos Méndez",  "cmendez@empresa.com",    "operador123",   "operador"),
    ]
    for nombre, correo, pw, rol in usuarios_default:
        ph = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        cur.execute("INSERT OR IGNORE INTO usuarios (nombre,correo,password_hash,rol) VALUES (?,?,?,?)",
                    (nombre, correo, ph, rol))
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

@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    u = conn.execute("SELECT * FROM usuarios WHERE correo=? AND activo=1", (form.username,)).fetchone()
    conn.close()
    if not u or not bcrypt.checkpw(form.password.encode(), u["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = crear_token({"sub": u["correo"], "rol": u["rol"], "nombre": u["nombre"]})
    return {"access_token": token, "token_type": "bearer",
            "usuario": {"id": u["id"], "nombre": u["nombre"], "correo": u["correo"], "rol": u["rol"]}}

@app.get("/auth/me")
def me(u=Depends(get_usuario_actual)):
    return {k: u[k] for k in ("id","nombre","correo","rol")}

# ── Archivos ───────────────────────────────────────────────────────────────────
@app.get("/archivos")
def listar_archivos(linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    conn = get_db()
    q = """SELECT a.*, us.nombre as subido_por_nombre
           FROM archivos a LEFT JOIN usuarios us ON a.subido_por=us.id"""
    params = []
    if linea:
        q += " WHERE a.linea=?"; params.append(linea)
    q += " ORDER BY a.subido_en DESC LIMIT 50"
    rows = conn.execute(q, params).fetchall(); conn.close()
    return [dict(r) for r in rows]

@app.post("/archivos/upload")
async def upload_archivo(
    file: UploadFile = File(...),
    linea: str = Query(default="A"),
    password_confirmacion: str = Query(default=""),
    u=Depends(get_usuario_actual)
):
    # Solo admins pueden cargar
    if u["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden cargar archivos")

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
    ruta = f"reportes/{archivo_id}_reporte.xlsx"
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    conn = get_db()
    a = conn.execute("SELECT nombre FROM archivos WHERE id=?", (archivo_id,)).fetchone()
    conn.close()
    nombre = (a["nombre"].rsplit(".", 1)[0] if a else f"reporte_{archivo_id}") + "_analisis.xlsx"
    with open(ruta, "rb") as f: data = f.read()
    return StreamingResponse(io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

@app.get("/archivos/{archivo_id}/reporte")
def ver_reporte(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    row = conn.execute("SELECT reporte_json,resumen_json FROM archivos WHERE id=?", (archivo_id,)).fetchone()
    conn.close()
    if not row or not row["reporte_json"]:
        raise HTTPException(status_code=404, detail="Reporte no disponible")
    return {"reporte": json.loads(row["reporte_json"]),
            "resumen": json.loads(row["resumen_json"]) if row["resumen_json"] else {}}

@app.delete("/archivos/{archivo_id}")
def eliminar_archivo(archivo_id: int, u=Depends(require_admin)):
    conn = get_db()
    archivo = conn.execute("SELECT id FROM archivos WHERE id=?", (archivo_id,)).fetchone()
    if not archivo:
        conn.close()
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    conn.execute("DELETE FROM archivos WHERE id=?", (archivo_id,))
    conn.commit()
    conn.close()

    ruta = f"reportes/{archivo_id}_reporte.xlsx"
    if os.path.exists(ruta):
        os.remove(ruta)

    return {"mensaje": "Archivo eliminado correctamente", "archivo_id": archivo_id}

# ── Dashboard — datos reales de archivos procesados ───────────────────────────
def _get_todos_reportes(linea: Optional[str] = None):
    """Carga y une todos los reportes procesados de la DB."""
    import pandas as pd
    conn = get_db()
    q = "SELECT reporte_json, linea FROM archivos WHERE estado='procesado' AND reporte_json IS NOT NULL"
    params = []
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
    df = _get_todos_reportes(linea)
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
        df = _get_todos_reportes(linea)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    return {
        "unidades":     int(df["qty_passed"].sum()),
        "rechazos":     int(df["qty_failed"].sum()),
        "eficiencia":   round(float(df["rendimiento_%"].mean()), 1) if "rendimiento_%" in df else 0,
        "tiempo_paro":  round(float(df["horas_muertas"].sum()), 2),
        "horas_reales": round(float(df["horas_reales"].sum()), 2),
        "fuente":       "real",
    }

@app.get("/dashboard/por-modelo")
def por_modelo(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea)
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
    return res.to_dict(orient="records")

@app.get("/dashboard/por-linea")
def por_linea(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea)
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
    return res.to_dict(orient="records")

@app.get("/dashboard/tendencia")
def tendencia(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea)
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
    return res.to_dict(orient="records")

@app.get("/dashboard/rendimiento-lineas")
def rendimiento_lineas(periodo: str = "dia", linea: Optional[str] = None, u=Depends(get_usuario_actual)):
    import pandas as pd
    df = _get_todos_reportes(linea)
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
             "rendimiento": round(r["rendimiento"], 1),
             "horas_muertas": round(r["horas_muertas"], 2),
             "qty_passed": int(r["qty_passed"])} for _, r in res.iterrows()]

# ── Usuarios ───────────────────────────────────────────────────────────────────
@app.get("/usuarios")
def listar_usuarios(u=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT id,nombre,correo,rol,activo,creado_en FROM usuarios").fetchall()
    conn.close()
    return [dict(r) for r in rows]

init_db()
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
