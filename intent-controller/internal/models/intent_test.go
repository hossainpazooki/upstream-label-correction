package models

import "testing"

func TestIsValidTransition_Valid(t *testing.T) {
	valid := []struct{ from, to IntentStatus }{
		{IntentStatusDeclared, IntentStatusResolving},
		{IntentStatusResolving, IntentStatusActive},
		{IntentStatusResolving, IntentStatusBlocked},
		{IntentStatusBlocked, IntentStatusResolving},
		{IntentStatusActive, IntentStatusVerifying},
		{IntentStatusVerifying, IntentStatusAchieved},
		{IntentStatusDeclared, IntentStatusCancelled},
		{IntentStatusActive, IntentStatusFailed},
		{IntentStatusVerifying, IntentStatusFailed},
	}
	for _, c := range valid {
		if !IsValidTransition(c.from, c.to) {
			t.Errorf("expected %s -> %s to be valid", c.from, c.to)
		}
	}
}

func TestIsValidTransition_Invalid(t *testing.T) {
	invalid := []struct{ from, to IntentStatus }{
		{IntentStatusDeclared, IntentStatusActive},     // must resolve first
		{IntentStatusDeclared, IntentStatusAchieved},   // cannot skip the loop
		{IntentStatusResolving, IntentStatusVerifying}, // must pass through active
		{IntentStatusActive, IntentStatusDeclared},     // no going back
		{IntentStatusAchieved, IntentStatusActive},     // terminal
		{IntentStatusFailed, IntentStatusResolving},    // terminal
		{IntentStatusCancelled, IntentStatusResolving}, // terminal
		{IntentStatusDeclared, IntentStatusFailed},     // declared must resolve or cancel
		{IntentStatusBlocked, IntentStatusActive},      // blocked must re-resolve first
		{IntentStatusBlocked, IntentStatusFailed},      // blocked may only resolve or cancel
	}
	for _, c := range invalid {
		if IsValidTransition(c.from, c.to) {
			t.Errorf("expected %s -> %s to be invalid", c.from, c.to)
		}
	}
}

func TestTerminalStates(t *testing.T) {
	for _, s := range []IntentStatus{IntentStatusAchieved, IntentStatusFailed, IntentStatusCancelled} {
		if !TerminalStates[s] {
			t.Errorf("expected %s to be terminal", s)
		}
	}
	for _, s := range []IntentStatus{
		IntentStatusDeclared, IntentStatusResolving, IntentStatusBlocked,
		IntentStatusActive, IntentStatusVerifying,
	} {
		if TerminalStates[s] {
			t.Errorf("expected %s to be non-terminal", s)
		}
	}
}

// Terminal states must be sinks: no legal outgoing transition.
func TestTerminalStatesAreSinks(t *testing.T) {
	all := []IntentStatus{
		IntentStatusDeclared, IntentStatusResolving, IntentStatusBlocked,
		IntentStatusActive, IntentStatusVerifying, IntentStatusAchieved,
		IntentStatusFailed, IntentStatusCancelled,
	}
	for term := range TerminalStates {
		for _, to := range all {
			if IsValidTransition(term, to) {
				t.Errorf("terminal state %s should be a sink, found -> %s", term, to)
			}
		}
	}
}

func TestIntentSpecsRegistry(t *testing.T) {
	for _, typ := range []string{"analysis", "training", "validation"} {
		spec, ok := IntentSpecs[typ]
		if !ok {
			t.Fatalf("missing intent spec for %q", typ)
		}
		if spec.IntentType != typ {
			t.Errorf("spec %q has IntentType %q", typ, spec.IntentType)
		}
	}

	training := IntentSpecs["training"]
	if !training.TriggersDeploy {
		t.Error("training intent should trigger deploy")
	}
	if training.MaxGPUCount != 4 {
		t.Errorf("training MaxGPUCount = %d, want 4", training.MaxGPUCount)
	}
	// Training gates its auto-deploy on the evals that probe the fine-tuned SLM.
	assertCriteria(t, "training", training.EvalCriteria, map[string]float64{
		"hallucination_detection": 0.90,
		"adversarial_robustness":  1.0,
	})

	analysis := IntentSpecs["analysis"]
	assertCriteria(t, "analysis", analysis.EvalCriteria, map[string]float64{
		"biological_validity": 0.60,
		"reproducibility":     0.85,
	})

	// Validation leads with the CLUE detection-fidelity evals, then the LLM checks.
	validation := IntentSpecs["validation"]
	assertCriteria(t, "validation", validation.EvalCriteria, map[string]float64{
		"fidelity_gate":           0.80,
		"mislabel_detection":      0.70,
		"hallucination_detection": 0.90,
		"adversarial_robustness":  1.0,
	})
	if infra := validation.RequiredInfra; len(infra) != 0 {
		t.Errorf("validation should need no infra, got %v", infra)
	}
}

// assertCriteria checks an intent's eval criteria match the expected
// name→threshold set exactly (no missing, extra, or mismatched entries).
func assertCriteria(t *testing.T, intentType string, got []EvalCriterion, want map[string]float64) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("%s should have %d eval criteria, got %d", intentType, len(want), len(got))
	}
	for _, c := range got {
		w, ok := want[c.Name]
		if !ok {
			t.Errorf("unexpected %s criterion %q", intentType, c.Name)
		} else if w != c.Threshold {
			t.Errorf("%s criterion %q threshold = %v, want %v", intentType, c.Name, c.Threshold, w)
		}
	}
}

func TestCreateIntentRequestValidate(t *testing.T) {
	t.Run("defaults requested_by", func(t *testing.T) {
		req := CreateIntentRequest{IntentType: "analysis"}
		if err := req.Validate(); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if req.RequestedBy != "agent" {
			t.Errorf("RequestedBy default = %q, want agent", req.RequestedBy)
		}
	})

	t.Run("preserves explicit requested_by", func(t *testing.T) {
		req := CreateIntentRequest{IntentType: "training", RequestedBy: "alice"}
		if err := req.Validate(); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if req.RequestedBy != "alice" {
			t.Errorf("RequestedBy = %q, want alice", req.RequestedBy)
		}
	})

	t.Run("rejects missing type", func(t *testing.T) {
		req := CreateIntentRequest{}
		if err := req.Validate(); err == nil {
			t.Error("expected error for missing intent_type")
		}
	})

	t.Run("rejects unknown type", func(t *testing.T) {
		req := CreateIntentRequest{IntentType: "nope"}
		if err := req.Validate(); err == nil {
			t.Error("expected error for unknown intent type")
		}
	})
}
