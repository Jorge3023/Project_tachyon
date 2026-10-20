"""Quién puede ver o editar un archivo: el dueño, y quienes lo recibieron compartido por correo."""
from fastapi import HTTPException

def cond_visible(u, alias="a"):
    return (f"({alias}.subido_por=? OR EXISTS (SELECT 1 FROM comparticiones c "
            f"WHERE c.archivo_id={alias}.id AND c.correo=?))", [u["id"], u["correo"].lower()])

def archivo_con_acceso(conn, archivo_id, u):
    """Devuelve el archivo si el usuario puede verlo; si no, 404 (no revela que exista)."""
    cond, params = cond_visible(u)
    a = conn.execute(f"SELECT a.* FROM archivos a WHERE a.id=? AND {cond}", [archivo_id, *params]).fetchone()
    if not a:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return a

def archivo_propio(conn, archivo_id, u):
    a = conn.execute("SELECT * FROM archivos WHERE id=? AND subido_por=?", (archivo_id, u["id"])).fetchone()
    if not a:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return a

def proyecto_propio(conn, proyecto_id, u):
    p = conn.execute("SELECT * FROM proyectos WHERE id=? AND owner_id=?", (proyecto_id, u["id"])).fetchone()
    if not p:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return p
