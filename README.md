# FDE Agent Starter

A scaffold for Forward Deployed Engineers to ship a working SQL analytics agent
on a customer engagement in ~15 minutes. Clone the template, edit three files,
ask Claude (or any MCP client) questions about a real database.

```bash
gh repo create acme-deployment --template tushar-badhwar/fde-agent-starter
cd acme-deployment
```

## What this v0 actually is

Be honest about scope so customer demos don't break:

| | What works **today** | Roadmap |
|---|---|---|
| **Databases** | SQLite, PostgreSQL, MySQL via SQLAlchemy | Snowflake, BigQuery, Databricks |
| **Agent SDK** | Claude Agent SDK | OpenAI Agents SDK, Gemini ADK |
| **Schema scale** | Small (tens of tables) — full schema fits in context | Semantic retrieval for warehouse-scale (hundreds+ tables) |
| **Domain context** | Hand-written markdown prepended to system prompt | Structured `business_context.yaml`, column-level annotations |
| **Self-correcting memory** | Not built | Tell-it-when-wrong feedback loop with persistent memory |

This starter is the foundation. Add SDKs / connectors / features when a real
engagement demands them, not preemptively.

## What you get out of the box

```
.
├── tools/
│   ├── sql.py             6 MCP primitives over SQLAlchemy (read-only enforced)
│   └── server.py          MCP stdio server wrapping those primitives
├── tracing/
│   └── jsonl.py           One JSONL trace per run; every tool call recorded
├── adapters/
│   └── claude.py          Claude Agent SDK runner (~150 LoC, no retries)
├── prompts/
│   └── system.md          Senior-data-analyst prompt with workflow + hard rules
├── run.py                 CLI entry point: one question → answer
├── pyproject.toml
└── README.md
```

## 15-minute setup

### 1. Install (Python 3.10–3.13; CrewAI-style dep)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
# optional, for non-SQLite engagements:
# pip install -e ".[postgres]"     # adds psycopg
# pip install -e ".[mysql]"        # adds pymysql
```

### 2. Set your API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. Point it at a database

A 30-second demo with a synthetic SQLite DB:

```bash
sqlite3 demo.db <<'EOF'
CREATE TABLE customer (id INTEGER PRIMARY KEY, name TEXT, plan TEXT);
INSERT INTO customer VALUES (1,'Acme','enterprise'),(2,'Globex','starter'),(3,'Initech','enterprise');
CREATE TABLE event (id INTEGER PRIMARY KEY, customer_id INTEGER, type TEXT, ts TEXT);
INSERT INTO event VALUES (1,1,'login','2026-05-01'),(2,1,'purchase','2026-05-02'),
                        (3,2,'login','2026-05-03'),(4,3,'purchase','2026-05-04');
EOF

python run.py "Which customers had purchase events?" --dsn sqlite:///demo.db
```

For a real customer database:

```bash
python run.py "How many enterprise customers churned last quarter?" \
    --dsn "postgresql+psycopg://user:pw@host:5432/db"
```

### 4. Add customer business context (the part that earns the engagement)

Create `business_context.md` (gitignored — keep customer info out of the
public template) with anything the model would otherwise have to guess:

```markdown
# Acme business context

- "Churned" means `subscription.status = 'cancelled'` AND
  `subscription.cancelled_at >= NOW() - INTERVAL '90 days'`.
- The `plan_tier` column has values: 'free', 'starter', 'pro', 'enterprise'.
  Treat 'pro' and 'enterprise' both as "paid" unless the question is explicit.
- The `customer` table's `created_at` is in UTC; the `event` table's `ts` is
  local time. Be careful when joining.
- We don't have data older than 2024-01-01.
```

Then:

```bash
python run.py "How many enterprise customers churned last quarter?" \
    --dsn "postgresql+psycopg://user:pw@host:5432/db" \
    --business-context business_context.md
```

The model now has the vocabulary and rules it would otherwise misinterpret.

## Use with an MCP client (Claude Desktop, Cursor, etc.)

Skip `run.py` entirely — point any MCP client at `tools.server`:

```json
{
  "mcpServers": {
    "sql": {
      "command": "python",
      "args": ["-m", "tools.server"],
      "cwd": "/path/to/your-deployment"
    }
  }
}
```

The client's model (Claude in Claude Desktop, GPT-class in Cursor, etc.) sees
the 6 SQL tools and drives the analysis itself. No `ANTHROPIC_API_KEY` is
needed in this mode — the client's subscription does the LLM work. See
[nlsql-mcp-server](https://www.npmjs.com/package/nlsql-mcp-server) for the
same pattern packaged as an npm-installable end-user product.

## Tool surface (the 6 MCP primitives)

| Tool | Purpose |
|---|---|
| `connect(dsn)` | Open a SQLAlchemy connection; returns `connection_id` |
| `list_tables(connection_id, pattern?)` | Discover tables |
| `describe_schema(connection_id, tables[])` | Columns, types, PK/FK, row counts — **selective** (give it the few relevant tables) |
| `sample_rows(connection_id, table, n=5)` | Peek at real values for ambiguous columns |
| `validate_sql(connection_id, sql)` | Parse-only dry run |
| `execute_sql(connection_id, sql, max_rows=100, timeout_s=30)` | Run a `SELECT/WITH/EXPLAIN/PRAGMA`; read-only enforced |

All connections are read-only. Writes (`INSERT`/`UPDATE`/`DROP`/...) are
rejected by a regex guard plus, for SQLite, `PRAGMA query_only = ON`.

## What to extend per engagement

The point of the template is that ~90% of code stays. Edit:

1. **`business_context.md`** — customer vocabulary, business rules, gotchas.
   This is where most of the engagement value lives.
2. **`prompts/system.md`** — optional: tweak the workflow / hard rules if the
   customer has unusual conventions (always group by tenant_id, never join
   across two specific tables, etc.).
3. **`run.py`** — optional: wrap with whatever input surface the customer
   uses (Slack bot, scheduled report, ticket triage).

Don't fork `tools/` or `adapters/` per customer — if a customer needs
different behavior, file an issue / PR upstream so every future engagement
benefits.

## Why this starter and not LangChain / CrewAI / etc.

- **One file per concern.** Six primitives in `sql.py`, ~150 LoC adapter,
  ~50 LoC server, one prompt. No abstraction layers to learn before shipping.
- **MCP as the boundary.** Any MCP client (Claude Desktop, Cursor, custom)
  drives the same tools. The adapter exists for headless / scheduled use, not
  because the boundary is the agent loop.
- **Honest about scope.** This is a v0 designed to graduate via real customer
  use, not a framework designed to anticipate every use case.

## Contributing

Improvements that generalize to all engagements: PRs welcome. Customer-specific
behavior: keep it in your forked deployment repo, not here.

## License

MIT — see [LICENSE](LICENSE).
