# AWS Connect Practices

Hands-on Amazon Connect and Agentic CX Designer (ACXD) exercises for intelligent contact centers. Each practice lives in its own top-level folder; shared configuration and utilities stay at the repository root.

## Practices

| Practice | Scope | Start here |
| --- | --- | --- |
| Retail Banking CX | AnyBank mock API, ACXD assets, and published Connect flows and queues | [Practice guide](retail-banking-cx/README.md) |

## Sandbox setup

1. Manually create the Amazon Connect instance, selecting users stored in Connect.
2. Copy `config/sandbox.env.example` to `config/sandbox.env` if it does not exist.
3. Set temporary AWS credentials, session token, region, instance ID, and access details in that local file.
4. Update it whenever the 8-hour sandbox is renewed, even more than once per day.
5. Open a practice README and follow its deployment and testing steps.

Install the shared Python SDK once; backend exercises also require Node.js 22+:

```bash
python -m pip install -r requirements.txt
```

The scripts read the environment file themselves. AWS CLI and editor extensions do not load it automatically. The Connect administrator password is for browser sign-in; programmatic access uses AWS credentials. Local `.env` files are excluded from Git. Keep the versioned template free of credentials and passwords.

## Repository layout

```text
config/
  sandbox.env.example
scripts/
  export-connect.py
  export-acxd.py
requirements.txt
retail-banking-cx/
  README.md
  acxd/
  backend/
  connect-exports/
  scripts/
  tests/
```

For another exercise, create a sibling folder such as `insurance-cx/` or `travel-cx/`. Add it to the practice table above. Keep its scenario, setup, tests, and expected results in its own README. Create only the subfolders it needs:

| Location | What belongs there |
| --- | --- |
| `config/` | Shared local sandbox identity and instance configuration |
| Root `scripts/` | Utilities that work across practices |
| `<practice>/acxd/` | That practice's conversational assets |
| `<practice>/backend/` | Its API and business logic |
| `<practice>/scripts/` | Its deployment and verification commands |
| `<practice>/connect-exports/` | Preserved source-instance snapshots |
| `<practice>/tests/` | Its automated tests |
| `<practice>/.build/`, local `.env` files | Generated files and secrets, excluded from Git |

Use practice-specific AWS resource names to avoid collisions in a shared sandbox. A practice script must not modify another practice's resources. Workshop-required shared roles are explicit exceptions and must keep their mandatory permissions boundaries.

## Preserve Connect definitions

Choose the practice that should hold the snapshot:

```bash
python scripts/export-connect.py --practice retail-banking-cx
```

The export reads the entire configured instance and saves a new timestamped directory inside that practice's `connect-exports/`. It does not filter resources by practice. Inspect `manifest.json`: partial exports retain saved files and exit unsuccessfully. Optional `--output` must point inside the selected practice.

Snapshots preserve definitions, not a full environment backup. Generic restoration and ID/ARN remapping are not implemented. Recordings, contact history, users, prompt audio, external Lambda code, and complete Lex definitions need separate preservation. The Retail Banking deployment scripts recreate their own demo resources; they do not restore an arbitrary snapshot. An automated pipeline is not implemented.

## Preserve ACXD definitions

Save the programmatic user's key as `ACXD_API_KEY` in local `config/sandbox.env`. This is separate from the mock backend's `API_Key`. Use a workspace-scoped read-only user for backups. The workspace UUID appears after `/acxd/w/` in the browser URL.

```bash
python scripts/export-acxd.py --practice retail-banking-cx --workspace-id YOUR_WORKSPACE_UUID
```

Alternatively, set `ACXD_WORKSPACE_ID` locally and omit the flag. Each run writes a timestamped `acxd-exports/` snapshot inside the selected practice. It preserves current applications, flows, data requests, slots, guardrails, knowledge base articles, modalities, context variables, and build/deployment metadata. Only Secret names and metadata are included; recreate their values in the destination workspace.

This is a read-only SDK-API backup, not an automated restore or a set of UI import files. Recreating another workspace requires dependency/ID remapping, new secrets, builds/deployments, and reconnecting the destination Connect flow. Check the manifest for errors and exclusions before treating a snapshot as complete.
## Git workflow

Branch by purpose, without dates: `codex/base-sandbox`, `codex/retail-banking-flows`, or `codex/insurance-cx`. Keep `main` stable and commits small, with English messages:

- `docs: explain sandbox renewal`
- `feat: add banking support queues`
- `fix: resolve queue references after sandbox renewal`

Review staged changes for local configuration and secrets before committing.
