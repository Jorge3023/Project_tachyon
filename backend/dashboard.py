"""Motor de dashboards sobre datasets genéricos.

El cliente nunca manda filas ni fórmulas: manda una *configuración* (lista de gráficas + filtros) que aquí se
valida contra el esquema del dataset (nombres de columna y roles reales, agregaciones en lista blanca, límites)
y se calcula en el servidor con pandas. El navegador solo recibe los resultados ya agregados.

Configuración (JSON):
    {"grano": "auto|dia|semana|mes|trimestre|anio",
     "filtros": [<filtro>],
     "widgets": [{"id", "tipo", "titulo", "ancho", "x", "y", "medida", "agg", "serie", ...}]}
Filtro: {"col", "desde"/"hasta" (fecha) | "min"/"max" (número) | "valores" (categoría)}
"""
import math
import re
import unicodedata

import numpy as np
import pandas as pd

TIPOS = ("kpi", "linea", "area", "barras", "dona", "dispersion", "histograma", "calor", "pareto", "tabla", "mapa")
AGGS = ("suma", "promedio", "conteo", "min", "max", "mediana", "unicos")
AGGS_REPARTO = ("suma", "conteo", "unicos")          # las que tienen sentido como "parte de un total"
GRANOS = ("auto", "dia", "semana", "mes", "trimestre", "anio")
ANCHOS = (3, 4, 6, 8, 12)
MAX_WIDGETS = 24
MAX_FILTROS = 8
MAX_VALORES_FILTRO = 200
MAX_PUNTOS_DISPERSION = 1500
MAX_PUNTOS_MAPA = 800
MAX_BUCKETS = 3000
SERIES_MAX = 6

R_FECHA = ("fecha",)
R_DIM = ("categoria", "estado", "identificador")
R_NUM = ("numero",)
ETIQUETA_TIPO = {"kpi": "Indicador", "linea": "Líneas", "area": "Área", "barras": "Barras", "dona": "Circular",
                 "dispersion": "Dispersión", "histograma": "Histograma", "calor": "Mapa de calor",
                 "pareto": "Pareto", "tabla": "Tabla", "mapa": "Mapa geográfico"}


class ConfigInvalida(ValueError):
    pass


# ── Validación ────────────────────────────────────────────────────────────────────────────────────
def _roles(esquema):
    return {c["nombre"]: c["rol"] for c in esquema if c.get("rol") != "ignorar"}


def _col(w, campo, roles, permitidos, obligatorio=False, etiqueta=None):
    v = w.get(campo)
    if v in (None, ""):
        if obligatorio:
            raise ConfigInvalida(f"Falta elegir {etiqueta or campo}")
        return None
    if not isinstance(v, str) or v not in roles:
        raise ConfigInvalida(f"La columna «{str(v)[:40]}» no existe en este archivo")
    if roles[v] not in permitidos:
        raise ConfigInvalida(f"«{v}» es de tipo {roles[v]} y aquí no se puede usar como {etiqueta or campo}")
    return v


def _entero(v, defecto, minimo, maximo):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return defecto
    return max(minimo, min(maximo, n))


def _fecha_iso(v):
    if v in (None, ""):
        return None
    try:
        return pd.Timestamp(str(v)[:10]).strftime("%Y-%m-%d")
    except Exception:
        raise ConfigInvalida("Fecha no válida en un filtro")


def _numero(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ConfigInvalida("Número no válido en un filtro")
    if not math.isfinite(f):
        raise ConfigInvalida("Número no válido en un filtro")
    return f


def limpiar_filtros(filtros, roles):
    if filtros in (None, ""):
        return []
    if not isinstance(filtros, list) or len(filtros) > MAX_FILTROS:
        raise ConfigInvalida(f"Máximo {MAX_FILTROS} filtros")
    out = []
    for f in filtros:
        if not isinstance(f, dict):
            raise ConfigInvalida("Filtro no válido")
        col = f.get("col")
        if col not in roles:
            raise ConfigInvalida(f"Filtro sobre una columna que no existe: «{str(col)[:40]}»")
        rol = roles[col]
        if rol == "fecha":
            d, h = _fecha_iso(f.get("desde")), _fecha_iso(f.get("hasta"))
            if d or h:
                out.append({"col": col, "desde": d, "hasta": h})
        elif rol == "numero":
            lo, hi = _numero(f.get("min")), _numero(f.get("max"))
            if lo is not None or hi is not None:
                out.append({"col": col, "min": lo, "max": hi})
        else:
            vals = f.get("valores")
            if not isinstance(vals, list):
                raise ConfigInvalida("Los valores de un filtro deben ser una lista")
            vals = [str(v)[:120] for v in vals[:MAX_VALORES_FILTRO]]
            if vals:
                out.append({"col": col, "valores": vals})
    return out


def _widget(w, roles, i, ids_usados):
    if not isinstance(w, dict):
        raise ConfigInvalida("Gráfica no válida")
    tipo = w.get("tipo")
    if tipo not in TIPOS:
        raise ConfigInvalida(f"Tipo de gráfica no válido: {str(tipo)[:30]}")
    wid = re.sub(r"[^A-Za-z0-9_-]", "", str(w.get("id") or ""))[:24] or f"w{i + 1}"
    while wid in ids_usados:
        wid += "x"
    ids_usados.add(wid)
    out = {"id": wid, "tipo": tipo, "titulo": " ".join(str(w.get("titulo") or "").split())[:80],
           "ancho": w.get("ancho") if w.get("ancho") in ANCHOS else (3 if tipo == "kpi" else 6)}
    color = w.get("color")
    out["color"] = color if isinstance(color, int) and not isinstance(color, bool) and 0 <= color <= 7 else None
    out["filtros"] = limpiar_filtros(w.get("filtros"), roles)
    grano = w.get("grano", "auto")
    out["grano"] = grano if grano in GRANOS else "auto"

    def agg(permitidas=AGGS, defecto="suma"):
        a = w.get("agg") or defecto
        if a not in permitidas:
            raise ConfigInvalida(f"Agregación no permitida aquí: {str(a)[:20]}")
        return a

    if tipo == "kpi":
        out["medida"] = _col(w, "medida", roles, R_NUM, etiqueta="la métrica")
        out["agg"] = agg(defecto="suma") if out["medida"] else "conteo"
        out["x"] = _col(w, "x", roles, R_FECHA, etiqueta="la fecha de comparación")
    elif tipo in ("linea", "area"):
        out["x"] = _col(w, "x", roles, R_FECHA + ("categoria", "estado"), True, "el eje X")
        out["medida"] = _col(w, "medida", roles, R_NUM, etiqueta="la métrica")
        out["agg"] = agg() if out["medida"] else "conteo"
        out["serie"] = _col(w, "serie", roles, ("categoria", "estado"), etiqueta="la serie")
    elif tipo == "barras":
        out["x"] = _col(w, "x", roles, R_FECHA + R_DIM, True, "el eje X")
        out["medida"] = _col(w, "medida", roles, R_NUM, etiqueta="la métrica")
        out["agg"] = agg() if out["medida"] else "conteo"
        out["serie"] = _col(w, "serie", roles, ("categoria", "estado"), etiqueta="la serie")
        out["apilado"] = bool(w.get("apilado"))
        out["orientacion"] = "h" if w.get("orientacion") == "h" else "v"
        out["top"] = _entero(w.get("top"), 10, 1, 50)
        out["orden"] = w.get("orden") if w.get("orden") in ("desc", "asc", "natural") else "desc"
    elif tipo in ("dona", "pareto"):
        out["x"] = _col(w, "x", roles, R_DIM, True, "la categoría")
        out["medida"] = _col(w, "medida", roles, R_NUM, etiqueta="la métrica")
        out["agg"] = agg(AGGS_REPARTO) if out["medida"] else "conteo"
        out["top"] = _entero(w.get("top"), 6 if tipo == "dona" else 10, 2 if tipo == "dona" else 3,
                             12 if tipo == "dona" else 30)
    elif tipo == "dispersion":
        out["x"] = _col(w, "x", roles, R_NUM, True, "el eje X")
        out["y"] = _col(w, "y", roles, R_NUM, True, "el eje Y")
        out["serie"] = _col(w, "serie", roles, ("categoria", "estado"), etiqueta="la serie")
    elif tipo == "histograma":
        out["x"] = _col(w, "x", roles, R_NUM, True, "la columna")
        out["bins"] = _entero(w.get("bins"), 0, 0, 60)           # 0 = automático
    elif tipo == "calor":
        out["x"] = _col(w, "x", roles, R_FECHA + R_DIM, True, "el eje X")
        out["y"] = _col(w, "y", roles, R_DIM, True, "el eje Y")
        if out["x"] == out["y"]:
            raise ConfigInvalida("El mapa de calor necesita dos columnas distintas")
        out["medida"] = _col(w, "medida", roles, R_NUM, etiqueta="la métrica")
        out["agg"] = agg() if out["medida"] else "conteo"
        out["top"] = _entero(w.get("top"), 10, 2, 15)
    elif tipo == "mapa":
        out["lat"] = _col(w, "lat", roles, R_NUM, True, "la latitud")
        out["lon"] = _col(w, "lon", roles, R_NUM, True, "la longitud")
        if out["lat"] == out["lon"]:
            raise ConfigInvalida("El mapa necesita dos columnas distintas (latitud y longitud)")
        out["medida"] = _col(w, "medida", roles, R_NUM, etiqueta="la métrica")
        out["agg"] = agg() if out["medida"] else "conteo"
        out["serie"] = _col(w, "serie", roles, ("categoria", "estado"), etiqueta="el color por categoría")
    elif tipo == "tabla":
        cols = w.get("columnas")
        if not isinstance(cols, list) or not cols:
            cols = list(roles)[:6]
        cols = [c for c in cols if isinstance(c, str)]
        if any(c not in roles for c in cols):
            raise ConfigInvalida("La tabla usa una columna que no existe")
        out["columnas"] = cols[:10]
        out["filas"] = _entero(w.get("filas"), 10, 1, 50)
        orden = w.get("orden")
        out["orden"] = orden if orden in roles else None
        out["dir"] = "asc" if w.get("dir") == "asc" else "desc"
    return out


def limpiar_config(config, esquema):
    """Devuelve la configuración saneada (solo claves conocidas) o lanza ConfigInvalida."""
    if not isinstance(config, dict):
        raise ConfigInvalida("Configuración no válida")
    roles = _roles(esquema)
    widgets = config.get("widgets", [])
    if not isinstance(widgets, list) or len(widgets) > MAX_WIDGETS:
        raise ConfigInvalida(f"Máximo {MAX_WIDGETS} gráficas por vista")
    ids = set()
    grano = config.get("grano", "auto")
    return {"v": 1, "grano": grano if grano in GRANOS else "auto",
            "filtros": limpiar_filtros(config.get("filtros"), roles),
            "widgets": [_widget(w, roles, i, ids) for i, w in enumerate(widgets)]}


def columnas_usadas(config):
    cols = set()
    for f in config["filtros"]:
        cols.add(f["col"])
    for w in config["widgets"]:
        for f in w["filtros"]:
            cols.add(f["col"])
        for campo in ("x", "y", "lat", "lon", "medida", "serie", "orden"):
            if w.get(campo):
                cols.add(w[campo])
        cols.update(w.get("columnas", []))
    return sorted(cols)


# ── Cálculo ───────────────────────────────────────────────────────────────────────────────────────
def _n(v, dec=6):
    """float JSON-seguro (NaN/inf → None)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else round(f, dec)


def _py(v):
    """Valor de celda a tipo JSON."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute, v.second) == (0, 0, 0) else v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return _n(v)
    if v is pd.NaT:
        return None
    return v if isinstance(v, (int, bool, str)) else str(v)


def aplicar_filtros(df, filtros, roles):
    if not filtros:
        return df
    mask = pd.Series(True, index=df.index)
    for f in filtros:
        s = df[f["col"]]
        rol = roles[f["col"]]
        if rol == "fecha":
            if f.get("desde"):
                mask &= s >= pd.Timestamp(f["desde"])
            if f.get("hasta"):
                mask &= s < pd.Timestamp(f["hasta"]) + pd.Timedelta(days=1)
        elif rol == "numero":
            if f.get("min") is not None:
                mask &= s >= f["min"]
            if f.get("max") is not None:
                mask &= s <= f["max"]
        else:
            mask &= s.notna() & s.astype(str).isin(f["valores"])
    return df[mask]


def _grano_auto(s):
    s = s.dropna()
    if s.empty:
        return "mes"
    dias = (s.max() - s.min()).days
    return "dia" if dias <= 45 else "semana" if dias <= 180 else "mes" if dias <= 1460 else "anio"


def _clave_fecha(s, grano):
    if grano == "dia":
        return s.dt.strftime("%Y-%m-%d")
    if grano == "semana":
        return (s.dt.normalize() - pd.to_timedelta(s.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")
    if grano == "trimestre":
        return s.dt.year.astype("Int64").astype(str) + "-T" + s.dt.quarter.astype("Int64").astype(str)
    if grano == "anio":
        return s.dt.strftime("%Y")
    return s.dt.strftime("%Y-%m")


def _etiquetas_completas(minimo, maximo, grano):
    """Todas las etiquetas de periodo entre dos fechas (para no esconder periodos sin datos)."""
    if grano == "dia":
        r = pd.date_range(minimo.normalize(), maximo.normalize(), freq="D"); f = "%Y-%m-%d"
    elif grano == "semana":
        ini = minimo.normalize() - pd.Timedelta(days=minimo.weekday())
        fin = maximo.normalize() - pd.Timedelta(days=maximo.weekday())
        r = pd.date_range(ini, fin, freq="7D"); f = "%Y-%m-%d"
    elif grano == "trimestre":
        r = pd.period_range(minimo, maximo, freq="Q")
        return [f"{p.year}-T{p.quarter}" for p in r]
    elif grano == "anio":
        r = pd.date_range(f"{minimo.year}-01-01", f"{maximo.year}-01-01", freq="YS"); f = "%Y"
    else:
        r = pd.date_range(minimo.replace(day=1).normalize(), maximo.replace(day=1).normalize(), freq="MS"); f = "%Y-%m"
    return [d.strftime(f) for d in r]


def _clave(df, col, roles, grano_global, grano_w):
    """(Serie de claves de texto, etiquetas completas en orden cronológico o None)."""
    if roles[col] == "fecha":
        s = df[col]
        grano = grano_w if grano_w != "auto" else (grano_global if grano_global != "auto" else _grano_auto(s))
        claves = _clave_fecha(s, grano)
        claves = claves.where(s.notna())
        completas = None
        v = s.dropna()
        if not v.empty:
            completas = _etiquetas_completas(v.min(), v.max(), grano)
            if len(completas) > MAX_BUCKETS:
                raise ConfigInvalida("Demasiados periodos: elige una granularidad más amplia (semana, mes…)")
        return claves, completas, grano
    return df[col].astype("string").where(df[col].notna()), None, None


def _agregar(df, claves, medida, agg):
    """Serie agregada por las claves (lista de Series alineadas con df)."""
    d = pd.DataFrame({f"k{i}": k for i, k in enumerate(claves)})
    nombres = list(d.columns)
    if medida is not None:
        d["_m"] = df[medida].values
    d = d.dropna(subset=nombres)
    if d.empty:
        return pd.Series(dtype="float64")
    g = d.groupby(nombres, sort=True, observed=True)
    if agg == "conteo" or medida is None:
        return g.size().astype("float64")
    m = g["_m"]
    return {"suma": m.sum, "promedio": m.mean, "min": m.min, "max": m.max, "mediana": m.median,
            "unicos": m.nunique}[agg]().astype("float64")


def _valor_total(df, medida, agg):
    if agg == "conteo" or medida is None:
        return float(len(df))
    s = df[medida].dropna()
    if s.empty:
        return None
    return float({"suma": s.sum, "promedio": s.mean, "min": s.min, "max": s.max, "mediana": s.median,
                  "unicos": s.nunique}[agg]())


def _top_con_otros(claves, n, otros="Otros"):
    """Serie de claves donde las menos frecuentes (más allá de n) pasan a 'Otros'."""
    cuenta = claves.value_counts()
    if len(cuenta) <= n:
        return claves, False
    mantener = set(cuenta.head(n).index)
    return claves.where(claves.isin(mantener) | claves.isna(), otros), True


_FREC_PERIODO = {"semana": "W-SUN", "mes": "M", "trimestre": "Q", "anio": "Y"}


def _periodo_incompleto(s, grano):
    """True si la última fecha de los datos cae antes del final de su periodo (periodo en curso)."""
    f = _FREC_PERIODO.get(grano)
    v = s.dropna()
    if f is None or v.empty:
        return False
    ultimo = v.max()
    return ultimo.normalize() < pd.Period(ultimo, freq=f).end_time.normalize()


def _calc_kpi(df, w, roles, gg):
    valor = _valor_total(df, w["medida"], w["agg"])
    delta = None
    if w.get("x") and len(df):
        clave, completas, grano = _clave(df, w["x"], roles, gg, w["grano"])
        ser = _agregar(df, [clave], w["medida"], w["agg"])
        if completas:
            ser = ser.reindex(completas)
        acumula = w["agg"] in ("suma", "conteo", "unicos")
        ser = ser.fillna(0) if acumula else ser.dropna()
        # Si el último periodo aún no termina (p. ej. el mes en curso), una suma/conteo parcial
        # saldría siempre "a la baja": se compara el último periodo COMPLETO contra el anterior.
        parcial = None
        if acumula and grano and len(ser) >= 3 and _periodo_incompleto(df[w["x"]], grano):
            parcial = str(ser.index[-1])
            ser = ser.iloc[:-1]
        if len(ser) >= 2:
            act, ant = float(ser.iloc[-1]), float(ser.iloc[-2])
            delta = {"pct": _n((act - ant) / abs(ant) * 100, 2) if ant else None,
                     "actual": str(ser.index[-1]), "anterior": str(ser.index[-2]), "grano": grano}
            if parcial:
                delta["excluido"] = parcial
    return {"valor": _n(valor), "delta": delta}


def _calc_serie_cat(df, w, roles, gg):
    """líneas / área / barras: categorías en X y una o varias series."""
    x, medida, agg = w["x"], w["medida"], w["agg"]
    claves, completas, grano = _clave(df, x, roles, gg, w["grano"])
    es_tiempo = roles[x] == "fecha"
    adv = None
    serie_col = w.get("serie")
    if serie_col:
        sk, recortado = _top_con_otros(df[serie_col].astype("string").where(df[serie_col].notna()), SERIES_MAX)
        ser = _agregar(df, [claves, sk], medida, agg)
        if ser.empty:
            return {"categorias": [], "series": [], "grano": grano}
        tabla = ser.unstack(level=1)
        if recortado:
            adv = f"Se muestran las {SERIES_MAX} series principales; el resto va en «Otros»."
        nombres = list(tabla.columns)
        total = _agregar(df, [claves], medida, agg)
    else:
        ser = _agregar(df, [claves], medida, agg)
        tabla = ser.to_frame(name=w["titulo"] or "Valor") if len(ser) else pd.DataFrame()
        nombres = list(tabla.columns)
        total = ser
    if tabla.empty:
        return {"categorias": [], "series": [], "grano": grano}
    relleno = 0.0 if agg in ("suma", "conteo", "unicos") else None
    if es_tiempo and completas:
        tabla = tabla.reindex(completas)
        if relleno is not None:
            tabla = tabla.fillna(relleno)
        orden_cat = completas
    elif w["tipo"] == "barras" and w.get("orden") != "natural":
        ordenado = total.sort_values(ascending=(w.get("orden") == "asc"), kind="stable")
        if not es_tiempo:
            if len(ordenado) > w["top"]:
                adv = f"Mostrando {w['top']} de {len(ordenado)} categorías."
            ordenado = ordenado.head(w["top"])
        orden_cat = list(ordenado.index)
        tabla = tabla.reindex(orden_cat)
    else:
        orden_cat = list(tabla.index)
        if w["tipo"] == "barras" and not es_tiempo and len(orden_cat) > w["top"]:
            orden_cat = orden_cat[:w["top"]]
            adv = f"Mostrando {w['top']} de {len(tabla)} categorías."
            tabla = tabla.reindex(orden_cat)
        elif w["tipo"] in ("linea", "area") and not es_tiempo and len(orden_cat) > 40:
            orden_cat = orden_cat[:40]; tabla = tabla.reindex(orden_cat)
            adv = "Mostrando las primeras 40 categorías."
    return {"categorias": [str(c) for c in orden_cat],
            "series": [{"nombre": str(n), "valores": [_n(v) for v in tabla[n].tolist()]} for n in nombres],
            "grano": grano, "advertencia": adv}


def _calc_reparto(df, w, roles, gg):
    """dona / pareto."""
    x = w["x"]
    claves = df[x].astype("string").where(df[x].notna())
    if w["tipo"] == "dona":
        claves, recortado = _top_con_otros(claves, w["top"])
    else:
        recortado = False
    ser = _agregar(df, [claves], w["medida"], w["agg"]).sort_values(ascending=False, kind="stable")
    if ser.empty:
        return {"total": 0, "partes": [] if w["tipo"] == "dona" else None, "categorias": []}
    total = float(ser.sum())
    if w["tipo"] == "dona":
        if "Otros" in ser.index:                       # "Otros" siempre al final
            ser = pd.concat([ser.drop("Otros"), ser[["Otros"]]])
        return {"total": _n(total), "partes": [
            {"nombre": str(k), "valor": _n(v), "pct": _n(v / total * 100, 2) if total else 0} for k, v in ser.items()],
            "advertencia": f"Se muestran las {w['top']} principales; el resto va en «Otros»." if recortado else None}
    top = ser.head(w["top"])
    acum = (top.cumsum() / total * 100) if total else top * 0
    return {"total": _n(total), "categorias": [str(c) for c in top.index], "valores": [_n(v) for v in top.tolist()],
            "acumulado": [_n(v, 2) for v in acum.tolist()],
            "advertencia": f"Mostrando {w['top']} de {len(ser)} categorías." if len(ser) > w["top"] else None}


def _calc_dispersion(df, w, roles, gg):
    cols = [w["x"], w["y"]] + ([w["serie"]] if w.get("serie") else [])
    d = df[cols].dropna(subset=[w["x"], w["y"]])
    total = len(d)
    if total < 1:
        return {"puntos": [], "series": [], "total": 0, "muestra": 0, "correlacion": None}
    r = None
    if total >= 3 and d[w["x"]].std() > 0 and d[w["y"]].std() > 0:
        r = _n(np.corrcoef(d[w["x"]].astype(float), d[w["y"]].astype(float))[0, 1], 3)
    if total > MAX_PUNTOS_DISPERSION:
        d = d.sample(MAX_PUNTOS_DISPERSION, random_state=7)
    nombres, idx = ["Todos"], np.zeros(len(d), dtype=int)
    if w.get("serie"):
        sk, _ = _top_con_otros(d[w["serie"]].astype("string").fillna("(vacío)"), 2)
        cat = pd.Categorical(sk)
        nombres, idx = [str(c) for c in cat.categories], cat.codes
    pts = [[_n(a, 4), _n(b, 4), int(s)] for a, b, s in zip(d[w["x"]], d[w["y"]], idx)]
    return {"puntos": pts, "series": nombres, "total": int(total), "muestra": len(d), "correlacion": r}


_AGG_PANDAS = {"suma": "sum", "promedio": "mean", "min": "min", "max": "max", "mediana": "median", "unicos": "nunique"}
_CELDAS_MAPA = (0.0001, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0)   # grados; ~11 m ... ~1100 km


def _calc_mapa(df, w, roles, gg):
    """Puntos sobre un mapa. Si hay demasiados, se agrupan en una cuadrícula cada vez más gruesa (máx. MAX_PUNTOS_MAPA)."""
    la, lo, med, ser = w["lat"], w["lon"], w.get("medida"), w.get("serie")
    cols = list(dict.fromkeys([la, lo] + ([med] if med else []) + ([ser] if ser else [])))
    d = df[cols].dropna(subset=[la, lo])
    d = d.assign(**{la: d[la].astype(float), lo: d[lo].astype(float)})
    ok = d[la].between(-90, 90) & d[lo].between(-180, 180)
    fuera = int((~ok).sum())
    d = d[ok]
    if d.empty:
        return {"puntos": [], "series": [], "total": 0, "fuera": fuera,
                "advertencia": (f"{fuera} filas tienen coordenadas fuera de rango (latitud ±90, longitud ±180)" if fuera else None)}
    # color por categoría (las menos frecuentes pasan a «Otros»)
    nombres, cod = [], None
    if ser:
        sk, _ = _top_con_otros(d[ser].astype("string").fillna("(vacío)"), SERIES_MAX)
        cat = pd.Categorical(sk)
        nombres, cod = [str(c) for c in cat.categories], pd.Series(cat.codes, index=d.index)
    # celda más fina con la que no se pasa del máximo de puntos
    celda = _CELDAS_MAPA[-1]
    for c in _CELDAS_MAPA:
        kl, ko = np.round(d[la] / c).astype("int64"), np.round(d[lo] / c).astype("int64")
        if len(pd.MultiIndex.from_arrays([kl, ko]).unique()) <= MAX_PUNTOS_MAPA:
            celda = c
            break
    kl, ko = np.round(d[la] / celda).astype("int64"), np.round(d[lo] / celda).astype("int64")
    g = d.groupby([kl.rename("_a"), ko.rename("_b")], sort=False)
    n = g.size()
    out = pd.DataFrame({"lat": g[la].mean(), "lon": g[lo].mean(), "n": n})
    if med and w["agg"] != "conteo":
        out["valor"] = getattr(g[med], _AGG_PANDAS[w["agg"]])()
    else:
        out["valor"] = n
    if cod is not None:
        out["cat"] = cod.groupby([kl, ko], sort=False).agg(lambda s: int(s.mode().iat[0]))
    out = out.sort_values("valor", ascending=False, kind="stable")      # los grandes primero (se dibujan al fondo)
    pts = [[_n(r.lat, 5), _n(r.lon, 5), _n(r.valor), int(r.n)] + ([int(r.cat)] if cod is not None else [])
           for r in out.itertuples(index=False)]
    avisos = []
    if len(d) > len(out):
        avisos.append(f"{len(d):,} filas en {len(out):,} puntos (las cercanas se agrupan)")
    if fuera:
        avisos.append(f"{fuera} filas con coordenadas fuera de rango no se muestran")
    return {"puntos": pts, "series": nombres, "total": int(len(d)), "fuera": fuera, "celda": celda,
            "agrupado": bool(len(d) > len(out)), "medida": med, "agg": w["agg"] if med else "conteo",
            "limites": [[_n(d[la].min(), 5), _n(d[lo].min(), 5)], [_n(d[la].max(), 5), _n(d[lo].max(), 5)]],
            "advertencia": " · ".join(avisos) if avisos else None}


def _calc_histograma(df, w, roles, gg):
    v = df[w["x"]].dropna().astype(float)
    if v.empty:
        return {"bins": [], "n": 0}
    bins = w["bins"] or int(min(30, max(6, math.ceil(math.log2(len(v)) + 1))))
    if v.min() == v.max():
        return {"bins": [{"desde": _n(v.min()), "hasta": _n(v.max()), "n": int(len(v))}], "n": int(len(v)),
                "media": _n(v.mean()), "mediana": _n(v.median())}
    cuentas, bordes = np.histogram(v, bins=bins)
    return {"bins": [{"desde": _n(bordes[i], 4), "hasta": _n(bordes[i + 1], 4), "n": int(cuentas[i])}
                     for i in range(len(cuentas))],
            "n": int(len(v)), "media": _n(v.mean()), "mediana": _n(v.median())}


def _calc_calor(df, w, roles, gg):
    cx, completas, grano = _clave(df, w["x"], roles, gg, w["grano"])
    cy = df[w["y"]].astype("string").where(df[w["y"]].notna())
    ser = _agregar(df, [cx, cy], w["medida"], w["agg"])
    if ser.empty:
        return {"filas": [], "columnas": [], "valores": []}
    tabla = ser.unstack(level=1)
    top = w["top"]
    peso = _agregar(df, [cy], None, "conteo")
    filas = list(peso.sort_values(ascending=False, kind="stable").head(top).index)
    if roles[w["x"]] == "fecha":
        cols = list(completas or tabla.index)[-24:]           # los últimos 24 periodos
    else:
        pesox = _agregar(df, [cx], None, "conteo")
        cols = list(pesox.sort_values(ascending=False, kind="stable").head(top).index)
    tabla = tabla.reindex(index=cols, columns=filas)
    vals = [[_n(tabla.iloc[i, j]) for i in range(len(cols))] for j in range(len(filas))]   # filas (Y) x columnas (X)
    planos = [v for fila in vals for v in fila if v is not None]
    return {"filas": [str(f) for f in filas], "columnas": [str(c) for c in cols], "valores": vals,
            "min": min(planos) if planos else None, "max": max(planos) if planos else None, "grano": grano}


def _calc_tabla(df, w, roles, gg):
    d = df
    if w.get("orden"):
        d = d.sort_values(w["orden"], ascending=(w["dir"] == "asc"), kind="stable", na_position="last")
    d = d.head(w["filas"])[w["columnas"]]
    return {"columnas": w["columnas"], "roles": [roles[c] for c in w["columnas"]],
            "filas": [[_py(v) for v in fila] for fila in d.itertuples(index=False, name=None)], "total": int(len(df))}


_CALC = {"kpi": _calc_kpi, "linea": _calc_serie_cat, "area": _calc_serie_cat, "barras": _calc_serie_cat,
         "dona": _calc_reparto, "pareto": _calc_reparto, "dispersion": _calc_dispersion,
         "histograma": _calc_histograma, "calor": _calc_calor, "tabla": _calc_tabla, "mapa": _calc_mapa}


def calcular(df, config, esquema):
    """Calcula todas las gráficas de una configuración ya saneada. Un error en una gráfica no tumba a las demás."""
    roles = _roles(esquema)
    base = aplicar_filtros(df, config["filtros"], roles)
    out = {}
    for w in config["widgets"]:
        try:
            d = aplicar_filtros(base, w["filtros"], roles)
            r = _CALC[w["tipo"]](d, w, roles, config["grano"])
            r.setdefault("n", int(len(d)))
            out[w["id"]] = r
        except ConfigInvalida as e:
            out[w["id"]] = {"error": str(e)}
        except Exception:
            out[w["id"]] = {"error": "No se pudo calcular esta gráfica con los datos actuales"}
    return {"widgets": out, "filas_filtradas": int(len(base)), "filas_total": int(len(df))}


# ── Valores para los filtros ────────────────────────────────────────────────────────────────────────
def valores_columna(serie, rol):
    s = serie.dropna()
    if rol == "numero":
        return {"tipo": "numero", "min": _n(s.min()) if len(s) else None, "max": _n(s.max()) if len(s) else None}
    if rol == "fecha":
        return {"tipo": "fecha", "min": s.min().strftime("%Y-%m-%d") if len(s) else None,
                "max": s.max().strftime("%Y-%m-%d") if len(s) else None}
    cuenta = s.astype(str).value_counts()
    return {"tipo": "categoria", "unicos": int(len(cuenta)),
            "valores": [{"valor": k, "n": int(v)} for k, v in cuenta.head(100).items()]}


# ── Sugerencia automática según los roles de las columnas ────────────────────────────────────────────
_NOMBRES_MEDIA = re.compile(r"(precio|promedio|tasa|porcentaje|%|ratio|edad|calif|score|temperatura|tiempo|ticket)", re.I)
# Qué columna numérica se toma como "la métrica principal": importes antes que cantidades, promedios al final
_PRIORIDAD = [re.compile(r"(importe|monto|venta|ingreso|revenue|sales|amount|total)", re.I),
              re.compile(r"(costo|cost|gasto|valor|pago)", re.I),
              re.compile(r"(cantidad|qty|unidades|piezas|volumen)", re.I)]


def _puntaje(nombre):
    if _NOMBRES_MEDIA.search(nombre):
        return len(_PRIORIDAD) + 1
    for i, rx in enumerate(_PRIORIDAD):
        if rx.search(nombre):
            return i
    return len(_PRIORIDAD)


_RX_LAT = re.compile(r"^(lat|latitud|latitude|latitu)$", re.I)
_RX_LON = re.compile(r"^(lon|lng|long|longitud|longitude)$", re.I)


def _norm_geo(nombre):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", str(nombre).lower()).encode("ascii", "ignore").decode())


def columnas_geo(esquema, resumen):
    """(latitud, longitud) si hay dos columnas numéricas con ese nombre y rango válido; si no, (None, None)."""
    res = {r["nombre"]: r for r in (resumen or [])}
    nums = [c["nombre"] for c in esquema if c.get("rol") == "numero"]

    def valido(n, tope):
        r = res.get(n, {})
        return r.get("min") is not None and r.get("max") is not None and -tope <= r["min"] and r["max"] <= tope
    la = next((n for n in nums if _RX_LAT.match(_norm_geo(n)) and valido(n, 90)), None)
    lo = next((n for n in nums if _RX_LON.match(_norm_geo(n)) and valido(n, 180)), None)
    return (la, lo) if la and lo else (None, None)


def sugerir(esquema, resumen):
    """Dashboard propuesto: indicadores + las gráficas que mejor encajan con los tipos de columna detectados."""
    res = {r["nombre"]: r for r in (resumen or [])}
    cols = [c for c in esquema if c.get("rol") != "ignorar"]
    fechas = [c["nombre"] for c in cols if c["rol"] == "fecha"]
    lat, lon = columnas_geo(esquema, resumen)
    nums = sorted([c["nombre"] for c in cols if c["rol"] == "numero" and c["nombre"] not in (lat, lon)], key=_puntaje)   # estable
    dims = [c["nombre"] for c in cols if c["rol"] in ("categoria", "estado")]

    def card(n):
        return res.get(n, {}).get("unicos") or 0
    bajas = [d for d in dims if 2 <= card(d) <= 8]                # pocas categorías → circular / series
    altas = [d for d in dims if card(d) > 8]                       # muchas → barras / Pareto
    ws, n = [], [0]

    def add(**kw):
        n[0] += 1
        ws.append({"id": f"w{n[0]}", **kw})

    add(tipo="kpi", titulo="Registros", agg="conteo", ancho=3, x=fechas[0] if fechas else None)
    for m in nums[:3]:
        a = "promedio" if _NOMBRES_MEDIA.search(m) else "suma"
        add(tipo="kpi", titulo=f"{'Promedio' if a == 'promedio' else 'Total'} de {m}", medida=m, agg=a, ancho=3,
            x=fechas[0] if fechas else None)
    m1 = nums[0] if nums else None
    agg1 = ("promedio" if m1 and _NOMBRES_MEDIA.search(m1) else "suma") if m1 else "conteo"
    if fechas:
        add(tipo="linea", titulo=f"{m1 or 'Registros'} por periodo", x=fechas[0], medida=m1,
            agg=agg1, ancho=12 if not bajas else 8, color=0)
    for d in bajas[:2]:
        add(tipo="dona", titulo=f"{(m1 + ' por ') if m1 and agg1 == 'suma' else 'Registros por '}{d}", x=d,
            medida=m1 if agg1 == "suma" else None, agg="suma" if (m1 and agg1 == "suma") else "conteo", ancho=4, top=6)
    if altas:
        d = altas[0]
        add(tipo="barras", titulo=f"{m1 or 'Registros'} por {d}", x=d, medida=m1, agg=agg1, orientacion="h", top=10,
            orden="desc", ancho=6, color=0)
        if card(d) > 10 and agg1 in ("suma",):
            add(tipo="pareto", titulo=f"Pareto de {m1} por {d}", x=d, medida=m1, agg="suma", top=10, ancho=6)
    elif bajas and not fechas:
        d = bajas[0]
        add(tipo="barras", titulo=f"{m1 or 'Registros'} por {d}", x=d, medida=m1, agg=agg1, orden="desc", ancho=6, color=0)
    if len(nums) >= 2:
        add(tipo="dispersion", titulo=f"{nums[0]} vs {nums[1]}", x=nums[0], y=nums[1],
            serie=bajas[0] if bajas and card(bajas[0]) <= 3 else None, ancho=6)
    if m1:
        add(tipo="histograma", titulo=f"Distribución de {m1}", x=m1, ancho=6, color=0)
    pares = [d for d in dims if 2 <= card(d) <= 12]
    if len(pares) >= 2:
        add(tipo="calor", titulo=f"{pares[0]} × {pares[1]}", x=pares[0], y=pares[1], medida=m1 if agg1 == "suma" else None,
            agg="suma" if (m1 and agg1 == "suma") else "conteo", ancho=6)
    elif fechas and pares:
        add(tipo="calor", titulo=f"{pares[0]} por periodo", x=fechas[0], y=pares[0], grano="mes", ancho=6)
    if lat and lon:
        add(tipo="mapa", titulo="Mapa" + (f" de {m1}" if m1 and agg1 == "suma" else ""), lat=lat, lon=lon,
            medida=m1 if agg1 == "suma" else None, agg="suma" if (m1 and agg1 == "suma") else "conteo",
            serie=bajas[0] if bajas and card(bajas[0]) <= 6 else None, ancho=12)
    add(tipo="tabla", titulo="Datos", columnas=[c["nombre"] for c in cols][:6], filas=8, ancho=12)
    return {"v": 1, "grano": "auto", "filtros": [], "widgets": ws[:15]}
