---
name: aep-implement-epic
description: 'Autonomous epic implementation pipeline with multi-epic support. Use when the user says "implement epic" or "run the epic pipeline".'
---

## Overview

Orchestrates end-to-end implementation of one or more epics by sequentially running `/aep-implement-story` for each pending story. Discovers stories from sprint-status, spawns each through a fresh `claude -p` subprocess, verifies completion via triple-signal checks (sprint status + quality report + CI), and halts on any failure. Done stories are skipped automatically, making re-runs idempotent and safe.

**Syntax:** `/aep-implement-epic <epic-ids>` (e.g. `1` or `1,2,3`)

## On Activation

1. Load config from `{project-root}/_bmad/config.toml` (`[modules.aep]` section) and `config.user.toml`. If missing, fall back to the `[modules.bmm]` section. If still missing, inform the user that `/aep-setup` can configure the module. Use sensible defaults for anything not configured:
   - `planning_artifacts`: `{project-root}/_bmad-output/planning-artifacts`
   - `implementation_artifacts`: `{project-root}/_bmad-output/implementation-artifacts`

2. Resolve derived paths:
   - `sprint_status_file`: `{implementation_artifacts}/sprint-status.yaml`
   - `story_location`: `{implementation_artifacts}/stories`
   - `quality_report_location`: `{implementation_artifacts}/quality-reports`
   - `epics_source`: `{planning_artifacts}/epics.md`

3. **Build project context.** Read `{project-root}/CLAUDE.md` and `{planning_artifacts}/architecture.md`. Extract a compact project context summary (~200 words max) covering: project name, toolchain/package manager, app/package structure, test commands, and key conventions. Store as `{{project_context}}` for injection into sub-agent prompts.

4. Proceed to `references/epic-orchestrator.md`.
