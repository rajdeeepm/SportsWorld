import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { LiveProvider } from './lib/live'
import './styles/app.css'
import './styles/legacy.css'

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: false } } })

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <LiveProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </LiveProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
