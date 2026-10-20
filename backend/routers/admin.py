"""Administración: diagnóstico del sistema y gestión de usuarios (solo administradores)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import bcrypt
import os
from core import db, storage
from core.validacion import EMAIL_RE
from core.db import get_db
from core.seguridad import require_admin

router = APIRouter(tags=["Administración"])

@router.get("/admin/diagnostico")
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

@router.get("/usuarios")
def listar_usuarios(u=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT id,nombre,username,correo,rol,activo,creado_en FROM usuarios ORDER BY id").fetchall()
    conn.close()
    return [{**dict(r), "pendiente_username": not r["username"]} for r in rows]

class UsuarioNuevo(BaseModel):
    correo: str
    password: str
    rol: str = "operador"

@router.post("/usuarios")
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

@router.patch("/usuarios/{usuario_id}")
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
