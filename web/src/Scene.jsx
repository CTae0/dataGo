// 지역 유형별 대표 그림 (애니메이션 SVG). 유형은 mart.region_features.archetype
//   metropolis / commuter_town / small_city / harbor_city / seaside_village / mountain_village / farmland / island
// 구름·파도·배·연기·기차가 천천히 움직인다. '동작 줄이기' 설정이면 멈춘다 (styles.css .scene).
import { useId } from 'react'

const W = 320, H = 180

function Sky({ top = '#bfe0ff', bottom = '#eef7ff', sun = true }) {
  const id = useId().replace(/:/g, '')   // 카드 여러 장이 한 화면에 있어도 그라디언트 id가 겹치지 않게
  return (
    <>
      <defs>
        <linearGradient id={`sky${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={top} /><stop offset="1" stopColor={bottom} />
        </linearGradient>
      </defs>
      <rect width={W} height={H} fill={`url(#sky${id})`} />
      {sun && <circle cx="262" cy="38" r="16" fill="#ffd66b" className="s-pulse" />}
      <g className="s-drift">
        <Cloud x={40} y={30} s={1} /><Cloud x={170} y={20} s={0.75} /><Cloud x={330} y={40} s={0.9} />
      </g>
    </>
  )
}

function Cloud({ x, y, s }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} fill="#ffffff" opacity="0.95">
      <ellipse cx="0" cy="8" rx="22" ry="9" /><ellipse cx="14" cy="2" rx="14" ry="10" /><ellipse cx="-12" cy="4" rx="11" ry="8" />
    </g>
  )
}

function Sea({ y = 130, color = '#4aa3df' }) {
  return (
    <>
      <rect x="0" y={y} width={W} height={H - y} fill={color} />
      <g className="s-wave" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" opacity="0.8">
        {[0, 1, 2].map((i) => (
          <path key={i} d={`M-40 ${y + 10 + i * 13} q 20 -6 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0 t 40 0`} />
        ))}
      </g>
    </>
  )
}

function Gull({ x, y }) {
  return <path className="s-flap" d={`M${x} ${y} q 5 -5 10 0 q 5 -5 10 0`} fill="none" stroke="#3b3b3b" strokeWidth="1.6" strokeLinecap="round" />
}

function Boat({ x, y }) {
  return (
    <g className="s-bob" transform={`translate(${x} ${y})`}>
      <path d="M0 0 h40 l-6 10 h-28 z" fill="#e85d4a" />
      <rect x="18" y="-22" width="2" height="22" fill="#5b4636" />
      <path d="M20 -22 l14 16 h-14 z" fill="#ffffff" />
    </g>
  )
}

function Tree({ x, y, s = 1, color = '#4caf6a' }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <rect x="-2" y="0" width="4" height="10" fill="#7a5a3a" />
      <circle cx="0" cy="-4" r="9" fill={color} />
    </g>
  )
}

function House({ x, y, wall = '#fff4e0', roof = '#e07a5f', smoke = false }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      {smoke && (
        <g className="s-smoke" fill="#ffffff" opacity="0.8">
          <circle cx="20" cy="-22" r="4" /><circle cx="24" cy="-30" r="5" /><circle cx="20" cy="-40" r="6" />
        </g>
      )}
      <rect x="16" y="-18" width="6" height="10" fill="#8d6e63" />
      <path d="M-4 0 L14 -16 L32 0 Z" fill={roof} />
      <rect x="0" y="0" width="28" height="20" fill={wall} />
      <rect x="10" y="8" width="8" height="12" fill="#8d6e63" />
    </g>
  )
}

function Buildings({ base = 140, colors = ['#7e8fb3', '#9aa9c9', '#6b7aa1', '#b3c0dc'], heights = [70, 95, 60, 110, 80, 50, 90, 65], twinkle = true }) {
  let x = 6
  return (
    <g>
      {heights.map((h, i) => {
        const w = 30 + (i % 3) * 6
        const bx = x
        x += w + 6
        return (
          <g key={i}>
            <rect x={bx} y={base - h} width={w} height={h} fill={colors[i % colors.length]} rx="2" />
            {twinkle && Array.from({ length: Math.floor(h / 16) }).map((_, r) => (
              <rect key={r} x={bx + 6} y={base - h + 8 + r * 16} width={w - 12} height="5" fill="#fff6c9"
                    className={(r + i) % 3 === 0 ? 's-twinkle' : ''} opacity="0.85" />
            ))}
          </g>
        )
      })}
    </g>
  )
}

const SCENES = {
  metropolis: () => (
    <>
      <Sky top="#9fc8ff" />
      <Buildings base={150} heights={[90, 120, 75, 135, 100, 70, 115, 85]} />
      <rect x="0" y="150" width={W} height="30" fill="#5d6577" />
      <g className="s-train"><rect x="-120" y="154" width="110" height="14" rx="4" fill="#3fa9a0" />
        {[0, 1, 2, 3, 4].map((i) => <rect key={i} x={-114 + i * 20} y="157" width="12" height="6" fill="#e9fffb" />)}</g>
    </>
  ),
  commuter_town: () => (
    <>
      <Sky />
      <g opacity="0.45"><Buildings base={120} heights={[40, 60, 45, 70, 50, 38, 62, 44]} twinkle={false} /></g>
      {[20, 80, 140, 200, 260].map((x, i) => (
        <g key={x}><rect x={x} y={70 + (i % 2) * 10} width="44" height={80 - (i % 2) * 10} fill={i % 2 ? '#f2d7b6' : '#e8c39e'} />
          {Array.from({ length: 5 }).map((_, r) => <rect key={r} x={x + 6} y={78 + (i % 2) * 10 + r * 13} width="32" height="4" fill="#fffaf0" />)}</g>
      ))}
      <rect x="0" y="150" width={W} height="30" fill="#8fbf7a" />
      <rect x="0" y="158" width={W} height="10" fill="#6f6f6f" />
      <g className="s-car"><rect x="-40" y="154" width="26" height="9" rx="3" fill="#e85d4a" /><circle cx="-34" cy="164" r="3" fill="#333" /><circle cx="-20" cy="164" r="3" fill="#333" /></g>
    </>
  ),
  small_city: () => (
    <>
      <Sky />
      <rect x="0" y="120" width={W} height="60" fill="#9ccc80" />
      <path d="M0 160 C 80 145, 160 175, 320 152 L320 180 L0 180 Z" fill="#6fb7e6" />
      <Buildings base={125} heights={[40, 55, 35, 60, 45, 30, 50, 38]} colors={['#e8b4a0', '#f2d1a5', '#c9d6a3', '#b8cfe6']} twinkle={false} />
      <Tree x={30} y={140} /><Tree x={290} y={138} s={1.2} /><Tree x={150} y={142} s={0.9} />
    </>
  ),
  harbor_city: () => (
    <>
      <Sky />
      <Buildings base={120} heights={[55, 80, 50, 95, 65, 45, 70, 58]} />
      <rect x="0" y="118" width={W} height="10" fill="#c9b79c" />
      <Sea y={128} />
      <Boat x={200} y={140} />
      <Gull x={60} y={60} /><Gull x={100} y={48} />
    </>
  ),
  seaside_village: () => (
    <>
      <Sky top="#a9dbff" />
      <path d="M0 110 C 60 100, 120 104, 180 112 L180 135 L0 135 Z" fill="#f3d9a4" />
      <House x={24} y={92} roof="#4f8fd6" /><House x={70} y={96} roof="#e07a5f" /><House x={118} y={98} roof="#f2b134" />
      <Sea y={122} color="#53b3e6" />
      <Boat x={230} y={135} />
      <Gull x={200} y={60} /><Gull x={240} y={72} />
    </>
  ),
  mountain_village: () => (
    <>
      <Sky top="#b8e1ff" />
      <path d="M-20 140 L60 60 L120 120 L190 50 L270 115 L340 70 L340 180 L-20 180 Z" fill="#7aa874" />
      <path d="M-20 160 L50 100 L110 140 L170 95 L240 145 L340 110 L340 180 L-20 180 Z" fill="#5c8f5a" />
      <path d="M175 58 L190 50 L205 60 Z" fill="#ffffff" />
      <House x={130} y={140} roof="#a65d3f" smoke />
      <Tree x={60} y={150} color="#3f7d4a" /><Tree x={80} y={156} s={0.8} color="#3f7d4a" /><Tree x={260} y={152} color="#3f7d4a" />
    </>
  ),
  farmland: () => (
    <>
      <Sky top="#c4e6ff" />
      <rect x="0" y="105" width={W} height="75" fill="#e6c96a" />
      {[0, 1, 2, 3, 4, 5].map((i) => <path key={i} d={`M0 ${112 + i * 12} Q 160 ${104 + i * 12} 320 ${112 + i * 12}`} stroke="#c9a94a" strokeWidth="3" fill="none" />)}
      <House x={220} y={86} wall="#f7ead0" roof="#c0392b" smoke />
      <Tree x={40} y={98} s={1.1} /><Tree x={70} y={100} s={0.9} />
      <g className="s-tractor"><rect x="-50" y="140" width="22" height="12" rx="2" fill="#2e8b57" /><rect x="-36" y="132" width="10" height="10" fill="#2e8b57" />
        <circle cx="-44" cy="154" r="5" fill="#333" /><circle cx="-30" cy="154" r="3.5" fill="#333" /></g>
    </>
  ),
  island: () => (
    <>
      <Sky top="#a4d8ff" />
      <Sea y={110} color="#3fa1d8" />
      <path d="M90 125 C 120 85, 200 85, 235 125 Z" fill="#7fb069" />
      <path d="M85 125 h155 l-8 6 h-140 z" fill="#f0d8a0" />
      <g transform="translate(200 92)"><rect x="-4" y="0" width="8" height="30" fill="#ffffff" /><rect x="-4" y="8" width="8" height="5" fill="#e85d4a" />
        <rect x="-6" y="-6" width="12" height="7" fill="#e85d4a" /><circle cx="0" cy="-2" r="2.5" fill="#ffe082" className="s-pulse" /></g>
      <Tree x={125} y={110} s={1.1} color="#3f9d58" />
      <Boat x={30} y={140} />
      <Gull x={250} y={50} />
    </>
  ),
}

export default function Scene({ type }) {
  const Draw = SCENES[type] || SCENES.small_city
  return (
    <svg className="scene" viewBox={`0 0 ${W} ${H}`} role="img" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
      <Draw />
    </svg>
  )
}
