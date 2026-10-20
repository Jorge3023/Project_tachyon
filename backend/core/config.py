"""Configuración leída del entorno: clave de firma de sesiones, caducidad y orígenes permitidos (CORS)."""
import os
import warnings

# CORS: en producción define ALLOWED_ORIGINS con la(s) URL(s) del frontend, separadas por coma
# (ej. "https://tachyon.pages.dev"). Sin definirla se permite cualquier origen (solo para desarrollo).
ORIGENES_PERMITIDOS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# SECRET_KEY: define la variable de entorno SECRET_KEY en producción (>= 32 caracteres).
# Si no existe se usa una clave de desarrollo y se avisa en consola.
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = "clave-solo-para-desarrollo-no-usar-en-produccion-0000"
    warnings.warn("SECRET_KEY no definida: usando clave de desarrollo. Defínela en producción.")
ALGORITHM = "HS256"
TOKEN_HOURS = 8
