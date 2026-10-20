"""Dashboards: propuesta automática, cálculo de gráficas, vistas guardadas y valores de filtros."""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
import json
import io
from servicios import dashboard as dash
from core.db import get_db
from core.seguridad import get_usuario_actual
from core.acceso import archivo_con_acceso, archivo_propio
from servicios.parquet import (esquema_dataset, datos_dataset)
from servicios.vistas import MAX_VISTAS, nombre_vista, config_limpia, vista_de, lista_vistas, columnas_editor

router = APIRouter(tags=["Dashboards"])

class ConfigDashIn(BaseModel):
    config: dict

class VistaIn(BaseModel):
    nombre: Optional[str] = None
    config: Optional[dict] = None

@router.get("/datasets/{archivo_id}/dashboard")
def ver_dashboard(archivo_id: int, vista: Optional[int] = None, u=Depends(get_usuario_actual)):
    """Vista guardada (la pedida o la primera) o, si el archivo aún no tiene ninguna, la propuesta automática."""
    conn = get_db()
    try:
        a = archivo_con_acceso(conn, archivo_id, u)
        esquema = esquema_dataset(a)
        vistas = lista_vistas(conn, a)
        config, actual = None, None
        if vista is not None:
            actual = vista_de(conn, a, vista)
        elif vistas:
            actual = vista_de(conn, a, vistas[0]["id"])
        if actual is not None:
            try:
                config = dash.limpiar_config(json.loads(actual["config_json"]), esquema)
            except (dash.ConfigInvalida, ValueError):
                config = None                      # configuración dañada: se muestra la propuesta
        guardada = config is not None
        if config is None:
            resumen = json.loads(a["resumen_json"]) if a["resumen_json"] else []
            config = dash.limpiar_config(dash.sugerir(esquema, resumen), esquema)
        return {"archivo": {"id": a["id"], "nombre": a["nombre"], "filas": a["filas"], "es_mio": a["subido_por"] == u["id"]},
                "vistas": vistas,
                "vista": {"id": actual["id"] if guardada else None,
                          "nombre": actual["nombre"] if guardada else "Resumen sugerido", "guardada": guardada},
                "config": config,
                "columnas": columnas_editor(a, esquema)}
    finally:
        conn.close()

@router.post("/datasets/{archivo_id}/dashboard/datos")
def datos_dashboard(archivo_id: int, datos: ConfigDashIn, u=Depends(get_usuario_actual)):
    """Calcula las gráficas de una configuración (guardada o en edición) sobre el archivo, ya filtrado y agregado."""
    import pandas as pd
    import pyarrow.parquet as pq
    conn = get_db()
    try:
        a = archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    esquema, parquet = datos_dataset(a)
    config = config_limpia(datos.config, esquema)
    cols = dash.columnas_usadas(config)
    pf = pq.ParquetFile(io.BytesIO(parquet))
    if cols:
        df = pf.read(columns=cols).to_pandas()
    else:
        df = pd.DataFrame(index=range(pf.metadata.num_rows))
    out = dash.calcular(df, config, esquema)
    out["config"] = config
    return out

@router.get("/datasets/{archivo_id}/valores")
def valores_columna(archivo_id: int, columna: str, u=Depends(get_usuario_actual)):
    """Valores posibles de una columna (para armar filtros): categorías más frecuentes, o mínimo y máximo."""
    import pyarrow.parquet as pq
    conn = get_db()
    try:
        a = archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    esquema, parquet = datos_dataset(a)
    roles = {c["nombre"]: c["rol"] for c in esquema if c["rol"] != "ignorar"}
    if columna not in roles:
        raise HTTPException(status_code=404, detail="Columna no encontrada")
    serie = pq.ParquetFile(io.BytesIO(parquet)).read(columns=[columna]).to_pandas()[columna]
    return dash.valores_columna(serie, roles[columna])

@router.post("/datasets/{archivo_id}/dashboard")
def crear_vista(archivo_id: int, datos: VistaIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = archivo_propio(conn, archivo_id, u)
        esquema = esquema_dataset(a)
        nombre = nombre_vista(datos.nombre)
        vistas = lista_vistas(conn, a)
        if len(vistas) >= MAX_VISTAS:
            raise HTTPException(status_code=422, detail=f"Máximo {MAX_VISTAS} vistas por archivo")
        if any(v["nombre"].lower() == nombre.lower() for v in vistas):
            raise HTTPException(status_code=409, detail="Ya hay una vista con ese nombre")
        if datos.config is None:
            resumen = json.loads(a["resumen_json"]) if a["resumen_json"] else []
            datos.config = dash.sugerir(esquema, resumen)
        config = config_limpia(datos.config, esquema)
        cur = conn.execute("INSERT INTO dashboards (archivo_id, owner_id, nombre, config_json) VALUES (?,?,?,?)",
                           (archivo_id, u["id"], nombre, json.dumps(config)))
        vid = cur.lastrowid; conn.commit()
    finally:
        conn.close()
    return {"id": vid, "nombre": nombre, "config": config}

@router.put("/datasets/{archivo_id}/dashboard/{vista_id}")
def guardar_vista(archivo_id: int, vista_id: int, datos: VistaIn, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = archivo_propio(conn, archivo_id, u)
        esquema = esquema_dataset(a)
        v = vista_de(conn, a, vista_id)
        nombre, config = v["nombre"], None
        if datos.nombre is not None:
            nombre = nombre_vista(datos.nombre)
            if any(x["nombre"].lower() == nombre.lower() and x["id"] != vista_id for x in lista_vistas(conn, a)):
                raise HTTPException(status_code=409, detail="Ya hay una vista con ese nombre")
        if datos.config is not None:
            config = config_limpia(datos.config, esquema)
        conn.execute("UPDATE dashboards SET nombre=?, config_json=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                     (nombre, json.dumps(config) if config is not None else v["config_json"], vista_id))
        conn.commit()
    finally:
        conn.close()
    return {"id": vista_id, "nombre": nombre, **({"config": config} if config is not None else {})}

@router.delete("/datasets/{archivo_id}/dashboard/{vista_id}")
def borrar_vista(archivo_id: int, vista_id: int, u=Depends(get_usuario_actual)):
    conn = get_db()
    try:
        a = archivo_propio(conn, archivo_id, u)
        vista_de(conn, a, vista_id)
        conn.execute("DELETE FROM dashboards WHERE id=?", (vista_id,)); conn.commit()
    finally:
        conn.close()
    return {"mensaje": "Vista eliminada"}
