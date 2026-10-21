import { useEffect, useMemo, useState } from 'react'
import MapView from './MapView.jsx'
import Legend from './Legend.jsx'
import DetailPanel from './DetailPanel.jsx'
import Attribution from './Attribution.jsx'
import Questionnaire from './Questionnaire.jsx'
import Results from './Results.jsx'
import Home from './Home.jsx'
import Logo from './Logo.jsx'
import RandomPick from './RandomPick.jsx'
import { quantileBreaks } from './format.js'
import { apiJSON } from './api.js'

async function getJSON(url, opts) {
  const r = await fetch(url, opts)
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`)
  return r.json()
}

// 답변은 URL(?a=…)에 넣어 새로고침·공유해도 결과가 남게 한다 (개인정보 없음)
function readAnswers() {
  try {
    const a = new URLSearchParams(location.search).get('a')
    return a ? JSON.parse(a) : null
  } catch { return null }
}
function writeAnswers(a) {
  const url = new URL(location.href)
  if (a) url.searchParams.set('a', JSON.stringify(a))
  else url.searchParams.delete('a')
  history.replaceState(null, '', url)
}
// 첫 화면은 '/', 지도는 '?view=map'
// 랜덤 뽑기는 '?view=random&code=시군구코드' (공유하면 같은 지역이 열린다)
const startMode = () => ({ map: 'explore', random: 'random' }[new URLSearchParams(location.search).get('view')] || 'home')
function writeView(mode, code) {
  const url = new URL(location.href)
  if (mode === 'explore') url.searchParams.set('view', 'map')
  else if (mode === 'random') url.searchParams.set('view', 'random')
  else url.searchParams.delete('view')
  if (mode === 'random' && code) url.searchParams.set('code', code)
  else url.searchParams.delete('code')
  history.replaceState(null, '', url)
}

const EST_METRIC = {
  id: 'est_total', label: '내 예상 월 생활비', detail: '답변으로 계산한 주거·관리비·전기·가스·물·외식·장보기·교통·기름값 합계 (조건 밖 지역은 회색)',
  unit: '원/월', field: 'est_total', gran: null, better: 'low',
  sources: ['molit_rent', 'kapt_fee', 'kepco_house_power', 'std_water_sewage_fee', 'std_trash_bag_price',
            'mois_public_fee', 'mois_dining', 'kca_price', 'opinet_price'],
}

// 휴대폰 폭(styles.css의 760px 기준과 같게)인지. 창 크기가 바뀌면 다시 계산한다
function useIsMobile(query = '(max-width: 760px)') {
  const get = () => typeof window !== 'undefined' && window.matchMedia(query).matches
  const [m, setM] = useState(get)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setM(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return m
}

export default function App() {
  const [metrics, setMetrics] = useState([])
  const [regions, setRegions] = useState(null)   // region_code → 요약 행
  const [geo, setGeo] = useState(null)
  const [sources, setSources] = useState([])
  const [spec, setSpec] = useState(null)         // /api/questions
  const [metricId, setMetricId] = useState('cost_s')
  const [selected, setSelected] = useState(null)
  const [mode, setModeRaw] = useState(startMode) // home | explore | quiz | results
  const setMode = (m) => { setModeRaw(m); if (m !== 'random') writeView(m) }
  const [pick, setPick] = useState(null)           // /api/random 응답 (아무 데나 살아보기)
  const pickRandom = (code) => {
    apiJSON(`/api/random${code ? `?code=${encodeURIComponent(code)}` : ''}`)
      .then((d) => { setPick(d); setSelected(d.result.region_code); setModeRaw('random'); writeView('random', d.result.region_code) })
      .catch((e) => setError(String(e)))
  }
  const [answers, setAnswers] = useState(readAnswers)
  const [rec, setRec] = useState(null)           // /api/recommend 응답
  const [error, setError] = useState(null)
  const isMobile = useIsMobile()
  const [mapOpen, setMapOpen] = useState(false)   // 휴대폰 결과 화면: 지도는 눌렀을 때만 띄운다

  useEffect(() => {
    Promise.all([apiJSON('/api/metrics'), apiJSON('/api/regions'), apiJSON('/api/sources'),
                 getJSON('/sigungu.geojson'), apiJSON('/api/questions')])   // 경계 geojson은 화면과 같이 배포된 정적 파일
      .then(([m, r, s, g, q]) => {
        setMetrics(m)
        setRegions(Object.fromEntries(r.map((row) => [row.region_code, row])))
        setSources(s)
        setGeo(g)
        setSpec(q)
      })
      .catch((e) => setError(String(e)))
  }, [])

  // URL에 답변이 있으면 바로 결과로
  useEffect(() => {
    if (!answers) return
    apiJSON('/api/recommend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(answers) })
      .then((d) => { setRec(d); setMode('results') })
      .catch((e) => setError(String(e)))
  }, [answers])

  // 주소가 ?view=random(&code=)이면 처음에 뽑아 둔다
  useEffect(() => {
    if (startMode() === 'random') pickRandom(new URLSearchParams(location.search).get('code') || undefined)
  }, [])

  const inResults = mode === 'results' && rec && spec   // 질문 정의(spec)가 와야 결과 문구를 만들 수 있다
  const hideMap = isMobile && inResults && !mapOpen
  const metric = inResults ? EST_METRIC : metrics.find((m) => m.id === metricId)

  // 결과 모드: 지도에 '내 예상 월 생활비'를 넣는다 (조건 밖 지역은 null → 회색)
  const mapRegions = useMemo(() => {
    if (!regions) return null
    if (!inResults) return regions
    const est = Object.fromEntries(rec.results.map((x) => [x.region_code, x.total]))
    return Object.fromEntries(Object.entries(regions).map(([k, r]) => [k, { ...r, est_total: est[k] ?? null }]))
  }, [regions, inResults, rec])

  const breaks = useMemo(() => {
    if (!mapRegions || !metric) return []
    return quantileBreaks(Object.values(mapRegions).map((r) => r[metric.field]))
  }, [mapRegions, metric])

  const groups = useMemo(() => {
    const g = {}
    for (const m of metrics) (g[m.group] ||= []).push(m)
    return Object.entries(g)
  }, [metrics])

  const finishQuiz = (a) => { setMapOpen(false); writeAnswers(a); setSelected(null); setAnswers({ ...a }) }
  const backToMap = () => { writeAnswers(null); setAnswers(null); setRec(null); setMode('explore'); setSelected(null) }
  const goHome = () => { writeAnswers(null); setAnswers(null); setRec(null); setMode('home'); setSelected(null) }

  return (
    <div className="app">
      <header className="topbar">
        <h1><button type="button" className="brand" onClick={goHome}><Logo size={28} /><span>어디 살까?</span></button></h1>
        {(mode === 'explore' || mode === 'random') && (
          <button type="button" className="secondary" onClick={() => pickRandom()}>🎲 아무 데나</button>
        )}
        {mode === 'explore' && (
          <>
            <button type="button" className="primary" onClick={() => setMode('quiz')} disabled={!spec}>나한테 맞는 동네 찾기</button>
            <label className="metric-select">
              <span>지도에 칠할 지표</span>
              <select value={metricId} onChange={(e) => setMetricId(e.target.value)}>
                {groups.map(([group, ms]) => (
                  <optgroup key={group} label={group}>
                    {ms.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
          </>
        )}
        {inResults && isMobile && (
          <button type="button" className="secondary" aria-expanded={mapOpen} onClick={() => setMapOpen(!mapOpen)}>
            {mapOpen ? '지도 닫기' : '🗺 지도로 보기'}
          </button>
        )}
        {inResults && <button type="button" className="secondary" onClick={backToMap}>지표 지도로</button>}
        {metric && (mode === 'explore' || (inResults && !hideMap)) && <p className="metric-detail">{metric.detail}</p>}
        {mode === 'home' && <button type="button" className="secondary topbar-right" onClick={() => setMode('explore')}>지도로 둘러보기</button>}
      </header>

      {mode === 'home' && !inResults ? (
        <Home spec={spec} error={error} onStart={() => setMode('quiz')} onMap={() => setMode('explore')} onRandom={() => pickRandom()} />
      ) : mode === 'quiz' && spec ? (
        <main className="body quiz-body">
          <Questionnaire spec={spec} initial={answers} onDone={finishQuiz} onCancel={() => setMode(rec ? 'results' : 'home')} />
        </main>
      ) : (
        <main className="body">
          {!hideMap && (
            <section className="map-wrap">
              {error && <div className="error">지금 서버가 쉬는 중이에요. 잠시 뒤 새로고침해 주세요.</div>}
              {!error && (!geo || !regions) && <div className="loading">지도를 불러오는 중…</div>}
              {geo && mapRegions && metric && (
                <MapView geo={geo} regions={mapRegions} metric={metric} breaks={breaks}
                         selected={selected} focus={mode === 'random' ? pick?.result.region_code : null}
                         onSelect={mode === 'random' ? pickRandom : setSelected} />
              )}
              {metric && mapRegions && <Legend metric={metric} breaks={breaks} />}
            </section>
          )}
          {inResults ? (
            <aside className="panel wide">
              <Results spec={spec} data={rec} selected={selected} onSelect={setSelected} onRestart={() => setMode('quiz')} />
              {selected && regions?.[selected] && (
                <DetailPanel code={selected} summary={regions[selected]} metrics={metrics} sources={sources}
                             onClose={() => setSelected(null)} embedded />
              )}
            </aside>
          ) : mode === 'random' && pick ? (
            <aside className="panel wide">
              <RandomPick data={pick} onAgain={() => pickRandom()} onQuiz={() => setMode('quiz')} />
              {regions?.[pick.result.region_code] && (
                <DetailPanel code={pick.result.region_code} summary={regions[pick.result.region_code]} metrics={metrics}
                             sources={sources} onClose={() => setMode('explore')} embedded />
              )}
            </aside>
          ) : (
            selected && regions?.[selected] && (
              <DetailPanel code={selected} summary={regions[selected]} metrics={metrics} sources={sources}
                           onClose={() => setSelected(null)} />
            )
          )}
        </main>
      )}

      <Attribution sources={sources}
                   active={mode === 'home' ? EST_METRIC.sources
                     : [...(metric?.sources || (metric ? [metric.source] : [])), 'vworld_sigungu']} />
    </div>
  )
}
