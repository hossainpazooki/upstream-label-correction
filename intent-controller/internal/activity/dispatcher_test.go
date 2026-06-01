package activity

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// fakeDeployer is a test double for the Deployer seam. It records the args it
// was called with and returns a configurable error/behavior. It never touches
// real infrastructure or the network.
type fakeDeployer struct {
	calls      int
	gotStack   string
	gotImage   string
	err        error
	blockUntil chan struct{} // if non-nil, Deploy blocks until ctx is done or this closes
}

func (f *fakeDeployer) Deploy(ctx context.Context, stackName, imageTag string) error {
	f.calls++
	f.gotStack = stackName
	f.gotImage = imageTag

	if f.blockUntil != nil {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-f.blockUntil:
		}
	}
	return f.err
}

func newTestDispatcher(dep Deployer) *Dispatcher {
	d := NewDispatcher("http://ml.invalid")
	d.SetDeployer(dep)
	return d
}

func TestDeployModel_Success(t *testing.T) {
	fake := &fakeDeployer{}
	d := newTestDispatcher(fake)

	err := d.DeployModel(context.Background(), "dev", "v1.2.3")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if fake.calls != 1 {
		t.Errorf("Deploy called %d times, want 1", fake.calls)
	}
	if fake.gotStack != "dev" || fake.gotImage != "v1.2.3" {
		t.Errorf("Deploy got (stack=%q, image=%q), want (dev, v1.2.3)", fake.gotStack, fake.gotImage)
	}
}

func TestDeployModel_PropagatesError(t *testing.T) {
	sentinel := errors.New("pulumi up exploded")
	fake := &fakeDeployer{err: sentinel}
	d := newTestDispatcher(fake)

	err := d.DeployModel(context.Background(), "dev", "latest")
	if err == nil {
		t.Fatal("expected error, got nil (failure must propagate)")
	}
	if !errors.Is(err, sentinel) {
		t.Errorf("err = %v, want wrapped sentinel %v", err, sentinel)
	}
}

func TestDeployModel_ContextCancellation(t *testing.T) {
	// Deployer blocks until ctx is cancelled; it never unblocks on its own.
	fake := &fakeDeployer{blockUntil: make(chan struct{})}
	d := newTestDispatcher(fake)

	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan error, 1)
	go func() {
		done <- d.DeployModel(ctx, "dev", "latest")
	}()

	// Give the goroutine a moment to enter the blocking Deploy, then cancel.
	time.Sleep(20 * time.Millisecond)
	cancel()

	select {
	case err := <-done:
		if err == nil {
			t.Fatal("expected cancellation error, got nil")
		}
		if !errors.Is(err, context.Canceled) {
			t.Errorf("err = %v, want context.Canceled", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("DeployModel did not return after ctx cancellation")
	}
}

func TestDeployModel_NoDeployerConfigured(t *testing.T) {
	// Defensive guard: an explicitly nil deployer must error, not panic/nil.
	d := NewDispatcher("http://ml.invalid")
	d.SetDeployer(nil)

	if err := d.DeployModel(context.Background(), "dev", "latest"); err == nil {
		t.Fatal("expected error when no deployer is configured")
	}
}

func TestPulumiDeployer_RejectsEmptyStack(t *testing.T) {
	// Validation happens before any exec, so this never runs the CLI.
	p := newPulumiDeployer()
	if err := p.Deploy(context.Background(), "", "latest"); err == nil {
		t.Fatal("expected error for empty stack name")
	}
}

func TestNewPulumiDeployer_DefaultWorkDir(t *testing.T) {
	// With no override, workDir defaults to an absolute "infra-ts".
	t.Setenv("PULUMI_WORKDIR", "")

	p := newPulumiDeployer()
	want, err := filepath.Abs("infra-ts")
	if err != nil {
		t.Fatalf("filepath.Abs: %v", err)
	}
	if p.workDir != want {
		t.Errorf("workDir = %q, want %q", p.workDir, want)
	}
}

func TestNewPulumiDeployer_WorkDirOverride(t *testing.T) {
	// Setting PULUMI_WORKDIR overrides the default and is resolved to an
	// absolute path.
	override := filepath.Join(os.TempDir(), "custom-infra")
	t.Setenv("PULUMI_WORKDIR", override)

	p := newPulumiDeployer()
	want, err := filepath.Abs(override)
	if err != nil {
		t.Fatalf("filepath.Abs: %v", err)
	}
	if p.workDir != want {
		t.Errorf("workDir = %q, want %q", p.workDir, want)
	}
}

func TestPulumiDeployer_RespectsPreCancelledContext(t *testing.T) {
	// A pre-cancelled context must short-circuit before exec'ing pulumi,
	// guaranteeing the test never shells out to real infra.
	p := newPulumiDeployer()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := p.Deploy(ctx, "dev", "latest")
	if !errors.Is(err, context.Canceled) {
		t.Errorf("err = %v, want context.Canceled", err)
	}
}
