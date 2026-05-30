# Archived Documentation

These documents are **historical** — kept for context and provenance, but no
longer describe the current system. They are not maintained. For current
documentation see the [project README](../../README.md), [DEPLOY.md](../../DEPLOY.md),
and [PULUMI_MIGRATION_PLAN.md](../../PULUMI_MIGRATION_PLAN.md).

| Document | Retired because |
|---|---|
| [MIGRATION_PLAN.md](MIGRATION_PLAN.md) | Put the workflow engine + intent lifecycle in TypeScript. Reversed — both now live in the Go `intent-controller`. Superseded by [PULUMI_MIGRATION_PLAN.md](../../PULUMI_MIGRATION_PLAN.md). |
| [GCP_DEPLOYMENT.md](GCP_DEPLOYMENT.md) | Describes the retired Terraform / Python-Pulumi + GCP Workflows deploy. Infrastructure moved to TypeScript Pulumi in [`infra-ts/`](../../infra-ts/); see [DEPLOY.md](../../DEPLOY.md). GCP project facts (project ID, region, IAM) remain accurate. |
| [TEMPORAL_TO_GCP_WORKFLOWS_MIGRATION.md](TEMPORAL_TO_GCP_WORKFLOWS_MIGRATION.md) | Self-described historical plan for Temporal → GCP Workflows. Orchestration has since moved again, off GCP Workflows and into the Go `intent-controller`. |
| [precision-genomics-agent-platform-IMPLEMENTATION-PLAN-v3.md](precision-genomics-agent-platform-IMPLEMENTATION-PLAN-v3.md) | Original (Feb 2026) implementation plan, predating the Go + TypeScript pivot. Useful for design rationale and the precisionFDA foundation only. |

> Note: relative links *inside* these archived files may point at paths as they
> existed before archival. Trust the table above over in-document links.
