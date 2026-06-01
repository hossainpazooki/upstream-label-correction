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
  };
}
