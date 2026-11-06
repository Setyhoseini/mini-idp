# mini-idp

A single-realm OIDC Identity Provider, built from scratch for the *Microservices
Engineering* homework. Implements users, groups, scopes, sessions (SSO), the
OAuth2 Authorization Code flow with PKCE, RS256-signed JWTs, introspection,
revocation, and a standalone demo Resource Server that verifies tokens via
JWKS and enforces scopes per endpoint.

Design and implementation notes: [`docs/architecture.md`](docs/architecture.md).
Library justifications: [`docs/report-appendix.md`](docs/report-appendix.md).

## Requirements

- Python 3.11 or newer
- Two terminals (both with `.venv` activated)

## Setup (one time)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/generate_keys.py
python scripts/bootstrap.py        # prints an admin JWT for API testing