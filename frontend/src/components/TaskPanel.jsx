import { useState } from 'react'

/**
 * TaskPanel — left sidebar where the user defines a high-level task and optional candidate profile.
 * Connected to FastAPI task execution API.
 */
export default function TaskPanel({ onStartTask, isRunning, taskId, errors = [] }) {
  const [goal, setGoal] = useState('')
  const [showProfile, setShowProfile] = useState(false)

  // Candidate Profile fields
  const [preferredRole, setPreferredRole] = useState('')
  const [education, setEducation] = useState('')
  const [graduationYear, setGraduationYear] = useState('')
  const [skills, setSkills] = useState('')
  const [locations, setLocations] = useState('')
  const [constraints, setConstraints] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!goal.trim() || isRunning) return

    let profile = null
    const hasProfileData = preferredRole.trim() || education.trim() || graduationYear.trim() || skills.trim() || locations.trim() || constraints.trim()

    if (hasProfileData) {
      profile = {
        preferred_role: preferredRole.trim() || undefined,
        education: education.trim() || undefined,
        graduation_year: graduationYear.trim() ? parseInt(graduationYear.trim(), 10) : undefined,
        technical_skills: skills ? skills.split(',').map((s) => s.trim()).filter(Boolean) : [],
        location_preferences: locations ? locations.split(',').map((s) => s.trim()).filter(Boolean) : [],
        internship_constraints: constraints ? constraints.split(',').map((s) => s.trim()).filter(Boolean) : [],
      }
    }

    onStartTask(goal.trim(), profile)
  }

  const hasErrors = errors && errors.length > 0
  const isProfileConfigured = Boolean(preferredRole || education || graduationYear || skills || locations || constraints)

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

      {/* Task input form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <div className="flex flex-col gap-2">
          <label htmlFor="task-input" className="text-[11px] uppercase tracking-[0.15em] text-slate-500 font-medium">
            High-level objective
          </label>
          <textarea
            id="task-input"
            rows={4}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            disabled={isRunning}
            className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-slate-200
                       placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500/60
                       focus:border-blue-500/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder="Find software engineering internships matching my candidate profile and evaluate suitability…"
          />
        </div>

        {/* Candidate Profile Accordion Toggle */}
        <div className="flex flex-col rounded-lg border border-white/8 bg-white/[0.02] overflow-hidden">
          <button
            type="button"
            id="toggle-profile-btn"
            onClick={() => setShowProfile(!showProfile)}
            className="flex items-center justify-between px-3 py-2 text-xs font-medium text-slate-300 hover:text-white hover:bg-white/[0.03] transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-1.5">
              <ProfileIcon />
              <span>Candidate Profile</span>
              {isProfileConfigured && (
                <span className="size-1.5 rounded-full bg-blue-400 ml-0.5" title="Profile configured" />
              )}
            </div>
            <span className="text-slate-500 text-[10px]">{showProfile ? '▲ Hide' : '▼ Expand'}</span>
          </button>

          {showProfile && (
            <div className="flex flex-col gap-2.5 p-3 border-t border-white/6 bg-white/[0.01]">
              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-slate-400">Preferred Role</label>
                <input
                  type="text"
                  id="profile-role"
                  value={preferredRole}
                  onChange={(e) => setPreferredRole(e.target.value)}
                  disabled={isRunning}
                  placeholder="e.g. Software Engineering Intern"
                  className="rounded border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
                />
              </div>

              <div className="flex gap-2">
                <div className="flex flex-col gap-1 flex-1">
                  <label className="text-[10px] text-slate-400">Education</label>
                  <input
                    type="text"
                    id="profile-education"
                    value={education}
                    onChange={(e) => setEducation(e.target.value)}
                    disabled={isRunning}
                    placeholder="e.g. B.S. in CS"
                    className="rounded border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
                  />
                </div>
                <div className="flex flex-col gap-1 w-20">
                  <label className="text-[10px] text-slate-400">Grad Year</label>
                  <input
                    type="number"
                    id="profile-grad-year"
                    value={graduationYear}
                    onChange={(e) => setGraduationYear(e.target.value)}
                    disabled={isRunning}
                    placeholder="2026"
                    className="rounded border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-slate-400">Technical Skills (comma-separated)</label>
                <input
                  type="text"
                  id="profile-skills"
                  value={skills}
                  onChange={(e) => setSkills(e.target.value)}
                  disabled={isRunning}
                  placeholder="Python, React, FastAPI, Docker"
                  className="rounded border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-slate-400">Location Preferences</label>
                <input
                  type="text"
                  id="profile-locations"
                  value={locations}
                  onChange={(e) => setLocations(e.target.value)}
                  disabled={isRunning}
                  placeholder="Remote, San Francisco, Bangalore"
                  className="rounded border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-slate-400">Internship Constraints</label>
                <input
                  type="text"
                  id="profile-constraints"
                  value={constraints}
                  onChange={(e) => setConstraints(e.target.value)}
                  disabled={isRunning}
                  placeholder="Summer 2026, Paid only"
                  className="rounded border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
                />
              </div>
            </div>
          )}
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

function ProfileIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round" className="size-3.5 text-blue-400" aria-hidden="true">
      <path d="M8 8a3 3 0 100-6 3 3 0 000 6zM2 14a6 6 0 0112 0" />
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
