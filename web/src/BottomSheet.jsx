import { useEffect, useRef, useState } from 'react'

// 휴대폰 지도 위 바텀시트 (라이브러리 없음)
// level: 'peek'(요약) | 'half'(반) | 'full'(전체). 손잡이를 끌거나 튕기면 가까운 단계로 붙고, 누르면 다음 단계로.
// Esc → onClose. 펼치면 시트 안으로 포커스를 옮긴다.
const ORDER = ['peek', 'half', 'full']

function heights() {
  const vh = window.innerHeight
  const top = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--topbar-h')) || 56
  const tab = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--tabbar-h')) || 64
  const room = vh - top - tab
  return { peek: 112, half: Math.round(room * 0.55), full: Math.round(room - 8) }
}

export default function BottomSheet({ level, onLevel, onClose, label, children }) {
  const [drag, setDrag] = useState(null)      // { startY, startH, h, t }
  const box = useRef(null)
  const h = heights()
  const height = drag ? drag.h : h[level]

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  useEffect(() => { if (level === 'full') box.current?.focus() }, [level])

  const down = (e) => {
    try { e.currentTarget.setPointerCapture?.(e.pointerId) } catch { /* 이미 끝난 포인터면 무시 */ }
    setDrag({ startY: e.clientY, startH: h[level], h: h[level], t: performance.now(), moved: false })
  }
  const move = (e) => {
    if (!drag) return
    const nh = Math.max(64, Math.min(h.full, drag.startH + (drag.startY - e.clientY)))
    setDrag({ ...drag, h: nh, moved: drag.moved || Math.abs(drag.startY - e.clientY) > 6 })
  }
  const up = (e) => {
    if (!drag) return
    const dy = drag.startY - e.clientY
    const v = dy / Math.max(1, performance.now() - drag.t)       // px/ms, 위로 +
    setDrag(null)
    if (!drag.moved) {                                             // 그냥 누름 → 다음 단계 (전체면 접기)
      onLevel(level === 'full' ? 'peek' : ORDER[ORDER.indexOf(level) + 1])
      return
    }
    if (v > 0.6) return onLevel(level === 'peek' ? 'half' : 'full')   // 위로 튕김
    if (v < -0.6) return level === 'peek' ? onClose?.() : onLevel(level === 'full' ? 'half' : 'peek')
    const nearest = ORDER.reduce((a, b) => (Math.abs(h[b] - drag.h) < Math.abs(h[a] - drag.h) ? b : a))
    if (drag.h < h.peek * 0.6) onClose?.()
    else onLevel(nearest)
  }

  return (
    <section className={`sheet ${drag ? 'dragging' : ''} level-${level}`} style={{ height }} aria-label={label}
             ref={box} tabIndex={-1}>
      <button type="button" className="sheet-handle" aria-expanded={level === 'full'}
              aria-label={level === 'full' ? '시트 접기' : '시트 더 펼치기'}
              onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => setDrag(null)}>
        <span aria-hidden="true" />
      </button>
      <div className="sheet-body">{children}</div>
    </section>
  )
}
