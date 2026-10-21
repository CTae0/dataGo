// '어디 살까?' 아이콘: 파란 바탕 + 흰 지도 핀 + 핀 안의 집 + 노란 해. 같은 그림이 web/public/icon.svg(파비콘)에 있다
export default function Logo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <rect width="64" height="64" rx="15" fill="#2a78d6" />
      <path d="M32 55C32 55 16 38.8 16 27a16 16 0 0 1 32 0c0 11.8-16 28-16 28Z" fill="#ffffff" />
      <path d="M22.5 28.5 32 20l9.5 8.5" fill="none" stroke="#2a78d6" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M25.5 27v9.5h13V27" fill="#2a78d6" />
      <rect x="30" y="30.5" width="4" height="6" rx="1" fill="#ffffff" />
      <circle cx="45.5" cy="15" r="5" fill="#ffd66b" />
    </svg>
  )
}
