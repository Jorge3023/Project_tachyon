"""Configuración leída del entorno: clave de firma de sesiones, caducidad y orígenes permitidos (CORS)."""
import os
import warnings

# CORS: en producción define ALLOWED_ORIGINS con la(s) URL(s) del frontend, separadas por coma
# (ej. "https://tachyon.pages.dev"). Sin definirla se permite cualquier origen (solo para desarrollo).
ORIGENES_PERMITIDOS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# SECRET_KEY: define la variable de entorno SECRET_KEY en producción (>= 32 caracteres).
# Si no existe se usa una clave de desarrollo y se avisa en consola.
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

# Se considera producción cualquier entorno con base de datos o almacenamiento reales, un host conocido,
# o ENTORNO=produccion. Ahí la clave de desarrollo (que es pública: está en este repositorio) permitiría
# a cualquiera fabricar una sesión de administrador, así que el servidor no arranca sin una clave propia.
EN_PRODUCCION = bool(os.getenv("DATABASE_URL") or os.getenv("SUPABASE_URL") or os.getenv("RENDER")
                     or os.getenv("ENTORNO", "").strip().lower() in ("produccion", "producción", "production"))
if not SECRET_KEY:
    if EN_PRODUCCION:
        raise RuntimeError(
            "Falta la variable de entorno SECRET_KEY. Sin ella las sesiones se firmarían con una clave pública. "
            "Genera una con:  python -c \"import secrets; print(secrets.token_urlsafe(48))\"  y defínela en tu hosting.")
    SECRET_KEY = "clave-solo-para-desarrollo-no-usar-en-produccion-0000"
    warnings.warn("SECRET_KEY no definida: usando clave de desarrollo (solo válido en tu computadora).")
elif EN_PRODUCCION and len(SECRET_KEY) < 32:
    warnings.warn("SECRET_KEY tiene menos de 32 caracteres: usa una más larga (ver backend/.env.example).")
if EN_PRODUCCION and "*" in ORIGENES_PERMITIDOS:
    warnings.warn("ALLOWED_ORIGINS no está definida: la API acepta peticiones desde cualquier sitio. "
                  "Define la URL de tu frontend.")
ALGORITHM = "HS256"
TOKEN_HOURS = 8
