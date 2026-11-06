export type Role = "HR_ADMIN" | "HRBP" | "LEADER";
export type Unit = "count" | "percent" | "years" | "hours" | "ratio";

export interface Me {
  email: string;
  role: Role;
  label: string;
  departments: string[];
  sees_individuals: boolean;
  scope: string;
}

export interface MetricInfo {
  key: string;
  label: string;
  unit: Unit;
  definition: string;
  formula: string;
  point_in_time?: boolean;
  higher_is_better: boolean | null;
}

export interface DimensionInfo {
  key: string;
  label: string;
  time: boolean;
  values: { code: string; label: string }[] | null;
}

export interface Meta {
  first_month: string;
  last_month: string;
  min_group_size: number;
  scope: string[] | null;
  metrics: MetricInfo[];
  dimensions: DimensionInfo[];
  examples: string[];
}

export interface Filter {
  dimension: string;
  values: string[];
}

export interface Spec {
  metric: string;
  dimensions: string[];
  filters: Filter[];
  period: { start: string; end: string };
  order: "value_desc" | "value_asc" | null;
  limit: number | null;
}

export interface ResultRow {
  value: number | null;
  population: number;
  suppressed: boolean;
  [key: string]: string | number | boolean | null;
}

export interface QueryResult {
  spec: Spec;
  description: string;
  metric: MetricInfo;
  dimensions: { key: string; label: string }[];
  rows: ResultRow[];
  suppressed: number;
  sql: string;
  params: Record<string, unknown>;
}

export interface Kpi {
  key: string;
  label: string;
  unit: Unit;
  definition: string;
  higher_is_better: boolean | null;
  value: number | null;
  previous: number | null;
  period: string;
}

export interface Dashboard {
  period: { start: string; end: string };
  previous_period: { start: string; end: string };
  scope: string[] | null;
  kpis: Kpi[];
  headcount_trend: QueryResult;
  resignations_trend: QueryResult;
  hires_trend: QueryResult;
  turnover_by_department: QueryResult;
  turnover_by_tenure: QueryResult;
  turnover_by_age: QueryResult;
}

export interface AskResponse {
  question: string;
  parser: "rules" | "gemini";
  status: "ok" | "unsupported" | "invalid";
  message?: string;
  suggestions?: string[];
  result?: QueryResult;
  spec?: Spec;
}

export interface Cohort {
  cohort: string;
  label: string;
  hires: number;
  suppressed: boolean;
  points: { months: number; retained: number | null }[];
}

export interface Cohorts {
  checkpoints: number[];
  cohorts: Cohort[];
  pooled: { months: number; retained: number | null; hires: number }[];
  scope: string[] | null;
}

export interface Driver {
  feature: string;
  text: string;
  contribution: number;
}

export interface RiskSummary {
  model_version: string;
  scored_month: string;
  horizon_months: number;
  scored: number;
  high: number;
  elevated: number;
  flagged: number;
  departments: {
    department: string;
    department_label: string;
    scored: number;
    suppressed: boolean;
    high: number | null;
    elevated: number | null;
    high_share: number | null;
    mean_probability: number | null;
  }[];
  drivers: { feature: string; label: string; count: number; share: number | null }[];
  test_metrics: {
    roc_auc: number;
    pr_auc: number;
    base_rate: number;
    top_10pct: { flagged: number; precision: number; recall: number; lift: number } | null;
  };
  scope: string[] | null;
}

export interface RiskEmployee {
  employee_no: string;
  name: string;
  department: string;
  department_label: string;
  location: string;
  grade: string;
  tenure_months: number;
  employment_type: string;
  probability: number;
  band: "high" | "elevated" | "low";
  drivers: Driver[];
}

export interface FairnessGroup {
  group: string;
  n: number;
  observed_rate: number;
  mean_predicted: number;
  flag_rate: number;
  recall: number | null;
}

export interface ModelCard {
  version: string;
  trained_at: string;
  notes: string | null;
  metrics: {
    rows: Record<string, number>;
    best_iteration: number;
    test_months: [string, string];
    base_rate: number;
    roc_auc: number;
    pr_auc: number;
    brier_raw: number;
    brier_calibrated: number;
    valid_base_rate: number;
    mean_predicted: number;
    top_10pct_all_test_months: { flagged: number; precision: number; recall: number; lift: number };
    point_in_time: {
      month: string;
      employees: number;
      leavers_next_6m: number;
      roc_auc: number | null;
      top_10pct: { flagged: number; precision: number; recall: number; lift: number };
    };
    ceiling: {
      roc_auc: number;
      pr_auc: number;
      point_in_time_top_10pct: { flagged: number; precision: number; recall: number; lift: number };
    };
  };
  fairness: {
    threshold_top_10pct: number;
    gender: { groups: FairnessGroup[]; flag_rate_ratio_min_max: number | null };
    age_band: { groups: FairnessGroup[]; flag_rate_ratio_min_max: number | null };
  };
  importance: { feature: string; label: string; mean_abs_shap: number; gain_share: number }[];
  calibration: { bucket: number; predicted: number; observed: number; n: number }[];
}
