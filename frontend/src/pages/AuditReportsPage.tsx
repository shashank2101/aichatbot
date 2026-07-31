import { useEffect, useState } from 'react'
import { FileText, Copy, RefreshCw, MapPin, Sparkles, ChevronDown, ChevronUp } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getWarehouses, getAuditReport, getConsolidatedAuditReport } from '../api'
import type { Warehouse, AuditReport, ConsolidatedAuditReport } from '../types'

export function AuditReportsPage() {
  const { user } = useAuth()
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [report, setReport] = useState<AuditReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const [consolidated, setConsolidated] = useState<ConsolidatedAuditReport | null>(null)
  const [consolidatedLoading, setConsolidatedLoading] = useState(false)
  const [consolidatedOpen, setConsolidatedOpen] = useState(true)

  useEffect(() => {
    if (!user) return
    getWarehouses(user.token).then(setWarehouses).catch(() => {})
    loadConsolidated()
  }, [user])

  async function loadConsolidated() {
    if (!user) return
    setConsolidatedLoading(true)
    try {
      const r = await getConsolidatedAuditReport(user.token)
      setConsolidated(r)
    } catch {
      setConsolidated(null)
    } finally {
      setConsolidatedLoading(false)
    }
  }

  async function loadReport(warehouseId: number) {
    if (!user) return
    setSelected(warehouseId)
    setLoading(true)
    try {
      const r = await getAuditReport(warehouseId, user.token)
      setReport(r)
    } catch {
      setReport(null)
    } finally {
      setLoading(false)
    }
  }

  function copyReport() {
    if (!report) return
    const text = `${report.warehouse} (${report.region})\nDiscrepancies: ${report.discrepancy_count}\n\n${report.summary}`
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <button
          onClick={() => setConsolidatedOpen((o) => !o)}
          className="flex w-full items-center justify-between text-left"
        >
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-indigo-50 p-2">
              <Sparkles className="h-4 w-4 text-indigo-600" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">AI Insights — All Warehouses</h2>
              <p className="text-xs text-slate-500">
                {consolidated
                  ? `${consolidated.warehouse_count} warehouses · ${consolidated.total_discrepancies} discrepancies · ${consolidated.total_high_severity} high severity`
                  : 'Consolidated summary across every warehouse in your scope'}
              </p>
            </div>
          </div>
          {consolidatedOpen ? (
            <ChevronUp className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          )}
        </button>

        {consolidatedOpen && (
          <div className="mt-3">
            {consolidatedLoading ? (
              <p className="text-sm text-slate-400">Generating consolidated summary…</p>
            ) : consolidated ? (
              <>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{consolidated.summary}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {consolidated.per_warehouse.map((w) => (
                    <span
                      key={w.warehouse}
                      className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
                    >
                      {w.warehouse}: {w.discrepancy_count} disc. ({w.high_severity_count} high)
                    </span>
                  ))}
                </div>
                <button
                  onClick={loadConsolidated}
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                >
                  <RefreshCw className="h-3 w-3" /> Regenerate
                </button>
              </>
            ) : (
              <p className="text-sm text-red-600">Failed to load consolidated summary.</p>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-1 overflow-hidden">
      <div className="w-72 shrink-0 border-r border-slate-200 bg-white p-4 overflow-auto">
        <h2 className="mb-3 text-sm font-semibold text-slate-900">Warehouses</h2>
        <div className="space-y-2">
          {warehouses.map((w) => (
            <button
              key={w.warehouse_id}
              onClick={() => loadReport(w.warehouse_id)}
              className={`w-full rounded-lg px-3 py-2.5 text-left text-sm transition ${
                selected === w.warehouse_id
                  ? 'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200'
                  : 'text-slate-700 hover:bg-slate-50'
              }`}
            >
              <p className="font-medium">{w.name}</p>
              <p className="text-xs text-slate-500">{w.region}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {!selected ? (
          <div className="flex h-full flex-col items-center justify-center text-slate-400">
            <FileText className="mb-3 h-12 w-12" />
            <p>Select a warehouse to view its audit report</p>
          </div>
        ) : loading ? (
          <div className="flex h-full items-center justify-center text-slate-400">Generating report…</div>
        ) : report ? (
          <div className="mx-auto max-w-3xl">
            <div className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/60">
              <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
                <div className="flex items-start gap-3">
                  <div className="rounded-lg bg-indigo-50 p-2.5">
                    <FileText className="h-6 w-6 text-indigo-600" />
                  </div>
                  <div>
                    <h1 className="text-lg font-semibold text-slate-900">{report.warehouse}</h1>
                    <p className="mt-0.5 flex items-center gap-1 text-sm text-slate-500">
                      <MapPin className="h-3.5 w-3.5" /> {report.region}
                    </p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <span className="rounded-full bg-red-50 px-3 py-1 text-sm font-medium text-red-700">
                    {report.discrepancy_count} discrepancies
                  </span>
                  {typeof report.high_severity_count === 'number' && report.high_severity_count > 0 && (
                    <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                      {report.high_severity_count} high severity
                    </span>
                  )}
                </div>
              </div>

              <div className="px-6 py-5">
                <div className="prose prose-sm max-w-none text-slate-700 whitespace-pre-wrap leading-relaxed">
                  {report.summary}
                </div>

                {report.risk_stats && (
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                      {report.risk_stats.low_stock_count} low stock
                    </span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                      {report.risk_stats.out_of_stock_count} out of stock
                    </span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                      {report.risk_stats.overstock_count} overstock
                    </span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                      {report.risk_stats.invalid_location_count} invalid location
                    </span>
                  </div>
                )}
              </div>

              <div className="flex gap-2 border-t border-slate-100 px-6 py-4">
                <button
                  onClick={() => loadReport(selected)}
                  className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-50"
                >
                  <RefreshCw className="h-4 w-4" /> Regenerate
                </button>
                <button
                  onClick={copyReport}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700"
                >
                  <Copy className="h-4 w-4" /> {copied ? 'Copied!' : 'Copy Report'}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-red-600">Failed to load report.</div>
        )}
      </div>
      </div>
    </div>
  )
}
