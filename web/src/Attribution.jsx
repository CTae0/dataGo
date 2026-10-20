import { useState } from 'react'

// 출처 표시 (ATTRIBUTION.md 규칙): 지금 화면에 쓰인 출처는 항상 보이고, 전체 목록은 펼쳐서 본다.
export default function Attribution({ sources, active }) {
  const [open, setOpen] = useState(false)
  const now = sources.filter((s) => active.includes(s.source_id))
  return (
    <footer className="attribution">
      <div className="attr-now">
        {now.map((s) => (
          <a key={s.source_id} href={s.portal_url} target="_blank" rel="noreferrer">{s.attribution_text}</a>
        ))}
        <span className="muted">(가공)</span>
        <button type="button" className="link" onClick={() => setOpen(!open)}>{open ? '출처 닫기' : '전체 데이터 출처'}</button>
      </div>
      {open && (
        <ul className="attr-all">
          {sources.map((s) => (
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
