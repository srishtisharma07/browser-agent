import { useEffect, useState } from 'react'

/**
 * StatusBadge — small pill that shows backend health status.
 */
function StatusBadge({ status }) {
  const colours = {
    checking: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
    ok:       'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    error:    'bg-red-500/20 text-red-300 border-red-500/40',
  }
  const labels = { checking: 'Backend: Checking…', ok: 'Backend: Connected', error: 'Backend: Disconnected' }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${colours[status]}`}
    >
      <span
        className={`size-1.5 rounded-full ${
          status === 'ok' ? 'bg-emerald-400 animate-pulse' :
          status === 'error' ? 'bg-red-400' : 'bg-yellow-400 animate-pulse'
        }`}
      />
      {labels[status]}
    </span>
  )
}

/**
 * App — Phase 1 placeholder.
 *
 * Displays project identity and confirms that the Vite dev server is running.
 * The actual Agent Control Center UI will be built in later phases.
 */
export default function App() {
  const [backendStatus, setBackendStatus] = useState('checking')

  // Probe the FastAPI health endpoint on load.
  // VITE_API_BASE_URL is read from .env (defaults to '' so Vite proxy handles /api/* in dev).
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => {
        if (data?.status === 'ok') setBackendStatus('ok')
        else setBackendStatus('error')
      })
      .catch(() => setBackendStatus('error'))
  }, [])

  return (
    <div className="min-h-screen flex flex-col items-center justify-center relative overflow-hidden bg-[#0a0f1e] px-4">

      {/* ── Ambient glow blobs ── */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 50% at 20% 30%, rgba(37,99,235,0.18) 0%, transparent 70%),' +
            'radial-gradient(ellipse 50% 60% at 80% 70%, rgba(124,58,237,0.15) 0%, transparent 70%)',
        }}
      />

      {/* ── Main card ── */}
      <div
        className="relative z-10 w-full max-w-lg rounded-2xl border border-white/10 p-10 text-center shadow-2xl"
        style={{
          background: 'rgba(13,21,48,0.75)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
        }}
      >

        {/* Logo / Icon */}
        <div className="mx-auto mb-6 flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-violet-600 shadow-lg shadow-blue-500/30">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="white"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="size-8"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="2" y1="12" x2="22" y2="12" />
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
        </div>

        {/* Heading */}
        <h1 className="text-3xl font-bold tracking-tight text-white">
          AI Browser Agent
        </h1>
        <p className="mt-1 text-sm font-mono text-blue-400 tracking-widest">
          SIH260171
        </p>

        {/* Divider */}
        <div className="my-6 h-px w-full bg-gradient-to-r from-transparent via-white/15 to-transparent" />

        {/* Agent Control Center placeholder */}
        <div className="rounded-xl border border-white/8 bg-white/5 px-6 py-5">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-400 mb-2">
            Agent Control Center
          </p>
          <p className="text-xl font-semibold text-white/70 italic">
            Coming online…
          </p>
        </div>

        {/* Backend status */}
        <div className="mt-6 flex justify-center">
          <StatusBadge status={backendStatus} />
        </div>

        {/* Phase badge */}
        <p className="mt-8 text-xs text-slate-500">
          Phase 1 &mdash; Initialisation &bull; Browser automation &amp; AI agent not yet implemented
        </p>
      </div>

      {/* ── Bottom tech stack strip ── */}
      <div className="relative z-10 mt-8 flex flex-wrap justify-center gap-3 text-[11px] text-slate-500">
        {['React + Vite', 'Tailwind CSS', 'FastAPI', 'LangGraph (planned)', 'Gemini API (planned)', 'Playwright (planned)'].map((t) => (
          <span key={t} className="rounded-full border border-white/10 bg-white/5 px-3 py-1">
            {t}
          </span>
        ))}
      </div>

    </div>
  )
}
