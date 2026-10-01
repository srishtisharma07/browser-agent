/**
 * TaskStatus — bottom bar showing the current agent execution state.
 *
 * Phase 1: all fields are static placeholders.
 * These will be driven by real agent state in Phase 2.
 */
export default function TaskStatus() {
  const fields = [
    { id: 'status-field',    label: 'Status',            value: 'Idle',              accent: false },
    { id: 'objective-field', label: 'Current objective', value: 'Waiting for task',  accent: false },
    { id: 'progress-field',  label: 'Progress',          value: '0 %',               accent: false },
    { id: 'verify-field',    label: 'Verification',      value: 'Not started',       accent: false },
  ]

  return (
    <footer
      className="shrink-0 flex items-center gap-6 px-5 py-3 border-t border-white/8 bg-[#0b1120]/90 backdrop-blur-sm"
      aria-label="Task status"
    >
      {/* Status label */}
      <span className="text-[10px] uppercase tracking-[0.15em] text-slate-600 font-medium whitespace-nowrap">
        Task Status
      </span>

      <div className="w-px h-4 bg-white/8" aria-hidden="true" />

      {/* Fields */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5">
        {fields.map(({ id, label, value }) => (
          <StatusField key={id} id={id} label={label} value={value} />
        ))}
      </div>
    </footer>
  )
}

function StatusField({ id, label, value }) {
  return (
    <div id={id} className="flex items-center gap-1.5">
      <span className="text-[10px] text-slate-600">{label}:</span>
      <span className="text-[10px] font-medium text-slate-400">{value}</span>
    </div>
  )
}
