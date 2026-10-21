import { useState } from 'react'

// 질문지: 한 화면에 한 문항. 문구·선택지는 /api/questions에서 온다 (api/cost_model.py의 QUESTIONS)
export default function Questionnaire({ spec, initial, onDone, onCancel }) {
  const qs = spec.questions
  const [step, setStep] = useState(0)
  const [ans, setAns] = useState({ ...spec.defaults, ...(initial || {}) })
  const q = qs[step]
  const last = step === qs.length - 1

  // 상태는 항상 이전 값에서 갱신 (빠르게 여러 번 눌러도 앞의 선택이 사라지지 않게)
  const pick = (id) => {
    setAns((prev) => ({ ...prev, [q.id]: id }))
    if (!last) setStep(step + 1)
  }
  const toggleSido = (s) => setAns((prev) => {
    const cur = new Set(prev.sidos || [])
    cur.has(s) ? cur.delete(s) : cur.add(s)
    return { ...prev, sidos: [...cur] }
  })

  return (
    <div className="quiz">
      <div className="quiz-top">
        <button type="button" className="link" onClick={onCancel}>지도로 돌아가기</button>
        <span className="muted">{step + 1} / {qs.length}</span>
      </div>
      <div className="progress" aria-hidden="true"><div style={{ width: `${((step + 1) / qs.length) * 100}%` }} /></div>
      <h2 className="quiz-title">{q.title}</h2>

      {q.kind === 'single' && (
        <div className="options" role="radiogroup" aria-label={q.title}>
          {q.options.map((o) => (
            <button key={o.id} type="button" role="radio" aria-checked={ans[q.id] === o.id}
                    className={`option ${ans[q.id] === o.id ? 'on' : ''}`} onClick={() => pick(o.id)}>
              <span className="option-label">{o.label}</span>
              <span className="option-hint">{o.hint}</span>
            </button>
          ))}
        </div>
      )}

      {q.kind === 'filters' && (
        <div className="filters">
          <fieldset>
            <legend>{q.fields[0].label} <span className="muted small">{q.fields[0].hint}</span></legend>
            <div className="chips">
              {spec.sidos.map((s) => (
                <button key={s} type="button" aria-pressed={(ans.sidos || []).includes(s)}
                        className={`chip ${(ans.sidos || []).includes(s) ? 'on' : ''}`} onClick={() => toggleSido(s)}>{s}</button>
              ))}
            </div>
          </fieldset>
          <label className="field">
            <span>{q.fields[1].label} <span className="muted small">{q.fields[1].hint}</span></span>
            <input type="number" min="0" step="5" inputMode="numeric" value={ans.housing_cap ?? ''}
                   onChange={(e) => { const v = e.target.value; setAns((prev) => ({ ...prev, housing_cap: v === '' ? null : Number(v) })) }} />
          </label>
          <label className="check">
            <input type="checkbox" checked={!!ans.need_mart} onChange={(e) => { const v = e.target.checked; setAns((prev) => ({ ...prev, need_mart: v })) }} />
            <span>{q.fields[2].label} <span className="muted small">{q.fields[2].hint}</span></span>
          </label>
        </div>
      )}

      <div className="quiz-nav">
        <button type="button" className="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>이전</button>
        {last
          ? <button type="button" className="primary" onClick={() => onDone(ans)}>내 동네 계산하기</button>
          : <button type="button" className="secondary" onClick={() => setStep(step + 1)}>다음</button>}
      </div>
    </div>
  )
}
