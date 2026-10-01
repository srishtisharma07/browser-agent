/**
 * TaskPanel — left sidebar where the user defines a high-level task for the agent.
 *
 * The "Run Agent" button is intentionally non-functional in Phase 1.
 * It will be wired to the LangGraph agent in a later phase.
 */
export default function TaskPanel() {
  return (
    <aside className="flex flex-col gap-4 w-72 shrink-0">
      {/* Section header */}
      <SectionHeader icon={<TaskIcon />} title="Task" />

      {/* Task input */}
      <div className="flex flex-col gap-2">
        <label htmlFor="task-input" className="text-[11px] uppercase tracking-[0.15em] text-slate-500 font-medium">
          High-level objective
        </label>
        <textarea
          id="task-input"
          rows={5}
          className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-3.5 py-3 text-sm text-slate-200
                     placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500/60
                     focus:border-blue-500/50 transition-colors"
          placeholder="Find software engineering internships matching my profile and prepare suitable applications…"
        />
      </div>

      {/* Run Agent button — disabled until agent engine exists */}
      <button
        id="run-agent-btn"
        disabled
        aria-disabled="true"
        className="flex items-center justify-center gap-2 w-full rounded-lg border border-white/10
                   bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-500 cursor-not-allowed
                   select-none"
        title="Agent engine not connected"
      >
        <RunIcon />
        Run Agent
      </button>

      {/* Disabled-state explanation */}
      <p className="text-[11px] text-slate-600 text-center leading-relaxed">
        Agent engine not connected.
        <br />Available in a later phase.
      </p>

      {/* Divider */}
      <div className="h-px bg-white/6 mt-auto" />

      {/* Quick config hints */}
      <div className="flex flex-col gap-2">
        <SectionHeader icon={<ConfigIcon />} title="Configuration" small />
        <ConfigRow label="Model" value="Gemini (planned)" />
        <ConfigRow label="Browser" value="Playwright (planned)" />
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

function ConfigIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5" aria-hidden="true">
      <circle cx="8" cy="8" r="2" />
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.2 3.2l1.4 1.4M11.4 11.4l1.4 1.4M3.2 12.8l1.4-1.4M11.4 4.6l1.4-1.4" />
    </svg>
  )
}
