import { lazy, Suspense } from 'react'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, PieChart, Pie, Cell, ScatterChart, Scatter, ZAxis,
} from 'recharts'
import {
  TINTA, PALETA, colorSerie, colorRampa, tintaSobre, fmtNum, fmtValor, etiquetaPeriodo, etiquetaLarga,
} from '@/features/dashboard/lib/dash'

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
  const grano = d?.grano || (widget.grano === 'auto' ? 'mes' : widget.grano)
  return (
    <div>
      <p className="text-2xl sm:text-3xl font-semibold tracking-tight tabular-nums" style={{ color: TINTA.primaria }}
        title={datos.valor === null ? '' : fmtValor(datos.valor, datos.formato)}>
        {fmtValor(datos.valor, datos.formato, 'cifra')}
      </p>
      {d && d.pct !== null && (
        <p className="text-xs mt-1 flex items-center gap-1 flex-wrap" style={{ color: TINTA.secundaria }}>
          <span aria-hidden="true">{sube ? '▲' : baja ? '▼' : '■'}</span>
          <span className="font-medium">{sube ? '+' : ''}{fmtNum(d.pct)} %</span>
          <span>{etiquetaPeriodo(d.actual, grano)} vs {etiquetaPeriodo(d.anterior, grano)}</span>
        </p>
      )}
      {d?.excluido && (
        <p className="text-xs mt-0.5" style={{ color: TINTA.suave || TINTA.secundaria }}>
          Sin contar {etiquetaPeriodo(d.excluido, d.grano)}: está incompleto
        </p>
      )}
    </div>
  )
}

/* ── Líneas / área / barras ─────────────────────────────────────────────────── */
// v{j}: el valor real (tooltip). s{j}: lo que se dibuja sólido. p{j}: el tramo hacia el último periodo, que está
// incompleto (los datos no llegan a fin de mes) y se dibuja punteado para que no se lea como una caída.
function datosCategorias(datos, partir = false) {
  const n = datos.categorias.length
  const parcial = partir && datos.parcial && n >= 2 && datos.categorias[n - 1] === datos.parcial
  return datos.categorias.map((c, i) => {
    const fila = { c, etiqueta: etiquetaPeriodo(c, datos.grano) }
    datos.series.forEach((s, j) => {
      const v = s.valores[i]
      fila[`v${j}`] = v
      fila[`s${j}`] = parcial && i === n - 1 ? null : v
      if (parcial) fila[`p${j}`] = i >= n - 2 ? v : null
    })
    return fila
  })
}

function TooltipSeries({ active, payload, datos }) {
  if (!active || !payload?.length) return null
  const fila = payload[0].payload
  const parcial = datos.parcial && fila.c === datos.parcial
  return <CajaTooltip titulo={`${etiquetaLarga(fila.c, datos.grano)}${parcial ? ' (incompleto)' : ''}`}
    filas={datos.series.map((s, j) => ({ nombre: s.nombre, valor: fmtValor(fila[`v${j}`], datos.formato), color: colorSerie(j, s.nombre, datos.series.length === 1 ? datos._color : null) }))} />
}

export function LineaArea({ widget, datos }) {
  const area = widget.tipo === 'area'
  const multi = datos.series.length > 1
  const partir = !(area && multi)                     // con áreas apiladas el tramo punteado no se puede separar
  const data = datosCategorias(datos, partir)
  const conParcial = partir && data.some(f => f.p0 !== undefined)
  const Chart = area ? AreaChart : LineChart
  const ejeY = v => fmtValor(v, datos.formato, 'compacto')
  return (
    <>
      <ResponsiveContainer width="100%" height={ALTO}>
        <Chart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={TINTA.rejilla} />
          <XAxis dataKey="etiqueta" {...EJE} minTickGap={24} interval="preserveStartEnd" />
          <YAxis {...EJE} width={56} tickFormatter={ejeY} axisLine={false} />
          <Tooltip content={<TooltipSeries datos={{ ...datos, _color: widget.color ?? 0 }} />} cursor={{ stroke: TINTA.eje }} />
          {datos.series.map((s, j) => {
            const col = colorSerie(j, s.nombre, multi ? null : widget.color ?? 0)
            const punto = { r: 4, stroke: TINTA.superficie, strokeWidth: 2 }
            return area
              ? [<Area key={j} type="monotone" dataKey={`s${j}`} stroke={col} strokeWidth={2} fill={col} fillOpacity={0.15}
                  stackId={multi ? 'a' : undefined} dot={false} activeDot={punto} isAnimationActive={false} />,
                 conParcial && <Area key={`p${j}`} type="monotone" dataKey={`p${j}`} stroke={col} strokeWidth={2} strokeDasharray="4 4"
                  fill={col} fillOpacity={0.06} dot={false} activeDot={false} isAnimationActive={false} legendType="none" />]
              : [<Line key={j} type="monotone" dataKey={`s${j}`} stroke={col} strokeWidth={2} dot={false}
                  activeDot={punto} isAnimationActive={false} />,
                 conParcial && <Line key={`p${j}`} type="monotone" dataKey={`p${j}`} stroke={col} strokeWidth={2} strokeDasharray="4 4"
                  dot={false} activeDot={false} isAnimationActive={false} legendType="none" />]
          })}
        </Chart>
      </ResponsiveContainer>
      {multi && <Leyenda items={datos.series.map((s, j) => ({ nombre: s.nombre, color: colorSerie(j, s.nombre) }))} />}
    </>
  )
}

// Clic en una barra, porción o fila de Pareto → filtra el resto del tablero por esa categoría.
// `elegido` es el valor ya filtrado: se resalta y lo demás se atenúa. «Otros» no se puede elegir (agrupa varias).
const elegible = (v) => v !== undefined && v !== null && v !== 'Otros'

export function Barras({ widget, datos, onElegir, elegido }) {
  const data = datosCategorias(datos)
  const horiz = widget.orientacion === 'h'
  const multi = datos.series.length > 1
  const apilado = multi && widget.apilado
  const largo = Math.max(...datos.categorias.map(c => String(c).length), 0)
  const ejeV = v => fmtValor(v, datos.formato, 'compacto')
  const ultimo = datos.parcial ? datos.categorias.length - 1 : -1      // barra del periodo incompleto: más tenue
  const clic = onElegir && !datos.grano ? (e) => { const c = e?.payload?.c ?? e?.c; if (elegible(c)) onElegir(widget.x, c) } : undefined
  const opacidad = (i) => (i === ultimo ? 0.4 : 1) * (elegido !== undefined && data[i]?.c !== elegido ? 0.35 : 1)
  const conCeldas = ultimo >= 0 || elegido !== undefined
  return (
    <>
      <ResponsiveContainer width="100%" height={horiz ? Math.max(ALTO, datos.categorias.length * 30 + 30) : ALTO}>
        <BarChart data={data} layout={horiz ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          barCategoryGap={horiz ? '30%' : '25%'} barGap={2}>
          <CartesianGrid horizontal={!horiz} vertical={horiz} stroke={TINTA.rejilla} />
          {horiz ? (
            <>
              <XAxis type="number" {...EJE} tickFormatter={ejeV} axisLine={false} />
              <YAxis type="category" dataKey="etiqueta" {...EJE} width={Math.min(130, 20 + largo * 6)} tickFormatter={v => corta(v, 20)} />
            </>
          ) : (
            <>
              <XAxis dataKey="etiqueta" {...EJE} interval={data.length <= 14 ? 0 : 'preserveStartEnd'} minTickGap={12}
                tickFormatter={v => corta(v, data.length > 8 ? 8 : 14)} />
              <YAxis {...EJE} width={56} tickFormatter={ejeV} axisLine={false} />
            </>
          )}
          <Tooltip content={<TooltipSeries datos={{ ...datos, _color: widget.color ?? 0 }} />} cursor={{ fill: 'rgba(11,11,11,0.04)' }} />
          {datos.series.map((s, j) => (
            <Bar key={j} dataKey={`s${j}`} fill={colorSerie(j, s.nombre, multi ? null : widget.color ?? 0)} maxBarSize={24}
              stackId={apilado ? 'a' : undefined}
              stroke={apilado ? TINTA.superficie : 'none'} strokeWidth={apilado ? 2 : 0}
              radius={apilado ? 0 : horiz ? [0, 4, 4, 0] : [4, 4, 0, 0]} isAnimationActive={false}
              onClick={clic} cursor={clic ? 'pointer' : undefined}>
              {conCeldas && data.map((_, i) => <Cell key={i} fillOpacity={opacidad(i)} />)}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
      {multi && <Leyenda items={datos.series.map((s, j) => ({ nombre: s.nombre, color: colorSerie(j, s.nombre) }))} />}
    </>
  )
}

/* ── Circular ───────────────────────────────────────────────────────────────── */
export function Dona({ widget, datos, onElegir, elegido }) {
  const partes = datos.partes
  const clic = onElegir ? (nombre) => { if (elegible(nombre)) onElegir(widget.x, nombre) } : null
  const tenue = (n) => elegido !== undefined && n !== elegido
  return (
    <div className="flex items-center gap-4 flex-wrap justify-center">
      <div className="relative" style={{ width: 170, height: 170 }}>
        <PieChart width={170} height={170}>
          <Pie data={partes} dataKey="valor" nameKey="nombre" innerRadius={55} outerRadius={82} paddingAngle={partes.length > 1 ? 2 : 0}
            stroke={TINTA.superficie} strokeWidth={2} isAnimationActive={false}
            onClick={clic ? (e) => clic(e?.payload?.nombre ?? e?.name) : undefined} cursor={clic ? 'pointer' : undefined}>
            {partes.map((p, i) => <Cell key={p.nombre} fill={colorSerie(i, p.nombre)} fillOpacity={tenue(p.nombre) ? 0.3 : 1} />)}
          </Pie>
          <Tooltip content={({ active, payload }) => active && payload?.length
            ? <CajaTooltip titulo={payload[0].payload.nombre} filas={[{ nombre: 'Valor', valor: fmtValor(payload[0].payload.valor, datos.formato) }, { nombre: 'Participación', valor: `${fmtNum(payload[0].payload.pct)} %` }]} /> : null} />
        </PieChart>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-lg font-semibold" style={{ color: TINTA.primaria }}>{fmtValor(datos.total, datos.formato, 'compacto')}</span>
          <span className="text-[11px]" style={{ color: TINTA.suave }}>total</span>
        </div>
      </div>
      <ul className="text-xs space-y-1.5 min-w-[130px] flex-1">
        {partes.map((p, i) => {
          const contenido = <>
            <span className="inline-block w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: colorSerie(i, p.nombre), opacity: tenue(p.nombre) ? 0.3 : 1 }} />
            <span className="truncate" style={{ color: TINTA.secundaria }} title={p.nombre}>{p.nombre}</span>
            <span className="ml-auto tabular-nums font-medium" style={{ color: TINTA.primaria }}>{fmtNum(p.pct)} %</span>
          </>
          return (
            <li key={p.nombre}>
              {clic && elegible(p.nombre)
                ? <button type="button" onClick={() => clic(p.nombre)} aria-pressed={elegido === p.nombre}
                    className="w-full flex items-center gap-2 text-left rounded hover:bg-gray-50 -mx-1 px-1">{contenido}</button>
                : <div className="flex items-center gap-2">{contenido}</div>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/* ── Pareto: ranking con el acumulado como etiqueta (un solo eje) ──────────────── */
export function Pareto({ widget, datos, onElegir, elegido }) {
  const max = Math.max(...datos.valores, 0) || 1
  const col = PALETA[widget.color ?? 0]
  return (
    <div>
      <div className="flex text-[11px] mb-1 gap-3" style={{ color: TINTA.suave }}>
        <span className="flex-1">Categoría</span><span className="w-20 text-right">Valor</span><span className="w-16 text-right">Acumulado</span>
      </div>
      <ol className="space-y-1.5">
        {datos.categorias.map((c, i) => {
          const fila = <>
            <span className="w-24 truncate flex-shrink-0" style={{ color: TINTA.secundaria }} title={c}>{c}</span>
            <span className="flex-1 h-4 rounded-r" style={{ background: '#f0efec' }}>
              <span className="block h-full" style={{ width: `${(datos.valores[i] / max) * 100}%`, background: col, borderRadius: '0 4px 4px 0', minWidth: 2,
                opacity: elegido !== undefined && c !== elegido ? 0.35 : 1 }} />
            </span>
            <span className="w-20 text-right tabular-nums whitespace-nowrap" style={{ color: TINTA.primaria }}>{fmtValor(datos.valores[i], datos.formato, 'compacto')}</span>
            <span className="w-16 text-right tabular-nums whitespace-nowrap" style={{ color: TINTA.secundaria }}>{fmtValor(datos.acumulado[i], 'porcentaje', 'compacto')}</span>
          </>
          return (
            <li key={c}>
              {onElegir && elegible(c)
                ? <button type="button" onClick={() => onElegir(widget.x, c)} aria-pressed={elegido === c}
                    className="w-full flex items-center gap-3 text-xs text-left rounded hover:bg-gray-50">{fila}</button>
                : <div className="flex items-center gap-3 text-xs">{fila}</div>}
            </li>
          )
        })}
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
      <ResponsiveContainer width="100%" height={ALTO + 16}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: 18, left: 8 }}>
          <CartesianGrid stroke={TINTA.rejilla} />
          <XAxis type="number" dataKey="x" name={widget.x} {...EJE} tickFormatter={v => fmtValor(v, datos.formato_x, 'compacto')} domain={['auto', 'auto']}
            label={{ value: widget.x, position: 'insideBottom', offset: -12, fill: TINTA.secundaria, fontSize: 11 }} />
          <YAxis type="number" dataKey="y" name={widget.y} {...EJE} width={60} tickFormatter={v => fmtValor(v, datos.formato_y, 'compacto')} axisLine={false} domain={['auto', 'auto']}
            label={{ value: widget.y, angle: -90, position: 'insideLeft', offset: 0, fill: TINTA.secundaria, fontSize: 11, style: { textAnchor: 'middle' } }} />
          <ZAxis range={[48, 48]} />
          <Tooltip cursor={{ strokeDasharray: '3 3', stroke: TINTA.eje }} content={({ active, payload }) => active && payload?.length
            ? <CajaTooltip titulo={multi ? payload[0].name : undefined} filas={[{ nombre: widget.x, valor: fmtValor(payload[0].payload.x, datos.formato_x) }, { nombre: widget.y, valor: fmtValor(payload[0].payload.y, datos.formato_y) }]} /> : null} />
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
  const data = datos.bins.map(b => ({ ...b, etiqueta: fmtValor(b.desde, datos.formato, 'compacto'), rango: `${fmtValor(b.desde, datos.formato)} – ${fmtValor(b.hasta, datos.formato)}` }))
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
          {columnas.map((c, i) => <EncabezadoPeriodo key={c} c={c} previo={columnas[i - 1]} grano={datos.grano} />)}
          {filas.map((f, j) => (
            <Fila key={f} nombre={f} celdas={valores[j]} columnas={columnas} min={min} rango={rango} mostrar={mostrarValor} grano={datos.grano} formato={datos.formato} />
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2 mt-3 text-[11px]" style={{ color: TINTA.suave }}>
        <span>{fmtValor(min, datos.formato, 'compacto')}</span>
        <span className="h-2 flex-1 max-w-[140px] rounded" style={{ background: `linear-gradient(90deg, ${colorRampa(0)}, ${colorRampa(0.5)}, ${colorRampa(1)})` }} />
        <span>{fmtValor(max, datos.formato, 'compacto')}</span>
      </div>
    </div>
  )
}
/** Encabezado de columna del mapa de calor: con meses, «ene» y el año solo cuando cambia (las columnas son angostas). */
function EncabezadoPeriodo({ c, previo, grano }) {
  const s = String(c)
  if (grano === 'mes' && /^\d{4}-\d{2}$/.test(s)) {
    const anio = s.slice(0, 4), nuevo = !previo || String(previo).slice(0, 4) !== anio
    return (
      <span className="text-center leading-tight px-0.5" style={{ color: TINTA.suave }} title={etiquetaLarga(s, grano)}>
        {etiquetaPeriodo(s, grano).split(' ')[0]}
        <span className="block text-[10px]" style={{ color: nuevo ? TINTA.secundaria : 'transparent' }}>{anio}</span>
      </span>
    )
  }
  return <span className="text-center truncate px-0.5" style={{ color: TINTA.suave }} title={s}>{etiquetaPeriodo(s, grano)}</span>
}

function Fila({ nombre, celdas, columnas, min, rango, mostrar, grano, formato }) {
  return (
    <>
      <span className="truncate pr-2 flex items-center" style={{ color: TINTA.secundaria }} title={nombre}>{nombre}</span>
      {celdas.map((v, i) => {
        const bg = v === null ? '#f0efec' : colorRampa((v - min) / rango)
        return (
          <span key={i} className="h-7 rounded-sm flex items-center justify-center tabular-nums"
            style={{ background: bg, color: v === null ? TINTA.suave : tintaSobre(bg) }}
            title={`${nombre} · ${etiquetaLarga(columnas[i], grano)}: ${v === null ? 'sin datos' : fmtValor(v, formato)}`}>
            {mostrar && v !== null ? fmtValor(v, formato, 'compacto') : ''}
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
                  {v === null ? '' : typeof v === 'number' ? fmtValor(v, datos.formatos?.[i]) : String(v)}
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
  let cols = [], filas = [], formatos = []          // formato de cada columna (moneda, porcentaje o número)
  const f = datos.formato
  if (['linea', 'area', 'barras'].includes(widget.tipo)) {
    cols = [widget.x, ...datos.series.map(s => s.nombre)]
    filas = datos.categorias.map((c, i) => [etiquetaLarga(c, datos.grano), ...datos.series.map(s => s.valores[i])])
    formatos = cols.map((_, j) => (j ? f : null))
  } else if (widget.tipo === 'dona') {
    cols = [widget.x, 'Valor', '%']; filas = datos.partes.map(p => [p.nombre, p.valor, p.pct]); formatos = [null, f, 'porcentaje']
  } else if (widget.tipo === 'pareto') {
    cols = [widget.x, 'Valor', '% acumulado']; filas = datos.categorias.map((c, i) => [c, datos.valores[i], datos.acumulado[i]]); formatos = [null, f, 'porcentaje']
  } else if (widget.tipo === 'histograma') {
    cols = ['Desde', 'Hasta', 'Filas']; filas = datos.bins.map(b => [b.desde, b.hasta, b.n]); formatos = [f, f, null]
  } else if (widget.tipo === 'calor') {
    cols = [widget.y, ...datos.columnas]; filas = datos.filas.map((fl, j) => [fl, ...datos.valores[j]])
    formatos = cols.map((_, j) => (j ? f : null))
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
            {f.map((v, j) => <td key={j} className={`py-1 px-2 ${typeof v === 'number' ? 'tabular-nums' : ''}`} style={{ color: TINTA.secundaria }}>{v === null ? '' : typeof v === 'number' ? fmtValor(v, formatos[j]) : String(v)}</td>)}
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

export function Grafica({ widget, datos, onElegir, elegido }) {
  switch (widget.tipo) {
    case 'kpi': return <Kpi widget={widget} datos={datos} />
    case 'linea': case 'area': return <LineaArea widget={widget} datos={datos} />
    case 'barras': return <Barras widget={widget} datos={datos} onElegir={onElegir} elegido={elegido} />
    case 'dona': return <Dona widget={widget} datos={datos} onElegir={onElegir} elegido={elegido} />
    case 'pareto': return <Pareto widget={widget} datos={datos} onElegir={onElegir} elegido={elegido} />
    case 'dispersion': return <Dispersion widget={widget} datos={datos} />
    case 'histograma': return <Histograma widget={widget} datos={datos} />
    case 'calor': return <MapaCalor widget={widget} datos={datos} />
    case 'mapa': return <Suspense fallback={<div className="animate-pulse bg-gray-100 rounded-lg" style={{ height: 340 }} />}><Mapa widget={widget} datos={datos} /></Suspense>
    case 'tabla': return <Tabla datos={datos} />
    default: return null
  }
}
