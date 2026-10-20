"""Proyectos: crear, renombrar, borrar, mover archivos, privacidad."""
import os, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
repo = os.path.abspath(REPO); sys.path.insert(0, os.path.join(repo, "backend"))
os.chdir(tempfile.mkdtemp(prefix="tachyon_pr_")); os.environ["SEED_DEMO_USERS"] = "1"
from fastapi.testclient import TestClient
import main
c = TestClient(main.app, raise_server_exceptions=False)
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {extra}" if (extra and not cond) else ""))
    if not cond: fallos.append(n)
def login(u, p):
    r = c.post("/auth/login", data={"username": u, "password": p}); return {"Authorization": f"Bearer {r.json()['access_token']}"}
ana = login("mrodriguez@empresa.com", "operador123"); car = login("cmendez@empresa.com", "operador123")
def crear(h, proyecto_id=None):
    filas = ["Fecha,Cliente,Monto"] + [f"2026-01-{(i % 28) + 1:02d},{'ABC'[i % 3]},{10 + i}" for i in range(20)]
    a = c.post("/datasets/analizar", headers=h, files={"file": ("v.csv", "\n".join(filas).encode(), "text/csv")}).json()
    r = c.post(f"/datasets/{a['archivo_id']}/confirmar", headers=h, json={"fila_encabezado": a["fila_encabezado"], "proyecto_id": proyecto_id,
        "columnas": [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre"]} for x in a["columnas"]]})
    return a["archivo_id"], r
check("sin proyectos al inicio", c.get("/proyectos", headers=ana).json() == [])
r = c.post("/proyectos", headers=ana, json={"nombre": "  Ventas   2026 "}); p1 = r.json()
check("crear proyecto (espacios normalizados)", r.status_code == 200 and p1["nombre"] == "Ventas 2026", r.text)
check("nombre repetido (sin importar mayúsculas) => 409", c.post("/proyectos", headers=ana, json={"nombre": "ventas 2026"}).status_code == 409)
check("nombre vacío => 422", c.post("/proyectos", headers=ana, json={"nombre": "   "}).status_code == 422)
check("nombre muy largo => 422", c.post("/proyectos", headers=ana, json={"nombre": "x" * 41}).status_code == 422)
check("otro usuario puede usar el mismo nombre", c.post("/proyectos", headers=car, json={"nombre": "Ventas 2026"}).status_code == 200)
p2 = c.post("/proyectos", headers=ana, json={"nombre": "Producción"}).json()
check("lista ordenada y solo propios", [p["nombre"] for p in c.get("/proyectos", headers=ana).json()] == ["Producción", "Ventas 2026"])
# archivos
a1, r = crear(ana, p1["id"]); check("guardar archivo directo en un proyecto", r.status_code == 200)
a2, r = crear(ana); check("archivo sin proyecto", r.status_code == 200)
a3, r = crear(ana, p1["id"] + 999); check("proyecto inexistente al confirmar => 404", r.status_code == 404)
a4, r = crear(ana, [p["id"] for p in c.get("/proyectos", headers=car).json()][0]); check("proyecto AJENO al confirmar => 404", r.status_code == 404)
ls = lambda q: sorted(x["id"] for x in c.get("/archivos" + q, headers=ana).json())
check("filtro por proyecto", ls(f"?proyecto={p1['id']}") == [a1])
check("filtro 'sin'", ls("?proyecto=sin") == [a2])
check("filtro inválido => 422", c.get("/archivos?proyecto=abc", headers=ana).status_code == 422)
check("contador de archivos", {p["nombre"]: p["num_archivos"] for p in c.get("/proyectos", headers=ana).json()} == {"Producción": 0, "Ventas 2026": 1})
check("mover a otro proyecto", c.put(f"/archivos/{a2}/proyecto", headers=ana, json={"proyecto_id": p2["id"]}).status_code == 200 and ls(f"?proyecto={p2['id']}") == [a2])
check("mover a proyecto ajeno => 404", c.put(f"/archivos/{a2}/proyecto", headers=ana, json={"proyecto_id": [p["id"] for p in c.get("/proyectos", headers=car).json()][0]}).status_code == 404)
check("mover archivo ajeno => 404", c.put(f"/archivos/{a1}/proyecto", headers=car, json={"proyecto_id": None}).status_code == 404)
# compartido: el otro lo ve, pero sin su proyecto, y el filtro no lo trae
c.post(f"/archivos/{a1}/comparticiones", headers=ana, json={"correo": "cmendez@empresa.com"})
v = [x for x in c.get("/archivos", headers=car).json() if x["id"] == a1]
check("compartido: el otro lo ve sin proyecto_id", len(v) == 1 and v[0]["proyecto_id"] is None)
check("compartido: no entra al filtro 'sin' del otro", a1 not in sorted(x["id"] for x in c.get("/archivos?proyecto=sin", headers=car).json()))
# renombrar / borrar
check("renombrar", c.patch(f"/proyectos/{p2['id']}", headers=ana, json={"nombre": "Calidad"}).status_code == 200)
check("renombrar al nombre de otro propio => 409", c.patch(f"/proyectos/{p2['id']}", headers=ana, json={"nombre": "Ventas 2026"}).status_code == 409)
check("renombrar ajeno => 404", c.patch(f"/proyectos/{p2['id']}", headers=car, json={"nombre": "X"}).status_code == 404)
check("borrar ajeno => 404", c.delete(f"/proyectos/{p2['id']}", headers=car).status_code == 404)
check("borrar proyecto conserva sus archivos", c.delete(f"/proyectos/{p2['id']}", headers=ana).status_code == 200 and a2 in ls("?proyecto=sin") and c.get(f"/datasets/{a2}/datos", headers=ana).status_code == 200)
check("borrar un archivo no toca el proyecto", c.delete(f"/archivos/{a1}", headers=ana).status_code == 200 and any(p["id"] == p1["id"] for p in c.get("/proyectos", headers=ana).json()))
print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
