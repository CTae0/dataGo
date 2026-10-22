import { useState } from 'react'

// 출처 표시 (ATTRIBUTION.md 규칙): 지금 화면에 쓰인 출처는 항상 보이게 한다.
//  - 기본(PC 하단): 앞 2곳 + '외 N곳' + 펼치기
//  - compact(휴대폰 본문 끝): 한 줄 "출처: 첫 곳 외 N곳 (가공) ›" → 누르면 onOpen(바텀시트)
//  - expanded(바텀시트 안): 지금 화면 출처 전부 + 나머지 출처 목록
const INLINE_MAX = 2

function List({ items, withLicense }) {
  return (
    <ul className="attr-all">
      {items.map((s) => (
        <li key={s.source_id}>
          <a href={s.portal_url} target="_blank" rel="noreferrer">{s.attribution_text}</a>
          {withLicense && s.license && <span className="muted"> · {s.license}</span>}
        </li>
      ))}
    </ul>
  )
}

export default function Attribution({ sources, active, compact = false, expanded = false, onOpen }) {
  const [open, setOpen] = useState(false)
  const now = sources.filter((s) => active.includes(s.source_id))
  const rest = sources.filter((s) => !active.includes(s.source_id))

  if (expanded) {
    return (
      <div className="attr-sheet">
        <h3>이 화면에 쓴 자료</h3>
        <List items={now} withLicense />
        <p className="muted small">값은 원자료를 가공(중위값·환산·지수화)한 추정치입니다.</p>
        {rest.length > 0 && (<><h3>그 밖의 자료</h3><List items={rest} withLicense /></>)}
      </div>
    )
  }
  if (compact) {
    return (
      <footer className="attribution compact">
        <button type="button" className="attr-line" onClick={onOpen}>
          <span>출처: {now[0]?.attribution_text.replace(/^출처:\s*/, '') || '공공데이터'}</span>
          {now.length > 1 && <span className="attr-more"> 외 {now.length - 1}곳</span>}
          <span className="muted"> (가공) ›</span>
        </button>
      </footer>
    )
  }
  const shown = open ? now : now.slice(0, INLINE_MAX)
  const hidden = now.length - shown.length
  return (
    <footer className="attribution">
      <div className="attr-now">
        {shown.map((s) => (
          <a key={s.source_id} href={s.portal_url} target="_blank" rel="noreferrer">{s.attribution_text}</a>
        ))}
        {hidden > 0 && <span className="attr-more">외 {hidden}곳</span>}
        <span className="muted">(가공)</span>
        <button type="button" className="link" onClick={() => setOpen(!open)}>{open ? '출처 접기' : '출처 모두 보기'}</button>
      </div>
      {open && <List items={rest} withLicense />}
    </footer>
  )
}
