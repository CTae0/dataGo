import { STAR_GROUPS, formatValue, manwon } from './format.js'
import { starText } from './Results.jsx'

// 휴대폰 지도 시트의 지역 요약: 이름 · 지금 지표 값 · (결과가 있으면) 내 예상 생활비 · 별점 · 핵심 숫자
export default function RegionSummary({ summary: s, metric, mine, onMore }) {
  const r0 = (v) => (v == null ? '–' : Math.round(v).toLocaleString('ko-KR'))
  return (
    <div className="region-summary">
      <div className="rs-head">
        <div>
          <span className="muted">{s.sido}</span>
          <strong className="rs-name">{s.sigungu}</strong>
        </div>
        {metric && <span className="rs-metric">{metric.label}<b>{formatValue(s[metric.field], metric.unit)}</b></span>}
      </div>
      {mine && <p className="rs-mine">내 답 기준 <b>월 약 {manwon(mine.total)}</b> · 추천 {mine.rank}위</p>}
      <dl className="rs-grid">
        <div><dt>1인 주거비</dt><dd>{s.cost_s != null ? `월 ${s.cost_s.toFixed(1)}만` : '–'}</dd></div>
        {STAR_GROUPS.map((g) => <div key={g.key}><dt>{g.label}</dt><dd className="stars">{starText(s[`${g.key}_stars`])}</dd></div>)}
      </dl>
      {onMore && <button type="button" className="secondary rs-more" onClick={onMore}>자세히 보기</button>}
    </div>
  )
}
