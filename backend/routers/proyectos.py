"""Proyectos: carpetas personales para agrupar archivos."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel
from core.db import get_db
from core.seguridad import get_usuario_actual
from core.acceso import archivo_propio, proyecto_propio

router = APIRouter(tags=["Proyectos"])

MAX_PROYECTOS = 50

class ProyectoIn(BaseModel):
    nombre: str

class MoverIn(BaseModel):
    proyecto_id: Optional[int] = None

def _nombre_proyecto(texto):
    n = " ".join((texto or "").split())
    if not 1 <= len(n) <= 40:
        raise HTTPException(status_code=422, detail="El nombre del proyecto debe tener entre 1 y 40 caracteres")
    return n

def _nombre_libre(conn, nombre, u, excepto=None):
    for r in conn.execute("SELECT id, nombre FROM proyectos WHERE owner_id=?", (u["id"],)).fetchall():
        if r["nombre"].lower() == nombre.lower() and r["id"] != excepto:
            raise HTTPException(status_code=409, detail="Ya tienes un proyecto con ese nombre")

@router.get("/proyectos")
def listar_proyectos(u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        rows = conn.execute("""SELECT p.id, p.nombre, p.creado_en,
                   (SELECT COUNT(*) FROM archivos a WHERE a.proyecto_id=p.id AND a.subido_por=p.owner_id
                    AND a.estado='procesado' AND a.tipo='generico') AS num_archivos
                FROM proyectos p WHERE p.owner_id=? ORDER BY lower(p.nombre)""", (u["id"],)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

@router.post("/proyectos")
def crear_proyecto(datos: ProyectoIn, u=Depends(get_usuario_actual)):
    nombre = _nombre_proyecto(datos.nombre)
    conn = get_db()
    try:
        _nombre_libre(conn, nombre, u)
        if conn.execute("SELECT COUNT(*) AS n FROM proyectos WHERE owner_id=?", (u["id"],)).fetchone()["n"] >= MAX_PROYECTOS:
            raise HTTPException(status_code=422, detail=f"Máximo {MAX_PROYECTOS} proyectos")
        cur = conn.execute("INSERT INTO proyectos (owner_id, nombre) VALUES (?,?)", (u["id"], nombre))
        pid = cur.lastrowid; conn.commit()
    finally:
        conn.close()
    return {"id": pid, "nombre": nombre, "num_archivos": 0}

@router.patch("/proyectos/{proyecto_id}")
def renombrar_proyecto(proyecto_id: int, datos: ProyectoIn, u=Depends(get_usuario_actual)):
    nombre = _nombre_proyecto(datos.nombre)
    conn = get_db()
    try:
        proyecto_propio(conn, proyecto_id, u)
        _nombre_libre(conn, nombre, u, excepto=proyecto_id)
        conn.execute("UPDATE proyectos SET nombre=? WHERE id=?", (nombre, proyecto_id)); conn.commit()
    finally:
        conn.close()
    return {"id": proyecto_id, "nombre": nombre}

@router.delete("/proyectos/{proyecto_id}")
def borrar_proyecto(proyecto_id: int, u=Depends(get_usuario_actual)):
    """Borra el proyecto, NO sus archivos: quedan sin proyecto."""
    conn = get_db()
    try:
        proyecto_propio(conn, proyecto_id, u)
        conn.execute("UPDATE archivos SET proyecto_id=NULL WHERE proyecto_id=? AND subido_por=?", (proyecto_id, u["id"]))
        conn.execute("DELETE FROM proyectos WHERE id=?", (proyecto_id,)); conn.commit()
    finally:
        conn.close()
    return {"mensaje": "Proyecto eliminado; sus archivos siguen en Mis archivos"}

@router.put("/archivos/{archivo_id}/proyecto")
def mover_a_proyecto(archivo_id: int, datos: MoverIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        archivo_propio(conn, archivo_id, u)
        if datos.proyecto_id is not None:
            proyecto_propio(conn, datos.proyecto_id, u)
        conn.execute("UPDATE archivos SET proyecto_id=? WHERE id=?", (datos.proyecto_id, archivo_id)); conn.commit()
    finally:
        conn.close()
    return {"archivo_id": archivo_id, "proyecto_id": datos.proyecto_id}
