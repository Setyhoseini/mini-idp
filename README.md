# mini-idp

A single-realm OIDC Identity Provider built from scratch for a microservices
engineering course assignment. Implements users, groups, scopes, OIDC clients,
SSO sessions, Authorization Code + PKCE, and RS256-signed JWTs.

Design document: [`docs/architecture.md`](docs/architecture.md).

## Requirements

- Python 3.11 or newer

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
python scripts/generate_keys.py
python scripts/bootstrap.py        # seeds realm, scopes, admin, demo; prints admin JWT

uvicorn app.main:app --reload
```

Then:

- Health:     <http://localhost:8000/healthz>
- API docs:   <http://localhost:8000/docs>

The bootstrap script is idempotent — safe to re-run. It prints an admin JWT
with a 1-hour default TTL (set `BOOTSTRAP_ADMIN_TOKEN_TTL_SECONDS` to change).

## Running

Two terminals, both with `(.venv)` activated, from the project root.

**Terminal 1 — Identity Provider (port 8000):**

```bash
uvicorn app.main:app --reload
```

**Terminal 2 — Demo Resource Server (port 8001):**

```bash
uvicorn resource_server.main:app --reload --port 8001
```

Then:

- IdP health:       <http://localhost:8000/healthz>
- IdP API docs:     <http://localhost:8000/docs>
- RS health:        <http://localhost:8001/healthz>
- RS API docs:      <http://localhost:8001/docs>

## Demo

With both servers running:

```bash
python scripts/demo_sso.py       # SSO + scope filtering at the IdP
python scripts/demo_resource.py  # SSO + scope enforcement at the RS
```