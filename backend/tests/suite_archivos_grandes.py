"""Archivos grandes: límites que cortan a tiempo y vías rápidas que deben dar exactamente lo mismo que las lentas."""
import os, sys, tempfile, io, zipfile
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backend")); os.chdir(tempfile.mkdtemp(prefix="tachyon_ag_")); os.environ["SEED_DEMO_USERS"] = "1"
import numpy as np, pandas as pd
from servicios import detector as D
from servicios import parquet as P
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {extra}" if (extra and not cond) else ""))
    if not cond: fallos.append(n)
def mismo(a, b):
    """Mismos valores Y mismos tipos, celda por celda (NaN == NaN)."""
    a, b = list(a), list(b)
    return len(a) == len(b) and all(type(x) is type(y) and (x == y or (x != x and y != y)) for x, y in zip(a, b))

# ── Vías rápidas == vías lentas ──
raros = ["12", "-3.75", "0012", " 12 ", "$1,234.50", "(300)", "1.234,5", "12%", "1e3", "inf", "nan", "N/A", "", "  ", None,
         np.nan, 7, 2.5, True, False, "+5", "1,5", "١٢", "1_000", "0x1A", ".5", "5.", "-", "--1", pd.Timestamp("2024-01-02"), "12 pesos", "USD 40"]
s = pd.Series(raros, dtype=object)
def conv_lento(x):
    if D._vacio(x) or isinstance(x, bool): return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)): return float(x)
    v = D._parse_num_str(str(x)); return np.nan if v is None else v
check("_a_numero: igual que el conversor celda por celda", mismo(D._a_numero(s), s.map(conv_lento).astype(float)))
check("_a_numero: columna sin ningún texto", mismo(D._a_numero(pd.Series([1, 2.5, None], dtype=object)), [1.0, 2.5, np.nan]))
check("_vacios: igual que _vacio", mismo(D._vacios(s), s.map(D._vacio)))
check("_vacios: columna numérica", mismo(D._vacios(pd.Series([1.0, np.nan])), [False, True]))

fechas = ["15/08/2023", "03-ene-25", "12 de abril de 2026", "2024-05-06", "", None, "no aplica", " 01/02/2024 ", "13/01/2024", "2024-05-06 10:30"]
grande = pd.Series(fechas * 400, dtype=object)            # activa el camino «convertir solo los distintos»
ref = pd.concat([D._a_fecha(pd.Series(fechas, dtype=object))] * 400, ignore_index=True)
check("_a_fecha: repartir desde los valores distintos da lo mismo", D._a_fecha(grande).equals(ref) and ref.notna().sum() == 7 * 400, str(D._a_fecha(pd.Series(fechas, dtype=object)).tolist()))
iso = pd.Series(["2026-04-12", "2026-12-04"] * 1500, dtype=object)
check("_a_fecha: ISO nunca se invierte", D._a_fecha(iso).dt.month.tolist()[:2] == [4, 12])

# ── CSV: mismas tablas que antes (filas desiguales, comillas con saltos de línea, CRLF) ──
csv_raro = 'Notas del reporte\r\n\r\nNombre;Monto;Comentario\r\nAna;10;"línea 1\nlínea 2"\r\nLuis;20\r\nEva;30;ok;extra\r\n;;\r\n'
r = D.leer_archivo(csv_raro.encode("cp1252"), "raro.csv")
df = r["df"]
check("CSV: encabezado, filas desiguales y celda con salto de línea",
      list(df.columns) == ["Nombre", "Monto", "Comentario", "Columna 4"] and df.shape == (3, 4)
      and df.iloc[0, 2] == "línea 1\nlínea 2" and df.iloc[1, 2] == "" and df.iloc[2, 3] == "extra", f"{list(df.columns)} {df.values.tolist()}")
check("CSV: sin límite de filas se comporta igual", D.leer_archivo(csv_raro.encode("cp1252"), "raro.csv", max_filas=10)["df"].equals(df))

# ── Límite de filas: se corta al leer ──
cuerpo = "a,b\n" + "".join(f"{i},x\n" for i in range(500))
try:
    D.leer_archivo(cuerpo.encode(), "largo.csv", max_filas=100); cortado = False
except D.ArchivoNoSoportado as e:
    cortado = "más de 100 filas" in str(e)
check("CSV más largo que el máximo: se rechaza durante la lectura", cortado)
check("CSV dentro del máximo: pasa", len(D.leer_archivo(cuerpo.encode(), "ok.csv", max_filas=500)["df"]) == 500)
con_blancos = "a,b\n" + "\n,\n".join(f"{i},x" for i in range(120)) + "\n"
check("las filas en blanco no cuentan para el límite", len(D.leer_archivo(con_blancos.encode(), "b.csv", max_filas=120)["df"]) == 120)

# ── Excel: tope del tamaño descomprimido y una sola apertura del libro ──
buf = io.BytesIO()
with pd.ExcelWriter(buf) as xw:
    pd.DataFrame({"nota": ["hola"]}).to_excel(xw, sheet_name="Notas", index=False)
    pd.DataFrame({"Fecha": pd.date_range("2024-01-01", periods=40), "Total": range(40)}).to_excel(xw, sheet_name="Datos", index=False)
libro = buf.getvalue()
r = D.leer_archivo(libro, "libro.xlsx")
check("Excel: elige la hoja con más datos", r["hoja"] == "Datos" and r["hojas"] == ["Notas", "Datos"] and r["df"].shape == (40, 2))
check("Excel: hoja pedida", D.leer_archivo(libro, "libro.xlsx", hoja="Notas")["df"].shape == (1, 1))
tope = D.MAX_XLSX_DESCOMPRIMIDO
try:
    D.MAX_XLSX_DESCOMPRIMIDO = 1000
    try:
        D.leer_archivo(libro, "libro.xlsx"); rechazado = False
    except D.ArchivoNoSoportado as e:
        rechazado = "al abrirse" in str(e)
finally:
    D.MAX_XLSX_DESCOMPRIMIDO = tope
check("Excel que se expande demasiado: se rechaza sin abrirlo", rechazado)
try:
    D.leer_archivo(b"no soy un excel", "x.xlsx"); malo = False
except D.ArchivoNoSoportado:
    malo = True
check("Excel dañado: error claro", malo)
try:
    D.leer_archivo(b"x", "x.pdf"); otro = False
except D.ArchivoNoSoportado:
    otro = True
check("extensión no soportada", otro)

# ── Parquet por tramos == Parquet de una vez ──
n = P.FILAS_POR_GRUPO * 5 + 1234
t = pd.DataFrame({"f": pd.date_range("2020-01-01", periods=n, freq="h"), "n": np.arange(n) / 3,
                  "c": pd.Series(["a", None, "ñ"] * (n // 3 + 1), dtype=object)[:n], "v": pd.Series([None] * n, dtype=object)})
b1 = io.BytesIO(); t.to_parquet(b1, engine="pyarrow", compression="zstd", index=False, row_group_size=P.FILAS_POR_GRUPO)
b2 = P.a_parquet(t)
import pyarrow.parquet as pq
f1, f2 = pq.ParquetFile(io.BytesIO(b1.getvalue())), pq.ParquetFile(io.BytesIO(b2))
grupos = lambda f: [f.metadata.row_group(i).num_rows for i in range(f.metadata.num_row_groups)]
check("a_parquet: mismos datos, esquema y grupos de filas", f1.read().to_pandas().equals(f2.read().to_pandas())
      and f1.schema_arrow.equals(f2.schema_arrow) and grupos(f1) == grupos(f2), f"{grupos(f1)[:3]} {grupos(f2)[:3]}")
total, pag = P.pagina_parquet(b2, P.FILAS_POR_GRUPO * 2 - 5, 10)
check("a_parquet: la paginación sigue leyendo solo lo necesario", total == n and pag["n"].tolist() == t["n"].iloc[P.FILAS_POR_GRUPO * 2 - 5:P.FILAS_POR_GRUPO * 2 + 5].tolist())

# ── API: el límite también se aplica al subir y al confirmar ──
from fastapi.testclient import TestClient
import main
from routers import datasets as R
c = TestClient(main.app, raise_server_exceptions=False)
h = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "mrodriguez@empresa.com", "password": "operador123"}).json()["access_token"]}
original = R.MAX_FILAS_DATASET
try:
    R.MAX_FILAS_DATASET = 100
    r = c.post("/datasets/analizar", headers=h, files={"file": ("largo.csv", cuerpo.encode(), "text/csv")})
    check("subir un CSV con demasiadas filas => 422 claro", r.status_code == 422 and "máximo 100" in r.json()["detail"], r.text)
    R.MAX_FILAS_DATASET = 1000
    r = c.post("/datasets/analizar", headers=h, files={"file": ("ok.csv", cuerpo.encode(), "text/csv")})
    check("dentro del límite se analiza", r.status_code == 200 and r.json()["filas"] == 500, r.text)
    an = r.json()
    R.MAX_FILAS_DATASET = 100
    r = c.post(f"/datasets/{an['archivo_id']}/confirmar", headers=h, json={"columnas": [{"nombre": x["nombre"], "rol": x["rol"]} for x in an["columnas"]]})
    check("confirmar también respeta el límite", r.status_code == 422, r.text)
    R.MAX_FILAS_DATASET = 1000
    r = c.post(f"/datasets/{an['archivo_id']}/confirmar", headers=h, json={"columnas": [{"nombre": x["nombre"], "rol": x["rol"]} for x in an["columnas"]]})
    check("confirmar guarda y se puede leer", r.status_code == 200 and c.get(f"/datasets/{an['archivo_id']}/datos", headers=h).json()["total"] == 500, r.text)
finally:
    R.MAX_FILAS_DATASET = original

print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
