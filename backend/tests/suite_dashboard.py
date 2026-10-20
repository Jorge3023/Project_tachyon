"""Dashboards: sugerencia, cálculo contra pandas, filtros, validación y permisos."""
import os, sys, tempfile, json
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
repo = os.path.abspath(REPO); sys.path.insert(0, os.path.join(repo, "backend"))
os.chdir(tempfile.mkdtemp(prefix="tachyon_dash_")); os.environ["SEED_DEMO_USERS"] = "1"
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
import main
from core.db import get_db
from servicios import parquet
c = TestClient(main.app, raise_server_exceptions=False)
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {str(extra)[:200]}" if (extra and not cond) else ""))
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

# ── Datos de prueba: 8 meses (con un mes SIN datos), 4 regiones, 14 productos, 3 estados ──────────
rng = np.random.default_rng(3)
n = 420
fechas = pd.to_datetime("2026-01-01") + pd.to_timedelta(rng.integers(0, 240, n), unit="D")
fechas = fechas[~((fechas >= "2026-04-01") & (fechas < "2026-05-01"))]       # abril vacío
n = len(fechas)
df = pd.DataFrame({"Fecha": fechas.strftime("%Y-%m-%d"), "Region": rng.choice(["Norte", "Centro", "Sur", "Occidente"], n),
                   "Producto": [f"P{k:02d}" for k in rng.integers(0, 14, n)], "Estado": rng.choice(["Abierto", "Cerrado", "Pendiente"], n),
                   "Monto": np.round(rng.gamma(2.0, 300, n), 2), "Cantidad": rng.integers(1, 20, n)})
df["Precio"] = np.round(df["Monto"] / df["Cantidad"], 2)
aid, roles = subir(ana, df)
print("roles detectados:", roles)
d = df.copy(); d["Fecha"] = pd.to_datetime(d["Fecha"])
def calc(widgets, **extra):
    r = c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": {"widgets": widgets, **extra}})
    assert r.status_code == 200, r.text
    return r.json()
def uno(w, **extra): return calc([{"id": "a", **w}], **extra)["widgets"]["a"]

# ── 1. Sugerencia automática ──────────────────────────────────────────────────────────────────────
r = c.get(f"/datasets/{aid}/dashboard", headers=ana).json()
tipos = [w["tipo"] for w in r["config"]["widgets"]]
check("sin vistas guardadas: se propone un dashboard", r["vista"]["guardada"] is False and len(tipos) >= 6, tipos)
check("la propuesta trae indicadores, línea, circular, barras, dispersión, histograma y tabla",
      all(t in tipos for t in ("kpi", "linea", "dona", "barras", "dispersion", "histograma", "tabla")), tipos)
check("la propuesta incluye Pareto (producto con 14 valores)", "pareto" in tipos, tipos)
km = [w["medida"] for w in r["config"]["widgets"] if w["tipo"] == "kpi" and w.get("medida")]
check("la métrica principal es el importe (no la cantidad ni el precio)", km == ["Monto", "Cantidad", "Precio"], km)
res = c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": r["config"]}).json()
check("todas las gráficas propuestas se calculan sin error", all("error" not in v for v in res["widgets"].values()),
      {k: v for k, v in res["widgets"].items() if "error" in v})
check("columnas y roles se devuelven", {x["nombre"] for x in r["columnas"]} == set(df.columns))

# ── 2. Indicadores ────────────────────────────────────────────────────────────────────────────────
check("KPI suma", abs(uno({"tipo": "kpi", "medida": "Monto", "agg": "suma"})["valor"] - d["Monto"].sum()) < 0.01)
check("KPI promedio", abs(uno({"tipo": "kpi", "medida": "Monto", "agg": "promedio"})["valor"] - d["Monto"].mean()) < 0.01)
check("KPI mediana/min/max", all(abs(uno({"tipo": "kpi", "medida": "Cantidad", "agg": a})["valor"] - getattr(d["Cantidad"], a if a != "mediana" else "median")()) < 1e-6 for a in ("min", "max", "mediana")))
check("KPI conteo de registros", uno({"tipo": "kpi"})["valor"] == len(d))
check("KPI valores únicos", uno({"tipo": "kpi", "medida": "Cantidad", "agg": "unicos"})["valor"] == d["Cantidad"].nunique())
k = uno({"tipo": "kpi", "medida": "Monto", "agg": "suma", "x": "Fecha", "grano": "mes"})
m = d.groupby(d["Fecha"].dt.strftime("%Y-%m"))["Monto"].sum().reindex(pd.date_range("2026-01-01", "2026-08-01", freq="MS").strftime("%Y-%m")).fillna(0)
_incompleto = d["Fecha"].max().normalize() < (d["Fecha"].max() + pd.offsets.MonthEnd(0)).normalize()
_i = -2 if _incompleto else -1
check("KPI: la suma ignora el periodo en curso (incompleto) y compara los dos últimos completos",
      _incompleto and k["delta"] and k["delta"]["actual"] == m.index[_i] and k["delta"].get("excluido") == m.index[-1]
      and abs(k["delta"]["pct"] - (m.iloc[_i] - m.iloc[_i - 1]) / m.iloc[_i - 1] * 100) < 0.01 and k["delta"]["grano"] == "mes", k)
kp = uno({"tipo": "kpi", "medida": "Monto", "agg": "promedio", "x": "Fecha", "grano": "mes"})
check("KPI: el promedio sí usa el último periodo aunque esté incompleto", kp["delta"] and kp["delta"]["actual"] == m.index[-1] and "excluido" not in kp["delta"], kp)
kc = uno({"tipo": "kpi", "medida": "Monto", "agg": "suma", "x": "Fecha", "grano": "mes"}, filtros=[{"col": "Fecha", "hasta": "2026-07-31"}])
mj = m.loc[:"2026-07"]
check("KPI: con el último mes completo no se excluye nada y compara contra el anterior",
      kc["delta"] and kc["delta"]["actual"] == "2026-07" and "excluido" not in kc["delta"]
      and abs(kc["delta"]["pct"] - (mj.iloc[-1] - mj.iloc[-2]) / mj.iloc[-2] * 100) < 0.01, kc)

# ── 3. Series de tiempo ───────────────────────────────────────────────────────────────────────────
l = uno({"tipo": "linea", "x": "Fecha", "medida": "Monto", "agg": "suma", "grano": "mes"})
check("línea por mes = groupby de pandas", [round(v, 2) for v in l["series"][0]["valores"]] == [round(v, 2) for v in m.tolist()], l["series"][0]["valores"][:4])
check("el mes sin datos aparece con 0 (no se esconde)", "2026-04" in l["categorias"] and l["series"][0]["valores"][l["categorias"].index("2026-04")] == 0)
l = uno({"tipo": "linea", "x": "Fecha", "agg": "conteo", "grano": "semana"})
check("línea por semana (conteo) suma todas las filas", sum(l["series"][0]["valores"]) == len(d) and l["categorias"][0] <= "2026-01-05")
l = uno({"tipo": "area", "x": "Fecha", "medida": "Monto", "agg": "suma", "serie": "Region", "grano": "mes"})
tot = {s["nombre"]: sum(s["valores"]) for s in l["series"]}
check("serie por región: 4 series y totales correctos", set(tot) == set(d["Region"].unique()) and all(abs(tot[r] - d[d.Region == r]["Monto"].sum()) < 0.05 for r in tot), tot)
check("grano auto elige uno razonable", uno({"tipo": "linea", "x": "Fecha", "agg": "conteo"})["grano"] in ("semana", "mes"))
check("grano global se aplica", uno({"tipo": "linea", "x": "Fecha", "agg": "conteo"}, grano="trimestre")["categorias"] == ["2026-T1", "2026-T2", "2026-T3"])
check("grano año", uno({"tipo": "linea", "x": "Fecha", "agg": "conteo", "grano": "anio"})["categorias"] == ["2026"])

# ── 4. Barras, circular, Pareto ───────────────────────────────────────────────────────────────────
b = uno({"tipo": "barras", "x": "Producto", "medida": "Monto", "agg": "suma", "top": 5, "orden": "desc"})
esp = d.groupby("Producto")["Monto"].sum().sort_values(ascending=False).head(5)
check("barras top 5 ordenadas = pandas", b["categorias"] == list(esp.index) and all(abs(a - e) < 0.01 for a, e in zip(b["series"][0]["valores"], esp)), b["categorias"])
check("barras avisa que hay más categorías", "5 de 14" in (b.get("advertencia") or ""), b.get("advertencia"))
b = uno({"tipo": "barras", "x": "Region", "medida": "Monto", "agg": "promedio", "orden": "asc"})
esp = d.groupby("Region")["Monto"].mean().sort_values()
check("barras promedio ascendente", b["categorias"] == list(esp.index) and abs(b["series"][0]["valores"][0] - esp.iloc[0]) < 0.01)
b = uno({"tipo": "barras", "x": "Region", "serie": "Estado", "agg": "conteo", "apilado": True, "orden": "natural"})
check("barras apiladas por estado: suma = filas", abs(sum(sum(s["valores"]) for s in b["series"]) - len(d)) < 1e-9 and len(b["series"]) == 3)
dn = uno({"tipo": "dona", "x": "Region", "medida": "Monto", "agg": "suma"})
check("circular: porcentajes suman 100 y total correcto", abs(sum(p["pct"] for p in dn["partes"]) - 100) < 0.1 and abs(dn["total"] - d["Monto"].sum()) < 0.05)
dn = uno({"tipo": "dona", "x": "Producto", "agg": "conteo", "top": 4})
check("circular con más categorías agrupa en 'Otros' al final", len(dn["partes"]) == 5 and dn["partes"][-1]["nombre"] == "Otros" and sum(p["valor"] for p in dn["partes"]) == len(d), [p["nombre"] for p in dn["partes"]])
pa = uno({"tipo": "pareto", "x": "Producto", "medida": "Monto", "agg": "suma", "top": 6})
esp = d.groupby("Producto")["Monto"].sum().sort_values(ascending=False)
check("Pareto: orden y acumulado correctos", pa["categorias"] == list(esp.head(6).index) and abs(pa["acumulado"][-1] - esp.head(6).sum() / esp.sum() * 100) < 0.01 and pa["acumulado"] == sorted(pa["acumulado"]))

# ── 5. Dispersión, histograma, mapa de calor, tabla ────────────────────────────────────────────────
ds = uno({"tipo": "dispersion", "x": "Cantidad", "y": "Monto"})
check("dispersión: puntos y correlación = numpy", ds["muestra"] == len(d) and abs(ds["correlacion"] - round(float(np.corrcoef(d.Cantidad, d.Monto)[0, 1]), 3)) < 1e-9)
ds = uno({"tipo": "dispersion", "x": "Cantidad", "y": "Monto", "serie": "Region"})
check("dispersión por serie: máximo 3 series (2 + Otros)", len(ds["series"]) == 3 and "Otros" in ds["series"], ds["series"])
grande = pd.DataFrame({"a": rng.normal(size=4000), "b": rng.normal(size=4000)}); gid, _ = subir(ana, grande, "g.csv")
r = c.post(f"/datasets/{gid}/dashboard/datos", headers=ana, json={"config": {"widgets": [{"id": "s", "tipo": "dispersion", "x": "a", "y": "b"}]}}).json()["widgets"]["s"]
check("dispersión grande se muestrea (≤1500) y lo indica", r["muestra"] == 1500 and r["total"] == 4000 and len(r["puntos"]) == 1500)
h = uno({"tipo": "histograma", "x": "Monto"})
check("histograma: la suma de los bins = filas", sum(b["n"] for b in h["bins"]) == len(d) and h["bins"][0]["desde"] <= d.Monto.min() + 1e-3)
h = uno({"tipo": "histograma", "x": "Monto", "bins": 7})
check("histograma con bins elegidos", len(h["bins"]) == 7)
ca = uno({"tipo": "calor", "x": "Region", "y": "Estado", "agg": "conteo"})
piv = d.pivot_table(index="Estado", columns="Region", values="Monto", aggfunc="size")
ok = all(ca["valores"][ca["filas"].index(e)][ca["columnas"].index(r)] == piv.loc[e, r] for e in ca["filas"] for r in ca["columnas"])
check("mapa de calor = tabla dinámica de pandas", ok and ca["max"] >= ca["min"], ca)
ca = uno({"tipo": "calor", "x": "Fecha", "y": "Region", "grano": "mes", "medida": "Monto", "agg": "suma"})
check("mapa de calor con fecha por mes", len(ca["columnas"]) == 8 and len(ca["filas"]) == 4)
t = uno({"tipo": "tabla", "columnas": ["Producto", "Monto"], "filas": 5, "orden": "Monto", "dir": "desc"})
esp = d.sort_values("Monto", ascending=False).head(5)
check("tabla ordenada y recortada", [f[1] for f in t["filas"]] == [round(v, 2) for v in esp["Monto"]] and t["total"] == len(d) and t["columnas"] == ["Producto", "Monto"])

# ── 6. Filtros ────────────────────────────────────────────────────────────────────────────────────
f = [{"col": "Fecha", "desde": "2026-02-01", "hasta": "2026-03-31"}, {"col": "Region", "valores": ["Norte", "Sur"]}, {"col": "Monto", "min": 100}]
dd = d[(d.Fecha >= "2026-02-01") & (d.Fecha < "2026-04-01") & d.Region.isin(["Norte", "Sur"]) & (d.Monto >= 100)]
r = calc([{"id": "a", "tipo": "kpi", "medida": "Monto", "agg": "suma"}], filtros=f)
check("filtros globales (fecha + categoría + número)", abs(r["widgets"]["a"]["valor"] - dd.Monto.sum()) < 0.01 and r["filas_filtradas"] == len(dd) and r["filas_total"] == len(d), r["filas_filtradas"])
r = calc([{"id": "a", "tipo": "kpi", "medida": "Monto", "agg": "suma", "filtros": [{"col": "Estado", "valores": ["Abierto"]}]}, {"id": "b", "tipo": "kpi"}])
check("filtro por gráfica solo afecta a esa gráfica", abs(r["widgets"]["a"]["valor"] - d[d.Estado == "Abierto"].Monto.sum()) < 0.01 and r["widgets"]["b"]["valor"] == len(d))
r = calc([{"id": "a", "tipo": "kpi", "medida": "Monto", "agg": "suma"}], filtros=[{"col": "Region", "valores": ["No existe"]}])
check("filtro sin resultados no rompe (valor nulo)", r["widgets"]["a"]["valor"] is None and r["filas_filtradas"] == 0)
r = calc([{"id": "a", "tipo": "linea", "x": "Fecha", "agg": "conteo"}, {"id": "b", "tipo": "dona", "x": "Region"}, {"id": "c", "tipo": "histograma", "x": "Monto"}, {"id": "d", "tipo": "calor", "x": "Region", "y": "Estado"}, {"id": "e", "tipo": "dispersion", "x": "Monto", "y": "Cantidad"}], filtros=[{"col": "Region", "valores": ["No existe"]}])
check("todas las gráficas toleran 0 filas", all("error" not in v for v in r["widgets"].values()), r["widgets"])
v = c.get(f"/datasets/{aid}/valores?columna=Region", headers=ana).json()
check("valores para filtros: categorías", v["tipo"] == "categoria" and {x["valor"] for x in v["valores"]} == set(d.Region.unique()))
v = c.get(f"/datasets/{aid}/valores?columna=Monto", headers=ana).json(); check("valores para filtros: rango numérico", abs(v["min"] - d.Monto.min()) < 1e-6 and abs(v["max"] - d.Monto.max()) < 1e-6)
v = c.get(f"/datasets/{aid}/valores?columna=Fecha", headers=ana).json(); check("valores para filtros: rango de fechas", v["min"] == d.Fecha.min().strftime("%Y-%m-%d"))
check("valores de columna inexistente => 404", c.get(f"/datasets/{aid}/valores?columna=Nope", headers=ana).status_code == 404)

# ── 7. Validación (lista blanca) ────────────────────────────────────────────────────────────────────
def mala(w, **extra): return c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": {"widgets": [w], **extra}}).status_code
check("columna inexistente => 422", mala({"tipo": "barras", "x": "'; DROP TABLE archivos;--"}) == 422)
check("rol incompatible (suma de una categoría) => 422", mala({"tipo": "barras", "x": "Region", "medida": "Producto"}) == 422)
check("rol incompatible (línea con eje numérico) => 422", mala({"tipo": "linea", "x": "Monto"}) == 422)
check("agregación fuera de la lista => 422", mala({"tipo": "kpi", "medida": "Monto", "agg": "__import__('os')"}) == 422)
check("suma en circular de promedio => 422", mala({"tipo": "dona", "x": "Region", "medida": "Monto", "agg": "promedio"}) == 422)
check("tipo desconocido => 422", mala({"tipo": "pastel3d"}) == 422)
check("falta el eje X => 422", mala({"tipo": "barras"}) == 422)
check("mapa de calor con la misma columna => 422", mala({"tipo": "calor", "x": "Region", "y": "Region"}) == 422)
check("filtro sobre columna inexistente => 422", mala({"tipo": "kpi"}, filtros=[{"col": "Nope", "valores": ["x"]}]) == 422)
check("fecha inválida en filtro => 422", mala({"tipo": "kpi"}, filtros=[{"col": "Fecha", "desde": "ayer"}]) == 422)
check("más de 24 gráficas => 422", c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": {"widgets": [{"tipo": "kpi"}] * 25}}).status_code == 422)
check("config que no es objeto => 422", c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": []}).status_code == 422)
ok = uno({"tipo": "kpi", "medida": "Monto", "agg": "suma", "campo_extra": "x", "ancho": 99})
check("claves desconocidas se ignoran; ancho inválido se corrige", "valor" in ok)
r = calc([{"id": "dup", "tipo": "kpi"}, {"id": "dup", "tipo": "kpi"}]); check("ids repetidos se corrigen", len(r["widgets"]) == 2)

# ── 8. Vistas: crear, guardar, renombrar, borrar ───────────────────────────────────────────────────
cfg = {"grano": "mes", "filtros": [{"col": "Region", "valores": ["Norte"]}], "widgets": [{"id": "k1", "tipo": "kpi", "titulo": "Ventas", "medida": "Monto", "agg": "suma", "ancho": 3}]}
r = c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": " Mi  vista ", "config": cfg}); v1 = r.json()
check("crear vista (nombre normalizado)", r.status_code == 200 and v1["nombre"] == "Mi vista", r.text)
g = c.get(f"/datasets/{aid}/dashboard", headers=ana).json()
check("la vista guardada se carga con su configuración", g["vista"]["guardada"] and g["vista"]["id"] == v1["id"] and g["config"]["widgets"][0]["titulo"] == "Ventas" and g["config"]["filtros"][0]["valores"] == ["Norte"], g["vista"])
check("nombre repetido => 409", c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": "mi vista"}).status_code == 409)
r = c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": "Propuesta"}); check("vista nueva sin config usa la sugerencia", r.status_code == 200 and len(r.json()["config"]["widgets"]) >= 6)
v2 = r.json()["id"]
check("guardar cambios", c.put(f"/datasets/{aid}/dashboard/{v1['id']}", headers=ana, json={"config": {"widgets": [{"id": "k1", "tipo": "kpi"}]}}).status_code == 200 and len(c.get(f"/datasets/{aid}/dashboard?vista={v1['id']}", headers=ana).json()["config"]["widgets"]) == 1)
check("renombrar", c.put(f"/datasets/{aid}/dashboard/{v1['id']}", headers=ana, json={"nombre": "Resumen"}).json()["nombre"] == "Resumen")
check("renombrar a un nombre en uso => 409", c.put(f"/datasets/{aid}/dashboard/{v1['id']}", headers=ana, json={"nombre": "Propuesta"}).status_code == 409)
check("guardar una config inválida => 422 y no cambia nada", c.put(f"/datasets/{aid}/dashboard/{v1['id']}", headers=ana, json={"config": {"widgets": [{"tipo": "barras", "x": "Nope"}]}}).status_code == 422)
check("la lista de vistas trae las dos", [v["nombre"] for v in c.get(f"/datasets/{aid}/dashboard", headers=ana).json()["vistas"]] == ["Resumen", "Propuesta"])
check("vista inexistente => 404", c.get(f"/datasets/{aid}/dashboard?vista=99999", headers=ana).status_code == 404)

# ── 9. Permisos ───────────────────────────────────────────────────────────────────────────────────
H = lambda m, ruta, **kw: getattr(c, m)(f"/datasets/{aid}{ruta}", headers=car, **kw).status_code
check("ajeno: ver dashboard => 404", H("get", "/dashboard") == 404)
check("ajeno: calcular => 404", H("post", "/dashboard/datos", json={"config": {"widgets": []}}) == 404)
check("ajeno: valores => 404", H("get", "/valores?columna=Region") == 404)
check("ajeno: crear vista => 404", H("post", "/dashboard", json={"nombre": "x"}) == 404)
check("ajeno: guardar/borrar vista => 404", H("put", f"/dashboard/{v1['id']}", json={"nombre": "x"}) == 404 and H("delete", f"/dashboard/{v1['id']}") == 404)
c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "cmendez@empresa.com"})
g = c.get(f"/datasets/{aid}/dashboard", headers=car).json()
check("compartido: ve las vistas del dueño, solo lectura", g["archivo"]["es_mio"] is False and len(g["vistas"]) == 2)
check("compartido: puede calcular (solo lectura)", H("post", "/dashboard/datos", json={"config": {"widgets": [{"id": "a", "tipo": "kpi"}]}}) == 200)
check("compartido: NO puede crear, guardar ni borrar", H("post", "/dashboard", json={"nombre": "x"}) == 404 and H("put", f"/dashboard/{v1['id']}", json={"nombre": "x"}) == 404 and H("delete", f"/dashboard/{v1['id']}") == 404)
c.delete(f"/archivos/{aid}/comparticiones/cmendez@empresa.com", headers=ana)
check("sin compartir: otra vez 404", H("get", "/dashboard") == 404)
check("sin sesión => 401", c.get(f"/datasets/{aid}/dashboard").status_code == 401)

# ── 10. Límites y limpieza ─────────────────────────────────────────────────────────────────────────
for i in range(8): c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": f"V{i}"})
check("máximo de vistas por archivo", c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": "una más"}).status_code == 422)
check("borrar vista", c.delete(f"/datasets/{aid}/dashboard/{v2}", headers=ana).status_code == 200)
_ok = c.delete(f"/archivos/{aid}", headers=ana).status_code == 200
_cn = get_db(); _q = _cn.execute("SELECT 1 FROM dashboards WHERE archivo_id=?", (aid,)).fetchall(); _cn.close()
check("borrar el archivo borra sus vistas", _ok and not _q)
# caché de Parquet
check("la caché no deja datos de archivos borrados", aid not in parquet._PARQUET_CACHE)
# dataset sin numéricos ni fechas
solo = pd.DataFrame({"Color": rng.choice(["rojo", "azul"], 60), "Talla": rng.choice(list("SML"), 60)}); sid, _ = subir(ana, solo, "s.csv")
r = c.get(f"/datasets/{sid}/dashboard", headers=ana).json(); rr = c.post(f"/datasets/{sid}/dashboard/datos", headers=ana, json={"config": r["config"]}).json()
check("archivo solo con categorías: propuesta válida y calculable", len(r["config"]["widgets"]) >= 3 and all("error" not in v for v in rr["widgets"].values()), [w["tipo"] for w in r["config"]["widgets"]])
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
