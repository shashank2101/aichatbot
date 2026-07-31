import type {
  User,
  ChatResponse,
  DashboardMetrics,
  Alert,
  Warehouse,
  AuditReport,
  ConsolidatedAuditReport,
  ObservabilityData,
  IngestResult,
} from './types'

const BASE = import.meta.env.VITE_API_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
  }
  return res.json()
}

export function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export async function login(username: string, password: string): Promise<User> {
  return request<User>('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export async function sendChat(question: string, token: string, sessionId: string): Promise<ChatResponse> {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, token, session_id: sessionId }),
  })
}

export interface StoredChatMessage {
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ChatSession {
  session_id: string
  preview: string
  updated_at: string
}

export async function getChatHistory(sessionId: string, token: string): Promise<StoredChatMessage[]> {
  const params = new URLSearchParams({ session_id: sessionId })
  const response = await request<{ messages: StoredChatMessage[] }>(`/chat/history?${params}`, {
    headers: authHeaders(token),
  })
  return response.messages
}

export async function getChatSessions(token: string): Promise<ChatSession[]> {
  const response = await request<{ sessions: ChatSession[] }>('/chat/sessions', {
    headers: authHeaders(token),
  })
  return response.sessions
}

export async function sendFeedback(logId: number, thumbs: 'up' | 'down', token: string) {
  return request('/chat/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify({ log_id: logId, thumbs }),
  })
}

export async function getDashboardMetrics(token: string): Promise<DashboardMetrics> {
  return request('/dashboard/metrics', { headers: authHeaders(token) })
}

export async function getAlerts(token: string): Promise<{ alerts: Alert[] }> {
  return request('/alerts', { headers: authHeaders(token) })
}

export async function getWarehouses(token: string): Promise<Warehouse[]> {
  return request('/warehouses', { headers: authHeaders(token) })
}

export async function getAuditReport(warehouseId: number, token: string): Promise<AuditReport> {
  return request(`/audit-report/${warehouseId}`, { headers: authHeaders(token) })
}

export async function getObservability(token: string): Promise<ObservabilityData> {
  return request('/admin/observability', { headers: authHeaders(token) })
}

export async function getConsolidatedAuditReport(token: string): Promise<ConsolidatedAuditReport> {
  return request('/audit-report/consolidated', { headers: authHeaders(token) })
}

export async function uploadIngestCsv(file: File, token: string): Promise<IngestResult> {
  const form = new FormData()
  form.append('file', file)
  return request('/ingest/upload-csv', {
    method: 'POST',
    headers: authHeaders(token),
    body: form,
  })
}
