// API 주소: 빌드할 때 VITE_API_BASE(예: https://xxxx.ngrok-free.dev)가 있으면 그 서버를 부른다.
// 비어 있으면 '/api'를 그대로 쓴다 → 로컬 개발에서는 vite 프록시가 localhost:8000으로 넘긴다 (vite.config.js).
// 배포 값은 web/.env.production, 또는 Vercel 환경변수(같은 이름, 이쪽이 우선).
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')

// ngrok 무료 도메인은 브라우저 요청에 경고 페이지(HTML)를 끼워 넣는다 → 이 헤더가 있으면 건너뛴다.
// (헤더 때문에 브라우저가 사전 요청(OPTIONS)을 보내므로 API의 CORS가 이 헤더를 허용해야 한다: api/main.py)
const EXTRA_HEADERS = /ngrok/.test(BASE) ? { 'ngrok-skip-browser-warning': '1' } : {}

export function apiFetch(path, opts = {}) {
  return fetch(`${BASE}${path}`, { ...opts, headers: { ...EXTRA_HEADERS, ...(opts.headers || {}) } })
}

export async function apiJSON(path, opts) {
  const r = await apiFetch(path, opts)
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return r.json()
}
