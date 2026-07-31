import { useState, useMemo } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

interface DataTableProps {
  rows: Record<string, unknown>[]
}

export function DataTable({ rows }: DataTableProps) {
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const columns = useMemo(() => (rows.length > 0 ? Object.keys(rows[0]) : []), [rows])

  const sorted = useMemo(() => {
    if (!sortKey) return rows
    return [...rows].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (av == null) return 1
      if (bv == null) return -1
      const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true })
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [rows, sortKey, sortDir])

  function toggleSort(key: string) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  if (rows.length === 0) return null

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-sm">
        <thead className="sticky top-0 bg-slate-50">
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                onClick={() => toggleSort(col)}
                className="cursor-pointer px-4 py-2.5 text-left font-medium text-slate-600 hover:bg-slate-100"
              >
                <span className="inline-flex items-center gap-1">
                  {col.replace(/_/g, ' ')}
                  {sortKey === col && (sortDir === 'asc' ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
              {columns.map((col) => (
                <td key={col} className="px-4 py-2 text-slate-700 tabular-nums">
                  {String(row[col] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
