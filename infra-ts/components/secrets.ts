import * as pulumi from "@pulumi/pulumi";
import * as gcp from "@pulumi/gcp";

export class SecretStore extends pulumi.ComponentResource {
  public readonly anthropicKeySecretId: pulumi.Output<string>;
  public readonly dbPasswordSecretId: pulumi.Output<string>;
  // Shared internal service token (gap #8) and the public web edge's API keys.
  public readonly serviceAuthTokenSecretId: pulumi.Output<string>;
  public readonly webApiKeysSecretId: pulumi.Output<string>;

  constructor(
    name: string,
    args: {
      projectId: string;
      anthropicApiKey: pulumi.Input<string>;
      dbPassword: pulumi.Input<string>;
      serviceAuthToken: pulumi.Input<string>;
      webApiKeys: pulumi.Input<string>;
    },
    opts?: pulumi.ComponentResourceOptions,
  ) {
    super("genomics:infra:SecretStore", name, {}, opts);
    const child = { parent: this };

    const anthropicSecret = new gcp.secretmanager.Secret(`${name}-anthropic`, {
      secretId: "anthropic-api-key",
      project: args.projectId,
      replication: { auto: {} },
    }, child);

    new gcp.secretmanager.SecretVersion(`${name}-anthropic-version`, {
      secret: anthropicSecret.id,
      secretData: args.anthropicApiKey,
    }, child);

    const dbSecret = new gcp.secretmanager.Secret(`${name}-db-password`, {
      secretId: "database-password",
      project: args.projectId,
      replication: { auto: {} },
    }, child);

    new gcp.secretmanager.SecretVersion(`${name}-db-password-version`, {
      secret: dbSecret.id,
      secretData: args.dbPassword,
    }, child);

    const serviceTokenSecret = new gcp.secretmanager.Secret(`${name}-service-auth-token`, {
      secretId: "service-auth-token",
      project: args.projectId,
      replication: { auto: {} },
    }, child);

    new gcp.secretmanager.SecretVersion(`${name}-service-auth-token-version`, {
      secret: serviceTokenSecret.id,
      secretData: args.serviceAuthToken,
    }, child);

    const webApiKeysSecret = new gcp.secretmanager.Secret(`${name}-web-api-keys`, {
      secretId: "web-api-keys",
      project: args.projectId,
      replication: { auto: {} },
    }, child);

    new gcp.secretmanager.SecretVersion(`${name}-web-api-keys-version`, {
      secret: webApiKeysSecret.id,
      secretData: args.webApiKeys,
    }, child);

    this.anthropicKeySecretId = anthropicSecret.secretId;
    this.dbPasswordSecretId = dbSecret.secretId;
    this.serviceAuthTokenSecretId = serviceTokenSecret.secretId;
    this.webApiKeysSecretId = webApiKeysSecret.secretId;

    this.registerOutputs({
      anthropicKeySecretId: this.anthropicKeySecretId,
      dbPasswordSecretId: this.dbPasswordSecretId,
      serviceAuthTokenSecretId: this.serviceAuthTokenSecretId,
      webApiKeysSecretId: this.webApiKeysSecretId,
    });
  }
}
