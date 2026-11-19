import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initializeEmbeddedPresentation } from './embeddedPresentation'
import './embeddedPresentation.css'

const root = createRoot(document.getElementById('root')!)
void initializeEmbeddedPresentation().then(async () => {
  await document.fonts.ready
  root.render(<App />)
  const origin = new URLSearchParams(window.location.search).get('hostOrigin')
  if (window.parent !== window && origin) {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      window.parent.postMessage({ type: 'semantica:presentation-ready' }, origin)
    }))
  }
}).catch(() => {
  root.render(<main role="alert">Explorer presentation could not be initialized. Reload from the host application.</main>)
})
