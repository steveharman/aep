# Implement and Test Story — Autonomous Pipeline v2

> **Mode:** Autonomous. Each phase runs as a Claude Code Task sub-agent with fresh context.
> The orchestrator identifies the target story, spawns 3 phases sequentially, parses structured output, and halts on any failure.
> **HALT rule:** Any phase returning HALTED or FAILED stops the entire pipeline immediately.
> **Architecture:** Phase 3 (Quality Gate) runs as a SINGLE sub-agent with its own fresh context window. This is critical — do NOT inline quality gate steps in the orchestrator.

---

## Step 0: Pre-Flight Checks & Story Identification

**Goal:** Verify prerequisites, identify the target story, and resolve paths.

### Pre-Flight: Verify Dependencies

<action>**Check required BMad files.** Verify each of these exists. Collect any missing into `{{missing_deps}}`:

| File | Required by |
|------|------------|
| `{project-root}/.claude/skills/bmad-create-story/SKILL.md` | Phase 1 (story creation) |
| `{project-root}/.claude/skills/bmad-dev-story/SKILL.md` | Phase 2 (implementation) |
| `{project-root}/.claude/skills/aep-post-story-quality/SKILL.md` | Phase 3 (quality gate) |
| `{project-root}/CLAUDE.md` | All phases (project context) |
</action>

<check if="missing_deps is not empty">
  <action>**HALT:** Present a clear error:

  ```
  **AEP Pre-Flight Failed — Missing Dependencies**

  The following required files were not found:
  {{for each missing: - {{file}} (needed for {{required_by}})}}

  To fix:
  1. Install the BMad framework: https://github.com/bmad-artifacts/bmad-agent
     Ensure Core, BMM, and TEA modules are installed.
  2. Create a CLAUDE.md at project root with your project rules and toolchain.
  3. Run /aep-setup to configure AEP.
  ```
  </action>
</check>

### Resolve Paths (from config — set during On Activation)

- `{{sprint_status_file}}` — sprint status YAML
- `{{story_location}}` — story spec files directory
- `{{quality_report_location}}` — quality report output directory
- `{{epics_source}}` — epics breakdown document
- `{{architecture_doc}}` — architecture document

**Code roots are story-dependent.** The story file itself indicates which app/package the work touches.

### Resolve Second-Opinion Review Configuration

<action>Read `second_opinion_provider`, `second_opinion_model`, `second_opinion_required`, and `second_opinion_api_key_source` from the customize.toml config (already loaded during On Activation).</action>

<check if="second_opinion_provider != 'none'">
  <action>**Resolve the API key.** The key source name is `{{second_opinion_api_key_source}}` (e.g. "deepseek-api-key").
  1. Check environment variable: convert to SCREAMING_SNAKE_CASE with underscores replacing hyphens (e.g. "deepseek-api-key" → `DEEPSEEK_API_KEY`). If set, use it.
  2. If not in env, read `{project-root}/.env.keys`. Find the line matching `{{second_opinion_api_key_source}}=...`. Extract the value.
  3. If not in `.env.keys`, read `{project-root}/.env.local` and `{project-root}/.env` in that order.
  4. Store the resolved key as `{{second_opinion_api_key}}`.
  </action>

  <check if="API key was found">
    <action>Set `second_opinion_available = true`.</action>
    <action>Log: "Second-opinion review: {{second_opinion_provider}} / {{second_opinion_model}} — API key resolved."</action>
  </check>

  <check if="API key was NOT found">
    <action>Set `second_opinion_available = false`.</action>
    <check if="second_opinion_required == true">
      <action>**HALT:** "Second-opinion review is required but API key '{{second_opinion_api_key_source}}' not found in environment, .env.keys, .env.local, or .env."</action>
    </check>
    <check if="second_opinion_required == false">
      <action>Log: "WARNING: Second-opinion review unavailable — API key not found. Skipping (not required)."</action>
    </check>
  </check>
</check>

<check if="second_opinion_provider == 'none'">
  <action>Set `second_opinion_available = false`.</action>
  <action>Log: "Second-opinion review: disabled by config."</action>
</check>

### Story Identification

<check if="story_id is already set (provided by user or caller)">
  **Fast path.**
  <action>Derive `epic_num` from the story_id prefix (e.g. "4-3" -> epic_num = "4", "1-2" -> epic_num = "1", "R-1" -> epic_num = "R").</action>
  <action>Find the sprint-status entry matching `{{story_id}}-*`. Extract story_key and story_name.</action>
  <action>If no match -> **HALT:** "Story {{story_id}} not found in sprint-status.yaml."</action>
</check>

<check if="story_id is NOT set">
  **Auto-discovery path.**
  <action>Scan sprint-status top-to-bottom for the FIRST story where status == "backlog".</action>
  <action>If none found -> **HALT:** "No backlog stories in sprint-status.yaml."</action>
  <action>Extract story_id, epic_num, story_key, story_name.</action>
  <action>Verify parent epic (epic-{{epic_num}}) is "in-progress". If not -> **HALT:** "Story {{story_id}} belongs to epic-{{epic_num}} which is not yet in-progress."</action>
</check>

<action>Log: "**Starting pipeline for Story {{story_id}}: {{story_name}}**"</action>
<action>Enter YOLO mode for the remainder of this workflow.</action>

---

## Phase 1: Create Story

**Goal:** Spawn the create-story workflow as a sub-agent. The sub-agent creates the story file and marks it "ready-for-dev" in sprint-status.

<action>Spawn a `general-purpose` Claude Code Task sub-agent with the following prompt:</action>

```
You are running autonomous story creation as part of an implement-and-test pipeline.

CRITICAL INSTRUCTIONS:
1. Read the FULL skill file at: {project-root}/.claude/skills/bmad-create-story/SKILL.md
2. Follow the workflow instructions EXACTLY.

CONTEXT:
- Story ID: {{story_id}}
- Sprint status file: {{sprint_status_file}}

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{architecture_doc}} for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

STORY ID OVERRIDE:
- You MUST use story ID "{{story_id}}" — do NOT auto-discover a different story.

MANDATORY FORMAT RULES — ACCEPTANCE CRITERIA:
- Each AC MUST use Given/When/Then/And Gherkin syntax.
- Split monolithic chains into separate numbered scenarios per behaviour.
- Use ```gherkin fenced code blocks. Give each AC a heading: ### AC1: [Short Name]
- Do NOT flatten or convert Gherkin into declarative sentences.
- Reference any recent story file in {{story_location}}/ for format guidance.

IMPLEMENTATION CONSTRAINTS — EMBED IN STORY:
Include a "## Implementation Constraints" section (after ACs, before Tasks) with binding rules
extracted from these documents:
1. `CLAUDE.md` (project root) — Master project rules
2. {{architecture_doc}} — Architecture decisions (REQUIRED)
3. Any UX/design specification referenced in CLAUDE.md (REQUIRED for UI stories; skip for non-UI work)
4. `docs/TESTING.md` — Testing patterns (load if exists; skip if not)
5. `docs/project-context.md` — Coding standards (load if exists; skip if not)

End with: "Violations of these constraints are classified as MEDIUM severity by the quality
gate and will trigger loop-back fixes."

SPRINT STATUS — SYMLINK HANDLING:
The sprint status file may be a symlink. If editing fails with a symlink error, resolve the
real path with `readlink -f {{sprint_status_file}}` and use that path for all edits. You must
Read the real path before using Edit on it.

AUTONOMOUS BEHAVIOR:
- YOLO mode — skip all confirmations. Complete entire workflow without stopping.
- Story should reach "ready-for-dev" status.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED|HALTED]
story_id: [e.g. "1-3"]
story_key: [e.g. "1-3-setup-auth-middleware"]
story_file: [full path to created story file]
story_name: [human-readable name]
sprint_status_updated: [yes|no]
notes: [1-3 sentence summary]
---END---
```

<action>Parse ---RESULTS---. No block = status FAILED.</action>

<check if="status != 'PASSED'">
  <action>**HALT:** "Pipeline HALTED at Phase 1 (Create Story). {{notes}}"</action>
</check>

**Post-creation verification** (orchestrator, not sub-agent):

<action>Read the story file at {{story_file}}.</action>

<action>**AC format check:** Search for Given/When/Then keywords. If absent -> read epics source + a reference story file, rewrite ACs to Gherkin format, save.</action>

<action>**Implementation constraints check:** Search for "Implementation Constraints" heading. If absent -> read reference documents, generate the section, inject into story file, save.</action>

<action>Log: "**Phase 1 complete.** Story {{story_id}} created at {{story_file}}"</action>

---

## Phase 2: Implement Story

**Goal:** Spawn the dev-story workflow as a sub-agent. The sub-agent implements all tasks/subtasks with tests. Story reaches "review" status.

<action>Spawn a `general-purpose` Claude Code Task sub-agent with the following prompt:</action>

```
You are running autonomous story implementation as part of an implement-and-test pipeline.

CRITICAL INSTRUCTIONS:
1. Read the FULL skill file at: {project-root}/.claude/skills/bmad-dev-story/SKILL.md
2. Follow the workflow instructions EXACTLY.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story file: {{story_file}}
- Sprint status file: {{sprint_status_file}}

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{architecture_doc}} for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

- Determine the relevant app/package(s) for this story by reading the story file's Tasks
  and File List. Use those as your code roots.
- Use the project's package manager and build tools as specified in CLAUDE.md. Never assume
  a specific package manager — always defer to CLAUDE.md.

MANDATORY PRE-IMPLEMENTATION — READ BEFORE ANY CODE:
1. **CLAUDE.md** (project root) — THE MOST IMPORTANT FILE. Read completely.
2. {{architecture_doc}} — Architecture decisions (REQUIRED)
3. Any UX/design specification referenced in CLAUDE.md (REQUIRED for UI stories; skip for non-UI work)
4. `docs/TESTING.md` — Testing patterns (load if exists; skip if not)
5. `docs/project-context.md` — Coding standards (load if exists; skip if not)
6. Glob `{{story_location}}/*retro*.md` — most recent by date, if any
7. **Available Skills** — Scan all available skills listed in your system prompt. For each
    skill whose description matches this story's technology stack, invoke it via the Skill
    tool to load its implementation guidance. Treat loaded skill rules as binding constraints
    alongside CLAUDE.md. Only invoke skills relevant to this story.

SPRINT STATUS — SYMLINK HANDLING:
The sprint status file may be a symlink. If editing fails with a symlink error, resolve the
real path with `readlink -f {{sprint_status_file}}` and use that path for all edits. You must
Read the real path before using Edit on it.

AUTONOMOUS BEHAVIOR:
- YOLO mode. Execute continuously — implement ALL tasks/subtasks.
- Red-green-refactor per task.
- Do NOT commit or push — just implement and update the story file.
- Do NOT stop at "milestones" or "session boundaries".

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED|HALTED]
story_status: [e.g. "review" or "in-progress"]
tasks_total: [number]
tasks_completed: [number]
tests_passing: [number]
tests_failing: [number]
files_modified: [comma-separated list]
halt_reason: [reason if HALTED, "none" otherwise]
notes: [1-3 sentence summary]
---END---
```

<action>Parse ---RESULTS---. No block = status FAILED.</action>

<check if="status != 'PASSED'">
  <action>**HALT:** "Pipeline HALTED at Phase 2 (Implement). {{halt_reason}}. Tasks: {{tasks_completed}}/{{tasks_total}}, Tests failing: {{tests_failing}}"</action>
</check>

<action>Log: "**Phase 2 complete.** {{tasks_completed}}/{{tasks_total}} tasks, {{tests_passing}} tests passing."</action>

---

## Phase 3: Quality Gate

**Goal:** Spawn the quality gate as a SINGLE sub-agent with fresh context. This sub-agent runs its own multi-step quality gate (code review, edge cases, complementary review, test quality, traceability, documentation, CI verification, sprint status update) with internal sub-agents and loop-backs. It handles commit, push, and quality report generation.

**CRITICAL:** This phase MUST run as a single sub-agent — do NOT inline quality gate steps here in the orchestrator. The sub-agent gets a fresh context window, preventing context exhaustion from Phases 1-2.

<action>Spawn a `general-purpose` Claude Code Task sub-agent with the following prompt:</action>

```
You are running the autonomous post-story quality gate as part of an implement-and-test pipeline.

CRITICAL INSTRUCTIONS:
1. Read the FULL skill file at: {project-root}/.claude/skills/aep-post-story-quality/SKILL.md
2. Follow its On Activation steps to load config and resolve paths.
3. Then read and execute the quality gate instructions at: {project-root}/.claude/skills/aep-post-story-quality/references/quality-gate.md
4. Follow the quality-gate.md instructions EXACTLY — it is a self-contained workflow.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story file: {{story_file}}
- Sprint status file: {{sprint_status_file}}
- This story has already been created (Phase 1) and implemented (Phase 2).

MANDATORY REFERENCE DOCUMENTS — READ BEFORE REVIEWING:
The quality gate sub-agents MUST read these documents to correctly classify severity and
identify violations. Every rule in these documents is enforceable — violations are MEDIUM severity.

1. `{project-root}/CLAUDE.md` — Master project rules
2. {{architecture_doc}} — Architecture decisions
3. Any UX/design specification referenced in CLAUDE.md (for UI stories)
4. `{project-root}/docs/TESTING.md` — Testing patterns (if exists)
5. `{project-root}/docs/project-context.md` — Coding standards (if exists)

SPRINT STATUS — SYMLINK HANDLING:
The sprint status file may be a symlink. If editing fails with a symlink error, resolve the
real path with `readlink -f {{sprint_status_file}}` and use that path for all edits. You must
Read the real path before using Edit on it.

QUALITY REPORT PATH OVERRIDE:
Write the quality report to: {{quality_report_location}}/story-{{story_id}}-quality-report.md
(This overrides any default path the quality gate workflow may compute.)

QUALITY GATE OVERRIDES — These override the default quality gate behavior:

OVERRIDE 1 — HARDENED COMPLEMENTARY REVIEW PROMPT:
When you spawn the complementary review sub-agent, ensure its prompt includes:
  ACTIVELY TRY TO BREAK the implementation:
  - Try calling mutations with mismatched IDs — does auth prevent it?
  - Check for unbounded queries without limits — what happens with 10,000 records?
  - Check for race conditions in check-then-insert patterns
  - Verify multi-tenancy scoping: can Business A see Business B's data?
  - Check for silent error swallowing (catch blocks returning empty results)
  - Verify security-sensitive code paths have test coverage

OVERRIDE 2 — LOOP-BACK INCLUDES MEDIUM:
Trigger loop-backs on MEDIUM findings too, not just HIGH.
Both HIGH and MEDIUM issues must be fixed before the gate passes.

OVERRIDE 3 — GATE STATUS:
PASSED_WITH_CONCERNS only applies when LOW-severity findings remain.
If any MEDIUM+ issues were found, they must have been resolved via loop-back for PASSED.

AUTONOMOUS BEHAVIOR:
- Run in YOLO mode — this workflow is already designed for autonomous execution.
- Execute all quality gate steps with sub-agents and loop-backs.
- Handle commit, push, and CI verification as specified in the quality gate workflow.
- The quality gate will commit and push code — this is expected and authorized.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure — flat key-value pairs only):
---RESULTS---
status: [PASSED|PASSED_WITH_CONCERNS|FAILED|HALTED]
overall_gate_status: [PASSED|PASSED_WITH_CONCERNS|FAILED|HALTED]
total_loopbacks: [number]
total_inline_fixes: [number]
halted_at_step: [step name if HALTED, "none" otherwise]
quality_report_path: [path to generated quality report]
notes: [1-3 sentence summary]
---END---
```

<action>Parse the ---RESULTS--- block from the sub-agent output. If the sub-agent output does not contain a ---RESULTS--- block (crash, timeout, or truncated output), treat as status=FAILED with notes="Sub-agent did not return structured results."</action>

<check if="status == 'HALTED' or status == 'FAILED'">
  <action>Log: "**Pipeline partially complete.** Quality gate {{status}} at {{halted_at_step}} after {{total_loopbacks}} total loop-backs."</action>
  <action>Note: Phases 1 and 2 succeeded. Code IS implemented but quality gate didn't fully pass.</action>
</check>

<check if="status == 'PASSED' or status == 'PASSED_WITH_CONCERNS'">
  <action>Log: "**Phase 3 complete:** Quality gate {{overall_gate_status}}, {{total_loopbacks}} loop-backs, {{total_inline_fixes}} inline fixes. Report: {{quality_report_path}}"</action>
</check>

---

## Phase 4: Second-Opinion Review

**Goal:** Independent code review by an external model (DeepSeek) for cross-model verification. Runs AFTER Phase 3 so the reviewer sees the final committed code. Uses direct `curl` to the DeepSeek API — no `claude --bare` needed.

<check if="second_opinion_available == false AND second_opinion_required == true">
  <action>**HALT:** "Phase 4: Second-opinion review unavailable — no API key found. Second-opinion review is mandatory per config."</action>
</check>
<check if="second_opinion_available == false AND second_opinion_required == false">
  <action>Log: "Phase 4: Second-opinion review skipped (provider unavailable, not required)."</action>
  <action>Proceed to Post-Pipeline Verification.</action>
</check>

<action>**Collect implementation files for review.**

1. Get the list of source files changed by this story. Use the Phase 3 quality gate's commit:
   `git diff --name-only HEAD~1 HEAD -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.css' '*.mjs'`
   If that returns nothing (e.g. multiple commits), widen: `git log --oneline --since="1 hour ago" --format=%H | tail -1` as base, then `git diff --name-only <base> HEAD`.
2. For each file, read its contents using the Read tool. Concatenate into `{{review_content}}` with file separators.
3. Also read the story file and CLAUDE.md for context.
</action>

<action>**Build the review prompt.**

```
Review the implementation of Story {{story_id}} ({{story_name}}).

STORY CONTEXT:
[Include story acceptance criteria summary from {{story_file}}]

PROJECT RULES (from CLAUDE.md):
[Include key mandatory rules from CLAUDE.md]

IMPLEMENTATION FILES:
{{review_content}}

REVIEW FOCUS:
A) ADVERSARIAL: Architecture compliance, security, hardcoded values, missing tokens, raw errors in UI
B) EDGE CASES: Guard clauses, null checks, type coercion, boundary conditions
C) TEST QUALITY: Are tests meaningful? Do they cover all acceptance criteria?

SEVERITY:
- HIGH: Broken functionality, security hole, data loss
- MEDIUM: Architecture violations, accessibility gaps, mandatory rule violations from CLAUDE.md
- LOW: Style, refactoring suggestions

For EVERY LOW finding, verify it does not violate a mandatory rule from the project rules above.
If it does, upgrade to MEDIUM.

OUTPUT FORMAT:
---RESULTS---
high_count: [number]
medium_count: [number]
low_count: [number]
findings: [detailed list with severity, file, line, description for each]
notes: [1-3 sentence summary]
---END---
```
</action>

<action>**Call DeepSeek API via curl.**

```bash
RESPONSE=$(curl -s https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer {{second_opinion_api_key}}" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg prompt "$REVIEW_PROMPT" --arg model "{{second_opinion_model}}" \
    '{model: $model, messages: [{role: "user", content: $prompt}], max_tokens: 8192}')")

REVIEW_OUTPUT=$(echo "$RESPONSE" | jq -r '.choices[0].message.content // "ERROR: No response"')
```

If the curl fails or returns an error:
- Retry up to 3 times with 10-second delays
- If still failing and `second_opinion_required == true` -> **HALT**
- If still failing and `second_opinion_required == false` -> log warning and proceed
</action>

<action>**Parse the review output.** Extract `---RESULTS---` block. Count HIGH and MEDIUM findings.</action>

<action>Store findings as `{{second_opinion_findings}}` for the quality report.</action>

<action>Log: "**Phase 4 complete.** Second-opinion review: {{high_count}} HIGH, {{medium_count}} MEDIUM, {{low_count}} LOW."</action>

<check if="high_count == 0 AND medium_count == 0">
  <action>Proceed to Post-Pipeline Verification.</action>
</check>

### Phase 4b: Second-Opinion Fix

<check if="high_count > 0 OR medium_count > 0">
  <action>Initialize `second_opinion_fix_loops = 0`, `max_second_opinion_fix_loops = 3`.</action>

  <action>Spawn a `general-purpose` fix sub-agent:

  ```
  Fix ALL HIGH and MEDIUM severity findings from the second-opinion review of Story {{story_id}}.

  BINDING RULES:
  Read {project-root}/CLAUDE.md for all project rules.
  Read {{architecture_doc}} for architecture decisions.

  FINDINGS TO FIX:
  {{second_opinion_findings}}

  RULES:
  1. Fix every HIGH and MEDIUM finding.
  2. Write tests covering fixed behaviour where applicable.
  3. After all fixes, run tests and type check to confirm nothing broken.

  REQUIRED OUTPUT FORMAT:
  ---RESULTS---
  status: [PASSED|FAILED]
  fixes_applied: [number]
  tests_passing: [total]
  tests_failing: [total]
  remaining_high: [number]
  remaining_medium: [number]
  notes: [1-2 sentence summary]
  ---END---
  ```
  </action>

  <action>Parse results.</action>

  <check if="remaining_high == 0 AND remaining_medium == 0 AND tests_failing == 0">
    <action>Commit fixes: `git add . && git commit -m "fix: address second-opinion review findings for Story {{story_id}}"` with Co-Authored-By trailer. Push.</action>
    <action>Log: "**Phase 4b complete.** {{fixes_applied}} second-opinion fixes applied."</action>
  </check>

  <check if="(remaining_high > 0 OR remaining_medium > 0) AND second_opinion_fix_loops < max_second_opinion_fix_loops">
    <action>Increment second_opinion_fix_loops. Re-run fix sub-agent.</action>
  </check>

  <check if="remaining issues AND second_opinion_fix_loops >= max_second_opinion_fix_loops">
    <action>**HALT:** "Phase 4b exhausted {{max_second_opinion_fix_loops}} loops. {{remaining_high}} HIGH, {{remaining_medium}} MEDIUM remain."</action>
  </check>
</check>

---

## Post-Pipeline Verification

**Goal:** Verify that Phase 3 actually completed its deliverables. Sub-agents have a proven pattern of reporting success without completing all steps. These checks run in the orchestrator (not a sub-agent).

### Verify Sprint Status

<action>Read {{sprint_status_file}} (resolve symlink if needed: `readlink -f {{sprint_status_file}}`).</action>
<action>Find the entry for story {{story_id}}.</action>

<check if="story status is NOT 'done' AND Phase 3 status was PASSED or PASSED_WITH_CONCERNS">
  <action>Log: "**WARNING: Story {{story_id}} is '{{current_status}}' — should be 'done'. Fixing now.**"</action>
  <action>Read the real sprint status file path, then Edit to update status to "done".</action>
  <action>Stage and commit: `git add {{sprint_status_file}} && git commit -m "fix: update Story {{story_id}} sprint status to done"` with Co-Authored-By trailer.</action>
  <action>Push: `git push`.</action>
</check>

### Verify Quality Report

<action>Check if quality report exists at {{quality_report_location}}/story-{{story_id}}-quality-report.md.</action>

<check if="quality report file does NOT exist AND Phase 3 status was PASSED or PASSED_WITH_CONCERNS">
  <action>Log: "**WARNING: Quality report not found. Phase 3 reported success but didn't write the report.**"</action>
  <action>**HALT:** "Quality gate reported {{status}} but no quality report was written."</action>
</check>

<check if="quality report exists">
  <action>Verify `grep -c '^\*\*Overall Gate Status:\*\*' <path>` returns 1.</action>
  <action>If missing -> log warning but do not halt (the report exists, just incomplete format).</action>
</check>

---

## Pipeline Summary

<action>Present:

```
**Pipeline Complete — Story {{story_id}}: {{story_name}}**

| Phase | Status | Details |
|-------|--------|---------|
| 1. Create Story | {{phase1_status}} | {{phase1_notes}} |
| 2. Implement | {{phase2_status}} | {{tasks_completed}}/{{tasks_total}} tasks, {{tests_passing}} tests |
| 3. Quality Gate | {{phase3_status}} | {{total_loopbacks}} loop-backs, {{total_inline_fixes}} inline fixes |
| 4. Second-Opinion | {{phase4_status}} | {{second_opinion_high}} HIGH, {{second_opinion_medium}} MEDIUM |

**Overall: {{overall_status}}**
Quality Report: {{quality_report_path}}
```
</action>

<action>Check sprint-status for remaining stories. Suggest next action.</action>
