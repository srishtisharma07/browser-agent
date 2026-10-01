/**
 * BrowserViewer — large central panel that will later display
 * the live Playwright browser session via a screenshot/video stream.
 *
 * Phase 1: empty-state placeholder only.
 */
export default function BrowserViewer() {
  return (
    <section className="flex flex-col flex-1 min-w-0" aria-label="Browser viewer">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/8">
        <div className="flex items-center gap-2">
          <BrowserIcon />
          <span className="text-[11px] uppercase tracking-[0.15em] text-slate-500 font-medium">
            Live Browser
          </span>
        </div>

        {/* Traffic-light dots — decorative, signals "browser chrome" */}
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <span className="size-2 rounded-full bg-white/10" />
          <span className="size-2 rounded-full bg-white/10" />
          <span className="size-2 rounded-full bg-white/10" />
        </div>
      </div>

      {/* URL bar — placeholder */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/6 bg-white/[0.02]">
        <span className="text-slate-700">
          <LockIcon />
        </span>
        <span className="text-[11px] font-mono text-slate-700 truncate select-none">
          about:blank — no active session
        </span>
      </div>

      {/* Main viewport */}
      <div
        id="browser-viewport"
        className="flex-1 flex flex-col items-center justify-center gap-4 bg-[#080d1a] rounded-b-xl"
      >
        {/* Dashed border placeholder */}
        <div className="flex flex-col items-center gap-3 p-8 rounded-xl border border-dashed border-white/10 max-w-sm text-center">
          <ScreenIcon />
          <p className="text-sm font-medium text-slate-400">Browser session will appear here</p>
          <p className="text-xs text-slate-700 leading-relaxed">
            The Playwright-controlled Chromium window will be
            streamed into this panel when the agent is running.
          </p>
        </div>

        {/* Phase label */}
        <p className="text-[10px] text-slate-700 font-mono">
          PLAYWRIGHT NOT CONNECTED · PHASE 1
        </p>
      </div>
    </section>
  )
}

/* ── Icons ───────────────────────────────────────────────────────── */

function BrowserIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5 text-slate-500" aria-hidden="true">
      <rect x="1" y="2" width="14" height="12" rx="2" />
      <line x1="1" y1="6" x2="15" y2="6" />
      <circle cx="4" cy="4" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="7" cy="4" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  )
}

function LockIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3" aria-hidden="true">
      <rect x="3" y="7" width="10" height="8" rx="1.5" />
      <path d="M5 7V5a3 3 0 0 1 6 0v2" />
    </svg>
  )
}

function ScreenIcon() {
  return (
    <svg viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.2"
         strokeLinecap="round" strokeLinejoin="round" className="size-10 text-slate-700" aria-hidden="true">
      <rect x="2" y="5" width="36" height="24" rx="3" />
      <line x1="14" y1="34" x2="26" y2="34" />
      <line x1="20" y1="29" x2="20" y2="34" />
      <line x1="8" y1="12" x2="32" y2="12" strokeDasharray="2 2" />
      <line x1="8" y1="18" x2="28" y2="18" strokeDasharray="2 2" />
      <line x1="8" y1="24" x2="22" y2="24" strokeDasharray="2 2" />
    </svg>
  )
}
