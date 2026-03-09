# blackroad-workflow-builder

> **BlackRoad Workflow Builder** — A DAG-based visual workflow execution engine with step dependencies, cycle detection, run history, Stripe payment integration, and a full CLI. Built for production.

[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![npm](https://img.shields.io/badge/npm-blackroad--workflow--builder-cb3837.svg)](https://www.npmjs.com/package/blackroad-workflow-builder)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#testing)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
  - [Python / pip](#python--pip)
  - [npm](#npm)
- [CLI Reference](#cli-reference)
  - [create](#create)
  - [add-step](#add-step)
  - [validate](#validate)
  - [run](#run)
  - [history](#history)
  - [list](#list)
  - [export](#export)
  - [delete](#delete)
- [Step Types](#step-types)
- [Condition Operators](#condition-operators)
- [Architecture](#architecture)
- [Database Schema](#database-schema)
- [Stripe Integration](#stripe-integration)
  - [Payment Capture Workflow](#payment-capture-workflow)
  - [Subscription Lifecycle Workflow](#subscription-lifecycle-workflow)
- [Configuration](#configuration)
- [API Reference](#api-reference)
  - [WorkflowEngine](#workflowengine)
  - [DAGValidator](#dagvalidator)
  - [WorkflowDB](#workflowdb)
- [Testing](#testing)
  - [Unit Tests](#unit-tests)
  - [End-to-End Tests](#end-to-end-tests)
- [License](#license)

---

## Overview

`blackroad-workflow-builder` is a production-grade DAG (Directed Acyclic Graph) workflow engine for orchestrating multi-step business processes. Use it to automate CI/CD pipelines, payment processing flows, data transformations, and event-driven operations — all with a built-in audit trail, retry logic, and cycle-safe execution.

---

## Features

| Feature | Description |
|---|---|
| 📊 **DAG Validation** | DFS cycle detection + Kahn's topological sort |
| ⚡ **Execution Engine** | Runs steps in dependency order with context propagation |
| 🔄 **Step Types** | `task`, `condition`, `transform`, `notify`, `delay`, `parallel` |
| 🧮 **Condition Evaluation** | Expression-based branching: `eq`, `ne`, `gt`, `lt`, `ge`, `le`, `contains`, `startswith` |
| 📜 **Run History** | Full audit trail per workflow with duration and per-step results |
| 🔀 **Critical Path** | Longest path analysis for performance optimization |
| 💾 **SQLite Persistence** | 5-table schema with foreign keys and indexes |
| 💳 **Stripe Integration** | Pre-built workflow templates for payment capture and subscription events |
| 🔁 **Retry Logic** | Per-step configurable retry count and delay |
| 🎨 **ANSI CLI** | 8 subcommands with color-coded output |

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Create a workflow
python src/workflow_builder.py create my-pipeline --description "My first pipeline" --tags "demo"

# 3. Add steps
python src/workflow_builder.py add-step my-pipeline fetch  --type task --config '{"command":"git pull"}'
python src/workflow_builder.py add-step my-pipeline build  --type task --depends-on <step_id>
python src/workflow_builder.py add-step my-pipeline notify --type notify --config '{"channel":"slack","message":"Build done!"}'

# 4. Validate the DAG
python src/workflow_builder.py validate my-pipeline

# 5. Run it
python src/workflow_builder.py run my-pipeline --context '{"env":"prod"}'

# 6. Inspect results
python src/workflow_builder.py history my-pipeline --limit 5
```

---

## Installation

### Python / pip

```bash
# Clone the repository
git clone https://github.com/BlackRoad-OS/blackroad-workflow-builder.git
cd blackroad-workflow-builder

# Install dependencies
pip install -r requirements.txt

# (Optional) Set a custom database location
export WORKFLOW_DB=/data/blackroad/workflow.db
```

### npm

```bash
npm install blackroad-workflow-builder
```

The npm package exposes a Node.js CLI wrapper and a JavaScript client for
embedding workflows in your Node/Express/Next.js applications:

```js
const { WorkflowClient } = require('blackroad-workflow-builder');

const client = new WorkflowClient({ dbPath: process.env.WORKFLOW_DB });
await client.create('payment-flow', { description: 'Stripe payment capture' });
```

---

## CLI Reference

All commands follow the pattern:

```
python src/workflow_builder.py <command> [arguments] [options]
```

### create

Create a new workflow.

```bash
python src/workflow_builder.py create <name> \
  [--description "..."] \
  [--tags "tag1,tag2"] \
  [--timeout <minutes>]
```

| Argument | Default | Description |
|---|---|---|
| `name` | — | Unique workflow name |
| `--description` | `""` | Human-readable description |
| `--tags` | `""` | Comma-separated tags |
| `--timeout` | `60` | Max run duration in minutes |

### add-step

Add a step to an existing workflow.

```bash
python src/workflow_builder.py add-step <workflow> <name> \
  [--type task|condition|transform|notify|delay|parallel] \
  [--config '{"key":"value"}'] \
  [--depends-on <step_id>] \
  [--timeout <seconds>] \
  [--retry <count>]
```

| Argument | Default | Description |
|---|---|---|
| `workflow` | — | Workflow name |
| `name` | — | Step name (unique within workflow) |
| `--type` | `task` | Step type (see [Step Types](#step-types)) |
| `--config` | `{}` | JSON config blob for the step |
| `--depends-on` | `""` | Comma-separated step IDs this step depends on |
| `--timeout` | `30` | Step timeout in seconds |
| `--retry` | `0` | Number of retry attempts on failure |

### validate

Validate the workflow DAG for cycles and missing dependencies.

```bash
python src/workflow_builder.py validate <workflow>
```

Outputs execution order, roots, leaves, and critical path. Exits `1` if invalid.

### run

Execute a workflow.

```bash
python src/workflow_builder.py run <workflow> \
  [--context '{"key":"value"}']
```

| Argument | Default | Description |
|---|---|---|
| `workflow` | — | Workflow name |
| `--context` | `{}` | JSON context variables injected into every step |

### history

View run history for a workflow.

```bash
python src/workflow_builder.py history <workflow> [--limit <n>]
```

### list

List all workflows with step counts, run counts, and success rates.

```bash
python src/workflow_builder.py list
```

### export

Export a workflow definition and all steps to JSON.

```bash
python src/workflow_builder.py export <workflow> [--output workflow.json]
```

If `--output` is omitted, JSON is printed to stdout.

### delete

Permanently delete a workflow and all associated steps, triggers, and run history.

```bash
python src/workflow_builder.py delete <workflow>
```

---

## Step Types

| Type | Description | Config Keys |
|---|---|---|
| `task` | Runs a shell command | `command`, `env` |
| `condition` | Evaluates an expression and branches | `expression`, `operator`, `negate`, `true_next`, `false_next` |
| `transform` | Maps context keys to new keys | `mapping` (object: `{dest: src}`) |
| `notify` | Sends a notification | `channel`, `message`, `recipients` |
| `delay` | Pauses execution | `seconds` |
| `parallel` | Marks parallel execution group | — |

---

## Condition Operators

Use these inside a `condition` step's `expression` field (`"<lhs> <op> <rhs>"`):

| Operator | Meaning |
|---|---|
| `eq` | Equal (`==`) |
| `ne` | Not equal (`!=`) |
| `gt` | Greater than (`>`) |
| `lt` | Less than (`<`) |
| `ge` | Greater than or equal (`>=`) |
| `le` | Less than or equal (`<=`) |
| `contains` | String contains |
| `startswith` | String starts with |

Set `"negate": true` in config to invert the result.

---

## Architecture

```
blackroad-workflow-builder
├── src/
│   └── workflow_builder.py
│       ├── WorkflowEngine          ← Orchestrates all operations
│       │   ├── create_workflow()
│       │   ├── add_step()
│       │   ├── add_trigger()
│       │   ├── validate_dag()
│       │   ├── execute_workflow()
│       │   ├── get_run_history()
│       │   ├── list_workflows()
│       │   ├── export_workflow()
│       │   └── delete_workflow()
│       ├── DAGValidator            ← DFS + Kahn's algorithm
│       │   ├── detect_cycle()
│       │   ├── topological_sort()
│       │   ├── find_roots()
│       │   ├── find_leaves()
│       │   └── critical_path()
│       ├── WorkflowDB              ← SQLite (5 tables)
│       │   └── _init_schema()
│       ├── Condition               ← Expression evaluator
│       │   └── evaluate()
│       └── CLI (8 subcommands)
├── tests/
│   ├── test_workflow_builder.py    ← Unit tests
│   └── test_e2e.py                 ← End-to-end tests
├── package.json                    ← npm package manifest
├── requirements.txt
└── README.md
```

**Execution flow:**

```
CLI → WorkflowEngine.execute_workflow()
          │
          ├─► validate_dag()  ← DAGValidator (cycle check + topo sort)
          │
          └─► for step in execution_order:
                  _execute_step(type, config, context)
                      │
                      ├── task       → shell command metadata
                      ├── condition  → Condition.evaluate() → branch
                      ├── transform  → context key remapping
                      ├── notify     → channel/message payload
                      └── delay      → delay metadata
          │
          └─► _persist_run()  ← WorkflowDB (SQLite)
```

---

## Database Schema

Five tables with foreign-key constraints and indexed hot paths:

```sql
workflows (id PK, name UNIQUE, description, version, enabled,
           max_concurrent_runs, timeout_minutes, tags, created_at, updated_at)

steps     (id PK, workflow_id FK→workflows, name, step_type, config,
           depends_on, timeout_seconds, retry_count, retry_delay, created_at)

conditions (id PK, step_id FK→steps, expression, true_next, false_next,
            operator, negate, created_at)

triggers  (id PK, workflow_id FK→workflows, trigger_type, config,
           enabled, fire_count, last_fired, created_at)

runs      (id PK, workflow_id FK→workflows, status, started_at,
           completed_at, step_results, error, triggered_by, context,
           duration_ms)
```

**Indexes:**

```sql
idx_steps_workflow  ON steps(workflow_id)
idx_runs_workflow   ON runs(workflow_id, started_at DESC)
```

---

## Stripe Integration

Use `blackroad-workflow-builder` to model Stripe payment and subscription flows as
auditable DAGs with branching, retries, and notifications.

### Payment Capture Workflow

```bash
# Create the workflow
python src/workflow_builder.py create stripe-payment-capture \
  --description "Stripe payment intent → capture → notify" \
  --tags "stripe,payments,production"

# Step 1 — Validate the payment intent
python src/workflow_builder.py add-step stripe-payment-capture validate-intent \
  --type task \
  --config '{"command":"stripe payment_intents retrieve","env":{"PAYMENT_INTENT_ID":"payment_intent_id"}}'

# Step 2 — Check intent status (condition gate)
VALIDATE_ID=$(python src/workflow_builder.py list | grep validate-intent | awk '{print $1}')
python src/workflow_builder.py add-step stripe-payment-capture check-status \
  --type condition \
  --config '{"expression":"payment_status eq requires_capture","true_next":"capture","false_next":"notify-failed"}' \
  --depends-on "$VALIDATE_ID"

# Step 3a — Capture the payment
python src/workflow_builder.py add-step stripe-payment-capture capture \
  --type task \
  --config '{"command":"stripe payment_intents capture"}' \
  --retry 2

# Step 3b — Notify on failure
python src/workflow_builder.py add-step stripe-payment-capture notify-failed \
  --type notify \
  --config '{"channel":"slack","message":"Payment capture failed — manual review required"}'

# Step 4 — Send receipt
python src/workflow_builder.py add-step stripe-payment-capture send-receipt \
  --type notify \
  --config '{"channel":"email","message":"Your payment was captured successfully"}'

# Validate and run
python src/workflow_builder.py validate stripe-payment-capture
python src/workflow_builder.py run stripe-payment-capture \
  --context '{"payment_intent_id":"pi_xxxxx","payment_status":"requires_capture"}'
```

### Subscription Lifecycle Workflow

```bash
python src/workflow_builder.py create stripe-subscription-lifecycle \
  --description "Handle Stripe subscription events" \
  --tags "stripe,subscriptions,billing"

python src/workflow_builder.py add-step stripe-subscription-lifecycle check-event \
  --type condition \
  --config '{"expression":"event_type eq customer.subscription.deleted","true_next":"cancel-access","false_next":"update-entitlements"}'

python src/workflow_builder.py add-step stripe-subscription-lifecycle cancel-access \
  --type task \
  --config '{"command":"revoke_user_access"}'

python src/workflow_builder.py add-step stripe-subscription-lifecycle update-entitlements \
  --type transform \
  --config '{"mapping":{"user_tier":"new_plan","billing_period":"period_end"}}'

python src/workflow_builder.py add-step stripe-subscription-lifecycle notify-customer \
  --type notify \
  --config '{"channel":"email","message":"Your subscription has been updated"}'

python src/workflow_builder.py run stripe-subscription-lifecycle \
  --context '{"event_type":"customer.subscription.updated","new_plan":"pro","period_end":"2026-12-31"}'
```

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `WORKFLOW_DB` | `~/.blackroad/workflow.db` | Path to the SQLite database file |

```bash
# Use a custom database path
export WORKFLOW_DB=/var/data/blackroad/workflow.db

# Or pass inline
WORKFLOW_DB=/tmp/test.db python src/workflow_builder.py list
```

---

## API Reference

### WorkflowEngine

```python
from src.workflow_builder import WorkflowEngine, WorkflowDB

engine = WorkflowEngine(WorkflowDB("/path/to/workflow.db"))
```

| Method | Returns | Description |
|---|---|---|
| `create_workflow(name, description, tags, timeout_minutes)` | `Workflow` | Create a new workflow |
| `get_workflow_by_name(name)` | `dict \| None` | Look up a workflow by name |
| `add_step(workflow_id, name, step_type, config, depends_on, timeout, retry_count)` | `WorkflowStep` | Add a step |
| `add_trigger(workflow_id, trigger_type, config)` | `Trigger` | Register a trigger |
| `validate_dag(workflow_id)` | `dict` | Validate DAG; returns cycle info, execution order, critical path |
| `execute_workflow(workflow_id, context, triggered_by)` | `WorkflowRun` | Run the workflow |
| `get_run_history(workflow_id, limit)` | `list[dict]` | Fetch run history |
| `list_workflows()` | `list[dict]` | List all workflows with stats |
| `export_workflow(workflow_id)` | `dict` | Export workflow + steps + triggers |
| `delete_workflow(workflow_id)` | `bool` | Delete workflow and all related data |

### DAGValidator

```python
from src.workflow_builder import DAGValidator

# graph: {node_id: [dependency_id, ...]}
validator = DAGValidator(graph)
```

| Method | Returns | Description |
|---|---|---|
| `detect_cycle()` | `(bool, list[str])` | `(has_cycle, cycle_path)` |
| `topological_sort()` | `list[str]` | Kahn's algorithm execution order |
| `find_roots()` | `list[str]` | Nodes with no dependents |
| `find_leaves()` | `list[str]` | Nodes with no dependencies |
| `critical_path()` | `list[str]` | Longest path through the DAG |

### WorkflowDB

```python
from src.workflow_builder import WorkflowDB

db = WorkflowDB(db_path="/path/to/workflow.db")
# db.conn is a sqlite3.Connection
```

The constructor creates the database and runs `_init_schema()` to set up all
five tables and indexes automatically.

---

## Testing

### Unit Tests

```bash
# Run all unit tests with coverage
pytest tests/test_workflow_builder.py -v --cov=src --cov-report=term-missing

# Run a specific test
pytest tests/test_workflow_builder.py::test_dag_validation_no_cycle -v
```

### End-to-End Tests

```bash
# Run the full E2E suite (creates isolated temp databases)
pytest tests/test_e2e.py -v

# Run E2E + unit tests together
pytest tests/ -v --cov=src --cov-report=term-missing
```

The E2E tests cover:

- Complete CI/CD pipeline workflow (create → add steps → validate → run → inspect history)
- Stripe payment capture workflow (condition branching, retry, notify)
- Subscription lifecycle workflow (transform, multi-step context propagation)
- DAG export and re-import round-trip
- Concurrent workflow isolation

---

## License

Proprietary — BlackRoad OS, Inc. All rights reserved.
