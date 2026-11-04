import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { SandboxApp } from './sandbox/SandboxApp.tsx'

// `#fb...` routes render the simulated social platform; everything else is the Crime Sentinel console.
function Root() {
  const [sandbox, setSandbox] = useState(() => window.location.hash.startsWith('#fb'))
  useEffect(() => {
    const on = () => setSandbox(window.location.hash.startsWith('#fb'))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return sandbox ? <SandboxApp /> : <App />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
