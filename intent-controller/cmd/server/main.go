package main

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/precision-genomics/intent-controller/internal/activity"
	"github.com/precision-genomics/intent-controller/internal/api"
	"github.com/precision-genomics/intent-controller/internal/intent"
	"github.com/precision-genomics/intent-controller/internal/store"
	"github.com/precision-genomics/intent-controller/internal/workflow"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	port := envOr("PORT", "8090")
	dbURL := envOr("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/precision_genomics")
	mlURL := envOr("ML_SERVICE_URL", "http://localhost:8000")

	// Stable per-replica worker identity for cross-replica CLAIM/LEASE. Multiple
	// replicas must have distinct ids so neither double-processes an intent nor
	// double-recovers a workflow. hostname+pid is stable within a process; a
	// random suffix guards against two replicas sharing a hostname (and against
	// hostname lookup failing).
	workerID := makeWorkerID()
	slog.Info("worker identity", "worker_id", workerID)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Database
	db, err := store.NewPostgres(ctx, dbURL)
	if err != nil {
		slog.Error("failed to connect to database", "error", err)
		os.Exit(1)
	}
	defer db.Close()

	if err := db.Migrate(ctx); err != nil {
		slog.Error("failed to run migrations", "error", err)
		os.Exit(1)
	}

	// Repositories
	intentRepo := store.NewIntentRepo(db)
	workflowRepo := store.NewWorkflowRepo(db)

	// Activity dispatcher
	dispatcher := activity.NewDispatcher(mlURL)

	// Workflow engine
	engine := workflow.NewEngine(workflowRepo, dispatcher)
	engine.SetWorkerID(workerID)

	// Durable execution: claim and resume workflows left "running" by a previous
	// process. Kicked off as the server starts; must not block startup. The
	// claim makes this safe across replicas: two replicas starting at once split
	// the running workflows instead of both recovering each one.
	go func() {
		if err := engine.Recover(ctx); err != nil {
			slog.Error("workflow recovery sweep failed", "error", err)
		}
	}()

	// Periodic orphan-reclaim: re-run Recover on a ticker so a workflow whose
	// owner replica died mid-run is reclaimed without waiting for a restart.
	// ClaimRunning only returns NULL/expired-lease rows, so this sweep skips
	// healthy in-flight workflows kept alive by the heartbeat below.
	recoverInterval := envDuration("RECOVER_INTERVAL", 2*time.Minute)
	go engine.RecoverLoop(ctx, recoverInterval)

	// Lease heartbeat: a live replica renews the leases on its own running
	// workflows on a ticker well under the lease TTL, so a phase that outlives
	// the TTL never lets the lease expire and get double-resumed by the sweep.
	go engine.HeartbeatLoop(ctx)

	// Intent manager
	manager := intent.NewManager(intentRepo, workflowRepo, engine, dispatcher)

	// Reconciler: periodically claims and advances non-terminal intents. Each
	// tick claims a disjoint batch under workerID, so additional replicas share
	// the work without double-processing.
	reconcileInterval := envDuration("RECONCILE_INTERVAL", 15*time.Second)
	reconciler := intent.NewReconciler(manager, intentRepo, reconcileInterval, workerID)
	go reconciler.Run(ctx)

	// HTTP server
	router := api.NewRouter(manager, engine, intentRepo, workflowRepo)

	srv := &http.Server{
		Addr:         ":" + port,
		Handler:      router,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 120 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Graceful shutdown
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh
		slog.Info("shutting down")
		cancel()
		shutCtx, shutCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutCancel()
		srv.Shutdown(shutCtx)
	}()

	slog.Info("intent-controller starting", "port", port)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		slog.Error("server error", "error", err)
		os.Exit(1)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	_ = fmt.Sprintf("using default for %s", key)
	return fallback
}

// envDuration parses a duration env var (e.g. "15s"), falling back on empty or
// unparseable input.
func envDuration(key string, fallback time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		slog.Warn("invalid duration env var, using default", "key", key, "value", v, "default", fallback)
		return fallback
	}
	return d
}

// makeWorkerID builds a stable per-replica identity. WORKER_ID overrides it
// outright (useful for tests and explicit deployments); otherwise it is
// hostname-pid-<random>, with a random fallback if the hostname is unavailable.
func makeWorkerID() string {
	if v := os.Getenv("WORKER_ID"); v != "" {
		return v
	}
	host, err := os.Hostname()
	if err != nil || host == "" {
		host = "host"
	}
	return fmt.Sprintf("%s-%d-%04d", host, os.Getpid(), rand.Intn(10000))
}
