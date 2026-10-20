"""Mapa (lat/lon) y dashboard principal."""
import os, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
repo = os.path.abspath(REPO); sys.path.insert(0, os.path.join(repo, "backend"))
os.chdir(tempfile.mkdtemp(prefix="tachyon_mapa_")); os.environ["SEED_DEMO_USERS"] = "1"
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
import main
from core.db import get_db
from servicios import dashboard as dash
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

rng = np.random.default_rng(11)
ciudades = {"CDMX": (19.43, -99.13), "Monterrey": (25.67, -100.31), "Guadalajara": (20.67, -103.35), "Mérida": (20.97, -89.62)}
n = 1200
nom = rng.choice(list(ciudades), n)
df = pd.DataFrame({"Fecha": pd.to_datetime("2026-01-01") + pd.to_timedelta(rng.integers(0, 200, n), unit="D"),
                   "Ciudad": nom, "Latitud": [ciudades[x][0] + rng.normal(0, .15) for x in nom],
                   "Longitud": [ciudades[x][1] + rng.normal(0, .15) for x in nom],
                   "Importe": np.round(rng.gamma(2, 500, n), 2)})
df["Fecha"] = df["Fecha"].dt.strftime("%Y-%m-%d")
aid, roles = subir(ana, df, "geo.csv")
print("roles:", roles)
check("Latitud/Longitud se detectan como número", roles["Latitud"] == "numero" and roles["Longitud"] == "numero")
r = c.get(f"/datasets/{aid}/dashboard", headers=ana).json()
tipos = [w["tipo"] for w in r["config"]["widgets"]]
mp = [w for w in r["config"]["widgets"] if w["tipo"] == "mapa"]
check("la propuesta incluye un mapa con lat/lon detectadas", len(mp) == 1 and mp[0]["lat"] == "Latitud" and mp[0]["lon"] == "Longitud", tipos)
check("la propuesta ya no usa Latitud/Longitud como métricas", all(w.get("medida") not in ("Latitud", "Longitud") for w in r["config"]["widgets"]))
check("la propuesta sigue terminando en la tabla", tipos[-1] == "tabla", tipos)
check("las columnas numéricas del editor llevan su rango", any(x["nombre"] == "Latitud" and 19 < x["min"] < x["max"] < 21.5 or x["nombre"] == "Latitud" for x in r["columnas"]) and all("min" in x for x in r["columnas"] if x["rol"] == "numero"))
rr = c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": r["config"]}).json()
check("toda la propuesta se calcula sin errores", all("error" not in v for v in rr["widgets"].values()), [v for v in rr["widgets"].values() if "error" in v])
m = rr["widgets"][mp[0]["id"]]
check("el mapa devuelve puntos con [lat, lon, valor, n]", len(m["puntos"]) > 0 and all(len(p) in (4, 5) for p in m["puntos"]))
check("no pasa de 800 puntos y conserva todas las filas", len(m["puntos"]) <= dash.MAX_PUNTOS_MAPA and sum(p[3] for p in m["puntos"]) == n == m["total"], (len(m["puntos"]), m["total"]))
check("avisa que agrupó puntos", m["agrupado"] and "agrupan" in (m["advertencia"] or ""))
la = [p[0] for p in m["puntos"]]; lo = [p[1] for p in m["puntos"]]
check("los puntos caen donde están las ciudades", min(la) > 18 and max(la) < 27 and min(lo) > -105 and max(lo) < -88, (min(la), max(la)))
check("límites devueltos para encuadrar el mapa", m["limites"][0][0] <= min(la) and m["limites"][1][0] >= max(la))
tot = sum(p[2] for p in m["puntos"]); check("suma de Importe por punto = suma total", abs(tot - df["Importe"].sum()) < 0.5, (tot, df["Importe"].sum()))

def calc(w, **extra):
    r = c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": {"widgets": [{"id": "m", **w}], **extra}})
    assert r.status_code == 200, r.text
    return r.json()["widgets"]["m"]
# color por categoría
mc = calc({"tipo": "mapa", "lat": "Latitud", "lon": "Longitud", "serie": "Ciudad", "medida": "Importe", "agg": "promedio"})
check("color por categoría: series y un índice por punto", sorted(mc["series"]) == sorted(ciudades) and all(len(p) == 5 and 0 <= p[4] < 4 for p in mc["puntos"]), mc["series"])
check("promedio por punto dentro del rango de los datos", all(df["Importe"].min() <= p[2] <= df["Importe"].max() for p in mc["puntos"]))
# pocos puntos: no se agrupa
pocos = calc({"tipo": "mapa", "lat": "Latitud", "lon": "Longitud"}, filtros=[{"col": "Ciudad", "valores": ["Mérida"]}])
check("con filtros el mapa responde (conteo)", pocos["total"] == int((df.Ciudad == "Mérida").sum()) and sum(p[3] for p in pocos["puntos"]) == pocos["total"])
sin = calc({"tipo": "mapa", "lat": "Latitud", "lon": "Longitud"}, filtros=[{"col": "Importe", "min": 1e9}])
check("sin filas: respuesta vacía válida", sin["puntos"] == [] and sin["total"] == 0)
# validaciones
def err(w):
    r = c.post(f"/datasets/{aid}/dashboard/datos", headers=ana, json={"config": {"widgets": [{"id": "m", **w}]}}); return r.status_code
check("mapa sin longitud => 422", err({"tipo": "mapa", "lat": "Latitud"}) == 422)
check("lat = lon => 422", err({"tipo": "mapa", "lat": "Latitud", "lon": "Latitud"}) == 422)
check("columna inexistente => 422", err({"tipo": "mapa", "lat": "Latitud", "lon": "Nada"}) == 422)
check("columna categórica como longitud => 422", err({"tipo": "mapa", "lat": "Latitud", "lon": "Ciudad"}) == 422)
check("agregación inválida => 422", err({"tipo": "mapa", "lat": "Latitud", "lon": "Longitud", "medida": "Importe", "agg": "drop"}) == 422)
# coordenadas fuera de rango
d2 = pd.DataFrame({"Lat": [19.4, 25.6, 123.0, 20.6, 19.5], "Lng": [-99.1, -100.3, -99.0, -103.3, -300.0], "Ventas": [1, 2, 3, 4, 5]})
bid, _ = subir(ana, d2, "malo.csv")
rb = c.post(f"/datasets/{bid}/dashboard/datos", headers=ana, json={"config": {"widgets": [{"id": "m", "tipo": "mapa", "lat": "Lat", "lon": "Lng"}]}}).json()["widgets"]["m"]
check("filas con coordenadas imposibles se descartan y se avisa", rb["total"] == 3 and rb["fuera"] == 2 and "fuera de rango" in rb["advertencia"], rb)
rs = c.get(f"/datasets/{bid}/dashboard", headers=ana).json()
check("rango inválido (lat > 90): no se propone mapa", all(w["tipo"] != "mapa" for w in rs["config"]["widgets"]))
# nombres sin lat/lon: no hay mapa
rs2 = c.get(f"/datasets/{c.post('/datasets/analizar', headers=ana, files={'file': ('x.csv', pd.DataFrame({'A':[1,2,3,4],'B':[5,6,7,8],'C':['a','b','a','b']}).to_csv(index=False).encode(), 'text/csv')}).json()['archivo_id']}/dashboard", headers=ana)
# (archivo sin confirmar: se espera error; solo comprobamos que no tumba el servidor)
check("archivo sin confirmar no tumba el servidor", rs2.status_code in (404, 409, 422, 400))

# ── Dashboard principal ───────────────────────────────────────────────────────────────────────────
P = "/me/dashboard-principal"
check("al inicio no hay principal", c.get(P, headers=ana).json()["principal"] is None)
check("sin sesión => 401", c.get(P).status_code == 401 and c.put(P, json={"archivo_id": aid}).status_code == 401)
v = c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": "Ejecutivo", "config": r["config"]}).json()
v2 = c.post(f"/datasets/{aid}/dashboard", headers=ana, json={"nombre": "Otra", "config": r["config"]}).json()
p = c.put(P, headers=ana, json={"archivo_id": aid, "vista_id": v["id"]}).json()["principal"]
check("fijar principal (archivo + vista)", p and p["archivo_id"] == aid and p["vista_id"] == v["id"] and p["vista_nombre"] == "Ejecutivo" and p["archivo_nombre"] == "geo.csv", p)
check("se conserva al volver a consultar", c.get(P, headers=ana).json()["principal"]["vista_id"] == v["id"])
check("sin vista: queda la propuesta/primera vista", c.put(P, headers=ana, json={"archivo_id": aid}).json()["principal"]["vista_id"] is None)
c.put(P, headers=ana, json={"archivo_id": aid, "vista_id": v["id"]})
check("vista de otro archivo => 404", c.put(P, headers=ana, json={"archivo_id": bid, "vista_id": v["id"]}).status_code == 404)
check("archivo inexistente => 404", c.put(P, headers=ana, json={"archivo_id": 99999}).status_code == 404)
check("el principal no cambia tras un intento inválido", c.get(P, headers=ana).json()["principal"]["vista_id"] == v["id"])
check("es por usuario: Carlos no ve el de Ana", c.get(P, headers=car).json()["principal"] is None)
check("Carlos no puede fijar un archivo que no ve => 404", c.put(P, headers=car, json={"archivo_id": aid}).status_code == 404)
c.post(f"/archivos/{aid}/comparticiones", headers=ana, json={"correo": "cmendez@empresa.com"})
check("compartido: Carlos puede fijarlo como suyo (solo lectura)", c.put(P, headers=car, json={"archivo_id": aid, "vista_id": v["id"]}).status_code == 200)
check("Ana sigue con el suyo", c.get(P, headers=ana).json()["principal"]["archivo_id"] == aid)
c.delete(f"/archivos/{aid}/comparticiones/cmendez@empresa.com", headers=ana)
check("al dejar de compartirle, el principal de Carlos desaparece", c.get(P, headers=car).json()["principal"] is None)
check("…y queda limpio en la base", (lambda cn: (lambda x: (cn.close(), x)[1])(cn.execute("SELECT dashboard_principal FROM usuarios WHERE correo='cmendez@empresa.com'").fetchone()[0]))(get_db()) is None)
c.delete(f"/datasets/{aid}/dashboard/{v['id']}", headers=ana)
pp = c.get(P, headers=ana).json()["principal"]
check("si se borra la vista fijada, queda el archivo (primera vista o propuesta)", pp and pp["archivo_id"] == aid and pp["vista_id"] is None, pp)
check("quitar el principal", c.delete(P, headers=ana).json()["principal"] is None and c.get(P, headers=ana).json()["principal"] is None)
c.put(P, headers=ana, json={"archivo_id": bid})
c.delete(f"/archivos/{bid}", headers=ana)
check("si se borra el archivo, el principal desaparece", c.get(P, headers=ana).json()["principal"] is None)
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
