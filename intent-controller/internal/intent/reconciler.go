package intent

import (
	"context"
	"log/slog"
	"time"

	"github.com/precision-genomics/intent-controller/internal/models"
	"github.com/precision-genomics/intent-controller/internal/store"
)

// nonTerminalStatuses are the intent states the reconciler advances. Terminal
// states (achieved/failed/cancelled) are never claimed.
var nonTerminalStatuses = []string{"declared", "resolving", "blocked", "active", "verifying"}

// Reconciler periodically claims and processes non-terminal intents to advance
// their state. It is safe to run in multiple replicas: each tick claims a
// disjoint batch via a cross-replica lease (see store.IntentRepo.ClaimIntents),
// so two replicas never double-process the same intent.
type Reconciler struct {
	manager  *Manager
	intents  *store.IntentRepo
	interval time.Duration
	workerID string
	ttl      time.Duration
	limit    int
}

// NewReconciler creates a reconciler that polls at the given interval, claiming
// intents under workerID. The lease TTL defaults to max(60s, 2*interval) so a
// crash mid-Process is reclaimed only after the in-flight work would have
// finished; the batch limit defaults to 100.
func NewReconciler(manager *Manager, intents *store.IntentRepo, interval time.Duration, workerID string) *Reconciler {
	ttl := 60 * time.Second
	if two := 2 * interval; two > ttl {
		ttl = two
	}
	return &Reconciler{
		manager:  manager,
		intents:  intents,
		interval: interval,
		workerID: workerID,
		ttl:      ttl,
		limit:    100,
	}
}

// Run starts the reconciliation loop. It blocks until ctx is cancelled.
func (r *Reconciler) Run(ctx context.Context) {
	ticker := time.NewTicker(r.interval)
	defer ticker.Stop()

	slog.Info("reconciler started", "interval", r.interval, "worker_id", r.workerID, "lease_ttl", r.ttl)

	for {
		select {
		case <-ctx.Done():
			slog.Info("reconciler stopped")
			return
		case <-ticker.C:
			r.reconcileAll(ctx)
		}
	}
}

func (r *Reconciler) reconcileAll(ctx context.Context) {
	intents, err := r.intents.ClaimIntents(ctx, r.workerID, nonTerminalStatuses, r.ttl.Seconds(), r.limit)
	if err != nil {
		slog.Error("reconciler: failed to claim intents", "worker_id", r.workerID, "error", err)
		return
	}

	for _, intent := range intents {
		if models.TerminalStates[intent.Status] {
			// Defensive: the claim guard already excludes terminal states.
			r.release(ctx, intent.IntentID)
			continue
		}

		if _, err := r.manager.Process(ctx, intent.IntentID); err != nil {
			slog.Error("reconciler: failed to process intent",
				"intent_id", intent.IntentID, "status", intent.Status, "error", err)
		}

		// Release after each intent so the next tick can re-claim it to advance
		// the next FSM step. The FSM plus idempotent Process make re-processing
		// safe. If Process crashed the process, the lease simply expires.
		r.release(ctx, intent.IntentID)
	}
}

func (r *Reconciler) release(ctx context.Context, intentID string) {
	if err := r.intents.ReleaseIntent(ctx, intentID); err != nil {
		slog.Error("reconciler: failed to release intent lease",
			"intent_id", intentID, "error", err)
	}
}
