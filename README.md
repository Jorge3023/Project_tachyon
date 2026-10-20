# Project_Tachyon

Plataforma web para analizar **cualquier Excel o CSV**: sube un archivo, el sistema detecta el tipo de cada columna, tú lo revisas y queda guardado de forma privada, listo para consultarlo, compartirlo en solo lectura y (próximamente) armar dashboards a tu medida y exportarlos.

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

- Inicio de sesión con cuentas creadas por el administrador.
- Subida de cualquier Excel o CSV con detección automática de columnas y revisión manual.
- Plantillas guardadas: un archivo con las mismas columnas se interpreta solo.
- **Proyectos**: carpetas personales para agrupar archivos (se crean con “+” en la barra lateral; borrar un proyecto no borra sus archivos).
- Visor de datos por páginas con resumen por columna.
- **Dashboards editables por archivo**: propuesta automática según el tipo de cada columna y editor propio (ver abajo).
- Datos privados por usuario y compartir por correo (solo lectura).
- API REST desarrollada con FastAPI.
- Interfaz desarrollada con React y Tailwind CSS.

---

## 📁 Estructura del proyecto

```text
project_tachyon/
│
├── backend/
│   ├── main.py
│   ├── db.py
│   ├── storage.py
│   ├── requirements.txt
│   └── tachyon.db (solo en desarrollo; se genera automáticamente)
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

- [x] Detección automática de columnas en cualquier Excel/CSV.
- [x] Plantillas, privacidad por usuario y compartir por correo.
- [x] Editor de dashboards con gráficas propuestas según el tipo de columnas.
- [x] Pantalla de exportación (imagen, PDF, PowerPoint, CSV/Excel).
- [ ] Clasificadores y análisis asistido.

---

## 📝 Notas

- La base de datos SQLite se crea automáticamente durante la primera ejecución del backend.
- - Este proyecto se encuentra en desarrollo y puede recibir cambios en la estructura y funcionalidades.

---

## 👨‍💻 Autor

Proyecto de análisis de datos de propósito general (Excel/CSV).


## 🗺️ Imagenes

## Login

![Login](images/login.png)

## Dashboard editable (propuesta automática)

![Dashboard](images/dashboard.png)

## Mis archivos y proyectos

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
| `PARQUET_CACHE_MAX_MB` | Memoria para guardar los datasets abiertos recientemente y no bajarlos del Storage en cada gráfica (por defecto 40). |

**Frontend (build)**

| Variable | Para qué sirve |
|---|---|
| `VITE_API_URL` | URL del backend. En desarrollo usa `http://localhost:8000` por defecto. |
| `VITE_BASE` | Solo si se publica en una subcarpeta (ej. `/Project_tachyon/`). Normalmente vacío. |
| `VITE_TILES_URL` / `VITE_TILES_ATTRIBUTION` | Proveedor de mosaicos del mapa. Por defecto OpenStreetMap (gratis, con atribución, para uso moderado); para mucho tráfico usa uno con cuenta (MapTiler, Stadia, Mapbox…) con una URL tipo `https://…/{z}/{x}/{y}.png`. |

## Usuarios, privacidad y compartir

- **Cuentas:** el administrador crea cuentas desde *Usuarios* (correo + contraseña temporal). En su primer ingreso, cada persona elige su **nombre de usuario** (único, de 3 a 20 caracteres, no se cambia después).
- **Privacidad:** cada archivo (y lo que se calcula de él) es solo de quien lo subió. Ni el administrador ve los archivos de los demás.
- **Compartir:** el dueño puede compartir un archivo por correo electrónico (solo lectura). Si la persona aún no tiene cuenta, lo verá cuando entre con ese correo. Se puede dejar de compartir en cualquier momento.

## Cualquier Excel o CSV (datasets genéricos)

En **Mis archivos → Subir cualquier Excel o CSV** puedes subir `.xlsx`, `.xls`, `.csv` o `.tsv` (hasta 25 MB).

1. El sistema lee el archivo (elige la hoja con más datos, salta filas de título, detecta separador y codificación) y **propone el tipo de cada columna**: fecha, número, categoría, identificador, estado o texto libre.
2. Una pantalla de revisión te deja corregir hoja, fila de encabezados, nombre y tipo de cada columna (o ignorarla). Las dudosas salen marcadas como *Revisar*.
3. Al guardar se limpian los valores (`$1,234.50`, `1.234,5`, `17,3%`, fechas `dd/mm/aaaa`, números de serie de Excel) y se guarda el dataset tipado.
4. Si marcas **guardar como plantilla**, cualquier archivo futuro con las mismas columnas (aunque cambie el orden o se agregue alguna) se interpreta solo.

Los datasets siguen las mismas reglas de privacidad: solo los ve su dueño y quienes él elija por correo. Endpoints: `GET|POST /proyectos`, `PATCH|DELETE /proyectos/{id}`, `PUT /archivos/{id}/proyecto`, `POST /datasets/analizar`, `GET /datasets/{id}/analisis`, `POST /datasets/{id}/confirmar`, `GET /datasets/{id}/datos`, `GET|DELETE /plantillas`.


## Dashboards

Desde **Mis archivos → Dashboard** (o desde un proyecto) se abre el dashboard de un archivo:

- **Propuesta automática:** según los roles de las columnas se arman indicadores, evolución en el tiempo, circulares, barras, Pareto, dispersión, histograma, mapa de calor, **mapa geográfico** (si hay columnas de latitud y longitud) y una tabla. La métrica principal es el importe/monto antes que cantidades o promedios.
- **Modo edición** (solo el dueño): agrega, duplica, elimina y reordena gráficas: arrastra el asa ⠿ de cada tarjeta (con mouse o con el dedo) y las demás se acomodan con animación en tiempo real; también con las flechas ↑ ↓ del teclado; cambia el tipo, las columnas, la agregación (suma, promedio, conteo, mín., máx., mediana, únicos), el desglose, la granularidad de fechas, el ancho y el color; cada gráfica puede tener sus propios filtros.
- **Filtros globales** por fecha, rango numérico o categorías, y granularidad (día, semana, mes, trimestre, año).
- **Vistas:** puedes guardar varias por archivo (hasta 10) y cambiar entre ellas. Quien recibe el archivo compartido ve esas vistas en solo lectura y puede filtrar sin guardar.
- Cada gráfica tiene su versión **«Tabla»** (accesibilidad) y los colores siguen una paleta validada para daltonismo.

El navegador nunca recibe las filas ni manda fórmulas: manda una *configuración* que el servidor valida contra las columnas reales del archivo (agregaciones en lista blanca, límites de tamaño) y calcula con pandas, devolviendo solo resultados ya agregados. Endpoints: `GET /datasets/{id}/dashboard`, `POST /datasets/{id}/dashboard/datos`, `GET /datasets/{id}/valores`, `POST|PUT|DELETE /datasets/{id}/dashboard[/{vista}]`.

**Mapa geográfico:** puntos sobre un mapa real (Leaflet + OpenStreetMap) a partir de una columna de latitud (±90) y otra de longitud (±180). El tamaño del punto puede ser el número de filas o una métrica (suma, promedio…) y el color puede ir por categoría. Si hay más de 800 ubicaciones distintas, el servidor agrupa las cercanas en una cuadrícula (el navegador nunca recibe más de 800 puntos) y avisa cuántas filas hay en cuántos puntos; las coordenadas imposibles se descartan y se avisa. La rueda del mouse solo acerca el mapa después de hacer clic en él, y en el móvil un dedo desplaza la página (dos dedos mueven el mapa). Leaflet solo se descarga cuando el dashboard tiene un mapa. Todavía no convierte nombres de ciudades en coordenadas (no hay geocodificación): hacen falta las columnas de latitud y longitud.

**Dashboard principal:** con **☆ Hacer principal** cualquier usuario elige el dashboard (una vista guardada, o la propuesta de un archivo, también si se lo compartieron) que se abre al entrar; es una preferencia personal. Mientras haya uno, el resumen de archivos queda en **Resumen** en el menú. Endpoints: `GET|PUT|DELETE /me/dashboard-principal`; si el archivo se borra o se deja de compartir, el principal se limpia solo.

**Exportar:** el botón **Exportar** del dashboard abre una pantalla aparte (`/datos/:id/exportar`) con vista previa. Lo puede usar cualquiera que vea el archivo, también quien lo recibió compartido. Lleva los cambios sin guardar del editor y tiene sus propios filtros, que solo afectan a la exportación.
- **Imagen (PNG)**: una sola imagen con título, filtros y fecha, o una por gráfica en un ZIP.
- **PDF**: Carta o A4, horizontal o vertical; las gráficas se acomodan por filas sin partir ninguna entre páginas, con encabezado y «Página n de N».
- **PowerPoint**: portada, y varias gráficas por diapositiva o una por diapositiva. Cada diapositiva lleva el nombre del archivo como texto editable.
- **Excel**: hoja «Resumen» (archivo, vista, filtros), hoja «Datos» con las filas filtradas y una hoja con los números de cada gráfica. Hasta 50 000 filas.
- **CSV**: las filas filtradas, UTF-8 con marca (Excel muestra bien los acentos). Hasta 500 000 filas.

Imagen, PDF y PowerPoint se arman en el navegador fotografiando las mismas gráficas que se ven en pantalla (`html-to-image`, `jspdf`, `pptxgenjs`, `jszip`; se descargan solo al exportar). Excel y CSV los genera el servidor: `POST /datasets/{id}/exportar` con `{config, formato: "csv"|"xlsx", datos, graficas, widgets, vista}`. Los textos que empiezan con `=`, `+`, `-` o `@` se guardan como texto para que Excel no los ejecute como fórmulas. En el mapa exportado se conserva la atribución de OpenStreetMap, como exige su licencia; si los mosaicos no cargan, el mapa sale sin fondo y se avisa. En móviles se limita la nitidez para no agotar la memoria.

## Configurar Supabase (producción)

La aplicación guarda **usuarios, archivos, plantillas y permisos en PostgreSQL** y los **datos limpios y borradores en Supabase Storage** (formato Parquet). Sin estas variables usa SQLite y el disco local, solo apropiados para desarrollo.

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
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` solo crean el administrador **si no existe**: cambiar `ADMIN_PASSWORD` después no cambia la contraseña de una cuenta ya creada.

### Dónde se guarda cada cosa

| Dónde | Qué |
|---|---|
| **PostgreSQL** (pequeño) | Usuarios (contraseña cifrada), una fila por archivo con sus metadatos y resumen, plantillas y con quién se comparte cada archivo |
| **Storage** `datasets/{id}.parquet` | Los datos limpios de cada Excel/CSV genérico, en grupos de 10 000 filas (Parquet + zstd) |
| **Storage** `borradores/{id}.src` | El archivo original, solo mientras revisas las columnas (se borra al confirmar o cancelar) |

Al abrir **Ver datos** solo se lee del Parquet la página pedida (no el archivo completo) y el resumen por columna se calcula una sola vez, al confirmar.
