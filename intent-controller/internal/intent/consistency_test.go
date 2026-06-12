package intent

import (
	"testing"

	"github.com/precision-genomics/intent-controller/internal/models"
)

// TestCheckEvalConsistency covers the gap-#6 trust-boundary defense: the Go gate
// corroborates the ML service's self-reported `passed` against the numeric
// evidence in the same response, failing closed on anything inconsistent.
func TestCheckEvalConsistency(t *testing.T) {
	crit := models.EvalCriterion{Name: "mislabel_detection", Threshold: 0.80}

	// JSON numbers decode to float64; mirror that here.
	cases := []struct {
		name       string
		result     map[string]interface{}
		wantPassed bool
		wantErr    bool
	}{
		{
			name:       "consistent pass",
			result:     map[string]interface{}{"passed": true, "score": 0.92, "threshold": 0.80},
			wantPassed: true,
		},
		{
			name:   "consistent fail",
			result: map[string]interface{}{"passed": false, "score": 0.40, "threshold": 0.80},
		},
		{
			name:       "boundary pass (score == threshold)",
			result:     map[string]interface{}{"passed": true, "score": 0.80, "threshold": 0.80},
			wantPassed: true,
		},
		{
			name:       "vacuous pass (score 1.0)",
			result:     map[string]interface{}{"passed": true, "score": 1.0, "threshold": 0.80},
			wantPassed: true,
		},
		{
			name:    "LYING pass: passed=true but score < threshold",
			result:  map[string]interface{}{"passed": true, "score": 0.50, "threshold": 0.80},
			wantErr: true,
		},
		{
			name:    "weakened gate: returned threshold below requested",
			result:  map[string]interface{}{"passed": true, "score": 0.60, "threshold": 0.50},
			wantErr: true,
		},
		{
			name:    "missing passed",
			result:  map[string]interface{}{"score": 0.90, "threshold": 0.80},
			wantErr: true,
		},
		{
			name:    "non-numeric score",
			result:  map[string]interface{}{"passed": true, "score": "high", "threshold": 0.80},
			wantErr: true,
		},
		{
			name:    "missing threshold",
			result:  map[string]interface{}{"passed": true, "score": 0.90},
			wantErr: true,
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			passed, err := checkEvalConsistency(c.result, crit)
			if c.wantErr {
				if err == nil {
					t.Fatalf("expected an error, got nil (passed=%v)", passed)
				}
				if passed {
					t.Errorf("a flagged result must not report passed=true")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if passed != c.wantPassed {
				t.Errorf("passed = %v, want %v", passed, c.wantPassed)
			}
		})
	}
}
