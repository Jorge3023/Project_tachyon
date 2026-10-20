"""Cuentas: foto de perfil (validación y privacidad) y eliminación de usuarios por el administrador."""
import os, sys, tempfile, struct, zlib
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
repo = os.path.abspath(REPO); sys.path.insert(0, os.path.join(repo, "backend"))
os.chdir(tempfile.mkdtemp(prefix="tachyon_cu_")); os.environ["SEED_DEMO_USERS"] = "1"
from fastapi.testclient import TestClient
import main
from core import storage
from core.db import get_db
c = TestClient(main.app, raise_server_exceptions=False)
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {extra}" if (extra and not cond) else ""))
    if not cond: fallos.append(n)
def login(u, p):
    r = c.post("/auth/login", data={"username": u, "password": p}); return {"Authorization": f"Bearer {r.json()['access_token']}"}
admin = login("admin@empresa.com", "admin123"); ana = login("mrodriguez@empresa.com", "operador123"); car = login("cmendez@empresa.com", "operador123")
ids = {u["correo"]: u["id"] for u in c.get("/usuarios", headers=admin).json()}
ANA, CAR, ADM = ids["mrodriguez@empresa.com"], ids["cmendez@empresa.com"], ids["admin@empresa.com"]

def png():
    raw = b"\x00\xff\x00\x00" * 1; crc = lambda t, d: struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + crc(t, d)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + ch(b"IEND", b"")
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 200

# ── Foto de perfil ──
check("sin foto al inicio (avatar_v = 0)", c.get("/auth/me", headers=ana).json()["avatar_v"] == 0)
check("sin foto => 404", c.get(f"/usuarios/{ANA}/avatar", headers=ana).status_code == 404)
r = c.put("/auth/avatar", headers=ana, files={"file": ("a.png", png(), "image/png")})
check("subir PNG válido", r.status_code == 200 and r.json()["avatar_v"] > 0, r.text)
v1 = r.json()["avatar_v"]
check("/auth/me trae la versión", c.get("/auth/me", headers=ana).json()["avatar_v"] == v1)
g = c.get(f"/usuarios/{ANA}/avatar", headers=ana)
check("el dueño descarga su foto con el tipo correcto", g.status_code == 200 and g.headers["content-type"] == "image/png" and g.content == png())
check("el admin también la ve", c.get(f"/usuarios/{ANA}/avatar", headers=admin).status_code == 200)
check("otro usuario NO la ve (404)", c.get(f"/usuarios/{ANA}/avatar", headers=car).status_code == 404)
check("sin sesión => 401", c.get(f"/usuarios/{ANA}/avatar").status_code == 401)
check("JPEG válido reemplaza", c.put("/auth/avatar", headers=ana, files={"file": ("a.jpg", JPG, "image/jpeg")}).status_code == 200)
check("tipo según los bytes, no el nombre", c.get(f"/usuarios/{ANA}/avatar", headers=ana).headers["content-type"] == "image/jpeg")
check("un .exe disfrazado de imagen => 422", c.put("/auth/avatar", headers=ana, files={"file": ("a.png", b"MZ\x90\x00" + b"\x00" * 100, "image/png")}).status_code == 422)
check("un SVG (puede llevar scripts) => 422", c.put("/auth/avatar", headers=ana, files={"file": ("a.svg", b"<svg onload='x()'></svg>", "image/svg+xml")}).status_code == 422)
check("demasiado pesada => 413", c.put("/auth/avatar", headers=ana, files={"file": ("a.jpg", JPG + b"\x00" * 310000, "image/jpeg")}).status_code == 413)
check("la fallida no cambió la foto", c.get(f"/usuarios/{ANA}/avatar", headers=ana).headers["content-type"] == "image/jpeg")
check("el listado de admin trae avatar_v", {u["id"]: u["avatar_v"] for u in c.get("/usuarios", headers=admin).json()}[ANA] > 0)
r = c.delete("/auth/avatar", headers=ana)
check("quitar foto", r.status_code == 200 and r.json()["avatar_v"] == 0 and c.get(f"/usuarios/{ANA}/avatar", headers=ana).status_code == 404)

# ── Eliminar cuentas ──
def crear(h, nombre="v.csv"):
    filas = ["Fecha,Cliente,Monto"] + [f"2026-01-{(i % 28) + 1:02d},{'ABC'[i % 3]},{10 + i}" for i in range(20)]
    a = c.post("/datasets/analizar", headers=h, files={"file": (nombre, "\n".join(filas).encode(), "text/csv")}).json()
    c.post(f"/datasets/{a['archivo_id']}/confirmar", headers=h, json={"fila_encabezado": a["fila_encabezado"],
        "columnas": [{"nombre": x["nombre"], "rol": x["rol"], "nombre_mostrar": x["nombre"]} for x in a["columnas"]]})
    return a["archivo_id"]
c.put("/auth/avatar", headers=car, files={"file": ("a.png", png(), "image/png")})
a_car = crear(car); a_car2 = crear(car); a_ana = crear(ana)
c.post("/proyectos", headers=car, json={"nombre": "Mío"})
c.post(f"/archivos/{a_car}/comparticiones", headers=car, json={"correo": "mrodriguez@empresa.com"})     # Carlos comparte con Ana
c.post(f"/archivos/{a_ana}/comparticiones", headers=ana, json={"correo": "cmendez@empresa.com"})        # Ana comparte con Carlos
c.get(f"/datasets/{a_car}/dashboard", headers=car)
check("Ana ve el archivo compartido por Carlos", a_car in [x["id"] for x in c.get("/archivos", headers=ana).json()])
check("el archivo existe en el almacenamiento", storage.existe(f"datasets/{a_car}.parquet"))

check("operador no puede eliminar cuentas => 403", c.delete(f"/usuarios/{CAR}", headers=ana).status_code == 403)
check("el admin no puede eliminarse a sí mismo => 422", c.delete(f"/usuarios/{ADM}", headers=admin).status_code == 422)
check("usuario inexistente => 404", c.delete("/usuarios/9999", headers=admin).status_code == 404)
r = c.delete(f"/usuarios/{CAR}", headers=admin)
check("el admin elimina a Carlos (2 archivos)", r.status_code == 200 and r.json()["archivos_eliminados"] == 2, r.text)
check("ya no aparece en la lista", CAR not in [u["id"] for u in c.get("/usuarios", headers=admin).json()])
check("su sesión deja de valer", c.get("/auth/me", headers=car).status_code == 401)
check("no puede volver a entrar", c.post("/auth/login", data={"username": "cmendez@empresa.com", "password": "operador123"}).status_code == 401)
check("sus archivos desaparecen del almacenamiento", not storage.existe(f"datasets/{a_car}.parquet") and not storage.existe(f"datasets/{a_car2}.parquet"))
check("su foto desaparece del almacenamiento", not storage.existe(f"avatares/{CAR}"))
check("Ana ya no ve lo que Carlos compartió", a_car not in [x["id"] for x in c.get("/archivos", headers=ana).json()])
check("lo de Ana sigue intacto", a_ana in [x["id"] for x in c.get("/archivos", headers=ana).json()] and storage.existe(f"datasets/{a_ana}.parquet"))
conn = get_db()
try:
    n = lambda q, *p: conn.execute(q, p).fetchone()["n"]
    check("sin filas huérfanas (archivos, proyectos, dashboards)",
          n("SELECT COUNT(*) AS n FROM archivos WHERE subido_por=?", CAR) == 0 and n("SELECT COUNT(*) AS n FROM proyectos WHERE owner_id=?", CAR) == 0
          and n("SELECT COUNT(*) AS n FROM dashboards WHERE owner_id=?", CAR) == 0)
    check("sin accesos compartidos ligados a su correo ni a su id",
          n("SELECT COUNT(*) AS n FROM comparticiones WHERE lower(correo)=?", "cmendez@empresa.com") == 0
          and n("SELECT COUNT(*) AS n FROM comparticiones WHERE compartido_por=?", CAR) == 0)
finally:
    conn.close()
# quien se registre luego con ese correo no hereda nada
r = c.post("/usuarios", headers=admin, json={"correo": "cmendez@empresa.com", "password": "otraclave123"}); nuevo = login("cmendez@empresa.com", "otraclave123")
check("recrear la cuenta empieza de cero (sin archivos ni foto)", r.status_code == 200 and c.get("/archivos", headers=nuevo).json() == [] and c.get("/auth/me", headers=nuevo).json()["avatar_v"] == 0)

print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
