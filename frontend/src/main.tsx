import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import OverlayScreen from './components/OverlayScreen'

const isOverlay = window.location.pathname === '/overlay'
if (isOverlay) {
  document.documentElement.classList.add('overlay-mode')
  document.body.classList.add('overlay-mode')
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isOverlay ? <OverlayScreen /> : (
      /* Last net. Anything that escapes a surface boundary lands here rather
         than on a white screen the user cannot recover from without a mouse. */
      <ErrorBoundary fallback={
        <div style={{
          width: '100%', height: '100%', display: 'flex', alignItems: 'center',
          justifyContent: 'center', flexDirection: 'column', gap: 10,
          fontFamily: "'Outfit', sans-serif", color: '#fff', textAlign: 'center', padding: 40,
        }}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>GameCore could not start the interface</div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)' }}>
            Hold L1 + R1 for 2 seconds to force the default theme, then restart.
          </div>
        </div>
      }>
        <App />
      </ErrorBoundary>
    )}
  </React.StrictMode>
)
