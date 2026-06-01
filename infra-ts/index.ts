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
};

const dataServiceSecrets: Record<string, pulumi.Input<string>> = {
  ...commonSecrets,
  DATABASE_PASSWORD: secrets.dbPasswordSecretId,
};

const redisUrl = pulumi.interpolate`redis://${cache.host}:${cache.port}/0`;

// --- Cloud Run: Web (Next.js) ---
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
  },
  secrets: commonSecrets,
  allowUnauthenticated: true,
});

// --- Cloud Run: ML Service (Python) ---
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
  envVars: {
    ...commonEnv,
    REDIS_URL: redisUrl,
    CLOUD_SQL_INSTANCE: database.connectionName,
    PERSIST_MODELS: "true",
  },
  secrets: dataServiceSecrets,
  timeout: "900s",
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
export const cloudSqlConnectionName = database.connectionName;
export const cloudSqlPrivateIp = database.privateIp;
export const redisHost = cache.host;
export const gcsDataBucket = gcs.dataBucketName;
export const gcsModelBucket = gcs.modelBucketName;
export const registryUrl = registry.registryUrl;
