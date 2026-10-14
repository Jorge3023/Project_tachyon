"""
Almacenamiento de archivos con dos destinos y la misma interfaz:

  - Disco local (por defecto): carpeta DATA_DIR (por defecto, el directorio actual).
  - Supabase Storage (producción): se activa con SUPABASE_URL + SUPABASE_SECRET_KEY (+ SUPABASE_BUCKET).

En hosts con disco efímero (Render gratis) el disco local se borra al reiniciar; por eso en producción
los datos limpios, los reportes y los borradores van a Supabase Storage.
"""
import os
from urllib.parse import quote

import httpx

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
# Se acepta SUPABASE_SERVICE_KEY como nombre alterno (clave `service_role` antigua)
SUPABASE_KEY = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or "").strip()
SUPABASE_BUCKET = (os.getenv("SUPABASE_BUCKET") or "datasets").strip()
ES_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)
DATA_DIR = os.getenv("DATA_DIR", ".")


class ErrorAlmacenamiento(Exception):
    pass


def _ruta_segura(ruta: str) -> str:
    ruta = ruta.replace("\\", "/").lstrip("/")
    if ".." in ruta.split("/") or not ruta:
        raise ErrorAlmacenamiento(f"Ruta no válida: {ruta!r}")
    return ruta


# ───────────────────────────── disco local ─────────────────────────────
def _local(ruta: str) -> str:
    return os.path.join(DATA_DIR, _ruta_segura(ruta))


# ───────────────────────────── Supabase Storage ─────────────────────────────
_cliente = None


def _http() -> httpx.Client:
    global _cliente
    if _cliente is None:
        _cliente = httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
    return _cliente


def _cabeceras(extra=None) -> dict:
    # Las claves nuevas (sb_secret_...) van solo en `apikey`; las antiguas (JWT, empiezan con "eyJ") también como Bearer.
    h = {"apikey": SUPABASE_KEY}
    if SUPABASE_KEY.startswith("eyJ"):
        h["Authorization"] = f"Bearer {SUPABASE_KEY}"
    if extra:
        h.update(extra)
    return h


def _url(ruta: str, autenticado=False) -> str:
    base = f"{SUPABASE_URL}/storage/v1/object"
    if autenticado:
        base += "/authenticated"
    return f"{base}/{quote(SUPABASE_BUCKET)}/{quote(_ruta_segura(ruta))}"


def _verificar(r: httpx.Response, accion: str):
    if r.status_code >= 400:
        raise ErrorAlmacenamiento(f"Supabase Storage ({accion}) respondió {r.status_code}: {r.text[:200]}")


# ───────────────────────────── interfaz pública ─────────────────────────────
def modo() -> str:
    return "supabase" if ES_SUPABASE else "local"


def put(ruta: str, datos: bytes, content_type: str = "application/octet-stream"):
    if ES_SUPABASE:
        try:
            r = _http().post(_url(ruta), content=datos,
                             headers=_cabeceras({"Content-Type": content_type, "x-upsert": "true"}))
        except httpx.HTTPError as e:
            raise ErrorAlmacenamiento(f"No se pudo conectar con Supabase Storage: {e}")
        _verificar(r, "subir")
        return
    destino = _local(ruta)
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    tmp = destino + ".tmp"
    with open(tmp, "wb") as f:
        f.write(datos)
    os.replace(tmp, destino)


def get(ruta: str) -> bytes:
    """Devuelve el contenido, o lanza FileNotFoundError si no existe."""
    if ES_SUPABASE:
        try:
            r = _http().get(_url(ruta, autenticado=True), headers=_cabeceras())
        except httpx.HTTPError as e:
            raise ErrorAlmacenamiento(f"No se pudo conectar con Supabase Storage: {e}")
        if r.status_code == 404 or (r.status_code == 400 and "not found" in r.text.lower()):
            raise FileNotFoundError(ruta)
        _verificar(r, "descargar")
        return r.content
    with open(_local(ruta), "rb") as f:
        return f.read()


def existe(ruta: str) -> bool:
    try:
        get(ruta)
        return True
    except FileNotFoundError:
        return False


def delete(ruta: str):
    """Borra si existe; si no existe no es un error."""
    if ES_SUPABASE:
        try:
            r = _http().delete(_url(ruta), headers=_cabeceras())
        except httpx.HTTPError as e:
            raise ErrorAlmacenamiento(f"No se pudo conectar con Supabase Storage: {e}")
        if r.status_code in (404,):
            return
        _verificar(r, "borrar")
        return
    try:
        os.remove(_local(ruta))
    except FileNotFoundError:
        pass
