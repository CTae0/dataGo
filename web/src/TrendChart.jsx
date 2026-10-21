import { useMemo, useState } from 'react'
import { SERIES, SIZE_LABEL, formatValue, ymLabel } from './format.js'

const W = 320, H = 150, PAD = { l: 40, r: 10, t: 10, b: 22 }
const MIN_DEALS = 5   // 거래가 너무 적은 달은 점을 찍지 않는다

// 면적대별 월 환산 주거비 추이 (한 축, 2px 선, 십자선 툴팁, 표 보기)
export default function TrendChart({ rows }) {
  const [hover, setHover] = useState(null)
  const [asTable, setAsTable] = useState(false)
  const { months, series, yMax } = useMemo(() => {
    const months = [...new Set(rows.map((r) => r.deal_ym))].sort()
    const series = {}
    for (const b of ['s', 'm', 'l']) {
      const byYm = Object.fromEntries(rows.filter((r) => r.size_band === b && r.deals >= MIN_DEALS)
        .map((r) => [r.deal_ym, r.monthly_cost]))
      series[b] = months.map((ym) => byYm[ym] ?? null)
    }
    const all = Object.values(series).flat().filter((v) => v !== null)
    return { months, series, yMax: all.length ? Math.max(...all) * 1.1 : 1 }
  }, [rows])

  if (!months.length) return <p className="muted">전월세 거래 자료가 없습니다.</p>
  const x = (i) => PAD.l + (months.length === 1 ? 0 : (i / (months.length - 1)) * (W - PAD.l - PAD.r))
  const y = (v) => PAD.t + (1 - v / yMax) * (H - PAD.t - PAD.b)
  const path = (vals) => vals.map((v, i) => (v === null ? null : `${x(i)},${y(v)}`))
    .reduce((acc, p) => { if (p === null) acc.push([]); else acc[acc.length - 1].push(p); return acc }, [[]])
    .filter((seg) => seg.length).map((seg) => `M${seg.join('L')}`).join('')
  const ticks = [0, yMax / 2, yMax].map((v) => Math.round(v))

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (months.length - 1))
    setHover(Math.max(0, Math.min(months.length - 1, i)))
  }

  return (
    <div className="trend">
      <div className="trend-head">
        <ul className="series-legend">
          {Object.keys(SERIES).map((b) => (
            <li key={b}><span className="line-key" style={{ background: SERIES[b] }} />{SIZE_LABEL[b]}</li>
          ))}
        </ul>
        <button type="button" className="link" onClick={() => setAsTable(!asTable)}>{asTable ? '그래프로 보기' : '표로 보기'}</button>
      </div>
      {asTable ? (
        <div className="table-scroll">
          <table>
            <thead><tr><th>월</th>{Object.keys(SERIES).map((b) => <th key={b}>{SIZE_LABEL[b]}</th>)}</tr></thead>
            <tbody>
              {months.map((ym, i) => (
                <tr key={ym}><td>{ymLabel(ym)}</td>
                  {Object.keys(SERIES).map((b) => <td key={b}>{series[b][i] === null ? '–' : formatValue(series[b][i], '만원/월')}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart-box">
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="면적대별 월 환산 주거비 추이"
               onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
            {ticks.map((t, i) => (
              <g key={i}>
                <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="grid" />
                <text x={PAD.l - 6} y={y(t) + 3} className="axis" textAnchor="end">{t}</text>
              </g>
            ))}
            <text x={PAD.l} y={H - 6} className="axis">{ymLabel(months[0])}</text>
            <text x={W - PAD.r} y={H - 6} className="axis" textAnchor="end">{ymLabel(months[months.length - 1])}</text>
            {Object.entries(series).map(([b, vals]) => (
              <path key={b} d={path(vals)} fill="none" stroke={SERIES[b]} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            ))}
            {hover !== null && (
              <g>
                <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} className="crosshair" />
                {Object.entries(series).map(([b, vals]) => vals[hover] !== null && (
                  <circle key={b} cx={x(hover)} cy={y(vals[hover])} r="4" fill={SERIES[b]} stroke="#fff" strokeWidth="2" />
                ))}
              </g>
            )}
          </svg>
          {hover !== null && (
            <div className="chart-tip">
              <strong>{ymLabel(months[hover])}</strong>
              {Object.keys(SERIES).map((b) => (
                <span key={b}><i className="line-key" style={{ background: SERIES[b] }} />{SIZE_LABEL[b]}: {series[b][hover] === null ? '–' : formatValue(series[b][hover], '만원/월')}</span>
              ))}
            </div>
          )}
          <p className="muted small">단위: 만 원/월 (보증금은 연 5.5%로 환산). 거래 {MIN_DEALS}건 미만인 달은 비웁니다.</p>
        </div>
      )}
    </div>
  )
}
