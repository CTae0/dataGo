// 휴대폰 지도 위 지표 칩 (가로로 밀어서 고른다)
export default function MetricChips({ metrics, value, onChange }) {
  return (
    <div className="metric-chips" role="radiogroup" aria-label="지도에 칠할 지표">
      {metrics.map((m) => (
        <button key={m.id} type="button" role="radio" aria-checked={value === m.id}
                className={`mchip ${value === m.id ? 'on' : ''}`} onClick={() => onChange(m.id)}>
          {m.label}
        </button>
      ))}
    </div>
  )
}
