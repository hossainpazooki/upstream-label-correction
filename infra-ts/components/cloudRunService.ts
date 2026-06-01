/**
 * Reusable Cloud Run v2 service ComponentResource.
 * Migrated from infra/components/cloud_run_service.py.
 */

import * as pulumi from "@pulumi/pulumi";
import * as gcp from "@pulumi/gcp";

export interface CloudRunServiceArgs {
  projectId: string;
  region: string;
  image: pulumi.Input<string>;
  port: number;
  cpu: string;
  memory: string;
  minInstances: number;
  maxInstances: number;
  vpcConnectorId: pulumi.Input<string>;
  envVars?: Record<string, pulumi.Input<string>>;
  secrets?: Record<string, pulumi.Input<string>>;
  timeout?: string;
  allowUnauthenticated?: boolean;
}

export class CloudRunService extends pulumi.ComponentResource {
  public readonly url: pulumi.Output<string>;
  public readonly serviceName: pulumi.Output<string>;

  constructor(
    name: string,
    args: CloudRunServiceArgs,
    opts?: pulumi.ComponentResourceOptions,
  ) {
    super("genomics:infra:CloudRunService", name, {}, opts);
    const child = { parent: this };

    // Build env var entries
    const envEntries: gcp.types.input.cloudrunv2.ServiceTemplateContainerEnv[] =
      [];

    for (const [key, value] of Object.entries(args.envVars ?? {})) {
      envEntries.push({ name: key, value });
    }

    for (const [key, secretId] of Object.entries(args.secrets ?? {})) {
      envEntries.push({
        name: key,
        valueSource: {
          secretKeyRef: {
            secret: secretId,
            version: "latest",
          },
        },
      });
    }

    const service = new gcp.cloudrunv2.Service(`${name}-service`, {
      name,
      project: args.projectId,
      location: args.region,
      template: {
        containers: [
          {
            image: args.image,
            ports: { containerPort: args.port },
            envs: envEntries,
            resources: {
              limits: { cpu: args.cpu, memory: args.memory },
            },
          },
        ],
        vpcAccess: {
          connector: args.vpcConnectorId,
          egress: "PRIVATE_RANGES_ONLY",
        },
        scaling: {
          minInstanceCount: args.minInstances,
          maxInstanceCount: args.maxInstances,
        },
        timeout: args.timeout ?? "300s",
      },
    }, child);

    if (args.allowUnauthenticated) {
      new gcp.cloudrunv2.ServiceIamMember(`${name}-public-access`, {
        project: args.projectId,
        location: args.region,
        name: service.name,
        role: "roles/run.invoker",
        member: "allUsers",
      }, child);
    }

    this.url = service.uri;
    this.serviceName = service.name;

    this.registerOutputs({ url: this.url, serviceName: this.serviceName });
  }
}
