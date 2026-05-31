package workflow

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/precision-genomics/intent-controller/internal/activity"
)

// No backoff so retry tests don't sleep.
var fastPolicy = RetryPolicy{MaxAttempts: 3, InitialBackoff: 0, MaxBackoff: 0, Multiplier: 1}

func TestRunWithRetry_SucceedsAfterFailures(t *testing.T) {
	calls := 0
	fn := func() (map[string]interface{}, error) {
		calls++
		if calls < 3 {
			return nil, errors.New("transient")
		}
		return map[string]interface{}{"done": true}, nil
	}

	res, err := runWithRetry(context.Background(), fastPolicy, fn)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if calls != 3 {
		t.Errorf("calls = %d, want 3", calls)
	}
	if res["done"] != true {
		t.Errorf("missing result after retry")
	}
}

func TestRunWithRetry_ExhaustsAndReturnsLastError(t *testing.T) {
	calls := 0
	sentinel := errors.New("always fails")
	fn := func() (map[string]interface{}, error) {
		calls++
		return nil, sentinel
	}

	_, err := runWithRetry(context.Background(), fastPolicy, fn)
	if !errors.Is(err, sentinel) {
		t.Errorf("err = %v, want sentinel", err)
	}
	if calls != 3 {
		t.Errorf("calls = %d, want 3 (all attempts)", calls)
	}
}

func TestRunWithRetry_SingleAttempt(t *testing.T) {
	calls := 0
	fn := func() (map[string]interface{}, error) {
		calls++
		return nil, errors.New("nope")
	}

	_, err := runWithRetry(context.Background(), RetryPolicy{MaxAttempts: 1}, fn)
	if err == nil {
		t.Error("expected error")
	}
	if calls != 1 {
		t.Errorf("calls = %d, want 1", calls)
	}
}

func TestRunWithRetry_CancellationStopsBackoff(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancelled before we start

	calls := 0
	// A long backoff proves the early return is the cancellation, not the timer.
	policy := RetryPolicy{MaxAttempts: 5, InitialBackoff: time.Hour, Multiplier: 2}
	fn := func() (map[string]interface{}, error) {
		calls++
		return nil, errors.New("fail")
	}

	_, err := runWithRetry(ctx, policy, fn)
	if !errors.Is(err, context.Canceled) {
		t.Errorf("err = %v, want context.Canceled", err)
	}
	if calls != 1 {
		t.Errorf("calls = %d, want 1 (cancel interrupts the first backoff)", calls)
	}
}

func phaseReturning(m map[string]interface{}) PhaseFunc {
	return func(_ context.Context, _ *activity.Dispatcher, _, _ map[string]interface{}) (map[string]interface{}, error) {
		return m, nil
	}
}

func TestRunFanOut_MergesDisjointResults(t *testing.T) {
	e := NewEngine(nil, nil)
	e.retryPolicy = RetryPolicy{MaxAttempts: 1}

	acts := []PhaseFunc{
		phaseReturning(map[string]interface{}{"a": 1}),
		phaseReturning(map[string]interface{}{"b": 2}),
		phaseReturning(map[string]interface{}{"c": 3}),
	}
	res, err := e.runFanOut(context.Background(), acts, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, k := range []string{"a", "b", "c"} {
		if _, ok := res[k]; !ok {
			t.Errorf("merged result missing key %q", k)
		}
	}
}

func TestRunFanOut_LaterBranchWinsOnCollision(t *testing.T) {
	e := NewEngine(nil, nil)
	e.retryPolicy = RetryPolicy{MaxAttempts: 1}

	acts := []PhaseFunc{
		phaseReturning(map[string]interface{}{"k": "first"}),
		phaseReturning(map[string]interface{}{"k": "second"}),
	}
	res, err := e.runFanOut(context.Background(), acts, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if res["k"] != "second" {
		t.Errorf("k = %v, want second (later branch wins, deterministically)", res["k"])
	}
}

func TestRunFanOut_PropagatesError(t *testing.T) {
	e := NewEngine(nil, nil)
	e.retryPolicy = RetryPolicy{MaxAttempts: 1}

	boom := errors.New("boom")
	acts := []PhaseFunc{
		phaseReturning(map[string]interface{}{"a": 1}),
		func(_ context.Context, _ *activity.Dispatcher, _, _ map[string]interface{}) (map[string]interface{}, error) {
			return nil, boom
		},
	}
	_, err := e.runFanOut(context.Background(), acts, nil, nil)
	if !errors.Is(err, boom) {
		t.Errorf("err = %v, want boom", err)
	}
}

// Proves the branches actually run in parallel: every branch must reach its
// start barrier before any is released. If runFanOut were sequential, branch 0
// would block on <-release and the barrier would never complete.
func TestRunFanOut_RunsConcurrently(t *testing.T) {
	e := NewEngine(nil, nil)
	e.retryPolicy = RetryPolicy{MaxAttempts: 1}

	const n = 3
	var started sync.WaitGroup
	started.Add(n)
	release := make(chan struct{})

	act := func(_ context.Context, _ *activity.Dispatcher, _, _ map[string]interface{}) (map[string]interface{}, error) {
		started.Done()
		<-release
		return map[string]interface{}{}, nil
	}
	acts := []PhaseFunc{act, act, act}

	done := make(chan struct{})
	go func() {
		_, _ = e.runFanOut(context.Background(), acts, nil, nil)
		close(done)
	}()

	allStarted := make(chan struct{})
	go func() {
		started.Wait()
		close(allStarted)
	}()

	select {
	case <-allStarted:
	case <-time.After(2 * time.Second):
		t.Fatal("fan-out branches did not all start concurrently")
	}
	close(release)
	<-done
}
