import { useEffect, useState } from 'react'

import Header from './components/Header'
import TaskPanel from './components/TaskPanel'
import BrowserViewer from './components/BrowserViewer'
import AgentActivity from './components/AgentActivity'
import TaskStatus from './components/TaskStatus'

/**
 * App — AI Agent Control Center shell.
 *
 * Connected to FastAPI backend:
 *  - Health check probe
 *  - Task execution via POST /api/tasks
 *  - Real-time status & observation polling via GET /api/tasks/:id
 */
export default function App() {
  const [backendStatus, setBackendStatus] = useState('checking')
  const [currentTask, setCurrentTask] = useState(null)
  const [isStarting, setIsStarting] = useState(false)
  const [taskError, setTaskError] = useState(null)

  // VITE_API_BASE_URL is empty in dev so the Vite proxy forwards /api/* → :8000
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

  // 1. Backend health check probe
  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => {
        setBackendStatus(data?.status === 'ok' ? 'ok' : 'error')
      })
      .catch(() => setBackendStatus('error'))
  }, [API_BASE])

  // 2. Poll active task while running or waiting for approval
  useEffect(() => {
    if (!currentTask?.task_id) return
    const activeStatuses = ['running', 'waiting_for_approval']
    if (!activeStatuses.includes(currentTask.status)) return

    const intervalId = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/tasks/${currentTask.task_id}`)
        if (res.ok) {
          const updated = await res.json()
          setCurrentTask(updated)
        }
      } catch (err) {
        console.error('Task polling error:', err)
      }
    }, 1000)

    return () => clearInterval(intervalId)
  }, [currentTask?.task_id, currentTask?.status, API_BASE])

  // 3. Start task handler
  const handleStartTask = async (goal, profile = null) => {
    if (!goal || !goal.trim() || isStarting) return
    setIsStarting(true)
    setTaskError(null)

    try {
      const payload = { goal: goal.trim() }
      if (profile) {
        payload.profile = profile
      }

      const res = await fetch(`${API_BASE}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        let errDetail = `Server returned ${res.status}`
        try {
          const errData = await res.json()
          if (errData?.detail) errDetail = errData.detail
        } catch {
          // ignore json parse error
        }
        setTaskError(errDetail)
        return
      }

      const data = await res.json()
      setCurrentTask(data)
    } catch (err) {
      setTaskError(err.message || 'Failed to connect to backend server.')
    } finally {
      setIsStarting(false)
    }
  }

  // Derive active states
  const taskStatus = currentTask?.status || 'idle'
  const isRunning = isStarting || taskStatus === 'running' || taskStatus === 'waiting_for_approval'
  const taskId = currentTask?.task_id || null
  const objective = currentTask?.goal || ''
  const candidateProfile = currentTask?.candidate_profile || null
  const observations = currentTask?.observations || []
  const evaluations = currentTask?.evaluations || []
  const applicationDrafts = currentTask?.application_drafts || []
  const discoveredItems = currentTask?.discovered_items || []
  const currentStep = currentTask?.current_step || null
  const cycleCount = currentTask?.cycle_count || 0
  const verificationStatus = currentTask?.verification_status || 'not_started'
  const finalResponse = currentTask?.final_response || null

  // Collect all errors (network / validation + task execution errors)
  const allErrors = []
  if (taskError) allErrors.push(taskError)
  if (currentTask?.errors) allErrors.push(...currentTask.errors)

  // Find latest active URL from observations
  const activeUrl = observations
    .slice()
    .reverse()
    .find((o) => Boolean(o.url))?.url || null

  return (
    <div className="h-screen flex flex-col bg-[#080d1a] text-slate-200 overflow-hidden">
      <Header backendStatus={backendStatus} />

      {/* Middle: three-column work area */}
      <div className="flex flex-1 min-h-0 divide-x divide-white/8">
        {/* Left sidebar — task input */}
        <div className="flex flex-col p-4 overflow-y-auto">
          <TaskPanel
            onStartTask={handleStartTask}
            isRunning={isRunning}
            taskId={taskId}
            errors={allErrors}
          />
        </div>

        {/* Centre — browser viewport */}
        <div className="flex flex-1 flex-col min-w-0 p-3">
          <BrowserViewer
            activeUrl={activeUrl}
            taskStatus={taskStatus}
            finalResponse={finalResponse}
            applicationDrafts={applicationDrafts}
            currentStep={currentStep}
            candidateProfile={candidateProfile}
          />
        </div>

        {/* Right sidebar — agent activity log */}
        <div className="flex flex-col overflow-hidden">
          <AgentActivity
            observations={observations}
            evaluations={evaluations}
            applicationDrafts={applicationDrafts}
            discoveredItems={discoveredItems}
            candidateProfile={candidateProfile}
            errors={allErrors}
            taskStatus={taskStatus}
          />
        </div>
      </div>

      <TaskStatus
        taskStatus={taskStatus}
        objective={objective}
        cycleCount={cycleCount}
        verificationStatus={verificationStatus}
        taskId={taskId}
        candidateProfile={candidateProfile}
      />
    </div>
  )
}
