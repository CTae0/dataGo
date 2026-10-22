import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import Legend from './Legend.jsx'
import DetailPanel from './DetailPanel.jsx'
import Attribution from './Attribution.jsx'
import Questionnaire from './Questionnaire.jsx'
import Results from './Results.jsx'
import Home from './Home.jsx'
import Logo from './Logo.jsx'
import RandomPick from './RandomPick.jsx'
import TabBar from './TabBar.jsx'
import BottomSheet from './BottomSheet.jsx'
import MetricChips from './MetricChips.jsx'
import RegionSummary from './RegionSummary.jsx'
import Skeleton from './Skeleton.jsx'
import { quantileBreaks } from './format.js'
import { apiJSON } from './api.js'

// 지도(maplibre)는 필요할 때만 불러온다 → 첫 화면이 가볍다
const MapView = lazy(() => import('./MapView.jsx'))

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
// 첫 화면은 '/', 지도는 '?view=map', 랜덤은 '?view=random&code=시군구코드', 결과는 '?a=답'
const startMode = () => {
  const q = new URLSearchParams(location.search)
  return { map: 'explore', random: 'random' }[q.get('view')] || (q.get('a') ? 'results' : 'home')
}
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
  unit: '원/월', field: 'est_total', gran: null, better: 'low', group: '내 결과',
  sources: ['molit_rent', 'kapt_fee', 'kepco_house_power', 'std_water_sewage_fee', 'std_trash_bag_price',
            'mois_public_fee', 'mois_dining', 'kca_price', 'opinet_price'],
}
const SCREEN_TITLE = { home: '', quiz: '질문', results: '내 동네', explore: '지도', random: '랜덤 동네' }

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
  const [mode, setModeRaw] = useState(startMode) // home | explore | quiz | results | random
  const setMode = (m) => { setModeRaw(m); if (m !== 'random') writeView(m) }
  const [pick, setPick] = useState(null)           // /api/random 응답 (아무 데나 살아보기)
  const [answers, setAnswers] = useState(readAnswers)
  const [rec, setRec] = useState(null)           // /api/recommend 응답
  const [error, setError] = useState(null)
  const isMobile = useIsMobile()
  const [sheet, setSheet] = useState(null)       // 휴대폰 지도 시트 단계: null | peek | half | full
  const [attrOpen, setAttrOpen] = useState(false)

  const pickRandom = useCallback((code) => {
    apiJSON(`/api/random${code ? `?code=${encodeURIComponent(code)}` : ''}`)
      .then((d) => {
        setPick(d); setMetricId((m) => (m === 'est_total' ? 'cost_s' : m)); setSelected(d.result.region_code); setModeRaw('random'); writeView('random', d.result.region_code)
        setSheet('half')
      })
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    Promise.all([apiJSON('/api/metrics'), apiJSON('/api/regions'), apiJSON('/api/sources'), apiJSON('/api/questions')])
      .then(([m, r, s, q]) => {
        setMetrics(m)
        setRegions(Object.fromEntries(r.map((row) => [row.region_code, row])))
        setSources(s)
        setSpec(q)
      })
      .catch((e) => setError(String(e)))
  }, [])

  // 지도가 필요한 화면에 처음 들어갈 때만 경계(geojson, 약 1MB)를 받는다
  const needMap = isMobile ? (mode === 'explore' || mode === 'random') : (mode !== 'home' && mode !== 'quiz')
  useEffect(() => {
    if (!needMap || geo) return
    getJSON('/sigungu.geojson').then(setGeo).catch((e) => setError(String(e)))
  }, [needMap, geo])

  // 답변이 바뀌면 다시 계산 (URL에 답변이 있으면 처음에 바로)
  useEffect(() => {
    if (!answers) return
    apiJSON('/api/recommend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(answers) })
      .then((d) => { setRec(d); setModeRaw((m) => (m === 'quiz' || m === 'home' || m === 'results' ? 'results' : m)) })
      .catch((e) => setError(String(e)))
  }, [answers])

  // 주소가 ?view=random(&code=)이면 처음에 뽑아 둔다
  useEffect(() => {
    if (startMode() === 'random') pickRandom(new URLSearchParams(location.search).get('code') || undefined)
  }, [pickRandom])

  const inResults = mode === 'results' && rec && spec   // 질문 정의(spec)가 와야 결과 문구를 만들 수 있다
  // 설문 결과는 결과 화면에서만 쓴다. 지도·랜덤은 늘 초기 상태(기본 지표·기본 답)로 보여 준다
  const quizMap = !!inResults
  const mapMetrics = useMemo(() => (quizMap ? [EST_METRIC, ...metrics] : metrics), [quizMap, metrics])
  const metric = !isMobile && inResults ? EST_METRIC : (mapMetrics.find((m) => m.id === metricId) || mapMetrics[0])

  const mapRegions = useMemo(() => {
    if (!regions) return null
    if (!rec || !quizMap) return regions
    const est = Object.fromEntries(rec.results.map((x) => [x.region_code, x.total]))
    return Object.fromEntries(Object.entries(regions).map(([k, r]) => [k, { ...r, est_total: est[k] ?? null }]))
  }, [regions, rec, quizMap])

  const breaks = useMemo(() => {
    if (!mapRegions || !metric) return []
    return quantileBreaks(Object.values(mapRegions).map((r) => r[metric.field]))
  }, [mapRegions, metric])

  const groups = useMemo(() => {
    const g = {}
    for (const m of mapMetrics) (g[m.group] ||= []).push(m)
    return Object.entries(g)
  }, [mapMetrics])

  const finishQuiz = (a) => { writeAnswers(a); setSelected(null); setAnswers({ ...a }); setModeRaw('results'); writeView('results') }
  const changeSort = (v) => { const a = { ...(answers || {}), sort: v }; writeAnswers(a); setAnswers(a) }
  const resetMap = () => { setSelected(null); setSheet(null); setMetricId('cost_s') }
  const backToMap = () => { setMode('explore'); resetMap() }
  const goHome = () => { setMode('home'); setSelected(null); setSheet(null) }
  const mineFor = (code) => (quizMap ? rec?.results.find((x) => x.region_code === code) : null)

  // 휴대폰 탭 이동
  const tabOf = { home: 'home', quiz: 'mine', results: 'mine', explore: 'map', random: 'random' }[mode]
  const goTab = (t) => {
    window.scrollTo({ top: 0 })
    if (t === 'home') goHome()
    else if (t === 'mine') setMode(rec ? 'results' : 'quiz')
    else if (t === 'map') { setMode('explore'); resetMap() }
    else if (t === 'random') { if (pick && mode !== 'random') { setModeRaw('random'); writeView('random', pick.result.region_code); setSelected(pick.result.region_code); setSheet('half') } else pickRandom() }
  }
  const selectOnMap = (code) => {
    if (mode === 'random') return pickRandom(code)
    setSelected(code)
    if (isMobile) setSheet('peek')
  }

  const activeSources = mode === 'home' ? EST_METRIC.sources
    : [...(metric?.sources || (metric ? [metric.source] : [])), 'vworld_sigungu']

  const mapEl = (
    <section className="map-wrap">
      {error && <div className="error">지금 서버가 쉬는 중이에요. 잠시 뒤 새로고침해 주세요.</div>}
      {!error && (!geo || !regions) && <div className="loading">지도를 불러오는 중…</div>}
      {geo && mapRegions && metric && (
        <Suspense fallback={<div className="loading">지도를 불러오는 중…</div>}>
          <MapView geo={geo} regions={mapRegions} metric={metric} breaks={breaks}
                   selected={selected} focus={mode === 'random' ? pick?.result.region_code : null}
                   onSelect={selectOnMap} />
        </Suspense>
      )}
      {metric && mapRegions && <Legend metric={metric} breaks={breaks} compact={isMobile} />}
    </section>
  )

  // ── 휴대폰 ───────────────────────────────────────────
  if (isMobile) {
    const mapScreen = mode === 'explore' || mode === 'random'
    return (
      <div className={`app mobile ${mapScreen ? 'map-screen' : ''} ${mode === 'quiz' ? 'in-quiz' : ''}`}>
        <header className="topbar slim">
          <button type="button" className="brand" onClick={goHome}><Logo size={26} /><span>어디 살까?</span></button>
          {SCREEN_TITLE[mode] && <span className="screen-title">{SCREEN_TITLE[mode]}</span>}
        </header>

        {mode === 'home' && (
          <Home spec={spec} error={error} onStart={() => setMode('quiz')} onMap={() => goTab('map')} onRandom={() => pickRandom()} />
        )}
        {mode === 'quiz' && (spec
          ? <main className="page quiz-body"><Questionnaire spec={spec} initial={answers} onDone={finishQuiz} onCancel={() => setMode(rec ? 'results' : 'home')} /></main>
          : <main className="page"><Skeleton kind="quiz" /></main>)}
        {mode === 'results' && (
          <main className="page">
            {inResults ? (
              <>
                <Results spec={spec} data={rec} selected={selected} onSelect={setSelected} onRestart={() => setMode('quiz')} onSort={changeSort} />
                {selected && regions?.[selected] && (
                  <DetailPanel code={selected} summary={regions[selected]} metrics={metrics} sources={sources}
                               onClose={() => setSelected(null)} embedded />
                )}
              </>
            ) : error ? <p className="relaxed">지금 서버가 쉬는 중이에요. 잠시 뒤 새로고침해 주세요.</p> : <Skeleton kind="results" label="결과를 계산하는 중…" />}
          </main>
        )}
        {mapScreen && (
          <main className="map-full">
            {mapEl}
            {mode === 'explore' && <MetricChips metrics={mapMetrics} value={metric?.id} onChange={setMetricId} />}
            {mode === 'explore' && selected && regions?.[selected] && sheet && (
              <BottomSheet level={sheet} onLevel={setSheet} onClose={() => { setSheet(null); setSelected(null) }}
                           label={`${regions[selected].sigungu} 정보`}>
                <RegionSummary summary={mapRegions?.[selected] || regions[selected]} metric={metric} mine={mineFor(selected)}
                               onMore={sheet !== 'full' ? () => setSheet('full') : null} />
                {sheet === 'full' && (
                  <DetailPanel code={selected} summary={regions[selected]} metrics={metrics} sources={sources}
                               onClose={() => setSheet('peek')} embedded />
                )}
              </BottomSheet>
            )}
            {mode === 'random' && pick && sheet && (
              <BottomSheet level={sheet} onLevel={setSheet} onClose={() => setSheet('peek')} label="랜덤 동네">
                <RandomPick data={pick} onAgain={() => pickRandom()} onQuiz={() => setMode('quiz')} />
                {sheet === 'full' && regions?.[pick.result.region_code] && (
                  <DetailPanel code={pick.result.region_code} summary={regions[pick.result.region_code]} metrics={metrics}
                               sources={sources} onClose={() => setSheet('half')} embedded />
                )}
              </BottomSheet>
            )}
            <button type="button" className="attr-chip" onClick={() => setAttrOpen(true)}>ⓘ 출처</button>
          </main>
        )}

        {!mapScreen && mode !== 'quiz' && (
          <Attribution sources={sources} active={activeSources} compact onOpen={() => setAttrOpen(true)} />
        )}
        {attrOpen && (
          <BottomSheet level="full" onLevel={(l) => l !== 'full' && setAttrOpen(false)} onClose={() => setAttrOpen(false)} label="자료 출처">
            <Attribution sources={sources} active={activeSources} expanded />
          </BottomSheet>
        )}
        {mode !== 'quiz' && <TabBar active={tabOf} onGo={goTab} />}
      </div>
    )
  }

  // ── PC ─────────────────────────────────────────────
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
              <select value={metric?.id} onChange={(e) => setMetricId(e.target.value)}>
                {groups.map(([group, ms]) => (
                  <optgroup key={group} label={group}>
                    {ms.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
          </>
        )}
        {inResults && <button type="button" className="secondary" onClick={backToMap}>지표 지도로</button>}
        {metric && (mode === 'explore' || inResults) && <p className="metric-detail">{metric.detail}</p>}
        {mode === 'home' && <button type="button" className="secondary topbar-right" onClick={backToMap}>지도로 둘러보기</button>}
      </header>

      {mode === 'home' ? (
        <Home spec={spec} error={error} onStart={() => setMode('quiz')} onMap={backToMap} onRandom={() => pickRandom()} />
      ) : mode === 'quiz' ? (
        <main className="body quiz-body">
          {spec ? <Questionnaire spec={spec} initial={answers} onDone={finishQuiz} onCancel={() => setMode(rec ? 'results' : 'home')} />
                : <Skeleton kind="quiz" />}
        </main>
      ) : (
        <main className="body">
          {mapEl}
          {mode === 'results' ? (
            <aside className="panel wide">
              {inResults ? (
                <>
                  <Results spec={spec} data={rec} selected={selected} onSelect={setSelected} onRestart={() => setMode('quiz')} onSort={changeSort} />
                  {selected && regions?.[selected] && (
                    <DetailPanel code={selected} summary={regions[selected]} metrics={metrics} sources={sources}
                                 onClose={() => setSelected(null)} embedded />
                  )}
                </>
              ) : <Skeleton kind="results" label="결과를 계산하는 중…" />}
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

      <Attribution sources={sources} active={activeSources} />
    </div>
  )
}
