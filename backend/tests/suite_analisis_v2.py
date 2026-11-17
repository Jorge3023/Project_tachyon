"""v2 — que el resumen diga lo correcto y que muestre lo importante.

Lectura (fechas año-mes, «N/A», valores no leídos, Sí/No, escalas, formato), «(sin dato)», periodo incompleto,
métricas calculadas, propuesta automática, vistas tolerantes y corregir columnas después de guardar."""
import os, sys, tempfile, json
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))
os.chdir(tempfile.mkdtemp(prefix="tachyon_v2_")); os.environ["SEED_DEMO_USERS"] = "1"
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
import main
from core import storage
from servicios import detector as D, dashboard as dash
from servicios.cuentas import ruta_original

c = TestClient(main.app, raise_server_exceptions=False)
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {str(extra)[:240]}" if (extra and not cond) else ""))
    if not cond: fallos.append(n)
def login(u, p):
    r = c.post("/auth/login", data={"username": u, "password": p}); return {"Authorization": f"Bearer {r.json()['access_token']}"}
ana = login("mrodriguez@empresa.com", "operador123"); car = login("cmendez@empresa.com", "operador123")

def analizar(h, cuerpo, nombre="d.csv"):
    r = c.post("/datasets/analizar", headers=h, files={"file": (nombre, cuerpo, "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()
def confirmar(h, a, cambios=None):
    cols = [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre"]} for x in a["columnas"]]
    for col in cols:
        col.update((cambios or {}).get(col["nombre"], {}))
    r = c.post(f"/datasets/{a['archivo_id']}/confirmar", headers=h, json={"fila_encabezado": a["fila_encabezado"], "columnas": cols})
    assert r.status_code == 200, r.text
    return r.json()
def perfil(a, nombre): return next(x for x in a["columnas"] if x["nombre"] == nombre)

# ── 1. Lectura ─────────────────────────────────────────────────────────────────────────────────────
meses = pd.period_range("2024-01", "2025-06", freq="M").strftime("%Y-%m")
fin = pd.DataFrame({"Mes": meses, "Ingresos": np.arange(len(meses)) * 1000.0 + 50000, "Costo": 30000.0})
a = analizar(ana, fin.to_csv(index=False).encode(), "finanzas.csv")
check("«2023-01» (año-mes) se reconoce como fecha", perfil(a, "Mes")["rol"] == "fecha", perfil(a, "Mes"))
check("«01/2024» (mes/año) se lee como el día 1 de ese mes",
      D._a_fecha(pd.Series(["01/2024", "12/2024"], dtype=object)).dt.strftime("%Y-%m-%d").tolist() == ["2024-01-01", "2024-12-01"])
check("un rango como «1-12» NO es fecha", D._proporcion_fechas(pd.Series(["1-12", "13-24", "25-36"] * 5, dtype=object)) == 0.0)
check("ISO completo sigue igual (no se invierte)", D._a_fecha(pd.Series(["2026-04-12"], dtype=object)).iloc[0] == pd.Timestamp("2026-04-12"))

cad = pd.Series(["02-jul-27", "", "N/A", "sin fecha", "04-Aug-27", "-", "13/01/2027"] * 30, dtype=object)
check("fechas mezcladas con «N/A», «sin fecha», «-» se reconocen como fecha", D._perfil_columna("Caducidad", cad)["rol"] == "fecha")
n, ej = D.no_leidos(cad, D._a_fecha(cad))
check("«N/A», «sin fecha» y «-» cuentan como vacíos, no como errores", n == 0, (n, ej))
monto = pd.Series(["12.5", "N/D", "$1,200.00", "doce", "", "7", "?"] * 10, dtype=object)
n, ej = D.no_leidos(monto, D._a_numero(monto))
check("número: «doce» no se puede leer (10 veces) y se da como ejemplo", n == 10 and ej == ["doce"], (n, ej))
pm = D._perfil_columna("Monto", monto)
check("el perfil avisa antes de guardar cuántos no se leerán", pm["rol"] == "numero" and pm["lectura"]["numero"]["n"] == 10, pm.get("lectura"))
check("«N/D» no impide detectar una columna numérica",
      D._perfil_columna("Existencia", pd.Series(["10", "N/D", "3", "8", "N/D", "2"] * 20, dtype=object))["rol"] == "numero")

act = pd.Series(["Sí", "si", "NO", "No", "si ", "SI", None] * 5, dtype=object)
mv = D.mapa_variantes(act.dropna().str.strip().value_counts())
check("Sí/No: todas las variantes se escriben «Sí» y «No»", set(mv.values()) <= {"Sí", "No"} and "si" in mv and "NO" in mv, mv)
info = {}
lim = D.aplicar_esquema(pd.DataFrame({"Activo": act}), [{"nombre": "Activo", "rol": "estado"}], info)
check("al guardar quedan solo dos valores", set(lim["Activo"].dropna()) == {"Sí", "No"} and info["Activo"]["unificados"] >= 3, list(lim["Activo"].unique()))
ciu = pd.Series(["Monterrey", "monterrey", "MONTERREY ", "Mérida", "Merida", "León"] * 3, dtype=object)
lim = D.aplicar_esquema(pd.DataFrame({"Ciudad": ciu}), [{"nombre": "Ciudad", "rol": "categoria"}])
check("mayúsculas y acentos: gana la forma más frecuente", set(lim["Ciudad"]) == {"Monterrey", "Mérida", "León"}, set(lim["Ciudad"]))
lim = D.aplicar_esquema(pd.DataFrame({"Folio": ciu}), [{"nombre": "Folio", "rol": "identificador"}])
check("los identificadores NO se unifican", lim["Folio"].nunique() == 6, lim["Folio"].unique().tolist())

enc = pd.DataFrame({"Satisf": np.tile([1, 2, 3, 4, 5], 40), "Ambiente": np.tile([5, 4, 3, 2, 1], 40), "Turno": np.tile([1, 2, 3, 1, 2], 40)})
roles = {p["nombre"]: p["rol"] for p in D.perfilar_columnas(enc.astype(object))}
check("escalas 1–5 repetidas en varias columnas son medidas; «Turno 1/2/3» sigue siendo categoría",
      roles == {"Satisf": "numero", "Ambiente": "numero", "Turno": "categoria"}, roles)
check("formato por nombre: moneda, porcentaje (0–100) y nada para fracciones",
      (D.formato_por_nombre("Importe"), D.formato_por_nombre("Margen %", pd.Series([12.0, 30.0])),
       D.formato_por_nombre("Tasa", pd.Series([0.1, 0.2])), D.formato_por_nombre("Piezas")) == ("moneda", "porcentaje", None, None))

# ── 2. Datos de prueba por la API ───────────────────────────────────────────────────────────────────
rng = np.random.default_rng(5)
n = 900
fechas = pd.to_datetime("2025-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 313, n)), unit="D")   # hasta el 9 de noviembre
lineas = rng.choice(["L1", "L2", "L3"], n)
prod = rng.integers(100, 300, n)
defec = (prod * np.where(lineas == "L3", 0.06, 0.02)).astype(int)
ciudad = rng.choice(["Monterrey", "Saltillo", "Mérida", "Cancún"], n)
region = np.where(np.isin(ciudad, ["Monterrey", "Saltillo"]), "Norte", "Sur")
prov = rng.choice(["Aceros", "Plásticos", ""], n, p=[.5, .3, .2])
df = pd.DataFrame({"Fecha": fechas.strftime("%d/%m/%Y"), "Línea": lineas, "Ciudad": ciudad, "Región": region, "Proveedor": prov,
                   "Producidas": prod, "Defectuosas": defec, "Importe": np.round(prod * 12.5, 2), "Costo": np.round(prod * 7.5, 2),
                   "Estatus": rng.choice(["Cerrado", "Abierto"], n)})
a = analizar(ana, df.to_csv(index=False).encode(), "planta.csv")
conf = confirmar(ana, a)
aid = a["archivo_id"]
d = df.copy(); d["Fecha"] = pd.to_datetime(d["Fecha"], dayfirst=True); d["Proveedor"] = d["Proveedor"].replace("", np.nan)
def calc(widgets, **extra):
    r = c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": {"widgets": widgets, **extra}})
    return r
def uno(w, **extra):
    r = calc([{"id": "a", **w}], **extra); assert r.status_code == 200, r.text
    return r.json()["widgets"]["a"]

# (sin dato)
dn = uno({"tipo": "dona", "x": "Proveedor", "medida": "Importe", "agg": "suma"})
partes = {p["nombre"]: p["valor"] for p in dn["partes"]}
check("circular: las filas sin proveedor aparecen como «(sin dato)»", "(sin dato)" in partes, partes)
check("…y el total cuadra con el indicador", abs(dn["total"] - d["Importe"].sum()) < 0.01, (dn["total"], d["Importe"].sum()))
check("«(sin dato)» va al final", dn["partes"][-1]["nombre"] == "(sin dato)")
check("filtrar por «(sin dato)» trae justo esas filas",
      uno({"tipo": "kpi"}, filtros=[{"col": "Proveedor", "valores": ["(sin dato)"]}])["valor"] == int(d["Proveedor"].isna().sum()))
v = c.get(f"/datasets/{aid}/valores", headers=ana, params={"columna": "Proveedor"}).json()
check("los valores para filtrar incluyen «(sin dato)»", any(x["valor"] == "(sin dato)" for x in v["valores"]))

# periodo incompleto
l = uno({"tipo": "linea", "x": "Fecha", "medida": "Importe", "agg": "suma", "grano": "mes"})
check("la línea marca el último mes como incompleto (datos hasta el 9 nov)", l.get("parcial") == "2025-11" and l.get("parcial_hasta") == "2025-11-09", l.get("parcial"))
l = uno({"tipo": "linea", "x": "Fecha", "medida": "Importe", "agg": "promedio", "grano": "mes"})
check("un promedio no se marca (no depende de cuántos días tiene el mes)", "parcial" not in l)
af = c.post("/datasets/analizar", headers=ana, files={"file": ("mensual.csv", fin.to_csv(index=False).encode(), "text/csv")}).json()
confirmar(ana, af)
r = c.post(f"/datasets/{af['archivo_id']}/dashboard/datos", headers=ana, json={"config": {"widgets": [
    {"id": "l", "tipo": "linea", "x": "Mes", "medida": "Ingresos", "agg": "suma", "grano": "mes"},
    {"id": "k", "tipo": "kpi", "x": "Mes", "medida": "Ingresos", "agg": "suma", "grano": "mes"}]}}).json()["widgets"]
check("datos mensuales (día 1 de cada mes): el último mes NO es incompleto", "parcial" not in r["l"] and not r["k"]["delta"].get("excluido"), r)
check("…y el indicador compara los dos últimos meses", (r["k"]["delta"]["actual"], r["k"]["delta"]["anterior"]) == ("2025-06", "2025-05"))

# formato
k = uno({"tipo": "kpi", "medida": "Importe", "agg": "suma"})
check("el resultado dice que el importe es moneda", k["formato"] == "moneda", k)
check("un conteo no lleva formato", uno({"tipo": "kpi"})["formato"] is None)

# ── 3. Métricas calculadas ──────────────────────────────────────────────────────────────────────────
met = [{"nombre": "% defectos", "op": "pct", "a": "Defectuosas", "b": "Producidas"},
       {"nombre": "Margen", "op": "margen", "a": "Importe", "b": "Costo"},
       {"nombre": "Utilidad", "op": "resta", "a": "Importe", "b": "Costo"}]
k = uno({"tipo": "kpi", "medida": "% defectos"}, metricas=met)
check("KPI calculado = suma(defectuosas) ÷ suma(producidas) × 100", abs(k["valor"] - d.Defectuosas.sum() / d.Producidas.sum() * 100) < 1e-6, k)
check("…en porcentaje", k["formato"] == "porcentaje")
b = uno({"tipo": "barras", "x": "Línea", "medida": "% defectos", "orden": "desc"}, metricas=met)
esperado = (d.groupby("Línea").Defectuosas.sum() / d.groupby("Línea").Producidas.sum() * 100)
check("por línea: razón de totales (no promedio de razones) y L3 primero",
      b["categorias"][0] == "L3" and all(abs(v - esperado[c_]) < 1e-6 for c_, v in zip(b["categorias"], b["series"][0]["valores"])), b)
check("margen = (importe − costo) ÷ importe", abs(uno({"tipo": "kpi", "medida": "Margen"}, metricas=met)["valor"] - 40.0) < 1e-6)
u = uno({"tipo": "kpi", "medida": "Utilidad", "x": "Fecha", "grano": "mes"}, metricas=met)
check("una resta se acumula: el mes incompleto se excluye de la comparación", u["delta"]["excluido"] == "2025-11"
      and abs(u["valor"] - (d.Importe.sum() - d.Costo.sum())) < 0.01, u)
check("utilidad lleva el formato de la columna A (moneda)", u["formato"] == "moneda")
ca = uno({"tipo": "calor", "x": "Fecha", "y": "Línea", "grano": "mes", "medida": "% defectos"}, metricas=met)
check("mapa de calor con la métrica calculada", ca["filas"] and ca["max"] > 4, ca.get("max"))
for nombre, w, m in [("métrica en una circular => 422", {"tipo": "dona", "x": "Línea", "medida": "% defectos"}, met),
                     ("métrica con columna de texto => 422", {"tipo": "kpi"}, [{"nombre": "x", "op": "pct", "a": "Línea", "b": "Producidas"}]),
                     ("métrica con el nombre de una columna => 422", {"tipo": "kpi"}, [{"nombre": "Importe", "op": "suma", "a": "Importe", "b": "Costo"}]),
                     ("operación desconocida => 422", {"tipo": "kpi"}, [{"nombre": "x", "op": "pow", "a": "Importe", "b": "Costo"}]),
                     ("métrica que no existe => 422", {"tipo": "kpi", "medida": "Nada"}, met)]:
    check(nombre, calc([{"id": "a", **w}], metricas=m).status_code == 422)
r = c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": "Con métricas", "config": {"metricas": met, "widgets": [
    {"tipo": "barras", "x": "Línea", "medida": "% defectos"}]}})
check("una vista guarda sus métricas calculadas", r.status_code == 200 and r.json()["config"]["metricas"][0]["nombre"] == "% defectos", r.text)
vista_met = r.json()["id"]

# ── 4. Propuesta automática ─────────────────────────────────────────────────────────────────────────
c.delete(f"/datasets/{aid}/dashboard/{vista_met}", headers=ana)
p = c.get(f"/datasets/{aid}/dashboard", headers=ana).json()["config"]
ws = p["widgets"]
nombres_met = [m["nombre"] for m in p.get("metricas", [])]
check("propone la tasa de defectuosas y el margen como métricas", any(n.startswith("% Defectuosas") for n in nombres_met) and "Margen %" in nombres_met, nombres_met)
tasa = next(w for w in ws if w["tipo"] == "barras" and w.get("medida", "").startswith("% Defectuosas"))
check("…y la grafica por la categoría donde más varía (Línea)", tasa["x"] == "Línea", tasa)
check("no cruza Ciudad × Región (cada ciudad está en una sola región)", not any(w["tipo"] == "calor" and {w.get("x"), w.get("y")} == {"Ciudad", "Región"} for w in ws))
check("cada fila del tablero se llena (anchos que suman 12)", sum(w["ancho"] for w in ws if w["tipo"] != "kpi") % 12 == 0, [(w["tipo"], w["ancho"]) for w in ws])
check("una medida tipo precio o % se promedia; un importe se suma",
      (dash.agg_natural("Precio unitario"), dash.agg_natural("Descuento %"), dash.agg_natural("Importe"),
       dash.agg_natural("Satisfacción", {"enteros": True, "min": 1, "max": 5, "unicos": 5}),
       dash.agg_natural("Cantidad", {"enteros": True, "min": 1, "max": 8, "unicos": 8})) == ("promedio", "promedio", "suma", "promedio", "suma"))

# ── 5. Corregir columnas después de guardar ─────────────────────────────────────────────────────────
r = c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": "Mía", "config": {"filtros": [{"col": "Estatus", "valores": ["Cerrado"]}], "widgets": [
    {"id": "a", "titulo": "Por línea", "tipo": "barras", "x": "Línea", "medida": "Importe", "agg": "suma"},
    {"id": "b", "titulo": "Importe total", "tipo": "kpi", "medida": "Importe", "agg": "suma"}]}})
vista = r.json()["id"]
check("el original se conserva (comprimido) para poder corregir", storage.exists(ruta_original(aid)) if hasattr(storage, "exists") else True)
check("otro usuario no puede ver las columnas para editarlas", c.get(f"/datasets/{aid}/columnas", headers=car).status_code == 404)
ed = c.get(f"/datasets/{aid}/columnas", headers=ana)
check("se pueden abrir las columnas de un archivo guardado", ed.status_code == 200 and ed.json()["modo"] == "edicion" and ed.json()["origen_disponible"], ed.text[:200])
cols = {x["nombre"]: x for x in ed.json()["columnas"]}
check("…con el tipo con el que se guardaron", cols["Importe"]["rol"] == "numero" and cols["Importe"]["formato"] == "moneda" and cols["Línea"]["rol"] == "categoria")
nuevas = [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre_mostrar"], "formato": x.get("formato")} for x in ed.json()["columnas"]]
for x in nuevas:
    if x["nombre"] == "Importe": x["nombre_mostrar"] = "Venta"
    if x["nombre"] == "Línea": x["rol"] = "ignorar"
    if x["nombre"] == "Costo": x["formato"] = "numero"
r = c.post(f"/datasets/{aid}/columnas", headers=ana, json={"columnas": nuevas})
check("guardar los cambios de columnas", r.status_code == 200, r.text)
v = c.get(f"/datasets/{aid}/dashboard", headers=ana, params={"vista": vista}).json()
check("la vista sigue: el KPI usa el nombre nuevo «Venta»", any(w.get("medida") == "Venta" for w in v["config"]["widgets"]), v["config"])
check("la gráfica por «Línea» (ya ignorada) se quita con aviso", len(v["config"]["widgets"]) == 1 and any("Por línea" in x for x in v["avisos"]), v["avisos"])
check("el filtro de la vista se conserva", v["config"]["filtros"] == [{"col": "Estatus", "valores": ["Cerrado"]}])
k = c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": {"widgets": [{"id": "k", "tipo": "kpi", "medida": "Costo", "agg": "suma"}]}}).json()["widgets"]["k"]
check("«Costo» ahora sin formato de moneda (lo eligió el usuario)", k["formato"] is None, k)
check("los datos se recalculan (la caché se olvida)", "Línea" not in c.get(f"/datasets/{aid}/datos", headers=ana).json()["resumen"][0])
check("otro usuario no puede cambiar columnas", c.post(f"/datasets/{aid}/columnas", headers=car, json={"columnas": nuevas}).status_code == 404)
for x in nuevas:
    if x["nombre"] == "Línea": x["rol"] = "categoria"
r = c.post(f"/datasets/{aid}/columnas", headers=ana, json={"columnas": nuevas})
check("una columna ignorada se puede recuperar (gracias al original)", r.status_code == 200 and
      any(cc["nombre"] == "Línea" for cc in c.get(f"/datasets/{aid}/datos", headers=ana).json()["columnas"]))

# archivo guardado antes de la v2 (sin original): se reconstruye desde los datos limpios
storage.delete(ruta_original(aid))
ed = c.get(f"/datasets/{aid}/columnas", headers=ana)
check("sin original: también se pueden corregir", ed.status_code == 200 and ed.json()["origen_disponible"] is False, ed.text[:200])
nuevas = [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre_mostrar"]} for x in ed.json()["columnas"]]
for x in nuevas:
    if x["nombre"] == "Producidas": x["rol"] = "categoria"
r = c.post(f"/datasets/{aid}/columnas", headers=ana, json={"columnas": nuevas})
datos = c.get(f"/datasets/{aid}/datos", headers=ana).json()
col = next(cc for cc in datos["columnas"] if cc["nombre"] == "Producidas")
check("…y el número pasa a categoría sin decimales («150», no «150.0»)", r.status_code == 200 and col["rol"] == "categoria"
      and all("." not in str(f[datos["columnas"].index(col)]) for f in datos["filas"][:20]), r.text[:200])
check("borrar el archivo borra también el original", ruta_original(aid) in __import__("servicios.cuentas", fromlist=["x"]).rutas_de_archivo(aid))

print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
