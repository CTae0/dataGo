import { useEffect, useState } from 'react'
import Scene from './Scene.jsx'
import { GROUP_COLOR, manwon } from './format.js'
import { apiFetch } from './api.js'

// 첫 화면: 퀴즈 먼저. 기본 답(1인·월세·빌라)으로 뽑은 예시 카드 3장을 미리 보여 준다.
const visible = (q, ans) => Object.entries(q.show_if || {}).every(([k, v]) => ans[k] === v)

export default function Home({ spec, onStart, onMap }) {
  const [sample, setSample] = useState(null)
  useEffect(() => {
    if (!spec) return
    apiFetch('/api/recommend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(spec.defaults) })
      .then((r) => (r.ok ? r.json() : null)).then(setSample).catch(() => setSample(null))
  }, [spec])
  const nq = spec ? spec.questions.filter((q) => visible(q, spec.defaults)).length : null

  return (
    <main className="body home-body">
      <div className="home">
        <section className="hero">
          <p className="hero-kicker">전국 256개 시군구 · 공공데이터로 계산</p>
          <h2 className="hero-title">질문 몇 개면,<br />내 생활비로 살기 좋은 동네 3곳</h2>
          <p className="hero-sub">
            샤워는 몇 분? 에어컨은 풀가동? 출근은 버스 아니면 내 차? 재미있는 A/B 질문에 답하면
            주거비·관리비·전기·가스·장보기·외식·기름값까지 합친 월 생활비로 동네를 골라 드려요.
          </p>
          <div className="hero-actions">
            <button type="button" className="primary big" onClick={onStart} disabled={!spec}>시작하기 →</button>
            <button type="button" className="link big" onClick={onMap}>전국 지도로 둘러보기 ›</button>
          </div>
          {nq && <p className="muted small">질문 {nq}개 · 1분이면 끝나요 · 답은 저장하지 않아요</p>}
        </section>

        <section className="home-groups" aria-label="계산하는 항목">
          {spec?.groups.map((g) => (
            <div key={g.id} className="hg">
              <span className="swatch" style={{ background: GROUP_COLOR[g.id] }} />
              <strong>{g.label}</strong>
              <span className="muted small">{spec.items.filter((it) => it.group === g.id).map((it) => it.label).join(' · ')}</span>
            </div>
          ))}
        </section>

        {sample?.results?.length > 0 && (
          <section className="home-sample">
            <h3>예를 들면, 혼자 사는 빌라 월세파에게는</h3>
            <div className="podium">
              {sample.results.slice(0, 3).map((x) => (
                <div key={x.region_code} className="pcard mini">
                  <div className="pcard-art"><Scene type={x.card?.archetype} /></div>
                  <div className="pcard-body">
                    <span className="pcard-nick">{x.card?.nickname}</span>
                    <span className="pcard-name">{x.sido} {x.sigungu}</span>
                    <strong>월 약 {manwon(x.total)}</strong>
                  </div>
                </div>
              ))}
            </div>
            <p className="muted small">내 답에 따라 순위가 완전히 달라져요.</p>
          </section>
        )}
      </div>
    </main>
  )
}
