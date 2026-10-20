"""Borrado de archivos y de cuentas completas (base de datos + almacenamiento)."""
from core import storage
from servicios.parquet import olvidar_parquet

def rutas_de_archivo(archivo_id):
    return (f"datasets/{archivo_id}.parquet", f"borradores/{archivo_id}.src")

def ruta_avatar(usuario_id):
    return f"avatares/{usuario_id}"

def quitar_archivo(conn, archivo_id):
    """Borra las filas de un archivo (sin hacer commit). Devuelve las rutas de almacenamiento a limpiar después."""
    conn.execute("DELETE FROM comparticiones WHERE archivo_id=?", (archivo_id,))
    conn.execute("DELETE FROM dashboards WHERE archivo_id=?", (archivo_id,))
    conn.execute("DELETE FROM archivos WHERE id=?", (archivo_id,))
    return rutas_de_archivo(archivo_id)

def limpiar_almacenamiento(archivo_id, rutas):
    """Tras confirmar el borrado en la base: olvida la caché y borra los objetos (los fallos no detienen el resto)."""
    olvidar_parquet(archivo_id)
    for ruta in rutas:
        try:
            storage.delete(ruta)
        except Exception:
            pass

def borrar_usuario(conn, usuario):
    """Elimina la cuenta y todo lo suyo. Un solo commit; el almacenamiento se limpia al final.
    También se quitan los archivos que otros compartieron CON su correo, para que quien se registre
    después con ese correo no herede accesos."""
    uid, correo = usuario["id"], usuario["correo"].lower()
    ids = [r["id"] for r in conn.execute("SELECT id FROM archivos WHERE subido_por=?", (uid,)).fetchall()]
    pendientes = [(i, quitar_archivo(conn, i)) for i in ids]
    conn.execute("DELETE FROM comparticiones WHERE compartido_por=? OR lower(correo)=?", (uid, correo))
    conn.execute("DELETE FROM dashboards WHERE owner_id=?", (uid,))
    conn.execute("DELETE FROM plantillas WHERE owner_id=?", (uid,))
    conn.execute("DELETE FROM proyectos WHERE owner_id=?", (uid,))
    conn.execute("DELETE FROM usuarios WHERE id=?", (uid,))
    conn.commit()
    for i, rutas in pendientes:
        limpiar_almacenamiento(i, rutas)
    try:
        storage.delete(ruta_avatar(uid))
    except Exception:
        pass
    return len(ids)
