import { useRef, useState } from 'react'
import { UploadCloud, FileSpreadsheet, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { uploadIngestCsv } from '../api'
import type { IngestResult } from '../types'

export function DataUploadPage() {
  const { user } = useAuth()
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<IngestResult | null>(null)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  function pickFile(f: File | null) {
    setResult(null)
    setError('')
    if (f && !f.name.toLowerCase().endsWith('.csv')) {
      setError('Please choose a .csv file.')
      setFile(null)
      return
    }
    setFile(f)
  }

  async function handleUpload() {
    if (!user || !file) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const r = await uploadIngestCsv(file, user.token)
      setResult(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-900">Data Upload</h1>
        <p className="text-sm text-slate-500">
          Push live inventory data from another source into the system via CSV — validated,
          deduplicated, and synced to the right regional store, same as the ERP push pipeline.
        </p>
      </div>

      <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200/60">
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            pickFile(e.dataTransfer.files?.[0] ?? null)
          }}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition ${
            dragOver ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 hover:border-slate-300'
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <>
              <FileSpreadsheet className="mb-3 h-10 w-10 text-indigo-500" />
              <p className="text-sm font-medium text-slate-900">{file.name}</p>
              <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB — click to replace</p>
            </>
          ) : (
            <>
              <UploadCloud className="mb-3 h-10 w-10 text-slate-400" />
              <p className="text-sm font-medium text-slate-900">Drop a CSV file here, or click to browse</p>
              <p className="mt-1 text-xs text-slate-500">
                Required columns: warehouse_id, sku_code, quantity. Optional: location_bin, source_system.
              </p>
            </>
          )}
        </div>

        {error && (
          <p className="mt-3 flex items-center gap-2 text-sm text-red-600">
            <XCircle className="h-4 w-4" /> {error}
          </p>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || loading}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <UploadCloud className="h-4 w-4" /> {loading ? 'Uploading…' : 'Push to database'}
        </button>
      </div>

      {result && (
        <div className="mt-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200/60">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">Result — {result.filename}</h2>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Accepted" value={result.accepted} tone="green" />
            <Stat label="Rejected" value={result.rejected} tone="red" />
            <Stat
              label="Synced (secondary)"
              value={Object.values(result.synced_to_secondary ?? {}).reduce((a, b) => a + b, 0)}
              tone="indigo"
            />
            <Stat label="Parse errors" value={result.parse_errors?.length ?? 0} tone="amber" />
          </div>

          {result.accepted > 0 && (
            <p className="mb-4 flex items-center gap-2 text-sm text-green-700">
              <CheckCircle2 className="h-4 w-4" /> {result.accepted} row(s) written to primary.db and
              synced to the correct regional store.
            </p>
          )}

          {(result.rejected_details?.length ?? 0) > 0 && (
            <div className="mb-4">
              <p className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                <AlertTriangle className="h-3.5 w-3.5" /> Rejected rows
              </p>
              <div className="max-h-56 space-y-1.5 overflow-auto rounded-lg bg-slate-50 p-3">
                {result.rejected_details.map((r, i) => (
                  <p key={i} className="text-xs text-slate-600">
                    <span className="font-mono text-slate-500">{JSON.stringify(r.record)}</span> — {r.reason}
                  </p>
                ))}
              </div>
            </div>
          )}

          {(result.parse_errors?.length ?? 0) > 0 && (
            <div>
              <p className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                <AlertTriangle className="h-3.5 w-3.5" /> Parse errors
              </p>
              <div className="space-y-1.5 rounded-lg bg-slate-50 p-3">
                {result.parse_errors!.map((e, i) => (
                  <p key={i} className="text-xs text-slate-600">
                    {e.row ? `Row ${e.row}` : 'File'} — {e.reason}
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone: 'green' | 'red' | 'indigo' | 'amber' }) {
  const toneClass = {
    green: 'text-green-700 bg-green-50',
    red: 'text-red-700 bg-red-50',
    indigo: 'text-indigo-700 bg-indigo-50',
    amber: 'text-amber-700 bg-amber-50',
  }[tone]
  return (
    <div className={`rounded-lg px-3 py-2.5 ${toneClass}`}>
      <p className="text-lg font-semibold">{value}</p>
      <p className="text-xs">{label}</p>
    </div>
  )
}
