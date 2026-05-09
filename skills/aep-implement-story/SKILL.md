---
name: aep-implement-story
description: 'Autonomous end-to-end story pipeline: create, implement, verify, review, fix, document, commit, quality report. Use when the user says "implement story" or "run the story pipeline".'
---

## Overview

Autonomous 12-step pipeline that takes a story from backlog to done in a single invocation. Identifies the target story from sprint-status, creates the spec, implements it, runs three parallel code reviewers (adversarial, edge-case, test quality), applies batch fixes, optionally gets a second-opinion review from an alternative LLM, runs a business logic review, generates documentation, pushes, verifies CI, and writes a quality report.

All heavy work runs in Claude Code Task sub-agents with fresh context. The orchestrator coordinates sequencing, parses structured `---RESULTS---` output from each sub-agent, and halts immediately on any failure. Fix loops are bounded. Step 4 runs three reviewers in parallel.

## On Activation

1. Load config from `{project-root}/_bmad/config.yaml` (`aep` section) and `config.user.yaml`. If missing, fall back to the `bmm` section. If still missing, inform the user that `/aep-setup` can configure the module. Use sensible defaults for anything not configured:
   - `planning_artifacts`: `{project-root}/_bmad-output/planning-artifacts`
   - `implementation_artifacts`: `{project-root}/_bmad-output/implementation-artifacts`

2. Resolve derived paths:
   - `sprint_status_file`: `{implementation_artifacts}/sprint-status.yaml`
   - `story_location`: `{implementation_artifacts}/stories`
   - `quality_report_location`: `{implementation_artifacts}/quality-reports`
   - `epics_source`: `{planning_artifacts}/epics.md`
   - `architecture_doc`: `{planning_artifacts}/architecture.md`

3. Resolve customization — read `customize.toml` values (second-opinion provider, max loopbacks, etc.). Apply overrides from `{project-root}/_bmad/custom/aep-implement-story.toml` and `.user.toml` if present.

4. **Build project context.** Read `{project-root}/CLAUDE.md` and `{{architecture_doc}}`. Extract a compact project context summary (~200 words max) covering: project name, toolchain/package manager, app/package structure, test commands, and key conventions. Store as `{{project_context}}` for injection into sub-agent prompts.

5. If `story_id` was provided by the caller, use it directly. Otherwise, discover the next backlog story from sprint-status.

6. Proceed to `references/story-pipeline.md`.
