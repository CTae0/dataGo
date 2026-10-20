import { RAMP, NO_DATA, formatValue } from './format.js'

export default function Legend({ metric, breaks }) {
  const edges = [null, ...breaks, null]
  return (
    <div className="legend" aria-label="범례">
      <div className="legend-title">{metric.label}</div>
      <ul>
        {RAMP.map((c, i) => (
          <li key={c}>
            <span className="swatch" style={{ background: c }} />
            <span>
              {edges[i] === null ? '~ ' : `${formatValue(edges[i], metric.unit)} ~ `}
              {edges[i + 1] === null ? '' : formatValue(edges[i + 1], metric.unit)}
            </span>
          </li>
        ))}
        <li><span className="swatch" style={{ background: NO_DATA }} /><span>자료 없음</span></li>
        {metric.gran && <li><span className="swatch hatch" /><span>시도 평균으로 대체</span></li>}
      </ul>
      <div className="legend-note">{metric.better === 'low' ? '밝을수록 싸고, 진할수록 비쌉니다' : '진할수록 높습니다'} · 6분위</div>
    </div>
  )
}
