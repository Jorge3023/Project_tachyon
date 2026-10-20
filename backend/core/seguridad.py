"""Sesiones: token JWT, usuario actual y permiso de administrador."""
from fastapi import Depends, HTTPException
from datetime import datetime, timedelta
import jwt
from core.db import get_db
from fastapi.security import OAuth2PasswordBearer
from core.config import SECRET_KEY, ALGORITHM, TOKEN_HOURS
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

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

def usuario_publico(u):
    """Datos del usuario que ve el frontend. 'nombre' = username si ya lo eligió."""
    return {"id": u["id"], "nombre": u["username"] or u["nombre"], "username": u["username"],
            "correo": u["correo"], "rol": u["rol"], "necesita_username": not u["username"]}
