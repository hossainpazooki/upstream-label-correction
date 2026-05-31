package workflow

import (
	"context"
	"sync"
	"time"
)

// RetryPolicy controls how a phase is retried when its activity returns an error.
// Recovers the automatic-retry behaviour the platform had under Temporal, which
// the previous in-process engine dropped.
type RetryPolicy struct {
	MaxAttempts    int           // total attempts including the first (>= 1)
	InitialBackoff time.Duration // wait before the second attempt
	MaxBackoff     time.Duration // cap on the backoff between attempts
	Multiplier     float64       // backoff growth factor per attempt
}

// DefaultRetryPolicy is applied to every phase unless overridden.
func DefaultRetryPolicy() RetryPolicy {
	return RetryPolicy{
		MaxAttempts:    3,
		InitialBackoff: 500 * time.Millisecond,
		MaxBackoff:     10 * time.Second,
		Multiplier:     2.0,
	}
}

// runWithRetry executes fn up to policy.MaxAttempts times with capped exponential
// backoff. It returns on the first success; otherwise the last error. Backoff
// waits honour context cancellation so a cancelled workflow stops promptly.
func runWithRetry(
	ctx context.Context,
	policy RetryPolicy,
	fn func() (map[string]interface{}, error),
) (map[string]interface{}, error) {
	attempts := policy.MaxAttempts
	if attempts < 1 {
		attempts = 1
	}

	backoff := policy.InitialBackoff
	var lastErr error

	for attempt := 1; attempt <= attempts; attempt++ {
		result, err := fn()
		if err == nil {
			return result, nil
		}
		lastErr = err
		if attempt == attempts {
			break
		}

		if backoff > 0 {
			timer := time.NewTimer(backoff)
			select {
			case <-ctx.Done():
				timer.Stop()
				return nil, ctx.Err()
			case <-timer.C:
			}
		}

		if policy.Multiplier > 1 {
			backoff = time.Duration(float64(backoff) * policy.Multiplier)
		}
		if policy.MaxBackoff > 0 && backoff > policy.MaxBackoff {
			backoff = policy.MaxBackoff
		}
	}

	return nil, lastErr
}

// runPhase executes one phase: a fan-out group when Parallel is set, otherwise a
// single activity. Both paths apply the engine's retry policy.
func (e *Engine) runPhase(
	ctx context.Context,
	phase Phase,
	params, prev map[string]interface{},
) (map[string]interface{}, error) {
	if len(phase.Parallel) > 0 {
		return e.runFanOut(ctx, phase.Parallel, params, prev)
	}
	return runWithRetry(ctx, e.retryPolicy, func() (map[string]interface{}, error) {
		return phase.Activity(ctx, e.dispatcher, params, prev)
	})
}

// runFanOut runs activities concurrently (each with retry) and merges their
// result maps in branch order — later branches win on key collision, so the
// merge is deterministic. If any branch fails, the lowest-indexed error is
// returned and no partial result is produced.
func (e *Engine) runFanOut(
	ctx context.Context,
	activities []PhaseFunc,
	params, prev map[string]interface{},
) (map[string]interface{}, error) {
	type outcome struct {
		result map[string]interface{}
		err    error
	}

	// Each goroutine writes its own index, so results stays in branch order
	// without a post-sort; wg.Wait happens-before the read below.
	results := make([]outcome, len(activities))
	var wg sync.WaitGroup

	for i, activity := range activities {
		wg.Add(1)
		go func(i int, activity PhaseFunc) {
			defer wg.Done()
			r, err := runWithRetry(ctx, e.retryPolicy, func() (map[string]interface{}, error) {
				return activity(ctx, e.dispatcher, params, prev)
			})
			results[i] = outcome{result: r, err: err}
		}(i, activity)
	}
	wg.Wait()

	merged := map[string]interface{}{}
	for _, o := range results {
		if o.err != nil {
			return nil, o.err
		}
		for k, v := range o.result {
			merged[k] = v
		}
	}
	return merged, nil
}
