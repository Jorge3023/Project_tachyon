"""Datasets genéricos: subir, revisar columnas, confirmar y ver datos de cualquier Excel/CSV."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import Optional, List
from pydantic import BaseModel
import gzip
import json
import os
import io
from servicios import detector
from servicios import dashboard as dash
from core import db, storage
from core.db import get_db
from core.acceso import proyecto_propio, archivo_propio
from core.seguridad import get_usuario_actual
from core.acceso import archivo_con_acceso
from servicios.parquet import datos_dataset, pagina_parquet, a_parquet, olvidar_parquet, cargar_dataset
from servicios.cuentas import ruta_original

router = APIRouter(tags=["Datasets"])

MAX_BYTES_DATASET = 25 * 1024 * 1024
MAX_FILAS_DATASET = 500_000
MAX_COLUMNAS_DATASET = 200

class ColumnaIn(BaseModel):
    nombre: str                       # nombre original en el archivo
    rol: str
    nombre_mostrar: Optional[str] = None
    formato: Optional[str] = None     # solo números: "numero" | "moneda" | "porcentaje" (None = automático)

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

def _analisis(conn, archivo_id, contenido, nombre, u, hoja=None, fila_encabezado=None, con_plantilla=True):
    try:
        r = detector.leer_archivo(contenido, nombre, hoja=hoja, fila_encabezado=fila_encabezado,
                                  max_filas=MAX_FILAS_DATASET)
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
    pl, cfg, sim = _plantilla_para(conn, u, list(df.columns)) if con_plantilla else (None, None, 0.0)
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

def _leer_tabla(contenido, nombre, hoja, fila_encabezado):
    try:
        r = detector.leer_archivo(contenido, nombre, hoja=hoja, fila_encabezado=fila_encabezado, max_filas=MAX_FILAS_DATASET)
    except detector.ArchivoNoSoportado as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo: {e}")
    if len(r["df"]) > MAX_FILAS_DATASET:
        raise HTTPException(status_code=422, detail=f"El archivo tiene {len(r['df']):,} filas (máximo {MAX_FILAS_DATASET:,}).")
    return r


def _columnas_de(columnas_in, df0):
    for c in columnas_in:
        if c.rol not in detector.ROLES:
            raise HTTPException(status_code=422, detail=f"Rol no válido: {c.rol}")
        if c.formato is not None and c.formato not in detector.FORMATOS:
            raise HTTPException(status_code=422, detail=f"Formato no válido: {c.formato}")
    if not any(c.rol != "ignorar" for c in columnas_in):
        raise HTTPException(status_code=422, detail="Deja al menos una columna sin ignorar")
    return [{"nombre": c.nombre, "rol": c.rol, "nombre_mostrar": (c.nombre_mostrar or "").strip() or c.nombre,
             "formato": c.formato} for c in columnas_in if c.nombre in df0.columns]


def _construir(df0, columnas):
    """Tabla limpia + esquema (con formato y valores no leídos) + resumen por columna."""
    informe = {}
    limpio = detector.aplicar_esquema(df0, columnas, informe)
    if limpio.empty:
        raise HTTPException(status_code=422, detail="Después de limpiar no quedaron datos")
    # esquema final con los nombres ya únicos que quedaron en el DataFrame limpio
    activas = [c for c in columnas if c["rol"] != "ignorar"]
    esquema = []
    for nombre_final, c in zip(limpio.columns, activas):
        e = {"nombre": nombre_final, "rol": c["rol"], "origen": c["nombre"]}
        if c["rol"] == "numero":
            f = c.get("formato")
            if f is None:       # automático: lo que traía el archivo ($, %) o, si no, lo que sugiere el nombre
                f = detector._formato(df0[c["nombre"]]) or detector.formato_por_nombre(nombre_final, limpio[nombre_final])
            e["formato"] = f if f in ("moneda", "porcentaje") else None
        if informe.get(nombre_final, {}).get("no_leidos"):
            e["no_leidos"] = informe[nombre_final]["no_leidos"]
        esquema.append(e)
    # El resumen por columna se calcula una sola vez, aquí, y se guarda (es pequeño)
    resumen = _json_seguro(detector.resumen_columnas(
        limpio, [{"nombre": c["nombre"], "rol": c["rol"]} for c in esquema], informe))
    return limpio, esquema, resumen


def _guardar_plantilla(conn, u, columnas, nombre, hf):
    cfg = {"columnas": [{"nombre_origen": c["nombre"], "rol": c["rol"], "nombre_mostrar": c["nombre_mostrar"],
                         "formato": c.get("formato")} for c in columnas]}
    conn.execute("""INSERT INTO plantillas (owner_id,nombre,huella,config_json) VALUES (?,?,?,?)
                    ON CONFLICT(owner_id,huella) DO UPDATE SET nombre=excluded.nombre, config_json=excluded.config_json""",
                 (u["id"], nombre[:80], hf, json.dumps(cfg)))


def _aviso_no_leidos(esquema):
    malas = [f"{c['nombre']} ({c['no_leidos']:,})" for c in esquema if c.get("no_leidos")]
    return f" Valores que no se pudieron leer y quedaron vacíos: {', '.join(malas)}." if malas else ""


@router.post("/datasets/{archivo_id}/confirmar")
def confirmar_dataset(archivo_id: int, datos: ConfirmarIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = _borrador_propio(conn, archivo_id, u)
        if datos.proyecto_id is not None:
            proyecto_propio(conn, datos.proyecto_id, u)
        contenido = _leer_borrador(archivo_id)
        r = _leer_tabla(contenido, a["nombre"], datos.hoja, datos.fila_encabezado)
        df0 = r.pop("df")
        columnas = _columnas_de(datos.columnas, df0)
        limpio, esquema, resumen = _construir(df0, columnas)
        del df0                                   # la tabla cruda ya no hace falta: se libera antes de escribir el Parquet
        # Grupos de filas de tamaño fijo: así "Ver datos" puede leer solo la página que se pide
        storage.put(f"datasets/{archivo_id}.parquet", a_parquet(limpio), "application/octet-stream")
        try:
            # El original (comprimido) se conserva para poder corregir los tipos de columna después
            storage.put(ruta_original(archivo_id), gzip.compress(contenido, 6), "application/gzip")
            del contenido
            hf = detector.huella([c["nombre"] for c in columnas])
            conn.execute("""UPDATE archivos SET estado='procesado', filas=?, esquema_json=?, huella=?, resumen_json=?,
                            proyecto_id=? WHERE id=?""",
                         (int(len(limpio)), json.dumps({"hoja": r["hoja"], "fila_encabezado": r["fila_encabezado"],
                                                        "columnas": esquema}), hf, json.dumps(resumen), datos.proyecto_id, archivo_id))
            plantilla_guardada = False
            if datos.guardar_plantilla:
                nombre_pl = (datos.nombre_plantilla or "").strip() or os.path.splitext(a["nombre"])[0]
                _guardar_plantilla(conn, u, columnas, nombre_pl, hf)
                plantilla_guardada = True
            conn.commit()
        except Exception:
            storage.delete(f"datasets/{archivo_id}.parquet")   # no dejar archivos huérfanos si falla la base de datos
            storage.delete(ruta_original(archivo_id))
            raise
    finally:
        conn.close()
    storage.delete(f"borradores/{archivo_id}.src")
    return {"mensaje": f"'{a['nombre']}' guardado: {len(limpio):,} filas, {len(esquema)} columnas.{_aviso_no_leidos(esquema)}",
            "archivo_id": archivo_id, "filas": int(len(limpio)), "plantilla_guardada": plantilla_guardada,
            "no_leidos": {c["nombre"]: c["no_leidos"] for c in esquema if c.get("no_leidos")}}


# ── Corregir las columnas de un archivo ya guardado ──────────────────────────────────────────────────
def _leer_original(archivo_id):
    try:
        return gzip.decompress(storage.get(ruta_original(archivo_id)))
    except FileNotFoundError:
        return None


def _como_texto(df, esquema):
    """Archivos guardados antes de conservar el original: se reconstruye una tabla de texto desde los datos limpios
    (con los nombres originales), para volver a leerla con otros tipos. Las columnas que se ignoraron ya no están."""
    import pandas as pd
    out = {}
    for c in esquema:
        s = df[c["nombre"]]
        if c["rol"] == "fecha":
            t = s.dt.strftime("%Y-%m-%d %H:%M:%S").str.replace(" 00:00:00", "", regex=False)
        elif c["rol"] == "numero":
            t = s.map(lambda v: None if pd.isna(v) else (str(int(v)) if float(v).is_integer() and abs(v) < 1e15 else repr(float(v))))
        else:
            t = s
        out[c.get("origen") or c["nombre"]] = t.astype(object).where(s.notna(), None)
    return pd.DataFrame(out)


@router.get("/datasets/{archivo_id}/columnas")
def columnas_dataset(archivo_id: int, hoja: Optional[str] = None, fila_encabezado: Optional[int] = None,
                     u=Depends(get_usuario_actual)):
    """Las columnas de un archivo ya guardado, con su tipo actual, para corregirlas (solo el dueño)."""
    conn = get_db()
    try:
        a = archivo_propio(conn, archivo_id, u)
        meta = json.loads(a["esquema_json"] or "{}")
        esquema = meta.get("columnas") or []
        if a["estado"] != "procesado" or not esquema:
            raise HTTPException(status_code=404, detail="Datos no disponibles")
        contenido = _leer_original(archivo_id)
        if contenido is not None:
            mismo = (hoja in (None, meta.get("hoja"))) and (fila_encabezado in (None, meta.get("fila_encabezado")))
            res = _analisis(conn, archivo_id, contenido, a["nombre"], u, hoja=hoja or meta.get("hoja"),
                            fila_encabezado=meta.get("fila_encabezado") if fila_encabezado is None else fila_encabezado,
                            con_plantilla=False)
        else:
            mismo = True
            df, _ = cargar_dataset(a)
            texto = _como_texto(df, esquema)
            del df
            perfiles = detector.perfilar_columnas(texto)
            for p in perfiles:
                p["nombre_mostrar"] = p["nombre"]
            muestra = texto.head(8)
            res = _json_seguro({
                "archivo_id": archivo_id, "nombre": a["nombre"], "hojas": [], "hoja": meta.get("hoja"),
                "fila_encabezado": meta.get("fila_encabezado") or 0, "sin_encabezado": False, "filas": int(len(texto)),
                "columnas": perfiles, "roles": detector.ROLES, "umbral_revisar": detector.UMBRAL_REVISAR,
                "vista_previa": {"columnas": [str(c) for c in texto.columns],
                                 "filas": [[None if v is None else str(v) for v in fila] for fila in muestra.values.tolist()]},
                "plantilla": None})
    finally:
        conn.close()
    # Lo que el usuario eligió al guardar manda sobre lo que se detecta ahora
    por_origen = {c.get("origen") or c["nombre"]: c for c in esquema}
    for p in res["columnas"]:
        e = por_origen.get(p["nombre"])
        if e:
            p["rol"], p["nombre_mostrar"] = e["rol"], e["nombre"]
            if e["rol"] == "numero":
                p["formato"] = e.get("formato") or "numero"
            p["confianza"], p["revisar"], p["razon"] = 1.0, False, "Tipo con el que está guardada"
        elif mismo:
            p["rol"], p["confianza"], p["revisar"], p["razon"] = "ignorar", 1.0, False, "Se ignoró al guardar"
    res["modo"] = "edicion"
    res["origen_disponible"] = contenido is not None
    return res


@router.post("/datasets/{archivo_id}/columnas")
def guardar_columnas(archivo_id: int, datos: ConfirmarIn, u=Depends(get_usuario_actual)):
    """Vuelve a procesar un archivo guardado con otros tipos o nombres de columna. Las vistas se conservan:
    los nombres nuevos se actualizan en ellas, y lo que ya no encaje se quita (con aviso) al abrirlas."""
    conn = get_db()
    try:
        a = archivo_propio(conn, archivo_id, u)
        meta = json.loads(a["esquema_json"] or "{}")
        viejo = meta.get("columnas") or []
        if a["estado"] != "procesado" or not viejo:
            raise HTTPException(status_code=404, detail="Datos no disponibles")
        contenido = _leer_original(archivo_id)
        if contenido is not None:
            r = _leer_tabla(contenido, a["nombre"], datos.hoja if datos.hoja is not None else meta.get("hoja"),
                            datos.fila_encabezado if datos.fila_encabezado is not None else meta.get("fila_encabezado"))
            del contenido
            df0, hoja, fila = r.pop("df"), r["hoja"], r["fila_encabezado"]
        else:
            df, _ = cargar_dataset(a)
            df0 = _como_texto(df, viejo)
            del df
            hoja, fila = meta.get("hoja"), meta.get("fila_encabezado")
        columnas = _columnas_de(datos.columnas, df0)
        limpio, esquema, resumen = _construir(df0, columnas)
        del df0
        # Las vistas guardadas usan el nombre visible: si una columna se renombró, se actualiza en todas
        antes = {c.get("origen") or c["nombre"]: c["nombre"] for c in viejo}
        mapa = {antes[e["origen"]]: e["nombre"] for e in esquema if e["origen"] in antes and antes[e["origen"]] != e["nombre"]}
        for v in conn.execute("SELECT id, config_json FROM dashboards WHERE archivo_id=?", (archivo_id,)).fetchall():
            try:
                cfg = dash.renombrar_columnas(json.loads(v["config_json"]), mapa)
            except ValueError:
                continue
            conn.execute("UPDATE dashboards SET config_json=? WHERE id=?", (json.dumps(cfg), v["id"]))
        hf = detector.huella([c["nombre"] for c in columnas])
        conn.execute("UPDATE archivos SET filas=?, esquema_json=?, huella=?, resumen_json=? WHERE id=?",
                     (int(len(limpio)), json.dumps({"hoja": hoja, "fila_encabezado": fila, "columnas": esquema}), hf,
                      json.dumps(resumen), archivo_id))
        if datos.guardar_plantilla:
            nombre_pl = (datos.nombre_plantilla or "").strip() or os.path.splitext(a["nombre"])[0]
            _guardar_plantilla(conn, u, columnas, nombre_pl, hf)
        # El Parquet nuevo se escribe antes de confirmar: si falla, la base de datos no cambia
        storage.put(f"datasets/{archivo_id}.parquet", a_parquet(limpio), "application/octet-stream")
        conn.commit()
    finally:
        conn.close()
    olvidar_parquet(archivo_id)
    return {"mensaje": f"Columnas actualizadas: {len(limpio):,} filas, {len(esquema)} columnas.{_aviso_no_leidos(esquema)}",
            "archivo_id": archivo_id, "filas": int(len(limpio)),
            "no_leidos": {c["nombre"]: c["no_leidos"] for c in esquema if c.get("no_leidos")}}

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
