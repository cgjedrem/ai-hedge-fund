export interface Capabilities {
  mode: "live" | "demo";
  read_only: boolean;
  writes: boolean;
  network: boolean;
  local_operator_only: boolean;
  csrf_authenticates_users: false;
  container_observer: boolean;
  enrollment_state: "unenrolled" | "enrolled" | "invalid" | "drift";
  write_authority?: "protocol-native" | "operator-trusted-single-writer" | "ownership-unknown" | "unavailable";
  write_unavailable_reason: string | null;
  operator_trust_warning: string | null;
  protected_names: string[];
  mutation_token: string | null;
  deferred_actions: Record<string, string>;
}

export type ApiErrorCode =
  | "invalid-request"
  | "capability-denied"
  | "protected-root"
  | "read-only"
  | "broker-not-web-supported"
  | "not-found"
  | "stale-preview"
  | "request-conflict"
  | "writer-conflict"
  | "ownership-unknown"
  | "halted"
  | "replay-corrupt"
  | "reconciliation-required"
  | "readiness-denied"
  | "unsupported-filesystem"
  | "private-storage-unverified"
  | "expired-confirmation"
  | "capacity-denied"
  | "budget-exhausted"
  | "payload-too-large"
  | "observation-conflict"
  | "assets-unavailable"
  | "inspection-timeout"
  | "internal-error";

export type ApiRetryPolicy =
  | "none"
  | "review-again"
  | "reload"
  | "inspect-status"
  | "retry-later"
  | "retry-read-only";

export interface ApiErrorShape {
  detail: string | { message?: string }[];
  code?: ApiErrorCode;
  message?: string;
  refresh_required?: boolean;
  retry_policy?: ApiRetryPolicy;
  subject_id?: string | null;
  request_id?: string | null;
  current_head?: string | null;
  retry_after_seconds?: number | null;
}

export interface ModelOption {
  label: string;
  id: string;
  provider: string;
}

export interface StrategyModelOption {
  name: string;
  weight: number;
  params: Record<string, unknown>;
}

export interface StrategyBlendOption {
  method: string;
  gross_target: number;
  mode: string;
}

export interface StrategyOption {
  name: string;
  title: string;
  models: StrategyModelOption[];
  kind: "systematic" | "discretionary";
  mode: string;
  blend: StrategyBlendOption;
}

export interface AnalystOption {
  name: string;
  approach: "long_only" | "long_short";
}

export interface Catalog {
  models: ModelOption[];
  strategies: StrategyOption[];
  analysts: AnalystOption[];
  default_model: string;
}

export interface MandateStrategy {
  name: string;
  title: string;
  mode: string;
  weight: number;
}

export interface MandateSummary {
  name: string;
  mandate_hash: string;
  agent_count: number;
  strategies: MandateStrategy[];
  cadence: string;
  capital: number;
  benchmark: string;
  approval_required: boolean;
  broker: string;
  spec?: Record<string, unknown>;
}

export interface MandateCollection {
  items: MandateSummary[];
  errors: { name: string; error: string }[];
}

export interface HomeData {
  mode: "live" | "demo";
  mandate_count: number;
  paper_count: number;
  research_count: number;
  recorded_nav_total: number;
  paper_funds: PaperSummary[];
  errors: { name?: string; id?: string; error: string }[];
}

export type HaltState = "clear" | "halted" | "unreadable";

export interface PaperSummary {
  name: string;
  universe: string[];
  cadence: string;
  broker: string;
  nav: number | null;
  cash: number | null;
  last_session: string | null;
  ledger_ok: boolean;
  halted: string | null;
  halt_state: HaltState;
  runner: RunnerState;
}

export interface PaperCollection {
  items: PaperSummary[];
  errors: { name: string; error: string }[];
}

export interface RunnerState {
  status: string;
  available: boolean;
  reason: string | null;
  started_at?: string | null;
  expires_at?: string | null;
  sessions_completed?: number;
  max_sessions?: number | null;
  last_session?: string | null;
}

export interface Position {
  ticker: string;
  shares: number;
  mark: number | null;
  market_value: number | null;
}

export interface ValuationQuote {
  ticker: string;
  shares: string;
  price: string | null;
  quote_time: string | null;
  observation_age_seconds: number | null;
  status: "quoted" | "missing" | "stale" | "error";
  freshness: "unknown";
  reason: string | null;
}

export interface LiveValuation {
  status: "unavailable" | "estimated" | "partial" | "stale" | "obsolete";
  value: string | null;
  partial_estimate: string | null;
  as_of: string | null;
  provenance: string | null;
  expected_head: string | null;
  recorded_nav: string | null;
  request_id?: string;
  deployment?: string;
  coverage: {
    total: number;
    quoted: number;
    usable: number;
    missing: number;
    stale: number;
    errors: number;
  };
  quotes: ValuationQuote[];
  reason: string;
}

export interface CurvePoint {
  session: string;
  nav: number;
  benchmark_nav: number | null;
}

export interface SessionSummary {
  session: string;
  hash: string;
  nav: number;
  cash: number;
  rebalance: boolean;
  orders: number;
  fills: number;
  decision_as_of: string | null;
}

export interface PendingDecision {
  decision_as_of: string;
  source_record_hash: string;
  universe: string[];
  target_weights: Record<string, number>;
  final_weights: Record<string, number>;
  strategies: string[];
}

export interface Approval {
  verdict: "approve" | "reject";
  decision_as_of: string;
  decision_hash: string;
  decided_at: string;
  by: string;
}

export interface ScoreMetrics {
  fund: string;
  first_session: string;
  last_session: string;
  horizon: string | null;
  fund_pnl: number;
  trading_cost: number;
  unattributed: number;
  analysts: {
    name: string;
    n_views: number;
    n_directional: number;
    n_abstained: number;
    hit_rate: number | null;
    slugging: number | null;
    ic_mean: number | null;
    ic_t_stat: number | null;
  }[];
  strategies: {
    name: string;
    n_periods: number;
    pnl: number;
    return_pct: number;
    win_rate: number | null;
    share_of_pnl: number | null;
    max_drawdown_pct: number;
  }[];
}

export interface PaperSnapshot {
  name: string;
  spec: Record<string, unknown> & { approval_required?: boolean };
  universe: string[];
  broker: string;
  created: string;
  cadence: string;
  last_session: string | null;
  last_record_hash: string | null;
  nav: number | null;
  cash: number | null;
  positions: Position[];
  curve: CurvePoint[];
  sessions: SessionSummary[];
  session_reports?: SessionReport[];
  pending: PendingDecision | null;
  approval: Approval | null;
  next_run: string | null;
  halted: string | null;
  halt_state: HaltState;
  ledger: { ok: boolean; error: string | null };
  runner: RunnerState;
  live_value: LiveValuation;
  scorecard: ScoreMetrics | null;
  scorecard_error: string | null;
}

export interface PaperReconciliationPreview {
  schema_version: 1;
  required: boolean;
  recoverable: boolean;
  reason:
    | "no-ambiguous-tick-failure"
    | "multiple-unreconciled-failures"
    | "failure-identity-incomplete"
    | "ledger-head-changed"
    | "broker-not-local-paper"
    | "broker-book-unavailable"
    | "broker-book-invalid"
    | "broker-book-changed"
    | "broker-book-mismatch"
    | "ready";
  failure_id: string | null;
  failed_request_id: string | null;
  operation_id: string | null;
  expected_head: string | null;
  current_head: string | null;
  broker_book_sha256: string | null;
  fill_identity_sha256: string;
  capture_id: string | null;
  capture_digest: string | null;
  book_matches_ledger: boolean;
  head_matches_failure: boolean;
  decision: "confirm-paper-book-matches-ledger";
  residual_uncertainty: "external-broker-state-not-applicable-local-paper-only";
  preview_digest: string | null;
}

export interface PaperTickIntentReconciliationPreview {
  schema_version: 1;
  required: boolean;
  recoverable: boolean;
  reason:
    | "no-unresolved-tick-intent"
    | "multiple-unresolved-tick-intents"
    | "intent-not-found"
    | "ledger-head-changed"
    | "broker-not-local-paper"
    | "broker-book-unavailable"
    | "broker-book-invalid"
    | "broker-book-changed"
    | "broker-book-mismatch"
    | "ready";
  intent_request_id: string | null;
  intent_session: string | null;
  intent_digest: string | null;
  metadata_complete: boolean | null;
  corrupt_event_digests: string[];
  expected_head: string | null;
  current_head: string | null;
  broker_book_sha256: string | null;
  fill_identity_sha256: string;
  book_matches_ledger: boolean;
  head_matches_intent: boolean;
  decision: "confirm-paper-book-matches-ledger";
  residual_uncertainty: "external-broker-state-not-applicable-local-paper-only";
  preview_digest: string | null;
}

export interface PaperReconciliation {
  name: string;
  halted: string | null;
  resume_allowed: boolean;
  preview: PaperReconciliationPreview;
  intent_preview: PaperTickIntentReconciliationPreview;
  intent_targets: PaperTickIntentReconciliationTarget[];
}

export interface PaperTickIntentReconciliationTarget {
  intent_request_id: string | null;
  intent_session: string | null;
  intent_digest: string;
  recorded_at: string | null;
  metadata_complete: boolean;
}

export interface PaperSessionsCollection {
  items: SessionSummary[];
  errors: { id: string; error: string }[];
  next_cursor: string | null;
  limit: number;
  total: number;
  search: string;
  ledger: { ok: boolean; error: string | null };
}

export interface OrderDto {
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
}

export interface FillDto {
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
}

export interface SignalDto {
  model_name: string;
  ticker: string;
  date: string;
  value: number;
  reasoning: string | null;
  components: Record<string, number>;
}

export interface RiskLimitsDto {
  max_position_pct: number;
  max_gross_exposure: number;
}

export interface ClampEventDto {
  limit: "max_position_pct" | "max_gross_exposure";
  ticker: string | null;
  before: number;
  after: number;
}

export interface SessionReport {
  session: string;
  fund: string;
  hash: string;
  prev_hash: string | null;
  code_version: string;
  mandate_hash: string;
  nav: number;
  cash: number;
  positions: Record<string, number>;
  marks: Record<string, number>;
  benchmark: string;
  benchmark_close: number;
  rebalance: boolean;
  executed: {
    as_of: string;
    spec: { risk: RiskLimitsDto };
    clamps: ClampEventDto[];
    risk_scale_factor: number | null;
    orders: OrderDto[];
    fills: FillDto[];
    trading_cost?: number;
    traded_notional?: number;
    commission?: number;
    slippage?: number;
  } | null;
  proposed: {
    as_of: string;
    universe: string[];
    target_weights: Record<string, number>;
    final_weights: Record<string, number>;
    clamps: ClampEventDto[];
    risk: RiskLimitsDto;
    risk_scale_factor: number | null;
    strategies: {
      name: string;
      signals: SignalDto[];
      convictions: Record<string, number>;
      weights: Record<string, number>;
    }[];
  } | null;
}

export interface ResearchSummary {
  id: string;
  fund: string;
  start: string;
  end: string;
  rebalance: string;
  benchmark: string;
  universe: string[];
  session_count: number;
  metrics: {
    total_return_pct: number;
    annualized_return_pct: number;
    sharpe_ratio: number;
    max_drawdown_pct: number;
    benchmark_return_pct: number;
    excess_return_pct: number;
    n_cycles: number;
    n_orders: number;
    traded_notional: number;
    trading_cost: number;
  };
}

export interface ResearchReport extends ResearchSummary {
  dates: string[];
  nav: number[];
  benchmark_nav: number[];
  sessions: SessionSummary[];
}

export interface ResearchCollection {
  items: ResearchSummary[];
  errors: { id: string; error: string }[];
  next_cursor: string | null;
  limit: number;
  total: number;
  search: string;
}

export interface Job {
  id: string;
  fund: string;
  provider: string;
  model: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  submitted_at: string;
  started_at: string | null;
  completed_at: string | null;
  report_id: string | null;
  error: string | null;
  cancel_requested: boolean;
}

export type OperationStatus =
  | "accepted"
  | "running"
  | "completed"
  | "failed"
  | "interrupted"
  | "cancel-requested"
  | "cancelled";

export interface BacktestPayload {
  fund: string;
  universe: string[];
  start: string;
  end: string;
  provider: string;
  model: string;
  mandate_hash: string;
  authorize_paid_provider?: boolean;
  confirm_fd_self_service_pricing?: boolean;
  cost_model_id?: string | null;
  cost_model_version?: string | null;
  paid_max_calls?: number | null;
  paid_max_cost_usd?: string | null;
  paid_max_attempt_cost_usd?: string | null;
}

export interface OperationPreviewRequest {
  action: "backtest";
  subject_id: string;
  expected_head: string;
  payload: BacktestPayload;
}

export interface OperationAcceptRequest extends OperationPreviewRequest {
  request_id: string;
  preview_id: string;
  preview_digest: string;
  confirmation_token: string;
  due_set: string[];
}

export interface OperationCancelRequest {
  request_id: string;
}

export interface Operation {
  operation_id: string;
  request_id: string;
  action: string;
  subject_id: string;
  capture_id: string;
  capture_digest: string;
  status: OperationStatus;
  created_at: string;
  updated_at: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  progress: number;
  id: string;
  fund: string;
  provider: string | null;
  model: string | null;
  report_id: string | null;
  error: string | null;
  cancel_requested: boolean;
  status_url: string;
}

export interface OperationPreview {
  preview_id: string;
  preview_digest: string;
  confirmation_token: string;
  action: "backtest";
  subject_id: string;
  expected_head: string;
  due_set: string[];
  capture_id: string;
  capture_digest: string;
  expires_at: string;
  payload: BacktestPayload;
  capture: Record<string, unknown>;
  estimate: {
    maximum_model_calls: number;
    paid_provider?: string | null;
    maximum_cost_usd: number | null;
    maximum_paid_calls?: number;
    maximum_attempt_cost_usd?: number | null;
    cost_model_id?: string | null;
    cost_model_version?: string | null;
    cost_model?: string | null;
    market_data_provider: string;
  };
  warnings: string[];
}

export interface PaperOperationPreview {
  preview_id: string;
  preview_digest: string;
  confirmation_token: string;
  action: "paper-tick" | "paper-runner-start";
  subject_id: string;
  expected_head: string | null;
  due_set: string[];
  outcome?: "ready" | "nothing-due";
  capture_id: string;
  capture_digest: string;
  expires_at: string;
  payload: Record<string, unknown>;
  capture: Record<string, unknown>;
  estimate: {
    maximum_model_calls_per_session: number;
    maximum_calls: number;
    maximum_resources: number;
    maximum_cost_usd: number;
    market_data_provider: string;
  };
  warnings: string[];
}

export interface Settings {
  model: string;
  llm_provider: string;
  endpoint: string | null;
  timeout_seconds: number;
  parameters: Record<string, number>;
  version: number;
  provenance: Record<string, "default" | "persisted" | "environment" | "launch">;
  settings_error: string | null;
  models: ModelOption[];
  providers: { provider: string; requires_key: boolean; configured: boolean; version: number }[];
  data_provider: string;
  data_providers: {
    id: string;
    label: string;
    requires_key?: boolean;
    configured?: boolean;
    version?: number;
  }[];
  active_captures: {
    capture_id: string;
    subject_id: string;
    status: "accepted" | "running" | "cancel-requested";
    capture_details_available: boolean;
    settings_version: number | null;
    data_provider: string | null;
    llm_provider: string | null;
    model: string | null;
    endpoint: string | null;
    restart_needed: boolean | null;
  }[];
  active_captures_available: boolean;
  configuration?: ConfigurationProvenance;
  endpoint_redacted?: boolean;
  network_enabled: boolean;
}

export interface SaxoSimStatus {
  environment: "SIM";
  read_only: true;
  capability: {
    enabled: boolean;
    state: "disabled" | "unavailable" | "requires-auth" | "available" | "expired" | "revoked";
    generation: number;
    expires_at: string | null;
    actions: { discover: boolean; inspect: boolean; revoke: boolean };
  };
}

export interface SaxoSimChoice {
  selection_id: string;
  label: string;
  currency: string;
}

export interface SaxoSimDiscovery {
  environment: "SIM";
  read_only: true;
  generation: number;
  selection_required: true;
  choices: SaxoSimChoice[];
}

export interface SaxoSimInspection {
  environment: "SIM";
  read_only: true;
  generation: number;
  account: {
    label: string;
    currency: string;
    cash_balance: number;
    positions: { uic: number; amount: number }[];
  };
  fund_connected: false;
  trading_enabled: false;
}

export type SettingsSource = "default" | "persisted" | "environment" | "launch";

export interface ConfigurationField {
  field: string;
  source: SettingsSource;
  override: string | null;
  stored_source: SettingsSource | null;
  stored: unknown;
  effective: unknown;
  redacted: boolean;
  diverges: boolean;
  shadowed: boolean;
}

export type RestartReason =
  | "stored-version-changed"
  | "override-shadows-stored"
  | "active-capture-stale"
  | "owned-runner-stale"
  | "owned-runner-unverified";

export interface ConfigurationProvenance {
  stored: { available: boolean; version: number | null; present: boolean };
  effective: { version: number; startup_version: number };
  fields: ConfigurationField[];
  overrides: { field: string; source: SettingsSource; variable: string }[];
  restart_required: boolean;
  restart_reasons: RestartReason[];
  stored_values: {
    data_provider: string;
    llm_provider: string;
    model: string;
    endpoint: string | null;
    timeout_seconds: number;
    parameters: Record<string, number>;
  } | null;
  active: { available: boolean; count: number; stale_count: number };
  runners: { available: boolean; count: number; stale_count: number; stale_unverified_count: number; ownership_unknown_count: number };
  credential_captures: {
    capture_id: string;
    subject_id: string;
    status: string;
    provider: string;
    captured_version: number;
    current_version: number | null;
    configured: boolean | null;
    captured_version_retained: boolean | null;
    state: "current" | "superseded" | "deleted-after-capture" | "not-captured" | "unavailable";
  }[];
  policy: {
    hot_reload: boolean;
    environment_read_at: string;
    process_environment_credentials_used: boolean;
    restart_action: string;
  };
}
