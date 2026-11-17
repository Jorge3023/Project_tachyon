"""Administración: diagnóstico del sistema y gestión de usuarios (solo administradores)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import bcrypt
import os
from core import db, storage
from core.validacion import EMAIL_RE
from core.db import get_db
from core.seguridad import require_admin
from servicios.cuentas import borrar_usuario
from routers.auth import validar_password

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
    rows = conn.execute("SELECT id,nombre,username,correo,rol,activo,creado_en,avatar_v,debe_cambiar_password FROM usuarios ORDER BY id").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["pendiente_password"] = bool(d.pop("debe_cambiar_password"))
        out.append({**d, "pendiente_username": not r["username"]})
    return out

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
    validar_password(datos.password)
    if datos.rol not in ("admin", "operador"):
        raise HTTPException(status_code=422, detail="Rol no válido")
    ph = bcrypt.hashpw(datos.password.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM usuarios WHERE lower(correo)=?", (correo,)).fetchone():
            raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo")
        # La contraseña la conoce el administrador: es temporal y el usuario la cambia en su primer ingreso
        cur = conn.execute("INSERT INTO usuarios (nombre,correo,password_hash,rol,debe_cambiar_password) VALUES (?,?,?,?,1)",
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

class PasswordTemporalIn(BaseModel):
    password: str

@router.post("/usuarios/{usuario_id}/password")
def restablecer_password(usuario_id: int, datos: PasswordTemporalIn, u=Depends(require_admin)):
    """Para quien olvidó su contraseña: el admin pone una temporal, se cierran las sesiones de esa cuenta
    y el usuario debe elegir una nueva al entrar."""
    if usuario_id == u["id"]:
        raise HTTPException(status_code=422, detail="Tu propia contraseña se cambia desde tu perfil")
    validar_password(datos.password)
    ph = bcrypt.hashpw(datos.password.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM usuarios WHERE id=?", (usuario_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        conn.execute("UPDATE usuarios SET password_hash=?, debe_cambiar_password=1, password_v=COALESCE(password_v,0)+1 "
                     "WHERE id=?", (ph, usuario_id))
        conn.commit()
    finally:
        conn.close()
    return {"id": usuario_id, "mensaje": "Contraseña temporal guardada"}

@router.delete("/usuarios/{usuario_id}")
def eliminar_usuario(usuario_id: int, u=Depends(require_admin)):
    """Borra la cuenta y todo lo suyo (archivos, proyectos, dashboards, accesos compartidos y foto). No se puede deshacer."""
    if usuario_id == u["id"]:
        raise HTTPException(status_code=422, detail="No puedes eliminar tu propia cuenta")
    conn = get_db()
    try:
        objetivo = conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        if not objetivo:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        n = borrar_usuario(conn, dict(objetivo))
    finally:
        conn.close()
    return {"mensaje": "Cuenta eliminada", "id": usuario_id, "archivos_eliminados": n}
