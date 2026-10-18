import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The admin app imports the student web app's design CSS from ../web/src/styles (read only).
export default defineConfig({
  plugins: [react()],
  server: { fs: { allow: ['..'] } },
  build: { sourcemap: false },
})
