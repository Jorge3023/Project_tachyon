"""Prueba del detector con archivos sintéticos de formatos muy distintos.
Uso: python3 -I test_detector.py <repo>"""
import io, sys, os, random
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(REPO, "backend"))
import numpy as np, pandas as pd
from servicios import detector as D

random.seed(7); np.random.seed(7)
N = 300
fechas = [datetime(2026, 1, 1) + timedelta(days=int(i % 90), hours=int(i % 24)) for i in range(N)]
clientes = [f"Cliente {c}" for c in "ABCDEFGHIJKLMNOPQRST"]
nombres = [f"Empleado Apellido{i}" for i in range(N)]
casos = []   # (nombre_archivo, bytes, esperado{col: roles_aceptables}, hoja_esperada, fila_esperada)

def xlsx(frames, filas_arriba=0, hojas=None):
    """frames: dict hoja->df. filas_arriba: filas de título antes de la tabla."""
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as w:
        for h, df in frames.items():
            df.to_excel(w, sheet_name=h, index=False, startrow=filas_arriba if h == list(frames)[-1] else 0)
            if filas_arriba and h == list(frames)[-1]:
                ws = w.sheets[h]
                ws["A1"] = "Reporte mensual de ventas - Sucursal Norte"
                ws["A2"] = "Generado por Finanzas"
    return b.getvalue()

# 1) Ventas en español con filas de título arriba
v = pd.DataFrame({
    "Fecha": fechas, "Folio": [f"F-{i:05d}" for i in range(N)],
    "Cliente": np.random.choice(clientes, N), "Producto": np.random.choice(list("PQRSTUVW"), N),
    "Región": np.random.choice(["Norte", "Sur", "Centro", "Occidente"], N),
    "Cantidad": np.random.randint(1, 50, N), "Precio Unitario": np.round(np.random.uniform(10, 900, N), 2),
    "Total": np.round(np.random.uniform(100, 20000, N), 2),
    "Estatus": np.random.choice(["Pagado", "Pendiente", "Cancelado"], N),
    "Comentarios": [f"Cliente solicitó entrega especial número {i} con instrucciones detalladas del pedido" for i in range(N)],
})
casos.append(("ventas_es_titulos.xlsx", xlsx({"Ventas": v}, filas_arriba=3),
    {"Fecha": {"fecha"}, "Folio": {"identificador"}, "Cliente": {"categoria"}, "Producto": {"categoria"},
     "Región": {"categoria"}, "Cantidad": {"numero"}, "Precio Unitario": {"numero"}, "Total": {"numero"},
     "Estatus": {"estado"}, "Comentarios": {"texto"}}, "Ventas", 2))

# 2) Producción en inglés (CSV coma, utf-8)
p = pd.DataFrame({"DateTime": fechas, "ProductID2": np.random.choice(["A-100", "A-200", "B-300"], N),
                  "Result": np.random.choice(["Passed", "Failed"], N, p=[.9, .1]),
                  "Equipment": np.random.choice(["SMT-1", "SMT-2"], N), "Shift": np.random.choice([1, 2, 3], N),
                  "Qty": np.random.randint(1, 5, N)})
casos.append(("produccion.csv", p.to_csv(index=False).encode(),
    {"DateTime": {"fecha"}, "ProductID2": {"categoria", "identificador"}, "Result": {"estado"},
     "Equipment": {"categoria"}, "Shift": {"categoria"}, "Qty": {"numero"}}, None, 0))

# 3) CSV ; latin-1, coma decimal, fechas dd/mm/aaaa como texto, porcentaje
s = pd.DataFrame({"Fecha": [f.strftime("%d/%m/%Y") for f in fechas], "Sucursal": np.random.choice(["Monterrey", "Guadalajara", "Puebla", "Mérida"], N),
                  "Ventas": [f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") for x in np.random.uniform(1000, 90000, N)],
                  "Margen %": [f"{x:.1f}%".replace(".", ",") for x in np.random.uniform(5, 40, N)],
                  "Empleado": nombres})
casos.append(("ventas_mx.csv", s.to_csv(index=False, sep=";").encode("latin-1"),
    {"Fecha": {"fecha"}, "Sucursal": {"categoria"}, "Ventas": {"numero"}, "Margen %": {"numero"}, "Empleado": {"identificador", "texto"}}, None, 0))

# 4) Moneda como texto con $ y miles
m = pd.DataFrame({"Fecha de pedido": [f.strftime("%Y-%m-%d") for f in fechas], "Pedido": [f"PED-{i}" for i in range(N)],
                  "Monto": [f"${x:,.2f}" for x in np.random.uniform(100, 99999, N)],
                  "Descuento": [f"{x:.0f}%" for x in np.random.uniform(0, 30, N)],
                  "Canal": np.random.choice(["Web", "Tienda", "Telefono"], N)})
casos.append(("pedidos_moneda.xlsx", xlsx({"Pedidos": m}),
    {"Fecha de pedido": {"fecha"}, "Pedido": {"identificador"}, "Monto": {"numero"}, "Descuento": {"numero"}, "Canal": {"categoria"}}, "Pedidos", 0))

# 5) Libro con hoja de notas primero y datos en la segunda; Recursos Humanos
rh = pd.DataFrame({"ID Empleado": range(1001, 1001 + N), "Nombre": nombres,
                   "Departamento": np.random.choice(["Ventas", "TI", "RH", "Operaciones", "Finanzas"], N),
                   "Fecha ingreso": [datetime(2015, 1, 1) + timedelta(days=int(d)) for d in np.random.randint(0, 3000, N)],
                   "Salario": np.round(np.random.uniform(9000, 60000, N), 0), "Edad": np.random.randint(20, 60, N),
                   "Activo": np.random.choice(["Sí", "No"], N, p=[.85, .15])})
notas = pd.DataFrame({"Notas": ["Datos confidenciales", "Actualizado octubre"]})
b = io.BytesIO()
with pd.ExcelWriter(b, engine="openpyxl") as w:
    notas.to_excel(w, sheet_name="Notas", index=False); rh.to_excel(w, sheet_name="Plantilla", index=False)
casos.append(("rh_multihoja.xlsx", b.getvalue(),
    {"ID Empleado": {"identificador"}, "Nombre": {"identificador", "texto"}, "Departamento": {"categoria"},
     "Fecha ingreso": {"fecha"}, "Salario": {"numero"}, "Edad": {"numero"}, "Activo": {"estado"}}, "Plantilla", 0))

# 6) Códigos con ceros y fechas como número de serie de Excel
z = pd.DataFrame({"Fecha": [(datetime(2026, 1, 1) + timedelta(days=int(i % 60)) - datetime(1899, 12, 30)).days for i in range(N)],
                  "Código": [f"{i % 40:05d}" for i in range(N)], "Piezas": np.random.randint(1, 200, N),
                  "Almacén": np.random.choice(["A1", "A2", "B1"], N)})
casos.append(("inventario_serie.xlsx", xlsx({"Inv": z}),
    {"Fecha": {"fecha"}, "Código": {"identificador", "categoria"}, "Piezas": {"numero"}, "Almacén": {"categoria"}}, "Inv", 0))

# 7) Sin encabezado (solo números)
sin = pd.DataFrame(np.random.rand(60, 4).round(3))
casos.append(("sin_encabezado.csv", sin.to_csv(index=False, header=False).encode(), {}, None, None))

# 8) TSV con muchas columnas numéricas (sensores) y una fecha
sn = pd.DataFrame({"timestamp": [(datetime(2026, 3, 1) + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(N)],
                   "temp_c": np.random.normal(60, 5, N).round(2), "presion_kpa": np.random.normal(101, 2, N).round(2),
                   "vibracion": np.random.normal(.5, .1, N).round(3), "maquina": np.random.choice(["M1", "M2"], N)})
casos.append(("sensores.tsv", sn.to_csv(index=False, sep="\t").encode(),
    {"timestamp": {"fecha"}, "temp_c": {"numero"}, "presion_kpa": {"numero"}, "vibracion": {"numero"}, "maquina": {"categoria"}}, None, 0))

tot = ok = 0
fallas = []
for nombre, datos, esperado, hoja_esp, fila_esp in casos:
    try:
        r = D.leer_archivo(datos, nombre)
    except Exception as e:
        print(f"[{nombre}] ERROR de lectura: {e}"); fallas.append(nombre); continue
    df, perf = r["df"], None
    perf = {x["nombre"]: x for x in D.perfilar_columnas(df)}
    linea = f"[{nombre}] hoja={r['hoja']!r} fila_enc={r['fila_encabezado']} filas={len(df)} cols={len(df.columns)}"
    if r["sin_encabezado"]: linea += " SIN_ENCABEZADO"
    print(linea)
    if hoja_esp and r["hoja"] != hoja_esp:
        print(f"   FALLA hoja: esperaba {hoja_esp}"); fallas.append((nombre, "hoja"))
    if fila_esp is not None and r["fila_encabezado"] != fila_esp and not r["sin_encabezado"]:
        print(f"   FALLA fila encabezado: esperaba {fila_esp}"); fallas.append((nombre, "fila"))
    for col, aceptables in esperado.items():
        tot += 1
        x = perf.get(col)
        if not x:
            print(f"   FALLA columna ausente: {col!r} (hay {list(perf)})"); fallas.append((nombre, col)); continue
        bien = x["rol"] in aceptables
        ok += bien
        marca = "ok " if bien else "MAL"
        rev = " revisar" if x["confianza"] < D.UMBRAL_REVISAR else ""
        print(f"   {marca} {col:18s} -> {x['rol']:13s} conf={x['confianza']:.2f}{rev}  ({x['razon']})")
        if not bien: fallas.append((nombre, col))

# limpieza: tipos reales
print()
r = D.leer_archivo(casos[2][1], "ventas_mx.csv")
perf = D.perfilar_columnas(r["df"])
limpio = D.aplicar_esquema(r["df"], [{"nombre": x["nombre"], "rol": x["rol"]} for x in perf])
print("Limpieza ventas_mx:", dict(limpio.dtypes.astype(str)))
print(limpio.head(2).to_string())
v1 = float(limpio["Ventas"].iloc[0]); orig = s["Ventas"].iloc[0]
print("  Ventas[0] original:", orig, "-> parseado:", v1)
print("  Margen %[0] original:", s["Margen %"].iloc[0], "-> parseado:", limpio["Margen %"].iloc[0])
print("  Fecha[0] original:", s["Fecha"].iloc[0], "-> parseado:", limpio["Fecha"].iloc[0])
# fechas ISO (año primero) nunca se invierten, aunque el día sea <= 12
_f = lambda v: [str(x.date()) for x in D._a_fecha(pd.Series(v))]
_iso = _f(["2026-04-12", "2026-03-05", "2026-08-28"]) == ["2026-04-12", "2026-03-05", "2026-08-28"]
_mix = _f(["2026-04-12", "12/04/2026", "13/04/2026"]) == ["2026-04-12", "2026-04-12", "2026-04-13"]
_dmy = _f(["05/03/2026", "25/03/2026"]) == ["2026-03-05", "2026-03-25"]
_hms = _f(["2026-04-12 14:30:00", "2026-04-05 08:00:00"]) == ["2026-04-12", "2026-04-05"]
for _n, _ok in (("ISO aaaa-mm-dd sin invertir", _iso), ("ISO mezclado con dd/mm/aaaa", _mix), ("dd/mm/aaaa sigue siendo día primero", _dmy), ("ISO con hora", _hms)):
    tot += 1; ok += bool(_ok)
    if not _ok: fallas.append(_n)
    print(("OK    " if _ok else "FALLA ") + _n)
# meses escritos en español
_es1 = _f(["12 de abril de 2026", "3 de mayo de 2026", "1 de enero de 2026"]) == ["2026-04-12", "2026-05-03", "2026-01-01"]
_es2 = _f(["12-abr-26", "03-sep-26", "01-dic-26"]) == ["2026-04-12", "2026-09-03", "2026-12-01"]
_es3 = _f(["Abril 2026", "Mayo 2026"]) == ["2026-04-01", "2026-05-01"]
_es4 = all(D._proporcion_fechas(pd.Series(v)) >= 0.99 for v in (["12-abr-26", "03-may-26"], ["12 de abril de 2026", "5 de dic. de 2025"], ["Abril 2026", "Mayo 2026"]))
_es5 = D._proporcion_fechas(pd.Series(["Marketing 2026", "Ventas 2025", "Ana 3"] * 3)) == 0 and D._proporcion_fechas(pd.Series(["Mar", "Marketing", "Ana", "Luis"] * 5)) == 0
for _n, _ok in (("meses en español: '12 de abril de 2026'", _es1), ("meses en español: '12-abr-26'", _es2), ("meses en español: 'Abril 2026'", _es3), ("columna con meses en español se detecta como fecha", _es4), ("texto con 'mar'/'Marketing' no es fecha", _es5)):
    tot += 1; ok += bool(_ok)
    if not _ok: fallas.append(_n)
    print(("OK    " if _ok else "FALLA ") + _n)
# huella estable
print("Huella igual con otro orden/mayúsculas:", D.huella(["Fecha", "Total"]) == D.huella(["total", "FECHA"]))

print()
print(f"ACIERTOS: {ok}/{tot}  ({100*ok/tot:.0f}%)")
print("FALLAS:", fallas if fallas else "ninguna")
sys.exit(0 if not fallas else 1)
