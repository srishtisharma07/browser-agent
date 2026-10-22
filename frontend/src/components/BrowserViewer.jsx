/**
 * BrowserViewer — large central panel displaying live browser session URL,
 * execution state, and autonomous research results.
 */
export default function BrowserViewer({
  activeUrl = null,
  taskStatus = 'idle',
  finalResponse = null,
  applicationDrafts = [],
  currentStep = null,
  candidateProfile = null,
}) {
  const displayUrl = activeUrl || (taskStatus === 'running' ? 'about:blank — navigating…' : 'about:blank — no active session')

  return (
    <section className="flex flex-col flex-1 min-w-0" aria-label="Browser viewer">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/8">
        <div className="flex items-center gap-2">
          <BrowserIcon />
          <span className="text-[11px] uppercase tracking-[0.15em] text-slate-500 font-medium">
            Live Browser
          </span>
          {taskStatus === 'running' && (
            <span className="ml-2 flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-[10px] font-medium text-blue-400">
              <span className="size-1.5 rounded-full bg-blue-400 animate-pulse" />
              Active Session
            </span>
          )}
          {candidateProfile && (
            <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-mono text-indigo-300 truncate max-w-xs">
              Profile: {candidateProfile.preferred_role || candidateProfile.education || 'Configured'}
            </span>
          )}
        </div>

        {/* Traffic-light dots */}
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <span className="size-2 rounded-full bg-white/10" />
          <span className="size-2 rounded-full bg-white/10" />
          <span className="size-2 rounded-full bg-white/10" />
        </div>
      </div>

      {/* URL bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/6 bg-white/[0.02]">
        <span className={activeUrl ? "text-emerald-400" : "text-slate-700"}>
          <LockIcon />
        </span>
        <span className={`text-[11px] font-mono truncate select-none ${activeUrl ? "text-slate-200" : "text-slate-700"}`}>
          {displayUrl}
        </span>
      </div>

      {/* Main viewport */}
      <div
        id="browser-viewport"
        className="flex-1 flex flex-col items-center justify-center gap-4 bg-[#080d1a] rounded-b-xl p-6 overflow-y-auto"
      >
        {finalResponse ? (
          <div className="flex flex-col gap-4 w-full max-w-xl rounded-xl border border-white/10 bg-white/[0.03] p-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/8 pb-3">
              <div className="flex items-center gap-2">
                <CheckCircleIcon />
                <h2 className="text-sm font-semibold text-white">Agent Response</h2>
              </div>
              {applicationDrafts.length > 0 && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                  {applicationDrafts.length} Draft{applicationDrafts.length > 1 ? 's' : ''} Prepared
                </span>
              )}
            </div>
            <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
              {finalResponse}
            </div>
            {applicationDrafts.length > 0 && (
              <div className="flex flex-col gap-2 pt-2 border-t border-white/6">
                <span className="text-[11px] uppercase tracking-wider text-slate-500 font-medium">Prepared Applications (Draft)</span>
                <div className="flex flex-col gap-1.5">
                  {applicationDrafts.map((draft, idx) => (
                    <div key={idx} className="flex items-center justify-between text-xs px-3 py-2 rounded bg-white/[0.02] border border-white/6">
                      <span className="font-medium text-slate-200 truncate">{draft.item_title}</span>
                      <span className="text-[10px] font-mono text-emerald-400 capitalize px-2 py-0.5 rounded bg-emerald-500/10">
                        {draft.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : taskStatus === 'running' ? (
          <div className="flex flex-col items-center gap-3 p-8 rounded-xl border border-blue-500/20 bg-blue-500/[0.02] max-w-sm text-center">
            <div className="size-10 rounded-full border-2 border-blue-500/30 border-t-blue-400 animate-spin flex items-center justify-center">
              <span className="size-2 rounded-full bg-blue-400" />
            </div>
            <p className="text-sm font-medium text-slate-200">Executing autonomous task</p>
            <p className="text-xs text-slate-400 leading-relaxed">
              {currentStep || 'Browser operations and decision cycles in progress…'}
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-col items-center gap-3 p-8 rounded-xl border border-dashed border-white/10 max-w-sm text-center">
              <ScreenIcon />
              <p className="text-sm font-medium text-slate-400">Browser session will appear here</p>
              <p className="text-xs text-slate-700 leading-relaxed">
                The Playwright-controlled Chromium window operates during active tasks.
                Observations and responses will render live in this panel.
              </p>
            </div>
            <p className="text-[10px] text-slate-700 font-mono">
              CONTROL CENTER CONNECTED · PLAYWRIGHT AUTOMATION READY
            </p>
          </>
        )}
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

function CheckCircleIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-4 text-emerald-400" aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <path d="M5.5 8l1.8 1.8L11 6" />
    </svg>
  )
}
