import { useState } from 'react'
import { ThumbsUp, ThumbsDown, ChevronDown, ChevronRight, Zap, RotateCcw, ShieldAlert } from 'lucide-react'
import type { ChatMessage as ChatMessageType } from '../types'
import { DataTable } from './DataTable'
import { sendFeedback } from '../api'

interface Props {
  message: ChatMessageType
  token: string
}

export function ChatMessage({ message, token }: Props) {
  const [showData, setShowData] = useState(false)
  const [showSql, setShowSql] = useState(false)
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null)

  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-3 text-sm text-white shadow-sm">
          {message.content}
        </div>
      </div>
    )
  }

  if (message.loading) {
    return (
      <div className="flex justify-start">
        <div className="rounded-2xl rounded-bl-md bg-white px-4 py-3 shadow-sm ring-1 ring-slate-200/60">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="inline-flex gap-1">
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:0ms]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:150ms]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:300ms]" />
            </span>
            Analyzing your question…
          </div>
        </div>
      </div>
    )
  }

  const resp = message.response
  const blocked = resp?.blocked

  async function handleFeedback(thumbs: 'up' | 'down') {
    if (!resp?.log_id || feedback) return
    try {
      await sendFeedback(resp.log_id, thumbs, token)
      setFeedback(thumbs)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 shadow-sm ring-1 ${
          blocked
            ? 'bg-amber-50 ring-amber-200/60'
            : 'bg-white ring-slate-200/60'
        }`}
      >
        {blocked && (
          <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-amber-700">
            <ShieldAlert className="h-3.5 w-3.5" />
            Restricted response
          </div>
        )}
        <p className="text-sm leading-relaxed text-slate-800 whitespace-pre-wrap">{message.content}</p>

        {resp && !blocked && resp.rows && resp.rows.length > 0 && (
          <div className="mt-3">
            <button
              onClick={() => setShowData(!showData)}
              className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              {showData ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              View data ({resp.rows.length} rows)
            </button>
            {showData && (
              <div className="mt-2">
                <DataTable rows={resp.rows} />
              </div>
            )}
          </div>
        )}

        {resp && !blocked && resp.sql && (
          <div className="mt-2">
            <button
              onClick={() => setShowSql(!showSql)}
              className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
            >
              {showSql ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              View generated SQL
            </button>
            {showSql && (
              <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-green-300">
                {resp.sql}
              </pre>
            )}
          </div>
        )}

        {resp && (
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2">
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{resp.intent}</span>
            {resp.cache_hit && (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-green-50 px-2 py-0.5 text-xs text-green-700">
                <Zap className="h-3 w-3" /> cache hit
              </span>
            )}
            {resp.retries > 0 && (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                <RotateCcw className="h-3 w-3" /> refined ×{resp.retries}
              </span>
            )}
            {resp.log_id && !blocked && (
              <div className="ml-auto flex items-center gap-1">
                <button
                  onClick={() => handleFeedback('up')}
                  disabled={feedback !== null}
                  className={`rounded-lg p-1.5 transition ${feedback === 'up' ? 'bg-green-100 text-green-600' : 'text-slate-400 hover:bg-slate-100 hover:text-green-600'}`}
                >
                  <ThumbsUp className="h-4 w-4" />
                </button>
                <button
                  onClick={() => handleFeedback('down')}
                  disabled={feedback !== null}
                  className={`rounded-lg p-1.5 transition ${feedback === 'down' ? 'bg-red-100 text-red-600' : 'text-slate-400 hover:bg-slate-100 hover:text-red-600'}`}
                >
                  <ThumbsDown className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
