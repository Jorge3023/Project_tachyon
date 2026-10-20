"""Compartir archivos por correo (solo lectura para quien los recibe)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.validacion import EMAIL_RE
from core.db import get_db
from core.seguridad import get_usuario_actual
from core.acceso import archivo_propio

router = APIRouter(tags=["Compartir"])

class CompartirIn(BaseModel):
    correo: str

@router.get("/archivos/{archivo_id}/comparticiones")
def ver_comparticiones(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        archivo_propio(conn, archivo_id, u)
        rows = conn.execute("SELECT correo, creado_en FROM comparticiones WHERE archivo_id=? ORDER BY creado_en",
                            (archivo_id,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

@router.post("/archivos/{archivo_id}/comparticiones")
def compartir_archivo(archivo_id: int, datos: CompartirIn, u=Depends(get_usuario_actual)):
    correo = datos.correo.strip().lower()
    if not EMAIL_RE.match(correo):
        raise HTTPException(status_code=422, detail="Correo electrónico no válido")
    if correo == u["correo"].lower():
        raise HTTPException(status_code=422, detail="Ese archivo ya es tuyo")
    conn = get_db()
    try:
        archivo_propio(conn, archivo_id, u)
        # No se revela si el correo tiene cuenta: quien se registre con él verá el archivo.
        conn.execute("INSERT OR IGNORE INTO comparticiones (archivo_id, correo, compartido_por) VALUES (?,?,?)",
                     (archivo_id, correo, u["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"mensaje": f"Compartido con {correo}", "correo": correo}

@router.delete("/archivos/{archivo_id}/comparticiones/{correo}")
def dejar_de_compartir(archivo_id: int, correo: str, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        archivo_propio(conn, archivo_id, u)
        conn.execute("DELETE FROM comparticiones WHERE archivo_id=? AND correo=?", (archivo_id, correo.strip().lower()))
        conn.commit()
    finally:
        conn.close()
    return {"mensaje": "Se dejó de compartir"}
