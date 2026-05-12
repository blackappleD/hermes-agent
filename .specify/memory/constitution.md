# Hermes Agent Spec Constitution

## Core Principles

### I. Profile-Scoped State

Every feature that stores runtime or identity state must scope that state to the active Hermes profile. New features must use the repository's profile-aware configuration and runtime-state helpers instead of writing implicit global state. Migration from legacy external tools is out of scope unless a spec explicitly includes it.

### II. Native Surfaces Before Optional Skills

Capabilities described as native Hermes behavior must be available through core CLI, runtime, gateway, or tool surfaces without requiring an optional skill or plugin. Optional adapters may extend behavior, but core identity, safety, and user-visible diagnostics must not depend on opt-in packages.

### III. Fail-Closed External Side Effects

Operations that affect external systems must validate identity, login/session state, authorization, catalog membership, payload shape, and governance policy before making the external call. Unknown authorization, failed refresh, missing identity, or invalid payload must block the side effect and return actionable diagnostics.

### IV. Privacy and Audit Separation

Sensitive payloads, raw tokens, private keys, and unrestricted event bodies must not appear in prompts, normal tool results, default CLI/UI output, or user-facing logs. Features may retain restricted audit references only when the spec defines the retention purpose, access boundary, and redacted summary used for ordinary views.

### V. Testable Incremental Delivery

Specifications must break work into independently testable increments. High-risk behavior such as identity idempotency, fail-closed registration, authorization blocking, event deduplication, retry limits, receipt recording, and redaction must have explicit tests before implementation is considered complete.

## Technical Constraints

- Prefer existing Hermes infrastructure before introducing new frameworks: config loaders, profile-aware paths, gateway platform registry, tool registry, SessionDB or existing runtime state facilities.
- New required dependencies must be justified in the spec and reviewed before Builder implementation. Optional transports must degrade with clear diagnostics when unavailable.
- Default behavior must preserve user control. Automatic online listening, automatic responses, self-driven continuation, and automatic external publishing require explicit configuration or a separate approved feature.
- Specs must document non-goals and excluded migrations when source plans include broader work than the current issue.

## Workflow Gates

- Planner updates must modify spec-kit artifacts only unless the issue explicitly requests implementation.
- Reviewer checks must verify consistency among `spec.md`, `plan.md`, `tasks.md`, contracts, data model, quickstart, and this constitution.
- Builder may start only after spec review approval, and should implement in the story order defined by `tasks.md`.
- Each spec update that changes requirements, scope, acceptance criteria, or task breakdown must be committed and pushed on the issue branch.

## Governance

This constitution governs spec-kit work for this repository. Changes require a spec commit that explains the reason and updates any affected plan gate checks. When this constitution conflicts with issue-specific human clarification, Planner must update the spec to record the clarification and keep implementation tasks consistent with it.

**Version**: 1.0.0 | **Approved**: 2026-05-12 | **Last Amended**: 2026-05-12
