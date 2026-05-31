package main

import (
	"context"
	"fmt"
	"log/slog"
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

	// Durable execution: resume workflows left "running" by a previous process.
	// Kicked off as the server starts; must not block startup.
	go func() {
		if err := engine.Recover(ctx); err != nil {
			slog.Error("workflow recovery sweep failed", "error", err)
		}
	}()

	// Intent manager
	manager := intent.NewManager(intentRepo, workflowRepo, engine, dispatcher)

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
