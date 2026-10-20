"""Inicio de sesión y nombre de usuario."""
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel
import bcrypt
import re
import time
from core import storage
from core.db import get_db
from core.seguridad import crear_token, get_usuario_actual, usuario_publico
from servicios.cuentas import ruta_avatar

router = APIRouter(tags=["Sesión"])

@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    u = conn.execute("SELECT * FROM usuarios WHERE lower(correo)=lower(?) AND activo=1",
                     (form.username.strip(),)).fetchone()
    conn.close()
    if not u or not bcrypt.checkpw(form.password.encode(), u["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = crear_token({"sub": u["correo"], "rol": u["rol"]})
    return {"access_token": token, "token_type": "bearer", "usuario": usuario_publico(u)}

@router.get("/auth/me")
def me(u=Depends(get_usuario_actual)):
    return usuario_publico(u)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,20}$")

class UsernameIn(BaseModel):
    username: str

@router.post("/auth/username")
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
    return usuario_publico(nuevo)


# ── Foto de perfil ──────────────────────────────────────────────────────────────
MAX_AVATAR = 300 * 1024   # el navegador la reduce a ~256 px antes de enviarla; esto es solo el tope de seguridad

def _tipo_imagen(b: bytes):
    """Tipo real según los primeros bytes (no se confía en el nombre ni en el Content-Type enviado)."""
    if b[:3] == b"\xff\xd8\xff": return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n": return "image/png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP": return "image/webp"
    return None

@router.put("/auth/avatar")
async def subir_avatar(file: UploadFile = File(...), u=Depends(get_usuario_actual)):
    datos = await file.read(MAX_AVATAR + 1)
    if len(datos) > MAX_AVATAR:
        raise HTTPException(status_code=413, detail="La foto es demasiado pesada (máximo 300 KB)")
    tipo = _tipo_imagen(datos)
    if not tipo:
        raise HTTPException(status_code=422, detail="Formato no válido: usa una imagen JPG, PNG o WebP")
    storage.put(ruta_avatar(u["id"]), datos, tipo)
    version = int(time.time())
    conn = get_db()
    try:
        conn.execute("UPDATE usuarios SET avatar_v=? WHERE id=?", (version, u["id"])); conn.commit()
        nuevo = conn.execute("SELECT * FROM usuarios WHERE id=?", (u["id"],)).fetchone()
    finally:
        conn.close()
    return usuario_publico(nuevo)

@router.delete("/auth/avatar")
def quitar_avatar(u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        conn.execute("UPDATE usuarios SET avatar_v=0 WHERE id=?", (u["id"],)); conn.commit()
        nuevo = conn.execute("SELECT * FROM usuarios WHERE id=?", (u["id"],)).fetchone()
    finally:
        conn.close()
    try: storage.delete(ruta_avatar(u["id"]))
    except Exception: pass
    return usuario_publico(nuevo)

@router.get("/usuarios/{usuario_id}/avatar")
def ver_avatar(usuario_id: int, u=Depends(get_usuario_actual)):
    """La foto la ve su dueño y los administradores (que gestionan las cuentas); nadie más."""
    if usuario_id != u["id"] and u["rol"] != "admin":
        raise HTTPException(status_code=404, detail="Sin foto")
    conn = get_db()
    try:
        r = conn.execute("SELECT avatar_v FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    finally:
        conn.close()
    if not r or not (r["avatar_v"] or 0):
        raise HTTPException(status_code=404, detail="Sin foto")
    try:
        datos = storage.get(ruta_avatar(usuario_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Sin foto")
    return Response(content=datos, media_type=_tipo_imagen(datos) or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})
