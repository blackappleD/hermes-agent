# Contract: OS_RUNTIME Logs UI

## Entry Point

Page: dashboard `/logs`

The page header right side must render controls in this order:

1. `OS_RUNTIME` switch
2. Auto-refresh switch and label
3. Live badge when auto-refresh is active
4. Refresh button

## Mode Behavior

### Normal Logs Mode

When `OS_RUNTIME` is off:

- Render the existing file, level, component and line-count filters.
- Fetch via existing normal logs API.
- Render the existing raw log card.
- Preserve current auto-refresh and manual refresh behavior.

### OS_RUNTIME Mode

When `OS_RUNTIME` is on:

- Fetch via OS_RUNTIME logs API.
- Render module snapshots instead of the normal raw log card.
- Keep the page visually consistent with the existing logs page.
- Keep auto-refresh state unchanged.
- Manual refresh fetches OS_RUNTIME data.
- The regular raw log filters must not imply they filter module parameters. If shown, they must be clearly limited to raw line count; otherwise hide them in this mode.

## Required Modules

Always reserve presentation for:

- Life State
- Tension Field
- Action Potential

If no data is present for one of these modules, show an empty/unknown state without defaulting missing values to zero.

Optional modules appear only when data exists:

- SelfPrompt
- OpenIntent
- Arbitration
- Runtime Driver / Autonomous Loop

## Module Rendering

Each module must show:

- Module title
- Latest update timestamp or "No data"
- One-line summary when available
- Parameter rows containing label, current value and change cue
- Partial-data indicator when some expected fields are absent

Long values must wrap or truncate within their container without overlapping nearby controls.

## Raw Line Drawer

The bottom raw line area must:

- Start collapsed by default.
- Toggle expanded/collapsed from within OS_RUNTIME mode.
- Show OS_RUNTIME raw lines from the API response.
- Use an independent scroll container.
- Preserve a readable scroll position during auto-refresh when the user is reviewing history.
- Show invalid/unparsed lines as raw text.

## Empty and Error States

- No OS_RUNTIME data: show a concise empty state in the module area and keep refresh controls available.
- Partial module data: show available modules and mark missing modules as no data.
- API error: show a non-destructive error message and keep the OS_RUNTIME switch available so the user can return to normal logs.

## Visual Consistency

- Use existing dashboard components and style tokens.
- Keep card radius, borders, typography, badges and control density aligned with current `LogsPage`.
- Avoid nested decorative cards; module cards are repeated information items, raw drawer is a functional panel.
- Do not add a landing/hero treatment; the first viewport is the monitoring tool itself.
