import { useEffect, useMemo, useState } from 'react'
import MapView from './MapView.jsx'
import Legend from './Legend.jsx'
import DetailPanel from './DetailPanel.jsx'
import Attribution from './Attribution.jsx'
import { quantileBreaks } from './format.js'

async function getJSON(url) {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`)
  return r.json()
}

export default function App() {
  const [metrics, setMetrics] = useState([])
  const [regions, setRegions] = useState(null)   // region_code → 요약 행
  const [geo, setGeo] = useState(null)
  const [sources, setSources] = useState([])
  const [metricId, setMetricId] = useState('cost_s')
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([getJSON('/api/metrics'), getJSON('/api/regions'), getJSON('/api/sources'), getJSON('/sigungu.geojson')])
      .then(([m, r, s, g]) => {
        setMetrics(m)
        setRegions(Object.fromEntries(r.map((row) => [row.region_code, row])))
        setSources(s)
        setGeo(g)
      })
      .catch((e) => setError(String(e)))
  }, [])

  const metric = metrics.find((m) => m.id === metricId)
  const breaks = useMemo(() => {
    if (!regions || !metric) return []
    return quantileBreaks(Object.values(regions).map((r) => r[metric.field]))
  }, [regions, metric])

  const groups = useMemo(() => {
    const g = {}
    for (const m of metrics) (g[m.group] ||= []).push(m)
    return Object.entries(g)
  }, [metrics])

  return (
    <div className="app">
      <header className="topbar">
        <h1>어디 살까?</h1>
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
        {metric && <p className="metric-detail">{metric.detail}</p>}
      </header>

      <main className="body">
        <section className="map-wrap">
          {error && <div className="error">불러오지 못했습니다: {error}</div>}
          {!error && (!geo || !regions) && <div className="loading">지도를 불러오는 중…</div>}
          {geo && regions && metric && (
            <MapView geo={geo} regions={regions} metric={metric} breaks={breaks}
                     selected={selected} onSelect={setSelected} />
          )}
          {metric && regions && <Legend metric={metric} breaks={breaks} />}
        </section>
        {selected && regions?.[selected] && (
          <DetailPanel code={selected} summary={regions[selected]} metrics={metrics} sources={sources}
                       onClose={() => setSelected(null)} />
        )}
      </main>

      <Attribution sources={sources} active={[...(metric?.sources || (metric ? [metric.source] : [])), 'vworld_sigungu']} />
    </div>
  )
}
