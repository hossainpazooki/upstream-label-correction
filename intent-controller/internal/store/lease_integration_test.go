//go:build integration

package store

import (
	"context"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/precision-genomics/intent-controller/internal/models"
)

// TestClaimIntentsAtMostOnce proves cross-replica at-most-once claiming on the
// intents table: two concurrent ClaimIntents calls with different worker ids
// receive DISJOINT row sets that together cover every eligible row, so no row is
// ever claimed twice. It is guarded by the `integration` build tag and skips
// without DATABASE_URL.
//
//	DATABASE_URL=postgresql://postgres:postgres@localhost:5432/precision_genomics \
//	    go test -tags=integration ./internal/store/...
func TestClaimIntentsAtMostOnce(t *testing.T) {
	db := openTestDB(t)
	repo := NewIntentRepo(db)

	const n = 12
	runTag := "lease-itest-" + uuid.NewString()
	ids := make([]string, 0, n)
	for i := 0; i < n; i++ {
		intentID := runTag + "-" + uuid.NewString()
		ids = append(ids, intentID)
		intent := &models.Intent{
			IntentID:    intentID,
			IntentType:  "analysis",
			Status:      models.IntentStatusDeclared,
			Params:      map[string]interface{}{},
			InfraState:  map[string]interface{}{},
			WorkflowIDs: []string{},
			EvalResults: map[string]interface{}{},
			CreatedAt:   time.Now().UTC(),
			RequestedBy: "lease-integration-test",
		}
		if err := repo.Create(context.Background(), intent); err != nil {
			t.Fatalf("Create intent %d: %v", i, err)
		}
	}

	t.Cleanup(func() {
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		for _, id := range ids {
			if _, err := db.Pool.Exec(cleanupCtx, `DELETE FROM intents WHERE intent_id = $1`, id); err != nil {
				t.Errorf("cleanup intent %s: %v", id, err)
			}
		}
	})

	statuses := []string{"declared", "resolving", "blocked", "active", "verifying"}

	// Two workers claim concurrently with a long TTL so no lease expires mid-test.
	setA, setB := concurrentClaim(t, func(ctx context.Context, worker string) []string {
		claimed, err := repo.ClaimIntents(ctx, worker, statuses, 300, n)
		if err != nil {
			t.Errorf("ClaimIntents(%s): %v", worker, err)
			return nil
		}
		out := make([]string, len(claimed))
		for i, c := range claimed {
			out[i] = c.IntentID
		}
		return out
	})

	// Restrict to rows this test created (a shared DB may hold other intents).
	mine := make(map[string]bool, len(ids))
	for _, id := range ids {
		mine[id] = true
	}
	assertDisjointAndComplete(t, "intents", filterSet(setA, mine), filterSet(setB, mine), ids)
}

// TestClaimRunningAtMostOnce proves the same at-most-once guarantee on
// workflow_executions via ClaimRunning.
func TestClaimRunningAtMostOnce(t *testing.T) {
	db := openTestDB(t)
	repo := NewWorkflowRepo(db)

	const n = 12
	runTag := "lease-wf-itest-" + uuid.NewString()
	ids := make([]string, 0, n)
	for i := 0; i < n; i++ {
		workflowID := runTag + "-" + uuid.NewString()
		ids = append(ids, workflowID)
		wf := &models.WorkflowExecution{
			WorkflowID:      workflowID,
			WorkflowType:    "cosmo_pipeline",
			Status:          models.WorkflowStatusRunning,
			CurrentPhase:    "data_loading",
			PhasesCompleted: []string{},
			Params:          map[string]interface{}{},
			StartedAt:       time.Now().UTC(),
			Result:          map[string]interface{}{},
		}
		if err := repo.Create(context.Background(), wf); err != nil {
			t.Fatalf("Create workflow %d: %v", i, err)
		}
	}

	t.Cleanup(func() {
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		for _, id := range ids {
			if _, err := db.Pool.Exec(cleanupCtx, `DELETE FROM workflow_executions WHERE workflow_id = $1`, id); err != nil {
				t.Errorf("cleanup workflow %s: %v", id, err)
			}
		}
	})

	setA, setB := concurrentClaim(t, func(ctx context.Context, worker string) []string {
		claimed, err := repo.ClaimRunning(ctx, worker, 300, n)
		if err != nil {
			t.Errorf("ClaimRunning(%s): %v", worker, err)
			return nil
		}
		out := make([]string, len(claimed))
		for i, c := range claimed {
			out[i] = c.WorkflowID
		}
		return out
	})

	mine := make(map[string]bool, len(ids))
	for _, id := range ids {
		mine[id] = true
	}
	assertDisjointAndComplete(t, "workflow_executions", filterSet(setA, mine), filterSet(setB, mine), ids)
}

// openTestDB connects, migrates, and returns a Postgres handle, skipping the
// test when DATABASE_URL is unset and closing the pool in t.Cleanup.
func openTestDB(t *testing.T) *Postgres {
	t.Helper()
	connStr := envOrSkip(t, "DATABASE_URL")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	db, err := NewPostgres(ctx, connStr)
	if err != nil {
		t.Fatalf("NewPostgres: %v", err)
	}
	t.Cleanup(db.Close)

	if err := db.Migrate(ctx); err != nil {
		t.Fatalf("Migrate: %v", err)
	}
	return db
}

func envOrSkip(t *testing.T, key string) string {
	t.Helper()
	v := os.Getenv(key)
	if v == "" {
		t.Skipf("%s not set; skipping Postgres integration test", key)
	}
	return v
}

// concurrentClaim runs claim under two distinct worker ids at the same time,
// using a barrier so both fire as close together as possible, and returns each
// worker's claimed-id set.
func concurrentClaim(t *testing.T, claim func(ctx context.Context, worker string) []string) (a, b []string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	var start sync.WaitGroup
	start.Add(1)
	var done sync.WaitGroup
	done.Add(2)

	run := func(worker string, out *[]string) {
		defer done.Done()
		start.Wait()
		*out = claim(ctx, worker)
	}

	go run("worker-a", &a)
	go run("worker-b", &b)

	start.Done() // release both goroutines together
	done.Wait()
	return a, b
}

// assertDisjointAndComplete verifies the two claimed sets share no element and
// together equal want (each eligible row claimed exactly once).
func assertDisjointAndComplete(t *testing.T, table string, a, b, want []string) {
	t.Helper()

	seen := map[string]int{}
	for _, id := range a {
		seen[id]++
	}
	for _, id := range b {
		seen[id]++
	}

	for id, c := range seen {
		if c > 1 {
			t.Errorf("%s: row %s claimed %d times (must be at most once)", table, id, c)
		}
	}

	for _, id := range want {
		if seen[id] == 0 {
			t.Errorf("%s: eligible row %s was never claimed", table, id)
		}
	}

	if total := len(a) + len(b); total != len(want) {
		t.Errorf("%s: total claimed = %d, want %d (a=%d, b=%d)", table, total, len(want), len(a), len(b))
	}
}

func filterSet(ids []string, keep map[string]bool) []string {
	out := make([]string, 0, len(ids))
	for _, id := range ids {
		if keep[id] {
			out = append(out, id)
		}
	}
	return out
}
