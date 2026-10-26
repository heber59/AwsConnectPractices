# Retail Banking CX

> Current voice exercise (October 26, 2026): see [AnyBank voice routing practice](VOICE-PRACTICE.md) for the new sandbox, ACXD application, three specialist queues, agent assignments, call testing, and current snapshots. The backend deployment details below describe the earlier sandbox and must be revalidated after renewal.


Learn how **AnyBank's River assistant**, a Connect flow, a backend lookup, a queue, and a human agent work together. Use one fictional customer throughout the exercise.

**Verified:** balance and card lookup flows display mock data and route to the correct queues. River asks for a customer ID, accepts a valid ID, and can hand off to a human. **Pending:** River's balance request transfers to a human because the Main flow's AI node has no tools attached. The two backend Secrets are now configured; attach the five read tools and publish the ACXD application before retesting. Browser-based agent acceptance is still a manual test.

## Start here: test the published flows

| Connect flow | Expected result | Queue |
| --- | --- | --- |
| `AnyBank-01-Balance` | Alex Morgan: checking USD 4,180.00, savings USD 12,000.00 | `AnyBank-General-Service` |
| `AnyBank-02-Cards` | Active card ending 1242 | `AnyBank-Cards-Support` |
| `AnyBank-03-AI` | River's natural conversation and human handoff | General service |

1. In **Routing → Flows**, open `AnyBank-01-Balance`. Follow: welcome → invoke Lambda → show result → set working queue → transfer to queue.
2. In **Routing → Queues**, inspect the two queues above. In **Routing → Routing profiles**, inspect `AnyBank-Demo-Agents`, which includes both queues for CHAT and VOICE.
3. In **Users → User management**, assign your test user to **AnyBank-Demo-Agents**. The deployment does not change users automatically; remember your previous profile.
4. Open **Channels → Test chat → Test Settings**, select `AnyBank-01-Balance`, and choose **Apply**. Start a new customer chat; send `Hello` if prompted.
5. Expect the welcome, both balances, and the transfer message. With the agent Offline, the contact waits in the queue. You can observe it in **Analytics and optimization → Real-time metrics → Queues**.
6. Activate the **Contact Control Panel (CCP)**, set the agent to **Available**, accept the chat, and reply. Your reply should appear in the customer widget.
7. End the contact and finish after-contact work. Select `AnyBank-02-Cards`, Apply, and open a new chat to repeat with the cards queue.

These first two flows use fixed demo customer `CUST-12345`; they do not interpret the typed request or change banking data. They demonstrate **customer → flow → backend → queue → agent**.

For the interactive experience, select `AnyBank-03-AI`, Apply, and start a new chat. River asks `What is your customer ID?`; enter `CUST-12345`, `CUST-67890`, or `CUST-11111`. After identification, try `What is my available checking balance?`, `What fees apply to overdrafts?`, or `Please connect me with a human agent.` Asking for and accepting an ID are verified; balance answering remains pending and currently triggers a handoff. This flow does not prefill `customerId`, so ACXD starts in its configured `Entry` flow instead of skipping identification. It reuses the application from the unchanged `MainFlow`. Publishing a Connect flow does not publish changes inside ACXD.

## Recreate in another sandbox

First follow the [shared setup](../README.md#sandbox-setup). Python dependencies are in the root `requirements.txt`; Node.js 22+ is also required. Update temporary credentials and `CONNECT_INSTANCE_ID` in local `config/sandbox.env`.

From the repository root, inspect and deploy the backend:

```bash
python retail-banking-cx/scripts/deploy-readonly.py
python retail-banking-cx/scripts/deploy-readonly.py --apply
python retail-banking-cx/scripts/verify-readonly.py
```

The first command only inspects AWS. `--apply` creates missing resources or updates the function, preserving existing data, the key, and URL on repeat deployment. It discovers the account ID automatically and keeps the mandatory workshop boundary. Repeat deployment and all seven HTTP checks passed; automatic creation in a completely fresh sandbox remains untested.

Open local `retail-banking-cx/readonly.env` and copy its values into **ACXD → Resources → Secrets**:

| Secret | Value |
| --- | --- |
| `API_URL_Base` | Generated base URL, without a trailing slash |
| `API_Key` | Generated API key; keep sensitive |

These correspond to the workshop's `ApiUrl` and `ApiKey`; this direct deployment does not publish them into **Event outputs**. Deploy your ACXD changes to the alias used by the Connect Agentic CX block. Enable only the five read tools with this backend.

The same two Secrets can be configured from local values with a programmatic user authorized to create/update workspace Secrets:

```bash
python retail-banking-cx/scripts/configure-acxd.py --workspace-id YOUR_WORKSPACE_UUID --apply
```

The command first validates the backend, then creates or updates only those two Secrets without logging their values. A read-only export key cannot perform this step.
To create the visible Connect exercise, the destination instance must have a published `MainFlow` with an Agentic CX block and the default customer queue flow. The script reuses that application's workspace, application, and alias:

```bash
python retail-banking-cx/scripts/deploy-connect-practice.py
python retail-banking-cx/scripts/deploy-connect-practice.py --apply
```

This creates the three flows, two queues, demo schedule, routing profile, and read-only Lambda adapter. It does not reassign users or phone numbers. Restoring ACXD resources and an arbitrary Connect snapshot is not automated.

## What is deployed

| AWS component | Purpose |
| --- | --- |
| Lambda `anybank-readonly-api` + Function URL | HTTPS GET API with `x-api-key` authentication |
| Lambda `anybank-connect-demo` | Returns a flat `Message` for Connect from the same dataset |
| DynamoDB `anybank-readonly-state` | Fictional banking records |
| IAM `lambdaDynamoRole` + existing `WorkshopLambdaBoundary` | Read access and logging within sandbox restrictions |
| CloudWatch Logs | Lambda and enabled Connect flow logs |
| STS | Deployment identity/account checks |
| Connect | Three flows, two queues, `AnyBank-Demo-Agents` profile, `AnyBank-Demo-24x7` schedule |

The backend does not use API Gateway, S3, CloudFormation, or Secrets Manager. The public API supports `getAccounts`, `getCards`, `getPayees`, `getTransactions`, and `getDisputes`; missing/incorrect keys return 403 and writes return 405. The adapter is invoked directly by Connect with instance-scoped permission.

## Fictional scenarios

Every customer starts with checking/savings balances of USD 4,180 / USD 12,000, a saved payee named City Utilities, and a posted USD 42.50 debit at Corner Market already reflected in checking.

| Customer | Name | Checking / savings | Card / last four | Payee | Charge |
| --- | --- | --- | --- | --- | --- |
| CUST-12345 | Alex Morgan | CHK-100 / SAV-100 | CARD-1000 / 1242 | PAYEE-100 | TXN-BK-1000 |
| CUST-67890 | Jordan Lee | CHK-200 / SAV-200 | CARD-2000 / 2242 | PAYEE-200 | TXN-BK-2000 |
| CUST-11111 | Taylor Reed | CHK-300 / SAV-300 | CARD-3000 / 3242 | PAYEE-300 | TXN-BK-3000 |

These project-defined fixtures differ from the original workshop seed files. Customer IDs simulate identification, not production authentication. A new sandbox receives fresh fixtures, not the previous database state.

## Local development

The local mock implements all eleven workshop tools, including writes. AWS remains read-only because the Lambda boundary does not allow DynamoDB writes.

```powershell
$env:API_KEY = 'local-workshop-key'
node retail-banking-cx/backend/server.cjs
```

The local server requires `x-api-key`, listens on `127.0.0.1:3000`, and resets on restart. ACXD cannot access localhost directly. The assistant must confirm writes before invoking them; card replacement is irreversible. Transfers/payments update local balances, disputes do not refund money, and repeated writes are not deduplicated automatically.

```bash
node --test retail-banking-cx/tests/*.test.cjs
```

GET responses use named arrays such as `accounts`; errors contain `error.message`. Request paths and parameters are defined in the supplied `acxd/*.datarequest.json` files. Response formats are project-defined.

## Files and snapshots

- `acxd-exports/`: read-only snapshots of the live workspace, including current app settings and FAQ articles; Secret values are excluded.
- `acxd/`: 21 supplied workshop assets; keep write definitions for the full scenario, but disable their tools with the AWS read-only endpoint.
- `backend/`: mock logic, local server, HTTP Lambda, and Connect adapter.
- `scripts/`: backend deployment, endpoint verification, and Connect exercise deployment.
- `tests/`: behavior, authentication, and local HTTP checks.
- `lambda-trust.json`: trust policy used when creating the bounded Lambda role.
- `connect-exports/`: timestamped snapshots of the configured instance. The first snapshot predates the demo flows and queues; its manifest describes the resources captured then.
- `.build/` and `readonly.env`: ignored local artifacts, tooling, deployment IDs, and secrets.

Capture the current instance with the [shared export utility](../scripts/export-connect.py):

```bash
python scripts/export-connect.py --practice retail-banking-cx
```

The export captures the entire configured instance, including unrelated flows if they share it. It preserves parsed flow definitions, indexes, queue/profile associations, and supported instance settings. It does not export recordings, users, prompt audio, external Lambda code, complete Lex definitions, or separate unpublished drafts. Check the manifest for gaps; restoring IDs/ARNs remains manual.

Capture ACXD separately from Connect:

```bash
python scripts/export-acxd.py --practice retail-banking-cx --workspace-id YOUR_WORKSPACE_UUID
```

The first live ACXD snapshot completed without errors: two applications, two flows, eleven data requests, one slot type, five guardrails, one knowledge base with eight FAQ articles, four modalities, and four context variables. It found no Secrets in the workspace. The imported data requests refer to `API_URL_Base` and `API_Key`, so these must be created in **ACXD → Resources → Secrets** from local `readonly.env` before retesting the API request. The snapshot does not make automatic restore available.
