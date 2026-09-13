# Graph Fact Checker

An AI agent that verifies factual claims — especially on-chain / crypto claims —
against two independent sources of truth:

1. **Live on-chain data**, queried through [The Graph](https://thegraph.com/)'s
   Token API and Subgraph products.
2. **A structured knowledge graph** (GRC-20 / Geo), for claims that aren't purely
   transactional — "who founded this DAO", "what does this contract address
   correspond to", "what did this audit report conclude".

The agent doesn't just say "true" or "false" — it returns a verdict, a
confidence score, and the exact evidence (transaction hashes, entity IDs,
source links) that a human can independently check.
Every verification is logged, so the system builds an audit trail and, over time, an evaluation
dataset of how accurate it actually is.

## Why this architecture

A "fact-checking AI" that only calls an LLM is not trustworthy — the LLM can
hallucinate a plausible-sounding verdict.
The whole point of this project is that **every claim resolves to real, checkable data**:

- On-chain claims resolve to a `tx_hash` that anyone can look up on a block
  explorer.
- Knowledge-graph claims resolve to a GRC-20 entity ID that anyone can look up
  in the source Space.

The AI's job is narrower than it sounds: extract what's actually being
claimed, decide which data source(s) can check it, call them, and compare.
That's a much more constrained (and more reliable) task than "ask an LLM if
this is true."

## Quickstart

By default the project runs entirely against **recorded fixtures** — real,
previously-captured API responses — so you can run and test the whole system
before you have any API keys. This mirrors how you'd develop against a
flaky or rate-limited external API in any production system.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run the test suite (uses fixtures, no network calls, no API keys needed)
pytest

# Start the API
uvicorn app.main:app --reload --port 8001
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.

## Switching to live data

Once you have keys, set these in `.env` and switch `DATA_SOURCE=live`:

- `ANTHROPIC_API_KEY` — for the agent's reasoning (get one at
  https://console.anthropic.com/)
- `THE_GRAPH_API_KEY` — for Token API / Subgraph queries via The Graph's
  gateway (get one at https://thegraph.com/studio/)
- `GRC20_API_ORIGIN` — the GRC-20 / Geo API endpoint you're reading from.
  **This is evolving infrastructure** — check
  https://thegraph.com/docs/en/hypergraph/overview for the current endpoint
  and package name before wiring this up for real. The client in
  `app/tools/knowledge_graph.py` is written against a stable interface so you
  can update the underlying endpoint without touching the rest of the app.

## Running with Docker

```bash
docker compose up --build
```

This starts the API, a Postgres database, and a Redis cache together. See
`docker-compose.yml`.

## Documentation for newcomers

Every module has a docstring at the top explaining **what it does and why it
exists**, aimed at someone who knows Python but is new to either AI agents or
The Graph's ecosystem. If you're new to:

- **The Graph / subgraphs**: start with `app/tools/subgraph_mcp.py`
- **GRC-20 / knowledge graphs**: start with `app/tools/knowledge_graph.py`
- **AI tool-use / agents**: start with `app/agent/orchestrator.py`
- **How it all fits together**: start with `app/services/verification.py`
