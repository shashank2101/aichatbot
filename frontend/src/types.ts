export interface User {
  token: string
  username: string
  role: string
  region: string | null
  full_name: string
}

export interface ChatResponse {
  answer: string
  sql?: string | null
  rows?: Record<string, unknown>[] | null
  intent: string
  cache_hit: boolean
  retries: number
  log_id?: number | null
  blocked: boolean
}

export interface Alert {
  severity: string
  type: string
  message: string
}

export interface Warehouse {
  warehouse_id: number
  name: string
  region: string
  capacity_units: number
}

export interface AuditReport {
  warehouse: string
  region: string
  summary: string
  discrepancy_count: number
  high_severity_count?: number
  risk_stats?: {
    sku_lines: number
    low_stock_count: number
    out_of_stock_count: number
    overstock_count: number
    invalid_location_count: number
  }
  tokens_used: number
}

export interface ConsolidatedAuditReport {
  summary: string
  warehouse_count: number
  total_audits: number
  total_audits_completed: number
  total_discrepancies: number
  total_high_severity: number
  per_warehouse: {
    warehouse: string
    region: string
    audits_total: number
    audits_completed: number
    discrepancy_count: number
    high_severity_count: number
  }[]
  tokens_used: number
}

export interface IngestResult {
  accepted: number
  rejected: number
  rejected_details: { record: Record<string, unknown>; reason: string }[]
  synced_to_secondary: Record<string, number>
  parse_errors?: { row: number | null; reason: string }[]
  filename?: string
}

export interface DashboardMetrics {
  inventory: {
    total_warehouses: number
    total_skus: number
    total_inventory_units: number
    inventory_value: number
    low_stock_count: number
    out_of_stock_count: number
    overstock_count: number
    duplicate_sku_count: number
    missing_sku_count: number
    invalid_location_count: number
  }
  audit: {
    audit_progress_pct: number
    completed_audits: number
    pending_audits: number
    active_audits: number
    total_audits: number
  }
  discrepancy: {
    total_discrepancies: number
    shortages: number
    overstock: number
    wrong_location: number
    damaged: number
    expired: number
    high_variance: number
    high_severity: number
  }
  operational: {
    warehouse_utilization: { warehouse: string; utilization_pct: number }[]
    top_discrepancy_warehouse: { warehouse: string; discrepancy_count: number }
    frequently_affected_skus: { sku_code: string; count: number }[]
  }
  ai_metrics: {
    total_questions: number
    avg_latency_ms: number
    avg_tokens_used: number
    cache_hit_rate_pct: number
    jailbreak_attempts: number
    thumbs_up: number
    thumbs_down: number
    unsatisfied_answers: number
  }
}

export interface ObservabilityData {
  total_questions: number
  avg_latency_ms: number
  avg_tokens_used: number
  cache_hit_rate_pct: number
  jailbreak_attempts: number
  thumbs_up: number
  thumbs_down: number
  unsatisfied_answers: number
  top_questions: { question: string; c: number }[]
  recent_failures: { username: string; question: string; intent: string; created_at: string }[]
  jailbreak_events: { username: string; question: string; created_at: string }[]
  recent_activity: {
    id: number
    username: string
    question: string
    intent: string
    cache_hit: number
    latency_ms: number
    tokens_used: number
    thumbs: string | null
    satisfied: number | null
    retries: number
    jailbreak_flag: number
    created_at: string
  }[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  response?: ChatResponse
  loading?: boolean
}
