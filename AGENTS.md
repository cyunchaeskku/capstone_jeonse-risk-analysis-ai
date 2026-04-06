# AGENTS.md

## Purpose

This file provides working instructions and project context for agents operating in this repository.
Read this file before making changes.

## Project

- Name: AI-based Jeonse Fraud Risk Analysis and Legal Knowledge Support System
- Repository root: `capstone_jeonse-risk-analysis-ai`
- Primary goal: analyze jeonse-related risk factors from user input and documents, explain the result, and support law/case-based Q&A

## Current State

- Repository is in an early planning stage
- Core documentation skeleton has been created under `docs/`
- Proposal document exists and should be treated as submission-oriented material, not the implementation source of truth
- Two external legal data assets are selected for documentation and future integration:
  - `korean-law-mcp`: `https://github.com/chrisryugj/korean-law-mcp`
  - `legalize-kr`: `https://github.com/legalize-kr/legalize-kr/tree/main`

## Source Of Truth

Use these files as the main implementation references:

- `docs/architecture.md`
- `docs/domain-model.md`
- `docs/api-contract.md`
- `docs/specs/risk-analysis.md`
- `docs/specs/document-pipeline.md`
- `docs/specs/legal-qa.md`
- `docs/adr/`
- `docs/WORKING_CONTEXT.md`

## Working Rules

- Do not treat the LLM as the final authority for risk scoring
- Keep risk judgment deterministic and rule-based unless an ADR explicitly changes that
- Keep legal Q&A separate from risk evaluation logic
- Treat external legal sources as integration dependencies, not as implicit source of truth without a spec update
- Prefer updating docs first when making architecture or interface decisions
- Record major technical decisions in `docs/adr/`
- Keep `docs/WORKING_CONTEXT.md` short and current so future sessions can resume quickly

## Expected System Boundaries

- Frontend: user input, upload flow, result presentation, Q&A UI
- Backend API: orchestration, validation, result delivery
- Document pipeline: parsing, normalization, storage handoff
- Risk engine: rule evaluation and aggregated risk result
- Explanation layer: natural-language explanation from structured analysis results
- Legal QA: retrieval plus grounded answer generation from laws and cases
- External legal sources: `korean-law-mcp` for law lookup candidates, `legalize-kr` for legal text ingestion candidates

## Non-Goals For Early Versions

- End-to-end autonomous legal judgment
- LLM-only risk classification
- Mixing Q&A output into the deterministic risk score

## Documentation Practice

- Proposal-style writing belongs in `docs/제안서.md`
- Execution-oriented design belongs in `docs/`
- When adding a new feature, update the relevant spec before or alongside implementation
- If a decision changes an existing assumption, update both ADR and working context

## Session Handoff

Before ending a substantial work session, update:

1. `docs/WORKING_CONTEXT.md`
2. Relevant spec documents in `docs/specs/`
3. ADR documents if a technical decision was made

## Notes

- Prefer concise, implementation-oriented documentation
- Avoid broad refactors without first checking documented boundaries
- If repo structure evolves, keep this file aligned with the current source of truth
