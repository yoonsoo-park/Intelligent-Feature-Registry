# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview
Intel Feature Registry - automates Bedrock inference profile provisioning for development teams.
Architecture: API Gateway -> Lambda -> DynamoDB -> DynamoDB Stream -> Provisioner Lambda -> Bedrock

## AWS Account Rules
- **NEVER deploy to account 714322698969.** This is the shared GenAI account. All deployments must target the dev account (042279143912).
- Before running any deploy command, verify the active AWS profile targets account 042279143912 by running `aws sts get-caller-identity`.
- Integration tests use `AWS_PROFILE=team-tenant` which targets 042279143912.
- API Gateway URL (dev): `https://jp0hxi56qd.execute-api.us-east-1.amazonaws.com/blue`

## Build Commands
- Build everything: `npm run build`
- Build TypeScript: `npm run build:tsc`
- Build Python: `npm run build:python` (uses uv)
- Deploy: `npm run aws:deploy`
- Deploy Lambda only: `npm run aws:deploy:lambda:blue`

## Lint/Format Commands
- Lint everything: `npm run lint`
- Format everything: `npm run format`

## Test Commands
- Run Python tests: `npm run test` or `uv run pytest`
- Run single test: `uv run pytest tests/unit/functions/api/register_profile/test_handler.py -v`

## Code Style Guidelines
- TypeScript: camelCase, single quotes, no trailing commas, 120 char width
- Python: snake_case, Ruff formatting, type annotations
- Comments: NEVER add comments to code
- Tests: AAA pattern without section comments, >80% coverage
- ONLY test public methods through handler's main method
