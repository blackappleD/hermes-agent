# Contract: `/os_runtime`

## Command Surface

`/os_runtime` is available from CLI slash handling, gateway slash/command handling, and TUI `command.dispatch` where applicable.

## Subcommands

### `/os_runtime status`

Returns current state.

Expected output includes:

- status
- mode
- goal, if set
- turns used/max turns
- paused reason, if any
- last arbitration decision/risk, if any

### `/os_runtime passive`

Sets os_runtime state for the current session to passive.

Response:

- type: exec
- output: state line indicating passive mode

### `/os_runtime goal <text>`

Sets assisted goal for the current session and returns kickoff message.

Validation:

- `<text>` must be non-empty.
- `os_runtime.enabled` must be true.

Response:

- type: send or equivalent surface result
- notice: goal set with turn budget
- message: goal text

### `/os_runtime pause`

Pauses the current os_runtime goal and requests pending synthetic os_runtime continuation cleanup.

Response:

- type: exec
- output: paused line or no active goal

### `/os_runtime resume`

Resumes a paused os_runtime goal.

Response:

- type: send when kickoff is needed, otherwise exec status

### `/os_runtime clear`

Clears current os_runtime goal/state and requests pending synthetic os_runtime continuation cleanup.

Response:

- type: exec
- output: cleared line or no active goal

### `/os_runtime tick`

Runs one manual driver evaluation for the current session.

Rules:

- Still obeys enabled/mode/arbitration/budget gates.
- In passive mode, records but does not continue.

## Error Cases

- Config disabled: return actionable message; do not mutate state.
- Missing session id: return error.
- Empty goal: return validation error.
- Driver error: return fail-closed diagnostic and no continuation.

## Compatibility

- `/goal` behavior must remain unchanged when `os_runtime.enabled=false`.
- `/os_runtime` synthetic continuation must be distinguishable from `/goal` continuation for queue cleanup.
