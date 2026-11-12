"""
Lectura flexible de Excel/CSV y detección automática del rol de cada columna.

Flujo:
  leer_archivo()      -> tabla cruda (hoja, fila de encabezado, codificación/separador resueltos)
  perfilar_columnas() -> por columna: rol sugerido + confianza + alternativas + ejemplos
  aplicar_esquema()   -> tabla limpia con los tipos que el usuario confirmó
  huella()            -> identifica "esta misma estructura de columnas" (para plantillas)

Roles: fecha | numero | categoria | identificador | estado | texto | ignorar
"""
import csv
import hashlib
import io
import os
import re
import unicodedata
import warnings
import zipfile
from typing import Optional

import numpy as np
import pandas as pd

ROLES = ["fecha", "numero", "categoria", "identificador", "estado", "texto", "ignorar"]
UMBRAL_REVISAR = 0.75          # por debajo de esto la pantalla marca la columna como "revisar"
MAX_FILAS_VENTANA_ENCABEZADO = 30
# Un .xlsx es un zip: 25 MB comprimidos pueden ser gigabytes al abrirse. Tope del tamaño ya descomprimido.
MAX_XLSX_DESCOMPRIMIDO = int(os.getenv("MAX_XLSX_DESCOMPRIMIDO_MB", "200")) * 1024 * 1024


# ───────────────────────────── utilidades de texto ─────────────────────────────
def _norm(s) -> str:
    """minúsculas, sin acentos, solo letras/números separados por espacio."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _tokens(nombre) -> set:
    return set(_norm(nombre).split())


def _vacio(x) -> bool:
    if x is None:
        return True
    if isinstance(x, float) and np.isnan(x):
        return True
    if isinstance(x, str) and x.strip() == "":
        return True
    try:
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def _vacios(serie: pd.Series) -> pd.Series:
    """Igual que serie.map(_vacio), pero de una sola pasada por columna (mucho más rápido en archivos grandes)."""
    m = serie.isna()
    if serie.dtype == object:
        try:
            en_blanco = serie.str.strip().eq("")          # lo que no es texto queda como NaN -> False
        except AttributeError:                            # la columna no tiene ningún texto
            return m
        m = m | en_blanco
    return m


def _todo_texto(serie: pd.Series) -> bool:
    """True si todos los valores no vacíos son cadenas (permite usar las operaciones rápidas de texto)."""
    return serie.dtype == object and pd.api.types.infer_dtype(serie, skipna=True) == "string"


# ───────────────────────────── lectura de archivos ─────────────────────────────
class ArchivoNoSoportado(Exception):
    pass


def _extension(nombre: str) -> str:
    return nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""


def _decodificar(contenido: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return contenido.decode(enc)
        except UnicodeDecodeError:
            continue
    return contenido.decode("latin-1", errors="replace")


def _detectar_separador(texto: str) -> str:
    # Solo hacen falta las primeras 50 líneas: no se parte el archivo entero en una lista
    lineas = texto[:1_000_000].splitlines()
    if len(lineas) <= 50 and len(texto) > 1_000_000:
        lineas = texto.splitlines()
    muestra = "\n".join(lineas[:50])
    try:
        return csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
    except csv.Error:
        cuentas = {d: muestra.count(d) for d in (",", ";", "\t", "|")}
        return max(cuentas, key=cuentas.get)


_MAX_TEXTOS_COMPARTIDOS = 100_000


def _lineas(texto: str):
    """Recorre el texto línea por línea (cortando en \\n, como io.StringIO) sin duplicarlo en memoria."""
    i, n = 0, len(texto)
    while i < n:
        j = texto.find("\n", i)
        if j < 0:
            yield texto[i:]
            return
        yield texto[i:j + 1]
        i = j + 1


def _grid_csv(contenido: bytes, max_filas: Optional[int] = None) -> pd.DataFrame:
    texto = _decodificar(contenido)
    sep = _detectar_separador(texto)
    lector = csv.reader(_lineas(texto), delimiter=sep)
    # Los valores repetidos (categorías, fechas, estados) comparten un solo objeto en memoria.
    vistos, filas, con_datos, ancho = {}, [], 0, 0
    tope = None if max_filas is None else max_filas + MAX_FILAS_VENTANA_ENCABEZADO + 1
    for fila in lector:
        for j, celda in enumerate(fila):
            v = vistos.get(celda)
            if v is not None:
                fila[j] = v
            elif len(vistos) < _MAX_TEXTOS_COMPARTIDOS:
                vistos[celda] = celda
        if len(fila) > ancho:
            ancho = len(fila)
        filas.append(fila)
        if tope is not None and any(c.strip() for c in fila):
            con_datos += 1
            if con_datos > tope:      # se corta aquí en vez de cargar todo para rechazarlo después
                raise ArchivoNoSoportado(f"El archivo tiene más de {max_filas:,} filas (máximo {max_filas:,}).")
    if ancho == 0:
        raise ArchivoNoSoportado("El archivo está vacío")
    # Se pasa fila por fila a la tabla y se suelta cada lista: así no conviven dos copias completas.
    tabla = np.full((len(filas), ancho), "", dtype=object)
    for i, f in enumerate(filas):
        tabla[i, :len(f)] = f
        filas[i] = None
    return pd.DataFrame(tabla, copy=False)


def _verificar_tamano_xlsx(contenido: bytes):
    """Rechaza libros que al descomprimirse ocuparían demasiada memoria (los .xls antiguos no son zip)."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            total = sum(i.file_size for i in z.infolist())
    except zipfile.BadZipFile:
        return
    if total > MAX_XLSX_DESCOMPRIMIDO:
        raise ArchivoNoSoportado(
            f"El libro ocupa {total // (1024 * 1024):,} MB al abrirse (máximo {MAX_XLSX_DESCOMPRIMIDO // (1024 * 1024)} MB). "
            "Guarda la hoja que necesitas como CSV y súbela así.")


def listar_hojas(contenido: bytes, nombre: str) -> list:
    ext = _extension(nombre)
    if ext in ("csv", "txt", "tsv"):
        return ["(archivo CSV)"]
    if ext not in ("xlsx", "xlsm", "xls"):
        raise ArchivoNoSoportado("Formato no soportado. Usa .xlsx, .xls o .csv")
    try:
        with pd.ExcelFile(io.BytesIO(contenido)) as xl:
            return list(xl.sheet_names)
    except Exception as e:
        raise ArchivoNoSoportado(f"No se pudo abrir el Excel: {e}")


def _grid(contenido: bytes, nombre: str, hoja: Optional[str], max_filas: Optional[int] = None) -> tuple:
    """Devuelve (grid crudo sin encabezado, nombre de hoja usada, lista de hojas)."""
    ext = _extension(nombre)
    if ext in ("csv", "txt", "tsv"):
        return _grid_csv(contenido, max_filas), "(archivo CSV)", ["(archivo CSV)"]
    if ext not in ("xlsx", "xlsm", "xls"):
        raise ArchivoNoSoportado("Formato no soportado. Usa .xlsx, .xls o .csv")
    _verificar_tamano_xlsx(contenido)
    try:
        xl = pd.ExcelFile(io.BytesIO(contenido))
    except Exception as e:
        raise ArchivoNoSoportado(f"No se pudo abrir el Excel: {e}")
    # El libro se abre UNA vez: antes se volvía a abrir completo por cada hoja que se revisaba.
    with xl:
        hojas = list(xl.sheet_names)
        if not hojas:
            raise ArchivoNoSoportado("El libro no tiene hojas")
        if hoja in hojas:
            return xl.parse(hoja, header=None, dtype=object), hoja, hojas
        # sin hoja elegida: la que más celdas con datos tenga (suele ser la tabla real, no las notas)
        usada, mejor, grid = hojas[0], -1, None
        for h in hojas[:15]:
            g = xl.parse(h, header=None, dtype=object)
            llenas = int(g.notna().sum().sum())
            if llenas > mejor:
                usada, mejor, grid = h, llenas, g
            del g
        return grid, usada, hojas


def _tipo_celda(x) -> str:
    if _vacio(x):
        return "vacio"
    if isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool):
        return "num"
    if isinstance(x, (pd.Timestamp,)) or hasattr(x, "year"):
        return "fecha"
    s = str(x).strip()
    if _parse_num_str(s) is not None and re.search(r"\d", s):
        return "num"
    return "texto"


def detectar_fila_encabezado(grid: pd.DataFrame) -> int:
    """Primera fila (0-based) que parece encabezado: casi toda llena, textual y sin repetidos."""
    ventana = grid.head(MAX_FILAS_VENTANA_ENCABEZADO)
    if ventana.empty:
        return 0
    llenos = [sum(not _vacio(v) for v in fila) for fila in ventana.itertuples(index=False)]
    ancho_efectivo = max(llenos) if llenos else 0
    if ancho_efectivo == 0:
        return 0
    for i, fila in enumerate(ventana.itertuples(index=False)):
        celdas = [v for v in fila if not _vacio(v)]
        if len(celdas) < max(2, 0.6 * ancho_efectivo) and ancho_efectivo > 1:
            continue
        tipos = [_tipo_celda(v) for v in celdas]
        if tipos.count("texto") < 0.7 * len(celdas):
            continue
        etiquetas = [_norm(v) for v in celdas]
        if len(set(etiquetas)) < 0.9 * len(etiquetas):
            continue
        # la fila siguiente debe tener datos
        if i + 1 < len(ventana):
            sig = [v for v in ventana.iloc[i + 1] if not _vacio(v)]
            if len(sig) < 0.5 * len(celdas):
                continue
        return i
    return 0


def leer_archivo(contenido: bytes, nombre: str, hoja: Optional[str] = None,
                 fila_encabezado: Optional[int] = None, max_filas: Optional[int] = None) -> dict:
    """
    Lee el archivo y devuelve:
      df, hojas, hoja, fila_encabezado (0-based, fila del grid), sin_encabezado, filas_omitidas
    Si fila_encabezado es None se detecta sola.
    max_filas: si se indica, un CSV más largo se rechaza mientras se lee (sin cargarlo completo).
    """
    grid, hoja_usada, hojas = _grid(contenido, nombre, hoja, max_filas)
    # quitar filas totalmente vacías (las filas en blanco arriba de la tabla no cuentan)
    fila_vacia = np.ones(len(grid), dtype=bool)
    for j in range(grid.shape[1]):
        fila_vacia &= _vacios(grid.iloc[:, j]).to_numpy()
    if fila_vacia.any():
        grid = grid[~fila_vacia]
    grid = grid.reset_index(drop=True)
    if grid.empty:
        raise ArchivoNoSoportado("La hoja no tiene datos")

    auto = fila_encabezado is None
    fila = detectar_fila_encabezado(grid) if auto else max(0, min(int(fila_encabezado), len(grid) - 1))

    encabezado = list(grid.iloc[fila])
    tipos = [_tipo_celda(v) for v in encabezado if not _vacio(v)]
    sin_encabezado = bool(tipos) and tipos.count("num") > 0.5 * len(tipos)
    if sin_encabezado:
        nombres = [f"Columna {j + 1}" for j in range(grid.shape[1])]
        datos = grid.iloc[fila:]
    else:
        nombres, vistos = [], {}
        for j, v in enumerate(encabezado):
            n = f"Columna {j + 1}" if _vacio(v) else re.sub(r"\s+", " ", str(v)).strip()
            if n in vistos:
                vistos[n] += 1
                n = f"{n}_{vistos[n]}"
            else:
                vistos[n] = 1
            nombres.append(n)
        datos = grid.iloc[fila + 1:]

    df = datos.reset_index(drop=True)
    del grid, datos
    df.columns = nombres
    # quitar columnas totalmente vacías
    vacias = [j for j in range(df.shape[1]) if _vacios(df.iloc[:, j]).all()]
    if vacias:
        df = df.drop(columns=[df.columns[j] for j in vacias])
    return {"df": df, "hojas": hojas, "hoja": hoja_usada, "fila_encabezado": int(fila),
            "sin_encabezado": sin_encabezado}


# ───────────────────────────── parseo de valores ─────────────────────────────
_RE_US = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
_RE_EU = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$")
_RE_COMA_DEC = re.compile(r"^-?\d+,\d{1,2}$")
_SIMBOLOS = re.compile(r"[\s$€£¥]|MXN|USD|EUR|pesos?", re.IGNORECASE)


def _parse_num_str(s: str) -> Optional[float]:
    """'$1,234.50' '12%' '(300)' '1.234,5' -> float; None si no es número."""
    t = _SIMBOLOS.sub("", s.strip())
    if not t:
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]
    if t.endswith("%"):
        t = t[:-1]
    if t.startswith("+"):
        t = t[1:]
    try:
        if _RE_US.match(t):
            v = float(t.replace(",", ""))
        elif _RE_EU.match(t):
            v = float(t.replace(".", "").replace(",", "."))
        elif _RE_COMA_DEC.match(t):
            v = float(t.replace(",", "."))
        else:
            if not re.match(r"^-?\d*\.?\d+([eE][-+]?\d+)?$", t):
                return None
            v = float(t)
    except ValueError:
        return None
    return -v if neg else v


_RE_NUM_SIMPLE = re.compile(r"-?[0-9]+(\.[0-9]+)?")


def _a_numero(serie: pd.Series) -> pd.Series:
    def conv(x):
        if _vacio(x):
            return np.nan
        if isinstance(x, bool):
            return np.nan
        if isinstance(x, (int, float, np.integer, np.floating)):
            return float(x)
        v = _parse_num_str(str(x))
        return np.nan if v is None else v
    if serie.dtype != object:
        return serie.map(conv).astype(float)
    # Vía rápida: los textos con forma de número simple ("1250", "-3.75") se convierten en bloque;
    # solo lo demás ("$1,234.50", "12%", "(300)"…) pasa por el conversor celda por celda.
    valores = serie.to_numpy(dtype=object)
    out = np.full(len(valores), np.nan, dtype=float)
    try:
        simple = serie.str.fullmatch(_RE_NUM_SIMPLE).eq(True).to_numpy(dtype=bool)   # lo que no es texto queda fuera
    except AttributeError:
        simple = np.zeros(len(valores), dtype=bool)
    if simple.any():
        out[simple] = valores[simple].astype(float)
    resto = ~simple
    if resto.any():
        out[resto] = [conv(x) for x in valores[resto]]
    return pd.Series(out, index=serie.index, name=serie.name, dtype=float)


_RE_FECHA_TXT = re.compile(
    r"(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})|(\d{1,2}\s*(de\s+)?[a-zA-Záéíóú]{3,10}\.?\s*(de\s+)?\d{2,4})|(^\d{1,2}:\d{2})")


def _dayfirst(valores: list) -> bool:
    """dd/mm/aaaa (México) salvo que los datos demuestren mm/dd."""
    for v in valores:
        m = re.match(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-]\d{2,4}", str(v))
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12:
                return True
            if b > 12:
                return False
    return True


_MESES_ES = {"enero": "Jan", "ene": "Jan", "febrero": "Feb", "feb": "Feb", "marzo": "Mar", "mar": "Mar",
             "abril": "Apr", "abr": "Apr", "mayo": "May", "may": "May", "junio": "Jun", "jun": "Jun",
             "julio": "Jul", "jul": "Jul", "agosto": "Aug", "ago": "Aug", "septiembre": "Sep", "setiembre": "Sep",
             "sept": "Sep", "sep": "Sep", "octubre": "Oct", "oct": "Oct", "noviembre": "Nov", "nov": "Nov",
             "diciembre": "Dec", "dic": "Dec"}
_RE_MES_ES = re.compile(r"\b(" + "|".join(sorted(_MESES_ES, key=len, reverse=True)) + r")\b\.?", re.IGNORECASE)
_RE_DE = re.compile(r"\s+de\s+", re.IGNORECASE)


def _meses_es_a_en(t: str) -> str:
    """'12 de abril de 2026' / '12-abr-26' → '12 Apr 2026' / '12-Apr-26' (pandas entiende los meses en inglés)."""
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóú]", t):
        return t
    t2 = _RE_MES_ES.sub(lambda m: _MESES_ES[m.group(1).lower()], t)
    if t2 == t:
        return t
    return _RE_DE.sub(" ", t2)


def _a_fecha(serie: pd.Series) -> pd.Series:
    """Convierte a datetime64; lo que no se pueda queda NaT."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    vac = _vacios(serie)
    nn = serie[~vac]
    if nn.empty:
        return pd.to_datetime(serie, errors="coerce")
    # Serie con objetos datetime / Timestamp
    if all(hasattr(v, "year") and not isinstance(v, str) for v in nn.head(200)):
        return pd.to_datetime(serie.map(lambda v: pd.NaT if _vacio(v) else v), errors="coerce")
    # Números de serie de Excel (fechas guardadas como 45123)
    nums = _a_numero(serie)
    if nums.notna().mean() > 0.9 and nums.dropna().between(20000, 80000).all():
        return pd.to_datetime("1899-12-30") + pd.to_timedelta(nums, unit="D")
    if _todo_texto(serie):
        texto = serie.str.strip().astype(object)
        con_letras = texto.str.contains(r"[A-Za-zÁÉÍÓÚáéíóú]", na=False).to_numpy(dtype=bool) & ~vac.to_numpy()
        if con_letras.any():
            texto[con_letras] = [_meses_es_a_en(t) for t in texto[con_letras]]
        texto[vac.to_numpy()] = np.nan
    else:
        texto = serie.map(lambda v: np.nan if _vacio(v) else _meses_es_a_en(str(v).strip()))
    df_first = _dayfirst(list(texto.dropna().head(500)))

    def _convertir(t, dayfirst):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                return pd.to_datetime(t, errors="coerce", dayfirst=dayfirst, format="mixed")
            except (TypeError, ValueError):
                return pd.to_datetime(t, errors="coerce", dayfirst=dayfirst)

    def convertir(t, dayfirst):
        # Cada texto se interpreta por separado, así que basta convertir los distintos y repartir el resultado:
        # una columna de 300 mil filas suele tener unos cientos de fechas diferentes.
        if len(t) > 2000:
            distintos = pd.Series(t.dropna().unique(), dtype=object)
            if len(distintos) <= len(t) // 2:
                r = _convertir(distintos, dayfirst)
                if pd.api.types.is_datetime64_any_dtype(r):
                    return t.map(pd.Series(r.to_numpy(), index=distintos.to_numpy()))
        return _convertir(t, dayfirst)

    # aaaa-mm-dd (ISO, año primero) es siempre año-mes-día: dayfirst NO debe aplicarse (invertiría 2026-04-12)
    iso = texto.str.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", na=False)
    if iso.all():
        return convertir(texto, False)
    if iso.any():
        out = pd.Series(pd.NaT, index=texto.index, dtype="datetime64[ns]")
        out[iso] = convertir(texto[iso], False)
        out[~iso] = convertir(texto[~iso], df_first)
        return out
    return convertir(texto, df_first)


def _proporcion_fechas(serie: pd.Series) -> float:
    nn = serie[~_vacios(serie)]
    if nn.empty:
        return 0.0
    if pd.api.types.is_datetime64_any_dtype(serie):
        return 1.0
    muestra = nn.head(500)
    es_obj_fecha = [hasattr(v, "year") and not isinstance(v, str) for v in muestra]
    if all(es_obj_fecha):
        return 1.0
    # un valor suelto que solo "parece" número no es fecha: exigir separadores o mes escrito
    cand = muestra[[bool(_RE_FECHA_TXT.search(str(v)) or (_RE_MES_ES.search(str(v)) and re.search(r"\d", str(v))))
                    for v in muestra]]
    if len(cand) < 0.8 * len(muestra):
        return 0.0
    parsed = _a_fecha(cand)
    return float(parsed.notna().sum()) / len(muestra)


# ───────────────────────────── perfilado y roles ─────────────────────────────
PISTAS = {
    "fecha": {"fecha", "date", "datetime", "dia", "day", "timestamp", "periodo", "period", "mes", "month",
              "fec", "time", "hora", "creado", "created", "vencimiento"},
    "identificador": {"id", "folio", "codigo", "code", "sku", "clave", "serie", "serial", "uuid", "ticket",
                      "factura", "invoice", "orden", "order", "pedido", "nro", "no", "num", "guid", "matricula"},
    "estado": {"estado", "estatus", "status", "resultado", "result", "aprobado", "passed", "failed", "pass",
               "fail", "ok", "activo", "situacion"},
    "numero": {"total", "importe", "monto", "precio", "price", "costo", "cost", "cantidad", "qty", "quantity",
               "venta", "ventas", "sales", "ingreso", "ingresos", "revenue", "gasto", "gastos", "utilidad",
               "margen", "horas", "hours", "minutos", "minutes", "peso", "weight", "edad", "age", "puntos",
               "score", "kg", "pct", "porcentaje", "tasa", "rate", "saldo", "balance", "valor", "value",
               "unidades", "units", "piezas", "pzas", "subtotal", "iva", "descuento", "discount", "amount",
               "duracion", "duration", "promedio", "avg", "sum", "count", "conteo", "salario", "sueldo",
               "pago", "nomina", "comision", "bono", "tarifa", "renta", "altura", "longitud", "temperatura"},
    "categoria": {"categoria", "category", "tipo", "type", "region", "zona", "area", "departamento", "depto",
                  "linea", "line", "turno", "shift", "equipo", "equipment", "cliente", "customer", "producto",
                  "product", "modelo", "model", "sucursal", "marca", "brand", "pais", "country", "ciudad",
                  "city", "segmento", "canal", "channel", "vendedor", "seller", "grupo", "group", "clase",
                  "class", "genero", "sexo", "puesto", "rol", "proveedor", "supplier", "estacion", "maquina"},
}
VOCAB_ESTADO = {"passed", "failed", "pass", "fail", "ok", "nok", "ng", "si", "no", "yes", "true", "false",
                "activo", "inactivo", "aprobado", "rechazado", "pendiente", "completado", "cerrado",
                "abierto", "cancelado", "entregado", "enviado", "pagado", "vencido", "valido", "invalido",
                "correcto", "incorrecto", "en proceso", "terminado", "finalizado"}


def _pista(nombre) -> Optional[str]:
    t = _tokens(nombre)
    # "id" dentro de nombres compuestos: ProductID2 -> "productid2" no separa; revisar sufijos
    plano = _norm(nombre).replace(" ", "")
    for rol in ("fecha", "estado", "identificador", "numero", "categoria"):
        if t & PISTAS[rol]:
            return rol
    if re.search(r"(id\d*|folio|codigo|sku)$", plano):
        return "identificador"
    return None


def _formato(serie: pd.Series) -> Optional[str]:
    muestra = [str(v) for v in serie[~_vacios(serie)].head(200)]
    if not muestra:
        return None
    if sum("%" in v for v in muestra) > 0.6 * len(muestra):
        return "porcentaje"
    if sum(bool(re.search(r"[$€£]", v)) for v in muestra) > 0.6 * len(muestra):
        return "moneda"
    return None


def _perfil_columna(nombre: str, serie: pd.Series) -> dict:
    vacios = _vacios(serie)
    nn = serie[~vacios]
    n = len(nn)
    total = len(serie)
    base = {"nombre": nombre, "nulos_pct": round(100 * (1 - n / total), 1) if total else 100.0,
            "unicos": 0, "ejemplos": [], "formato": None}
    if n == 0:
        return {**base, "rol": "ignorar", "confianza": 1.0, "alternativas": [],
                "razon": "La columna está vacía"}
    texto_nn = nn.str.strip() if _todo_texto(nn) else nn.map(lambda v: str(v).strip())
    unicos = int(texto_nn.nunique())
    ratio_unicos = unicos / n
    ejemplos = list(dict.fromkeys(texto_nn.head(200)))[:5]
    base.update({"unicos": unicos, "ejemplos": ejemplos, "formato": _formato(serie)})

    pista = _pista(nombre)
    cand = {}          # rol -> (confianza, razón)

    # — fecha
    pf = _proporcion_fechas(serie)
    nativo = pd.api.types.is_datetime64_any_dtype(serie) or all(
        hasattr(v, "year") and not isinstance(v, str) for v in nn.head(200))
    if pf >= 0.85:
        c = 0.97 if nativo else 0.9
        if pista == "fecha":
            c = 0.99
        cand["fecha"] = (c, "Los valores son fechas" + (" y el nombre lo confirma" if pista == "fecha" else ""))
    elif pista == "fecha":
        nums = _a_numero(serie)
        if nums.notna().mean() > 0.9 and nums.dropna().between(20000, 80000).all():
            cand["fecha"] = (0.8, "Números de serie de Excel con nombre de fecha")

    # — número
    numeros = _a_numero(serie)
    pn = float(numeros.notna().sum()) / n
    con_ceros = bool((texto_nn.str.match(r"^0\d+$")).any())
    if pn >= 0.9 and "fecha" not in cand and not con_ceros:
        valores = numeros.dropna()
        enteros = bool((valores == valores.round()).all())
        c = 0.9
        razon = "Los valores son numéricos"
        if pista == "numero":
            c, razon = 0.97, "Valores numéricos y el nombre sugiere una métrica"
        if enteros and unicos <= 10 and pista != "numero":
            # pocos enteros distintos: parece una categoría codificada (turno 1/2/3, mes 1-12…)
            cand["categoria"] = (0.8, f"Solo {unicos} valores numéricos distintos: parece un código")
            cand["numero"] = (0.55, razon)
        elif enteros and ratio_unicos >= 0.97 and n >= 20 and pista in (None, "identificador"):
            # un identificador suele ser una secuencia densa (1001, 1002…); una métrica se reparte en un rango amplio
            rango = float(valores.max() - valores.min() + 1)
            if rango <= 1.5 * n or valores.is_monotonic_increasing or pista == "identificador":
                cand["identificador"] = (0.8, "Enteros consecutivos que no se repiten: parece un identificador")
                cand["numero"] = (0.55, razon)
            else:
                cand["numero"] = (0.72, "Valores numéricos casi todos distintos y repartidos en un rango amplio")
                cand["identificador"] = (0.5, "O un identificador")
        elif pista == "identificador":
            cand["identificador"] = (0.85, "El nombre sugiere identificador")
            cand["numero"] = (0.6, razon)
        else:
            cand["numero"] = (c, razon)
    elif con_ceros:
        cand["identificador"] = (0.85, "Códigos con ceros a la izquierda: se tratan como texto")

    # — texto / categoría / estado / identificador (valores no numéricos)
    if "fecha" not in cand and ("numero" not in cand or pn < 0.9):
        len_media = float(texto_nn.str.len().mean())
        # solo importa cuando hay pocos valores distintos: se normalizan esos, no cada fila
        en_vocab = 0.0
        if unicos <= 12:
            en_vocab = sum(int(k) for v, k in texto_nn.value_counts().items() if _norm(v) in VOCAB_ESTADO) / n
        if unicos <= 12 and (en_vocab >= 0.8 or (pista == "estado" and unicos <= 12)):
            c = 0.93 if en_vocab >= 0.8 else 0.8
            cand["estado"] = (c, "Pocos valores que describen un estado/resultado")
            cand["categoria"] = (0.6, "También podría ser una categoría")
        elif ratio_unicos >= 0.9 and n >= 20 and len_media < 40:
            c = 0.95 if pista == "identificador" else 0.8
            cand["identificador"] = (c, "Casi todos los valores son distintos: parece un identificador")
            cand["texto"] = (0.5, "O texto libre")
        elif len_media > 40 or (ratio_unicos > 0.6 and len_media > 25):
            cand["texto"] = (0.8, "Textos largos o casi únicos")
            cand["categoria"] = (0.4, "O una categoría")
        elif unicos <= max(50, 0.2 * n):
            c = 0.92 if unicos <= 30 else 0.8
            if pista == "categoria":
                c = min(0.98, c + 0.05)
            cand["categoria"] = (c, f"{unicos} valores distintos que se repiten")
        else:
            cand["texto"] = (0.55, "Muchos valores distintos sin patrón claro")
            cand["categoria"] = (0.5, "O una categoría con muchos valores")

    # — ajuste por nombre
    if pista and cand:
        mejor = max(cand, key=lambda r: cand[r][0])
        if pista == mejor:
            cand[mejor] = (min(0.99, cand[mejor][0] + 0.04), cand[mejor][1] + " (coincide con el nombre)")
        elif pista in cand:
            cand[pista] = (min(0.9, cand[pista][0] + 0.15), cand[pista][1])
            m2 = max(cand, key=lambda r: cand[r][0])
            if m2 != pista and cand[m2][0] - cand[pista][0] < 0.1:
                cand[m2] = (cand[m2][0] - 0.1, cand[m2][1])
        else:
            cand[mejor] = (cand[mejor][0] - 0.1, cand[mejor][1] + f" (el nombre sugiere '{pista}')")

    if not cand:
        cand["texto"] = (0.5, "No se reconoce un patrón claro")

    orden = sorted(cand.items(), key=lambda kv: -kv[1][0])
    rol, (conf, razon) = orden[0]
    alternativas = [{"rol": r, "confianza": round(c, 2)} for r, (c, _) in orden[1:3]]
    # si la mejor alternativa está muy cerca, la confianza baja (hay duda real)
    if alternativas and conf - alternativas[0]["confianza"] < 0.15:
        conf = min(conf, 0.7)
    return {**base, "rol": rol, "confianza": round(conf, 2), "alternativas": alternativas, "razon": razon}


def perfilar_columnas(df: pd.DataFrame) -> list:
    return [_perfil_columna(str(c), df[c]) for c in df.columns]


# ───────────────────────────── plantillas ─────────────────────────────
def huella(nombres: list) -> str:
    base = "|".join(sorted(_norm(n) for n in nombres))
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def similitud(nombres_a: list, nombres_b: list) -> float:
    a, b = {_norm(n) for n in nombres_a}, {_norm(n) for n in nombres_b}
    return len(a & b) / len(a | b) if (a | b) else 0.0


def aplicar_plantilla(perfiles: list, plantilla_cols: list) -> list:
    """Sobrescribe rol/nombre de las columnas que existen en la plantilla guardada."""
    por_nombre = {_norm(c["nombre_origen"]): c for c in plantilla_cols}
    for p in perfiles:
        c = por_nombre.get(_norm(p["nombre"]))
        if c:
            p["rol"], p["confianza"], p["razon"] = c["rol"], 1.0, "Tomado de tu plantilla guardada"
            p["alternativas"] = []
            p["nombre_mostrar"] = c.get("nombre_mostrar") or p["nombre"]
    return perfiles


# ───────────────────────────── aplicar el esquema confirmado ─────────────────────────────
def aplicar_esquema(df: pd.DataFrame, columnas: list) -> pd.DataFrame:
    """
    columnas: [{nombre (origen), rol, nombre_mostrar?}]. Devuelve el DataFrame limpio y tipado.
    """
    out = {}
    usados = set()
    for c in columnas:
        origen, rol = c["nombre"], c["rol"]
        if rol == "ignorar" or origen not in df.columns:
            continue
        nombre = (c.get("nombre_mostrar") or origen).strip() or origen
        base, k = nombre, 2
        while nombre in usados:
            nombre, k = f"{base}_{k}", k + 1
        usados.add(nombre)
        s = df[origen]
        if rol == "fecha":
            out[nombre] = _a_fecha(s)
        elif rol == "numero":
            out[nombre] = _a_numero(s)
        elif _todo_texto(s):
            limpio = s.str.strip().astype(object)
            limpio[_vacios(limpio).to_numpy()] = None
            out[nombre] = limpio
        else:
            out[nombre] = s.map(lambda v: None if _vacio(v) else str(v).strip())
    res = pd.DataFrame(out)
    # quitar filas totalmente vacías tras la limpieza
    if not res.empty:
        res = res.dropna(how="all").reset_index(drop=True)
    return res


def resumen_columnas(df: pd.DataFrame, columnas: list) -> list:
    """Resumen por columna ya limpia, para la página 'Ver datos'."""
    roles = {(c.get("nombre_mostrar") or c["nombre"]): c["rol"] for c in columnas if c["rol"] != "ignorar"}
    out = []
    for col in df.columns:
        s = df[col]
        rol = roles.get(col, "texto")
        d = {"nombre": col, "rol": rol, "nulos": int(s.isna().sum())}
        if rol == "numero":
            v = s.dropna()
            if len(v):
                d.update({"min": float(v.min()), "max": float(v.max()), "media": float(v.mean()),
                          "suma": float(v.sum())})
        elif rol == "fecha":
            v = s.dropna()
            if len(v):
                d.update({"desde": v.min().strftime("%Y-%m-%d"), "hasta": v.max().strftime("%Y-%m-%d")})
        else:
            d["unicos"] = int(s.nunique())
            top = s.value_counts().head(5)
            d["top"] = [{"valor": str(k), "n": int(v)} for k, v in top.items()]
        out.append(d)
    return out
