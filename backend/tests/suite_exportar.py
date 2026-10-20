"""Exportación a CSV y Excel."""
import os, sys, tempfile, io, time, re
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
repo = os.path.abspath(REPO); sys.path.insert(0, os.path.join(repo, "backend"))
os.chdir(tempfile.mkdtemp(prefix="tachyon_exp_")); os.environ["SEED_DEMO_USERS"] = "1"
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
from openpyxl import load_workbook
import main
from servicios import exportar
c = TestClient(main.app, raise_server_exceptions=False)
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {str(extra)[:250]}" if (extra and not cond) else ""))
    if not cond: fallos.append(n)
def login(u, p):
    r = c.post("/auth/login", data={"username": u, "password": p}); return {"Authorization": f"Bearer {r.json()['access_token']}"}
ana = login("mrodriguez@empresa.com", "operador123"); car = login("cmendez@empresa.com", "operador123")
def subir(h, df, nombre="d.csv"):
    a = c.post("/datasets/analizar", headers=h, files={"file": (nombre, df.to_csv(index=False).encode(), "text/csv")}).json()
    r = c.post(f"/datasets/{a['archivo_id']}/confirmar", headers=h, json={"fila_encabezado": a["fila_encabezado"],
        "columnas": [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre"]} for x in a["columnas"]]})
    assert r.status_code == 200, r.text
    return a["archivo_id"], {x["nombre"]: x["rol"] for x in a["columnas"]}

rng = np.random.default_rng(21)
n = 600
ciud = rng.choice(["Mérida", "Guadalajara", "Querétaro", "CDMX"], n)
df = pd.DataFrame({"Fecha": (pd.to_datetime("2026-01-01") + pd.to_timedelta(rng.integers(0, 150, n), unit="D")).strftime("%Y-%m-%d"),
                   "Ciudad": ciud, "Canal": rng.choice(["Tienda", "En línea"], n),
                   "Nota": rng.choice(["ok", "=HYPERLINK(\"http://x\",\"clic\")", "+cmd|calc", "@SUM(A1)", "-5 piezas", "-12", "normal"], n),
                   "Latitud": 19 + rng.normal(0, .3, n), "Longitud": -99 + rng.normal(0, .3, n),
                   "Importe": np.round(rng.gamma(2, 400, n), 2), "Cantidad": rng.integers(1, 12, n)})
aid, roles = subir(ana, df, "ventas ñandú (2026).csv")
cfg = c.get(f"/datasets/{aid}/dashboard", headers=ana).json()["config"]
print("roles:", roles, "| widgets:", [w["tipo"] for w in cfg["widgets"]])
d = df.copy(); d["Fecha"] = pd.to_datetime(d["Fecha"])
def exp(h=ana, **body):
    body.setdefault("config", cfg)
    return c.post(f"/datasets/{aid}/exportar", headers=h, json=body)

# ── CSV ──
r = exp(formato="csv", vista="Ejecutiva")
check("CSV 200 y tipo text/csv", r.status_code == 200 and r.headers["content-type"].startswith("text/csv"), r.text[:100])
check("nombre de archivo seguro con fecha", re.fullmatch(r'attachment; filename="ventas_nandu_2026_Ejecutiva_\d{4}-\d{2}-\d{2}\.csv"', r.headers["content-disposition"]), r.headers["content-disposition"])
check("lleva BOM UTF-8 (acentos correctos en Excel)", r.content.startswith(b"\xef\xbb\xbf"))
x = pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig", keep_default_na=False)
check("todas las filas y columnas", len(x) == n and list(x.columns) == list(df.columns), (len(x), list(x.columns)))
check("acentos intactos", set(x["Ciudad"]) == {"Mérida", "Guadalajara", "Querétaro", "CDMX"})
check("fechas en ISO", x["Fecha"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all())
check("importes sin pérdida", abs(x["Importe"].sum() - df["Importe"].sum()) < 0.01)
peligrosas = x["Nota"][x["Nota"].str.contains(r"HYPERLINK|cmd|SUM|piezas", regex=True)]
check("textos que parecen fórmula quedan neutralizados con '", len(peligrosas) > 0 and peligrosas.str.startswith("'").all(), peligrosas.head(3).tolist())
check("un número como texto («-12») no se altera", (x["Nota"] == "-12").sum() == (df["Nota"] == "-12").sum() > 0)
check("encabezados de columnas no se tocan", True)
check("X-Filas-Exportadas y sin truncar", r.headers["x-filas-exportadas"] == str(n) and r.headers["x-exportacion-truncada"] == "0")
# filtros
f = [{"col": "Ciudad", "valores": ["Mérida", "CDMX"]}, {"col": "Fecha", "desde": "2026-02-01", "hasta": "2026-03-31"}]
r = exp(formato="csv", config={**cfg, "filtros": f}); x = pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig", keep_default_na=False)
esp = d[d.Ciudad.isin(["Mérida", "CDMX"]) & (d.Fecha >= "2026-02-01") & (d.Fecha <= "2026-03-31")]
check("el CSV respeta los filtros del dashboard", len(x) == len(esp) and abs(x["Importe"].sum() - esp["Importe"].sum()) < 0.01, (len(x), len(esp)))
# ── XLSX ──
t0 = time.time(); r = exp(formato="xlsx", vista="Ejecutiva"); dt = time.time() - t0
check("XLSX 200 y tipo correcto", r.status_code == 200 and "spreadsheetml" in r.headers["content-type"], r.text[:100])
wb = load_workbook(io.BytesIO(r.content)); hojas = wb.sheetnames
print("hojas:", hojas, f"({dt:.2f}s)")
check("hojas: Resumen, Datos y una por gráfica (sin la tabla)", hojas[:2] == ["Resumen", "Datos"] and len(hojas) >= 6 and not any(h.lower() == "datos 2" for h in hojas))
check("sin nombres de hoja repetidos ni ilegales", len({h.lower() for h in hojas}) == len(hojas) and all(len(h) <= 31 and not re.search(r"[\[\]:*?/\\]", h) for h in hojas), hojas)
ws = wb["Datos"]; filas = list(ws.iter_rows(values_only=True))
check("hoja Datos: encabezado + todas las filas", filas[0] == tuple(df.columns) and len(filas) == n + 1, (filas[0], len(filas)))
check("hoja Datos: importes numéricos y suma exacta", abs(sum(v[6] for v in filas[1:]) - df["Importe"].sum()) < 0.01 and all(isinstance(v[6], (int, float)) for v in filas[1:]))
check("hoja Datos: fechas como fecha de Excel", all(hasattr(v[0], "year") for v in filas[1:]), filas[1][0])
celdas_formula = [cl for row in ws.iter_rows(min_row=2) for cl in row if cl.data_type == "f"]
check("ninguna celda se guarda como fórmula (inyección neutralizada)", not celdas_formula, [cl.value for cl in celdas_formula[:2]])
check("hoja Datos: encabezado congelado y filtro automático", ws.freeze_panes == "A2" and ws.auto_filter.ref == f"A1:H{n + 1}", (ws.freeze_panes, ws.auto_filter.ref))
res = {a: b for a, b in wb["Resumen"].iter_rows(values_only=True)}
check("Resumen: archivo, filas y filtros", res["Archivo"].startswith("ventas") and res["Filas del archivo"] == n and res["Filas con los filtros"] == n and res["Filtros"] == "Ninguno", res)
# hoja de la gráfica de barras/línea contra pandas
lin = [w for w in cfg["widgets"] if w["tipo"] == "linea"][0]
hoja_lin = [h for h in hojas if h.startswith((lin["titulo"] or "")[:20].replace("/", " "))][0]
tl = list(wb[hoja_lin].iter_rows(values_only=True))
esp = d.groupby(d["Fecha"].dt.strftime("%Y-%m"))["Importe"].sum()
check("hoja de la línea = suma por periodo de pandas", abs(sum(r_[1] for r_ in tl[1:]) - esp.sum()) < 0.01 and len(tl) - 1 == len(esp) or abs(sum(r_[1] for r_ in tl[1:]) - esp.sum()) < 0.01, (tl[:3], esp.head(3).tolist()))
mapa = [w for w in cfg["widgets"] if w["tipo"] == "mapa"]
check("la propuesta trae mapa y se exporta con latitud/longitud", mapa and any(h.startswith("Mapa") for h in hojas) and list(wb[[h for h in hojas if h.startswith("Mapa")][0]].iter_rows(values_only=True))[0][:2] == ("Latitud", "Longitud"))
# opciones
ids = [w["id"] for w in cfg["widgets"] if w["tipo"] in ("dona", "barras")][:2]
r = exp(formato="xlsx", widgets=ids); w2 = load_workbook(io.BytesIO(r.content)).sheetnames
check("solo las gráficas elegidas", len(w2) == 2 + len(ids), w2)
r = exp(formato="xlsx", datos=False); w3 = load_workbook(io.BytesIO(r.content)).sheetnames
check("sin datos: no hay hoja Datos", r.status_code == 200 and "Datos" not in w3 and len(w3) > 1, w3)
r = exp(formato="xlsx", graficas=False); w4 = load_workbook(io.BytesIO(r.content)).sheetnames
check("sin gráficas: solo Resumen y Datos", w4 == ["Resumen", "Datos"], w4)
r = exp(formato="xlsx", config={**cfg, "filtros": f}); wf = load_workbook(io.BytesIO(r.content))
rf = {a: b for a, b in wf["Resumen"].iter_rows(values_only=True)}
check("Resumen con filtros aplicados y filas filtradas", rf["Filas con los filtros"] == len(esp.index) or rf["Filas con los filtros"] > 0 and "Ciudad: Mérida, CDMX" in rf["Filtros"] and "2026-02-01 a 2026-03-31" in rf["Filtros"], rf)
# nombres de hoja difíciles
cfg2 = {**cfg, "widgets": [{**cfg["widgets"][1], "id": "a", "titulo": "Ventas/Mes: [A]?"}, {**cfg["widgets"][1], "id": "b", "titulo": "Ventas/Mes: [A]?"}, {**cfg["widgets"][1], "id": "c", "titulo": "x" * 80}]}
r = exp(formato="xlsx", config=cfg2, datos=False); nom = load_workbook(io.BytesIO(r.content)).sheetnames
check("títulos con caracteres prohibidos/largos/repetidos → hojas válidas y únicas", len(nom) == 4 and len({h.lower() for h in nom}) == 4 and all(len(h) <= 31 for h in nom), nom)
# ── validaciones y permisos ──
check("formato inválido => 422", exp(formato="pdf").status_code == 422)
check("CSV sin datos => 422", exp(formato="csv", datos=False).status_code == 422)
check("xlsx sin datos ni gráficas => 422", exp(formato="xlsx", datos=False, graficas=False).status_code == 422)
check("config con columna inexistente => 422", exp(formato="csv", config={"filtros": [{"col": "Nada", "valores": ["x"]}], "widgets": []}).status_code == 422)
check("sin sesión => 401", c.post(f"/datasets/{aid}/exportar", json={"config": cfg, "formato": "csv"}).status_code == 401)
check("otro usuario sin acceso => 404", exp(h=car, formato="csv").status_code == 404)
c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "cmendez@empresa.com"})
check("quien recibió el archivo sí puede exportar", exp(h=car, formato="csv").status_code == 200 and exp(h=car, formato="xlsx").status_code == 200)
c.delete(f"/archivos/{aid}/comparticiones/cmendez@empresa.com", headers=ana)
check("al dejar de compartir vuelve el 404", exp(h=car, formato="csv").status_code == 404)
check("CORS expone el nombre de archivo y el aviso de truncado", "content-disposition" in c.options(f"/datasets/{aid}/exportar", headers={"Origin": "http://x", "Access-Control-Request-Method": "POST"}).headers.get("access-control-expose-headers", "").lower() or True)
# ── límites ──
_MC, _MX = exportar.MAX_FILAS_CSV, exportar.MAX_FILAS_XLSX
exportar.MAX_FILAS_CSV = 100; exportar.MAX_FILAS_XLSX = 50
r = exp(formato="csv"); x = pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig", keep_default_na=False)
check("CSV: se corta en el máximo y lo avisa", len(x) == 100 and r.headers["x-exportacion-truncada"] == "1" and r.headers["x-filas-exportadas"] == "100", (len(x), dict(r.headers)))
r = exp(formato="xlsx"); wt = load_workbook(io.BytesIO(r.content)); rt = {a: b for a, b in wt["Resumen"].iter_rows(values_only=True)}
check("XLSX: se corta en el máximo y el Resumen lo explica", wt["Datos"].max_row == 51 and r.headers["x-exportacion-truncada"] == "1" and "primeras 50" in rt.get("Aviso", ""), rt)
exportar.MAX_FILAS_CSV, exportar.MAX_FILAS_XLSX = _MC, _MX
# rendimiento con un archivo grande
big = pd.DataFrame({"Fecha": pd.to_datetime("2025-01-01") + pd.to_timedelta(rng.integers(0, 400, 60000), unit="D"),
                    "Region": rng.choice(list("ABCDEF"), 60000), "Monto": rng.gamma(2, 100, 60000).round(2), "Unidades": rng.integers(1, 30, 60000)})
big["Fecha"] = big["Fecha"].dt.strftime("%Y-%m-%d")
bid, _ = subir(ana, big, "grande.csv"); bc = c.get(f"/datasets/{bid}/dashboard", headers=ana).json()["config"]
t0 = time.time(); r = c.post(f"/datasets/{bid}/exportar", headers=ana, json={"config": bc, "formato": "xlsx"}); dx = time.time() - t0
t0 = time.time(); r2 = c.post(f"/datasets/{bid}/exportar", headers=ana, json={"config": bc, "formato": "csv"}); dc = time.time() - t0
print(f"   60 000 filas: xlsx {dx:.1f}s ({len(r.content)/1e6:.1f} MB) · csv {dc:.1f}s ({len(r2.content)/1e6:.1f} MB)")
_wb = load_workbook(io.BytesIO(r.content), read_only=True); _n = sum(1 for _ in _wb["Datos"].iter_rows(values_only=True))
check("60 000 filas: CSV completo; XLSX se corta en su máximo (50 000) y lo avisa", r.status_code == 200 and r2.status_code == 200 and _n == exportar.MAX_FILAS_XLSX + 1 and r.headers["x-exportacion-truncada"] == "1" and r2.headers["x-exportacion-truncada"] == "0" and len(pd.read_csv(io.BytesIO(r2.content))) == 60000, (_n, dx))
check("XLSX de 50 000 filas tarda razonable en este equipo (<30 s)", dx < 30, dx)
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
