import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'   // v6는 default export가 없다
// v6는 worker가 별도 ESM 파일이라 Vite에서는 주소를 직접 알려 줘야 한다
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

maplibregl.setWorkerUrl(workerUrl)
import { RAMP, NO_DATA, classOf, formatValue, isFallback, GRAN_LABEL } from './format.js'

const KOREA = [[124.5, 33.0], [131.0, 38.7]]

// 시도 평균으로 채운 지역 위에 덮는 사선 무늬 (색만으로 구분하지 않기 위해)
function hatchImage() {
  const size = 8
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')
  ctx.strokeStyle = 'rgba(40, 40, 38, 0.45)'
  ctx.lineWidth = 1.2
  ctx.beginPath()
  ctx.moveTo(0, size); ctx.lineTo(size, 0)
  ctx.moveTo(-size / 2, size / 2); ctx.lineTo(size / 2, -size / 2)
  ctx.moveTo(size / 2, size + size / 2); ctx.lineTo(size + size / 2, size / 2)
  ctx.stroke()
  return ctx.getImageData(0, 0, size, size)
}

function withValues(geo, regions, metric, breaks) {
  return {
    type: 'FeatureCollection',
    features: geo.features.map((f, i) => {
      const code = f.properties.sig_cd
      const r = regions[code] || {}
      const v = r[metric.field] ?? null
      const gran = metric.gran ? r[metric.gran] : 'exact'
      return {
        type: 'Feature', id: i, geometry: f.geometry,
        properties: { code, name: r.sigungu || f.properties.sig_kor_nm, sido: r.sido || '',
                      v, cls: classOf(v, breaks), fallback: v !== null && isFallback(gran), gran: gran || '' },
      }
    }),
  }
}

export default function MapView({ geo, regions, metric, breaks, selected, onSelect }) {
  const box = useRef(null)
  const map = useRef(null)
  const hovered = useRef(null)
  const [tip, setTip] = useState(null)
  const latest = useRef({ metric })
  latest.current = { metric, onSelect }

  // 지도 한 번 만들기 (배경 타일 없이 경계만 — 외부 키·요청 없음)
  useEffect(() => {
    const m = new maplibregl.Map({
      container: box.current,
      style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f4f6f8' } }] },
      bounds: KOREA, fitBoundsOptions: { padding: 24 }, attributionControl: false, dragRotate: false,
    })
    m.touchZoomRotate.disableRotation()
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('load', () => {
      m.addImage('hatch', hatchImage(), { pixelRatio: 2 })
      m.addSource('sgg', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      m.addLayer({ id: 'fill', type: 'fill', source: 'sgg', paint: {
        'fill-color': ['match', ['get', 'cls'], ...RAMP.flatMap((c, i) => [i, c]), NO_DATA],
      } })
      m.addLayer({ id: 'hatch', type: 'fill', source: 'sgg', filter: ['==', ['get', 'fallback'], true],
                   paint: { 'fill-pattern': 'hatch' } })
      // 이웃 사이 2px 표면 간격 역할: 흰 경계선
      m.addLayer({ id: 'line', type: 'line', source: 'sgg', paint: { 'line-color': '#ffffff', 'line-width': 0.6 } })
      m.addLayer({ id: 'hover', type: 'line', source: 'sgg', paint: {
        'line-color': '#0b0b0b',
        'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.5,
                       ['boolean', ['feature-state', 'hover'], false], 1.5, 0],
      } })
      map.current = m
      m.fire('eodi:ready')
    })
    m.on('mousemove', 'fill', (e) => {
      const f = e.features[0]
      if (hovered.current !== null && hovered.current !== f.id) m.setFeatureState({ source: 'sgg', id: hovered.current }, { hover: false })
      hovered.current = f.id
      m.setFeatureState({ source: 'sgg', id: f.id }, { hover: true })
      m.getCanvas().style.cursor = 'pointer'
      const p = f.properties
      setTip({ x: e.point.x, y: e.point.y, name: `${p.sido} ${p.name}`,
               value: formatValue(p.v === null || p.v === 'null' ? null : Number(p.v), latest.current.metric.unit),
               gran: p.fallback === true || p.fallback === 'true' ? GRAN_LABEL[p.gran] : null })
    })
    m.on('mouseleave', 'fill', () => {
      if (hovered.current !== null) m.setFeatureState({ source: 'sgg', id: hovered.current }, { hover: false })
      hovered.current = null
      m.getCanvas().style.cursor = ''
      setTip(null)
    })
    m.on('click', 'fill', (e) => latest.current.onSelect(e.features[0].properties.code))
    return () => m.remove()
  }, [])

  // 지표가 바뀌면 값만 다시 넣는다
  const fc = useRef(null)
  useEffect(() => {
    fc.current = withValues(geo, regions, metric, breaks)
    const apply = () => map.current?.getSource('sgg')?.setData(fc.current)
    if (map.current) apply()
    else {
      const t = setInterval(() => { if (map.current) { apply(); clearInterval(t) } }, 50)
      return () => clearInterval(t)
    }
  }, [geo, regions, metric, breaks])

  // 선택한 시군구 테두리
  useEffect(() => {
    const m = map.current
    if (!m || !fc.current) return
    for (const f of fc.current.features) m.setFeatureState({ source: 'sgg', id: f.id }, { selected: f.properties.code === selected })
  }, [selected, metric])

  return (
    <div className="map" ref={box} role="region" aria-label="전국 시군구 지도">
      {tip && (
        <div className="tooltip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          <strong>{tip.name}</strong>
          <span>{tip.value}</span>
          {tip.gran && <em>{tip.gran}로 대체</em>}
        </div>
      )}
    </div>
  )
}
