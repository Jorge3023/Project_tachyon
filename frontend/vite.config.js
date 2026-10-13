import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_BASE solo hace falta si publicas en una subcarpeta (ej. GitHub Pages: /Project_tachyon/).
// En Cloudflare Pages / Render / dominio propio se deja en '/'.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || '/',
})
