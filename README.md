# ProducciónApp

Panel de control para líneas de producción. Login + Dashboard con gráficas por día, semana y mes. Carga de archivos Excel (sin procesamiento por ahora).

---

## Requisitos

- Python 3.10 o superior
- Node.js 18 o superior

---

## Instalación y arranque

### 1. Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
python main.py
```

El backend corre en: http://localhost:8000
Documentación automática: http://localhost:8000/docs

### 2. Frontend (React + Vite)

En otra terminal:

```bash
cd frontend
npm install
npm run dev
```

La app corre en: http://localhost:5173

---

## Cuentas de prueba

| Correo | Contraseña | Rol |
|--------|-----------|-----|
| admin@empresa.com | admin123 | Administrador |
| jlopez@empresa.com | supervisor123 | Supervisor |

---

## Estructura del proyecto

```
produccion-app/
├── backend/
│   ├── main.py              # API completa (auth, dashboard, archivos)
│   ├── requirements.txt     # Dependencias Python
│   └── produccion.db        # Base de datos SQLite (se crea automático)
│
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── Login.jsx        # Pantalla de login
    │   │   ├── Dashboard.jsx    # Dashboard con gráficas
    │   │   ├── Archivos.jsx     # Carga de Excel
    │   │   └── Placeholders.jsx # Páginas futuras
    │   ├── components/
    │   │   ├── Sidebar.jsx      # Navegación lateral
    │   │   └── AppLayout.jsx    # Layout envolvente
    │   ├── context/
    │   │   └── AuthContext.jsx  # Manejo de sesión
    │   ├── services/
    │   │   └── api.js           # Cliente HTTP (axios)
    │   └── index.css            # Estilos globales (Tailwind)
    ├── tailwind.config.js
    ├── vite.config.js
    └── package.json
```

---

## Próximos pasos

- [ ] Parser de Excel con pandas (columnas a definir)
- [ ] Página de detalle por línea
- [ ] Generación de reportes PDF
- [ ] Gestión de usuarios (admin)
- [ ] Filtros por fecha en dashboard
