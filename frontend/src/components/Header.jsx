/**
 * Header — top bar with product identity and live backend status.
 * The `backendStatus` prop is controlled by App and comes from a real fetch.
 */
export default function Header({ backendStatus }) {
  const indicator = {
    checking: { dot: 'bg-yellow-400 animate-pulse', text: 'text-yellow-300', label: 'Checking…' },
    ok:       { dot: 'bg-emerald-400 animate-pulse', text: 'text-emerald-300', label: 'Backend: Connected' },
    error:    { dot: 'bg-red-500', text: 'text-red-400', label: 'Backend: Disconnected' },
  }[backendStatus] ?? { dot: 'bg-slate-500', text: 'text-slate-400', label: 'Unknown' }

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-white/8 bg-[#0b1120]/90 backdrop-blur-sm shrink-0">
      {/* Left — product identity */}
      <div className="flex items-center gap-3">
        {/* Icon */}
        <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 shadow shadow-blue-500/30">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.8"
               strokeLinecap="round" strokeLinejoin="round" className="size-4" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="2" y1="12" x2="22" y2="12" />
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
        </div>

        <div>
          <h1 className="text-sm font-semibold text-white leading-none">AI Browser Agent</h1>
          <p className="text-[10px] font-mono text-blue-400 tracking-widest mt-0.5">SIH260171</p>
        </div>
      </div>

      {/* Right — backend status pill */}
      <div
        id="backend-status-indicator"
        className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5"
        aria-live="polite"
        aria-label={`Backend status: ${indicator.label}`}
      >
        <span className={`size-1.5 rounded-full ${indicator.dot}`} />
        <span className={`text-xs font-medium ${indicator.text}`}>{indicator.label}</span>
      </div>
    </header>
  )
}
