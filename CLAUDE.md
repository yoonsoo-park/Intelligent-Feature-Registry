# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview
Intelligent Feature Registry - automates Bedrock inference profile provisioning for development teams.
Architecture: API Gateway -> Lambda -> DynamoDB -> DynamoDB Stream -> Provisioner Lambda -> Bedrock

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
- Run single test: `uv run pytest tests/unit/functions/api/register_feature/test_handler.py -v`

## Code Style Guidelines
- TypeScript: camelCase, single quotes, no trailing commas, 120 char width
- Python: snake_case, Ruff formatting, type annotations
- Comments: NEVER add comments to code
- Tests: AAA pattern without section comments, >80% coverage
- ONLY test public methods through handler's main method
