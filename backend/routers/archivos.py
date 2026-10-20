"""Lista y borrado de archivos."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from core.db import get_db
from core.seguridad import get_usuario_actual
from core.acceso import cond_visible, archivo_propio
from servicios.cuentas import quitar_archivo, limpiar_almacenamiento

router = APIRouter(tags=["Archivos"])

@router.get("/archivos")
def listar_archivos(origen: str = "todos", proyecto: Optional[str] = None, u=Depends(get_usuario_actual)):
    """Datasets visibles para el usuario. origen: 'mios' | 'compartidos' | 'todos'.
    proyecto: id de uno de MIS proyectos, o 'sin' para los que no están en ninguno (solo archivos propios)."""
    conn = get_db()
    cond, params = cond_visible(u)
    q = f"""SELECT a.id, a.nombre, a.filas, a.estado, a.tipo, a.subido_por, a.subido_en, a.proyecto_id,
                   COALESCE(us.username, us.nombre) AS subido_por_nombre,
                   (a.subido_por=?) AS es_mio,
                   (SELECT COUNT(*) FROM comparticiones c2 WHERE c2.archivo_id=a.id) AS num_compartidos
            FROM archivos a LEFT JOIN usuarios us ON a.subido_por=us.id
            WHERE {cond} AND a.estado<>'borrador' AND a.tipo='generico'"""
    params = [u["id"], *params]
    if origen == "mios":
        q += " AND a.subido_por=?"; params.append(u["id"])
    elif origen == "compartidos":
        q += " AND a.subido_por<>?"; params.append(u["id"])
    if proyecto == "sin":
        q += " AND a.subido_por=? AND a.proyecto_id IS NULL"; params.append(u["id"])
    elif proyecto:
        if not proyecto.isdigit():
            raise HTTPException(status_code=422, detail="Proyecto no válido")
        q += " AND a.subido_por=? AND a.proyecto_id=?"; params += [u["id"], int(proyecto)]
    q += " ORDER BY a.subido_en DESC LIMIT 50"
    rows = conn.execute(q, params).fetchall(); conn.close()
    out = []
    for r in rows:
        d = dict(r); d["es_mio"] = bool(d["es_mio"])
        if not d["es_mio"]:
            d["num_compartidos"] = None   # solo el dueño ve con cuántos se comparte
            d["proyecto_id"] = None       # los proyectos son personales de cada quien
        out.append(d)
    return out

@router.delete("/archivos/{archivo_id}")
def eliminar_archivo(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        archivo_propio(conn, archivo_id, u)
    except HTTPException:
        conn.close(); raise

    rutas = quitar_archivo(conn, archivo_id)
    conn.commit()
    conn.close()
    limpiar_almacenamiento(archivo_id, rutas)

    return {"mensaje": "Archivo eliminado correctamente", "archivo_id": archivo_id}
