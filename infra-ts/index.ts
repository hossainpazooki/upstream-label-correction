/**
 * Precision Genomics Agent Platform — Pulumi Infrastructure (TypeScript).
 * Migrated from infra/__main__.py.
 */

import * as pulumi from "@pulumi/pulumi";
import { loadConfig } from "./config";
import { Networking } from "./components/networking";
import { GCSBuckets } from "./components/storage";
import { ArtifactRegistry } from "./components/registry";
import { SecretStore } from "./components/secrets";
import { CloudSQLDatabase } from "./components/database";
import { MemorystoreRedis } from "./components/cache";
import { CloudRunService } from "./components/cloudRunService";
import { VertexAI } from "./components/vertexAi";
// GenomicsWorkflows removed — orchestration migrated to web/src/lib/workflows/engine.ts

const cfg = loadConfig();

// --- Networking (no dependencies) ---
const networking = new Networking("networking", {
  projectId: cfg.projectId,
  region: cfg.region,
});

// --- Storage & Registry (no dependencies) ---
const gcs = new GCSBuckets("gcs", {
  projectId: cfg.projectId,
  region: cfg.region,
});

const registry = new ArtifactRegistry("registry", {
  projectId: cfg.projectId,
  region: cfg.region,
});

// --- Secrets ---
const secrets = new SecretStore("secrets", {
  projectId: cfg.projectId,
  anthropicApiKey: cfg.anthropicApiKey,
  dbPassword: cfg.dbPassword,
  serviceAuthToken: cfg.serviceAuthToken,
  webApiKeys: cfg.webApiKeys,
});

// --- Database (depends on networking) ---
const database = new CloudSQLDatabase("database", {
  projectId: cfg.projectId,
  region: cfg.region,
  networkId: networking.networkId,
  dbPassword: cfg.dbPassword,
  dbTier: cfg.dbTier,
});

// --- Cache (depends on networking) ---
const cache = new MemorystoreRedis("cache", {
  projectId: cfg.projectId,
  region: cfg.region,
  networkId: networking.networkId,
});

// --- Shared environment variables ---
const commonEnv: Record<string, pulumi.Input<string>> = {
  ENVIRONMENT: "production",
  GCP_PROJECT_ID: cfg.projectId,
  GCS_DATA_BUCKET: gcs.dataBucketName,
  GCS_MODEL_BUCKET: gcs.modelBucketName,
  USE_SECRET_MANAGER: "true",
};

const commonSecrets: Record<string, pulumi.Input<string>> = {
  ANTHROPIC_API_KEY: secrets.anthropicKeySecretId,
  // Shared internal service token (gap #8): injected into every service so the
  // controller's dispatcher and web's server-side clients can present it and the
  // controller + ml_service can enforce it.
  SERVICE_AUTH_TOKEN: secrets.serviceAuthTokenSecretId,
};

const dataServiceSecrets: Record<string, pulumi.Input<string>> = {
  ...commonSecrets,
  DATABASE_PASSWORD: secrets.dbPasswordSecretId,
};

// The public web edge additionally gets the API keys it checks when REQUIRE_AUTH
// is on (gap #8: close the only internet-facing door into the control plane).
const webSecrets: Record<string, pulumi.Input<string>> = {
  ...commonSecrets,
  API_KEYS: secrets.webApiKeysSecretId,
};

const redisUrl = pulumi.interpolate`redis://${cache.host}:${cache.port}/0`;

// --- Cloud Run: ML Service (Python) ---
// Declared first: the intent-controller and mcp services reference its URL.
const mlService = new CloudRunService("precision-genomics-ml", {
  projectId: cfg.projectId,
  region: cfg.region,
  image: registry.registryUrl.apply((url) => `${url}/ml:${cfg.modelImageTag}`),
  port: 8000,
  cpu: "4",
  memory: "8Gi",
  minInstances: 0,
  maxInstances: 5,
  vpcConnectorId: networking.vpcConnectorId,
  // Internal-only: ml_service is never called from the public internet, only by
  // the controller and web over the VPC connector (defense-in-depth alongside
  // the SERVICE_AUTH_TOKEN check).
  ingress: "INGRESS_TRAFFIC_INTERNAL_ONLY",
  envVars: {
    ...commonEnv,
    REDIS_URL: redisUrl,
    CLOUD_SQL_INSTANCE: database.connectionName,
    PERSIST_MODELS: "true",
  },
  secrets: dataServiceSecrets,
  timeout: "900s",
});

// --- Cloud Run: Intent Controller (Go) ---
// The Go controller reads a full DATABASE_URL (not CLOUD_SQL_INSTANCE), so we
// assemble one from the Cloud SQL private IP and the `app` DB user/password the
// database component creates. cfg.dbPassword is a Pulumi secret, so Pulumi marks
// this value secret in state — but note it still lands as a plain Cloud Run env
// var (the password is visible in the service config), unlike the other services
// which inject DATABASE_PASSWORD via Secret Manager. Hardening path: store the
// assembled URL in Secret Manager and inject it via `secrets`. The password must
// be URL-safe (no @ : / # chars) as it is not percent-encoded here.
const intentDatabaseUrl = pulumi.interpolate`postgresql://app:${cfg.dbPassword}@${database.privateIp}:5432/precision_genomics`;

const intentService = new CloudRunService("precision-genomics-intent", {
  projectId: cfg.projectId,
  region: cfg.region,
  image: registry.registryUrl.apply((url) => `${url}/intent-controller:latest`),
  port: 8090,
  cpu: "1",
  memory: "512Mi",
  // Singleton: min 1 keeps the reconcile/recover loops always running. The
  // cross-replica claim/lease (durability "step 3") makes >1 safe if request
  // load ever needs it — raise maxInstances then. Internal only (no
  // allowUnauthenticated): it is fronted by the web service.
  minInstances: 1,
  maxInstances: 1,
  vpcConnectorId: networking.vpcConnectorId,
  // Internal-only: the controller drives `pulumi up`; it must never be reachable
  // from the public internet. Fronted by web over the VPC connector.
  ingress: "INGRESS_TRAFFIC_INTERNAL_ONLY",
  envVars: {
    ...commonEnv,
    DATABASE_URL: intentDatabaseUrl,
    ML_SERVICE_URL: mlService.url,
    PORT: "8090",
  },
  secrets: commonSecrets,
});

// --- Cloud Run: Web (Next.js) ---
// Declared after the intent-controller so it can proxy to its URL.
const webService = new CloudRunService("precision-genomics-web", {
  projectId: cfg.projectId,
  region: cfg.region,
  image: registry.registryUrl.apply((url) => `${url}/web:latest`),
  port: 3000,
  cpu: "2",
  memory: "2Gi",
  minInstances: 1,
  maxInstances: 10,
  vpcConnectorId: networking.vpcConnectorId,
  envVars: {
    ...commonEnv,
    REDIS_URL: redisUrl,
    CLOUD_SQL_INSTANCE: database.connectionName,
    ML_SERVICE_URL: mlService.url,
    INTENT_CONTROLLER_URL: intentService.url,
    // Close the only internet-facing door (gap #8): the web middleware enforces
    // an API key / JWT on /api/* when this is "true". API_KEYS is injected below.
    REQUIRE_AUTH: "true",
  },
  secrets: webSecrets,
  allowUnauthenticated: true,
});

// --- Cloud Run: MCP Server (TypeScript) ---
const mcpService = new CloudRunService("precision-genomics-mcp", {
  projectId: cfg.projectId,
  region: cfg.region,
  image: registry.registryUrl.apply((url) => `${url}/mcp:latest`),
  port: 8080,
  cpu: "1",
  memory: "2Gi",
  minInstances: 1,
  maxInstances: 5,
  vpcConnectorId: networking.vpcConnectorId,
  envVars: {
    ...commonEnv,
    ML_SERVICE_URL: mlService.url,
  },
  secrets: commonSecrets,
  allowUnauthenticated: true,
});

// --- Vertex AI ---
new VertexAI("vertex-ai", {
  projectId: cfg.projectId,
  region: cfg.region,
});

// --- Exports ---
export const webUrl = webService.url;
export const mlServiceUrl = mlService.url;
export const mcpUrl = mcpService.url;
export const intentControllerUrl = intentService.url;
export const cloudSqlConnectionName = database.connectionName;
export const cloudSqlPrivateIp = database.privateIp;
export const redisHost = cache.host;
export const gcsDataBucket = gcs.dataBucketName;
export const gcsModelBucket = gcs.modelBucketName;
export const registryUrl = registry.registryUrl;
