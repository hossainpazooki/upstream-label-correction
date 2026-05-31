package workflow

import "testing"

// NewEngine(nil, nil) is safe here: registerDefaults only populates the
// in-memory registry with phase-function values; it never touches the store or
// dispatcher. This keeps the test DB- and network-free.
func TestRegistryDefaults(t *testing.T) {
	e := NewEngine(nil, nil)

	wantPhases := map[string][]string{
		"biomarker_discovery": {"data_loading", "imputation", "feature_selection", "integration", "classification", "interpretation", "report"},
		"sample_qc":           {"data_loading", "classification_qc", "distance_matching", "cross_validation", "report"},
		"prompt_optimization": {"synthetic_cohort", "baseline_run", "dspy_compile", "optimized_run", "deploy"},
		"cosmo_pipeline":      {"data_loading", "imputation", "feature_selection", "classification", "cross_omics", "interpretation"},
	}

	for typ, phases := range wantPhases {
		def, ok := e.registry[typ]
		if !ok {
			t.Errorf("missing workflow definition %q", typ)
			continue
		}
		if def.Type != typ {
			t.Errorf("definition %q has Type %q", typ, def.Type)
		}
		if len(def.Phases) != len(phases) {
			t.Errorf("%q has %d phases, want %d", typ, len(def.Phases), len(phases))
			continue
		}
		for i, name := range phases {
			if def.Phases[i].Name != name {
				t.Errorf("%q phase[%d] = %q, want %q", typ, i, def.Phases[i].Name, name)
			}
			// A phase is executable via a single Activity or a fan-out group.
			if def.Phases[i].Activity == nil && len(def.Phases[i].Parallel) == 0 {
				t.Errorf("%q phase %q has no executable (nil Activity and empty Parallel)", typ, name)
			}
		}
	}
}

// biomarker_discovery imputes and selects features per modality concurrently.
func TestBiomarkerDiscoveryFansOutModalities(t *testing.T) {
	e := NewEngine(nil, nil)
	byName := map[string]Phase{}
	for _, p := range e.registry["biomarker_discovery"].Phases {
		byName[p.Name] = p
	}

	for _, name := range []string{"imputation", "feature_selection"} {
		p, ok := byName[name]
		if !ok {
			t.Fatalf("missing %q phase", name)
		}
		if p.Activity != nil {
			t.Errorf("%q should fan out, so Activity must be nil", name)
		}
		if len(p.Parallel) != len(biomarkerModalities) {
			t.Errorf("%q has %d branches, want %d (one per modality)", name, len(p.Parallel), len(biomarkerModalities))
		}
	}
}

func TestUnknownWorkflowTypeNotRegistered(t *testing.T) {
	e := NewEngine(nil, nil)
	if _, ok := e.registry["does_not_exist"]; ok {
		t.Error("unexpected workflow type registered")
	}
}

func TestMin(t *testing.T) {
	cases := []struct{ a, b, want int }{
		{1, 2, 1},
		{5, 3, 3},
		{4, 4, 4},
		{0, 10, 0},
	}
	for _, c := range cases {
		if got := min(c.a, c.b); got != c.want {
			t.Errorf("min(%d, %d) = %d, want %d", c.a, c.b, got, c.want)
		}
	}
}
