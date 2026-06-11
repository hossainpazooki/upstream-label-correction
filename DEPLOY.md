# Precision Genomics — Deployment

**GCP Project:** `prec-genomics-agent` (project number: `677590965589`)
**Region:** `us-central1`

Infrastructure is defined as **TypeScript Pulumi** in [`infra-ts/`](./infra-ts/)
(migrated from the earlier Terraform and Python-Pulumi stacks, both now retired).

---

## Architecture

Four Cloud Run services behind a Serverless VPC Connector, plus managed data
services and Vertex AI — all defined in `infra-ts/index.ts`.

| Service | Image | Port | Auth | Notes |
|---|---|---|---|---|
| `precision-genomics-web` | `web:latest` (Next.js) | 3000 | public | min 1 / max 10 instances |
| `precision-genomics-intent` | `intent-controller:latest` (Go) | 8090 | internal | singleton (min 1 / max 1); reconcile + recover loops |
| `precision-genomics-ml` | `ml:latest` (Python ML) | 8000 | internal | scale-to-zero, 8Gi, 900s timeout |
| `precision-genomics-mcp` | `mcp:latest` (MCP server) | 8080 | public | min 1 / max 5 instances |

> **`intent-controller` wiring:** it reads a full `DATABASE_URL` (assembled in
> `index.ts` from the Cloud SQL private IP and the `app` DB user/password) and
> `ML_SERVICE_URL` (the `precision-genomics-ml` URL). The `web` service is given
> `INTENT_CONTROLLER_URL` to proxy intent/workflow ops to it. It is a singleton
> (`max 1`); the cross-replica claim/lease (durability "step 3") makes scaling
> past 1 safe if request load ever requires it. One known follow-up, shared with
> `ml`: the DB password lands as a plain Cloud Run env via `DATABASE_URL` rather
> than a Secret-Manager-injected secret — harden by storing the assembled URL in
> Secret Manager.

> **Control-plane auth (gap #8).** The internal services are no longer open at
> the app layer. A shared `SERVICE_AUTH_TOKEN` (Secret Manager) is injected into
> all services; the controller's `/api/v1/*` routes and every `ml_service`
> endpoint (except health) require it via the `X-Service-Token` header, which the
> controller's dispatcher and web's server-side clients attach. `intent` and `ml`
> are also set to `ingress=INTERNAL_ONLY`, and the public web edge enforces
> `REQUIRE_AUTH=true` + `API_KEYS` on `/api/*`. Remaining hardening (follow-up):
> swap the shared token for GCP OIDC / `run.invoker` IAM bindings — the same
> middleware seam validates an OIDC token instead of a static one.

Backing services: Cloud SQL (PostgreSQL), Memorystore Redis, 3 GCS buckets,
Artifact Registry (`precision-genomics`), Secret Manager
(`ANTHROPIC_API_KEY`, `DATABASE_PASSWORD`), Vertex AI.

> **Orchestration note:** GCP Workflows are no longer used. Intent lifecycle and
> workflow orchestration run in the Go `intent-controller`
> (`intent-controller/internal/workflow`). See the retired
> [migration plan](docs/archive/PULUMI_MIGRATION_PLAN.md) for the full split.

---

## Prerequisites

- `gcloud` installed and authenticated (`gcloud auth login`)
- [Pulumi](https://www.pulumi.com/docs/install/) >= 3.0
- Node.js 20+
- A configured Pulumi stack (`dev`) — see `infra-ts/Pulumi.dev.yaml`

Enable required APIs (one-time):
```bash
gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com redis.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com vpcaccess.googleapis.com \
  servicenetworking.googleapis.com \
  --project=prec-genomics-agent
```

---

## Deploy with Pulumi

```bash
cd infra-ts
npm ci

# Configure secrets on the stack (first time only)
pulumi config set --secret anthropicApiKey <ANTHROPIC_API_KEY>
pulumi config set --secret dbPassword <DB_PASSWORD>
# gap #8 auth — REQUIRED (config.ts requireSecret; pulumi up fails without them):
#   service_auth_token: shared internal token (controller <-> ml, web -> both)
#   web_api_keys: comma-separated API key(s) the public web edge accepts
pulumi config set --secret service_auth_token <RANDOM_HIGH_ENTROPY_TOKEN>
pulumi config set --secret web_api_keys <KEY1,KEY2>

# Preview and apply
pulumi preview --stack dev
pulumi up --stack dev
```

Stack outputs (URLs, connection names, bucket names) after `pulumi up`:
```bash
pulumi stack output            # all outputs
pulumi stack output webUrl
pulumi stack output mlServiceUrl
pulumi stack output mcpUrl
pulumi stack output intentControllerUrl
```

### Build & push images

Images must exist in Artifact Registry before `pulumi up` can roll out the
Cloud Run services. Build and push each:
```bash
REGISTRY=us-central1-docker.pkg.dev/prec-genomics-agent/precision-genomics
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

docker build -f web/Dockerfile        -t $REGISTRY/web:latest              web/               && docker push $REGISTRY/web:latest
docker build -f Dockerfile.ml         -t $REGISTRY/ml:latest               .                  && docker push $REGISTRY/ml:latest
docker build -f web/Dockerfile.mcp    -t $REGISTRY/mcp:latest              web/               && docker push $REGISTRY/mcp:latest
docker build -f intent-controller/Dockerfile -t $REGISTRY/intent-controller:latest intent-controller/ && docker push $REGISTRY/intent-controller:latest
```

---

## CI/CD status

Both deploy workflows are **rewritten for the infra-ts/Pulumi architecture** —
they authenticate via Workload Identity Federation, build the images, and run
`pulumi up` from `infra-ts/`. The Pulumi path now provisions and builds all four
services; the only thing left to enable auto-deploy is the secrets.

- **`deploy-pulumi.yml`** (primary IaC path): builds/pushes `web`, `ml`, `mcp`,
  and `intent-controller` from the correct Dockerfiles — image names match what
  `infra-ts/index.ts` pulls — then runs `pulumi up` from `infra-ts/` via the
  Pulumi GitHub Action (CrossGuard policies in `infra-ts/policies`).
- **`deploy-gcp.yml`** (direct `gcloud` fallback): self-contained — builds
  `ml-service`/`mcp-sse` and `gcloud run deploy`s those same images directly
  (no Pulumi), so its names are internally consistent. Note: it does **not**
  deploy the `intent-controller` (Pulumi path only), and its Cloud Run service
  names (`precision-genomics-ml-service`, `-mcp-sse`) differ from the Pulumi
  path's — don't run both paths against one project or you'll get duplicate
  services. Prefer the Pulumi path for a complete deploy.

Both are **`workflow_dispatch`-only** today. To enable auto-deploy: configure
these four repo secrets, then restore the `workflow_run`/push trigger (a header
comment in `deploy-pulumi.yml` marks where):

| Secret | Purpose |
|---|---|
| `GCP_PROJECT_ID` | target project for images + Cloud Run |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | keyless WIF auth |
| `GCP_SERVICE_ACCOUNT` | deploy identity |
| `PULUMI_ACCESS_TOKEN` | Pulumi state backend |

Until the secrets land, trigger a deploy manually (Actions → *Deploy (Pulumi)* →
*Run workflow*) or run the Pulumi steps above locally.

The `web/` Next.js dashboard builds clean (`npm ci && npm run build`, Next 15
standalone output) and its image is wired into both workflows.

---

## Authentication (internal services)

`web` and `mcp` are public; `ml` is internal and requires an identity token:
```bash
TOKEN=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOKEN" "$(cd infra-ts && pulumi stack output mlServiceUrl)/health"
```

---

## Rollback

```bash
# Roll back to the previous Pulumi state
cd infra-ts && pulumi stack history && pulumi up --stack dev   # after reverting code

# Tear down all infrastructure
cd infra-ts && pulumi destroy --stack dev
```

---

## Estimated Monthly Cost

| Service | Estimate |
|---|---|
| Cloud SQL | ~$50–70 |
| Memorystore Redis (1GB BASIC) | ~$35 |
| Cloud Run (web + mcp min 1 instance) | ~$30–50 |
| Cloud Run (ml scale-to-zero) | pay-per-use |
| **Total baseline** | **~$115–155** |
