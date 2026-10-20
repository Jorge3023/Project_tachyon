import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { TINTA, PALETA, COLOR_OTROS, fmtNum, fmtCompacto } from '../../lib/dash'

// Mosaicos del mapa. Por defecto OpenStreetMap (gratis, con atribución). Para mucho tráfico conviene un proveedor
// propio: se cambia con VITE_TILES_URL (p. ej. MapTiler, Stadia, Mapbox) sin tocar el código.
const TILES = import.meta.env.VITE_TILES_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATRIBUCION = import.meta.env.VITE_TILES_ATTRIBUTION || '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>'
const ALTO = 340
const AGG_TXT = { suma: 'Suma', promedio: 'Promedio', conteo: 'Conteo', min: 'Mínimo', max: 'Máximo', mediana: 'Mediana', unicos: 'Únicos' }

function texto(tag, txt, clase) {
  const e = document.createElement(tag); e.textContent = txt; if (clase) e.className = clase; return e
}

export default function Mapa({ widget, datos }) {
  const caja = useRef(null)
  const mapa = useRef(null)
  const capa = useRef(null)
  const conSerie = (datos.series || []).length > 0
  const colorDe = (i) => (datos.series[i] === 'Otros' ? COLOR_OTROS : PALETA[i % PALETA.length])
  const colorUnico = PALETA[(widget.color ?? 0) % PALETA.length]

  // Crear el mapa una sola vez
  useEffect(() => {
    const m = L.map(caja.current, {
      zoomControl: true, attributionControl: true, scrollWheelZoom: false, minZoom: 2, worldCopyJump: true,
      dragging: !L.Browser.mobile,            // en el móvil un dedo desplaza la página; dos dedos mueven/acercan el mapa
      tap: false,
    })
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATRIBUCION, crossOrigin: true }).addTo(m)
    // la rueda solo acerca después de hacer clic en el mapa (si no, secuestra el desplazamiento de la página)
    m.on('click focus', () => m.scrollWheelZoom.enable())
    m.on('mouseout blur', () => m.scrollWheelZoom.disable())
    capa.current = L.layerGroup().addTo(m)
    mapa.current = m
    const ro = new ResizeObserver(() => m.invalidateSize())
    ro.observe(caja.current)
    return () => { ro.disconnect(); m.remove(); mapa.current = null }
  }, [])

  // Dibujar los puntos cada vez que cambian los datos
  useEffect(() => {
    const m = mapa.current, g = capa.current
    if (!m || !g) return
    g.clearLayers()
    const pts = datos.puntos || []
    const vmax = Math.max(...pts.map(p => Math.abs(p[2] ?? 0)), 0) || 1
    const nmax = Math.max(...pts.map(q => q[3]), 1)
    const hayMedida = !!datos.medida
    for (const p of pts) {
      const [lat, lon, valor, n, cat] = p
      const radio = hayMedida ? 4 + 13 * Math.sqrt(Math.abs(valor ?? 0) / vmax) : 4 + 10 * Math.sqrt(n / nmax)
      const col = cat !== undefined ? colorDe(cat) : colorUnico
      const c = L.circleMarker([lat, lon], { radius: radio, color: '#ffffff', opacity: 0.55, weight: 1, fillColor: col, fillOpacity: 0.62 })
      const caja = document.createElement('div')
      caja.appendChild(texto('strong', `${hayMedida ? `${AGG_TXT[datos.agg] || ''} de ${datos.medida}: ` : 'Filas: '}${fmtNum(hayMedida ? valor : n)}`))
      if (hayMedida) caja.appendChild(texto('div', `${fmtNum(n)} ${n === 1 ? 'fila' : 'filas'}`))
      if (cat !== undefined) caja.appendChild(texto('div', datos.series[cat]))
      caja.appendChild(texto('div', `${lat.toFixed(4)}, ${lon.toFixed(4)}`, 'mapa-coords'))
      c.bindTooltip(caja, { direction: 'top', offset: [0, -radio / 2], sticky: false })
      c.addTo(g)
    }
    if (datos.limites) {
      const [[a, b], [c, d]] = datos.limites
      if (a === c && b === d) m.setView([a, b], 12)
      else m.fitBounds([[a, b], [c, d]], { padding: [28, 28], maxZoom: 15, animate: false })
    }
  }, [datos])

  return (
    <div>
      <div ref={caja} role="img" aria-label={`Mapa con ${fmtNum(datos.puntos?.length || 0)} puntos`}
        style={{ height: ALTO, borderRadius: 8, background: '#e9e8e2', zIndex: 0 }} className="relative overflow-hidden" />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs" style={{ color: TINTA.secundaria }}>
        {conSerie && (
          <ul className="flex flex-wrap gap-x-4 gap-y-1">
            {datos.series.map((s, i) => (
              <li key={s} className="flex items-center gap-1.5">
                <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: colorDe(i) }} />{s}
              </li>
            ))}
          </ul>
        )}
        <span className="ml-auto" style={{ color: TINTA.suave }}>
          {datos.medida ? `Tamaño: ${(AGG_TXT[datos.agg] || '').toLowerCase()} de ${datos.medida}` : 'Tamaño: número de filas'}
          {datos.medida && datos.puntos?.length ? ` (máx. ${fmtCompacto(Math.max(...datos.puntos.map(p => Math.abs(p[2] ?? 0))))})` : ''}
        </span>
      </div>
    </div>
  )
}
