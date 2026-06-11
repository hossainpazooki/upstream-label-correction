/**
 * Typed configuration loader for Pulumi stack.
 * Replaces infra/config.py.
 */

import * as pulumi from "@pulumi/pulumi";

export interface InfraConfig {
  projectId: string;
  region: string;
  zone: string;
  dbTier: string;
  dbPassword: pulumi.Output<string>;
  anthropicApiKey: pulumi.Output<string>;
  experimentName: string;
  modelImageTag: string;
  // gap #8: shared internal service token + the public web edge's API keys.
  serviceAuthToken: pulumi.Output<string>;
  webApiKeys: pulumi.Output<string>;
}

export function loadConfig(): InfraConfig {
  const cfg = new pulumi.Config();
  const gcpCfg = new pulumi.Config("gcp");

  return {
    projectId: gcpCfg.require("project"),
    region: gcpCfg.get("region") ?? "us-central1",
    zone: cfg.get("zone") ?? "us-central1-a",
    dbTier: cfg.get("db_tier") ?? "db-custom-2-8192",
    dbPassword: cfg.requireSecret("db_password"),
    anthropicApiKey: cfg.requireSecret("anthropic_api_key"),
    experimentName: cfg.get("experiment_name") ?? "precision-genomics",
    modelImageTag: cfg.get("modelImageTag") ?? "latest",
    serviceAuthToken: cfg.requireSecret("service_auth_token"),
    webApiKeys: cfg.requireSecret("web_api_keys"),
  };
}
