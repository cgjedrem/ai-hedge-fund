export interface Capabilities {
  mode: "live" | "demo";
  read_only: boolean;
  writes: boolean;
  network: boolean;
  protected_names: string[];
  mutation_token: string | null;
  deferred_actions: Record<string, string>;
}

export interface ApiErrorShape {
  detail: string | { message?: string }[];
}

export interface ModelOption {
  label: string;
  id: string;
  provider: string;
}

export interface StrategyOption {
  name: string;
  title: string;
  models: string[];
  kind: "systematic" | "discretionary";
  mode: string;
}

export interface Catalog {
  models: ModelOption[];
  strategies: StrategyOption[];
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
  runner: RunnerState;
}

export interface PaperCollection {
  items: PaperSummary[];
  errors: { name: string; error: string }[];
}

export interface RunnerState {
  status: string;
  available: boolean;
  reason: string;
}

export interface Position {
  ticker: string;
  shares: number;
  mark: number | null;
  market_value: number | null;
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
  spec: Record<string, unknown>;
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
  ledger: { ok: boolean; error: string | null };
  runner: RunnerState;
  live_value: {
    status: string;
    value: number | null;
    as_of: string | null;
    provenance: string | null;
    reason: string;
  };
  scorecard: ScoreMetrics | null;
  scorecard_error: string | null;
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
}

export interface Job {
  id: string;
  fund: string;
  provider: string;
  model: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  submitted_at: string;
  started_at: string | null;
  completed_at: string | null;
  report_id: string | null;
  error: string | null;
}

export interface Settings {
  model: string;
  models: ModelOption[];
  providers: { provider: string; requires_key: boolean; configured: boolean }[];
  data_provider: string;
  network_enabled: boolean;
}
