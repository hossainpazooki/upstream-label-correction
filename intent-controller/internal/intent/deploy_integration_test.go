//go:build integration

package intent

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/precision-genomics/intent-controller/internal/activity"
	"github.com/precision-genomics/intent-controller/internal/models"
	"github.com/precision-genomics/intent-controller/internal/store"
)

// TestVerifyGatesDeploy proves the gap-#4 fix end to end: a deploy-triggering
// intent (training) deploys only after every eval criterion passes, and a
// single failing criterion both fails the intent and blocks the deploy. It
// guards the achieve() refactor — the deploy chain used to live solely in the
// no-criteria VERIFY branch, so adding eval criteria to a TriggersDeploy intent
// would have silently dropped the deploy.
//
// Guarded by the `integration` build tag; needs a live Postgres. Run with:
//
//	DATABASE_URL=postgresql://postgres:postgres@localhost:5432/precision_genomics \
//	    go test -tags=integration -run TestVerifyGatesDeploy ./internal/intent/...
func TestVerifyGatesDeploy(t *testing.T) {
	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		t.Skip("DATABASE_URL not set; skipping Postgres integration test")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	db, err := store.NewPostgres(ctx, connStr)
	if err != nil {
		t.Fatalf("NewPostgres: %v", err)
	}
	defer db.Close()
	if err := db.Migrate(ctx); err != nil {
		t.Fatalf("Migrate: %v", err)
	}
	repo := store.NewIntentRepo(db)

	t.Run("all evals pass -> achieved + deploy", func(t *testing.T) {
		dep := &fakeDeployer{}
		mgr, stub := newDeployTestManager(t, repo, dep, "")
		defer stub.Close()

		intent := seedVerifyingTraining(t, ctx, repo, db)

		if err := mgr.verify(ctx, intent); err != nil {
			t.Fatalf("verify: %v", err)
		}

		reloaded := mustReload(t, ctx, repo, intent.IntentID)
		if reloaded.Status != models.IntentStatusAchieved {
			t.Errorf("status = %q, want %q", reloaded.Status, models.IntentStatusAchieved)
		}
		calls := dep.snapshot()
		if len(calls) != 1 {
			t.Fatalf("deployer called %d times, want 1", len(calls))
		}
		if calls[0].stack != "dev-itest" || calls[0].tag != "v-itest" {
			t.Errorf("deploy(stack=%q tag=%q), want (dev-itest, v-itest)", calls[0].stack, calls[0].tag)
		}
	})

	t.Run("one eval fails -> failed + no deploy", func(t *testing.T) {
		dep := &fakeDeployer{}
		// Fail the SLM robustness gate; the intent must not deploy.
		mgr, stub := newDeployTestManager(t, repo, dep, "adversarial_robustness")
		defer stub.Close()

		intent := seedVerifyingTraining(t, ctx, repo, db)

		if err := mgr.verify(ctx, intent); err != nil {
			t.Fatalf("verify: %v", err)
		}

		reloaded := mustReload(t, ctx, repo, intent.IntentID)
		if reloaded.Status != models.IntentStatusFailed {
			t.Errorf("status = %q, want %q", reloaded.Status, models.IntentStatusFailed)
		}
		if reloaded.Error == nil {
			t.Error("expected a failure reason, got nil Error")
		}
		if n := len(dep.snapshot()); n != 0 {
			t.Errorf("deployer called %d times on a failed gate, want 0", n)
		}
	})
}

// newDeployTestManager wires a Manager whose RunEval hits a stub ML service and
// whose deploys are captured by dep. The stub returns passed=true for every
// eval_name except failEval (when non-empty), which returns passed=false.
func newDeployTestManager(t *testing.T, repo *store.IntentRepo, dep *fakeDeployer, failEval string) (*Manager, *httptest.Server) {
	t.Helper()
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var req struct {
			EvalName  string  `json:"eval_name"`
			Threshold float64 `json:"threshold"`
		}
		_ = json.Unmarshal(body, &req)
		passed := failEval == "" || req.EvalName != failEval
		score := 1.0
		if !passed {
			score = 0.0
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"name":      req.EvalName,
			"passed":    passed,
			"score":     score,
			"threshold": req.Threshold,
			"details":   map[string]interface{}{},
		})
	}))

	disp := activity.NewDispatcher(stub.URL)
	disp.SetDeployer(dep)
	// workflows/engine are unused on the VERIFY -> ACHIEVED -> deploy path.
	mgr := NewManager(repo, nil, nil, disp)
	return mgr, stub
}

// seedVerifyingTraining persists a training intent already in VERIFYING, with
// the InfraState/Params that triggerDeploy reads, and registers cleanup.
func seedVerifyingTraining(t *testing.T, ctx context.Context, repo *store.IntentRepo, pg *store.Postgres) *models.Intent {
	t.Helper()
	intentID := "itest-deploy-" + uuid.NewString()
	intent := &models.Intent{
		IntentID:    intentID,
		IntentType:  "training",
		Status:      models.IntentStatusVerifying,
		Params:      map[string]interface{}{"image_tag": "v-itest"},
		InfraState:  map[string]interface{}{"stack_name": "dev-itest"},
		WorkflowIDs: []string{},
		EvalResults: map[string]interface{}{},
		CreatedAt:   time.Now().UTC().Truncate(time.Microsecond),
		RequestedBy: "integration-test",
	}
	if err := repo.Create(ctx, intent); err != nil {
		t.Fatalf("Create intent: %v", err)
	}
	t.Cleanup(func() {
		cctx, ccancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer ccancel()
		if _, err := pg.Pool.Exec(cctx, `DELETE FROM intent_events WHERE intent_id = $1`, intentID); err != nil {
			t.Errorf("cleanup intent_events: %v", err)
		}
		if _, err := pg.Pool.Exec(cctx, `DELETE FROM intents WHERE intent_id = $1`, intentID); err != nil {
			t.Errorf("cleanup intents: %v", err)
		}
	})
	return intent
}

func mustReload(t *testing.T, ctx context.Context, repo *store.IntentRepo, intentID string) *models.Intent {
	t.Helper()
	got, err := repo.GetByIntentID(ctx, intentID)
	if err != nil {
		t.Fatalf("GetByIntentID: %v", err)
	}
	if got == nil {
		t.Fatalf("intent %s not found after verify", intentID)
	}
	return got
}

// fakeDeployer records Deploy calls instead of touching infrastructure.
type fakeDeployer struct {
	mu    sync.Mutex
	calls []deployCall
}

type deployCall struct{ stack, tag string }

func (f *fakeDeployer) Deploy(ctx context.Context, stackName, imageTag string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, deployCall{stackName, imageTag})
	return nil
}

func (f *fakeDeployer) snapshot() []deployCall {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]deployCall(nil), f.calls...)
}
