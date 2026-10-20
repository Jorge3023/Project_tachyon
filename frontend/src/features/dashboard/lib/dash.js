// Constantes y utilidades compartidas por el editor de dashboards y sus gráficas.

// Paleta categórica validada (ver dataviz): se asigna en orden fijo, nunca se cicla.
export const PALETA = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
export const COLOR_OTROS = '#898781'
export const TINTA = { primaria: '#0b0b0b', secundaria: '#52514e', suave: '#898781', rejilla: '#e1e0d9', eje: '#c3c2b7', superficie: '#fcfcfb' }
// Rampa secuencial (un solo tono, claro → oscuro) para el mapa de calor
export const RAMPA_AZUL = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']

export const ANCHOS = [
  { v: 3, l: '¼' }, { v: 4, l: '⅓' }, { v: 6, l: '½' }, { v: 8, l: '⅔' }, { v: 12, l: 'Todo' },
]
// Clases estáticas (Tailwind no detecta nombres armados con variables)
export const CLASE_ANCHO = {
  3: 'lg:col-span-3 sm:col-span-6', 4: 'lg:col-span-4 sm:col-span-6', 6: 'lg:col-span-6 sm:col-span-6',
  8: 'lg:col-span-8 sm:col-span-12', 12: 'lg:col-span-12 sm:col-span-12',
}

export const GRANOS = [
  { v: 'auto', l: 'Auto' }, { v: 'dia', l: 'Día' }, { v: 'semana', l: 'Semana' },
  { v: 'mes', l: 'Mes' }, { v: 'trimestre', l: 'Trim.' }, { v: 'anio', l: 'Año' },
]

export const AGGS = [
  { v: 'suma', l: 'Suma' }, { v: 'promedio', l: 'Promedio' }, { v: 'conteo', l: 'Conteo' },
  { v: 'min', l: 'Mín.' }, { v: 'max', l: 'Máx.' }, { v: 'mediana', l: 'Mediana' }, { v: 'unicos', l: 'Únicos' },
]
const AGG_TEXTO = { suma: 'Suma', promedio: 'Promedio', conteo: 'Conteo de filas', min: 'Mínimo', max: 'Máximo', mediana: 'Mediana', unicos: 'Valores únicos' }

const R_DIM = ['categoria', 'estado', 'identificador']
const R_X_TIEMPO = ['fecha', 'categoria', 'estado']

// Qué hace cada tipo y qué columnas admite en cada campo
export const TIPOS = {
  kpi:        { l: 'Indicador',    d: 'Una cifra clave, con comparación contra el periodo anterior.', campos: { medida: ['numero'], x: ['fecha'] }, aggs: true },
  linea:      { l: 'Líneas',       d: 'Evolución en el tiempo o entre categorías.', campos: { x: R_X_TIEMPO, medida: ['numero'], serie: ['categoria', 'estado'] }, aggs: true, grano: true },
  area:       { l: 'Área',         d: 'Como líneas, resaltando el volumen acumulado.', campos: { x: R_X_TIEMPO, medida: ['numero'], serie: ['categoria', 'estado'] }, aggs: true, grano: true },
  barras:     { l: 'Barras',       d: 'Compara categorías; agrupadas, apiladas u horizontales.', campos: { x: ['fecha', ...R_DIM], medida: ['numero'], serie: ['categoria', 'estado'] }, aggs: true, grano: true },
  dona:       { l: 'Circular',     d: 'Participación de cada categoría en el total.', campos: { x: R_DIM, medida: ['numero'] }, aggs: ['suma', 'conteo', 'unicos'] },
  pareto:     { l: 'Pareto',       d: 'Ranking de categorías con el acumulado del total.', campos: { x: R_DIM, medida: ['numero'] }, aggs: ['suma', 'conteo', 'unicos'] },
  dispersion: { l: 'Dispersión',   d: 'Relación entre dos columnas numéricas.', campos: { x: ['numero'], y: ['numero'], serie: ['categoria', 'estado'] } },
  histograma: { l: 'Histograma',   d: 'Cómo se distribuyen los valores de una columna.', campos: { x: ['numero'] } },
  calor:      { l: 'Mapa de calor', d: 'Cruza dos columnas y colorea la intensidad.', campos: { x: ['fecha', ...R_DIM], y: R_DIM, medida: ['numero'] }, aggs: true, grano: true },
  mapa:       { l: 'Mapa geográfico', d: 'Puntos sobre un mapa real a partir de latitud y longitud.', campos: { lat: ['numero'], lon: ['numero'], medida: ['numero'], serie: ['categoria', 'estado'] }, aggs: true },
  tabla:      { l: 'Tabla',        d: 'Las filas del archivo, ordenadas como quieras.', campos: {} },
}
export const ORDEN_TIPOS = ['kpi', 'linea', 'area', 'barras', 'dona', 'pareto', 'dispersion', 'histograma', 'calor', 'mapa', 'tabla']

export const ROL_TEXTO = { fecha: 'Fecha', numero: 'Número', categoria: 'Categoría', estado: 'Estado', identificador: 'Identificador', texto: 'Texto' }

const RX_LAT = /^(lat|latitud|latitude)$/i
const RX_LON = /^(lon|lng|long|longitud|longitude)$/i
const sinAcentos = (s) => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z]/g, '')
const cabe = (c, tope) => c.rol === 'numero' && (c.min === undefined || c.min === null || (c.min >= -tope && c.max <= tope))
/** Columnas que podrían ser latitud (±90) o longitud (±180) según su rango. */
export const candidatasLat = (columnas) => columnas.filter(c => cabe(c, 90))
export const candidatasLon = (columnas) => columnas.filter(c => cabe(c, 180))
/** Mejor latitud/longitud por nombre; si no hay nombres claros, las dos primeras que encajen por rango. */
export function columnasGeo(columnas) {
  const lat = candidatasLat(columnas), lon = candidatasLon(columnas)
  const la = lat.find(c => RX_LAT.test(sinAcentos(c.nombre))) || null
  const lo = lon.find(c => RX_LON.test(sinAcentos(c.nombre))) || null
  const a = la || lat[0] || null
  const b = lo || lon.find(c => c.nombre !== a?.nombre) || null
  return { lat: a?.nombre ?? null, lon: b?.nombre ?? null, porNombre: !!(la && lo) }
}

export function aggsPermitidas(tipo) {
  const a = TIPOS[tipo]?.aggs
  if (!a) return []
  return a === true ? AGGS.map(x => x.v) : a
}

/** ¿Hay columnas suficientes para armar este tipo de gráfica? Devuelve null si sí, o el motivo si no. */
export function motivoNoDisponible(tipo, columnas) {
  const hay = (roles) => columnas.some(c => roles.includes(c.rol))
  const cuantas = (roles) => columnas.filter(c => roles.includes(c.rol)).length
  const c = TIPOS[tipo].campos
  if (tipo === 'dispersion' && cuantas(['numero']) < 2) return 'Necesita dos columnas numéricas'
  if (tipo === 'mapa') { const g = columnasGeo(columnas); if (!g.lat || !g.lon || g.lat === g.lon) return 'Necesita columnas numéricas de latitud (±90) y longitud (±180)' }
  if (tipo === 'calor' && (cuantas([...R_DIM, 'fecha']) < 2 || !hay(R_DIM))) return 'Necesita dos columnas de categoría (o fecha y categoría)'
  for (const [campo, roles] of Object.entries(c)) {
    if (['x', 'y'].includes(campo) && !hay(roles) && tipo !== 'kpi') return `No hay columnas de tipo ${roles.map(r => ROL_TEXTO[r].toLowerCase()).join(' o ')}`
  }
  return null
}

let _contador = 0
export const nuevoId = () => `w${Date.now().toString(36)}${(_contador++).toString(36)}`

const RX_MEDIA = /(precio|promedio|tasa|porcentaje|%|ratio|edad|calif|score|temperatura|tiempo|ticket)/i
const RX_PRIORIDAD = [/(importe|monto|venta|ingreso|revenue|sales|amount|total)/i, /(costo|cost|gasto|valor|pago)/i, /(cantidad|qty|unidades|piezas|volumen)/i]
/** Misma regla que el servidor para elegir la métrica principal: importes primero, promedios al final. */
function puntajeMedida(nombre) {
  if (RX_MEDIA.test(nombre)) return RX_PRIORIDAD.length + 1
  const i = RX_PRIORIDAD.findIndex(rx => rx.test(nombre))
  return i === -1 ? RX_PRIORIDAD.length : i
}

/** Gráfica nueva con columnas por defecto según los roles disponibles. */
export function widgetNuevo(tipo, columnas) {
  const por = (roles, excluir = []) => columnas.filter(c => roles.includes(c.rol) && !excluir.includes(c.nombre))
  const w = { id: nuevoId(), tipo, titulo: '', ancho: tipo === 'kpi' ? 3 : 6, filtros: [], grano: 'auto' }
  const nums = por(['numero']).sort((a, b) => puntajeMedida(a.nombre) - puntajeMedida(b.nombre))   // importes antes que cantidades
  const dims = por(['categoria', 'estado'])
  const fechas = por(['fecha'])
  const dimsId = por(R_DIM)
  if (tipo === 'kpi') { w.medida = nums[0]?.nombre ?? null; w.agg = w.medida ? 'suma' : 'conteo' }
  if (tipo === 'linea' || tipo === 'area') {
    w.x = (fechas[0] || dims[0])?.nombre; w.medida = nums[0]?.nombre ?? null; w.agg = w.medida ? 'suma' : 'conteo'; w.ancho = 12
  }
  if (tipo === 'barras') { w.x = (dimsId[0] || fechas[0])?.nombre; w.medida = nums[0]?.nombre ?? null; w.agg = w.medida ? 'suma' : 'conteo'; w.top = 10; w.orden = 'desc'; w.orientacion = 'v'; w.apilado = false }
  if (tipo === 'dona' || tipo === 'pareto') { w.x = dimsId[0]?.nombre; w.medida = nums[0]?.nombre ?? null; w.agg = w.medida ? 'suma' : 'conteo'; w.top = tipo === 'dona' ? 6 : 10 }
  if (tipo === 'dispersion') { w.x = nums[0]?.nombre; w.y = nums[1]?.nombre }
  if (tipo === 'histograma') { w.x = nums[0]?.nombre; w.bins = 0 }
  if (tipo === 'calor') {
    w.x = (dimsId[0] || fechas[0])?.nombre
    w.y = por(R_DIM, [w.x])[0]?.nombre
    w.medida = nums[0]?.nombre ?? null; w.agg = w.medida ? 'suma' : 'conteo'; w.top = 10
  }
  if (tipo === 'mapa') {
    const g = columnasGeo(columnas)
    w.lat = g.lat; w.lon = g.lon; w.medida = null; w.agg = 'conteo'; w.serie = null; w.ancho = 12
  }
  if (tipo === 'tabla') { w.columnas = columnas.slice(0, 6).map(c => c.nombre); w.filas = 10; w.orden = null; w.dir = 'desc'; w.ancho = 12 }
  w.titulo = tituloAutomatico(w)
  return w
}

/** Título sugerido a partir de la configuración. */
export function tituloAutomatico(w) {
  const m = w.medida
  switch (w.tipo) {
    case 'kpi': return m ? `${AGG_TEXTO[w.agg]} de ${m}` : 'Registros'
    case 'linea': case 'area': return `${m ? `${m}` : 'Registros'} por ${w.x || '…'}`
    case 'barras': return `${m ? `${m}` : 'Registros'} por ${w.x || '…'}`
    case 'dona': return `${m ? `${m}` : 'Registros'} por ${w.x || '…'}`
    case 'pareto': return `Pareto de ${m || 'registros'} por ${w.x || '…'}`
    case 'dispersion': return `${w.x || '…'} vs ${w.y || '…'}`
    case 'histograma': return `Distribución de ${w.x || '…'}`
    case 'mapa': return w.medida ? `Mapa de ${w.medida}` : 'Mapa'
    case 'calor': return `${w.x || '…'} × ${w.y || '…'}`
    default: return 'Datos'
  }
}

export function subtituloWidget(w) {
  if (['linea', 'area', 'barras', 'calor', 'dona', 'pareto', 'mapa'].includes(w.tipo)) {
    return w.medida ? `${AGG_TEXTO[w.agg] || ''} de ${w.medida}` : 'Conteo de filas'
  }
  if (w.tipo === 'kpi') return w.medida ? AGG_TEXTO[w.agg] : 'Conteo de filas'
  return ''
}

const _num = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 2 })
const _int = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 0 })
export function fmtNum(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return Math.abs(v) >= 1000 ? _int.format(v) : _num.format(v)
}
/** Para ejes y cifras grandes: 1.38 M, 289 k. */
export function fmtCompacto(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e9) return `${_num.format(v / 1e9)} mil M`
  if (a >= 1e6) return `${_num.format(v / 1e6)} M`
  if (a >= 1e4) return `${_num.format(v / 1e3)} k`
  return fmtNum(v)
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
/** Etiqueta corta para un periodo del servidor ('2026-03' → 'mar 26'). Otras categorías pasan igual. */
export function etiquetaPeriodo(lbl, grano) {
  const s = String(lbl)
  if (grano === 'mes' && /^\d{4}-\d{2}$/.test(s)) return `${MESES[Number(s.slice(5)) - 1]} ${s.slice(2, 4)}`
  if ((grano === 'dia' || grano === 'semana') && /^\d{4}-\d{2}-\d{2}$/.test(s)) return `${Number(s.slice(8))} ${MESES[Number(s.slice(5, 7)) - 1]}`
  return s
}
export function etiquetaLarga(lbl, grano) {
  const s = String(lbl)
  if (grano === 'mes' && /^\d{4}-\d{2}$/.test(s)) return `${MESES[Number(s.slice(5)) - 1]} ${s.slice(0, 4)}`
  if (grano === 'semana' && /^\d{4}-\d{2}-\d{2}$/.test(s)) return `Semana del ${Number(s.slice(8))} ${MESES[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)}`
  if (grano === 'dia' && /^\d{4}-\d{2}-\d{2}$/.test(s)) return `${Number(s.slice(8))} ${MESES[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)}`
  return s
}

export function colorSerie(i, nombre, fijo = null) {
  if (nombre === 'Otros') return COLOR_OTROS
  if (fijo !== null && fijo !== undefined) return PALETA[fijo % PALETA.length]
  return PALETA[i % PALETA.length]
}

/** Interpola la rampa azul para t en [0,1]. */
export function colorRampa(t) {
  const n = RAMPA_AZUL.length - 1
  const x = Math.max(0, Math.min(1, t)) * n
  return RAMPA_AZUL[Math.round(x)]
}
export function tintaSobre(hex) {
  const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16)
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#0b0b0b' : '#ffffff'
}

/** Cambia el tipo de una gráfica conservando lo que sigue siendo válido (columnas, filtros, ancho, título propio). */
export function cambiarTipo(w, tipo, columnas) {
  const base = widgetNuevo(tipo, columnas)
  const roles = Object.fromEntries(columnas.map(c => [c.nombre, c.rol]))
  const campos = TIPOS[tipo].campos
  const out = { ...base, id: w.id, filtros: w.filtros || [], ancho: w.ancho && tipo !== 'kpi' && w.tipo !== 'kpi' ? w.ancho : base.ancho, color: w.color ?? null }
  for (const campo of ['x', 'y', 'lat', 'lon', 'medida', 'serie']) {
    if (campos[campo] && w[campo] && campos[campo].includes(roles[w[campo]])) out[campo] = w[campo]
  }
  if (out.x && out.x === out.y && tipo === 'calor') out.y = base.y
  if (w.agg && aggsPermitidas(tipo).includes(w.agg) && out.medida) out.agg = w.agg
  if (!out.medida && TIPOS[tipo].aggs) out.agg = 'conteo'
  if (w.grano) out.grano = w.grano
  out.titulo = w.titulo && w.titulo !== tituloAutomatico(w) ? w.titulo : tituloAutomatico(out)
  return out
}

/** Aplica un cambio y, si el título nunca se personalizó, lo regenera. */
export function actualizarWidget(w, patch) {
  const nuevo = { ...w, ...patch }
  if (!('titulo' in patch) && (!w.titulo || w.titulo === tituloAutomatico(w))) nuevo.titulo = tituloAutomatico(nuevo)
  if (nuevo.tipo !== 'tabla' && 'medida' in patch && !nuevo.medida) nuevo.agg = 'conteo'
  if ('medida' in patch && nuevo.medida && nuevo.agg === 'conteo' && TIPOS[nuevo.tipo].aggs) nuevo.agg = 'suma'
  return nuevo
}
