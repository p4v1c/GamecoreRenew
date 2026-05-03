import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import OverlayScreen from './components/OverlayScreen'

const isOverlay = window.location.pathname === '/overlay'
if (isOverlay) document.body.classList.add('overlay-mode')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isOverlay ? <OverlayScreen /> : <App />}
  </React.StrictMode>
)
