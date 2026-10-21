import { useState } from 'react'
import { formatValue, ymLabel } from './format.js'

const W = 320, H = 120, PAD = { l: 40, r: 6, t: 8, b: 20 }

// 가구 평균 전기요금 월별 막대 (한전, 최근 24개월). 한 계열이라 강조색 하나, 마우스를 올리면 그 달 값
export default function PowerChart({ rows }) {
  const [hover, setHover] = useState(null)
  if (!rows?.length) return <p className="muted">전기 자료가 없습니다.</p>
  const max = Math.max(...rows.map((r) => r.bill)) * 1.1
  const bw = (W - PAD.l - PAD.r) / rows.length
  const y = (v) => PAD.t + (1 - v / max) * (H - PAD.t - PAD.b)
  const ticks = [0, max / 2, max].map((v) => Math.round(v / 1000) * 1000)
  const h = hover !== null ? rows[hover] : rows[rows.length - 1]
  return (
    <div className="trend">
      <p className="small muted">{ymLabel(h.ym)} · 평균 {formatValue(h.bill, '원/월')} · {Math.round(h.power_kwh)}kWh</p>
      <div className="chart-box">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="가구 평균 전기요금 월별 추이"
             onMouseLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} />
              <text className="axis" x={PAD.l - 4} y={y(t) + 3} textAnchor="end">{(t / 10000).toFixed(1)}만</text>
            </g>
          ))}
          {rows.map((r, i) => (
            <rect key={r.ym} x={PAD.l + i * bw + 1} width={Math.max(1, bw - 2)} y={y(r.bill)} height={y(0) - y(r.bill)}
                  rx="1.5" fill={hover === i ? '#104281' : '#2a78d6'} onMouseEnter={() => setHover(i)} />
          ))}
          <text className="axis" x={PAD.l} y={H - 4}>{ymLabel(rows[0].ym)}</text>
          <text className="axis" x={W - PAD.r} y={H - 4} textAnchor="end">{ymLabel(rows[rows.length - 1].ym)}</text>
        </svg>
      </div>
    </div>
  )
}
