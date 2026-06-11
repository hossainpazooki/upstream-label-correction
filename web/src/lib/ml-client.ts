/**
 * Typed HTTP client for the Python ML microservice.
 * Used for synchronous operations (<5s): impute, classify, features, match, evaluate.
 */

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://localhost:8000";

// Shared service token for the internal control plane (gap #8). Server-only —
// never a NEXT_PUBLIC_ var. Attached to every ml_service call as X-Service-Token
// when set; unset (local dev) sends no header and ml_service runs in bypass.
const SERVICE_AUTH_TOKEN = process.env.SERVICE_AUTH_TOKEN;

export function mlHeaders(base: Record<string, string> = {}): Record<string, string> {
  return SERVICE_AUTH_TOKEN
    ? { ...base, "X-Service-Token": SERVICE_AUTH_TOKEN }
    : base;
}

export class MLServiceError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "MLServiceError";
  }
}

async function mlFetch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${ML_SERVICE_URL}${path}`, {
    method: "POST",
    headers: mlHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new MLServiceError(res.status, text);
  }
  return res.json() as Promise<T>;
}

async function mlGet<T>(path: string): Promise<T> {
  const res = await fetch(`${ML_SERVICE_URL}${path}`, {
    headers: mlHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new MLServiceError(res.status, text);
  }
  return res.json() as Promise<T>;
}

// --- ML Service Endpoints ---

export interface ImputeParams {
  dataset?: string;
  modality?: string;
  strategy?: string;
  classify_missingness?: boolean;
}

export interface ImputeResult {
  genes_before: number;
  genes_imputed_mar: number;
  genes_assigned_mnar_zero: number;
  nmf_reconstruction_error: number;
  features_recovered: number;
  comparison: Record<string, number>;
}

export function impute(params: ImputeParams): Promise<ImputeResult> {
  return mlFetch("/ml/impute", params);
}

export interface ClassifyParams {
  features?: string[] | string;
  target?: string;
  classifiers?: string[] | string;
  phenotype_strategy?: string;
  meta_learner?: string;
  test_size?: number;
  cv_folds?: number;
}

export interface ClassifyResult {
  ensemble_f1: number;
  per_classifier_f1: Record<string, number>;
  best_strategy: string;
  strategy_comparison: Record<string, number>;
  feature_importances: Array<Record<string, unknown>>;
  comparison_to_baseline: Record<string, number>;
}

export function classify(params: ClassifyParams): Promise<ClassifyResult> {
  return mlFetch("/ml/classify", params);
}

export interface FeatureSelectionParams {
  target?: string;
  modality?: string;
  methods?: string[] | string;
  integration?: string;
  n_top?: number;
  p_value_correction?: string;
}

export interface FeatureSelectionResult {
  biomarkers: Array<Record<string, unknown>>;
  method_agreement: Record<string, string[]>;
  comparison_to_original: Record<string, number>;
}

export function selectFeatures(
  params: FeatureSelectionParams,
): Promise<FeatureSelectionResult> {
  return mlFetch("/ml/features", params);
}

export interface MatchParams {
  dataset?: string;
  distance_method?: string;
  n_iterations?: number;
  gene_sampling_fraction?: number;
}

export interface MatchResult {
  distance_matrix_info: Record<string, unknown>;
  identified_mismatches: Array<Record<string, unknown>>;
  iteration_agreement: number;
}

export function matchCrossOmics(params: MatchParams): Promise<MatchResult> {
  return mlFetch("/ml/match", params);
}

export interface EvaluateParams {
  model_id?: string;
  test_data?: string;
  compare_to_baseline?: boolean;
}

export interface EvaluateResult {
  f1_score: number;
  precision: number;
  recall: number;
  confusion_matrix: number[][];
  roc_auc: number;
  baseline_comparison: Record<string, number>;
}

export function evaluate(params: EvaluateParams): Promise<EvaluateResult> {
  return mlFetch("/ml/evaluate", params);
}

export interface SyntheticParams {
  n_samples?: number;
  targets?: string[];
}

export function generateSynthetic(
  params: SyntheticParams,
): Promise<Record<string, unknown>> {
  return mlFetch("/ml/synthetic", params);
}

export interface PipelineParams {
  dataset?: string;
  target?: string;
  modalities?: string[];
  n_top_features?: number;
  cv_folds?: number;
}

export function runPipeline(
  params: PipelineParams,
): Promise<Record<string, unknown>> {
  return mlFetch("/ml/pipeline", params);
}

// DSPy proxy endpoints
export interface DspyParams {
  [key: string]: unknown;
}

export function dspyBiomarkerDiscovery(
  params: DspyParams,
): Promise<Record<string, unknown>> {
  return mlFetch("/ml/dspy/biomarker-discovery", params);
}

export function dspySampleQC(
  params: DspyParams,
): Promise<Record<string, unknown>> {
  return mlFetch("/ml/dspy/sample-qc", params);
}

export function dspyFeatureInterpret(
  params: DspyParams,
): Promise<Record<string, unknown>> {
  return mlFetch("/ml/dspy/feature-interpret", params);
}

export function dspyRegulatoryReport(
  params: DspyParams,
): Promise<Record<string, unknown>> {
  return mlFetch("/ml/dspy/regulatory-report", params);
}

export function dspyCompile(
  params: DspyParams,
): Promise<Record<string, unknown>> {
  return mlFetch("/ml/dspy/compile", params);
}

// Health check
export function mlHealth(): Promise<{ status: string }> {
  return mlGet("/health");
}
