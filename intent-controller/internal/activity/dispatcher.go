package activity

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/precision-genomics/intent-controller/internal/models"
)

// Deployer performs the actual infrastructure deployment for a model image.
// It is an injectable seam so DeployModel can be unit-tested without touching
// real infrastructure: production wires in pulumiDeployer, tests wire in a fake.
type Deployer interface {
	Deploy(ctx context.Context, stackName, imageTag string) error
}

// Dispatcher sends activity requests to the Python ML service over HTTP.
type Dispatcher struct {
	mlURL    string
	client   *http.Client
	deployer Deployer
}

// NewDispatcher creates a new activity dispatcher with the default (real)
// Pulumi-backed deployer.
func NewDispatcher(mlServiceURL string) *Dispatcher {
	return &Dispatcher{
		mlURL: mlServiceURL,
		client: &http.Client{
			Timeout: 5 * time.Minute,
		},
		deployer: newPulumiDeployer(),
	}
}

// SetDeployer overrides the deployment backend. It exists primarily to inject a
// fake Deployer in tests; production code uses the default from NewDispatcher.
func (d *Dispatcher) SetDeployer(dep Deployer) {
	d.deployer = dep
}

// CallML sends a POST request to the ML service and returns the response.
func (d *Dispatcher) CallML(ctx context.Context, path string, body map[string]interface{}) (map[string]interface{}, error) {
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	url := d.mlURL + path
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	slog.Debug("calling ML service", "url", url)

	resp, err := d.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("ML service request failed: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("ML service error (status %d): %s", resp.StatusCode, string(respBody))
	}

	var result map[string]interface{}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("unmarshal response: %w", err)
	}

	return result, nil
}

// HealthCheck verifies the ML service is reachable.
func (d *Dispatcher) HealthCheck(ctx context.Context) error {
	url := d.mlURL + "/health"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}

	resp, err := d.client.Do(req)
	if err != nil {
		return fmt.Errorf("ML service unreachable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("ML service unhealthy: status %d", resp.StatusCode)
	}
	return nil
}

// ResolveInfra dispatches infrastructure resolution for a specific requirement.
func (d *Dispatcher) ResolveInfra(ctx context.Context, requirement string, intent *models.Intent) (map[string]interface{}, error) {
	switch requirement {
	case "worker_scaled":
		return d.ensureWorkerScaled(ctx, intent)
	case "gcs_data_staged":
		return d.ensureDataStaged(ctx, intent)
	case "vertex_ai_job":
		return d.provisionTrainingJob(ctx, intent)
	case "gpu_allocated":
		return d.checkGPUQuota(ctx, intent)
	default:
		slog.Warn("no handler for infra requirement", "requirement", requirement)
		return map[string]interface{}{"status": "skipped", "reason": "no handler"}, nil
	}
}

func (d *Dispatcher) ensureWorkerScaled(ctx context.Context, intent *models.Intent) (map[string]interface{}, error) {
	// In production, this would call the Pulumi Go SDK.
	// For now, return a mock successful result.
	workerMax := 5
	if wm, ok := intent.Params["worker_max_instances"].(float64); ok {
		workerMax = int(wm)
	}
	slog.Info("scaling workers", "intent_id", intent.IntentID, "max_instances", workerMax)
	return map[string]interface{}{
		"status":     "scaled",
		"stack_name": "dev",
		"worker_url": "",
	}, nil
}

func (d *Dispatcher) ensureDataStaged(ctx context.Context, intent *models.Intent) (map[string]interface{}, error) {
	dataset, _ := intent.Params["dataset"].(string)
	if dataset == "" {
		dataset = "train"
	}
	// Local fallback — assume data is available
	return map[string]interface{}{
		"status":  "staged",
		"source":  "local",
		"dataset": dataset,
	}, nil
}

func (d *Dispatcher) provisionTrainingJob(ctx context.Context, intent *models.Intent) (map[string]interface{}, error) {
	modelType, _ := intent.Params["model_type"].(string)
	if modelType == "" {
		modelType = "slm"
	}
	// Delegate to ML service for training job provisioning
	result, err := d.CallML(ctx, "/ml/pipeline", map[string]interface{}{
		"action":     "provision_training",
		"model_type": modelType,
		"params":     intent.Params,
	})
	if err != nil {
		return nil, err
	}
	return map[string]interface{}{
		"status": "provisioned",
		"job":    result,
	}, nil
}

func (d *Dispatcher) checkGPUQuota(ctx context.Context, intent *models.Intent) (map[string]interface{}, error) {
	spec, ok := models.IntentSpecs[intent.IntentType]
	maxGPUs := 4
	if ok {
		maxGPUs = spec.MaxGPUCount
	}
	if maxGPUs == 0 {
		maxGPUs = 4
	}

	requestedGPUs := 1
	if n, ok := intent.Params["num_gpus"].(float64); ok {
		requestedGPUs = int(n)
	}

	if requestedGPUs > maxGPUs {
		return map[string]interface{}{
			"status": "failed",
			"error":  fmt.Sprintf("requested %d GPUs exceeds limit of %d", requestedGPUs, maxGPUs),
		}, nil
	}

	return map[string]interface{}{
		"status":      "approved",
		"num_gpus":    requestedGPUs,
		"max_allowed": maxGPUs,
	}, nil
}

// RunEval runs an evaluation criterion via the ML service.
func (d *Dispatcher) RunEval(ctx context.Context, evalName string, threshold float64, intent *models.Intent) (map[string]interface{}, error) {
	result, err := d.CallML(ctx, "/ml/evaluate", map[string]interface{}{
		"eval_name": evalName,
		"threshold": threshold,
		"params":    intent.Params,
		"intent_id": intent.IntentID,
	})
	if err != nil {
		return nil, err
	}
	return result, nil
}

// DeployModel triggers a model deployment for the given stack and image tag.
// It delegates to the configured Deployer (Pulumi CLI by default), propagating
// any error rather than silently succeeding, and respects ctx cancellation.
func (d *Dispatcher) DeployModel(ctx context.Context, stackName, imageTag string) error {
	if d.deployer == nil {
		return fmt.Errorf("deploy model: no deployer configured")
	}

	slog.Info("deploying model", "stack", stackName, "image_tag", imageTag)

	if err := d.deployer.Deploy(ctx, stackName, imageTag); err != nil {
		slog.Error("model deploy failed", "stack", stackName, "image_tag", imageTag, "error", err)
		return fmt.Errorf("deploy model (stack=%s image_tag=%s): %w", stackName, imageTag, err)
	}

	slog.Info("model deploy succeeded", "stack", stackName, "image_tag", imageTag)
	return nil
}

// pulumiDeployer is the production Deployer. It runs `pulumi up` against the
// infra-ts project, selecting the requested stack and passing the image tag as
// a stack config value. The exec is bound to the provided context (timeout and
// cancellation) and stdout/stderr are captured for diagnostics.
type pulumiDeployer struct {
	// workDir is the Pulumi project directory (infra-ts) the CLI runs in.
	workDir string
	// timeout caps a single deploy if the caller's context has no deadline.
	timeout time.Duration
	// pulumiBin is the CLI binary name/path; overridable for tests.
	pulumiBin string
}

func newPulumiDeployer() *pulumiDeployer {
	return &pulumiDeployer{
		workDir:   pulumiWorkDir(),
		timeout:   15 * time.Minute,
		pulumiBin: "pulumi",
	}
}

// pulumiWorkDir resolves the Pulumi project directory. It honors the
// PULUMI_WORKDIR env var (defaulting to "infra-ts") and resolves it to an
// absolute path so the controller binary can run from any directory. If the
// path cannot be made absolute, the configured value is used as-is.
func pulumiWorkDir() string {
	dir := os.Getenv("PULUMI_WORKDIR")
	if dir == "" {
		dir = "infra-ts"
	}
	if abs, err := filepath.Abs(dir); err == nil {
		return abs
	}
	return dir
}

func (p *pulumiDeployer) Deploy(ctx context.Context, stackName, imageTag string) error {
	if stackName == "" {
		return fmt.Errorf("stack name is required")
	}

	// Bail out early if the caller already cancelled.
	if err := ctx.Err(); err != nil {
		return err
	}

	// Apply a default deploy ceiling only when the caller gave no deadline.
	if _, hasDeadline := ctx.Deadline(); !hasDeadline && p.timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, p.timeout)
		defer cancel()
	}

	// Set the image tag as stack config, then deploy the selected stack
	// non-interactively. --yes avoids prompts; --non-interactive is mandatory
	// for an unattended controller.
	args := [][]string{
		{"config", "set", "modelImageTag", imageTag, "--stack", stackName, "--non-interactive"},
		{"up", "--yes", "--stack", stackName, "--non-interactive"},
	}

	for _, a := range args {
		var stdout, stderr bytes.Buffer
		cmd := exec.CommandContext(ctx, p.pulumiBin, a...)
		cmd.Dir = p.workDir
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		if err := cmd.Run(); err != nil {
			// Surface context cancellation/timeout distinctly from CLI failures.
			if cerr := ctx.Err(); cerr != nil {
				return fmt.Errorf("pulumi %s: %w", a[0], cerr)
			}
			return fmt.Errorf("pulumi %s failed: %w: %s", a[0], err, stderr.String())
		}
		slog.Debug("pulumi command completed", "command", a[0], "stack", stackName)
	}

	return nil
}
