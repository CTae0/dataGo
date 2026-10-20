import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api는 FastAPI(uvicorn, 8000)로 넘긴다: python -m uvicorn api.main:app --port 8000
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  // maplibre-gl v6의 worker(maplibre-gl-worker.mjs)가 ./maplibre-gl-shared.mjs를 상대경로로 불러서
  // 사전 번들(optimizeDeps)을 하면 경로가 깨진다 → 원본 ESM 그대로 쓴다
  optimizeDeps: { exclude: ['maplibre-gl'] },
})
