import { useState } from 'react'
import { RAMP, NO_DATA, formatShort, UNIT_TITLE } from './format.js'

// compact(휴대폰): 처음엔 색 막대 한 줄만, 누르면 구간까지 펼친다
export default function Legend({ metric, breaks, compact = false }) {
  const [open, setOpen] = useState(false)
  const edges = [null, ...breaks, null]
  const label = (i) => {
    const lo = edges[i], hi = edges[i + 1]
    if (lo === null) return `${formatShort(hi, metric.unit)} 이하`
    if (hi === null) return `${formatShort(lo, metric.unit)} 초과`
    return `${formatShort(lo, metric.unit)} ~ ${formatShort(hi, metric.unit)}`
  }
  if (compact && !open) {
    return (
      <button type="button" className="legend legend-mini" onClick={() => setOpen(true)} aria-label={`범례: ${metric.label}, 눌러서 펼치기`}>
        <span className="legend-bar">{RAMP.map((c) => <span key={c} style={{ background: c }} />)}</span>
        <span className="legend-ends"><span>{metric.better === 'low' ? '쌈' : '낮음'}</span><span>{metric.better === 'low' ? '비쌈' : '높음'}</span></span>
      </button>
    )
  }
  return (
    <div className="legend" aria-label="범례" onClick={compact ? () => setOpen(false) : undefined}>
      <div className="legend-title">{metric.label} <span className="muted">({UNIT_TITLE[metric.unit] || metric.unit})</span></div>
      <ul>
        {RAMP.map((c, i) => (
          <li key={c}><span className="swatch" style={{ background: c }} /><span>{label(i)}</span></li>
        ))}
        <li><span className="swatch" style={{ background: NO_DATA }} /><span>자료 없음</span></li>
        {metric.gran && <li><span className="swatch hatch" /><span>시도 평균으로 대체</span></li>}
      </ul>
      <div className="legend-note">{metric.better === 'low' ? '밝을수록 싸고, 진할수록 비쌉니다' : '진할수록 높습니다'} · 6분위</div>
    </div>
  )
}
