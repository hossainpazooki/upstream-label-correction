package workflow

import (
	"context"

	"github.com/precision-genomics/intent-controller/internal/activity"
)

// Phase implementations that dispatch to the ML service via the activity dispatcher.

func phaseLoadAndValidate(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	dataset := stringParam(params, "dataset", "train")
	modalities := stringSliceParam(params, "modalities", []string{"proteomics", "rnaseq"})
	return d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":     "load_and_validate",
		"dataset":    dataset,
		"modalities": modalities,
	})
}

func phaseLoadClinical(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	dataset := stringParam(params, "dataset", "train")
	return d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":  "load_clinical",
		"dataset": dataset,
	})
}

func phaseImpute(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	dataset := stringParam(params, "dataset", "train")
	modalities := stringSliceParam(params, "modalities", []string{"proteomics", "rnaseq"})
	results := map[string]interface{}{}
	for _, mod := range modalities {
		result, err := d.CallML(ctx, "/ml/impute", map[string]interface{}{
			"dataset":  dataset,
			"modality": mod,
		})
		if err != nil {
			return nil, err
		}
		results[mod] = result
	}
	return results, nil
}

func phaseSelectFeatures(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	dataset := stringParam(params, "dataset", "train")
	target := stringParam(params, "target", "msi")
	nTop := intParam(params, "n_top_features", 30)
	modalities := stringSliceParam(params, "modalities", []string{"proteomics", "rnaseq"})

	results := map[string]interface{}{}
	for _, mod := range modalities {
		result, err := d.CallML(ctx, "/ml/features", map[string]interface{}{
			"dataset":        dataset,
			"target":         target,
			"modality":       mod,
			"n_top_features": nTop,
		})
		if err != nil {
			return nil, err
		}
		results[mod] = result
	}
	return results, nil
}

func phaseIntegrateAndFilter(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	// Gather feature panels from previous step
	featurePanels := []interface{}{}
	if fs, ok := prev["feature_selection"]; ok {
		if fsMap, ok := fs.(map[string]interface{}); ok {
			for _, v := range fsMap {
				featurePanels = append(featurePanels, v)
			}
		}
	}
	return d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":         "integrate_and_filter",
		"feature_panels": featurePanels,
	})
}

func phaseTrainAndEvaluate(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	dataset := stringParam(params, "dataset", "train")
	target := stringParam(params, "target", "msi")
	return d.CallML(ctx, "/ml/classify", map[string]interface{}{
		"dataset": dataset,
		"target":  target,
	})
}

func phaseMatchCrossOmics(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	dataset := stringParam(params, "dataset", "train")
	return d.CallML(ctx, "/ml/match", map[string]interface{}{
		"dataset": dataset,
	})
}

func phaseInterpret(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	target := stringParam(params, "target", "msi")
	features := []interface{}{}
	if integration, ok := prev["integration"]; ok {
		if im, ok := integration.(map[string]interface{}); ok {
			if f, ok := im["features"]; ok {
				features, _ = f.([]interface{})
			}
		}
	}
	return d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":   "interpret",
		"target":   target,
		"features": features,
	})
}

func phaseCompileReport(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	return d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":  "compile_report",
		"results": prev,
	})
}

func phaseClassificationQC(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	dataset := stringParam(params, "dataset", "train")
	methods := stringSliceParam(params, "classification_methods", []string{"ensemble"})
	return d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":                 "classification_qc",
		"dataset":                dataset,
		"classification_methods": methods,
	})
}

func phaseDistanceMatrix(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	dataset := stringParam(params, "dataset", "train")
	nIterations := intParam(params, "n_iterations", 100)
	return d.CallML(ctx, "/ml/match", map[string]interface{}{
		"dataset":      dataset,
		"n_iterations": nIterations,
	})
}

func phaseCrossValidate(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	classResult := extractStringSlice(prev, "classification_qc", "flagged_samples")
	distResult := extractStringSlice(prev, "distance_matching", "flagged_samples")
	return d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":                    "cross_validate_flags",
		"flagged_by_classification": classResult,
		"flagged_by_distance":       distResult,
	})
}

func phaseGenerateSynthetic(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	return d.CallML(ctx, "/ml/synthetic", params)
}

func phaseRunPipeline(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	return d.CallML(ctx, "/ml/pipeline", params)
}

func phaseDSPYCompile(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	return d.CallML(ctx, "/ml/dspy/compile", map[string]interface{}{
		"module":   stringParam(params, "module", "biomarker_discovery"),
		"strategy": stringParam(params, "strategy", "mipro"),
	})
}

func phaseCompareAndDeploy(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
	return d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":  "compare_and_deploy",
		"results": prev,
	})
}

// --- biomarker-discovery fan-out (per-modality, run concurrently) ---

// biomarkerModalities are the omics modalities the biomarker-discovery workflow
// processes independently before integration. COSMO handles proteomics and
// RNA-Seq on separate paths, so they fan out and run concurrently.
var biomarkerModalities = []string{"proteomics", "rnaseq"}

// imputeModality imputes a single modality, keyed by modality name so fan-out
// branches merge into {proteomics: ..., rnaseq: ...} — the same shape the
// sequential phaseImpute produced.
func imputeModality(modality string) PhaseFunc {
	return func(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
		dataset := stringParam(params, "dataset", "train")
		result, err := d.CallML(ctx, "/ml/impute", map[string]interface{}{
			"dataset":  dataset,
			"modality": modality,
		})
		if err != nil {
			return nil, err
		}
		return map[string]interface{}{modality: result}, nil
	}
}

// selectFeaturesForModality selects features for a single modality, keyed by
// modality name (see imputeModality for the merge contract).
func selectFeaturesForModality(modality string) PhaseFunc {
	return func(ctx context.Context, d *activity.Dispatcher, params, prev map[string]interface{}) (map[string]interface{}, error) {
		dataset := stringParam(params, "dataset", "train")
		target := stringParam(params, "target", "msi")
		nTop := intParam(params, "n_top_features", 30)
		result, err := d.CallML(ctx, "/ml/features", map[string]interface{}{
			"dataset":        dataset,
			"target":         target,
			"modality":       modality,
			"n_top_features": nTop,
		})
		if err != nil {
			return nil, err
		}
		return map[string]interface{}{modality: result}, nil
	}
}

// fanOutModalities builds one parallel branch per biomarker modality.
func fanOutModalities(build func(string) PhaseFunc) []PhaseFunc {
	branches := make([]PhaseFunc, 0, len(biomarkerModalities))
	for _, modality := range biomarkerModalities {
		branches = append(branches, build(modality))
	}
	return branches
}

// helpers

func stringParam(params map[string]interface{}, key, def string) string {
	if v, ok := params[key].(string); ok && v != "" {
		return v
	}
	return def
}

func intParam(params map[string]interface{}, key string, def int) int {
	if v, ok := params[key].(float64); ok {
		return int(v)
	}
	return def
}

func stringSliceParam(params map[string]interface{}, key string, def []string) []string {
	if v, ok := params[key].([]interface{}); ok {
		result := make([]string, 0, len(v))
		for _, item := range v {
			if s, ok := item.(string); ok {
				result = append(result, s)
			}
		}
		if len(result) > 0 {
			return result
		}
	}
	return def
}

func extractStringSlice(prev map[string]interface{}, phaseKey, fieldKey string) []string {
	if phase, ok := prev[phaseKey].(map[string]interface{}); ok {
		if items, ok := phase[fieldKey].([]interface{}); ok {
			result := make([]string, 0, len(items))
			for _, item := range items {
				if s, ok := item.(string); ok {
					result = append(result, s)
				}
			}
			return result
		}
	}
	return []string{}
}
