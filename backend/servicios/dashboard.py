"""Motor de dashboards sobre datasets genéricos.

El cliente nunca manda filas ni fórmulas: manda una *configuración* (lista de gráficas + filtros) que aquí se
valida contra el esquema del dataset (nombres de columna y roles reales, agregaciones en lista blanca, límites)
y se calcula en el servidor con pandas. El navegador solo recibe los resultados ya agregados.

Configuración (JSON):
    {"grano": "auto|dia|semana|mes|trimestre|anio",
     "filtros": [<filtro>],
     "widgets": [{"id", "tipo", "titulo", "ancho", "x", "y", "medida", "agg", "serie", ...}]}
Filtro: {"col", "desde"/"hasta" (fecha) | "min"/"max" (número) | "valores" (categoría)}
Métrica calculada: {"nombre", "op", "a", "b"}. Se usa como "medida" de una gráfica por su nombre y se calcula sobre
los totales de cada grupo (p. ej. suma(defectuosas) ÷ suma(producidas)), nunca fila por fila.
"""
import math
import re
import unicodedata

import numpy as np
import pandas as pd

from servicios.detector import formato_por_nombre

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
MAX_METRICAS = 10
SIN_DATO = "(sin dato)"          # las filas sin valor en una categoría se muestran, no se esconden
# Métricas calculadas: (descripción, ¿se acumula como una suma?)
OPS = {"div": "A ÷ B", "pct": "A ÷ B en %", "resta": "A − B", "suma": "A + B", "margen": "(A − B) ÷ A en %"}
TIPOS_CON_CALCULADA = ("kpi", "linea", "area", "barras", "calor")

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
    if roles[v] == "calculada" and "calculada" not in permitidos:
        raise ConfigInvalida(f"«{v}» es una métrica calculada: úsala en indicadores, líneas, área, barras o mapa de calor")
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


def limpiar_filtros(filtros, roles, avisos=None):
    if filtros in (None, ""):
        return []
    if not isinstance(filtros, list) or len(filtros) > MAX_FILTROS:
        raise ConfigInvalida(f"Máximo {MAX_FILTROS} filtros")
    out = []
    for f in filtros:
        if avisos is not None:                     # modo tolerante: un filtro que ya no encaja se quita y se avisa
            try:
                out += limpiar_filtros([f], roles)
            except ConfigInvalida as e:
                avisos.append(f"Se quitó un filtro: {e}")
            continue
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


def _metricas(lista, roles):
    """Valida las métricas calculadas: nombre propio, operación conocida y dos columnas numéricas."""
    if lista in (None, ""):
        return []
    if not isinstance(lista, list) or len(lista) > MAX_METRICAS:
        raise ConfigInvalida(f"Máximo {MAX_METRICAS} métricas calculadas")
    out, nombres = [], set()
    for m in lista:
        if not isinstance(m, dict):
            raise ConfigInvalida("Métrica calculada no válida")
        nombre = " ".join(str(m.get("nombre") or "").split())[:40]
        if not nombre:
            raise ConfigInvalida("Ponle nombre a la métrica calculada")
        if nombre in roles or nombre.lower() in nombres:
            raise ConfigInvalida(f"Ya hay una columna o métrica llamada «{nombre}»")
        if m.get("op") not in OPS:
            raise ConfigInvalida("Operación no válida en una métrica calculada")
        for campo in ("a", "b"):
            v = m.get(campo)
            if not isinstance(v, str) or roles.get(v) != "numero":
                raise ConfigInvalida(f"La métrica «{nombre}» necesita dos columnas numéricas")
        nombres.add(nombre.lower())
        out.append({"nombre": nombre, "op": m["op"], "a": m["a"], "b": m["b"]})
    return out


def _widget(w, roles, i, ids_usados, roles_filtro=None):
    if not isinstance(w, dict):
        raise ConfigInvalida("Gráfica no válida")
    roles_filtro = roles_filtro if roles_filtro is not None else roles
    medibles = R_NUM + (("calculada",) if w.get("tipo") in TIPOS_CON_CALCULADA else ())
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
    out["filtros"] = limpiar_filtros(w.get("filtros"), roles_filtro)
    grano = w.get("grano", "auto")
    out["grano"] = grano if grano in GRANOS else "auto"

    def agg(permitidas=AGGS, defecto="suma"):
        if roles.get(w.get("medida")) == "calculada":
            return "calc"                            # la métrica calculada ya dice cómo se combina
        a = w.get("agg") or defecto
        if a not in permitidas:
            raise ConfigInvalida(f"Agregación no permitida aquí: {str(a)[:20]}")
        return a

    if tipo == "kpi":
        out["medida"] = _col(w, "medida", roles, medibles, etiqueta="la métrica")
        out["agg"] = agg(defecto="suma") if out["medida"] else "conteo"
        out["x"] = _col(w, "x", roles, R_FECHA, etiqueta="la fecha de comparación")
    elif tipo in ("linea", "area"):
        out["x"] = _col(w, "x", roles, R_FECHA + ("categoria", "estado"), True, "el eje X")
        out["medida"] = _col(w, "medida", roles, medibles, etiqueta="la métrica")
        out["agg"] = agg() if out["medida"] else "conteo"
        out["serie"] = _col(w, "serie", roles, ("categoria", "estado"), etiqueta="la serie")
    elif tipo == "barras":
        out["x"] = _col(w, "x", roles, R_FECHA + R_DIM, True, "el eje X")
        out["medida"] = _col(w, "medida", roles, medibles, etiqueta="la métrica")
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
        out["medida"] = _col(w, "medida", roles, medibles, etiqueta="la métrica")
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
            cols = list(roles_filtro)[:6]
        cols = [c for c in cols if isinstance(c, str)]
        if any(c not in roles_filtro for c in cols):
            raise ConfigInvalida("La tabla usa una columna que no existe")
        out["columnas"] = cols[:10]
        out["filas"] = _entero(w.get("filas"), 10, 1, 50)
        orden = w.get("orden")
        out["orden"] = orden if orden in roles_filtro else None
        out["dir"] = "asc" if w.get("dir") == "asc" else "desc"
    return out


def limpiar_config(config, esquema, avisos=None):
    """Devuelve la configuración saneada (solo claves conocidas) o lanza ConfigInvalida.
    Con `avisos` (una lista) trabaja en modo tolerante: quita lo que ya no encaja con el archivo —p. ej. después
    de cambiar el tipo de una columna— y anota qué quitó, en vez de rechazar toda la vista."""
    if not isinstance(config, dict):
        raise ConfigInvalida("Configuración no válida")
    roles = _roles(esquema)
    widgets = config.get("widgets", [])
    if not isinstance(widgets, list) or len(widgets) > MAX_WIDGETS:
        raise ConfigInvalida(f"Máximo {MAX_WIDGETS} gráficas por vista")
    if avisos is None:
        metricas = _metricas(config.get("metricas"), roles)
    else:
        metricas = []
        for m in (config.get("metricas") or [])[:MAX_METRICAS] if isinstance(config.get("metricas"), list) else []:
            try:
                metricas += _metricas([m], {**roles, **{x["nombre"]: "calculada" for x in metricas}})
            except ConfigInvalida as e:
                avisos.append(f"Se quitó la métrica «{str((m or {}).get('nombre', ''))[:40]}»: {e}")
    roles_w = {**roles, **{m["nombre"]: "calculada" for m in metricas}}
    ids = set()
    grano = config.get("grano", "auto")
    if avisos is None:
        ws = [_widget(w, roles_w, i, ids, roles) for i, w in enumerate(widgets)]
    else:
        ws = []
        for i, w in enumerate(widgets):
            try:
                ws.append(_widget(w, roles_w, i, ids, roles))
            except ConfigInvalida as e:
                titulo = str((w or {}).get("titulo") or "") if isinstance(w, dict) else ""
                avisos.append(f"Se quitó la gráfica «{titulo[:60] or 'sin título'}»: {e}")
    out = {"v": 1, "grano": grano if grano in GRANOS else "auto",
           "filtros": limpiar_filtros(config.get("filtros"), roles, avisos), "widgets": ws}
    if metricas:
        out["metricas"] = metricas
    return out


def renombrar_columnas(config, mapa):
    """Cambia los nombres de columna usados en una configuración (sin validarla). mapa: {nombre_viejo: nombre_nuevo}."""
    if not mapa or not isinstance(config, dict):
        return config
    r = lambda v: mapa.get(v, v) if isinstance(v, str) else v
    def filtros(fs):
        return [{**f, "col": r(f.get("col"))} if isinstance(f, dict) else f for f in (fs or [])] if isinstance(fs, list) else fs
    out = {**config, "filtros": filtros(config.get("filtros"))}
    if isinstance(config.get("metricas"), list):
        out["metricas"] = [{**m, "a": r(m.get("a")), "b": r(m.get("b"))} if isinstance(m, dict) else m for m in config["metricas"]]
    ws = []
    for w in config.get("widgets") or []:
        if isinstance(w, dict):
            w = {**w, **{k: r(w[k]) for k in ("x", "y", "lat", "lon", "medida", "serie", "orden") if k in w},
                 "filtros": filtros(w.get("filtros"))}
            if isinstance(w.get("columnas"), list):
                w["columnas"] = [r(c) for c in w["columnas"]]
        ws.append(w)
    out["widgets"] = ws
    return out


def columnas_usadas(config):
    calc = {m["nombre"]: m for m in config.get("metricas", [])}
    cols = set()
    for f in config["filtros"]:
        cols.add(f["col"])
    for w in config["widgets"]:
        for f in w["filtros"]:
            cols.add(f["col"])
        for campo in ("x", "y", "lat", "lon", "medida", "serie", "orden"):
            if w.get(campo):
                if w[campo] in calc:
                    cols.update((calc[w[campo]]["a"], calc[w[campo]]["b"]))
                else:
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
            m = s.notna() & s.astype(str).isin(f["valores"])
            if SIN_DATO in f["valores"]:
                m |= s.isna()
            mask &= m
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
    return _categorias(df[col]), None, None


def _categorias(serie):
    """Claves de texto de una columna de categoría; las celdas vacías cuentan como «(sin dato)»."""
    return serie.astype("string").fillna(SIN_DATO)


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
    """Serie de claves donde las menos frecuentes (más allá de n) pasan a 'Otros'. «(sin dato)» nunca se mezcla
    con «Otros»: así se ve cuánto falta."""
    cuenta = claves.value_counts().drop(SIN_DATO, errors="ignore")
    if len(cuenta) <= n:
        return claves, False
    mantener = set(cuenta.head(n).index) | {SIN_DATO}
    return claves.where(claves.isin(mantener) | claves.isna(), otros), True


def _combinar(a, b, op):
    """Combina los totales A y B de cada grupo según la operación de una métrica calculada."""
    a, b = a.astype("float64"), b.astype("float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        if op == "suma":
            r = a + b
        elif op == "resta":
            r = a - b
        elif op == "div":
            r = a / b.where(b != 0)
        elif op == "pct":
            r = a / b.where(b != 0) * 100
        else:                                        # margen
            r = (a - b) / a.where(a != 0) * 100
    return r.replace([np.inf, -np.inf], np.nan)


def _agregar_w(df, claves, w):
    """Como _agregar, pero entiende las métricas calculadas de la gráfica."""
    c = w.get("_calc")
    if not c:
        return _agregar(df, claves, w.get("medida"), w["agg"])
    sa, sb = _agregar(df, claves, c["a"], "suma"), _agregar(df, claves, c["b"], "suma")
    sa, sb = sa.align(sb, join="outer")
    return _combinar(sa.fillna(0), sb.fillna(0), c["op"])


def _total_w(df, w):
    c = w.get("_calc")
    if not c:
        return _valor_total(df, w.get("medida"), w["agg"])
    a, b = _valor_total(df, c["a"], "suma"), _valor_total(df, c["b"], "suma")
    if a is None and b is None:
        return None
    v = _combinar(pd.Series([a or 0.0]), pd.Series([b or 0.0]), c["op"]).iloc[0]
    return None if pd.isna(v) else float(v)


def _acumula(w):
    """¿El valor de un periodo crece con los días? (suma, conteo…). Un periodo a medias saldría «a la baja»."""
    c = w.get("_calc")
    if c:
        return c["op"] in ("suma", "resta")
    return w["agg"] in ("suma", "conteo", "unicos")


_FREC_PERIODO = {"semana": "W-SUN", "mes": "M", "trimestre": "Q", "anio": "Y"}


def _periodo_incompleto(s, grano):
    """True si la última fecha de los datos cae antes del final de su periodo (periodo en curso)."""
    f = _FREC_PERIODO.get(grano)
    v = s.dropna()
    if f is None or v.empty:
        return False
    if grano in ("mes", "trimestre", "anio") and bool((v.dt.day == 1).all()) and bool((v.dt.normalize() == v).all()):
        return False                     # datos mensuales (una fecha por mes, el día 1): cada mes ya está completo
    ultimo = v.max()
    return ultimo.normalize() < pd.Period(ultimo, freq=f).end_time.normalize()


def _calc_kpi(df, w, roles, gg):
    valor = _total_w(df, w)
    delta = None
    if w.get("x") and len(df):
        clave, completas, grano = _clave(df, w["x"], roles, gg, w["grano"])
        ser = _agregar_w(df, [clave], w)
        if completas:
            ser = ser.reindex(completas)
        acumula = _acumula(w)
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
    x = w["x"]
    claves, completas, grano = _clave(df, x, roles, gg, w["grano"])
    es_tiempo = roles[x] == "fecha"
    adv = None
    serie_col = w.get("serie")
    if serie_col:
        sk, recortado = _top_con_otros(_categorias(df[serie_col]), SERIES_MAX)
        ser = _agregar_w(df, [claves, sk], w)
        if ser.empty:
            return {"categorias": [], "series": [], "grano": grano}
        tabla = ser.unstack(level=1)
        if recortado:
            adv = f"Se muestran las {SERIES_MAX} series principales; el resto va en «Otros»."
        nombres = list(tabla.columns)
        total = _agregar_w(df, [claves], w)
    else:
        ser = _agregar_w(df, [claves], w)
        tabla = ser.to_frame(name=w["titulo"] or "Valor") if len(ser) else pd.DataFrame()
        nombres = list(tabla.columns)
        total = ser
    if tabla.empty:
        return {"categorias": [], "series": [], "grano": grano}
    relleno = 0.0 if _acumula(w) else None
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
    out = {"categorias": [str(c) for c in orden_cat],
           "series": [{"nombre": str(n), "valores": [_n(v) for v in tabla[n].tolist()]} for n in nombres],
           "grano": grano, "advertencia": adv}
    # El último periodo puede estar a medias (los datos llegan al 10 de noviembre): se marca para no leerlo como caída
    if es_tiempo and completas and len(orden_cat) >= 2 and _acumula(w) and _periodo_incompleto(df[x], grano):
        out["parcial"] = str(orden_cat[-1])
        out["parcial_hasta"] = df[x].max().strftime("%Y-%m-%d")
    return out


def _calc_reparto(df, w, roles, gg):
    """dona / pareto."""
    x = w["x"]
    claves = _categorias(df[x])
    if w["tipo"] == "dona":
        claves, recortado = _top_con_otros(claves, w["top"])
    else:
        recortado = False
    ser = _agregar(df, [claves], w["medida"], w["agg"]).sort_values(ascending=False, kind="stable")
    if ser.empty:
        return {"total": 0, "partes": [] if w["tipo"] == "dona" else None, "categorias": []}
    total = float(ser.sum())
    if w["tipo"] == "dona":
        for ultimo in ("Otros", SIN_DATO):              # «Otros» y «(sin dato)» siempre al final
            if ultimo in ser.index:
                ser = pd.concat([ser.drop(ultimo), ser[[ultimo]]])
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
        sk, _ = _top_con_otros(_categorias(d[w["serie"]]), 2)
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
        sk, _ = _top_con_otros(_categorias(d[ser]), SERIES_MAX)
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
    cy = _categorias(df[w["y"]])
    ser = _agregar_w(df, [cx, cy], w)
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


def formatos(esquema):
    """{columna: 'moneda' | 'porcentaje' | None}. Los archivos guardados antes de la v2 no lo traen: se deduce del nombre."""
    out = {}
    for c in esquema:
        if c.get("rol") != "numero":
            continue
        f = c["formato"] if "formato" in c else formato_por_nombre(c["nombre"])
        out[c["nombre"]] = f if f in ("moneda", "porcentaje") else None
    return out


def _formato_medida(w, fmts):
    m = w.get("medida")
    if not m or w.get("agg") in ("conteo", "unicos"):
        return None
    c = w.get("_calc")
    if c:
        return "porcentaje" if c["op"] in ("pct", "margen") else (None if c["op"] == "div" else fmts.get(c["a"]))
    return fmts.get(m)


def _con_formato(r, w, fmts):
    if w["tipo"] == "dispersion":
        r["formato_x"], r["formato_y"] = fmts.get(w["x"]), fmts.get(w["y"])
    elif w["tipo"] == "histograma":
        r["formato"] = fmts.get(w["x"])
    elif w["tipo"] == "tabla":
        r["formatos"] = [fmts.get(c) for c in w["columnas"]]
    else:
        r["formato"] = _formato_medida(w, fmts)
    return r


def calcular(df, config, esquema):
    """Calcula todas las gráficas de una configuración ya saneada. Un error en una gráfica no tumba a las demás."""
    roles = _roles(esquema)
    fmts = formatos(esquema)
    calc = {m["nombre"]: m for m in config.get("metricas", [])}
    base = aplicar_filtros(df, config["filtros"], roles)
    out = {}
    for w in config["widgets"]:
        try:
            d = aplicar_filtros(base, w["filtros"], roles)
            w = {**w, "_calc": calc.get(w.get("medida"))}
            r = _CALC[w["tipo"]](d, w, roles, config["grano"])
            r.setdefault("n", int(len(d)))
            out[w["id"]] = _con_formato(r, w, fmts)
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
    valores = [{"valor": k, "n": int(v)} for k, v in cuenta.head(100).items()]
    vacias = int(serie.isna().sum())
    if vacias:
        valores.append({"valor": SIN_DATO, "n": vacias})
    return {"tipo": "categoria", "unicos": int(len(cuenta)), "valores": valores}


# ── Sugerencia automática según los roles de las columnas ────────────────────────────────────────────
# Medidas que se promedian, no se suman (sumar precios, porcentajes o calificaciones no significa nada)
_NOMBRES_MEDIA = re.compile(r"(precio|promedio|tasa|porcentaje|%|ratio|edad|calif|score|temperatura|ciclo|ticket|"
                            r"unitari|unit\.|antig|nps|satisfac|puntua|puntaje|rating|evaluac|escala|humedad|velocidad|"
                            r"presi[oó]n|duraci[oó]n)", re.I)
# Qué columna numérica se toma como "la métrica principal": importes antes que cantidades
_PRIORIDAD = [re.compile(r"(importe|monto|venta|ingreso|revenue|sales|amount|total)", re.I),
              re.compile(r"(costo|cost|gasto|valor|pago)", re.I),
              re.compile(r"(cantidad|qty|unidades|piezas|volumen|producid)", re.I)]


def _puntaje(nombre):
    if _NOMBRES_MEDIA.search(nombre):
        return len(_PRIORIDAD) + 1
    for i, rx in enumerate(_PRIORIDAD):
        if rx.search(nombre):
            return i
    return len(_PRIORIDAD)


def agg_natural(nombre, info=None, formato=None):
    """'promedio' para precios, porcentajes, tiempos de ciclo, calificaciones…; 'suma' para importes y cantidades."""
    if formato == "porcentaje" or _NOMBRES_MEDIA.search(nombre):
        return "promedio"
    info = info or {}
    escala = (info.get("enteros") and info.get("min") is not None and 0 <= info["min"] and info.get("max", 99) <= 10
              and (info.get("unicos") or 99) <= 11)
    if escala and not any(rx.search(nombre) for rx in _PRIORIDAD):
        return "promedio"                            # calificación de 1 a 5, de 0 a 10…
    return "suma"


_RX_DEFECTO = re.compile(r"(defect|rechaz|scrap|merma|falla|fallid|mala|\bng\b|reproceso|devuel|error)", re.I)
_RX_BASE_TASA = re.compile(r"(produc|fabricad|inspecci|procesad|entregad|vendid|recibid|total)", re.I)
_RX_INGRESO = re.compile(r"(importe|venta|ingreso|revenue|sales|factur)", re.I)
_RX_COSTO = re.compile(r"(costo|cost)", re.I)


def metricas_sugeridas(sumables, nombres_columnas):
    """Métricas calculadas evidentes: tasa de defectos (defectuosas ÷ producidas) y margen ((ventas − costo) ÷ ventas)."""
    out = []
    usados = {n.lower() for n in nombres_columnas}
    a = next((n for n in sumables if _RX_DEFECTO.search(n)), None)
    b = next((n for n in sumables if n != a and _RX_BASE_TASA.search(n) and not _RX_DEFECTO.search(n)), None)
    if a and b and f"% {a}".lower() not in usados:
        out.append({"nombre": f"% {a}"[:40], "op": "pct", "a": a, "b": b})
    ing = next((n for n in sumables if _RX_INGRESO.search(n) and not _RX_COSTO.search(n)), None)
    cos = next((n for n in sumables if _RX_COSTO.search(n) and not re.search(r"unit", n, re.I)), None)
    if ing and cos and not any("margen" in n for n in usados):
        out.append({"nombre": "Margen %", "op": "margen", "a": ing, "b": cos})
    return out


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


def _acomodar(ws):
    """Anchos que llenan cada fila de 12 columnas: sin huecos al final de una fila."""
    kpis = [w for w in ws if w["tipo"] == "kpi"]
    ancho_kpi = {1: 12, 2: 6, 3: 4}.get(len(kpis), 3)
    for w in kpis:
        w["ancho"] = ancho_kpi
    fila, ultimo = 0, None
    for w in ws:
        if w["tipo"] == "kpi":
            continue
        if fila + w["ancho"] > 12:
            if ultimo is not None and fila < 12:
                ultimo["ancho"] += 12 - fila
            fila = 0
        fila += w["ancho"]
        ultimo = w
        if fila == 12:
            fila, ultimo = 0, None
    if ultimo is not None and 0 < fila < 12:
        ultimo["ancho"] += 12 - fila
    for w in ws:
        if w["ancho"] not in ANCHOS:
            w["ancho"] = min(a for a in ANCHOS if a >= w["ancho"])
    return ws


_RX_TITULAR = re.compile(r"(satisfac|nps|general|calificaci|puntua|global|total)", re.I)


def _texto_largo(info):
    """Una «categoría» cuyos valores son frases (comentarios, observaciones) no sirve para agrupar gráficas."""
    top = [t.get("valor", "") for t in (info or {}).get("top", [])]
    return bool(top) and sum(len(str(t)) for t in top) / len(top) > 22


def _dim_que_mas_varia(df, metrica, candidatos):
    """La categoría donde la métrica calculada cambia más entre grupos (p. ej. la línea con más defectos)."""
    mejor, mejor_v = None, -1.0
    w = {"medida": metrica["nombre"], "agg": "calc", "_calc": metrica}
    for d in candidatos:
        try:
            cuenta = df[d].value_counts()
            grupos = set(cuenta[cuenta >= max(5, len(df) * 0.01)].index.astype(str))
            r = _agregar_w(df, [_categorias(df[d])], w)
            r = r[r.index.isin(grupos)].dropna()
        except Exception:
            continue
        if len(r) >= 2:
            centro = abs(float(r.median())) or 1.0
            v = float(r.max() - r.min()) / centro
            if v > mejor_v:
                mejor, mejor_v = d, v
    return mejor


def sugerir(esquema, resumen, df=None):
    """Dashboard propuesto: indicadores + las gráficas que mejor cuentan algo con los tipos de columna detectados.

    Reglas: se suma lo que se acumula (importes, cantidades) y se promedia lo demás (precios, porcentajes,
    calificaciones); las razones evidentes (defectuosas ÷ producidas, margen) se proponen como métricas calculadas;
    cada categoría aparece una vez; no se cruzan categorías que son la misma información (Ciudad → Región) ni se
    grafican relaciones obvias (r ≈ 1)."""
    res = {r["nombre"]: r for r in (resumen or [])}
    fmts = formatos(esquema)
    cols = [c for c in esquema if c.get("rol") != "ignorar"]
    fechas = [c["nombre"] for c in cols if c["rol"] == "fecha"]
    f0 = fechas[0] if fechas else None
    lat, lon = columnas_geo(esquema, resumen)
    nums = sorted([c["nombre"] for c in cols if c["rol"] == "numero" and c["nombre"] not in (lat, lon)], key=_puntaje)
    aggs = {n: agg_natural(n, res.get(n), fmts.get(n)) for n in nums}
    sumables = [n for n in nums if aggs[n] == "suma"]
    promedios = sorted([n for n in nums if aggs[n] == "promedio"], key=lambda n: 0 if _RX_TITULAR.search(n) else 1)
    metricas = metricas_sugeridas(sumables, [c["nombre"] for c in esquema])

    def card(n):
        return res.get(n, {}).get("unicos") or 0
    dims = [c["nombre"] for c in cols if c["rol"] in ("categoria", "estado") and card(c["nombre"]) >= 2
            and not _texto_largo(res.get(c["nombre"]))]
    if df is not None and len(df):            # una categoría casi vacía («Causa de paro» con 88 % sin dato) no sirve de eje
        dims = [d for d in dims if d not in df.columns or df[d].isna().mean() <= 0.5]
    # Datos ya resumidos por periodo (una fila por mes): contar registros no dice nada
    por_periodo = bool(df is not None and f0 in getattr(df, "columns", []) and len(df) >= 3
                       and df[f0].dropna().dt.to_period("M").is_unique)
    estados = [c["nombre"] for c in cols if c["rol"] == "estado" and 2 <= card(c["nombre"]) <= 8]
    categorias = [d for d in dims if d not in estados]
    determina = {n: set(res.get(n, {}).get("determina") or []) for n in dims}
    jerarquicas = lambda a, b: b in determina.get(a, ()) or a in determina.get(b, ())

    # Métrica principal: el primer importe/cantidad; si todo se promedia (una encuesta), la primera calificación
    m1 = sumables[0] if sumables else (promedios[0] if promedios else None)
    a1 = aggs.get(m1, "conteo")
    ws, n = [], [0]

    def add(**kw):
        n[0] += 1
        ws.append({"id": f"w{n[0]}", "ancho": 6, **kw})

    def nombre_agg(m, a):
        return f"{'Promedio' if a == 'promedio' else 'Total'} de {m}"

    # 1. Indicadores: registros, dos totales y una razón (o un promedio)
    if not por_periodo:
        add(tipo="kpi", titulo="Registros", agg="conteo", x=f0)
    for m in sumables[:2 if not por_periodo else 3]:
        add(tipo="kpi", titulo=nombre_agg(m, "suma"), medida=m, agg="suma", x=f0)
    extra = [mt["nombre"] for mt in metricas] + promedios
    for m in extra[: 4 - len(ws)]:
        es_calc = any(mt["nombre"] == m for mt in metricas)
        add(tipo="kpi", titulo=m if es_calc else nombre_agg(m, "promedio"), medida=m,
            agg="calc" if es_calc else "promedio", x=f0)

    # 2. Evolución en el tiempo
    usadas = set()
    reparto = estados[0] if estados else next((d for d in categorias if 2 <= card(d) <= 6), None)
    if f0:
        add(tipo="linea", titulo=f"{(nombre_agg(m1, a1) if a1 == 'promedio' else m1) if m1 else 'Registros'} en el tiempo",
            x=f0, medida=m1, agg=a1, ancho=8 if reparto else 12, color=0)
    # 3. Reparto: un estado (Entregado / Cancelado…) se cuenta; una categoría corta se reparte por la métrica
    if reparto:
        usadas.add(reparto)
        por_suma = m1 and a1 == "suma" and reparto not in estados
        add(tipo="dona", titulo=f"{m1 if por_suma else 'Registros'} por {reparto}", x=reparto,
            medida=m1 if por_suma else None, agg="suma" if por_suma else "conteo", ancho=4, top=6)
    # 4. La razón calculada por la categoría que mejor la explica (p. ej. % defectuosas por línea)
    d_calc = None
    if metricas:
        cand = [d for d in categorias if 2 <= card(d) <= 30]
        d = _dim_que_mas_varia(df, metricas[0], [x for x in cand if card(x) <= 12] or cand) if df is not None else None
        d = d or next((x for x in cand if card(x) <= 12 and x not in usadas), None) or next(iter(cand), None)
        if d:
            usadas.add(d); d_calc = d
            mt = metricas[0]["nombre"]
            add(tipo="barras", titulo=f"{mt} por {d}", x=d, medida=mt, agg="calc", orden="desc", top=12,
                orientacion="h" if card(d) > 6 else "v", color=1)
    # 5. Rankings por las demás categorías (cada una una vez)
    # Una tasa o margen también en el tiempo (o un porcentaje que se promedia)
    seg = metricas[0]["nombre"] if metricas else next((m for m in promedios if fmts.get(m) == "porcentaje" and m != m1), None)
    if f0 and seg:
        add(tipo="linea", titulo=f"{seg} en el tiempo", x=f0, medida=seg, agg="calc" if metricas else "promedio", color=1)
    # Rankings: primero las categorías con unos 10 valores; al final las que repiten información ya graficada
    # (Región cuando ya está Ciudad, Categoría cuando ya está Producto). Se eligen de una en una.
    redundante = lambda d: any(d in determina.get(u, ()) for u in usadas)
    elegidas = []
    for _ in range(3):
        libres = [d for d in categorias if d not in usadas]
        if not libres:
            break
        d = min(libres, key=lambda d: (redundante(d), card(d) > 60, abs(math.log(max(card(d), 1) / 10))))
        usadas.add(d); elegidas.append(d)
    paretos = 0
    for d in elegidas:
        if card(d) > 15 and m1 and a1 == "suma" and not paretos:
            paretos += 1
            add(tipo="pareto", titulo=f"{m1} por {d}: los principales", x=d, medida=m1, agg="suma", top=10)
        else:
            add(tipo="barras", titulo=f"{(nombre_agg(m1, a1) if a1 == 'promedio' else m1) if m1 else 'Registros'} por {d}",
                x=d, medida=m1, agg=a1 if m1 else "conteo", orden="desc", top=10,
                orientacion="h" if card(d) > 6 else "v", color=0)
    # 6. Calor: una categoría corta a lo largo del tiempo (o dos categorías que no sean la misma información)
    cortas = [d for d in dims if 2 <= card(d) <= 12]
    if f0 and d_calc and card(d_calc) <= 12:
        mt = metricas[0]["nombre"]
        add(tipo="calor", titulo=f"{mt} por {d_calc} y periodo", x=f0, y=d_calc, grano="mes", medida=mt, agg="calc")
    elif f0 and cortas:
        d = cortas[0]
        add(tipo="calor", titulo=f"{(nombre_agg(m1, a1) if a1 == 'promedio' else m1) if m1 else 'Registros'} por {d} y periodo",
            x=f0, y=d, grano="mes", medida=m1, agg=a1 if m1 else "conteo")
    else:
        par = next(((a, b) for a in cortas for b in cortas if a < b and not jerarquicas(a, b)), None)
        if par:
            add(tipo="calor", titulo=f"{par[0]} × {par[1]}", x=par[0], y=par[1],
                medida=m1 if a1 == "suma" else None, agg="suma" if (m1 and a1 == "suma") else "conteo")
    # 7. Relación entre dos medidas, solo si no es obvia (|r| entre 0.3 y 0.9)
    par = None
    for x in nums[:5]:
        for y in nums[:5]:
            r = (res.get(x, {}).get("corr") or {}).get(y)
            if x < y and r is not None and 0.3 <= abs(r) <= 0.9:
                par = (x, y); break
        if par:
            break
    if par:
        add(tipo="dispersion", titulo=f"{par[0]} vs {par[1]}", x=par[0], y=par[1],
            serie=estados[0] if estados and card(estados[0]) <= 3 else None)
    # 8. Distribución: mejor de algo que se promedia (calificación, tiempo de ciclo) que de un importe
    h = promedios[0] if promedios else m1
    if h:
        add(tipo="histograma", titulo=f"Distribución de {h}", x=h, color=0)
    if lat and lon:
        add(tipo="mapa", titulo="Mapa" + (f" de {m1}" if m1 and a1 == "suma" else ""), lat=lat, lon=lon,
            medida=m1 if a1 == "suma" else None, agg="suma" if (m1 and a1 == "suma") else "conteo",
            serie=(estados or [d for d in dims if card(d) <= 6] or [None])[0], ancho=12)
    orden_tabla = fechas + [c["nombre"] for c in cols if c["rol"] == "identificador"] + dims + nums
    add(tipo="tabla", titulo="Datos", columnas=list(dict.fromkeys(orden_tabla))[:8], filas=8, ancho=12,
        orden=f0, dir="desc")
    ws = _acomodar(ws[:16])
    out = {"v": 1, "grano": "auto", "filtros": [], "widgets": ws}
    if metricas:
        out["metricas"] = metricas
    return out
