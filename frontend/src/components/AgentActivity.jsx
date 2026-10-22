import { useState } from 'react'

/**
 * AgentActivity — right-side panel showing actual agent observations,
 * candidate profile summary, discovered listings, evaluations, and prepared drafts.
 */
export default function AgentActivity({
  observations = [],
  evaluations = [],
  applicationDrafts = [],
  discoveredItems = [],
  candidateProfile = null,
  errors = [],
  taskStatus = 'idle',
}) {
  const [activeTab, setActiveTab] = useState('activity') // 'activity' | 'evaluations' | 'listings' | 'drafts'

  const hasErrors = errors && errors.length > 0

  const getSourceStyle = (source = '') => {
    switch (source) {
      case 'open_url':
        return { bar: 'bg-blue-500', badge: 'text-blue-400 bg-blue-500/10' }
      case 'get_page_text':
      case 'get_links':
        return { bar: 'bg-cyan-500', badge: 'text-cyan-400 bg-cyan-500/10' }
      case 'evaluate_item':
        return { bar: 'bg-indigo-500', badge: 'text-indigo-400 bg-indigo-500/10' }
      case 'prepare_application':
        return { bar: 'bg-emerald-500', badge: 'text-emerald-400 bg-emerald-500/10' }
      case 'loop_protection':
      case 'error':
        return { bar: 'bg-red-500', badge: 'text-red-400 bg-red-500/10' }
      default:
        return { bar: 'bg-slate-500', badge: 'text-slate-400 bg-slate-500/10' }
    }
  }

  const formatTimestamp = (ts) => {
    if (!ts) return 'now'
    try {
      const d = new Date(ts)
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return ts
    }
  }

  return (
    <aside className="flex flex-col w-72 shrink-0 border-l border-white/8 bg-[#080d1a]" aria-label="Agent activity">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/8">
        <div className="flex items-center gap-2">
          <ActivityIcon />
          <span className="text-[11px] uppercase tracking-[0.15em] text-slate-500 font-medium">
            Agent Feed
          </span>
        </div>
        {taskStatus === 'running' && (
          <span className="flex items-center gap-1 text-[10px] text-blue-400">
            <span className="size-1.5 rounded-full bg-blue-400 animate-pulse" />
            Live
          </span>
        )}
      </div>

      {/* Candidate Profile Summary Header (if present) */}
      {candidateProfile && (
        <div className="px-3 py-2 border-b border-white/6 bg-blue-500/[0.04]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase tracking-wider text-blue-400 font-medium">
              Target Candidate Profile
            </span>
            {candidateProfile.graduation_year && (
              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-blue-500/10 text-blue-300">
                Class of {candidateProfile.graduation_year}
              </span>
            )}
          </div>
          <p className="text-xs font-semibold text-slate-200 truncate">
            {candidateProfile.preferred_role || candidateProfile.education || 'Configured Profile'}
          </p>
          {candidateProfile.technical_skills && candidateProfile.technical_skills.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {candidateProfile.technical_skills.slice(0, 4).map((skill, sIdx) => (
                <span key={sIdx} className="text-[9px] px-1 rounded bg-white/5 text-slate-400">
                  {skill}
                </span>
              ))}
              {candidateProfile.technical_skills.length > 4 && (
                <span className="text-[9px] text-slate-500">
                  +{candidateProfile.technical_skills.length - 4} more
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center border-b border-white/6 px-1 bg-white/[0.01] overflow-x-auto">
        <TabButton
          active={activeTab === 'activity'}
          onClick={() => setActiveTab('activity')}
          label="Activity"
          count={observations.length}
        />
        <TabButton
          active={activeTab === 'evaluations'}
          onClick={() => setActiveTab('evaluations')}
          label="Evaluations"
          count={evaluations.length}
        />
        <TabButton
          active={activeTab === 'listings'}
          onClick={() => setActiveTab('listings')}
          label="Listings"
          count={discoveredItems.length}
        />
        <TabButton
          active={activeTab === 'drafts'}
          onClick={() => setActiveTab('drafts')}
          label="Drafts"
          count={applicationDrafts.length}
        />
      </div>

      {/* Feed Area */}
      <div className="flex flex-col flex-1 p-3 overflow-y-auto gap-2">
        {/* Error notice if present */}
        {hasErrors && (
          <div className="p-2.5 rounded-lg border border-red-500/30 bg-red-500/10 text-xs text-red-300">
            <div className="font-medium text-red-200 mb-0.5">Execution Alert</div>
            <p className="text-[11px] text-red-300/80 break-words">{errors[0]}</p>
          </div>
        )}

        {/* Tab Content: Activity */}
        {activeTab === 'activity' && (
          <ol className="flex flex-col gap-1.5" role="log" aria-live="polite" aria-label="Agent observations">
            {observations.length === 0 ? (
              <li className="text-center py-8 text-xs text-slate-600">
                No observations yet.
                <br />Activity will appear as the agent acts.
              </li>
            ) : (
              observations.map((obs, idx) => {
                const s = getSourceStyle(obs.source)
                return (
                  <li
                    key={idx}
                    className="flex gap-2.5 rounded-lg px-3 py-2 bg-white/[0.03] border border-white/6"
                  >
                    <span className={`w-0.5 self-stretch rounded-full shrink-0 ${s.bar}`} aria-hidden="true" />
                    <div className="flex flex-col gap-1 min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1">
                        <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded ${s.badge}`}>
                          {obs.source || 'observation'}
                        </span>
                        <span className="text-[9px] font-mono text-slate-600">
                          {formatTimestamp(obs.timestamp)}
                        </span>
                      </div>
                      <span className="text-xs text-slate-300 leading-snug break-words">
                        {obs.summary}
                      </span>
                      {obs.url && (
                        <span className="text-[10px] font-mono text-blue-400/80 truncate">
                          {obs.url}
                        </span>
                      )}
                    </div>
                  </li>
                )
              })
            )}
          </ol>
        )}

        {/* Tab Content: Evaluations */}
        {activeTab === 'evaluations' && (
          <div className="flex flex-col gap-2">
            {evaluations.length === 0 ? (
              <p className="text-center py-8 text-xs text-slate-600">
                No evaluations recorded yet.
              </p>
            ) : (
              evaluations.map((ev, idx) => {
                const isSelected = ev.decision === 'selected'
                const reasonLower = (ev.reason || '').toLowerCase()
                const isMissingInfo = reasonLower.includes('missing') || reasonLower.includes('unspecified') || reasonLower.includes('not provided')

                return (
                  <div
                    key={idx}
                    className="flex flex-col gap-1.5 rounded-lg p-2.5 bg-white/[0.03] border border-white/6"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-medium text-slate-200 line-clamp-2">
                        {ev.item}
                      </span>
                      <div className="flex items-center gap-1 shrink-0">
                        {isMissingInfo && !isSelected && (
                          <span className="text-[9px] font-mono uppercase px-1 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                            Missing Info
                          </span>
                        )}
                        <span
                          className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded font-medium ${
                            isSelected
                              ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                              : 'bg-rose-500/10 border border-rose-500/20 text-rose-400'
                          }`}
                        >
                          {ev.decision}
                        </span>
                      </div>
                    </div>
                    {ev.url && (
                      <a
                        href={ev.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[10px] font-mono text-blue-400/80 hover:underline truncate"
                      >
                        {ev.url}
                      </a>
                    )}
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      {ev.reason}
                    </p>
                  </div>
                )
              })
            )}
          </div>
        )}

        {/* Tab Content: Discovered Listings */}
        {activeTab === 'listings' && (
          <div className="flex flex-col gap-2">
            {discoveredItems.length === 0 ? (
              <p className="text-center py-8 text-xs text-slate-600">
                No internship listings discovered yet.
              </p>
            ) : (
              discoveredItems.map((item, idx) => (
                <div
                  key={idx}
                  className="flex flex-col gap-1 rounded-lg p-2.5 bg-white/[0.03] border border-white/6"
                >
                  <span className="text-xs font-medium text-slate-200 truncate">
                    {item.title}
                  </span>
                  {item.url && (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[10px] font-mono text-blue-400/80 hover:underline truncate"
                    >
                      {item.url}
                    </a>
                  )}
                  <span className="text-[9px] text-slate-500 uppercase tracking-wider font-mono">
                    Status: {item.status || 'Discovered'}
                  </span>
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab Content: Drafts */}
        {activeTab === 'drafts' && (
          <div className="flex flex-col gap-2">
            {applicationDrafts.length === 0 ? (
              <p className="text-center py-8 text-xs text-slate-600">
                No application drafts prepared yet.
              </p>
            ) : (
              applicationDrafts.map((draft, idx) => (
                <div
                  key={idx}
                  className="flex flex-col gap-2 rounded-lg p-3 bg-white/[0.03] border border-white/6"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-slate-200 truncate">
                      {draft.item_title}
                    </span>
                    <span className="text-[9px] font-mono capitalize px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      {draft.status}
                    </span>
                  </div>
                  {draft.matched_requirements && draft.matched_requirements.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {draft.matched_requirements.map((req, rIdx) => (
                        <span key={rIdx} className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-300">
                          ✓ {req}
                        </span>
                      ))}
                    </div>
                  )}
                  {draft.notes && (
                    <p className="text-[11px] text-slate-400 leading-snug">
                      {draft.notes}
                    </p>
                  )}
                  <div className="text-[9px] text-slate-600 font-mono pt-1 border-t border-white/4">
                    Draft prepared · Safety: Unsubmitted
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Footer note */}
      <div className="px-4 py-2 border-t border-white/8 bg-white/[0.01]">
        <p className="text-[10px] text-slate-600 leading-relaxed">
          {observations.length} observation{observations.length === 1 ? '' : 's'} · {evaluations.length} evaluation{evaluations.length === 1 ? '' : 's'}
        </p>
      </div>
    </aside>
  )
}

function TabButton({ active, onClick, label, count = 0 }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1 px-2.5 py-2 text-[11px] font-medium border-b-2 transition-colors cursor-pointer whitespace-nowrap ${
        active
          ? 'border-blue-500 text-white'
          : 'border-transparent text-slate-500 hover:text-slate-300'
      }`}
    >
      <span>{label}</span>
      {count > 0 && (
        <span className="text-[9px] font-mono px-1 rounded bg-white/10 text-slate-300">
          {count}
        </span>
      )}
    </button>
  )
}

function ActivityIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5 text-slate-500" aria-hidden="true">
      <polyline points="1,10 4,6 7,8 10,4 13,7 15,5" />
    </svg>
  )
}
