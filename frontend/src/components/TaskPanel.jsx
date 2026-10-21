import { useState } from 'react'

/**
 * TaskPanel — left sidebar where the user defines a high-level task for the agent.
 * Connected to FastAPI task execution API.
 */
export default function TaskPanel({ onStartTask, isRunning, taskId, errors = [] }) {
  const [goal, setGoal] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!goal.trim() || isRunning) return
    onStartTask(goal.trim())
  }

  const hasErrors = errors && errors.length > 0

  return (
    <aside className="flex flex-col gap-4 w-72 shrink-0">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <SectionHeader icon={<TaskIcon />} title="Task" />
        {taskId && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400">
            {taskId}
          </span>
        )}
      </div>

      {/* Task input */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <div className="flex flex-col gap-2">
          <label htmlFor="task-input" className="text-[11px] uppercase tracking-[0.15em] text-slate-500 font-medium">
            High-level objective
          </label>
          <textarea
            id="task-input"
            rows={5}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            disabled={isRunning}
            className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-3.5 py-3 text-sm text-slate-200
                       placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500/60
                       focus:border-blue-500/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder="Find software engineering internships matching my profile and prepare suitable applications…"
          />
        </div>

        {/* Action button */}
        <button
          id="run-agent-btn"
          type="submit"
          disabled={isRunning || !goal.trim()}
          aria-disabled={isRunning || !goal.trim()}
          aria-busy={isRunning}
          className={`flex items-center justify-center gap-2 w-full rounded-lg px-4 py-2.5 text-sm font-medium select-none transition-all ${
            isRunning
              ? 'bg-blue-600/30 border border-blue-500/40 text-blue-300 cursor-wait'
              : !goal.trim()
              ? 'border border-white/10 bg-white/5 text-slate-500 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20 active:scale-[0.98] cursor-pointer'
          }`}
          title={isRunning ? 'Task is executing...' : 'Start autonomous research task'}
        >
          {isRunning ? (
            <>
              <SpinnerIcon />
              <span>Running Agent…</span>
            </>
          ) : (
            <>
              <RunIcon />
              <span>Run Agent</span>
            </>
          )}
        </button>
      </form>

      {/* Actionable error notice */}
      {hasErrors && (
        <div
          id="task-error-banner"
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300 leading-relaxed flex flex-col gap-1"
        >
          <div className="flex items-center gap-1.5 font-medium text-red-200">
            <AlertIcon />
            <span>Execution Notice</span>
          </div>
          <p className="text-[11px] text-red-300/90 break-words">{errors[0]}</p>
        </div>
      )}

      {/* Status explanation */}
      {isRunning ? (
        <p className="text-[11px] text-blue-400/80 text-center leading-relaxed">
          Agent running autonomously.
          <br />Polling status and observations…
        </p>
      ) : (
        <p className="text-[11px] text-slate-600 text-center leading-relaxed">
          Enter an objective above to trigger
          <br />autonomous browser research.
        </p>
      )}

      {/* Divider */}
      <div className="h-px bg-white/6 mt-auto" />

      {/* Quick config hints */}
      <div className="flex flex-col gap-2">
        <SectionHeader icon={<ConfigIcon />} title="Configuration" small />
        <ConfigRow label="Model" value="Gemini (gemini-2.5-flash)" />
        <ConfigRow label="Browser" value="Playwright (Chromium)" />
        <ConfigRow label="Mode" value="Autonomous" />
      </div>
    </aside>
  )
}

/* ── Sub-components ──────────────────────────────────────────────── */

function SectionHeader({ icon, title, small = false }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-slate-500">{icon}</span>
      <span className={`${small ? 'text-[10px]' : 'text-[11px]'} uppercase tracking-[0.15em] text-slate-500 font-medium`}>
        {title}
      </span>
    </div>
  )
}

function ConfigRow({ label, value }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-600">{label}</span>
      <span className="text-slate-500 font-mono">{value}</span>
    </div>
  )
}

/* ── Icons ───────────────────────────────────────────────────────── */

function TaskIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5" aria-hidden="true">
      <path d="M2 4h12M2 8h8M2 12h5" />
    </svg>
  )
}

function RunIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5" aria-hidden="true">
      <polygon points="4,2 14,8 4,14" strokeLinejoin="round" />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg className="animate-spin size-3.5 text-blue-300" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  )
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5 text-red-400" aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <line x1="8" y1="5" x2="8" y2="9" />
      <circle cx="8" cy="12" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

function ConfigIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5" aria-hidden="true">
      <circle cx="8" cy="8" r="2" />
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.2 3.2l1.4 1.4M11.4 11.4l1.4 1.4M3.2 12.8l1.4-1.4M11.4 4.6l1.4-1.4" />
    </svg>
  )
}
