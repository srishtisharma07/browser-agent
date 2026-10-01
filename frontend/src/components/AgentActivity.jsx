/**
 * AgentActivity — right-side panel showing agent lifecycle events.
 *
 * Phase 1: static placeholder events only.
 * In Phase 2 these will be replaced by real-time WebSocket messages
 * pushed from the LangGraph agent runner.
 */

/** @type {{ id: string, type: 'info'|'warn'|'error'|'success', message: string, time: string }[]} */
const PLACEHOLDER_EVENTS = [
  { id: 'evt-1', type: 'success', message: 'System initialized',          time: 'now'   },
  { id: 'evt-2', type: 'info',    message: 'Waiting for task',             time: 'now'   },
  { id: 'evt-3', type: 'warn',    message: 'Browser session not started',  time: 'now'   },
]

const TYPE_STYLES = {
  info:    { bar: 'bg-blue-500',    text: 'text-slate-300',  badge: 'text-blue-400'    },
  success: { bar: 'bg-emerald-500', text: 'text-slate-300',  badge: 'text-emerald-400' },
  warn:    { bar: 'bg-yellow-500',  text: 'text-slate-400',  badge: 'text-yellow-400'  },
  error:   { bar: 'bg-red-500',     text: 'text-slate-400',  badge: 'text-red-400'     },
}

export default function AgentActivity() {
  return (
    <aside className="flex flex-col w-64 shrink-0" aria-label="Agent activity">
      {/* Panel header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/8">
        <ActivityIcon />
        <span className="text-[11px] uppercase tracking-[0.15em] text-slate-500 font-medium">
          Agent Activity
        </span>
      </div>

      {/* Event list */}
      <ol className="flex flex-col gap-1 p-3 overflow-y-auto flex-1" role="log" aria-live="polite" aria-label="Agent events">
        {PLACEHOLDER_EVENTS.map((evt) => {
          const s = TYPE_STYLES[evt.type]
          return (
            <li
              key={evt.id}
              className="flex gap-2.5 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/6"
            >
              {/* Coloured left bar */}
              <span className={`w-0.5 self-stretch rounded-full shrink-0 ${s.bar}`} aria-hidden="true" />

              <div className="flex flex-col gap-0.5 min-w-0">
                <span className={`text-xs leading-snug ${s.text}`}>{evt.message}</span>
                <span className={`text-[10px] font-mono ${s.badge}`}>{evt.time}</span>
              </div>
            </li>
          )
        })}
      </ol>

      {/* Footer note */}
      <div className="px-4 py-3 border-t border-white/8">
        <p className="text-[10px] text-slate-700 leading-relaxed">
          Real-time events will stream here via WebSocket when the agent is active.
        </p>
      </div>
    </aside>
  )
}

/* ── Icon ────────────────────────────────────────────────────────── */

function ActivityIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5 text-slate-500" aria-hidden="true">
      <polyline points="1,10 4,6 7,8 10,4 13,7 15,5" />
    </svg>
  )
}
