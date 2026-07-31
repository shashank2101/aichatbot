import { useEffect, useState } from 'react'
import { MessageSquare, Clock, Zap, ShieldAlert, ThumbsUp, BarChart2 } from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { useAuth } from '../context/AuthContext'
import { getObservability } from '../api'
import { StatCard } from '../components/StatCard'
import type { ObservabilityData } from '../types'

export function ObservabilityPage() {
  const { user } = useAuth()
  const [data, setData] = useState<ObservabilityData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    getObservability(user.token)
      .then(setData)
      .catch((e) => setError(e.message))
  }, [user])

  if (user?.role !== 'admin') {
    return (
      <div className="flex h-full items-center justify-center p-6 text-slate-500">
        Admin access required.
      </div>
    )
  }

  if (error) return <div className="p-6 text-red-600">{error}</div>
  if (!data) return <div className="flex items-center justify-center p-12 text-slate-400">Loading…</div>

  const faqChart = data.top_questions.map((q) => ({
    question: q.question.length > 40 ? q.question.slice(0, 40) + '…' : q.question,
    count: q.c,
  }))

  const thumbsRatio =
    data.thumbs_up + data.thumbs_down > 0
      ? `${data.thumbs_up}/${data.thumbs_down}`
      : '—'

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Observability</h1>
        <p className="text-sm text-slate-500">AI pipeline analytics, failures, and security events</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Total Questions" value={data.total_questions} icon={MessageSquare} />
        <StatCard label="Avg Latency" value={`${data.avg_latency_ms} ms`} icon={Clock} />
        <StatCard label="Avg Tokens" value={data.avg_tokens_used} icon={Zap} />
        <StatCard label="Cache Hit %" value={`${data.cache_hit_rate_pct}%`} icon={Zap} accent="success" />
        <StatCard
          label="Jailbreak Attempts"
          value={data.jailbreak_attempts}
          icon={ShieldAlert}
          accent={data.jailbreak_attempts > 0 ? 'danger' : 'default'}
        />
        <StatCard label="👍 / 👎" value={thumbsRatio} icon={ThumbsUp} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-900">
            <BarChart2 className="h-4 w-4" /> Frequently Asked Questions
          </h3>
          {faqChart.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={faqChart} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis dataKey="question" type="category" width={140} tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#4f46e5" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-slate-400">No questions logged yet.</p>
          )}
        </div>

        <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
          <h3 className="mb-4 text-sm font-semibold text-slate-900">Recent Failures / Unsatisfied Answers</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                  <th className="pb-2 pr-4">User</th>
                  <th className="pb-2 pr-4">Question</th>
                  <th className="pb-2">Time</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_failures.map((f, i) => (
                  <tr key={i} className="border-b border-slate-50">
                    <td className="py-2 pr-4 text-slate-700">{f.username}</td>
                    <td className="py-2 pr-4 text-slate-600 max-w-xs truncate">{f.question}</td>
                    <td className="py-2 text-xs text-slate-400">{f.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {data.jailbreak_events.length > 0 && (
        <div className="rounded-xl border border-red-200 bg-red-50/50 p-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-red-800">
            <ShieldAlert className="h-4 w-4" /> Flagged Jailbreak Attempts
          </h3>
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-red-100 text-left text-xs text-red-600">
                <th className="pb-2 pr-4">User</th>
                <th className="pb-2 pr-4">Question</th>
                <th className="pb-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {data.jailbreak_events.map((e, i) => (
                <tr key={i} className="border-b border-red-50">
                  <td className="py-2 pr-4 text-red-900">{e.username}</td>
                  <td className="py-2 pr-4 text-red-800">{e.question}</td>
                  <td className="py-2 text-xs text-red-600">{e.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
        <h3 className="text-sm font-semibold text-slate-900">Recent Activity Log</h3>
        <p className="mb-4 text-xs text-slate-400">Used for future response quality tuning</p>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                <th className="pb-2 pr-3">Time</th>
                <th className="pb-2 pr-3">User</th>
                <th className="pb-2 pr-3">Question</th>
                <th className="pb-2 pr-3">Intent</th>
                <th className="pb-2 pr-3">Cache</th>
                <th className="pb-2 pr-3">Latency</th>
                <th className="pb-2 pr-3">Tokens</th>
                <th className="pb-2 pr-3">👍/👎</th>
                <th className="pb-2 pr-3">OK</th>
                <th className="pb-2">Retries</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_activity.map((a) => (
                <tr key={a.id} className="border-b border-slate-50">
                  <td className="py-2 pr-3 text-xs text-slate-400 whitespace-nowrap">{a.created_at}</td>
                  <td className="py-2 pr-3 text-slate-700">{a.username}</td>
                  <td className="py-2 pr-3 text-slate-600 max-w-[200px] truncate">{a.question}</td>
                  <td className="py-2 pr-3 text-xs">{a.intent}</td>
                  <td className="py-2 pr-3">{a.cache_hit ? '⚡' : '—'}</td>
                  <td className="py-2 pr-3 tabular-nums">{a.latency_ms}ms</td>
                  <td className="py-2 pr-3 tabular-nums">{a.tokens_used}</td>
                  <td className="py-2 pr-3">{a.thumbs ?? '—'}</td>
                  <td className="py-2 pr-3">{a.satisfied === 1 ? '✓' : a.satisfied === 0 ? '✗' : '—'}</td>
                  <td className="py-2 tabular-nums">{a.retries}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
