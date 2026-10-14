# Project_Tachyon

Aplicación web para monitoreo y gestión de líneas de producción.

Incluye autenticación de usuarios, dashboard con métricas visuales y módulo de carga de archivos Excel preparado para futuras funcionalidades de análisis y procesamiento de datos.

---

## 🚀 Tecnologías utilizadas

### Backend
- FastAPI
- SQLite
- Pandas
- Python 3.10+

### Frontend
- React
- Vite
- Tailwind CSS
- Axios
- Node.js 18+

---

## 📋 Requisitos

Antes de ejecutar el proyecto asegúrate de tener instalado:

- Python 3.10 o superior
- Node.js 18 o superior
- npm

---

### 2. Configurar el Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

El backend estará disponible en:

```text
http://localhost:8000
```

Documentación automática de la API:

```text
http://localhost:8000/docs
```

---

### 3. Configurar el Frontend

Abrir una nueva terminal:

```bash
cd frontend
npm install
npm run dev
```

La aplicación estará disponible en:

```text
http://localhost:5173
```

---

## ✨ Funcionalidades actuales

- Inicio de sesión de usuarios.
- Dashboard con indicadores visuales.
- Métricas por día, semana y mes.
- Carga de archivos Excel.
- API REST desarrollada con FastAPI.
- Interfaz desarrollada con React y Tailwind CSS.

---

## 📁 Estructura del proyecto

```text
produccion-app/
│
├── backend/
│   ├── main.py
│   ├── excel_parser.py
│   ├── requirements.txt
│   └── produccion.db (se genera automáticamente)
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── context/
│   │   ├── services/
│   │   └── index.css
│   │
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
│
└── README.md
```

---

## Próximas funcionalidades

- [x] Procesamiento automático de archivos Excel.
- [ ] Generación de reportes PDF.
- [ ] Gestión avanzada de usuarios.
- [ ] Filtros por rango de fechas.
- [ ] Indicadores por línea de producción.
- [ ] Exportación de métricas.

---

## 📝 Notas

- La base de datos SQLite se crea automáticamente durante la primera ejecución del backend.
- Los archivos Excel cargados actualmente se almacenan para futuras funcionalidades de procesamiento.
- Este proyecto se encuentra en desarrollo y puede recibir cambios en la estructura y funcionalidades.

---

## 👨‍💻 Autor

Desarrollado como proyecto de gestión y monitoreo de producción


## 🗺️ Imagenes

## Login

![Login](images/login.png)

## Dashboard Principal

![Dashboard](images/dashboard.png)

## Módulo de Carga de Excel

![Archivos](images/archivos.png)

## Variables de entorno

**Backend (Render u otro host)**

| Variable | Para qué sirve |
|---|---|
| `SECRET_KEY` | Clave para firmar los tokens JWT (mínimo 32 caracteres). **Obligatoria en producción.** |
| `ALLOWED_ORIGINS` | URL(s) del frontend permitidas por CORS, separadas por coma. Ej: `https://tachyon.pages.dev` |
| `SEED_DEMO_USERS` | `1` crea cuentas de demostración con contraseñas públicas. **Solo para desarrollo local;** por defecto no se crean. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Crean el administrador inicial (contraseña de 8+ caracteres). **Necesarias** si no usas cuentas de demostración. |
| `DATABASE_URL` | Cadena de conexión de PostgreSQL (Supabase). Si no se define se usa SQLite local, que **se pierde** en hosts con disco efímero como Render gratis. |
| `SUPABASE_URL` | URL del proyecto de Supabase (`https://xxxx.supabase.co`). |
| `SUPABASE_SECRET_KEY` | Clave secreta de Supabase (`sb_secret_...`) para guardar archivos en Storage. Solo en el servidor, nunca en el frontend ni en Git. |
| `SUPABASE_BUCKET` | Nombre del bucket privado de Storage. Por defecto `datasets`. |
| `DB_POOL_MAX` | Conexiones máximas a la base de datos (por defecto 5). |

**Frontend (build)**

| Variable | Para qué sirve |
|---|---|
| `VITE_API_URL` | URL del backend. En desarrollo usa `http://localhost:8000` por defecto. |
| `VITE_BASE` | Solo si se publica en una subcarpeta (ej. `/Project_tachyon/`). Normalmente vacío. |

## Usuarios, privacidad y compartir

- **Cuentas:** el administrador crea cuentas desde *Usuarios* (correo + contraseña temporal). En su primer ingreso, cada persona elige su **nombre de usuario** (único, de 3 a 20 caracteres, no se cambia después).
- **Privacidad:** cada archivo (y lo que se calcula de él en el dashboard) es solo de quien lo subió. Ni el administrador ve los archivos de los demás.
- **Compartir:** el dueño puede compartir un archivo por correo electrónico (solo lectura). Si la persona aún no tiene cuenta, lo verá cuando entre con ese correo. Se puede dejar de compartir en cualquier momento.

## Cualquier Excel o CSV (datasets genéricos)

En **Mis archivos → Subir cualquier Excel o CSV** puedes subir `.xlsx`, `.xls`, `.csv` o `.tsv` (hasta 25 MB).

1. El sistema lee el archivo (elige la hoja con más datos, salta filas de título, detecta separador y codificación) y **propone el tipo de cada columna**: fecha, número, categoría, identificador, estado o texto libre.
2. Una pantalla de revisión te deja corregir hoja, fila de encabezados, nombre y tipo de cada columna (o ignorarla). Las dudosas salen marcadas como *Revisar*.
3. Al guardar se limpian los valores (`$1,234.50`, `1.234,5`, `17,3%`, fechas `dd/mm/aaaa`, números de serie de Excel) y se guarda el dataset tipado.
4. Si marcas **guardar como plantilla**, cualquier archivo futuro con las mismas columnas (aunque cambie el orden o se agregue alguna) se interpreta solo.

Los datasets siguen las mismas reglas de privacidad: solo los ve su dueño y quienes él elija por correo. Endpoints: `POST /datasets/analizar`, `GET /datasets/{id}/analisis`, `POST /datasets/{id}/confirmar`, `GET /datasets/{id}/datos`, `GET|DELETE /plantillas`.


## Configurar Supabase (producción)

La aplicación guarda **usuarios, archivos, plantillas y permisos en PostgreSQL** y los **datos limpios, reportes y borradores en Supabase Storage** (formato Parquet). Sin estas variables usa SQLite y el disco local, solo apropiados para desarrollo.

1. En [supabase.com](https://supabase.com) crea un proyecto. Anota la contraseña de la base de datos en un gestor de contraseñas.
2. **Storage → New bucket**: nombre `datasets`, **privado** (sin marcar "Public bucket").
3. **Connect** (arriba en el panel) → **Session pooler** → copia la cadena y sustituye `[YOUR-PASSWORD]` por tu contraseña. Usa el *session pooler* (no la conexión directa): la directa solo funciona por IPv6 y Render gratis usa IPv4. Si la contraseña tiene símbolos como `@`, `#`, `?` o `&`, codifícalos (por ejemplo `@` → `%40`).
4. **Settings → API Keys**: copia la *Project URL* y la clave **secret** (`sb_secret_...`).
5. En Render → **Environment** define `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY` y, si cambiaste el nombre del bucket, `SUPABASE_BUCKET`. Define también `ADMIN_EMAIL` y `ADMIN_PASSWORD` (la base nueva empieza vacía).
6. Entra como administrador → **Usuarios → Estado del sistema → Comprobar ahora**. Deben aparecer en verde *PostgreSQL (Supabase)* y *Supabase Storage*.

Notas:
- Las tablas se crean solas al arrancar, con la seguridad por filas activada y sin acceso para los roles públicos de Supabase (`anon`, `authenticated`): solo este servidor puede leerlas.
- La clave `sb_secret_` da acceso total a tu proyecto: no la subas a Git ni la pegues en el chat. Si se filtra, genera otra en *Settings → API Keys*.
- Si la clave nueva fallara en Storage, la clave antigua `service_role` (empieza con `eyJ`) también funciona en `SUPABASE_SECRET_KEY`.
- Plan gratis de Supabase: 500 MB de base de datos, 1 GB de archivos y el proyecto se pausa tras una semana sin uso.
- Los datos que ya estuvieran en el SQLite de Render **no se migran** (ese disco es efímero).
