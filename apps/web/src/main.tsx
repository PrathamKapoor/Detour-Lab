import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ApiClient } from './api/client'
import './styles/global.css'

const container = document.getElementById('root')
if (!container) throw new Error('Root container #root is missing from index.html')

// One client instance for the whole app; the base URL comes from configuration.
const api = new ApiClient()

createRoot(container).render(
  <StrictMode>
    <App api={api} />
  </StrictMode>,
)