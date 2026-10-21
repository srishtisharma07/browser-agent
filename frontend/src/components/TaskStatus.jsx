/**
 * TaskStatus — bottom bar showing the current agent execution state.
 * Connected to live agent state.
 */
export default function TaskStatus({
  taskStatus = 'idle',
  objective = '',
  cycleCount = 0,
  verificationStatus = 'not_started',
  taskId = null,
}) {
  const formatStatus = (s) => {
    switch (s) {
      case 'running':
        return { label: 'Running', dot: 'bg-blue-400 animate-pulse', text: 'text-blue-400 font-semibold' }
      case 'waiting_for_approval':
        return { label: 'Waiting for approval', dot: 'bg-amber-400 animate-pulse', text: 'text-amber-400 font-semibold' }
      case 'completed':
        return { label: 'Completed', dot: 'bg-emerald-400', text: 'text-emerald-400 font-semibold' }
      case 'failed':
        return { label: 'Failed', dot: 'bg-red-400', text: 'text-red-400 font-semibold' }
      case 'stopped':
        return { label: 'Stopped', dot: 'bg-slate-400', text: 'text-slate-400 font-semibold' }
      default:
        return { label: 'Idle', dot: 'bg-slate-500', text: 'text-slate-400 font-medium' }
    }
  }

  const formatVerification = (v) => {
    switch (v) {
      case 'response_success':
        return 'Response verified'
      case 'tool_success':
        return 'Tool success'
      case 'action_failed':
        return 'Action failed'
      default:
        return 'Not started'
    }
  }

  const statusConfig = formatStatus(taskStatus)

  const fields = [
    {
      id: 'status-field',
      label: 'Status',
      value: (
        <span className="flex items-center gap-1.5">
          <span className={`size-1.5 rounded-full ${statusConfig.dot}`} />
          <span className={statusConfig.text}>{statusConfig.label}</span>
        </span>
      ),
    },
    {
      id: 'objective-field',
      label: 'Current objective',
      value: objective ? (objective.length > 40 ? `${objective.slice(0, 40)}…` : objective) : 'Waiting for task',
    },
    {
      id: 'progress-field',
      label: 'Progress',
      value: taskStatus === 'completed' ? '100 %' : taskStatus === 'running' ? `Cycle ${cycleCount}` : '0 %',
    },
    {
      id: 'verify-field',
      label: 'Verification',
      value: formatVerification(verificationStatus),
    },
    ...(taskId ? [{ id: 'taskid-field', label: 'Task ID', value: taskId }] : []),
  ]

  return (
    <footer
      className="shrink-0 flex items-center gap-6 px-5 py-3 border-t border-white/8 bg-[#0b1120]/90 backdrop-blur-sm"
      aria-label="Task status"
    >
      <span className="text-[10px] uppercase tracking-[0.15em] text-slate-600 font-medium whitespace-nowrap">
        Task Status
      </span>

      <div className="w-px h-4 bg-white/8" aria-hidden="true" />

      <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5">
        {fields.map(({ id, label, value }) => (
          <div key={id} id={id} className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-600">{label}:</span>
            <span className="text-[10px] font-medium text-slate-300">{value}</span>
          </div>
        ))}
      </div>
    </footer>
  )
}
