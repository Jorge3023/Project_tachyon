"""Dashboard principal de cada usuario: el que se abre al entrar."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel
import json
from core.db import get_db
from core.seguridad import get_usuario_actual
from core.acceso import archivo_con_acceso
from servicios.vistas import vista_de

router = APIRouter(tags=["Dashboard principal"])

# ── Dashboard principal: el que cada usuario ve al entrar (puede ser de un archivo suyo o compartido) ────
class PrincipalIn(BaseModel):
    archivo_id: int
    vista_id: Optional[int] = None

def _principal_valido(conn, u):
    """Devuelve el dashboard principal vigente del usuario o None (si ya no existe o ya no tiene acceso)."""
    crudo = (conn.execute("SELECT dashboard_principal FROM usuarios WHERE id=?", (u["id"],)).fetchone() or {})
    crudo = crudo["dashboard_principal"] if crudo else None
    if not crudo:
        return None
    try:
        p = json.loads(crudo)
        a = archivo_con_acceso(conn, int(p["archivo_id"]), u)
    except (ValueError, KeyError, TypeError, HTTPException):
        conn.execute("UPDATE usuarios SET dashboard_principal=NULL WHERE id=?", (u["id"],)); conn.commit()
        return None
    if a["estado"] != "procesado":
        return None
    vista = None
    if p.get("vista_id") is not None:
        vista = conn.execute("SELECT id, nombre FROM dashboards WHERE id=? AND archivo_id=?", (p["vista_id"], a["id"])).fetchone()
    return {"archivo_id": a["id"], "archivo_nombre": a["nombre"], "vista_id": vista["id"] if vista else None,
            "vista_nombre": vista["nombre"] if vista else None}

@router.get("/me/dashboard-principal")
def ver_principal(u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        return {"principal": _principal_valido(conn, u)}
    finally:
        conn.close()

@router.put("/me/dashboard-principal")
def fijar_principal(datos: PrincipalIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = archivo_con_acceso(conn, datos.archivo_id, u)
        if a["estado"] != "procesado":
            raise HTTPException(status_code=409, detail="El archivo aún no está procesado")
        if datos.vista_id is not None:
            vista_de(conn, a, datos.vista_id)
        conn.execute("UPDATE usuarios SET dashboard_principal=? WHERE id=?",
                     (json.dumps({"archivo_id": a["id"], "vista_id": datos.vista_id}), u["id"]))
        conn.commit()
        return {"principal": _principal_valido(conn, u)}
    finally:
        conn.close()

@router.delete("/me/dashboard-principal")
def quitar_principal(u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        conn.execute("UPDATE usuarios SET dashboard_principal=NULL WHERE id=?", (u["id"],)); conn.commit()
    finally:
        conn.close()
    return {"principal": None}
