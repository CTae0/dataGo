import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import './mobile.css'   // 결과 공통·휴대폰 화면 틀 (styles.css의 토큰을 쓴다)
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
