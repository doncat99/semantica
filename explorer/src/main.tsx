import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initializeEmbeddedPresentation } from './embeddedPresentation'
import './embeddedPresentation.css'

const root = createRoot(document.getElementById('root')!)
void initializeEmbeddedPresentation().then(() => {
  root.render(<App />)
}).catch(() => {
  root.render(<main role="alert">Explorer presentation could not be initialized. Reload from the host application.</main>)
})
