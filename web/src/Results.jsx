import { useState } from 'react'
import Scene from './Scene.jsx'
import ShareBox from './ShareBox.jsx'
import { GROUP_COLOR, ITEM_COLOR, NA_COLOR, manwon, won } from './format.js'

const MEDALS = ['🥇 1위', '🥈 2위', '🥉 3위']

// 페르소나 한 줄: 몇몇 답의 앞부분
function persona(spec, answers) {
  const pick = ['house', 'transit', 'shower', 'aircon', 'dining']
  return pick.map((qid) => {
    const label = spec.questions.find((q) => q.id === qid)?.options.find((o) => o.id === answers[qid])?.label
    return label ? label.split(',')[0] : null
  }).filter(Boolean).join(' · ')
}

// 묶음별 합계 [{id, label, value}] (API의 items[k].group, spec.groups 순서)
function groupTotals(spec, items) {
  return spec.groups.map((g) => ({
    ...g, value: Object.values(items).filter((i) => i.group === g.id).reduce((a, i) => a + i.value, 0),
  }))
}

// 생활비 막대: 묶음 4색 한 줄. 'detail'이면 항목별 명도 단계
function Bar({ spec, items, total, detail = false }) {
  const parts = detail
    ? spec.items.filter((it) => items[it.id]?.value > 0).map((it) => ({ key: it.id, label: items[it.id].label,
        value: items[it.id].value, color: ITEM_COLOR[it.id] }))
    : groupTotals(spec, items).filter((g) => g.value > 0).map((g) => ({ key: g.id, label: g.label, value: g.value,
        color: GROUP_COLOR[g.id] }))
  return (
    <div className="stack" role="img" aria-label={parts.map((p) => `${p.label} ${won(p.value)}`).join(', ')}>
      {parts.map((p) => (
        <span key={p.key} title={`${p.label} ${won(p.value)}`}
              style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />
      ))}
    </div>
  )
}

// 펼친 항목 표: 묶음 → 항목 금액. 관리비 '해당 없음'은 회색, 시도 값으로 채운 항목은 *
function Breakdown({ spec, items }) {
  return (
    <div className="breakdown">
      {groupTotals(spec, items).map((g) => (
        <div key={g.id} className="bd-group">
          <div className="bd-head"><span className="swatch" style={{ background: GROUP_COLOR[g.id] }} />
            <span>{g.label}</span><strong>{won(g.value)}</strong></div>
          {spec.items.filter((it) => it.group === g.id).length > 1 && <ul>
            {spec.items.filter((it) => it.group === g.id).map((it) => {
              const v = items[it.id]
              return (
                <li key={it.id} className={v.na ? 'na' : ''}>
                  <span className="swatch sm" style={{ background: v.na ? NA_COLOR : ITEM_COLOR[it.id] }} />
                  <span>{v.label}</span>
                  <span>{v.na ? '해당 없음' : `${won(v.value)}${v.filled ? '*' : ''}`}</span>
                </li>
              )
            })}
          </ul>}
        </div>
      ))}
    </div>
  )
}

function PodiumCard({ spec, x, selected, onSelect }) {
  const [open, setOpen] = useState(false)
  const c = x.card
  const energy = c?.groups?.energy
  const withMgmt = x.items.mgmt && !x.items.mgmt.na
  return (
    <div className={`pcard ${selected ? 'on' : ''}`} data-code={x.region_code}>
      <button type="button" className="pcard-main" onClick={() => onSelect(x.region_code)}>
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
          <Bar spec={spec} items={x.items} total={x.total} />
          {energy > 0 && (
            <span className="pcard-energy">
              <span className="swatch sm" style={{ background: GROUP_COLOR.energy }} />
              에너지{withMgmt ? '·관리비' : ''} 월 약 {manwon(energy)}
            </span>
          )}
          {c && <p className="pcard-text">{c.text}</p>}
          {c?.facts?.length > 0 && <span className="pcard-facts">{c.facts.map((f) => <span key={f}>{f}</span>)}</span>}
        </div>
      </button>
      <button type="button" className="link pcard-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? '항목 접기' : '항목별로 보기'}
      </button>
      {open && (
        <div className="pcard-detail">
          <Bar spec={spec} items={x.items} total={x.total} detail />
          <Breakdown spec={spec} items={x.items} />
        </div>
      )}
    </div>
  )
}

export default function Results({ spec, data, onSelect, selected, onRestart }) {
  const [asTable, setAsTable] = useState(false)
  const answers = data.answers.answers || {}
  const top = data.results.slice(0, 1)   // 1위 카드 하나만 크게, 2위부터는 목록
  const rest = data.results.slice(1)
  const asm = data.assumptions
  const cols = spec.items.filter((it) => !data.results[0]?.items[it.id]?.na)   // 해당 없는 항목(관리비·기름값)은 표에서 뺀다

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
          <div className="podium single">
            {top.map((x) => <PodiumCard key={x.region_code} spec={spec} x={x} selected={selected === x.region_code} onSelect={onSelect} />)}
          </div>

          <ShareBox spec={spec} data={data} persona={persona(spec, answers)} />

          <div className="item-legend">
            <ul>{spec.groups.map((g) => {
              const names = spec.items.filter((it) => it.group === g.id).map((it) => it.label)
              return (
                <li key={g.id}><span className="swatch" style={{ background: GROUP_COLOR[g.id] }} />{g.label}
                  {names.length > 1 && <span className="muted">({names.join('·')})</span>}</li>
              )
            })}</ul>
            <button type="button" className="link" onClick={() => setAsTable(!asTable)}>{asTable ? '접기' : '전체를 표로 보기'}</button>
          </div>

          {asTable && (
            <div className="table-scroll tall">
              <table>
                <thead><tr><th>순위</th><th>지역</th><th>합계</th>{cols.map((it) => <th key={it.id}>{it.label}</th>)}</tr></thead>
                <tbody>
                  {data.results.map((x) => (
                    <tr key={x.region_code} onClick={() => onSelect(x.region_code)} className={selected === x.region_code ? 'sel' : ''}>
                      <td>{x.rank}</td><td>{x.sido} {x.sigungu}</td><td>{won(x.total)}</td>
                      {cols.map((it) => <td key={it.id}>{won(x.items[it.id].value)}{x.items[it.id].filled ? '*' : ''}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small">* 자료가 없거나 거래가 적어 같은 시도 중위값으로 채운 값</p>
            </div>
          )}
          {!asTable && rest.length > 0 && (
            <details className="rest" open>
              <summary>2위부터 {rest.length}곳 더 보기</summary>
              <ol start={2}>
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
