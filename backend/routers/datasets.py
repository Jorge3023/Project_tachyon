"""Datasets genéricos: subir, revisar columnas, confirmar y ver datos de cualquier Excel/CSV."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import Optional, List
from pydantic import BaseModel
import json
import os
import io
from servicios import detector
from core import db, storage
from core.db import get_db
from core.acceso import proyecto_propio
from core.seguridad import get_usuario_actual
from core.acceso import archivo_con_acceso
from servicios.parquet import (datos_dataset, pagina_parquet, FILAS_POR_GRUPO)

router = APIRouter(tags=["Datasets"])

MAX_BYTES_DATASET = 25 * 1024 * 1024
MAX_FILAS_DATASET = 500_000
MAX_COLUMNAS_DATASET = 200

class ColumnaIn(BaseModel):
    nombre: str                       # nombre original en el archivo
    rol: str
    nombre_mostrar: Optional[str] = None

class ConfirmarIn(BaseModel):
    hoja: Optional[str] = None
    fila_encabezado: Optional[int] = None
    columnas: List[ColumnaIn]
    guardar_plantilla: bool = False
    nombre_plantilla: Optional[str] = None
    proyecto_id: Optional[int] = None     # proyecto donde guardar el archivo (opcional)

def _json_seguro(obj):
    """Convierte tipos de numpy/pandas a tipos JSON normales."""
    return json.loads(json.dumps(obj, default=lambda o: o.item() if hasattr(o, "item") else str(o)))

def _borrador_propio(conn, archivo_id, u):
    a = conn.execute("SELECT * FROM archivos WHERE id=? AND subido_por=? AND tipo='generico' AND estado='borrador'",
                     (archivo_id, u["id"])).fetchone()
    if not a:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    return a

def _plantilla_para(conn, u, nombres):
    """Plantilla propia que coincide exacto (misma huella) o, si no, la más parecida (>= 70 %)."""
    filas = conn.execute("SELECT * FROM plantillas WHERE owner_id=?", (u["id"],)).fetchall()
    hf = detector.huella(nombres)
    mejor, mejor_s = None, 0.0
    for p in filas:
        cfg = json.loads(p["config_json"])
        s = 1.0 if p["huella"] == hf else detector.similitud(nombres, [c["nombre_origen"] for c in cfg["columnas"]])
        if s > mejor_s:
            mejor, mejor_s = (p, cfg), s
    if mejor and mejor_s >= 0.7:
        return mejor[0], mejor[1], mejor_s
    return None, None, 0.0

def _analisis(conn, archivo_id, contenido, nombre, u, hoja=None, fila_encabezado=None):
    try:
        r = detector.leer_archivo(contenido, nombre, hoja=hoja, fila_encabezado=fila_encabezado)
    except detector.ArchivoNoSoportado as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo: {e}")
    df = r["df"]
    if df.shape[1] > MAX_COLUMNAS_DATASET:
        raise HTTPException(status_code=422, detail=f"El archivo tiene {df.shape[1]} columnas (máximo {MAX_COLUMNAS_DATASET}).")
    if len(df) > MAX_FILAS_DATASET:
        raise HTTPException(status_code=422, detail=f"El archivo tiene {len(df):,} filas (máximo {MAX_FILAS_DATASET:,}).")
    perfiles = detector.perfilar_columnas(df)
    pl, cfg, sim = _plantilla_para(conn, u, list(df.columns))
    if pl:
        perfiles = detector.aplicar_plantilla(perfiles, cfg["columnas"])
    for p in perfiles:
        p.setdefault("nombre_mostrar", p["nombre"])
        p["revisar"] = p["confianza"] < detector.UMBRAL_REVISAR
    muestra = df.head(8).astype(object).where(df.head(8).notna(), None)
    return _json_seguro({
        "archivo_id": archivo_id, "nombre": nombre,
        "hojas": r["hojas"], "hoja": r["hoja"], "fila_encabezado": r["fila_encabezado"],
        "sin_encabezado": r["sin_encabezado"], "filas": int(len(df)),
        "columnas": perfiles, "roles": detector.ROLES, "umbral_revisar": detector.UMBRAL_REVISAR,
        "vista_previa": {"columnas": [str(c) for c in df.columns],
                         "filas": [[None if v is None else str(v) for v in fila] for fila in muestra.values.tolist()]},
        "plantilla": {"id": pl["id"], "nombre": pl["nombre"], "similitud": round(sim, 2)} if pl else None,
    })

def _leer_borrador(archivo_id: int) -> bytes:
    try:
        return storage.get(f"borradores/{archivo_id}.src")
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="El borrador expiró; vuelve a subir el archivo")

@router.post("/datasets/analizar")
async def analizar_dataset(file: UploadFile = File(...), u=Depends(get_usuario_actual)):
    contenido = await file.read(MAX_BYTES_DATASET + 1)
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo está vacío")
    if len(contenido) > MAX_BYTES_DATASET:
        raise HTTPException(status_code=413, detail=f"El archivo supera {MAX_BYTES_DATASET // (1024*1024)} MB")
    nombre = os.path.basename(file.filename or "archivo")
    conn = get_db()
    try:
        # borradores abandonados del mismo usuario (de más de un día) se limpian
        viejos = conn.execute("""SELECT id FROM archivos WHERE subido_por=? AND estado='borrador'
                                 AND subido_en < ?""", (u["id"], db.hace_dias(1))).fetchall()
        for v in viejos:
            conn.execute("DELETE FROM archivos WHERE id=?", (v["id"],))
            storage.delete(f"borradores/{v['id']}.src")
        cur = conn.execute("""INSERT INTO archivos (nombre,tipo,filas,estado,subido_por)
                              VALUES (?,'generico',0,'borrador',?)""", (nombre, u["id"]))
        aid = cur.lastrowid
        try:
            res = _analisis(conn, aid, contenido, nombre, u)
        except HTTPException:
            conn.execute("DELETE FROM archivos WHERE id=?", (aid,)); conn.commit()
            raise
        storage.put(f"borradores/{aid}.src", contenido)
        conn.commit()
        return res
    finally:
        conn.close()

@router.get("/datasets/{archivo_id}/analisis")
def reanalizar_dataset(archivo_id: int, hoja: Optional[str] = None, fila_encabezado: Optional[int] = None,
                       u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _borrador_propio(conn, archivo_id, u)
        contenido = _leer_borrador(archivo_id)
        return _analisis(conn, archivo_id, contenido, a["nombre"], u, hoja=hoja, fila_encabezado=fila_encabezado)
    finally:
        conn.close()

@router.delete("/datasets/{archivo_id}/borrador")
def cancelar_borrador(archivo_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        _borrador_propio(conn, archivo_id, u)
        conn.execute("DELETE FROM archivos WHERE id=?", (archivo_id,)); conn.commit()
    finally:
        conn.close()
    storage.delete(f"borradores/{archivo_id}.src")
    return {"mensaje": "Borrador descartado"}

@router.post("/datasets/{archivo_id}/confirmar")
def confirmar_dataset(archivo_id: int, datos: ConfirmarIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _borrador_propio(conn, archivo_id, u)
        if datos.proyecto_id is not None:
            proyecto_propio(conn, datos.proyecto_id, u)
        contenido = _leer_borrador(archivo_id)
        for c in datos.columnas:
            if c.rol not in detector.ROLES:
                raise HTTPException(status_code=422, detail=f"Rol no válido: {c.rol}")
        if not any(c.rol != "ignorar" for c in datos.columnas):
            raise HTTPException(status_code=422, detail="Deja al menos una columna sin ignorar")
        try:
            r = detector.leer_archivo(contenido, a["nombre"], hoja=datos.hoja, fila_encabezado=datos.fila_encabezado)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo: {e}")
        df0 = r["df"]
        columnas = [{"nombre": c.nombre, "rol": c.rol, "nombre_mostrar": (c.nombre_mostrar or "").strip() or c.nombre}
                    for c in datos.columnas if c.nombre in df0.columns]
        limpio = detector.aplicar_esquema(df0, columnas)
        if limpio.empty:
            raise HTTPException(status_code=422, detail="Después de limpiar no quedaron datos")
        # esquema final con los nombres ya únicos que quedaron en el DataFrame limpio
        activas = [c for c in columnas if c["rol"] != "ignorar"]
        esquema = [{"nombre": nombre_final, "rol": c["rol"], "origen": c["nombre"]}
                   for nombre_final, c in zip(limpio.columns, activas)]
        buf = io.BytesIO()
        # Grupos de filas de tamaño fijo: así "Ver datos" puede leer solo la página que se pide
        limpio.to_parquet(buf, engine="pyarrow", compression="zstd", index=False, row_group_size=FILAS_POR_GRUPO)
        storage.put(f"datasets/{archivo_id}.parquet", buf.getvalue(), "application/octet-stream")
        try:
            hf = detector.huella([c["nombre"] for c in columnas])
            # El resumen por columna se calcula una sola vez, aquí, y se guarda (es pequeño)
            resumen = _json_seguro(detector.resumen_columnas(
                limpio, [{"nombre": c["nombre"], "rol": c["rol"]} for c in esquema]))
            conn.execute("""UPDATE archivos SET estado='procesado', filas=?, esquema_json=?, huella=?, resumen_json=?,
                            proyecto_id=? WHERE id=?""",
                         (int(len(limpio)), json.dumps({"hoja": r["hoja"], "fila_encabezado": r["fila_encabezado"],
                                                        "columnas": esquema}), hf, json.dumps(resumen), datos.proyecto_id, archivo_id))
            plantilla_guardada = False
            if datos.guardar_plantilla:
                cfg = {"columnas": [{"nombre_origen": c["nombre"], "rol": c["rol"], "nombre_mostrar": c["nombre_mostrar"]}
                                    for c in columnas]}
                nombre_pl = (datos.nombre_plantilla or "").strip() or os.path.splitext(a["nombre"])[0]
                conn.execute("""INSERT INTO plantillas (owner_id,nombre,huella,config_json) VALUES (?,?,?,?)
                                ON CONFLICT(owner_id,huella) DO UPDATE SET nombre=excluded.nombre, config_json=excluded.config_json""",
                             (u["id"], nombre_pl[:80], hf, json.dumps(cfg)))
                plantilla_guardada = True
            conn.commit()
        except Exception:
            storage.delete(f"datasets/{archivo_id}.parquet")   # no dejar archivos huérfanos si falla la base de datos
            raise
    finally:
        conn.close()
    storage.delete(f"borradores/{archivo_id}.src")
    return {"mensaje": f"'{a['nombre']}' guardado: {len(limpio):,} filas, {len(esquema)} columnas.",
            "archivo_id": archivo_id, "filas": int(len(limpio)), "plantilla_guardada": plantilla_guardada}

@router.get("/datasets/{archivo_id}/datos")
def ver_dataset(archivo_id: int, pagina: int = Query(1, ge=1), por_pagina: int = Query(50, ge=1, le=200),
                u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    esquema, datos = datos_dataset(a)
    ini = (pagina - 1) * por_pagina
    total, trozo = pagina_parquet(datos, ini, por_pagina)
    for c in esquema:
        if c["rol"] == "fecha":
            trozo[c["nombre"]] = trozo[c["nombre"]].dt.strftime("%Y-%m-%d %H:%M").str.replace(" 00:00", "", regex=False)
    trozo = trozo.astype(object).where(trozo.notna(), None)
    if a["resumen_json"]:
        resumen = json.loads(a["resumen_json"])
    else:   # datasets guardados antes de que el resumen se calculara al confirmar
        import pandas as pd
        resumen = _json_seguro(detector.resumen_columnas(
            pd.read_parquet(io.BytesIO(datos), engine="pyarrow"),
            [{"nombre": c["nombre"], "rol": c["rol"]} for c in esquema]))
    return _json_seguro({
        "archivo": {"id": a["id"], "nombre": a["nombre"], "es_mio": a["subido_por"] == u["id"]},
        "columnas": esquema, "total": int(total), "pagina": pagina, "por_pagina": por_pagina,
        "filas": trozo.values.tolist(), "resumen": resumen,
    })
