"""Lectura de los datasets guardados en Parquet, con una caché pequeña en memoria."""
from fastapi import HTTPException
import json
import os
import io
import threading
from collections import OrderedDict
from core import storage

FILAS_POR_GRUPO = 10_000     # filas por grupo dentro de cada Parquet de datasets

# Caché pequeña de Parquets recientes (un dataset confirmado nunca cambia): evita bajar de Storage el mismo archivo
# en cada gráfica o página. Se llama solo después de comprobar que el usuario puede ver el archivo.
_PARQUET_CACHE: "OrderedDict[int, bytes]" = OrderedDict()
_PARQUET_CACHE_LOCK = threading.Lock()
PARQUET_CACHE_MAX_BYTES = int(os.getenv("PARQUET_CACHE_MAX_MB", "40")) * 1024 * 1024

def olvidar_parquet(archivo_id):
    with _PARQUET_CACHE_LOCK:
        _PARQUET_CACHE.pop(archivo_id, None)

def parquet_bytes(archivo_id):
    with _PARQUET_CACHE_LOCK:
        if archivo_id in _PARQUET_CACHE:
            _PARQUET_CACHE.move_to_end(archivo_id)
            return _PARQUET_CACHE[archivo_id]
    datos = storage.get(f"datasets/{archivo_id}.parquet")
    if len(datos) <= PARQUET_CACHE_MAX_BYTES:
        with _PARQUET_CACHE_LOCK:
            _PARQUET_CACHE[archivo_id] = datos
            while sum(len(v) for v in _PARQUET_CACHE.values()) > PARQUET_CACHE_MAX_BYTES:
                _PARQUET_CACHE.popitem(last=False)
    return datos

def esquema_dataset(a):
    """Esquema (columnas confirmadas) de un dataset procesado; 404 si no está disponible."""
    esquema = json.loads(a["esquema_json"] or "{}").get("columnas", [])
    if a["tipo"] != "generico" or a["estado"] != "procesado" or not esquema:
        raise HTTPException(status_code=404, detail="Datos no disponibles")
    return esquema

def datos_dataset(a):
    """(esquema, bytes del Parquet comprimido) de un dataset procesado; 404 si no está disponible."""
    esquema = esquema_dataset(a)
    try:
        return esquema, parquet_bytes(a["id"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Datos no disponibles")

def cargar_dataset(a):
    """DataFrame completo del dataset. Cargarlo entero cuesta memoria: úsalo solo cuando haga falta todo."""
    import pandas as pd
    esquema, datos = datos_dataset(a)
    return pd.read_parquet(io.BytesIO(datos), engine="pyarrow"), esquema

def pagina_parquet(datos: bytes, ini: int, n: int):
    """(total de filas, DataFrame con las filas [ini, ini+n)) leyendo solo los grupos de filas necesarios."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(io.BytesIO(datos))
    total = pf.metadata.num_rows
    grupos, saltar, acumulado = [], 0, 0
    for i in range(pf.metadata.num_row_groups):
        filas_grupo = pf.metadata.row_group(i).num_rows
        if acumulado + filas_grupo > ini and acumulado < ini + n:
            if not grupos:
                saltar = ini - acumulado
            grupos.append(i)
        acumulado += filas_grupo
        if acumulado >= ini + n:
            break
    if not grupos:
        return total, pf.schema_arrow.empty_table().to_pandas()
    return total, pf.read_row_groups(grupos).slice(saltar, n).to_pandas()
