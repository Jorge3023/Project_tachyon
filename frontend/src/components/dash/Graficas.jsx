import { lazy, Suspense } from 'react'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, PieChart, Pie, Cell, ScatterChart, Scatter, ZAxis,
} from 'recharts'
import {
  TINTA, PALETA, colorSerie, colorRampa, tintaSobre, fmtNum, fmtCompacto, etiquetaPeriodo, etiquetaLarga,
} from '../../lib/dash'

const ALTO = 240
// Leaflet (el mapa) solo se descarga cuando hay un mapa en el dashboard
const Mapa = lazy(() => import('./Mapa'))
const EJE = { stroke: TINTA.eje, tick: { fill: TINTA.suave, fontSize: 11 }, tickLine: false }
const corta = (s, n = 14) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s))

function CajaTooltip({ titulo, filas }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-md px-3 py-2 text-xs" style={{ color: TINTA.primaria }}>
      {titulo !== undefined && <p className="font-medium mb-1">{titulo}</p>}
      {filas.map((f, i) => (
        <p key={i} className="flex items-center gap-2" style={{ color: TINTA.secundaria }}>
          {f.color && <span className="inline-block w-2 h-2 rounded-sm" style={{ background: f.color }} />}
          <span>{f.nombre}</span>
          <span className="ml-auto pl-3 tabular-nums font-medium" style={{ color: TINTA.primaria }}>{f.valor}</span>
        </p>
      ))}
    </div>
  )
}

function Leyenda({ items }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 justify-center text-xs mt-2" style={{ color: TINTA.secundaria }}>
      {items.map(it => (
        <li key={it.nombre} className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: it.color }} />{it.nombre}
        </li>
      ))}
    </ul>
  )
}

/* ── Indicador ─────────────────────────────────────────────────────────────── */
export function Kpi({ widget, datos }) {
  const d = datos.delta
  const sube = d?.pct > 0, baja = d?.pct < 0
  return (
    <div>
      <p className="text-3xl font-semibold tracking-tight" style={{ color: TINTA.primaria }} title={datos.valor === null ? '' : String(datos.valor)}>
        {datos.valor === null ? '—' : fmtCompacto(datos.valor)}
      </p>
      {d && d.pct !== null && (
        <p className="text-xs mt-1 flex items-center gap-1" style={{ color: TINTA.secundaria }}>
          <span aria-hidden="true">{sube ? '▲' : baja ? '▼' : '■'}</span>
          <span className="font-medium">{sube ? '+' : ''}{fmtNum(d.pct)} %</span>
          <span>vs {etiquetaPeriodo(d.anterior, d.grano || (widget.grano === 'auto' ? 'mes' : widget.grano))}</span>
        </p>
      )}
      {d?.excluido && (
        <p className="text-xs mt-0.5" style={{ color: TINTA.suave || TINTA.secundaria }}>
          Sin contar {etiquetaPeriodo(d.excluido, d.grano)} (periodo en curso)
        </p>
      )}
    </div>
  )
}

/* ── Líneas / área / barras ─────────────────────────────────────────────────── */
function datosCategorias(datos) {
  return datos.categorias.map((c, i) => {
    const fila = { c, etiqueta: etiquetaPeriodo(c, datos.grano) }
    datos.series.forEach((s, j) => { fila[`s${j}`] = s.valores[i] })
    return fila
  })
}

function TooltipSeries({ active, payload, datos }) {
  if (!active || !payload?.length) return null
  const fila = payload[0].payload
  return <CajaTooltip titulo={etiquetaLarga(fila.c, datos.grano)}
    filas={datos.series.map((s, j) => ({ nombre: s.nombre, valor: fmtNum(fila[`s${j}`]), color: colorSerie(j, s.nombre, datos.series.length === 1 ? datos._color : null) }))} />
}

export function LineaArea({ widget, datos }) {
  const data = datosCategorias(datos)
  const area = widget.tipo === 'area'
  const multi = datos.series.length > 1
  const Chart = area ? AreaChart : LineChart
  return (
    <>
      <ResponsiveContainer width="100%" height={ALTO}>
        <Chart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={TINTA.rejilla} />
          <XAxis dataKey="etiqueta" {...EJE} minTickGap={24} interval="preserveStartEnd" />
          <YAxis {...EJE} width={48} tickFormatter={fmtCompacto} axisLine={false} />
          <Tooltip content={<TooltipSeries datos={{ ...datos, _color: widget.color ?? 0 }} />} cursor={{ stroke: TINTA.eje }} />
          {datos.series.map((s, j) => {
            const col = colorSerie(j, s.nombre, multi ? null : widget.color ?? 0)
            return area
              ? <Area key={j} type="monotone" dataKey={`s${j}`} stroke={col} strokeWidth={2} fill={col} fillOpacity={0.15}
                  stackId={multi ? 'a' : undefined} dot={false} activeDot={{ r: 4, stroke: TINTA.superficie, strokeWidth: 2 }} isAnimationActive={false} />
              : <Line key={j} type="monotone" dataKey={`s${j}`} stroke={col} strokeWidth={2} dot={false}
                  activeDot={{ r: 4, stroke: TINTA.superficie, strokeWidth: 2 }} isAnimationActive={false} />
          })}
        </Chart>
      </ResponsiveContainer>
      {multi && <Leyenda items={datos.series.map((s, j) => ({ nombre: s.nombre, color: colorSerie(j, s.nombre) }))} />}
    </>
  )
}

export function Barras({ widget, datos }) {
  const data = datosCategorias(datos)
  const horiz = widget.orientacion === 'h'
  const multi = datos.series.length > 1
  const apilado = multi && widget.apilado
  const largo = Math.max(...datos.categorias.map(c => String(c).length), 0)
  return (
    <>
      <ResponsiveContainer width="100%" height={horiz ? Math.max(ALTO, datos.categorias.length * 30 + 30) : ALTO}>
        <BarChart data={data} layout={horiz ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          barCategoryGap={horiz ? '30%' : '25%'} barGap={2}>
          <CartesianGrid horizontal={!horiz} vertical={horiz} stroke={TINTA.rejilla} />
          {horiz ? (
            <>
              <XAxis type="number" {...EJE} tickFormatter={fmtCompacto} axisLine={false} />
              <YAxis type="category" dataKey="etiqueta" {...EJE} width={Math.min(130, 20 + largo * 6)} tickFormatter={v => corta(v, 20)} />
            </>
          ) : (
            <>
              <XAxis dataKey="etiqueta" {...EJE} interval={data.length <= 14 ? 0 : 'preserveStartEnd'} minTickGap={12}
                tickFormatter={v => corta(v, data.length > 8 ? 8 : 14)} />
              <YAxis {...EJE} width={48} tickFormatter={fmtCompacto} axisLine={false} />
            </>
          )}
          <Tooltip content={<TooltipSeries datos={{ ...datos, _color: widget.color ?? 0 }} />} cursor={{ fill: 'rgba(11,11,11,0.04)' }} />
          {datos.series.map((s, j) => (
            <Bar key={j} dataKey={`s${j}`} fill={colorSerie(j, s.nombre, multi ? null : widget.color ?? 0)} maxBarSize={24}
              stackId={apilado ? 'a' : undefined}
              stroke={apilado ? TINTA.superficie : 'none'} strokeWidth={apilado ? 2 : 0}
              radius={apilado ? 0 : horiz ? [0, 4, 4, 0] : [4, 4, 0, 0]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
      {multi && <Leyenda items={datos.series.map((s, j) => ({ nombre: s.nombre, color: colorSerie(j, s.nombre) }))} />}
    </>
  )
}

/* ── Circular ───────────────────────────────────────────────────────────────── */
export function Dona({ widget, datos }) {
  const partes = datos.partes
  return (
    <div className="flex items-center gap-4 flex-wrap justify-center">
      <div className="relative" style={{ width: 170, height: 170 }}>
        <PieChart width={170} height={170}>
          <Pie data={partes} dataKey="valor" nameKey="nombre" innerRadius={55} outerRadius={82} paddingAngle={partes.length > 1 ? 2 : 0}
            stroke={TINTA.superficie} strokeWidth={2} isAnimationActive={false}>
            {partes.map((p, i) => <Cell key={p.nombre} fill={colorSerie(i, p.nombre)} />)}
          </Pie>
          <Tooltip content={({ active, payload }) => active && payload?.length
            ? <CajaTooltip titulo={payload[0].payload.nombre} filas={[{ nombre: 'Valor', valor: fmtNum(payload[0].payload.valor) }, { nombre: 'Participación', valor: `${fmtNum(payload[0].payload.pct)} %` }]} /> : null} />
        </PieChart>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-lg font-semibold" style={{ color: TINTA.primaria }}>{fmtCompacto(datos.total)}</span>
          <span className="text-[11px]" style={{ color: TINTA.suave }}>total</span>
        </div>
      </div>
      <ul className="text-xs space-y-1.5 min-w-[130px] flex-1">
        {partes.map((p, i) => (
          <li key={p.nombre} className="flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: colorSerie(i, p.nombre) }} />
            <span className="truncate" style={{ color: TINTA.secundaria }} title={p.nombre}>{p.nombre}</span>
            <span className="ml-auto tabular-nums font-medium" style={{ color: TINTA.primaria }}>{fmtNum(p.pct)} %</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ── Pareto: ranking con el acumulado como etiqueta (un solo eje) ──────────────── */
export function Pareto({ widget, datos }) {
  const max = Math.max(...datos.valores, 0) || 1
  const col = PALETA[widget.color ?? 0]
  return (
    <div>
      <div className="flex text-[11px] mb-1" style={{ color: TINTA.suave }}>
        <span className="flex-1">Categoría</span><span className="w-24 text-right">Valor</span><span className="w-16 text-right">Acum.</span>
      </div>
      <ol className="space-y-1.5">
        {datos.categorias.map((c, i) => (
          <li key={c} className="flex items-center gap-3 text-xs">
            <span className="w-24 truncate flex-shrink-0" style={{ color: TINTA.secundaria }} title={c}>{c}</span>
            <span className="flex-1 h-4 rounded-r" style={{ background: '#f0efec' }}>
              <span className="block h-full" style={{ width: `${(datos.valores[i] / max) * 100}%`, background: col, borderRadius: '0 4px 4px 0', minWidth: 2 }} />
            </span>
            <span className="w-16 text-right tabular-nums" style={{ color: TINTA.primaria }}>{fmtCompacto(datos.valores[i])}</span>
            <span className="w-12 text-right tabular-nums" style={{ color: TINTA.secundaria }}>{fmtNum(datos.acumulado[i])} %</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/* ── Dispersión ─────────────────────────────────────────────────────────────── */
export function Dispersion({ widget, datos }) {
  const series = datos.series.map((nombre, i) => ({ nombre, puntos: datos.puntos.filter(p => p[2] === i).map(p => ({ x: p[0], y: p[1] })) }))
  const multi = series.length > 1
  return (
    <>
      <ResponsiveContainer width="100%" height={ALTO}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={TINTA.rejilla} />
          <XAxis type="number" dataKey="x" name={widget.x} {...EJE} tickFormatter={fmtCompacto} domain={['auto', 'auto']} />
          <YAxis type="number" dataKey="y" name={widget.y} {...EJE} width={48} tickFormatter={fmtCompacto} axisLine={false} domain={['auto', 'auto']} />
          <ZAxis range={[48, 48]} />
          <Tooltip cursor={{ strokeDasharray: '3 3', stroke: TINTA.eje }} content={({ active, payload }) => active && payload?.length
            ? <CajaTooltip titulo={multi ? payload[0].name : undefined} filas={[{ nombre: widget.x, valor: fmtNum(payload[0].payload.x) }, { nombre: widget.y, valor: fmtNum(payload[0].payload.y) }]} /> : null} />
          {series.map((s, i) => (
            <Scatter key={s.nombre} name={s.nombre} data={s.puntos} fill={colorSerie(i, s.nombre, multi ? null : widget.color ?? 0)}
              fillOpacity={0.75} stroke={TINTA.superficie} strokeWidth={1} isAnimationActive={false} />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
      {multi && <Leyenda items={series.map((s, i) => ({ nombre: s.nombre, color: colorSerie(i, s.nombre) }))} />}
    </>
  )
}

/* ── Histograma ─────────────────────────────────────────────────────────────── */
export function Histograma({ widget, datos }) {
  const data = datos.bins.map(b => ({ ...b, etiqueta: fmtCompacto(b.desde), rango: `${fmtNum(b.desde)} – ${fmtNum(b.hasta)}` }))
  return (
    <ResponsiveContainer width="100%" height={ALTO}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap={2} barGap={0}>
        <CartesianGrid vertical={false} stroke={TINTA.rejilla} />
        <XAxis dataKey="etiqueta" {...EJE} interval="preserveStartEnd" minTickGap={16} />
        <YAxis {...EJE} width={40} axisLine={false} allowDecimals={false} />
        <Tooltip cursor={{ fill: 'rgba(11,11,11,0.04)' }} content={({ active, payload }) => active && payload?.length
          ? <CajaTooltip titulo={payload[0].payload.rango} filas={[{ nombre: 'Filas', valor: fmtNum(payload[0].payload.n) }]} /> : null} />
        <Bar dataKey="n" fill={PALETA[widget.color ?? 0]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ── Mapa de calor (rampa secuencial de un solo tono) ────────────────────────────── */
export function MapaCalor({ widget, datos }) {
  const { filas, columnas, valores, min, max } = datos
  const rango = (max ?? 0) - (min ?? 0) || 1
  const mostrarValor = columnas.length <= 12
  return (
    <div>
      <div className="overflow-x-auto">
        <div className="grid gap-0.5 text-[11px]" style={{ gridTemplateColumns: `minmax(70px,auto) repeat(${columnas.length}, minmax(30px, 1fr))` }}>
          <span />
          {columnas.map(c => <span key={c} className="text-center truncate px-0.5" style={{ color: TINTA.suave }} title={c}>{etiquetaPeriodo(c, datos.grano)}</span>)}
          {filas.map((f, j) => (
            <Fila key={f} nombre={f} celdas={valores[j]} columnas={columnas} min={min} rango={rango} mostrar={mostrarValor} grano={datos.grano} />
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2 mt-3 text-[11px]" style={{ color: TINTA.suave }}>
        <span>{fmtCompacto(min)}</span>
        <span className="h-2 flex-1 max-w-[140px] rounded" style={{ background: `linear-gradient(90deg, ${colorRampa(0)}, ${colorRampa(0.5)}, ${colorRampa(1)})` }} />
        <span>{fmtCompacto(max)}</span>
      </div>
    </div>
  )
}
function Fila({ nombre, celdas, columnas, min, rango, mostrar, grano }) {
  return (
    <>
      <span className="truncate pr-2 flex items-center" style={{ color: TINTA.secundaria }} title={nombre}>{nombre}</span>
      {celdas.map((v, i) => {
        const bg = v === null ? '#f0efec' : colorRampa((v - min) / rango)
        return (
          <span key={i} className="h-7 rounded-sm flex items-center justify-center tabular-nums"
            style={{ background: bg, color: v === null ? TINTA.suave : tintaSobre(bg) }}
            title={`${nombre} · ${etiquetaLarga(columnas[i], grano)}: ${v === null ? 'sin datos' : fmtNum(v)}`}>
            {mostrar && v !== null ? fmtCompacto(v) : ''}
          </span>
        )
      })}
    </>
  )
}

/* ── Tabla ──────────────────────────────────────────────────────────────────── */
export function Tabla({ datos }) {
  return (
    <div className="overflow-auto max-h-[360px] -mx-1">
      <table className="w-full text-xs">
        <thead>
          <tr>
            {datos.columnas.map((c, i) => (
              <th key={c} className={`sticky top-0 bg-white font-medium py-1.5 px-2 border-b border-gray-100 ${datos.roles[i] === 'numero' ? 'text-right' : 'text-left'}`} style={{ color: TINTA.suave }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {datos.filas.map((f, r) => (
            <tr key={r} className="border-b border-gray-50 last:border-0">
              {f.map((v, i) => (
                <td key={i} className={`py-1.5 px-2 whitespace-nowrap ${datos.roles[i] === 'numero' ? 'text-right tabular-nums' : ''}`} style={{ color: TINTA.secundaria }}>
                  {v === null ? '' : typeof v === 'number' ? fmtNum(v) : String(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[11px] mt-2 px-2" style={{ color: TINTA.suave }}>Mostrando {datos.filas.length} de {fmtNum(datos.total)} filas</p>
    </div>
  )
}

/* ── Vista alternativa en tabla (accesibilidad) ───────────────────────────────── */
export function TablaAlternativa({ widget, datos }) {
  let cols = [], filas = []
  if (['linea', 'area', 'barras'].includes(widget.tipo)) {
    cols = [widget.x, ...datos.series.map(s => s.nombre)]
    filas = datos.categorias.map((c, i) => [etiquetaLarga(c, datos.grano), ...datos.series.map(s => s.valores[i])])
  } else if (widget.tipo === 'dona') {
    cols = [widget.x, 'Valor', '%']; filas = datos.partes.map(p => [p.nombre, p.valor, p.pct])
  } else if (widget.tipo === 'pareto') {
    cols = [widget.x, 'Valor', '% acumulado']; filas = datos.categorias.map((c, i) => [c, datos.valores[i], datos.acumulado[i]])
  } else if (widget.tipo === 'histograma') {
    cols = ['Desde', 'Hasta', 'Filas']; filas = datos.bins.map(b => [b.desde, b.hasta, b.n])
  } else if (widget.tipo === 'calor') {
    cols = [widget.y, ...datos.columnas]; filas = datos.filas.map((f, j) => [f, ...datos.valores[j]])
  } else if (widget.tipo === 'mapa') {
    const conCat = datos.series?.length > 0
    cols = ['Latitud', 'Longitud', datos.medida ? `${datos.agg} de ${datos.medida}` : 'Filas', ...(datos.medida ? ['Filas'] : []), ...(conCat ? ['Categoría'] : [])]
    filas = datos.puntos.slice(0, 100).map(p => [p[0], p[1], datos.medida ? p[2] : p[3], ...(datos.medida ? [p[3]] : []), ...(conCat ? [datos.series[p[4]]] : [])])
  } else return null
  return (
    <div className="overflow-auto max-h-[260px]">
      <table className="w-full text-xs">
        <thead><tr>{cols.map(c => <th key={c} className="sticky top-0 bg-white text-left font-medium py-1 px-2 border-b border-gray-100" style={{ color: TINTA.suave }}>{etiquetaPeriodo(c, datos.grano)}</th>)}</tr></thead>
        <tbody>{filas.map((f, i) => (
          <tr key={i} className="border-b border-gray-50 last:border-0">
            {f.map((v, j) => <td key={j} className={`py-1 px-2 ${typeof v === 'number' ? 'tabular-nums' : ''}`} style={{ color: TINTA.secundaria }}>{v === null ? '' : typeof v === 'number' ? fmtNum(v) : String(v)}</td>)}
          </tr>))}
        </tbody>
      </table>
    </div>
  )
}

export function vacio(widget, datos) {
  switch (widget.tipo) {
    case 'kpi': return datos.valor === null
    case 'linea': case 'area': case 'barras': return !datos.categorias?.length
    case 'dona': return !datos.partes?.length
    case 'pareto': return !datos.categorias?.length
    case 'dispersion': return !datos.puntos?.length
    case 'histograma': return !datos.bins?.length
    case 'calor': return !datos.filas?.length
    case 'mapa': return !datos.puntos?.length
    default: return false
  }
}

export function Grafica({ widget, datos }) {
  switch (widget.tipo) {
    case 'kpi': return <Kpi widget={widget} datos={datos} />
    case 'linea': case 'area': return <LineaArea widget={widget} datos={datos} />
    case 'barras': return <Barras widget={widget} datos={datos} />
    case 'dona': return <Dona widget={widget} datos={datos} />
    case 'pareto': return <Pareto widget={widget} datos={datos} />
    case 'dispersion': return <Dispersion widget={widget} datos={datos} />
    case 'histograma': return <Histograma widget={widget} datos={datos} />
    case 'calor': return <MapaCalor widget={widget} datos={datos} />
    case 'mapa': return <Suspense fallback={<div className="animate-pulse bg-gray-100 rounded-lg" style={{ height: 340 }} />}><Mapa widget={widget} datos={datos} /></Suspense>
    case 'tabla': return <Tabla datos={datos} />
    default: return null
  }
}
