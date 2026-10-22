// 휴대폰 하단 탭 바: 홈 · 내 동네 · 지도 · 랜덤 (퀴즈 중에는 숨긴다 — App.jsx)
const TABS = [
  { id: 'home', icon: '🏠', label: '홈' },
  { id: 'mine', icon: '🏡', label: '내 동네' },
  { id: 'map', icon: '🗺️', label: '지도' },
  { id: 'random', icon: '🎲', label: '랜덤' },
]

export default function TabBar({ active, onGo }) {
  return (
    <nav className="tabbar" aria-label="화면 이동">
      {TABS.map((t) => (
        <button key={t.id} type="button" className={`tab ${active === t.id ? 'on' : ''}`}
                aria-current={active === t.id ? 'page' : undefined} onClick={() => onGo(t.id)}>
          <span className="tab-icon" aria-hidden="true">{t.icon}</span>
          <span className="tab-label">{t.label}</span>
        </button>
      ))}
    </nav>
  )
}
