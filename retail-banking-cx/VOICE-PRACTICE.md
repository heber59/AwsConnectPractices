# AnyBank voice routing practice

Snapshot date: October 26, 2026 (America/Bogota). This is a sandbox learning exercise, not a production banking system.

The caller describes a request over the phone. Agentic CX Designer classifies it, passes context back to Amazon Connect, and Connect selects a specialist queue. The user reported a successful call after troubleshooting routing with CloudWatch. The backup captures configuration; it does not independently certify every routing scenario.

## Current configuration

- Region: `us-east-1`.
- Connect instance alias: `hesan`.
- Connect flow: `AnyBank-ACXD-Prueba`.
- ACXD workspace: `prueba`.
- ACXD application: `AnyBank -Welcome`.
- Welcome flow: `AnyBankWelcome`.
- The original `AnyBank - entrada` flow remains preserved separately.

The application also contains the imported `Entry` and `Main` flows. Its Escalation, Fallback and Unknown default behaviors currently point to `Main`; they are not separate recovery flows. Review those defaults before expanding the exercise.

## Conversation and queue handoff

```text
Start -> welcome -> Generative Journey
  account  -> Basic: routingDepartment = account  -> Escalate
  card     -> Basic: routingDepartment = card     -> Escalate
  transfer -> Basic: routingDepartment = transfer -> Escalate

Connect Agentic CX block: Escalation
  -> Set contact attributes
  -> Check contact attributes
  -> Set working queue
  -> Transfer to queue
```

The current department values are **singular**: `account`, `card`, and `transfer`. Match them exactly; earlier learning instructions used plural examples.

The Set contact attributes block copies `$.AgenticCX.ContextVariables.routingDepartment` into user-defined `routingDepartment`. The Check block reads `$.Attributes.routingDepartment`.

| Attribute value | Working queue | Agent login |
| --- | --- | --- |
| `account` | `AnyBank-Accounts` | `accountAgent` |
| `card` | `AnyBank-Cards` | `cardAgent` |
| `transfer` | `AnyBank-Transfers` | `transferAgent` |

Each branch selects its working queue before transferring. Recovery paths use the `error routing` prompt and disconnect. Published flow JSON is the authoritative source for exact connections.

## Specialist routing profiles

All associations below use VOICE. Each agent has Agent security permissions, a softphone, persistent connection, automatic voice acceptance, and an after-contact-work limit of zero. No passwords are preserved.

| Routing profile | Accounts priority / delay | Cards priority / delay | Transfers priority / delay |
| --- | --- | --- | --- |
| `AnyBank-Accounts-Specialist` | 1 / 0s | 3 / 30s | 2 / 30s |
| `AnyBank-Cards-Specialist` | 3 / 30s | 1 / 0s | 2 / 30s |
| `AnyBank-Transfers-Specialist` | 3 / 30s | 2 / 30s | 1 / 0s |

Lower priority numbers take precedence. Delay is the minimum queue age before a contact can be offered to an agent with that routing profile; it does not move the contact between queues or guarantee a maximum wait. The backup includes the actual queue associations, priorities, delays, channel settings and default outbound queues.

## Call test

1. Ensure the ACXD application has a completed build and deployed alias.
2. Verify the Connect Agentic CX block references this destination workspace, application and alias.
3. Save and publish the Connect flow after editing it.
4. Associate the inbound phone number with that flow in Connect.
5. Sign in as the relevant agent, open the CCP, allow microphone access and select Available.
6. From Colombia, dial the practice toll-free number as `018000930676` (stored internationally as `+578000930676`). Reachability can depend on the originating carrier.
7. Ask for help with a card, account, or transfer, and confirm when prompted. Verify the call reaches the expected specialist.
8. End the contact and complete any after-contact work.

The number belongs to a temporary sandbox; it is not a permanent public demo number. After renewal, use the newly assigned number and destination IDs.

## Troubleshooting

Enable flow logs for the instance and place Set logging behavior -> Enable at the start of the Connect flow. Publish and repeat the call. Find its Contact ID through Contact search, then query the instance's CloudWatch log group in `us-east-1`:

```sql
fields @timestamp, ContactFlowModuleType, Results, Parameters, @message
| filter ContactId = "CONTACT_ID"
| sort @timestamp asc
| limit 200
```

Inspect the block immediately before `error routing`: attribute comparison, working queue selection, or queue transfer. A shared error prompt does not identify the failing block by itself. An offline agent normally leaves an otherwise valid contact waiting in queue.

## Preserved snapshots

- [Connect snapshot](connect-exports/20261026T203108215357Z/manifest.json): 22 flows, four queues including BasicQueue, four routing profiles including the default, one schedule, and supported instance definitions. No export errors.
- [ACXD snapshot](acxd-exports/20261026T203028061526Z/manifest.json): three applications, three flows, eleven Data requests, one slot type, five guardrails, one knowledge base with eight articles, four modalities and six context variables. No export errors.
- Supplemental `practice-agent-assignments.json` preserves the three demo logins and their profile/phone configuration without passwords or identity details.
- Supplemental `practice-phone-numbers.json` records the current phone inventory. Recheck the number-to-flow association manually when rebuilding.
- [Initial flow review](connect-exports/20261026T114022-entrada-review/flow.json) preserves the earlier welcome/DTMF version.

Credentials, API keys, secret values, agent passwords, recordings, contact history, and CloudWatch logs are not committed. IDs and ARNs refer to the source sandbox. These snapshots require dependency remapping and recreation in a new environment; they are not a one-command restore.

## Pending work

- Verify customer identity against a backend. A shared demo VIP code is not authentication.
- The current VIP branch sets `customerTier = VIP` and continues to cards. It does not yet validate membership or configure per-contact VIP routing priority.
- Add explicit fallback and unknown recovery behavior instead of reusing the imported Main assistant.
- Recreate and configure the read-only backend before enabling banking tools. The current workspace contains Data request definitions but no backend Secrets; the AI journey currently has no tools attached.
- Test silence/timeouts, failures, unavailable agents, queue capacity, cross-team delay and each specialty independently.
