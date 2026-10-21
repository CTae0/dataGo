import { useMemo, useState } from 'react'

// 질문지: 한 화면에 한 문항, 유머 섞인 A/B 두 답 (문구는 /api/questions = api/cost_model.py QUESTIONS)
// show_if: 앞 답에 따라 보이는 질문 (예: '같이 산다'일 때만 식구 수를 묻는다)
const visible = (q, ans) => Object.entries(q.show_if || {}).every(([k, v]) => ans[k] === v)

export default function Questionnaire({ spec, initial, onDone, onCancel }) {
  const [ans, setAns] = useState(() => {
    const base = { ...spec.defaults }
    for (const [k, v] of Object.entries(initial || {})) if (v === 'a' || v === 'b') base[k] = v
    return base
  })
  const [step, setStep] = useState(0)
  const qs = useMemo(() => spec.questions.filter((q) => visible(q, ans)), [spec, ans])
  const q = qs[Math.min(step, qs.length - 1)]
  const last = step >= qs.length - 1

  const pick = (id) => {
    const next = { ...ans, [q.id]: id }
    setAns(next)
    const nextQs = spec.questions.filter((x) => visible(x, next))
    if (step >= nextQs.length - 1) onDone(Object.fromEntries(nextQs.map((x) => [x.id, next[x.id]])))
    else setStep(step + 1)
  }

  return (
    <div className="quiz">
      <div className="quiz-top">
        <button type="button" className="link" onClick={onCancel}>지도로 돌아가기</button>
        <span className="muted">{step + 1} / {qs.length}</span>
      </div>
      <div className="progress" aria-hidden="true"><div style={{ width: `${((step + 1) / qs.length) * 100}%` }} /></div>
      <div className="quiz-group">{q.group === '어디서' ? '어디서 살고 싶나요' : '나의 생활'}</div>
      <h2 className="quiz-title">{q.title}</h2>

      <div className="options ab" role="radiogroup" aria-label={q.title}>
        {q.options.map((o) => (
          <button key={o.id} type="button" role="radio" aria-checked={ans[q.id] === o.id}
                  className={`option ${ans[q.id] === o.id ? 'on' : ''}`} onClick={() => pick(o.id)}>
            <span className="option-tag">{o.id.toUpperCase()}</span>
            <span className="option-label">{o.label}</span>
            <span className="option-hint">{o.hint}</span>
          </button>
        ))}
      </div>

      <div className="quiz-nav">
        <button type="button" className="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>이전</button>
        {last && <button type="button" className="primary"
                         onClick={() => onDone(Object.fromEntries(qs.map((x) => [x.id, ans[x.id]])))}>이대로 계산하기</button>}
      </div>
    </div>
  )
}
