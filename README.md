# AwsConnectPractices

Amazon Connect use cases and hands-on exercises for intelligent contact center solutions. Sandboxes last 8 hours: Git preserves resource definitions, and deployment scripts will recreate them in each environment.

## Getting started

1. Manually create an Amazon Connect instance with users stored in Connect.
2. Sign in through the instance access URL and verify that it belongs to the current sandbox.
3. Copy `config/sandbox.env.example` to `config/sandbox.env` if it does not exist.
4. Set temporary AWS credentials, region, and instance ID in the local file.
5. Check the S3 bucket, prefix, and CloudWatch log group for the current sandbox.

Update instance settings and credentials whenever the sandbox is renewed.

Do not commit `config/sandbox.env`. The template contains no credentials or password. The administrator password is used to sign in to Connect; CLI access requires temporary AWS credentials, including the session token.

## Project structure

```text
docs/
  sandbox.md
  development.md
  use-cases/
  exercises/
config/
  sandbox.env.example
resources/
  hours-of-operation/
  queues/
  routing-profiles/
  flows/
scripts/
```

Resource definitions are organized by type. Scripts will load the environment, resolve references for the current instance, and support repeated deployments without creating duplicates.

## First exercise

Create hours of operation, a support queue, and a welcome flow. Document the scenario, deploy its dependencies, and validate the behavior. CLI deployment and validation are not implemented yet; this repository currently provides documentation and configuration scaffolding.

## Documentation

- [Sandbox setup and renewal](docs/sandbox.md).
- [Development workflow, branches, and commits](docs/development.md).

Initial persistence covers definitions stored in Git. Keeping S3 and CloudWatch resource names does not back up recordings, transcripts, or logs outside the sandbox.
