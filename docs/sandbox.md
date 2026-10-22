# Sandbox setup

This repository contains Amazon Connect use cases and exercises for intelligent contact center solutions. Sandboxes last 8 hours; versioned definitions and scripts will allow resources to be recreated through the CLI.

## Prerequisites

Manually create an Amazon Connect instance before deploying resources. Select users stored in Amazon Connect for identity management. Copy the actual access URL shown by Amazon Connect.

## Local configuration

Copy `config/sandbox.env.example` to `config/sandbox.env` in a new checkout. Set temporary AWS credentials, session token, region, instance ID, and access URL.

Update the file whenever the sandbox is renewed, even multiple times on the same day. Store the administrator password only in the local file. This file contains plaintext secrets and is excluded from Git by `.gitignore`. Keep the versioned template free of secrets and avoid printing credentials in logs.

The administrator password is used to sign in to Connect. The CLI uses AWS credentials. Environment loading and deployment scripts are not implemented yet.

## Planned structure

- `docs/use-cases/`: scenarios and objectives.
- `docs/exercises/`: instructions and validation.
- `config/`: local configuration and template.
- `resources/queues/`: queues.
- `resources/flows/`: flows.
- `resources/routing-profiles/`: routing profiles.
- `resources/hours-of-operation/`: hours of operation.
- `scripts/`: CLI validation and deployment.

Deployments will start from an existing instance and resolve dependencies and identifiers in the current sandbox. Initial persistence covers definitions; recordings and contact history require a separate backup strategy.

## Branches and commits

Use purpose-based branches without dates, such as `codex/base-sandbox`. Merge validated work into `main` and create subsequent branches from that base.

- `docs: document sandbox renewal`
- `feat: add support queue definition`
- `fix: resolve queue references when switching instances`

## Access URL and storage

Set `CONNECT_ACCESS_URL` to the current instance access URL. If the alias changes, review the storage prefix as well.

- `CONNECT_S3_BUCKET`: bucket name; confirm it for each sandbox.
- `CONNECT_S3_PREFIX`: path within the bucket; confirm it for each sandbox.
- `CONNECT_LOG_GROUP`: CloudWatch log group; confirm it for each sandbox.

Review these values after creating each instance. The bucket and prefix are separate fields; do not include `s3://` in the bucket name. These destinations do not provide a backup outside the sandbox.

See the [development workflow](development.md) for branch and commit conventions.
