package models

import "testing"

// The string values are persisted to the DB and matched in SQL filters, so they
// must stay stable across the Go/Python migration.
func TestWorkflowStatusValues(t *testing.T) {
	cases := map[WorkflowStatus]string{
		WorkflowStatusPending:   "pending",
		WorkflowStatusRunning:   "running",
		WorkflowStatusCompleted: "completed",
		WorkflowStatusFailed:    "failed",
		WorkflowStatusCancelled: "cancelled",
	}
	for got, want := range cases {
		if string(got) != want {
			t.Errorf("workflow status = %q, want %q", got, want)
		}
	}
}

func TestIntentStatusValues(t *testing.T) {
	cases := map[IntentStatus]string{
		IntentStatusDeclared:  "declared",
		IntentStatusResolving: "resolving",
		IntentStatusBlocked:   "blocked",
		IntentStatusActive:    "active",
		IntentStatusVerifying: "verifying",
		IntentStatusAchieved:  "achieved",
		IntentStatusFailed:    "failed",
		IntentStatusCancelled: "cancelled",
	}
	for got, want := range cases {
		if string(got) != want {
			t.Errorf("intent status = %q, want %q", got, want)
		}
	}
}
