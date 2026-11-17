"""Seguridad de cuentas: SECRET_KEY obligatoria en producción, cambio y restablecimiento de contraseña."""
import os, sys, tempfile, subprocess
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKEND = os.path.join(REPO, "backend"); sys.path.insert(0, BACKEND)
os.chdir(tempfile.mkdtemp(prefix="tachyon_seg_")); os.environ["SEED_DEMO_USERS"] = "1"
from fastapi.testclient import TestClient
import main
c = TestClient(main.app, raise_server_exceptions=False)
fallos = []
def check(n, cond, extra=""):
    print(("OK    " if cond else "FALLA ") + n + (f"  -> {extra}" if (extra and not cond) else ""))
    if not cond: fallos.append(n)
def entrar(u, p):
    return c.post("/auth/login", data={"username": u, "password": p})
def cab(token): return {"Authorization": f"Bearer {token}"}

# ── SECRET_KEY: en producción el servidor no arranca con la clave pública de desarrollo ──
def config(**env):
    limpio = {k: v for k, v in os.environ.items()
              if k not in ("SECRET_KEY", "DATABASE_URL", "SUPABASE_URL", "RENDER", "ENTORNO", "ALLOWED_ORIGINS")}
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", "import core.config as c; print(len(c.SECRET_KEY))"],
                       cwd=BACKEND, env={**limpio, **env}, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr
check("desarrollo sin SECRET_KEY arranca", config()[0] == 0)
for nombre, env in (("RENDER", {"RENDER": "true"}), ("DATABASE_URL", {"DATABASE_URL": "postgresql://x/y"}),
                    ("SUPABASE_URL", {"SUPABASE_URL": "https://x.supabase.co"}), ("ENTORNO=produccion", {"ENTORNO": "produccion"})):
    cod, salida = config(**env)
    check(f"producción ({nombre}) sin SECRET_KEY NO arranca", cod != 0 and "SECRET_KEY" in salida, salida[-200:])
cod, salida = config(RENDER="true", SECRET_KEY="k" * 48)
check("producción con SECRET_KEY arranca", cod == 0 and salida.strip().endswith("48"), salida[-200:])

# ── Contraseña temporal: quien recibe una cuenta debe cambiarla ──
admin = cab(entrar("admin@empresa.com", "admin123").json()["access_token"])
r = c.post("/usuarios", headers=admin, json={"correo": "nueva@empresa.com", "password": "temporal-123"})
check("el admin crea la cuenta", r.status_code == 200, r.text)
NUEVA = r.json()["id"]
check("contraseña de más de 72 bytes se rechaza al crear", c.post("/usuarios", headers=admin, json={"correo": "larga@empresa.com", "password": "x" * 73}).status_code == 422)
r = entrar("nueva@empresa.com", "temporal-123"); t1 = r.json()["access_token"]
check("primer ingreso: necesita_password", r.json()["usuario"]["necesita_password"] is True)
check("las cuentas existentes no quedan obligadas", c.get("/auth/me", headers=admin).json()["necesita_password"] is False)
fila = next(u for u in c.get("/usuarios", headers=admin).json() if u["id"] == NUEVA)
check("el admin ve que está pendiente (sin ver nada más)", fila["pendiente_password"] is True and "password_hash" not in fila and "debe_cambiar_password" not in fila)

cambio = lambda tok, actual, nueva: c.post("/auth/password", headers=cab(tok), json={"actual": actual, "nueva": nueva})
r = cambio(t1, "equivocada", "mi-clave-nueva-1")
check("contraseña actual incorrecta => 400 (no 401, para no cerrar la sesión)", r.status_code == 400, r.text)
check("nueva demasiado corta => 422", cambio(t1, "temporal-123", "corta").status_code == 422)
check("nueva igual a la actual => 422", cambio(t1, "temporal-123", "temporal-123").status_code == 422)
check("nueva de más de 72 bytes => 422", cambio(t1, "temporal-123", "ñ" * 40).status_code == 422)
check("sin sesión => 401", c.post("/auth/password", json={"actual": "a", "nueva": "b"}).status_code == 401)
r = cambio(t1, "temporal-123", "mi-clave-nueva-1")
check("cambio correcto", r.status_code == 200 and r.json()["usuario"]["necesita_password"] is False, r.text)
t2 = r.json()["access_token"]
check("el token anterior deja de valer", c.get("/auth/me", headers=cab(t1)).status_code == 401)
check("el token nuevo funciona", c.get("/auth/me", headers=cab(t2)).status_code == 200)
check("la contraseña anterior ya no entra", entrar("nueva@empresa.com", "temporal-123").status_code == 401)
r = entrar("nueva@empresa.com", "mi-clave-nueva-1")
check("la nueva sí, y ya no pide cambiarla", r.status_code == 200 and r.json()["usuario"]["necesita_password"] is False)

# ── Restablecer (olvidó su contraseña) ──
url = f"/usuarios/{NUEVA}/password"
check("un usuario normal no puede restablecer", c.post(url, headers=cab(t2), json={"password": "otra-clave-123"}).status_code == 403)
check("temporal corta => 422", c.post(url, headers=admin, json={"password": "corta"}).status_code == 422)
check("cuenta inexistente => 404", c.post("/usuarios/99999/password", headers=admin, json={"password": "otra-clave-123"}).status_code == 404)
yo = c.get("/auth/me", headers=admin).json()["id"]
check("el admin no se restablece a sí mismo por aquí", c.post(f"/usuarios/{yo}/password", headers=admin, json={"password": "otra-clave-123"}).status_code == 422)
r = c.post(url, headers=admin, json={"password": "temporal-456"})
check("el admin restablece", r.status_code == 200, r.text)
check("se cierran las sesiones de esa cuenta", c.get("/auth/me", headers=cab(t2)).status_code == 401)
check("la contraseña que tenía ya no entra", entrar("nueva@empresa.com", "mi-clave-nueva-1").status_code == 401)
r = entrar("nueva@empresa.com", "temporal-456")
check("entra con la temporal y debe cambiarla", r.status_code == 200 and r.json()["usuario"]["necesita_password"] is True)
check("la sesión del admin sigue viva", c.get("/auth/me", headers=admin).status_code == 200)

print("\nRESULTADO:", "TODO OK" if not fallos else f"{len(fallos)} fallo(s): {fallos}")
sys.exit(1 if fallos else 0)
