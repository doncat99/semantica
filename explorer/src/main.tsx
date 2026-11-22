import { createRoot } from 'react-dom/client'
import './index.css'
import './embeddedPresentation.css'
import App from './App.tsx'

document.getElementById('root')!.classList.add('semantica-explorer');
createRoot(document.getElementById('root')!).render(
  <App />,
)
