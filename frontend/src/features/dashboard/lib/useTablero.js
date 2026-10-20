import { useRef, useState, useLayoutEffect, useCallback } from 'react'

/*
 * Tablero con reordenamiento animado.
 *
 *  - Arrastre con puntero (mouse, dedo o lápiz) desde el asa de cada tarjeta: la tarjeta se levanta y sigue al
 *    puntero en tiempo real, y las demás se deslizan a su nuevo lugar (técnica FLIP: medir antes, medir después
 *    y animar solo la diferencia con `transform`, que es barato para el navegador).
 *  - Cada cambio de orden o de ancho hecho desde el panel o los botones ↑ ↓ también se anima: basta llamar
 *    a `instantanea()` justo antes de cambiar el estado.
 *  - Respeta «reducir movimiento» del sistema. Cerca de los bordes de la pantalla desplaza el tablero solo.
 */
const DURACION = 240
const CURVA = 'cubic-bezier(.2,.8,.2,1)'
const sinMovimiento = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function contenedorConScroll(el) {
  for (let p = el?.parentElement; p; p = p.parentElement) {
    const o = getComputedStyle(p).overflowY
    if ((o === 'auto' || o === 'scroll') && p.scrollHeight > p.clientHeight + 1) return p
  }
  return window
}

/**
 * @param claveLayout  texto que cambia cuando cambia el orden o el ancho de las tarjetas
 * @param reordenar    (idQueSeMueve, idDestino) => void  — mueve la tarjeta a la posición de la otra
 */
export default function useTablero(claveLayout, reordenar) {
  const rejilla = useRef(null)
  const cajas = useRef(new Map())       // id → celda de la cuadrícula (la que cambia de lugar)
  const tarjetas = useRef(new Map())    // id → tarjeta visible (la que se levanta y sigue al puntero)
  const previas = useRef(null)          // posiciones antes del cambio
  const drag = useRef(null)
  const reordenarRef = useRef(reordenar); reordenarRef.current = reordenar
  const [arrastrando, setArrastrando] = useState(null)

  const caja = useCallback((id) => (el) => { el ? cajas.current.set(id, el) : cajas.current.delete(id) }, [])
  const tarjeta = useCallback((id) => (el) => { el ? tarjetas.current.set(id, el) : tarjetas.current.delete(id) }, [])

  /** Medir ahora (posición visual, incluso si hay una animación en curso). Llamar justo antes de cambiar el estado. */
  const instantanea = useCallback(() => {
    const g = rejilla.current
    if (!g) return
    const base = g.getBoundingClientRect()
    const m = new Map()
    cajas.current.forEach((el, id) => { const r = el.getBoundingClientRect(); m.set(id, { x: r.left - base.left, y: r.top - base.top }) })
    previas.current = { m, t: performance.now() }
  }, [])

  const aplicar = useCallback(() => {
    const d = drag.current
    if (!d) return
    const c = cajas.current.get(d.id), t = tarjetas.current.get(d.id)
    if (!c || !t) return
    const r = c.getBoundingClientRect()                       // la celda no tiene transform: es su lugar real
    t.style.transform = `translate(${d.x - d.gx - r.left}px, ${d.y - d.gy - r.top}px) scale(1.02)`
  }, [])

  // Después de cada cambio de orden/ancho: animar desde donde estaban hasta donde quedaron
  useLayoutEffect(() => {
    const p = previas.current; previas.current = null
    if (drag.current) aplicar()                               // la tarjeta arrastrada cambió de celda: seguir al puntero
    if (!p || performance.now() - p.t > 600 || !rejilla.current) return
    const base = rejilla.current.getBoundingClientRect()
    const movidas = [], nuevas = []
    cajas.current.forEach(el => { el.style.transition = 'none'; el.style.transform = '' })
    cajas.current.forEach((el, id) => {
      if (id === drag.current?.id) return
      const antes = p.m.get(id)
      if (!antes) { nuevas.push(el); return }
      const r = el.getBoundingClientRect()
      const dx = antes.x - (r.left - base.left), dy = antes.y - (r.top - base.top)
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return
      el.style.transform = `translate(${dx}px, ${dy}px)`
      movidas.push(el)
    })
    if (sinMovimiento()) { movidas.forEach(el => { el.style.transform = '' }); return }
    nuevas.forEach(el => el.animate?.([{ opacity: 0, transform: 'scale(.96)' }, { opacity: 1, transform: 'none' }], { duration: 220, easing: CURVA }))
    if (!movidas.length) return
    void rejilla.current.offsetWidth                           // forzar el cálculo con el transform inverso aplicado
    requestAnimationFrame(() => movidas.forEach(el => { el.style.transition = `transform ${DURACION}ms ${CURVA}`; el.style.transform = '' }))
    setTimeout(() => movidas.forEach(el => { if (!el.style.transform) el.style.transition = '' }), DURACION + 60)
  }, [claveLayout, aplicar])

  const decidir = useCallback(() => {
    const d = drag.current
    if (!d) return
    const ahora = performance.now()
    if (ahora - d.ultimo < 170) return                         // dejar terminar la animación anterior
    for (const [id, el] of cajas.current) {
      if (id === d.id) continue
      const r = el.getBoundingClientRect()
      if (d.x >= r.left && d.x <= r.right && d.y >= r.top && d.y <= r.bottom) {
        d.ultimo = ahora
        reordenarRef.current?.(d.id, id)
        break
      }
    }
  }, [])

  const bucle = useCallback(() => {
    const d = drag.current
    if (!d) return
    const sc = d.scroller
    const r = sc === window ? { top: 0, bottom: window.innerHeight } : sc.getBoundingClientRect()
    const zona = 90
    let v = 0
    if (d.y < r.top + zona) v = -Math.ceil((r.top + zona - d.y) / 5)
    else if (d.y > r.bottom - zona) v = Math.ceil((d.y - (r.bottom - zona)) / 5)
    v = Math.max(-26, Math.min(26, v))
    if (v) {
      if (sc === window) window.scrollBy(0, v); else sc.scrollTop += v
      aplicar()
    }
    decidir()                                                  // también con el puntero quieto: si quedó pendiente un cambio, se hace al terminar la pausa
    d.raf = requestAnimationFrame(bucle)
  }, [aplicar, decidir])

  const mover = useCallback((e) => {
    const d = drag.current
    if (!d || (d.pid !== undefined && e.pointerId !== d.pid)) return
    d.x = e.clientX; d.y = e.clientY
    aplicar(); decidir()
  }, [aplicar, decidir])

  const soltar = useCallback(() => {
    const d = drag.current
    if (!d) return
    cancelAnimationFrame(d.raf)
    window.removeEventListener('pointermove', mover)
    window.removeEventListener('pointerup', soltar)
    window.removeEventListener('pointercancel', soltar)
    window.removeEventListener('keydown', tecla)
    document.body.style.userSelect = d.userSelect
    const t = tarjetas.current.get(d.id)
    if (t) {
      aplicar()
      const ms = sinMovimiento() ? 0 : 220
      t.style.transition = `transform ${ms}ms ${CURVA}`
      t.style.transform = ''
      setTimeout(() => { if (!drag.current) t.style.transition = '' }, ms + 40)
    }
    drag.current = null
    setArrastrando(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aplicar, mover])
  const tecla = useCallback((e) => { if (e.key === 'Escape') soltar() }, [soltar])

  /** onPointerDown del asa de una tarjeta. */
  const iniciar = useCallback((e, id) => {
    if (drag.current || (e.button !== undefined && e.button !== 0)) return
    const c = cajas.current.get(id), t = tarjetas.current.get(id)
    if (!c || !t) return
    e.preventDefault()
    c.style.transition = 'none'; c.style.transform = ''
    const r = c.getBoundingClientRect()
    drag.current = { id, gx: e.clientX - r.left, gy: e.clientY - r.top, x: e.clientX, y: e.clientY, ultimo: 0, pid: e.pointerId,
      scroller: contenedorConScroll(rejilla.current), raf: 0, userSelect: document.body.style.userSelect }
    try { e.currentTarget.setPointerCapture?.(e.pointerId) } catch { /* el puntero ya no está activo */ }
    document.body.style.userSelect = 'none'
    t.style.transition = 'none'
    setArrastrando(id)
    aplicar()
    window.addEventListener('pointermove', mover)
    window.addEventListener('pointerup', soltar)
    window.addEventListener('pointercancel', soltar)
    window.addEventListener('keydown', tecla)
    drag.current.raf = requestAnimationFrame(bucle)
  }, [aplicar, mover, soltar, tecla, bucle])

  return { rejilla, caja, tarjeta, arrastrando, iniciar, instantanea }
}
