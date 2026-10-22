import { useState } from 'react'

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
  pendingApproval = null,
  onApprove,
  onReject,
  isDecidingApproval = false,
  isStopping = false,
  actionFeedback = null,
}) {
  const [rejectionReason, setRejectionReason] = useState('')
  const displayUrl = activeUrl || (taskStatus === 'running' ? 'about:blank — navigating…' : 'about:blank — no active session')

  const handleRejectClick = () => {
    if (onReject) {
      onReject(rejectionReason.trim() || undefined)
    }
  }

  const handleApproveClick = () => {
    if (onApprove) {
      onApprove()
    }
  }

  const isButtonsDisabled = isDecidingApproval || isStopping

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
          {taskStatus === 'waiting_for_approval' && (
            <span className="ml-2 flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-[10px] font-medium text-amber-300">
              <span className="size-1.5 rounded-full bg-amber-400 animate-pulse" />
              Approval Required
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
        {/* VIEW 1: Final Response */}
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
        ) : taskStatus === 'waiting_for_approval' ? (
          /* VIEW 2: Interactive Human-in-the-Loop Review Panel */
          <div
            id="approval-review-panel"
            className="flex flex-col gap-5 w-full max-w-xl rounded-xl border border-amber-500/30 bg-[#0c1322]/95 p-6 shadow-2xl backdrop-blur-sm"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-amber-500/20 pb-3">
              <div className="flex items-center gap-2">
                <ShieldAlertIcon />
                <h2 className="text-sm font-semibold text-amber-200">
                  Human Approval Required
                </h2>
              </div>
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/30 text-amber-300">
                Gate: Active Policy
              </span>
            </div>

            {/* Description note */}
            <p className="text-xs text-slate-300 leading-relaxed">
              The agent has paused execution before running a consequential action. Review the proposed action and exact arguments below. Approval resumes this exact action; rejection stops the agent safely.
            </p>

            {/* Structured details table */}
            <div className="flex flex-col gap-2 text-xs rounded-lg border border-white/8 bg-white/[0.02] p-3.5">
              <div className="flex items-start justify-between gap-4">
                <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold w-20">
                  Action
                </span>
                <span className="font-mono text-amber-300 font-semibold flex-1 text-right break-words">
                  {pendingApproval?.action || 'Unknown Action'}
                </span>
              </div>

              {pendingApproval?.target && (
                <div className="flex items-start justify-between gap-4 pt-1.5 border-t border-white/6">
                  <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold w-20">
                    Target
                  </span>
                  <span className="font-mono text-slate-200 flex-1 text-right break-all">
                    {pendingApproval.target}
                  </span>
                </div>
              )}

              {pendingApproval?.description && (
                <div className="flex items-start justify-between gap-4 pt-1.5 border-t border-white/6">
                  <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold w-20">
                    Details
                  </span>
                  <span className="text-slate-300 flex-1 text-right">
                    {pendingApproval.description}
                  </span>
                </div>
              )}
            </div>

            {/* Saved Arguments viewer */}
            {pendingApproval?.arguments && Object.keys(pendingApproval.arguments).length > 0 && (
              <div className="flex flex-col gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">
                  Saved Action Arguments
                </span>
                <pre className="text-[11px] font-mono p-3 rounded-lg border border-white/8 bg-black/40 text-slate-300 overflow-x-auto max-h-32">
                  {JSON.stringify(pendingApproval.arguments, null, 2)}
                </pre>
              </div>
            )}

            {/* Rejection reason write-in */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="rejection-reason-input" className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">
                Rejection reason (optional)
              </label>
              <input
                id="rejection-reason-input"
                type="text"
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                disabled={isButtonsDisabled}
                placeholder="e.g. Unverified recipient address or incorrect parameters…"
                className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-amber-500/50"
              />
            </div>

            {/* Action feedback */}
            {actionFeedback && (
              <div
                id="viewer-feedback-banner"
                className={`rounded-lg border p-2.5 text-xs ${
                  actionFeedback.type === 'success'
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                    : 'border-red-500/40 bg-red-500/10 text-red-300'
                }`}
              >
                {actionFeedback.message}
              </div>
            )}

            {/* Decision Controls */}
            <div className="flex items-center gap-3 pt-2">
              <button
                id="approve-action-btn"
                type="button"
                onClick={handleApproveClick}
                disabled={isButtonsDisabled}
                className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2.5 px-4 text-xs font-semibold select-none transition-all cursor-pointer ${
                  isButtonsDisabled
                    ? 'bg-emerald-600/30 border border-emerald-500/30 text-emerald-400/50 cursor-not-allowed'
                    : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/20 active:scale-[0.98]'
                }`}
              >
                <CheckIcon />
                <span>{isDecidingApproval ? 'Resuming…' : 'Approve & Resume'}</span>
              </button>

              <button
                id="reject-action-btn"
                type="button"
                onClick={handleRejectClick}
                disabled={isButtonsDisabled}
                className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2.5 px-4 text-xs font-semibold select-none transition-all cursor-pointer border ${
                  isButtonsDisabled
                    ? 'border-red-500/20 bg-red-500/10 text-red-400/50 cursor-not-allowed'
                    : 'border-red-500/50 bg-red-500/10 hover:bg-red-500/20 text-red-300 shadow-lg shadow-red-500/10 active:scale-[0.98]'
                }`}
              >
                <XIcon />
                <span>{isDecidingApproval ? 'Rejecting…' : 'Reject Action'}</span>
              </button>
            </div>
          </div>
        ) : taskStatus === 'running' ? (
          /* VIEW 3: Running spinner */
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
          /* VIEW 4: Idle session */
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

function ShieldAlertIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-4 text-amber-400" aria-hidden="true">
      <path d="M8 1.5l5 2v4.5c0 3.5-2.5 6-5 7-2.5-1-5-3.5-5-7V3.5l5-2z" />
      <line x1="8" y1="5.5" x2="8" y2="8.5" />
      <circle cx="8" cy="10.5" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5 text-white" aria-hidden="true">
      <polyline points="3 8 6.5 11.5 13 5" />
    </svg>
  )
}

function XIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5 text-red-400" aria-hidden="true">
      <line x1="4" y1="4" x2="12" y2="12" />
      <line x1="12" y1="4" x2="4" y2="12" />
    </svg>
  )
}

