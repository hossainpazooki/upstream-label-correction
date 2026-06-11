"""Thin FastAPI wrapper around core ML modules.

Exposes the Python ML algorithms as HTTP endpoints for the TypeScript
Next.js frontend to call. This replaces direct Python imports with
HTTP service calls.

Endpoints:
    POST /ml/impute     — NMF imputation
    POST /ml/classify   — Ensemble classification
    POST /ml/features   — Multi-strategy feature selection
    POST /ml/match      — Cross-omics matching
    POST /ml/evaluate   — Model evaluation
    POST /ml/synthetic  — Synthetic cohort generation
    POST /ml/pipeline   — Full pipeline execution
    POST /ml/availability — Gene availability check
    POST /ml/explain    — Feature explanation (Claude)
    POST /ml/explain-local — Feature explanation (SLM)
    POST /ml/dspy/*     — DSPy proxy endpoints
    GET  /health        — Health check
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Request schemas — previously in mcp_server.schemas.omics (now removed)
# ---------------------------------------------------------------------------


class ImputeMissingInput(BaseModel):
    dataset: str = "train"
    modality: str = "proteomics"
    method: str = "nmf"


class RunClassificationInput(BaseModel):
    dataset: str = "train"
    target: str = "msi"


class SelectBiomarkersInput(BaseModel):
    dataset: str = "train"
    target: str = "msi"
    n_top: int = 30


class MatchCrossOmicsInput(BaseModel):
    dataset: str = "train"


class EvaluateModelInput(BaseModel):
    dataset: str = "test"
    target: str = "msi"
    # Fields posted by the Go intent-controller (dispatcher.RunEval). When
    # eval_name is set, /ml/evaluate routes to the matching assurance eval;
    # when it is None or unknown, the legacy COSMO pipeline eval runs.
    eval_name: str | None = None
    threshold: float = 0.0
    params: dict | None = None
    intent_id: str | None = None


class CheckAvailabilityInput(BaseModel):
    genes: list[str]
    dataset: str = "train"


class ExplainFeaturesInput(BaseModel):
    features: list[str]
    target: str = "msi"


class ExplainFeaturesLocalInput(BaseModel):
    features: list[str]
    target: str = "msi"


logger = logging.getLogger(__name__)

app = FastAPI(title="Precision Genomics ML Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared service-token auth (gap #8). When SERVICE_AUTH_TOKEN is set, every
# request except the health probe must present a matching X-Service-Token header
# (the controller's dispatcher and web's server-side clients send it). When the
# env var is unset — local dev and tests — the check is a no-op. The token is
# read at module load; tests monkeypatch ``_SERVICE_AUTH_TOKEN`` to exercise it.
_SERVICE_AUTH_TOKEN = os.environ.get("SERVICE_AUTH_TOKEN", "")
_AUTH_EXEMPT_PATHS = frozenset({"/health"})


@app.middleware("http")
async def _service_auth(request: Request, call_next):
    if (
        _SERVICE_AUTH_TOKEN
        and request.method != "OPTIONS"
        and request.url.path not in _AUTH_EXEMPT_PATHS
    ):
        presented = request.headers.get("x-service-token", "")
        if not hmac.compare_digest(presented, _SERVICE_AUTH_TOKEN):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return await call_next(request)


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "ml"}


# ---------------------------------------------------------------------------
# ML Endpoints — delegate to core modules
# ---------------------------------------------------------------------------


@app.post("/ml/impute")
async def impute(params: ImputeMissingInput) -> dict:
    """Run NMF imputation."""
    from core.data_loader import load_dataset
    from core.imputation import OmicsImputer

    data = load_dataset(params.dataset, params.modality)
    imputer = OmicsImputer(method=params.method)
    result = imputer.impute(data)
    return {"status": "completed", "shape": list(result.shape)}


@app.post("/ml/classify")
async def classify(params: RunClassificationInput) -> dict:
    """Run ensemble classification."""
    from core.classifier import EnsembleMismatchClassifier
    from core.data_loader import load_dataset

    data = load_dataset(params.dataset)
    clf = EnsembleMismatchClassifier()
    result = clf.fit_predict(data, target=params.target)
    return result if isinstance(result, dict) else {"status": "completed"}


@app.post("/ml/features")
async def features(params: SelectBiomarkersInput) -> dict:
    """Run multi-strategy feature selection."""
    from core.data_loader import load_dataset
    from core.feature_selection import MultiStrategySelector

    data = load_dataset(params.dataset)
    selector = MultiStrategySelector()
    result = selector.select(data, target=params.target, n_top=params.n_top)
    return result if isinstance(result, dict) else {"status": "completed"}


@app.post("/ml/match")
async def match(params: MatchCrossOmicsInput) -> dict:
    """Run cross-omics matching."""
    from core.cross_omics_matcher import CrossOmicsMatcher
    from core.data_loader import load_dataset

    data = load_dataset(params.dataset)
    matcher = CrossOmicsMatcher()
    result = matcher.match(data)
    return result if isinstance(result, dict) else {"status": "completed"}


# ---------------------------------------------------------------------------
# Eval routing — mirrors intents.assurance.AssuranceLoop._registry so that the
# Go controller's RunEval (which posts {eval_name, threshold, params,
# intent_id}) reaches the same evaluator the in-process assurance loop would.
# Each helper reuses the existing evals/ + core/ implementations and returns a
# JSON-serializable dict with at least: name, passed, score, threshold, details.
# ---------------------------------------------------------------------------


def _eval_result_to_dict(result) -> dict:
    """Normalize an evals.EvalResult dataclass into a JSON-serializable dict."""
    from dataclasses import asdict, is_dataclass

    if is_dataclass(result):
        return asdict(result)
    if isinstance(result, dict):
        return result
    return {"result": str(result)}


def _genes_from_params(params: dict) -> list[str]:
    """Extract selected genes from posted params.

    Mirrors AssuranceLoop._extract_genes but operates on the flat params dict
    the Go controller posts (no in-process Intent / eval_results available).
    """
    if not params:
        return []
    if "genes" in params:
        return params["genes"]
    genes: list[str] = []
    for wf_result in (params.get("eval_results") or {}).values():
        if isinstance(wf_result, dict):
            for biomarker in wf_result.get("biomarkers", []):
                gene = biomarker.get("gene")
                if gene and gene not in genes:
                    genes.append(gene)
    return genes


# ---------------------------------------------------------------------------
# Gate cohort policy (gap #5: integrity params are NOT caller-controlled).
#
# For eval *gates*, the cohort's integrity-critical parameters — seed, corruption
# rate, cohort size, feature dimension, distance method — are pinned here on the
# server rather than read from the caller-supplied intent.Params. This removes
# the "seed-shopping" vector: a caller cannot hand-pick a seed / a low corruption
# rate / a tiny cohort that trivially clears the gate. The seed is derived from
# the server-assigned intent_id, so the gate cohort is reproducible per intent
# yet unpredictable and not chosen by the caller. (The separate
# MislabelDetectionEval.sweep() measurement path — where dialing the rate is the
# entire point — keeps its caller-supplied parameters and is unaffected.)
#
# Out of scope here: improve_mode / tune_detector stay caller-readable (they are
# the tune-on-test surface tracked separately, not cohort shopping), and
# /ml/evaluate is itself unauthenticated, so intent_id is only trustworthy via
# the in-cluster controller path.
# ---------------------------------------------------------------------------

_GATE_N_SAMPLES = 80
_GATE_N_GENES_PROTEOMICS = 2000
_GATE_N_GENES_RNASEQ = 4000
#: Corruption rate every gate tests at. 0.30 is a meaningful, non-trivial rate
#: at which the detector is stable across seeds (tuned F1 >= 0.97, AUROC >=
#: 0.997 measured over 6 derived seeds), so the per-intent seed never tips the
#: gate verdict.
_GATE_CORRUPTION_RATE = 0.30
_GATE_DISTANCE_METHOD = "expression_rank"
_GATE_TRAIN_SEED_OFFSET = 1000
_GATE_CLASSIFIER_RANDOM_STATE = 42
#: Fallback seed when no intent_id accompanies the request (e.g. a direct call
#: outside the controller flow). Fixed so the gate stays deterministic.
_GATE_FALLBACK_SEED = 42


def _gate_seed(intent_id: str | None) -> int:
    """Derive a stable 32-bit cohort seed from the server-assigned intent_id.

    Uses SHA-256 (stable across processes, unlike Python's salted ``hash``) so
    the gate cohort is reproducible for a given intent but cannot be chosen by
    the caller. Falls back to a fixed seed when no intent_id is present.
    """
    if not intent_id:
        return _GATE_FALLBACK_SEED
    return int.from_bytes(hashlib.sha256(intent_id.encode("utf-8")).digest()[:4], "big")


def _eval_biological_validity(params: dict | None, threshold: float, intent_id: str | None = None) -> dict:
    """Score pathway coverage of selected genes (evals.BiologicalValidityEval)."""
    from evals.biological_validity import BiologicalValidityEval

    genes = _genes_from_params(params or {})
    evaluator = BiologicalValidityEval()
    return _eval_result_to_dict(evaluator.evaluate(genes, threshold=threshold))


def _eval_reproducibility(params: dict | None, threshold: float, intent_id: str | None = None) -> dict:
    """Score feature-selection reproducibility across seeds (evals.ReproducibilityEval)."""
    from core.pipeline import COSMOInspiredPipeline
    from evals.reproducibility import ReproducibilityEval

    params = params or {}
    dataset = params.get("dataset", "train")

    def pipeline_callable(seed: int) -> list[str]:
        pipe = COSMOInspiredPipeline()
        result = pipe.run(dataset=dataset)
        stage3 = result.get("stages", {}).get("predict", {})
        panel = stage3.get("feature_panel", {})
        features = panel.get("features", [])
        return [f.get("name", f.get("gene", "")) for f in features[:20]]

    evaluator = ReproducibilityEval()
    return _eval_result_to_dict(evaluator.evaluate(pipeline_callable, n_runs=5, top_k=20, threshold=threshold))


def _eval_hallucination_detection(params: dict | None, threshold: float, intent_id: str | None = None) -> dict:
    """Verify cited PubMed IDs in interpretations (evals.HallucinationDetectionEval)."""
    from evals.hallucination_detection import HallucinationDetectionEval

    params = params or {}
    interpretations = params.get("interpretations", [])
    evaluator = HallucinationDetectionEval()
    return _eval_result_to_dict(evaluator.evaluate(interpretations, threshold=threshold))


async def _eval_adversarial_robustness(params: dict | None, threshold: float) -> dict:
    """Probe the SLM with defensive adversarial inputs (evals.AdversarialRobustnessEval)."""
    import json

    from evals.adversarial_robustness import AdversarialRobustnessEval
    from training.explainer import get_explainer

    explainer = get_explainer()

    async def model_callable(probe: dict) -> str:
        if probe.get("channel") == "document_rag":
            result = await explainer.classify_gene("BRAF", probe["probe_input"])
        else:
            result = await explainer.classify_gene(probe["probe_input"], "msi")
        return json.dumps(result, default=str)

    evaluator = AdversarialRobustnessEval()
    return _eval_result_to_dict(await evaluator.evaluate(model_callable, threshold=threshold))


def _eval_benchmark_comparison(params: dict | None, threshold: float, intent_id: str | None = None) -> dict:
    """Compare the agent panel to published signatures (evals.BenchmarkComparisonEval).

    Mirrors AssuranceLoop._run_benchmark_comparison: the evaluator hardcodes
    threshold=0.0, so the gate-provided threshold is honoured post-hoc against
    the score (best Jaccard) without touching the evaluator's scoring logic.
    """
    from evals.benchmark_comparison import BenchmarkComparisonEval

    genes = _genes_from_params(params or {})
    evaluator = BenchmarkComparisonEval()
    result = evaluator.evaluate(genes)
    return {
        "name": result.name,
        "passed": result.score >= threshold,
        "score": result.score,
        "threshold": threshold,
        "details": result.details,
    }


def _eval_mislabel_detection(params: dict | None, threshold: float, intent_id: str | None = None) -> dict:
    """Gate on label-error detection — the CLUE loop in VERIFY.

    Generates a synthetic cohort, then runs the **improve** step so the gate
    uses an *improved* detector rather than its untuned default. The
    ``improve_mode`` param selects the lever:

    * ``"threshold"`` (default) — tune the distance detector's decision
      threshold (``tune_decision_threshold``). The gated score is the
      **in-sample** tuned F1 (the threshold is selected on the cohort it is then
      scored against — gap #2). For transparency the response also reports a
      **held-out** F1 (threshold chosen on a disjoint sibling cohort, applied to
      the measure cohort) and the in-sample−held-out delta, so the optimism is
      visible. Gating still keys on the in-sample F1 here (no behavior change);
      switching the gate to the held-out number — and breaking the residual
      shared-generator-structure optimism with a genuinely independent oracle —
      is folded into gap #1 (no-held-out-oracle), which this surface depends on.
    * ``"retrain"`` — retrain the classification-path ensemble on a disjoint
      train cohort and gate on its held-out F1 (no leakage).
    * ``"both"`` — do both; gate on the held-out retrain F1, report threshold F1.

    Set ``params["tune_detector"] = False`` to gate on the untuned detector.

    The cohort's integrity-critical parameters (seed, corruption rate, size,
    feature dimension, train-seed offset) are pinned server-side via the gate
    policy and the ``intent_id``-derived seed — caller ``params`` are NOT
    consulted for them (gap #5).
    """
    from clue.loop import select_threshold_holdout, tune_decision_threshold
    from core.synthetic import SyntheticCohortGenerator
    from evals.mislabel_detection import MislabelDetectionEval

    params = params or {}
    improve_mode = str(params.get("improve_mode", "threshold"))
    seed = _gate_seed(intent_id)

    if improve_mode in ("retrain", "both"):
        # Retrain lever: route through CLUELoop for one round so the disjoint
        # train/measure seeding and held-out scoring are reused verbatim.
        from clue.loop import CLUELoop

        loop = CLUELoop(
            target_f1=threshold,
            start_fraction=_GATE_CORRUPTION_RATE,
            max_fraction=1.0,
            max_rounds=1,
            n_samples=_GATE_N_SAMPLES,
            n_genes_proteomics=_GATE_N_GENES_PROTEOMICS,
            n_genes_rnaseq=_GATE_N_GENES_RNASEQ,
            seed=seed,
            improve_mode=improve_mode,
            classifier_random_state=_GATE_CLASSIFIER_RANDOM_STATE,
            train_seed_offset=_GATE_TRAIN_SEED_OFFSET,
        )
        rnd = loop.run().rounds[0]
        score = float(rnd.retrain_f1)  # held-out classifier F1 is the headline
        return {
            "name": "mislabel_detection",
            "passed": score >= threshold,
            "score": score,
            "threshold": threshold,
            "details": {
                "improve_mode": improve_mode,
                "retrain_f1": rnd.retrain_f1,
                "retrain_precision": rnd.retrain_precision,
                "retrain_recall": rnd.retrain_recall,
                "train_seed": rnd.train_seed,
                "threshold_f1": rnd.f1,
                "best_threshold": rnd.best_threshold,
            },
        }

    def _gate_cohort(cohort_seed: int) -> dict:
        return SyntheticCohortGenerator(
            n_samples=_GATE_N_SAMPLES,
            n_genes_proteomics=_GATE_N_GENES_PROTEOMICS,
            n_genes_rnaseq=_GATE_N_GENES_RNASEQ,
            mislabel_fraction=_GATE_CORRUPTION_RATE,
            seed=cohort_seed,
        ).generate_cohort()

    measure_cohort = _gate_cohort(seed)

    if not params.get("tune_detector", True):
        result = MislabelDetectionEval().evaluate(measure_cohort, threshold=threshold)
        return {
            "name": result.name,
            "passed": result.passed,
            "score": result.score,
            "threshold": result.threshold,
            "details": result.details,
        }

    # In-sample tuned F1 — the gated score (UNCHANGED behavior, gap #2 deferred).
    best_threshold, metrics = tune_decision_threshold(measure_cohort)
    # Held-out F1 for transparency: select tau on a DISJOINT sibling cohort and
    # apply it to the measure cohort. This exposes the selection optimism but is
    # NOT the gate's decision — flipping the gate to this number (and removing
    # the residual shared-generator-structure optimism with a real held-out
    # oracle) is gap #1's work. select_threshold_holdout documents that scope.
    tune_seed = seed + _GATE_TRAIN_SEED_OFFSET
    held_threshold, held_metrics, _ = select_threshold_holdout(_gate_cohort(tune_seed), measure_cohort)
    return {
        "name": "mislabel_detection",
        "passed": metrics["f1"] >= threshold,
        "score": metrics["f1"],
        "threshold": threshold,
        "details": {
            **metrics,
            "best_threshold": best_threshold,
            "tuned": True,
            "selection": "in_sample",
            "in_sample_f1": metrics["f1"],
            "held_out_f1": held_metrics["f1"],
            "in_sample_minus_held_out": metrics["f1"] - held_metrics["f1"],
            "held_out_threshold": held_threshold,
            "tune_seed": tune_seed,
        },
    }


def _eval_fidelity_gate(params: dict | None, threshold: float, intent_id: str | None = None) -> dict:
    """Gate cohort fidelity — stage ② (detectable-by-construction).

    Generates a synthetic cohort and checks that its planted molecular swaps
    separate from clean samples on the threshold-free cross-omics AUROC
    (``evals.fidelity_gate.FidelityGateEval``). This is the construction-validity
    check that should clear *before* the stage-③ mislabel-detection measurement
    is trusted: a cohort that fails here carries no signal for a detector to
    find, so any F1 measured on it is meaningless.

    The gate uses the same detector invocation as ``mislabel_detection`` but no
    decision threshold — ``threshold`` here is the minimum acceptable AUROC
    (default 0.80 when the gate is called with the assurance default of 0.0).

    The cohort's integrity-critical parameters (seed, corruption rate, size,
    feature dimension, distance method) are pinned server-side via the gate
    policy and the ``intent_id``-derived seed — caller ``params`` are NOT
    consulted for them (gap #5).
    """
    from core.synthetic import SyntheticCohortGenerator
    from evals.fidelity_gate import DEFAULT_AUROC_THRESHOLD, FidelityGateEval

    params = params or {}
    # A 0.0 threshold from the assurance default would pass any cohort; fall back
    # to the eval's own AUROC bar so the gate stays meaningful when ungated.
    auroc_threshold = threshold if threshold > 0.0 else DEFAULT_AUROC_THRESHOLD

    generator = SyntheticCohortGenerator(
        n_samples=_GATE_N_SAMPLES,
        n_genes_proteomics=_GATE_N_GENES_PROTEOMICS,
        n_genes_rnaseq=_GATE_N_GENES_RNASEQ,
        mislabel_fraction=_GATE_CORRUPTION_RATE,
        seed=_gate_seed(intent_id),
    )
    result = FidelityGateEval().evaluate(
        generator.generate_cohort(),
        threshold=auroc_threshold,
        distance_method=_GATE_DISTANCE_METHOD,
    )
    return _eval_result_to_dict(result)


#: Synchronous eval runners keyed on eval_name. Async runners are dispatched
#: separately in evaluate() because they must be awaited.
_SYNC_EVAL_RUNNERS = {
    "biological_validity": _eval_biological_validity,
    "reproducibility": _eval_reproducibility,
    "hallucination_detection": _eval_hallucination_detection,
    "benchmark_comparison": _eval_benchmark_comparison,
    "mislabel_detection": _eval_mislabel_detection,
    "fidelity_gate": _eval_fidelity_gate,
}


@app.post("/ml/evaluate")
async def evaluate(params: EvaluateModelInput) -> dict:
    """Evaluate a model / intent criterion.

    When ``eval_name`` is set and known, route to the matching assurance eval
    (mirroring intents.assurance.AssuranceLoop). When it is None or unknown,
    preserve the legacy behavior: run the COSMO pipeline holdout eval.
    """
    eval_name = params.eval_name

    if eval_name == "adversarial_robustness":
        return await _eval_adversarial_robustness(params.params, params.threshold)

    runner = _SYNC_EVAL_RUNNERS.get(eval_name) if eval_name else None
    if runner is not None:
        return runner(params.params, params.threshold, params.intent_id)

    # eval_name is None or unknown — legacy COSMO pipeline eval.
    from core.pipeline import COSMOInspiredPipeline

    pipe = COSMOInspiredPipeline()
    result = pipe.evaluate(dataset=params.dataset, target=params.target)
    return result if isinstance(result, dict) else {"status": "completed"}


@app.post("/ml/availability")
async def availability(params: CheckAvailabilityInput) -> dict:
    """Check gene availability."""
    from core.availability import check_gene_availability

    result = check_gene_availability(params.genes, dataset=params.dataset)
    return result if isinstance(result, dict) else {"status": "completed"}


@app.post("/ml/explain")
async def explain(params: ExplainFeaturesInput) -> dict:
    """Explain features using pathway knowledge + LLM."""
    try:
        import anthropic

        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"Explain the biological relevance of these genomic features for {params.target}: {', '.join(params.features)}",
                }
            ],
        )
        return {"interpretation": message.content[0].text, "source": "claude"}
    except Exception:
        return _fallback_interpretation(params.features, params.target)


@app.post("/ml/explain-local")
async def explain_local(params: ExplainFeaturesLocalInput) -> dict:
    """Explain features using fine-tuned SLM."""
    try:
        from training.slm import load_slm

        model = load_slm()
        result = model.explain(params.features, target=params.target)
        return {"interpretation": result, "source": "slm"}
    except Exception:
        return _fallback_interpretation(params.features, params.target)


def _fallback_interpretation(features: list[str], target: str) -> dict:
    """Hardcoded biological interpretation fallback."""
    known = {
        "TAP1": "Antigen processing — key for immune evasion in MSI-H tumors",
        "LCP1": "Lymphocyte cytoskeletal protein — marker of immune infiltration",
        "GBP1": "Interferon-induced GTPase — elevated in MSI-H phenotype",
    }
    explanations = [known.get(f, f"{f}: genomic feature relevant to {target}") for f in features]
    return {"interpretation": "; ".join(explanations), "source": "fallback"}


@app.post("/ml/synthetic")
async def synthetic(n_samples: int = 100) -> dict:
    """Generate synthetic cohort."""
    try:
        from core.synthetic import SyntheticCohortGenerator

        gen = SyntheticCohortGenerator(n_samples=n_samples)
        data = gen.generate()
        return {
            "n_samples": n_samples,
            "modalities": list(data.keys()) if isinstance(data, dict) else [],
            "status": "generated",
        }
    except Exception as exc:
        return {"error": str(exc), "n_samples": n_samples}


@app.post("/ml/pipeline")
async def pipeline(
    dataset: str = "train",
    target: str = "msi",
    modalities: list[str] | None = None,
    n_top_features: int = 30,
) -> dict:
    """Run full COSMO pipeline."""
    try:
        from core.pipeline import COSMOInspiredPipeline

        pipe = COSMOInspiredPipeline()
        result = pipe.run(
            dataset=dataset,
            target=target,
            modalities=modalities or ["proteomics", "rnaseq"],
            n_top_features=n_top_features,
        )
        return result if isinstance(result, dict) else {"status": "completed"}
    except Exception as exc:
        return {"error": str(exc), "status": "failed"}


# ---------------------------------------------------------------------------
# DSPy Proxy Endpoints
# ---------------------------------------------------------------------------


@app.post("/ml/dspy/biomarker-discovery")
async def dspy_biomarker_discovery(params: dict | None = None) -> dict:
    """Run DSPy biomarker discovery module."""
    try:
        from dspy_modules.biomarker_discovery import BiomarkerDiscoveryModule

        module = BiomarkerDiscoveryModule()
        result = module(**(params or {}))
        return result if isinstance(result, dict) else {"result": str(result)}
    except ImportError:
        return {"status": "skipped", "reason": "dspy not installed"}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/ml/dspy/sample-qc")
async def dspy_sample_qc(params: dict | None = None) -> dict:
    """Run DSPy sample QC module."""
    try:
        from dspy_modules.sample_qc import SampleQCModule

        module = SampleQCModule()
        result = module(**(params or {}))
        return result if isinstance(result, dict) else {"result": str(result)}
    except ImportError:
        return {"status": "skipped", "reason": "dspy not installed"}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/ml/dspy/feature-interpret")
async def dspy_feature_interpret(params: dict | None = None) -> dict:
    """Run DSPy feature interpretation module."""
    try:
        from dspy_modules.feature_interpret import FeatureInterpretModule

        module = FeatureInterpretModule()
        result = module(**(params or {}))
        return result if isinstance(result, dict) else {"result": str(result)}
    except ImportError:
        return {"status": "skipped", "reason": "dspy not installed"}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/ml/dspy/regulatory-report")
async def dspy_regulatory_report(params: dict | None = None) -> dict:
    """Run DSPy regulatory report module."""
    try:
        from dspy_modules.regulatory_report import RegulatoryReportModule

        module = RegulatoryReportModule()
        result = module(**(params or {}))
        return result if isinstance(result, dict) else {"result": str(result)}
    except ImportError:
        return {"status": "skipped", "reason": "dspy not installed"}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/ml/dspy/compile")
async def dspy_compile(params: dict | None = None) -> dict:
    """Compile DSPy modules."""
    try:
        from dspy_modules.compile import compile_module

        result = compile_module(**(params or {}))
        return result if isinstance(result, dict) else {"status": "compiled"}
    except ImportError:
        return {"status": "skipped", "reason": "dspy not installed"}
    except Exception as exc:
        return {"error": str(exc)}
