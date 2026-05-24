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

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


@app.post("/ml/evaluate")
async def evaluate(params: EvaluateModelInput) -> dict:
    """Evaluate model on holdout data."""
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
