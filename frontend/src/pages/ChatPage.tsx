import { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { sendChat } from '../api'
import { ChatMessage } from '../components/ChatMessage'
import type { ChatMessage as ChatMessageType } from '../types'

const SUGGESTIONS = [
  'Which SKUs are out of stock?',
  'Show pending audits',
  'High severity discrepancies?',
  'Total inventory value',
  'List warehouses in my region',
  'How many audits are completed?',
]

export function ChatPage() {
  const { user } = useAuth()
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendQuestion(question: string) {
    if (!question.trim() || !user || sending) return
    const q = question.trim()
    setInput('')
    setSending(true)

    const userMsg: ChatMessageType = { id: crypto.randomUUID(), role: 'user', content: q }
    const loadingMsg: ChatMessageType = { id: crypto.randomUUID(), role: 'assistant', content: '', loading: true }
    setMessages((prev) => [...prev, userMsg, loadingMsg])

    try {
      const resp = await sendChat(q, user.token)
      setMessages((prev) => {
        const withoutLoading = prev.filter((m) => !m.loading)
        return [
          ...withoutLoading,
          { id: crypto.randomUUID(), role: 'assistant', content: resp.answer, response: resp },
        ]
      })
    } catch (err) {
      setMessages((prev) => {
        const withoutLoading = prev.filter((m) => !m.loading)
        return [
          ...withoutLoading,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: err instanceof Error ? err.message : 'Something went wrong.',
            response: { answer: '', intent: 'error', cache_hit: false, retries: 0, blocked: true },
          },
        ]
      })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <div className="mx-auto max-w-2xl text-center pt-16">
            <h2 className="text-xl font-semibold text-slate-900">Ask about your inventory</h2>
            <p className="mt-2 text-sm text-slate-500">
              Query stock levels, audit progress, discrepancies, and more — answers are scoped to your role and region.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => sendQuestion(s)}
                  className="rounded-full bg-white px-4 py-2 text-sm text-slate-600 shadow-sm ring-1 ring-slate-200/60 transition hover:ring-indigo-300 hover:text-indigo-600"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.map((m) => (
              <ChatMessage key={m.id} message={m} token={user!.token} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="border-t border-slate-200 bg-white px-6 py-4">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            sendQuestion(input)
          }}
          className="mx-auto flex max-w-3xl gap-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about inventory, stock, audits, or discrepancies…"
            className="flex-1 rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            disabled={sending}
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="flex items-center justify-center rounded-xl bg-indigo-600 px-4 py-3 text-white transition hover:bg-indigo-700 disabled:opacity-50"
          >
            <Send className="h-5 w-5" />
          </button>
        </form>
      </div>
    </div>
  )
}
