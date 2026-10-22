# Development

## Branches

Create purpose-based branches from `main`, such as `codex/base-sandbox`. Merge validated exercises before starting the next branch from `main`. Do not include dates in branch names.

## Commits

Keep commits small and descriptive:

- `docs: document sandbox renewal`
- `feat: add support queue definition`
- `fix: resolve queue references when switching instances`

Before committing, review the diff and check that it contains no credentials, passwords, or local environment files.

## Planned deployment workflow

1. Load and validate local configuration without displaying secrets.
2. Validate the AWS identity and selected instance.
3. Resolve existing resources and their dependencies.
4. Create or update hours of operation, queues, routing profiles, and flows in dependency order.
5. Store generated identifiers in local files excluded from Git.
6. Validate the exercise and document the result.

Build the pipeline after verifying this workflow through the CLI. Deployment scripts and a pipeline are not implemented yet.
