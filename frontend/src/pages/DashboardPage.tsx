import { useEffect, useState, useCallback } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  CartesianGrid,
} from 'recharts'
import {
  Warehouse,
  Package,
  Boxes,
  IndianRupee,
  ClipboardCheck,
  AlertTriangle,
  MessageSquare,
  Clock,
  Zap,
  ThumbsUp,
  RefreshCw,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getDashboardMetrics } from '../api'
import { StatCard } from '../components/StatCard'
import type { DashboardMetrics } from '../types'

const PIE_COLORS = ['#f59e0b', '#ef4444', '#8b5cf6', '#16a34a']

function RadialProgress({ pct }: { pct: number }) {
  const r = 40
  const circ = 2 * Math.PI * r
  const offset = circ - (pct / 100) * circ
  return (
    <div className="flex flex-col items-center">
      <svg width="100" height="100" className="-rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#e2e8f0" strokeWidth="8" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="#4f46e5"
          strokeWidth="8"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <p className="-mt-14 text-lg font-semibold tabular-nums text-slate-900">{pct}%</p>
      <p className="mt-8 text-xs text-slate-500">Audit Progress</p>
    </div>
  )
}

function formatCurrency(n: number) {
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

const REFRESH_INTERVAL_MS = 10_000

export function DashboardPage() {
  const { user } = useAuth()
  const [data, setData] = useState<DashboardMetrics | null>(null)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const fetchMetrics = useCallback(
    async (silent: boolean) => {
      if (!user) return
      if (silent) setRefreshing(true)
      try {
        const r = await getDashboardMetrics(user.token)
        setData(r)
        setLastUpdated(new Date())
        setError('')
      } catch (e) {
        // Keep showing the last-known-good data on a background refresh failure —
        // only surface the error page if we have nothing to show yet.
        if (!silent) setError(e instanceof Error ? e.message : 'Failed to load metrics')
      } finally {
        if (silent) setRefreshing(false)
      }
    },
    [user],
  )

  useEffect(() => {
    if (!user) return
    fetchMetrics(false) // initial load
    const id = setInterval(() => fetchMetrics(true), REFRESH_INTERVAL_MS)
    return () => clearInterval(id)
  }, [user, fetchMetrics])

  if (error) return <div className="p-6 text-red-600">{error}</div>
  if (!data) return <div className="flex items-center justify-center p-12 text-slate-400">Loading metrics…</div>

  const { inventory, audit, discrepancy, operational, ai_metrics } = data

  const discrepancyChart = [
    { name: 'Shortages', value: discrepancy.shortages },
    { name: 'Overstock', value: discrepancy.overstock },
    { name: 'Wrong Location', value: discrepancy.wrong_location },
    { name: 'Damaged', value: discrepancy.damaged },
    { name: 'Expired', value: discrepancy.expired },
    { name: 'High Variance', value: discrepancy.high_variance },
  ]

  const healthy =
    inventory.total_inventory_units -
    inventory.low_stock_count -
    inventory.out_of_stock_count -
    inventory.overstock_count

  const healthPie = [
    { name: 'Low Stock', value: inventory.low_stock_count },
    { name: 'Out of Stock', value: inventory.out_of_stock_count },
    { name: 'Overstock', value: inventory.overstock_count },
    { name: 'Healthy', value: Math.max(0, healthy) },
  ]

  const thumbsRatio =
    ai_metrics.thumbs_up + ai_metrics.thumbs_down > 0
      ? `${Math.round((ai_metrics.thumbs_up / (ai_metrics.thumbs_up + ai_metrics.thumbs_down)) * 100)}% 👍`
      : '—'

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500">Live inventory, audit, and operational metrics</p>
        </div>
        <div className="flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs text-slate-500 shadow-sm ring-1 ring-slate-200/60">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
          </span>
          Auto-refreshing every 10s
          <span className="text-slate-300">·</span>
          <span className="tabular-nums">
            {lastUpdated ? `Last updated ${lastUpdated.toLocaleTimeString()}` : 'Loading…'}
          </span>
          <button
            onClick={() => fetchMetrics(true)}
            disabled={refreshing}
            title="Refresh now"
            className="ml-1 rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total Warehouses" value={inventory.total_warehouses} icon={Warehouse} />
        <StatCard label="Total SKUs" value={inventory.total_skus} icon={Package} />
        <StatCard label="Inventory Units" value={inventory.total_inventory_units.toLocaleString()} icon={Boxes} />
        <StatCard label="Inventory Value" value={formatCurrency(inventory.inventory_value)} icon={IndianRupee} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex items-center justify-center rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
          <RadialProgress pct={audit.audit_progress_pct} />
        </div>
        <StatCard label="Completed Audits" value={audit.completed_audits} icon={ClipboardCheck} accent="success" />
        <StatCard label="Pending Audits" value={audit.pending_audits} icon={Clock} accent="warning" />
        <StatCard label="Active Audits" value={audit.active_audits} icon={ClipboardCheck} accent="default" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total Discrepancies" value={discrepancy.total_discrepancies} icon={AlertTriangle} accent="danger" />
        <StatCard label="Shortages" value={discrepancy.shortages} accent="warning" />
        <StatCard label="Overstock" value={discrepancy.overstock} accent="warning" />
        <StatCard label="High Severity" value={discrepancy.high_severity} accent="danger" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
          <h3 className="mb-4 text-sm font-semibold text-slate-900">Discrepancies by Type</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={discrepancyChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="value" fill="#4f46e5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
          <h3 className="mb-4 text-sm font-semibold text-slate-900">Inventory Health</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={healthPie} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3}>
                {healthPie.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-2 flex flex-wrap justify-center gap-3">
            {healthPie.map((d, i) => (
              <span key={d.name} className="flex items-center gap-1.5 text-xs text-slate-600">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: PIE_COLORS[i] }} />
                {d.name}: {d.value}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
          <h3 className="mb-4 text-sm font-semibold text-slate-900">Warehouse Utilization</h3>
          <div className="space-y-3">
            {operational.warehouse_utilization.map((w) => {
              const color = w.utilization_pct > 100 ? 'bg-red-500' : w.utilization_pct > 85 ? 'bg-amber-500' : 'bg-indigo-500'
              return (
                <div key={w.warehouse}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="text-slate-700">{w.warehouse}</span>
                    <span className="tabular-nums text-slate-500">{w.utilization_pct}%</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-slate-100">
                    <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(w.utilization_pct, 100)}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl bg-indigo-50 p-5 ring-1 ring-indigo-100">
            <p className="text-xs font-medium uppercase tracking-wide text-indigo-600">Top Discrepancy Warehouse</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">{operational.top_discrepancy_warehouse.warehouse}</p>
            <p className="text-sm text-slate-600">{operational.top_discrepancy_warehouse.discrepancy_count} discrepancies</p>
          </div>
          <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
            <h3 className="mb-3 text-sm font-semibold text-slate-900">Frequently Affected SKUs</h3>
            <div className="space-y-2">
              {operational.frequently_affected_skus.map((s) => (
                <div key={s.sku_code} className="flex justify-between text-sm">
                  <span className="font-mono text-slate-700">{s.sku_code}</span>
                  <span className="tabular-nums text-slate-500">{s.count} issues</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-slate-900">AI Metrics</h3>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Questions Asked" value={ai_metrics.total_questions} icon={MessageSquare} />
          <StatCard label="Avg Latency" value={`${ai_metrics.avg_latency_ms} ms`} icon={Clock} />
          <StatCard label="Cache Hit Rate" value={`${ai_metrics.cache_hit_rate_pct}%`} icon={Zap} accent="success" />
          <StatCard label="Thumbs Up Ratio" value={thumbsRatio} icon={ThumbsUp} />
        </div>
      </div>
    </div>
  )
}
