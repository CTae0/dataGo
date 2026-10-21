import { useState } from 'react'
import Scene from './Scene.jsx'

// 항목 색: categorical 1~7, 순서 고정 (dataviz 기본 팔레트)
export const ITEM_COLOR = { housing: '#2a78d6', water: '#eb6834', gas: '#1baf7a', trash: '#eda100',
                            transit: '#e87ba4', dining: '#008300', grocery: '#6250d6' }
const ITEMS = Object.keys(ITEM_COLOR)
const won = (v) => `${Math.round(v).toLocaleString('ko-KR')}원`
const manwon = (v) => `${Math.round(v / 10_000).toLocaleString('ko-KR')}만 원`
const MEDALS = ['🥇 1위', '🥈 2위', '🥉 3위']

// 페르소나 한 줄: 몇몇 답의 앞부분 (예: '부르주아처럼 신경 안 쓰고 콸콸' → '부르주아처럼 신경 안 쓰고 콸콸')
function persona(spec, answers) {
  const pick = ['shower', 'boiler', 'dining']
  return pick.map((qid) => {
    const label = spec.questions.find((q) => q.id === qid)?.options.find((o) => o.id === answers[qid])?.label
    return label ? label.split(',')[0] : null
  }).filter(Boolean).join(' · ')
}

function Bar({ items, total }) {
  return (
    <div className="stack" role="img" aria-label={ITEMS.map((k) => `${items[k].label} ${won(items[k].value)}`).join(', ')}>
      {ITEMS.filter((k) => items[k].value > 0).map((k) => (
        <span key={k} title={`${items[k].label} ${won(items[k].value)}`}
              style={{ width: `${(items[k].value / total) * 100}%`, background: ITEM_COLOR[k] }} />
      ))}
    </div>
  )
}

function PodiumCard({ x, selected, onSelect }) {
  const c = x.card
  return (
    <button type="button" className={`pcard ${selected ? 'on' : ''}`} onClick={() => onSelect(x.region_code)}>
      <div className="pcard-art">
        <Scene type={c?.archetype} />
        <span className="pcard-rank">{MEDALS[x.rank - 1]}</span>
      </div>
      <div className="pcard-body">
        {c && <span className="pcard-nick">{c.nickname}</span>}
        <span className="pcard-name">{x.sido} {x.sigungu}</span>
        <span className="pcard-level">
          <strong>월 약 {manwon(x.total)}</strong>
          {c && <span className="level-badge">{c.level.name} · 저렴한 순 상위 {c.level.pct}%</span>}
        </span>
        <Bar items={x.items} total={x.total} />
        {c && <p className="pcard-text">{c.text}</p>}
        {c?.facts?.length > 0 && <span className="pcard-facts">{c.facts.map((f) => <span key={f}>{f}</span>)}</span>}
      </div>
    </button>
  )
}

export default function Results({ spec, data, onSelect, selected, onRestart }) {
  const [asTable, setAsTable] = useState(false)
  const answers = data.answers.answers || {}
  const top = data.results.slice(0, 3)
  const rest = data.results.slice(3)
  const asm = data.assumptions

  return (
    <div className="results">
      <div className="results-head">
        <p className="persona">{persona(spec, answers)} 님에게 어울리는 동네예요</p>
        <button type="button" className="link" onClick={onRestart}>다시 하기</button>
      </div>
      {asm.where?.length > 0 && <p className="muted small">조건: {asm.where.join(' · ')}</p>}
      {asm.relaxed?.length > 0 && (
        <p className="relaxed">조건을 모두 만족하는 곳이 3곳보다 적어서 「{asm.relaxed.join('」, 「')}」 조건은 빼고 골랐어요.</p>
      )}

      {data.count > 0 && (
        <>
          <div className="podium">
            {top.map((x) => <PodiumCard key={x.region_code} x={x} selected={selected === x.region_code} onSelect={onSelect} />)}
          </div>

          <div className="item-legend">
            <ul>{ITEMS.map((k) => <li key={k}><span className="swatch" style={{ background: ITEM_COLOR[k] }} />{data.results[0].items[k].label}</li>)}</ul>
            <button type="button" className="link" onClick={() => setAsTable(!asTable)}>{asTable ? '접기' : '전체를 표로 보기'}</button>
          </div>

          {asTable && (
            <div className="table-scroll tall">
              <table>
                <thead><tr><th>순위</th><th>지역</th><th>합계</th>{ITEMS.map((k) => <th key={k}>{data.results[0].items[k].label}</th>)}</tr></thead>
                <tbody>
                  {data.results.map((x) => (
                    <tr key={x.region_code} onClick={() => onSelect(x.region_code)} className={selected === x.region_code ? 'sel' : ''}>
                      <td>{x.rank}</td><td>{x.sido} {x.sigungu}</td><td>{won(x.total)}</td>
                      {ITEMS.map((k) => <td key={k}>{won(x.items[k].value)}{x.items[k].filled ? '*' : ''}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small">* 자료가 없거나 거래가 적어 같은 시도 중위값으로 채운 값</p>
            </div>
          )}
          {!asTable && rest.length > 0 && (
            <details className="rest">
              <summary>4위부터 {rest.length}곳 더 보기</summary>
              <ol start={4}>
                {rest.map((x) => (
                  <li key={x.region_code}><button type="button" className="link" onClick={() => onSelect(x.region_code)}>{x.sido} {x.sigungu}</button> 월 약 {manwon(x.total)}</li>
                ))}
              </ol>
            </details>
          )}

          <details className="assumptions">
            <summary>이렇게 계산했어요 (가정 보기)</summary>
            <ul>{asm.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </details>
        </>
      )}
    </div>
  )
}
