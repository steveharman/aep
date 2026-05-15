---
name: aep-post-story-quality
description: 'Autonomous post-story quality gate with loop-backs. Use when the user says "run quality gate" or "quality check story".'
---

## Overview

Autonomous 7-step quality gate that runs after a story has been manually implemented. Uses Claude Code Task sub-agents for each review phase: adversarial code review, edge-case analysis, QA test generation, complementary business review, test quality assessment, traceability check, documentation, CI verification, and sprint status update. Each step supports bounded loop-backs with targeted verification (not full re-runs). Halts immediately on any step that fails after max loop-backs.

Use this when you've implemented a story manually and want to run the full quality checks before marking it done.

## On Activation

1. Load config from `{project-root}/_bmad/config.toml` (`[modules.aep]` section) and `config.user.toml`. If missing, fall back to the `[modules.bmm]` section. If still missing, inform the user that `/aep-setup` can configure the module. Use sensible defaults for anything not configured:
   - `planning_artifacts`: `{project-root}/_bmad-output/planning-artifacts`
   - `implementation_artifacts`: `{project-root}/_bmad-output/implementation-artifacts`

2. Resolve derived paths:
   - `sprint_status_file`: `{implementation_artifacts}/sprint-status.yaml`
   - `story_location`: `{implementation_artifacts}/stories`
   - `quality_report_location`: `{implementation_artifacts}/quality-reports`

3. Resolve customization — read `customize.toml` values (max loopbacks, etc.). Apply overrides from `{project-root}/_bmad/custom/aep-post-story-quality.toml` and `.user.toml` if present.

4. **Build project context.** Read `{project-root}/CLAUDE.md` and `{planning_artifacts}/architecture.md`. Extract a compact project context summary covering: project name, toolchain, app/package structure, test commands, key conventions. Store as `{{project_context}}`.

5. Proceed to `references/quality-gate.md`.
