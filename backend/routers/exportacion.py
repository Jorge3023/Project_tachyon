"""Exportación a Excel y CSV (PNG, PDF y PowerPoint se generan en el navegador)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from typing import Optional, List
from pydantic import BaseModel
import io
import re
from datetime import datetime
from servicios import dashboard as dash
from servicios import exportar
from core.db import get_db
from core.seguridad import get_usuario_actual
from core.acceso import archivo_con_acceso
from servicios.parquet import datos_dataset
from servicios.vistas import config_limpia

router = APIRouter(tags=["Exportación"])

class ExportarIn(BaseModel):
    config: dict
    formato: str                              # "csv" | "xlsx"
    datos: bool = True                        # incluir las filas filtradas del archivo
    graficas: bool = True                     # xlsx: una hoja con los números de cada gráfica
    widgets: Optional[List[str]] = None       # ids de las gráficas a incluir (por defecto todas)
    vista: Optional[str] = None               # nombre de la vista (solo para el nombre del archivo y el resumen)

@router.post("/datasets/{archivo_id}/exportar")
def exportar_datos(archivo_id: int, datos: ExportarIn, u=Depends(get_usuario_actual)):
    """CSV o Excel con las filas que deja el filtro del dashboard y/o los números detrás de cada gráfica.
    Lo puede hacer quien ve el archivo (dueño o con quien se compartió): ya puede ver esas filas en «Ver datos»."""
    import pandas as pd
    import pyarrow.parquet as pq
    if datos.formato not in ("csv", "xlsx"):
        raise HTTPException(status_code=422, detail="Formato no válido (csv o xlsx)")
    if not datos.datos and not (datos.formato == "xlsx" and datos.graficas):
        raise HTTPException(status_code=422, detail="Elige qué exportar")
    conn = get_db()
    try:
        a = archivo_con_acceso(conn, archivo_id, u)
    finally:
        conn.close()
    esquema, parquet = datos_dataset(a)
    config = config_limpia(datos.config, esquema)
    if datos.widgets is not None:
        quiero = set(datos.widgets)
        config = {**config, "widgets": [w for w in config["widgets"] if w["id"] in quiero]}
    roles = dash._roles(esquema)
    pf = pq.ParquetFile(io.BytesIO(parquet))
    total = pf.metadata.num_rows
    hojas, df_datos, truncada, n_filas = [], None, False, 0
    if datos.datos:
        df = pf.read().to_pandas()
        df = dash.aplicar_filtros(df, config["filtros"], roles)
        n_filas = len(df)
        tope = exportar.MAX_FILAS_CSV if datos.formato == "csv" else exportar.MAX_FILAS_XLSX
        if n_filas > tope:
            df, truncada = df.head(tope), True
        df_datos = exportar.preparar(df, esquema)
    if datos.formato == "xlsx" and datos.graficas and config["widgets"]:
        usadas = dash.columnas_usadas(config)
        base = pf.read(columns=usadas).to_pandas() if usadas else pd.DataFrame(index=range(total))
        res = dash.calcular(base, config, esquema)
        for w in config["widgets"]:
            if w["tipo"] == "tabla":
                continue
            t = exportar.tabla_widget(w, res["widgets"].get(w["id"]))
            if t:
                hojas.append((w.get("titulo") or dash.ETIQUETA_TIPO[w["tipo"]], t[0], t[1]))
        if not datos.datos:
            n_filas = res["filas_filtradas"]
    nombre_vista = " ".join((datos.vista or "").split())[:40]
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    if datos.formato == "csv":
        cuerpo, tipo, ext = exportar.a_csv(df_datos), "text/csv; charset=utf-8", "csv"
    else:
        resumen = [("Archivo", a["nombre"]), ("Vista", nombre_vista or "Resumen sugerido"), ("Exportado", ahora),
                   ("Filas del archivo", total), ("Filas con los filtros", n_filas)]
        filtros = exportar.descripcion_filtros(config)
        resumen += [("Filtros", "; ".join(filtros) if filtros else "Ninguno")]
        if truncada:
            resumen += [("Aviso", f"La hoja «Datos» incluye solo las primeras {exportar.MAX_FILAS_XLSX:,} filas de {n_filas:,}. Usa CSV para exportar más.")]
        if hojas:
            resumen += [("Gráficas incluidas", ", ".join(h[0] for h in hojas))]
        cuerpo = exportar.a_xlsx(df_datos, hojas, resumen)
        tipo, ext = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    base_nombre = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", a["nombre"])
    nombre = exportar.nombre_archivo(f"{base_nombre}_{nombre_vista}" if nombre_vista else base_nombre, ext)
    return Response(content=cuerpo, media_type=tipo, headers={
        "Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store",
        "X-Filas-Exportadas": str(min(n_filas, exportar.MAX_FILAS_CSV if datos.formato == "csv" else exportar.MAX_FILAS_XLSX)),
        "X-Exportacion-Truncada": "1" if truncada else "0"})
