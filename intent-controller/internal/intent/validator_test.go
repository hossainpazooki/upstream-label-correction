package intent

import "testing"

func TestValidateIntentParams_UnknownType(t *testing.T) {
	if err := ValidateIntentParams("bogus", nil); err == nil {
		t.Error("expected error for unknown intent type")
	}
}

func TestValidateAnalysisParams(t *testing.T) {
	ok := []map[string]interface{}{
		{"target": "msi"},
		{"target": "gender"},
		{"target": "mismatch"},
		{},                                                  // target is optional
		{"modalities": []interface{}{"proteomics", "rnaseq"}},
	}
	for _, p := range ok {
		if err := ValidateIntentParams("analysis", p); err != nil {
			t.Errorf("unexpected error for %v: %v", p, err)
		}
	}

	bad := []map[string]interface{}{
		{"target": "xyz"},                       // invalid target
		{"target": ""},                          // empty target
		{"modalities": []interface{}{"badmod"}}, // invalid modality
		{"modalities": "proteomics"},            // not an array
	}
	for _, p := range bad {
		if err := ValidateIntentParams("analysis", p); err == nil {
			t.Errorf("expected error for %v", p)
		}
	}
}

func TestValidateTrainingParams(t *testing.T) {
	if err := ValidateIntentParams("training", map[string]interface{}{
		"model_type": "slm", "num_gpus": float64(2),
	}); err != nil {
		t.Errorf("unexpected error: %v", err)
	}

	bad := []map[string]interface{}{
		{"model_type": "bogus"},  // invalid model_type
		{"num_gpus": float64(8)}, // out of range (1-4)
		{"num_gpus": float64(0)}, // out of range
		{"num_gpus": "two"},      // not numeric
	}
	for _, p := range bad {
		if err := ValidateIntentParams("training", p); err == nil {
			t.Errorf("expected error for %v", p)
		}
	}
}

func TestValidateValidationParams(t *testing.T) {
	if err := ValidateIntentParams("validation", map[string]interface{}{"dataset": "train"}); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}
