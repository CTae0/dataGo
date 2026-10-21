import { useState } from 'react'
import { GRAN_LABEL, isFallback } from './format.js'

// 항목 색: categorical 1~7, 순서 고정 (dataviz 기본 팔레트)
export const ITEM_COLOR = { housing: '#2a78d6', water: '#eb6834', gas: '#1baf7a', trash: '#eda100',
                            transit: '#e87ba4', dining: '#008300', grocery: '#6250d6' }
const ITEMS = Object.keys(ITEM_COLOR)
const won = (v) => `${Math.round(v).toLocaleString('ko-KR')}원`
const TITLES = ['통장 지킴이 1위', '가성비 은메달', '알뜰 동메달']

function optionLabel(spec, qid, oid) {
  return spec.questions.find((q) => q.id === qid)?.options?.find((o) => o.id === oid)?.label
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

export default function Results({ spec, data, onSelect, selected, onRestart }) {
  const [asTable, setAsTable] = useState(false)
  const a = data.answers
  const top = data.results.slice(0, 10)
  const rest = data.results.slice(10)
  const persona = ['household', 'shower', 'boiler', 'dining'].map((q) => optionLabel(spec, q, a[q])).filter(Boolean).join(' · ')

  return (
    <div className="results">
      <div className="results-head">
        <p className="persona">{persona} 님의 한 달 생활비를 계산했어요</p>
        <button type="button" className="link" onClick={onRestart}>답 바꾸기</button>
      </div>
      {data.count === 0 && <p className="muted">조건에 맞는 시군구가 없어요. 주거비 상한이나 지역을 넓혀 보세요.</p>}

      {data.count > 0 && (
        <>
          <div className="item-legend">
            <ul>{ITEMS.map((k) => <li key={k}><span className="swatch" style={{ background: ITEM_COLOR[k] }} />{data.results[0].items[k].label}</li>)}</ul>
            <button type="button" className="link" onClick={() => setAsTable(!asTable)}>{asTable ? '카드로 보기' : '표로 보기'}</button>
          </div>

          {asTable ? (
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
          ) : (
            <ol className="cards">
              {top.map((x) => (
                <li key={x.region_code}>
                  <button type="button" className={`card ${selected === x.region_code ? 'on' : ''}`} onClick={() => onSelect(x.region_code)}>
                    <span className="card-rank">{TITLES[x.rank - 1] || `${x.rank}위`}</span>
                    <span className="card-name">{x.sido} {x.sigungu}</span>
                    <span className="card-total">월 {won(x.total)}</span>
                    <Bar items={x.items} total={x.total} />
                    <span className="card-items">
                      {ITEMS.map((k) => (
                        <span key={k} className={isFallback(x.items[k].gran) || x.items[k].filled ? 'approx' : ''}>
                          {x.items[k].label} {won(x.items[k].value)}{x.items[k].filled ? '*' : ''}
                        </span>
                      ))}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
          {!asTable && rest.length > 0 && (
            <details className="rest">
              <summary>나머지 {rest.length}곳 보기</summary>
              <ol start={11}>
                {rest.map((x) => (
                  <li key={x.region_code}><button type="button" className="link" onClick={() => onSelect(x.region_code)}>{x.sido} {x.sigungu}</button> 월 {won(x.total)}</li>
                ))}
              </ol>
            </details>
          )}

          <details className="assumptions">
            <summary>이렇게 계산했어요 (가정 보기)</summary>
            <ul>
              {data.assumptions.notes.map((n) => <li key={n}>{n}</li>)}
              <li>흐린 글씨는 {GRAN_LABEL.sido} 등으로 대체한 값, *는 같은 시도 중위값으로 채운 값입니다.</li>
            </ul>
          </details>
        </>
      )}
    </div>
  )
}
