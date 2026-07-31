import { useEffect, useState } from 'react'
import { Box, Calendar, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getAlerts } from '../api'
import { SeverityPill } from '../components/SeverityPill'
import type { Alert } from '../types'

const FILTERS = ['All', 'High', 'Medium', 'Low'] as const

function alertIcon(type: string) {
  const t = type.toLowerCase()
  if (t.includes('stock') || t.includes('sku')) return Box
  if (t.includes('expir')) return Calendar
  return AlertTriangle
}

const BORDER: Record<string, string> = {
  High: 'border-l-red-500',
  Medium: 'border-l-amber-500',
  Low: 'border-l-slate-400',
}

export function AlertsPage() {
  const { user } = useAuth()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('All')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    getAlerts(user.token)
      .then((r) => setAlerts(r.alerts))
      .catch((e) => setError(e.message))
  }, [user])

  const filtered = filter === 'All' ? alerts : alerts.filter((a) => a.severity === filter)

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-900">Alerts</h1>
        <p className="text-sm text-slate-500">Active inventory and audit alerts in your scope</p>
      </div>

      {error && <p className="text-red-600">{error}</p>}

      <div className="mb-4 flex gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
              filter === f
                ? 'bg-indigo-600 text-white'
                : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-indigo-300'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl bg-white py-16 shadow-sm ring-1 ring-slate-200/60">
          <CheckCircle2 className="mb-3 h-12 w-12 text-green-400" />
          <p className="text-lg font-medium text-slate-900">No active alerts</p>
          <p className="text-sm text-slate-500">Inventory looks healthy in your region</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((alert, i) => {
            const Icon = alertIcon(alert.type)
            return (
              <div
                key={i}
                className={`flex items-start gap-4 rounded-xl border-l-4 bg-white p-4 shadow-sm ring-1 ring-slate-200/60 ${BORDER[alert.severity] ?? BORDER.Low}`}
              >
                <div className="rounded-lg bg-slate-50 p-2">
                  <Icon className="h-5 w-5 text-slate-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{alert.type}</p>
                  <p className="mt-0.5 text-sm text-slate-800">{alert.message}</p>
                </div>
                <SeverityPill severity={alert.severity} />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
