"""Plantillas de columnas guardadas (privadas de cada usuario)."""
from fastapi import APIRouter, Depends, HTTPException
import json
from core.db import get_db
from core.seguridad import get_usuario_actual

router = APIRouter(tags=["Plantillas"])

@router.get("/plantillas")
def listar_plantillas(u=Depends(get_usuario_actual)):
    conn = get_db()
    rows = conn.execute("SELECT id,nombre,config_json,creado_en FROM plantillas WHERE owner_id=? ORDER BY id DESC",
                        (u["id"],)).fetchall(); conn.close()
    return [{"id": r["id"], "nombre": r["nombre"], "creado_en": r["creado_en"],
             "columnas": [c["nombre_origen"] for c in json.loads(r["config_json"])["columnas"]]} for r in rows]

@router.delete("/plantillas/{plantilla_id}")
def borrar_plantilla(plantilla_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    cur = conn.execute("DELETE FROM plantillas WHERE id=? AND owner_id=?", (plantilla_id, u["id"]))
    conn.commit(); conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"mensaje": "Plantilla eliminada"}
