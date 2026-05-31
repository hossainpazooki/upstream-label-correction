package workflow

import "testing"

// phaseNames extracts the ordered Name slice from a phase list so tests can
// compare against an expected sequence without touching the activity funcs.
func phaseNames(phases []Phase) []string {
	names := make([]string, len(phases))
	for i, p := range phases {
		names[i] = p.Name
	}
	return names
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func TestRemainingPhases(t *testing.T) {
	phases := []Phase{
		{Name: "a"},
		{Name: "b"},
		{Name: "c"},
		{Name: "d"},
	}

	cases := []struct {
		name      string
		completed []string
		want      []string
	}{
		{
			name:      "nil completed runs all phases in order",
			completed: nil,
			want:      []string{"a", "b", "c", "d"},
		},
		{
			name:      "empty completed runs all phases in order",
			completed: []string{},
			want:      []string{"a", "b", "c", "d"},
		},
		{
			name:      "skips completed prefix, preserves order",
			completed: []string{"a", "b"},
			want:      []string{"c", "d"},
		},
		{
			name:      "skips completed phases anywhere, preserves order",
			completed: []string{"b"},
			want:      []string{"a", "c", "d"},
		},
		{
			name:      "all completed yields no remaining phases",
			completed: []string{"a", "b", "c", "d"},
			want:      []string{},
		},
		{
			name:      "unknown completed names are ignored",
			completed: []string{"x", "y", "a"},
			want:      []string{"b", "c", "d"},
		},
		{
			name:      "completed order does not matter",
			completed: []string{"c", "a"},
			want:      []string{"b", "d"},
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := phaseNames(remainingPhases(phases, c.completed))
			if !equalStrings(got, c.want) {
				t.Errorf("remainingPhases(..., %v) = %v, want %v", c.completed, got, c.want)
			}
		})
	}
}

// remainingPhases must return the actual Phase values (with their executables),
// not just names, so the resumed run can execute them.
func TestRemainingPhasesPreservesPhaseValues(t *testing.T) {
	called := false
	phases := []Phase{
		{Name: "done"},
		{Name: "todo", Activity: phaseReturning(map[string]interface{}{"ok": true})},
	}

	remaining := remainingPhases(phases, []string{"done"})
	if len(remaining) != 1 || remaining[0].Name != "todo" {
		t.Fatalf("remaining = %v, want single phase 'todo'", phaseNames(remaining))
	}
	if remaining[0].Activity == nil {
		t.Fatal("resumed phase lost its Activity function")
	}
	if _, err := remaining[0].Activity(nil, nil, nil, nil); err != nil {
		t.Fatalf("resumed phase Activity errored: %v", err)
	}
	called = true
	if !called {
		t.Fatal("unreachable")
	}
}

// Empty input phases yields empty (not nil-panicking) output regardless of
// completed contents.
func TestRemainingPhasesEmptyDefinition(t *testing.T) {
	if got := remainingPhases(nil, []string{"a"}); len(got) != 0 {
		t.Errorf("remainingPhases(nil, ...) = %v, want empty", phaseNames(got))
	}
	if got := remainingPhases([]Phase{}, nil); len(got) != 0 {
		t.Errorf("remainingPhases(empty, nil) = %v, want empty", phaseNames(got))
	}
}
