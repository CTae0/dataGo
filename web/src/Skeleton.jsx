// 불러오는 동안 보여 주는 회색 뼈대 (글자 대신 모양만)
export default function Skeleton({ kind = 'card', label = '불러오는 중…' }) {
  return (
    <div className={`skeleton sk-${kind}`} role="status" aria-label={label}>
      <div className="sk-block sk-art" />
      <div className="sk-line w60" />
      <div className="sk-line w40 tall" />
      <div className="sk-line w90" />
      <div className="sk-line w80" />
    </div>
  )
}
