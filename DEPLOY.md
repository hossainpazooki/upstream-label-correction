# Precision Genomics — Deployment

**GCP Project:** `prec-genomics-agent` (project number: `677590965589`)
**Region:** `us-central1`

Infrastructure is defined as **TypeScript Pulumi** in [`infra-ts/`](./infra-ts/)
(migrated from the earlier Terraform and Python-Pulumi stacks, both now retired).

---

## Architecture

Three Cloud Run services behind a Serverless VPC Connector, plus managed data
services and Vertex AI — all defined in `infra-ts/index.ts`.

| Service | Image | Port | Auth | Notes |
|---|---|---|---|---|
| `precision-genomics-web` | `web:latest` (Next.js) | 3000 | public | min 1 / max 10 instances |
| `precision-genomics-ml` | `ml:latest` (Python ML) | 8000 | internal | scale-to-zero, 8Gi, 900s timeout |
| `precision-genomics-mcp` | `mcp:latest` (MCP server) | 8080 | public | min 1 / max 5 instances |

> **Not yet in `infra-ts/`:** the Go `intent-controller` (port 8090) builds and
> runs (`intent-controller/Dockerfile`) but is **not provisioned by Pulumi
> yet** — no `CloudRunService` exists for it in `index.ts`. Adding it is a
> follow-up to Migration 1 in [`PULUMI_MIGRATION_PLAN.md`](./PULUMI_MIGRATION_PLAN.md).

Backing services: Cloud SQL (PostgreSQL), Memorystore Redis, 3 GCS buckets,
Artifact Registry (`precision-genomics`), Secret Manager
(`ANTHROPIC_API_KEY`, `DATABASE_PASSWORD`), Vertex AI.

> **Orchestration note:** GCP Workflows are no longer used. Intent lifecycle and
> workflow orchestration run in the Go `intent-controller`
> (`intent-controller/internal/workflow`). See
> [`PULUMI_MIGRATION_PLAN.md`](./PULUMI_MIGRATION_PLAN.md).

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
```

### Build & push images

Images must exist in Artifact Registry before `pulumi up` can roll out the
Cloud Run services. Build and push each:
```bash
REGISTRY=us-central1-docker.pkg.dev/prec-genomics-agent/precision-genomics
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

docker build -f web/Dockerfile     -t $REGISTRY/web:latest web/   && docker push $REGISTRY/web:latest
docker build -f Dockerfile.ml      -t $REGISTRY/ml:latest  .      && docker push $REGISTRY/ml:latest
docker build -f web/Dockerfile.mcp -t $REGISTRY/mcp:latest web/   && docker push $REGISTRY/mcp:latest
```

> The `intent-controller` image (`docker build -f intent-controller/Dockerfile
> intent-controller/`) is not consumed by `pulumi up` yet — build/push it only
> once a `CloudRunService` for it is added to `infra-ts/index.ts`.

---

## CI/CD status

⚠️ **Automated GCP deploy is currently disabled.** The
`.github/workflows/deploy-gcp.yml` workflow auto-trigger was removed (commit
`d2a263f`) because it referenced deleted Dockerfiles and the GCP auth secrets
are not yet configured. It is now `workflow_dispatch`-only and still encodes
the **old** `gcloud run deploy` flow rather than `pulumi up`.

**Before re-enabling, the workflow needs to be rewritten to:**
1. Build/push the four images (paths above).
2. Run `pulumi up` from `infra-ts/` instead of imperative `gcloud run deploy`.
3. Authenticate via Workload Identity Federation — requires repo secrets
   `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`.

Until then, deploy manually with the Pulumi steps above.

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
