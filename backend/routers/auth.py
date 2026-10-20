"""Inicio de sesión y nombre de usuario."""
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import bcrypt
import re
from core.db import get_db
from core.seguridad import crear_token, get_usuario_actual, usuario_publico

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
