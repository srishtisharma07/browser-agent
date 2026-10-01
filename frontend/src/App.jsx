import { useEffect, useState } from 'react'

import Header       from './components/Header'
import TaskPanel    from './components/TaskPanel'
import BrowserViewer from './components/BrowserViewer'
import AgentActivity from './components/AgentActivity'
import TaskStatus   from './components/TaskStatus'

/**
 * App — AI Agent Control Center shell.
 *
 * Responsibilities:
 *  - Own the `backendStatus` state and the real /api/health fetch.
 *  - Compose the full-screen dashboard layout.
 *  - Pass status down to Header; all other components are self-contained.
 *
 * Phase 1: UI only — no agent, no Playwright, no Gemini, no LangGraph.
 */
export default function App() {
  const [backendStatus, setBackendStatus] = useState('checking')

  // VITE_API_BASE_URL is empty in dev so the Vite proxy forwards /api/* → :8000
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => {
        setBackendStatus(data?.status === 'ok' ? 'ok' : 'error')
      })
      .catch(() => setBackendStatus('error'))
  }, [API_BASE])

  return (
    /*
     * Full-screen flex column:
     *   Header (fixed height)
     *   ├── Middle row (flex-1, fills remaining height)
     *   │   ├── TaskPanel  (left sidebar, fixed width)
     *   │   ├── BrowserViewer (centre, grows)
     *   │   └── AgentActivity (right sidebar, fixed width)
     *   TaskStatus (fixed height footer)
     */
    <div className="h-screen flex flex-col bg-[#080d1a] text-slate-200 overflow-hidden">

      <Header backendStatus={backendStatus} />

      {/* Middle: three-column work area */}
      <div className="flex flex-1 min-h-0 divide-x divide-white/8">

        {/* Left sidebar — task input */}
        <div className="flex flex-col p-4 overflow-y-auto">
          <TaskPanel />
        </div>

        {/* Centre — browser viewport */}
        <div className="flex flex-1 flex-col min-w-0 p-3">
          <BrowserViewer />
        </div>

        {/* Right sidebar — agent activity log */}
        <div className="flex flex-col overflow-hidden">
          <AgentActivity />
        </div>

      </div>

      <TaskStatus />

    </div>
  )
}
