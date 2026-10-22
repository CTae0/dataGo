import { useEffect, useState } from 'react'
import TrendChart from './TrendChart.jsx'
import { apiFetch } from './api.js'
import PowerChart from './PowerChart.jsx'
import { formatValue, GRAN_LABEL, isFallback } from './format.js'
import { starText } from './Results.jsx'

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

      <details className="dsec" open>
        <summary><h3>한눈에</h3></summary>
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
      </details>

      {error && <p className="error">상세를 불러오지 못했습니다: {error}</p>}
      {!detail && !error && <p className="muted">불러오는 중…</p>}
      {detail && (
        <>
          <details className="dsec" open>
            <summary><h3>월 주거비 추이</h3></summary>
            <TrendChart rows={detail.rent_trend} />
          </details>

          <details className="dsec">
            <summary><h3>가구 평균 전기요금 <Gran g={summary.power_gran} /></h3></summary>
            <PowerChart rows={detail.power_trend} />
            <p className="muted small">주택용 전기를 쓰는 이 지역 가구의 월평균 청구액 (1인~다인 가구 평균, 복지할인 포함)</p>
          </details>

          {summary.mgmt_per_m2 && (
            <details className="dsec">
              <summary><h3>아파트 관리비 <Gran g={summary.mgmt_gran} /></h3></summary>
              <dl className="kv">
                <div><dt>㎡당 월 관리비 (공용+장기수선)</dt><dd>{formatValue(summary.mgmt_per_m2, '원')}</dd></div>
                <div><dt>전용 59㎡(공급 약 77㎡) 기준</dt><dd>{formatValue(summary.mgmt_per_m2 * 77, '원/월')}</dd></div>
                <div><dt>전용 84㎡(공급 약 110㎡) 기준</dt><dd>{formatValue(summary.mgmt_per_m2 * 110, '원/월')}</dd></div>
              </dl>
              <p className="muted small">
                {summary.mgmt_complexes ? `관리비 공개 의무단지 ${summary.mgmt_complexes}곳의 중위값` : '이 지역 의무단지가 적어 시도 중위값'}
                {' '}· 전기·수도·가스 같은 개별사용료 제외
              </p>
            </details>
          )}

          {summary.edu_score != null && (
            <details className="dsec">
              <summary><h3>교육·문화 시설 <span className="muted small">(인구 {Number(summary.population || 0).toLocaleString('ko-KR')}명)</span></h3></summary>
              <table className="plain">
                <tbody>
                  <tr><th>교육·육아 점수</th><td>{Math.round(summary.edu_score)}점 {'★'.repeat(summary.edu_stars || 0)}{'☆'.repeat(4 - (summary.edu_stars || 0))}</td></tr>
                  <tr><th>초등학교 · 중고등학교</th><td>{Math.round(summary.elem)}곳 · {Math.round(summary.secondary)}곳</td></tr>
                  <tr><th>유치원 · 학원·교습소</th><td>{Math.round(summary.kinder)}곳 · {Math.round(summary.academy).toLocaleString('ko-KR')}곳</td></tr>
                  <tr><th>문화·여가 점수</th><td>{Math.round(summary.culture_score)}점 {'★'.repeat(summary.culture_stars || 0)}{'☆'.repeat(4 - (summary.culture_stars || 0))}</td></tr>
                  <tr><th>도서관 · 박물관·미술관</th><td>{Math.round(summary.library)}곳 · {Math.round(summary.museum)}곳</td></tr>
                  <tr><th>문예회관·생활문화센터</th><td>{Math.round(summary.arts)}곳</td></tr>
                  <tr><th>도시공원 (1인당 면적)</th><td>{Math.round(summary.parks)}곳 ({Math.round(summary.park_m2_per_person || 0)}㎡)</td></tr>
                </tbody>
              </table>
              <p className="muted small">점수는 인구 대비 비율과 면적(㎢) 대비 밀도를 전국과 비교한 백분위를 반반 섞은 값 (0~100). 나이스·유치원알리미·문화기반시설총람(2023 기준)·도시공원 표준데이터</p>
            </details>
          )}

          {summary.medical_score != null && (
            <details className="dsec">
              <summary><h3>안전·의료·환경</h3></summary>
              <table className="plain">
                <tbody>
                  <tr><th>의료 점수</th><td>{Math.round(summary.medical_score)}점 {starText(summary.medical_stars)}</td></tr>
                  <tr><th>병원·의원 · 약국</th><td>{Math.round(summary.hospitals).toLocaleString('ko-KR')}곳 · {Math.round(summary.pharmacies).toLocaleString('ko-KR')}곳</td></tr>
                  <tr><th>소아과 (이름 기준)</th><td>{Math.round(summary.pediatrics)}곳</td></tr>
                  <tr><th>가장 가까운 응급실</th><td>{summary.emergency_km != null ? `약 ${summary.emergency_km}km` : '자료 없음'}{summary.emergency_name ? ` · ${summary.emergency_name}` : ''}</td></tr>
                  {summary.safety_score != null && (
                    <tr><th>안전 (치안)</th><td>{Math.round(summary.safety_score)}점 {starText(summary.safety_stars)} · 주민 1천 명당 범죄 {summary.crimes_per_1k}건 <Gran g={summary.crime_gran} /></td></tr>
                  )}
                  <tr><th>환경</th><td>{summary.env_score != null ? `${Math.round(summary.env_score)}점 ${starText(summary.env_stars)}` : '자료 없음'}</td></tr>
                  <tr><th>초미세먼지 (PM2.5)</th><td>{summary.pm25 != null ? `${summary.pm25}㎍/㎥` : '자료 없음'}{summary.pm25_from ? ` · ${summary.pm25_from}~${summary.pm25_to} 평균` : ''}</td></tr>
                </tbody>
              </table>
              <p className="muted small">
                의료는 병원·의원·약국(인구 대비·면적 대비)과 응급실 직선거리, 안전은 {summary.crime_year || ''}년 강력·절도·폭력범죄 발생 건수(발생 장소 기준이라 도심·관광지가 불리),
                환경은 초미세먼지와 공원 점수의 평균이에요. 국립중앙의료원·경찰청·에어코리아(확정 전 자료)
              </p>
            </details>
          )}

          <details className="dsec">
            <summary><h3>공공요금</h3></summary>
            <table className="plain">
              <tbody>
                {Object.keys(UTIL_LABEL).filter((k) => util[k]).map((k) => (
                  <tr key={k}><th>{UTIL_LABEL[k]}</th><td>{formatValue(util[k].value, UTIL_UNIT[k])}</td><td><Gran g={util[k].granularity} /></td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">상하수도는 가정용 구간 단가로 계산했고 기본요금이 빠져 있어 실제보다 조금 낮습니다.</p>
          </details>

          <details className="dsec">
            <summary><h3>장바구니 물가 <span className="muted small">(전국 중위 = 100)</span></h3></summary>
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
          </details>

          {detail.dining && (
            <details className="dsec">
              <summary><h3>외식비 <span className="muted small">({detail.dining.dining_ym?.slice(0, 4)}.{detail.dining.dining_ym?.slice(4)})</span> <Gran g={detail.dining.dining_gran} /></h3></summary>
              <table className="plain">
                <tbody>
                  {DINING_ITEMS.filter(([k]) => detail.dining[k]).map(([k, label]) => (
                    <tr key={k}><th>{label}</th><td>{formatValue(detail.dining[k], '원')}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </>
      )}

      <details className="dsec panel-sources">
        <summary><h3>이 지역 자료 출처</h3></summary>
        <ul>
          {sources.filter((s) => usedSources.has(s.source_id)).map((s) => (
            <li key={s.source_id}><a href={s.portal_url} target="_blank" rel="noreferrer">{s.attribution_text}</a></li>
          ))}
        </ul>
        <p className="muted small">값은 원자료를 가공(중위값·환산·지수화)한 것입니다.</p>
      </details>
    </aside>
  )
}
