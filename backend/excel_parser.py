"""
Parser de reportes de producción SMT.

Flujo:
  Sheet1 (raw) → bloques por ProductID2+Date → cálculo de horas y tiempo muerto → reporte final

Lógica de bloques:
  - Cada vez que cambia ProductID2 o Date = nuevo bloque
  - Horas del bloque = último DateTime - primer DateTime del bloque
  - Si hay registros Failed dentro del bloque:
      · Tiempo muerto = último DateTime(Failed) - primer DateTime(Failed) en ese bloque
      · Horas reales = horas totales - tiempo muerto
  - Bloques del mismo ProductID2 en el mismo Date se SUMAN al final
"""

import pandas as pd
import io
from datetime import timedelta


# ---------------------------------------------------------------------------
# Lectura y limpieza
# ---------------------------------------------------------------------------

def leer_excel(file_bytes: bytes) -> pd.DataFrame:
    """Lee la primera hoja del Excel soportando formatos .xlsx y .xls."""
    buffer = io.BytesIO(file_bytes)
    errores = []

    for engine in (None, "openpyxl", "xlrd"):
        try:
            buffer.seek(0)
            xl = pd.ExcelFile(buffer, engine=engine) if engine else pd.ExcelFile(buffer)
            hoja = xl.sheet_names[0]
            df = xl.parse(hoja, header=0)
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as exc:
            nombre_engine = engine or "auto"
            errores.append(f"{nombre_engine}: {exc}")

    raise ValueError(
        "No se pudo leer el archivo Excel. Verifica que no esté dañado y que sea .xlsx o .xls válido. "
        f"Detalle: {' | '.join(errores)}"
    )


def limpiar_datos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza columnas clave y descarta filas sin DateTime."""

    def serie_columna(dataframe: pd.DataFrame, nombre: str) -> pd.Series:
        col = dataframe[nombre]
        if isinstance(col, pd.DataFrame):
            return col.iloc[:, 0]
        return col

    def deduplicar_columnas(dataframe: pd.DataFrame) -> pd.DataFrame:
        if not dataframe.columns.duplicated().any():
            return dataframe
        nuevas = []
        vistos = {}
        for col in dataframe.columns:
            rep = vistos.get(col, 0)
            nuevas.append(col if rep == 0 else f"{col}__dup{rep}")
            vistos[col] = rep + 1
        dataframe.columns = nuevas
        return dataframe

    # Buscar columnas por nombre aproximado (tolerante a mayúsculas/espacios)
    col_map = {}
    for col in df.columns:
        c = col.lower().replace(" ", "").replace("_", "")
        if c == "datetime":
            col_map["DateTime"] = col
        elif c in ("productid2",):
            col_map["ProductID2"] = col
        elif c in ("result", "result(failedorpassed)"):
            col_map["Result"] = col
        elif c == "date" or c == "date-1":
            if "Date" not in col_map:          # tomar el primer match
                col_map["Date"] = col
        elif c == "fecha3":
            col_map["Fecha3"] = col
        elif c == "fecha2":
            if "Fecha3" not in col_map:
                col_map["Fecha3"] = col
        elif c == "equipment":
            col_map["Equipment"] = col
        elif c == "shift":
            if "Shift" not in col_map:
                col_map["Shift"] = col

    # Renombrar a nombres canónicos
    df = df.rename(columns={v: k for k, v in col_map.items()})
    df = deduplicar_columnas(df)

    # DateTime como timestamp
    if "DateTime" in df.columns:
        df["DateTime"] = pd.to_datetime(serie_columna(df, "DateTime"), errors="coerce")
    else:
        raise ValueError("No se encontró la columna DateTime en el archivo.")

    # Usar Fecha3 como Date si existe, si no usar Date
    if "Fecha3" in df.columns:
        df["Date"] = pd.to_datetime(serie_columna(df, "Fecha3").astype(str), errors="coerce").dt.date
    elif "Date" in df.columns:
        df["Date"] = pd.to_datetime(serie_columna(df, "Date"), errors="coerce").dt.date
    else:
        df["Date"] = df["DateTime"].dt.date

    if "ProductID2" not in df.columns:
        raise ValueError("No se encontró la columna ProductID2 en el archivo.")

    if "Result" not in df.columns:
        df["Result"] = "Passed"

    # Limpiar
    df = df.dropna(subset=["DateTime", "ProductID2"])
    df["ProductID2"] = serie_columna(df, "ProductID2").astype(str).str.strip()
    df["Result"] = serie_columna(df, "Result").astype(str).str.strip().str.capitalize()
    df = df.sort_values("DateTime").reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Detección de bloques
# ---------------------------------------------------------------------------

def asignar_bloques(df: pd.DataFrame) -> pd.DataFrame:
    """
    Asigna un número de bloque cada vez que cambia ProductID2 o Date.
    Registros consecutivos del mismo modelo en el mismo día = mismo bloque.
    """
    cambia = (
        (df["ProductID2"] != df["ProductID2"].shift()) |
        (df["Date"] != df["Date"].shift())
    )
    df["bloque_id"] = cambia.cumsum()
    return df


# ---------------------------------------------------------------------------
# Cálculo por bloque
# ---------------------------------------------------------------------------

def calcular_bloques(df: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada bloque calcula:
      - horas_totales : duración total (último - primer DateTime)
      - horas_muertas : duración de los registros Failed (último_fail - primer_fail)
      - horas_reales  : horas_totales - horas_muertas
      - qty_passed    : conteo de Passed
      - qty_failed    : conteo de Failed
    """
    resultados = []

    for bloque_id, grupo in df.groupby("bloque_id", sort=False):
        producto  = grupo["ProductID2"].iloc[0]
        fecha     = grupo["Date"].iloc[0]
        equipo    = grupo.get("Equipment", pd.Series([""])).iloc[0] if "Equipment" in grupo.columns else ""
        turno     = grupo.get("Shift", pd.Series([""])).iloc[0]     if "Shift"     in grupo.columns else ""

        dt_min = grupo["DateTime"].min()
        dt_max = grupo["DateTime"].max()
        horas_totales = (dt_max - dt_min).total_seconds() / 3600

        passed = grupo[grupo["Result"] == "Passed"]
        failed = grupo[grupo["Result"] == "Failed"]

        qty_passed = len(passed)
        qty_failed = len(failed)

        # Tiempo muerto = duración del span de fallas dentro del bloque
        if len(failed) >= 2:
            horas_muertas = (failed["DateTime"].max() - failed["DateTime"].min()).total_seconds() / 3600
        elif len(failed) == 1:
            # Un solo registro failed: contamos 0 duración (punto en el tiempo)
            horas_muertas = 0.0
        else:
            horas_muertas = 0.0

        horas_reales = max(horas_totales - horas_muertas, 0.0)

        resultados.append({
            "Date":          fecha,
            "Equipment":     equipo,
            "Shift":         turno,
            "ProductID":     producto,
            "bloque_id":     bloque_id,
            "dt_inicio":     dt_min,
            "dt_fin":        dt_max,
            "horas_totales": round(horas_totales, 4),
            "horas_muertas": round(horas_muertas, 4),
            "horas_reales":  round(horas_reales,  4),
            "qty_passed":    qty_passed,
            "qty_failed":    qty_failed,
        })

    return pd.DataFrame(resultados)


# ---------------------------------------------------------------------------
# Reporte final — agrupa bloques del mismo modelo en el mismo día
# ---------------------------------------------------------------------------

def consolidar_reporte(bloques: pd.DataFrame) -> pd.DataFrame:
    """
    Suma bloques del mismo ProductID + Date (un modelo puede correr
    varias veces en el mismo día en distintos intervalos).
    """
    reporte = (
        bloques
        .groupby(["Date", "Equipment", "ProductID"], as_index=False)
        .agg(
            horas_totales=("horas_totales", "sum"),
            horas_muertas=("horas_muertas", "sum"),
            horas_reales =("horas_reales",  "sum"),
            qty_passed   =("qty_passed",    "sum"),
            qty_failed   =("qty_failed",    "sum"),
            corridas      =("bloque_id",    "count"),   # cuántas veces corrió
        )
        .sort_values(["Date", "ProductID"])
        .reset_index(drop=True)
    )
    reporte["rendimiento_%"] = (
        reporte["horas_reales"] / reporte["horas_totales"].replace(0, float("nan")) * 100
    ).round(1)

    return reporte


# ---------------------------------------------------------------------------
# Exportar Excel de reporte
# ---------------------------------------------------------------------------

def exportar_excel(reporte: pd.DataFrame, bloques: pd.DataFrame) -> bytes:
    """
    Genera un Excel con 2 hojas:
      - Resumen : reporte consolidado por día/modelo
      - Detalle : bloques individuales con timestamps
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        wb = writer.book

        # --- Formatos ---
        fmt_header = wb.add_format({
            "bold": True, "bg_color": "#185FA5", "font_color": "#FFFFFF",
            "border": 1, "align": "center", "valign": "vcenter",
            "font_name": "Arial", "font_size": 10,
        })
        fmt_date = wb.add_format({"num_format": "dd/mm/yyyy", "font_name": "Arial", "font_size": 10})
        fmt_num  = wb.add_format({"num_format": "#,##0",      "font_name": "Arial", "font_size": 10})
        fmt_dec  = wb.add_format({"num_format": "0.000",      "font_name": "Arial", "font_size": 10})
        fmt_pct  = wb.add_format({"num_format": "0.0\"%\"",   "font_name": "Arial", "font_size": 10})
        fmt_cell = wb.add_format({"font_name": "Arial", "font_size": 10})

        # ---- Hoja Resumen ----
        cols_resumen = {
            "Date":           ("Fecha de Produccion",     18, fmt_date),
            "ProductionLine": ("Linea de Produccion",     18, fmt_cell),
            "Equipment":      ("Equipo SMT",              14, fmt_cell),
            "ProductID":      ("Codigo de Ensamble",      28, fmt_cell),
            "corridas":       ("Corridas de Produccion",  20, fmt_num),
            "qty_passed":     ("Piezas Conformes",        16, fmt_num),
            "qty_failed":     ("Piezas No Conformes",     18, fmt_num),
            "horas_totales":  ("Tiempo de Ciclo (h)",     18, fmt_dec),
            "horas_muertas":  ("Tiempo de Paro (h)",      18, fmt_dec),
            "horas_reales":   ("Tiempo Efectivo (h)",     18, fmt_dec),
            "rendimiento_%":  ("Eficiencia Operativa (%)", 22, fmt_pct),
        }

        resumen_export = reporte[[c for c in cols_resumen if c in reporte.columns]].copy()
        resumen_export.to_excel(writer, sheet_name="Resumen", index=False, startrow=1)
        ws_res = writer.sheets["Resumen"]

        for i, (col_key, (header, width, _)) in enumerate(cols_resumen.items()):
            ws_res.write(0, i, header, fmt_header)
            ws_res.set_column(i, i, width)

        # Aplicar formatos por columna
        for row_idx in range(len(resumen_export)):
            for col_idx, (col_key, (_, _, fmt)) in enumerate(cols_resumen.items()):
                if col_key in resumen_export.columns:
                    val = resumen_export.iloc[row_idx][col_key]
                    ws_res.write(row_idx + 2, col_idx, val, fmt)

        ws_res.freeze_panes(2, 0)
        ws_res.autofilter(1, 0, len(resumen_export) + 1, len(cols_resumen) - 1)

        # ---- Hoja Detalle (bloques) ----
        fmt_dt = wb.add_format({"num_format": "dd/mm/yyyy hh:mm:ss", "font_name": "Arial", "font_size": 10})

        cols_detalle = {
            "Date":           ("Fecha de Produccion",     18, fmt_date),
            "ProductionLine": ("Linea de Produccion",     18, fmt_cell),
            "Equipment":      ("Equipo SMT",              14, fmt_cell),
            "ProductID":      ("Codigo de Ensamble",      28, fmt_cell),
            "bloque_id":      ("Lote de Corrida",         14, fmt_num),
            "dt_inicio":      ("Inicio de Corrida",       20, fmt_dt),
            "dt_fin":         ("Fin de Corrida",          20, fmt_dt),
            "horas_totales":  ("Tiempo de Ciclo (h)",     18, fmt_dec),
            "horas_muertas":  ("Tiempo de Paro (h)",      18, fmt_dec),
            "horas_reales":   ("Tiempo Efectivo (h)",     18, fmt_dec),
            "qty_passed":     ("Piezas Conformes",        16, fmt_num),
            "qty_failed":     ("Piezas No Conformes",     18, fmt_num),
        }

        detalle_export = bloques[[c for c in cols_detalle if c in bloques.columns]].copy()
        detalle_export.to_excel(writer, sheet_name="Detalle Bloques", index=False, startrow=1)
        ws_det = writer.sheets["Detalle Bloques"]

        for i, (col_key, (header, width, _)) in enumerate(cols_detalle.items()):
            ws_det.write(0, i, header, fmt_header)
            ws_det.set_column(i, i, width)

        for row_idx in range(len(detalle_export)):
            for col_idx, (col_key, (_, _, fmt)) in enumerate(cols_detalle.items()):
                if col_key in detalle_export.columns:
                    val = detalle_export.iloc[row_idx][col_key]
                    ws_det.write(row_idx + 2, col_idx, val, fmt)

        ws_det.freeze_panes(2, 0)
        ws_det.autofilter(1, 0, len(detalle_export) + 1, len(cols_detalle) - 1)

    return output.getvalue()


# ---------------------------------------------------------------------------
# Función principal — entrada pública
# ---------------------------------------------------------------------------

def procesar_excel(file_bytes: bytes, linea: str = "") -> dict:
    """
    Recibe el Excel crudo y devuelve:
      - reporte   : DataFrame consolidado (para dashboard)
      - bloques   : DataFrame de bloques individuales
      - excel_out : bytes del Excel de descarga
      - resumen   : métricas globales del archivo
    """
    df       = leer_excel(file_bytes)
    df       = limpiar_datos(df)
    df       = asignar_bloques(df)
    bloques  = calcular_bloques(df)
    reporte  = consolidar_reporte(bloques)
    if linea:
        bloques["ProductionLine"] = linea
        reporte["ProductionLine"] = linea
    excel_out = exportar_excel(reporte, bloques)

    resumen = {
        "total_registros": len(df),
        "total_passed":    int((df["Result"] == "Passed").sum()),
        "total_failed":    int((df["Result"] == "Failed").sum()),
        "horas_totales":   round(float(reporte["horas_totales"].sum()), 3),
        "horas_muertas":   round(float(reporte["horas_muertas"].sum()), 3),
        "horas_reales":    round(float(reporte["horas_reales"].sum()),  3),
        "modelos":         int(reporte["ProductID"].nunique()),
        "fechas":          sorted([str(d) for d in reporte["Date"].unique()]),
        "linea_produccion": linea,
    }

    return {
        "reporte":    reporte,
        "bloques":    bloques,
        "excel_out":  excel_out,
        "resumen":    resumen,
    }
