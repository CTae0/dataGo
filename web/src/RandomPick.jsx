import Scene from './Scene.jsx'
import { STAR_GROUPS, levelText, manwon } from './format.js'
import { starText } from './Results.jsx'

// '아무 데나 살아보기': 무작위로 뽑은 시군구 1곳의 카드 (기본 답 기준 생활비 + 주거·교육·문화 요약)
// 자세한 표·추이는 아래에 붙는 DetailPanel(embedded)이 보여 준다.
const r0 = (v) => (v == null ? '–' : Math.round(v).toLocaleString('ko-KR'))

export default function RandomPick({ data, onAgain, onQuiz }) {
  const x = data.result
  const s = data.summary
  const c = x.card
  return (
    <div className="random">
      <div className="random-head">
        <strong>🎲 아무 데나 살아보기</strong>
        <span className="muted small">전국 {data.count}곳 중 무작위로 뽑았어요</span>
      </div>
      <div className="pcard random-card">
        <div className="pcard-art"><Scene type={c?.archetype} /></div>
        <div className="pcard-body">
          {c && <span className="pcard-nick">{c.nickname}</span>}
          <span className="pcard-name">{x.sido} {x.sigungu}</span>
          <span className="pcard-level">
            <strong>월 약 {manwon(x.total)}</strong>
            {c && <span className="level-badge">{levelText(c.level)}</span>}
          </span>
          <span className="muted small">{data.profile}</span>
          {c?.stars && (
            <span className="pcard-stars">
              {STAR_GROUPS.filter((g) => c.stars[g.key]).map((g) => <span key={g.key}>{g.label} <b>{starText(c.stars[g.key])}</b></span>)}
            </span>
          )}
          {c && <p className="pcard-text">{c.text}</p>}
          {c?.facts?.length > 0 && <span className="pcard-facts">{c.facts.map((f) => <span key={f}>{f}</span>)}</span>}
        </div>
      </div>

      <dl className="random-grid">
        <div><dt>🏠 주거비 (월세 환산)</dt>
          <dd>1인 {s.cost_s != null ? `${s.cost_s.toFixed(1)}만` : '–'} · 2인 {s.cost_m != null ? `${s.cost_m.toFixed(1)}만` : '–'} · 가족 {s.cost_l != null ? `${s.cost_l.toFixed(1)}만` : '–'}</dd></div>
        <div><dt>🎒 교육·육아 {s.edu_score != null ? `${Math.round(s.edu_score)}점` : ''}</dt>
          <dd>초 {r0(s.elem)} · 중고 {r0(s.secondary)} · 유치원 {r0(s.kinder)} · 학원 {r0(s.academy)}곳</dd></div>
        <div><dt>🎨 문화·여가 {s.culture_score != null ? `${Math.round(s.culture_score)}점` : ''}</dt>
          <dd>도서관 {r0(s.library)} · 박물관·미술관 {r0(s.museum)} · 문화센터 {r0(s.arts)} · 공원 {r0(s.parks)}곳</dd></div>
        <div><dt>🏥 의료 {s.medical_score != null ? `${Math.round(s.medical_score)}점` : ''}</dt>
          <dd>병·의원 {r0(s.hospitals)} · 약국 {r0(s.pharmacies)}곳 · 응급실 {s.emergency_km != null ? `약 ${s.emergency_km}km` : '–'}</dd></div>
        <div><dt>🛡 안전·🌿 환경</dt>
          <dd>범죄 주민 1천 명당 {s.crimes_per_1k != null ? `${s.crimes_per_1k}건` : '–'} · 초미세먼지 {s.pm25 != null ? `${s.pm25}㎍/㎥` : '–'}</dd></div>
        <div><dt>⚡ 에너지·관리비</dt>
          <dd>가구 전기 월 {r0(s.power_bill)}원 · 아파트 관리비 ㎡당 {r0(s.mgmt_per_m2)}원</dd></div>
      </dl>

      <div className="random-actions">
        <button type="button" className="primary" onClick={onAgain}>🎲 다시 뽑기</button>
        <button type="button" className="secondary" onClick={onQuiz}>나한테 맞는 동네 찾기</button>
      </div>
    </div>
  )
}
