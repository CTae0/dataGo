import { useState } from 'react'

// 출처 표시 (ATTRIBUTION.md 규칙): 지금 화면에 쓰인 출처는 항상 보이게 한다.
// 출처가 많으면(추천 결과 등) 한 줄로 줄이고 펼쳐서 전부 본다 — 접혀 있어도 '외 N곳'과 링크는 늘 보인다.
const INLINE_MAX = 2

export default function Attribution({ sources, active }) {
  const [open, setOpen] = useState(false)
  const now = sources.filter((s) => active.includes(s.source_id))
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
      {open && (
        <ul className="attr-all">
          {sources.filter((s) => !active.includes(s.source_id)).map((s) => (
            <li key={s.source_id}>
              <a href={s.portal_url} target="_blank" rel="noreferrer">{s.attribution_text}</a>
              {s.license && <span className="muted"> · {s.license}</span>}
            </li>
          ))}
        </ul>
      )}
    </footer>
  )
}
