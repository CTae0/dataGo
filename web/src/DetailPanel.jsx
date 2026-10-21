import { useEffect, useState } from 'react'
import TrendChart from './TrendChart.jsx'
import { apiFetch } from './api.js'
import PowerChart from './PowerChart.jsx'
import { formatValue, GRAN_LABEL, isFallback } from './format.js'

const UTIL_LABEL = { water_20m3: '상수도 20㎥', sewer_20m3: '하수도 20㎥', trash_20l: '종량제봉투 20ℓ',
                     gas_total: '도시가스(월)', bus_card: '시내버스(카드)', taxi: '택시 기본요금' }
const UTIL_UNIT = { water_20m3: '원/월', sewer_20m3: '원/월', trash_20l: '원', gas_total: '원/월', bus_card: '원', taxi: '원' }
const DINING_ITEMS = [['naengmyeon', '냉면'], ['bibimbap', '비빔밥'], ['kimchi_jjigae', '김치찌개 백반'],
                      ['samgyeopsal_200g', '삼겹살 200g'], ['jajangmyeon', '자장면'], ['samgyetang', '삼계탕'],
                      ['kalguksu', '칼국수'], ['gimbap', '김밥']]

function Gran({ g }) {
  if (!g) return null
  return <span className={`badge ${isFallback(g) ? 'fallback' : ''}`}>{GRAN_LABEL[g] || g}</span>
}

export default function DetailPanel({ code, summary, metrics, sources, onClose, embedded = false }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    setDetail(null); setError(null)
    apiFetch(`/api/regions/${code}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setDetail).catch((e) => setError(String(e)))
  }, [code])

  // 공공요금은 항목마다 가장 정밀한 값 하나 (API가 정밀도 순으로 준다)
  const util = {}
  for (const u of detail?.utility || []) {
    const rank = { exact: 0, si: 1, legacy: 2, sido_part: 3, sido: 4 }
    if (!util[u.item] || rank[u.granularity] < rank[util[u.item].granularity]) util[u.item] = u
  }
  const usedSources = new Set([...(summary.sources || []), ...((detail?.dining?.sources) || []), 'vworld_sigungu'])

  return (
    <aside className={`panel ${embedded ? 'embedded' : ''}`} aria-label={`${summary.sido} ${summary.sigungu} 상세`}>
      <div className="panel-head">
        <div>
          <div className="muted">{summary.sido}</div>
          <h2>{summary.sigungu}</h2>
        </div>
        <button type="button" className="close" onClick={onClose} aria-label="닫기">×</button>
      </div>

      <section>
        <h3>한눈에</h3>
        <dl className="kv">
          {metrics.map((m) => (
            <div key={m.id}>
              <dt>{m.label}</dt>
              <dd>{formatValue(summary[m.field], m.unit)} <Gran g={m.gran ? summary[m.gran] : null} /></dd>
            </div>
          ))}
        </dl>
        {summary.rent_from_ym && (
          <p className="muted small">전월세: {summary.rent_from_ym.slice(0, 4)}.{summary.rent_from_ym.slice(4)} ~ {summary.rent_to_ym.slice(0, 4)}.{summary.rent_to_ym.slice(4)}, 거래 {Number(summary.rent_deals || 0).toLocaleString('ko-KR')}건</p>
        )}
      </section>

      {error && <p className="error">상세를 불러오지 못했습니다: {error}</p>}
      {!detail && !error && <p className="muted">불러오는 중…</p>}
      {detail && (
        <>
          <section>
            <h3>월 주거비 추이</h3>
            <TrendChart rows={detail.rent_trend} />
          </section>

          <section>
            <h3>가구 평균 전기요금 <Gran g={summary.power_gran} /></h3>
            <PowerChart rows={detail.power_trend} />
            <p className="muted small">주택용 전기를 쓰는 이 지역 가구의 월평균 청구액 (1인~다인 가구 평균, 복지할인 포함)</p>
          </section>

          {summary.mgmt_per_m2 && (
            <section>
              <h3>아파트 관리비 <Gran g={summary.mgmt_gran} /></h3>
              <dl className="kv">
                <div><dt>㎡당 월 관리비 (공용+장기수선)</dt><dd>{formatValue(summary.mgmt_per_m2, '원')}</dd></div>
                <div><dt>전용 59㎡(공급 약 77㎡) 기준</dt><dd>{formatValue(summary.mgmt_per_m2 * 77, '원/월')}</dd></div>
                <div><dt>전용 84㎡(공급 약 110㎡) 기준</dt><dd>{formatValue(summary.mgmt_per_m2 * 110, '원/월')}</dd></div>
              </dl>
              <p className="muted small">
                {summary.mgmt_complexes ? `관리비 공개 의무단지 ${summary.mgmt_complexes}곳의 중위값` : '이 지역 의무단지가 적어 시도 중위값'}
                {' '}· 전기·수도·가스 같은 개별사용료 제외
              </p>
            </section>
          )}

          <section>
            <h3>공공요금</h3>
            <table className="plain">
              <tbody>
                {Object.keys(UTIL_LABEL).filter((k) => util[k]).map((k) => (
                  <tr key={k}><th>{UTIL_LABEL[k]}</th><td>{formatValue(util[k].value, UTIL_UNIT[k])}</td><td><Gran g={util[k].granularity} /></td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">상하수도는 가정용 구간 단가로 계산했고 기본요금이 빠져 있어 실제보다 조금 낮습니다.</p>
          </section>

          <section>
            <h3>장바구니 물가 <span className="muted small">(전국 중위 = 100)</span></h3>
            <table className="plain">
              <tbody>
                {detail.grocery.map((g) => (
                  <tr key={g.category}><th>{g.category === 'all' ? '전체' : g.category}</th>
                    <td>{formatValue(g.price_index, '지수')}</td><td><Gran g={g.granularity} /></td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">
              {detail.grocery[0]?.stores_in_region ? `이 지역 조사 점포 ${detail.grocery[0].stores_in_region}곳` : '이 지역에는 조사 점포가 없어 같은 시도 점포로 계산'}
              {' '}· 대형마트·SSM·백화점 기준 (전통시장 미포함)
            </p>
          </section>

          {detail.dining && (
            <section>
              <h3>외식비 <span className="muted small">({detail.dining.dining_ym?.slice(0, 4)}.{detail.dining.dining_ym?.slice(4)})</span> <Gran g={detail.dining.dining_gran} /></h3>
              <table className="plain">
                <tbody>
                  {DINING_ITEMS.filter(([k]) => detail.dining[k]).map(([k, label]) => (
                    <tr key={k}><th>{label}</th><td>{formatValue(detail.dining[k], '원')}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}

      <section className="panel-sources">
        <h3>이 지역 자료 출처</h3>
        <ul>
          {sources.filter((s) => usedSources.has(s.source_id)).map((s) => (
            <li key={s.source_id}><a href={s.portal_url} target="_blank" rel="noreferrer">{s.attribution_text}</a></li>
          ))}
        </ul>
        <p className="muted small">값은 원자료를 가공(중위값·환산·지수화)한 것입니다.</p>
      </section>
    </aside>
  )
}
