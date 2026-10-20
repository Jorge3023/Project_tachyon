/* Exportación del dashboard.
   · PNG, PDF y PowerPoint se arman en el navegador fotografiando las mismas gráficas que se ven en pantalla
     (así lo exportado es idéntico a lo que se ve, incluido el mapa). Las librerías se cargan solo al exportar.
   · CSV y Excel los genera el servidor (POST /datasets/{id}/exportar) porque necesitan todas las filas. */
import api from '../services/api'

export const sleep = (ms) => new Promise(r => setTimeout(r, ms))
const frame = () => new Promise(r => requestAnimationFrame(() => r()))

/* ── Nombres y descargas ───────────────────────────────────────────────────── */

export function nombreArchivo(base, ext) {
  const limpio = String(base || 'dashboard').replace(/\.[A-Za-z0-9]{1,5}$/, '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9._-]+/g, '_').replace(/_+/g, '_').replace(/^[_.-]+|[_.-]+$/g, '').slice(0, 80)
  const d = new Date()
  const fecha = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return `${limpio || 'dashboard'}_${fecha}.${ext}`
}

export function descargar(blob, nombre) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = nombre; a.rel = 'noopener'
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

/** Texto de los filtros activos, p. ej. «Ciudad: Monterrey, Puebla». Los filtros vacíos no cuentan. */
export function describirFiltros(config) {
  const out = []
  for (const f of config?.filtros || []) {
    if (Array.isArray(f.valores) && f.valores.length) {
      const v = f.valores.slice(0, 4).join(', ') + (f.valores.length > 4 ? ` y ${f.valores.length - 4} más` : '')
      out.push(`${f.col}: ${v}`)
    } else if (f.min != null || f.max != null) {
      out.push(`${f.col}: ${f.min ?? '…'} a ${f.max ?? '…'}`)
    } else if (f.desde || f.hasta) {
      out.push(`${f.col}: ${f.desde || '…'} a ${f.hasta || '…'}`)
    }
  }
  return out
}

export const fechaLarga = () => new Date().toLocaleDateString('es-MX', { day: 'numeric', month: 'long', year: 'numeric' })

/* ── Esperar a que la pantalla esté lista para fotografiarse ───────────────── */

/** Espera tipografías, gráficas dibujadas y mosaicos del mapa. Nunca se queda colgada: tras `limiteMs` sigue y avisa. */
export async function esperarListo(raiz, { limiteMs = 12000 } = {}) {
  const t0 = performance.now()
  try { await document.fonts?.ready } catch { /* sin fuentes que esperar */ }
  await frame(); await frame()
  for (;;) {
    const esqueleto = raiz.querySelector('.animate-pulse')
    const sinDibujar = [...raiz.querySelectorAll('.recharts-responsive-container')].some(c => !c.querySelector('svg.recharts-surface'))
    const mosaicos = [...raiz.querySelectorAll('img.leaflet-tile')]
    const mapaSinMosaicos = [...raiz.querySelectorAll('.leaflet-container')].some(m => !m.querySelector('img.leaflet-tile'))
    if (!esqueleto && !sinDibujar && !mapaSinMosaicos && mosaicos.every(i => i.complete)) break
    if (performance.now() - t0 > limiteMs) break
    await sleep(100)
  }
  const mosaicos = [...raiz.querySelectorAll('img.leaflet-tile')]
  const mapaSinFondo = mosaicos.length > 0 && mosaicos.every(i => !i.naturalWidth)
  await sleep(450)          // fundido de los mosaicos y último redibujado
  return { mapaSinFondo }
}

/* ── Captura ───────────────────────────────────────────────────────────────── */

const MAX_PIXELES = 12_000_000     // los móviles se quedan sin memoria con lienzos mayores (iOS: ~16.7 M)
const MAX_LADO = 8192

/** Nitidez máxima que este dispositivo aguanta para una imagen de w×h. */
export function ratioSeguro(w, h, deseado) {
  const r = Math.min(deseado, Math.sqrt(MAX_PIXELES / Math.max(1, w * h)), MAX_LADO / Math.max(1, w), MAX_LADO / Math.max(1, h))
  return Math.max(0.5, Math.round(r * 100) / 100)
}

let _fuentes
let _calentado = false
const esSafari = () => /^((?!chrome|android|crios|fxios).)*safari/i.test(navigator.userAgent)

/** Se llama una vez antes de capturar: junta las tipografías web para no pedirlas en cada gráfica. */
export async function prepararCaptura(raiz) {
  const { getFontEmbedCSS } = await import('html-to-image')
  try {
    _fuentes = await Promise.race([getFontEmbedCSS(raiz), sleep(8000).then(() => { throw new Error('tiempo') })])
  } catch { _fuentes = '' }       // sin fuentes incrustadas: se usa la tipografía del sistema
}

const unPixel = (() => {
  let v
  return () => {
    if (!v) { const c = document.createElement('canvas'); c.width = c.height = 1; v = c.toDataURL('image/png') }
    return v
  }
})()

/** Fotografía un nodo. Devuelve el canvas y su tamaño en píxeles CSS. */
export async function capturar(nodo, { ratio = 2, fondo = '#ffffff' } = {}) {
  const { toCanvas } = await import('html-to-image')
  const w = nodo.offsetWidth, h = nodo.offsetHeight
  const base = {
    backgroundColor: fondo, cacheBust: false, imagePlaceholder: unPixel(),
    fontEmbedCSS: _fuentes ?? '',
    // la vista previa está encogida con `transform`; la foto debe salir a tamaño real
    style: { transform: 'none', margin: '0' },
    // los botones de zoom del mapa no sirven en una imagen; la atribución del mapa sí se queda (la exige la licencia)
    filter: (n) => !(n.classList && n.classList.contains('leaflet-control-zoom')),
  }
  if (!_calentado && esSafari()) {            // Safari deja imágenes en blanco en la primera foto
    try { await toCanvas(nodo, { ...base, pixelRatio: 1 }) } catch { /* se ignora: solo calienta */ }
    _calentado = true
  }
  const r = ratioSeguro(w, h, ratio)
  const canvas = await toCanvas(nodo, { ...base, pixelRatio: r })
  return { canvas, w, h, ratio: r }
}

export const aDataURL = (canvas) => canvas.toDataURL('image/png')
export const aBlob = (canvas) => new Promise((ok, mal) =>
  canvas.toBlob(b => b ? ok(b) : mal(new Error('Esta imagen es demasiado grande para tu dispositivo. Baja la nitidez o exporta menos gráficas.')), 'image/png'))

/** Lee de la pantalla dónde quedó cada gráfica (posición y tamaño en píxeles CSS, sin la escala de la vista previa). */
export function medirItems(rejilla) {
  return [...rejilla.querySelectorAll(':scope > [data-wid]')].map(el => ({
    id: el.dataset.wid, titulo: el.dataset.titulo || '', nodo: el.firstElementChild,
    x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight,
  }))
}

/** Fotografía cada gráfica, de a una, avisando el avance. */
export async function capturarItems(items, { ratio, onProgreso }) {
  const out = []
  for (let i = 0; i < items.length; i++) {
    onProgreso?.(`Capturando gráfica ${i + 1} de ${items.length}…`)
    await frame()                      // deja respirar a la página (y pintar el avance)
    const { canvas } = await capturar(items[i].nodo, { ratio })
    out.push({ ...items[i], img: aDataURL(canvas) })
  }
  return out
}

/* ── Acomodo en páginas ────────────────────────────────────────────────────── */

/** Reparte las gráficas en páginas respetando el orden y las filas de la pantalla.
    Una fila nunca se parte entre dos páginas; si una fila sola no cabe, se reduce para que quepa.
    Coordenadas de salida relativas a la esquina superior izquierda del área de contenido. */
export function empaquetar(items, { anchoGrid, areaW, areaH, gap = 16, unaPorPagina = false, kMax = 2 }) {
  const alto = typeof areaH === 'function' ? areaH : () => areaH
  const k0 = areaW / anchoGrid
  const paginas = []
  if (unaPorPagina) {
    items.forEach((it, i) => {
      const k = Math.min(areaW / it.w, alto(i) / it.h, k0 * kMax)
      const w = it.w * k, h = it.h * k
      paginas.push([{ ...it, x: (areaW - w) / 2, y: Math.max(0, (alto(i) - h) / 2), w, h }])
    })
    return paginas
  }
  const filas = []
  for (const it of [...items].sort((a, b) => a.y - b.y || a.x - b.x)) {
    const f = filas[filas.length - 1]
    if (f && Math.abs(it.y - f.y) < 3) f.items.push(it)
    else filas.push({ y: it.y, items: [it] })
  }
  let pagina = [], cursor = 0
  const nueva = () => { paginas.push(pagina); pagina = []; cursor = 0 }
  for (const f of filas) {
    const altoFila = Math.max(...f.items.map(i => i.h))
    let disp = alto(paginas.length)
    if (pagina.length && cursor + altoFila * k0 > disp) { nueva(); disp = alto(paginas.length) }
    const k = Math.min(k0, disp / altoFila)
    const sobra = (areaW - anchoGrid * k) / 2           // fila reducida: se centra
    for (const it of f.items) pagina.push({ ...it, x: sobra + it.x * k, y: cursor, w: it.w * k, h: it.h * k })
    cursor += altoFila * k + gap * k
  }
  if (pagina.length) paginas.push(pagina)
  return paginas
}

/* ── PNG ───────────────────────────────────────────────────────────────────── */

export async function crearZip(items, nombreBase) {
  const JSZip = (await import('jszip')).default
  const zip = new JSZip()
  const usados = new Set()
  items.forEach((it, i) => {
    let n = `${String(i + 1).padStart(2, '0')}_${nombreArchivo(it.titulo || it.id, 'png').replace(/_\d{4}-\d{2}-\d{2}\.png$/, '')}`
    while (usados.has(n)) n += '_'
    usados.add(n)
    zip.file(`${n}.png`, it.img.split(',')[1], { base64: true })
  })
  return zip.generateAsync({ type: 'blob', compression: 'STORE' })     // los PNG ya van comprimidos
}

/* ── PDF ───────────────────────────────────────────────────────────────────── */

// Las tipografías estándar del PDF solo traen Latin‑1: lo demás se sustituye para no ver cuadritos
const latin = (s) => String(s ?? '').replace(/[→←]/g, '-').replace(/[^\u0009\u000a -ÿ–—‘’“”•…]/g, '?')

export async function crearPDF({ items, titulo, lineas, tam, orientacion, encabezado, anchoGrid, onProgreso }) {
  const { jsPDF } = await import('jspdf')
  const doc = new jsPDF({ orientation: orientacion === 'vertical' ? 'p' : 'l', unit: 'pt', format: tam, compress: true })
  const W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight()
  const M = 36, PIE = 22
  const areaW = W - 2 * M
  let altoEnc = 0
  let lineasEnc = []
  if (encabezado) {
    doc.setFont('helvetica', 'normal'); doc.setFontSize(9)
    lineasEnc = (lineas || []).flatMap(l => doc.splitTextToSize(latin(l), areaW))
    altoEnc = 30 + lineasEnc.length * 12 + 10
  }
  const paginas = empaquetar(items, { anchoGrid, areaW, gap: 16, areaH: (i) => H - 2 * M - PIE - (i === 0 ? altoEnc : 0) })
  onProgreso?.('Armando el PDF…')
  paginas.forEach((pag, i) => {
    if (i > 0) doc.addPage()
    let top = M
    if (i === 0 && encabezado) {
      doc.setFont('helvetica', 'bold'); doc.setFontSize(16); doc.setTextColor(11, 11, 11)
      doc.text(latin(titulo), M, M + 14, { maxWidth: areaW })
      doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(82, 81, 78)
      lineasEnc.forEach((l, j) => doc.text(l, M, M + 32 + j * 12))
      top = M + altoEnc
    }
    for (const it of pag) doc.addImage(it.img, 'PNG', M + it.x, top + it.y, it.w, it.h, undefined, 'FAST')
  })
  const n = doc.getNumberOfPages()
  for (let p = 1; p <= n; p++) {
    doc.setPage(p); doc.setFont('helvetica', 'normal'); doc.setFontSize(8); doc.setTextColor(137, 135, 129)
    doc.text('Project Tachyon', M, H - M + 6)
    doc.text(`Página ${p} de ${n}`, W - M, H - M + 6, { align: 'right' })
  }
  doc.setProperties({ title: latin(titulo), creator: 'Project Tachyon' })
  return { blob: doc.output('blob'), paginas: n }
}

/* ── PowerPoint ────────────────────────────────────────────────────────────── */

export async function crearPPTX({ items, titulo, lineas, portada, unaPorDiapositiva, anchoGrid, onProgreso }) {
  const Pptx = (await import('pptxgenjs')).default
  const pptx = new Pptx()
  pptx.layout = 'LAYOUT_WIDE'                                // 13.33 × 7.5 pulgadas
  pptx.title = titulo; pptx.author = 'Project Tachyon'; pptx.company = 'Project Tachyon'
  pptx.defineSlideMaster({
    title: 'TACHYON', background: { color: 'FFFFFF' },
    objects: [{ text: { text: 'Project Tachyon', options: { x: 0.5, y: 7.1, w: 4, h: 0.3, fontSize: 9, color: '898781', fontFace: 'Calibri' } } }],
    slideNumber: { x: 12.3, y: 7.1, w: 0.6, h: 0.3, fontSize: 9, color: '898781', align: 'right' },
  })
  if (portada) {
    const s = pptx.addSlide({ masterName: 'TACHYON' })
    s.addShape('rect', { x: 0, y: 0, w: 0.35, h: 7.5, fill: { color: '2A78D6' }, line: { color: '2A78D6' } })
    s.addText(titulo, { x: 1.0, y: 2.3, w: 11.3, h: 1.4, fontSize: 36, bold: true, color: '0B0B0B', fontFace: 'Calibri', valign: 'bottom', fit: 'shrink' })
    s.addText((lineas || []).join('\n'), { x: 1.0, y: 3.9, w: 11.3, h: 1.8, fontSize: 16, color: '52514E', fontFace: 'Calibri', valign: 'top', fit: 'shrink' })
  }
  const AX = 0.5, AY = 0.75, AW = 12.33, AH = 6.2
  const paginas = empaquetar(items, { anchoGrid, areaW: AW, areaH: AH, gap: 16, unaPorPagina: unaPorDiapositiva })
  onProgreso?.('Armando la presentación…')
  paginas.forEach((pag) => {
    const s = pptx.addSlide({ masterName: 'TACHYON' })
    s.addText(titulo, { x: AX, y: 0.25, w: AW, h: 0.35, fontSize: 12, color: '898781', fontFace: 'Calibri', fit: 'shrink' })
    for (const it of pag) {
      s.addImage({ data: it.img.replace(/^data:/, ''), x: AX + it.x, y: AY + it.y, w: it.w, h: it.h, altText: it.titulo || 'Gráfica' })
    }
  })
  const blob = await pptx.write({ outputType: 'blob' })
  return { blob, diapositivas: paginas.length + (portada ? 1 : 0) }
}

/* ── Excel y CSV (los arma el servidor) ────────────────────────────────────── */

export async function mensajeError(e, def) {
  const d = e?.response?.data
  try {
    const j = d instanceof Blob ? JSON.parse(await d.text()) : d
    if (typeof j?.detail === 'string') return j.detail
  } catch { /* la respuesta no era JSON */ }
  if (e?.code === 'ECONNABORTED') return 'El servidor tardó demasiado. Prueba con menos filas (filtros) o con CSV.'
  if (!e?.response) return 'No se pudo conectar con el servidor.'
  return def
}

export async function pedirAlServidor({ archivoId, config, formato, datos, graficas, widgets, vista }) {
  const r = await api.post(`/datasets/${archivoId}/exportar`,
    { config, formato, datos, graficas, widgets, vista },
    { responseType: 'blob', timeout: 120000 })
  const cd = r.headers['content-disposition'] || ''
  return {
    blob: r.data,
    nombre: (/filename="([^"]+)"/.exec(cd) || [])[1] || nombreArchivo('datos', formato),
    truncada: r.headers['x-exportacion-truncada'] === '1',
    filas: Number(r.headers['x-filas-exportadas'] || 0),
  }
}
