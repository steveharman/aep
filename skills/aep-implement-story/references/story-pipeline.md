# Implement and Test Story — Autonomous Pipeline v2

> **Mode:** Autonomous. Each phase runs as a Claude Code Task sub-agent with fresh context.
> The orchestrator identifies the target story, spawns phases sequentially (with parallel reviewers at Step 4), parses structured output, and halts on any failure.
> **HALT rule:** Any phase returning HALTED or FAILED stops the entire pipeline immediately.

---

## Step 0: Story Identification & Context

**Goal:** Identify the target story and resolve paths.

## Resolved Paths (from config — set during On Activation)

- `{{sprint_status_file}}` — sprint status YAML
- `{{story_location}}` — story spec files directory
- `{{quality_report_location}}` — quality report output directory
- `{{epics_source}}` — epics breakdown document
- `{{architecture_doc}}` — architecture document

**Code roots are story-dependent.** The story file itself indicates which app/package the work touches.

Refer to "the relevant app/package" throughout — never hardcode a single root.

**Story identification:**

<check if="story_id is already set (provided by user or caller)">
  **Fast path.**
  <action>Derive `epic_num` from the story_id prefix (e.g. "4-3" -> epic_num = "4", "1-2" -> epic_num = "1").</action>
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

<action>**Load second-opinion config.**

Read `second_opinion_provider` from customize.toml (default: "deepseek").
Read `second_opinion_required` (default: true).
Read `second_opinion_model` (default: "deepseek-v4-pro").
Read `second_opinion_api_key_source` (default: "deepseek-api-key").

If provider is "none" -> set `{{second_opinion_available}} = false`, skip Step 5b entirely.
If provider is set, load the API key from `.env.keys` using the configured key source.
If key is empty and required is true -> set `{{second_opinion_available}} = false` and log warning.
If key is empty and required is false -> set `{{second_opinion_available}} = false` and log: "Warning: no API key for second-opinion provider — Step 5b will be skipped."
If key is present -> set `{{second_opinion_api_key}}` and `{{second_opinion_available}} = true`.
</action>

<action>Log: "**Starting pipeline for Story {{story_id}}: {{story_name}}**"</action>
<action>Enter YOLO mode for the remainder of this workflow.</action>

---

## Step 1: Create Story Spec

**Goal:** Create the story file with acceptance criteria, implementation constraints, and tasks.

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
  <action>**HALT:** "Pipeline HALTED at Step 1 (Create Story). {{notes}}"</action>
</check>

**Post-creation verification** (orchestrator, not sub-agent):

<action>Read the story file at {{story_file}}.</action>

<action>**AC format check:** Search for Given/When/Then keywords. If absent -> read epics source + a reference story file, rewrite ACs to Gherkin format, save.</action>

<action>**Implementation constraints check:** Search for "Implementation Constraints" heading. If absent -> read reference documents, generate the section, inject into story file, save.</action>

<action>Capture baseline SHA for later diff: `{{pre_story_sha}} = $(git rev-parse HEAD)`. This is the last commit before implementation begins — used by Step 4 to generate a precise diff.</action>

<action>Log: "**Step 1 complete.** Story {{story_id}} created at {{story_file}}"</action>

---

## Step 2: Implement Story

**Goal:** Implement all tasks/subtasks with tests. Story reaches "review" status.

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
  <action>**HALT:** "Pipeline HALTED at Step 2 (Implement). {{halt_reason}}. Tasks: {{tasks_completed}}/{{tasks_total}}, Tests failing: {{tests_failing}}"</action>
</check>

<action>Log: "**Step 2 complete.** {{tasks_completed}}/{{tasks_total}} tasks, {{tests_passing}} tests passing."</action>

---

## Step 3: Local Verification

**Goal:** Run tests and type-check in the orchestrator BEFORE burning reviewer tokens. Fast and cheap.

<action>Initialize `local_verify_loops = 0`, `max_local_verify_loops = 3`.</action>

### Step 3 — Verify

<action>Run tests:
- Determine which app/package was modified from the story's files_modified list.
- Run tests using the project's test runner as specified in CLAUDE.md
- Scope tests to the relevant app/package if the project supports scoped test runs
- Run type checking as specified in CLAUDE.md

Capture test output, count passing/failing.</action>

<action>Run type check:
- Use the project's type-check command as specified in CLAUDE.md

Capture any errors.</action>

<check if="tests all passing AND type check clean">
  <action>Log: "**Step 3 passed.** All tests green, types clean."</action>
  <action>Proceed to Step 4.</action>
</check>

<check if="failures exist AND local_verify_loops < max_local_verify_loops">
  <action>Increment local_verify_loops.</action>
  <action>Log: "**Step 3 loop-back {{local_verify_loops}}/{{max_local_verify_loops}}** — fixing test/type failures."</action>

  <action>Spawn a `general-purpose` fix sub-agent:

  ```
  Fix the following test and type-check failures for Story {{story_id}}.

  TEST FAILURES:
  {{test_output}}

  TYPE ERRORS:
  {{tsc_output}}

  PROJECT CONTEXT:
  {{project_context}}

  BINDING RULES:
  Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
  Read {{architecture_doc}} for architecture decisions and constraints.
  Treat rules from these documents as binding constraints.

  RULES:
  1. Fix only the failures listed.
  2. Prefer fixing tests if component behaviour is correct.
  3. After fixes, run tests and type check to confirm.
  4. Read CLAUDE.md for project rules if needed.

  REQUIRED OUTPUT FORMAT:
  ---RESULTS---
  status: [PASSED|FAILED]
  fixes_applied: [number]
  tests_passing: [number]
  tests_failing: [number]
  tsc_clean: [yes|no]
  notes: [1-2 sentence summary]
  ---END---
  ```
  </action>
  <goto step="Step 3 — Verify"/>
</check>

<check if="failures exist AND local_verify_loops >= max_local_verify_loops">
  <action>**HALT:** "Step 3 (Local Verification) failed after {{max_local_verify_loops}} loops. {{tests_failing}} test failures, type errors remain."</action>
</check>

---

## Step 4: Parallel Review

**Goal:** Run 3 independent Claude reviewers simultaneously. Collect all findings into a unified list for batch fixing. Second-opinion reviews separately after fixes (Step 5b).

<action>Generate the diff for reviewers: `git diff {{pre_story_sha}} HEAD -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.css'` (baseline SHA captured at end of Step 1). Store as `{{story_diff}}`.</action>

<action>If `{{story_diff}}` is empty (config/docs-only story) -> skip Steps 4-5c, proceed to Step 6.</action>

<action>Spawn ALL THREE sub-agents simultaneously (do not wait for one before starting the next):</action>

### 4a: Adversarial Code Review

```
You are an adversarial code reviewer. Challenge quality, architecture compliance, security, performance.

CRITICAL INSTRUCTIONS:
1. Read the adversarial review task: {project-root}/_bmad/core/tasks/review-adversarial-general.xml
2. Follow its instructions exactly.

CONTENT TO REVIEW:
{{story_diff}}

CONTEXT:
- Story ID: {{story_id}}, Story Name: {{story_name}}
- Story file: {{story_file}}

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{architecture_doc}} for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

ALSO CONSIDER (passed to task's also_consider input):
Focus areas beyond general adversarial analysis:
- Architecture compliance (tokens, patterns from ref docs below)
- Security: auth checks, multi-tenancy scoping, input validation
- Performance: unbounded queries, N+1 patterns
- Error handling: raw errors in UI, missing fallbacks

SEVERITY CLASSIFICATION:
- HIGH: Broken functionality, security hole, data loss
- MEDIUM: Architecture violations, accessibility gaps, missing validation, violations of mandatory rules from CLAUDE.md
- LOW: Style, refactoring, nice-to-haves

MANDATORY RULE ENFORCEMENT:
Read {project-root}/CLAUDE.md for project-specific mandatory rules. Any finding that violates
a mandatory rule from CLAUDE.md MUST be classified as MEDIUM or higher, regardless of how
minor it appears. Common mandatory-rule categories include: design token discipline, i18n
wrapping, accessibility attributes, directional CSS, touch targets — but defer to whatever
CLAUDE.md actually specifies for this project.

ANTI-DOWNGRADE CHECK:
For EVERY finding classified as LOW, verify it does not violate any mandatory rule from
CLAUDE.md. If it does, upgrade to MEDIUM.

Additional anti-downgrade rules:
- "Deferred to future story" is NOT a severity downgrade
- "No token exists for this value" is NOT a severity downgrade — flag MEDIUM and note
  that the token must be CREATED. A missing token means the design system has a gap.
- "Consistent with existing patterns" is NOT a severity downgrade if the pattern itself
  violates a mandatory rule. Both the existing code AND the new code are wrong.

Include a "## Downgrade Bias Check" section listing every LOW finding and confirming none
match the mandatory rules from CLAUDE.md.

AUTONOMOUS: YOLO mode. Fix HIGH issues directly (they are urgent). Report MEDIUM+LOW
findings in your output — do NOT fix them here. The dedicated Step 5 Batch Fix agent
will fix all MEDIUM findings in a single coordinated pass.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED]
high_count: [number]
medium_count: [number]
low_count: [number]
inline_fixes: [number of HIGH issues fixed directly]
findings: [detailed markdown list — severity, file, line, description, for each finding]
notes: [1-3 sentence summary]
---END---
```

### 4b: Edge Case Hunter

```
You are an exhaustive edge case analyst. Walk every branching path, guard clause, null check,
overflow boundary, type coercion edge, and concurrency window.

CRITICAL INSTRUCTIONS:
1. Read the edge-case-hunter task: {project-root}/_bmad/core/tasks/review-edge-case-hunter.xml
2. Follow its instructions exactly.

CONTENT TO REVIEW:
{{story_diff}}

CONTEXT:
- Story ID: {{story_id}}, Story Name: {{story_name}}
- Story file: {{story_file}}

SCOPE: Diff review only — paths reachable from changed lines that lack explicit guards.

AUTONOMOUS: YOLO mode. Return findings, do not fix.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED]
findings_count: [number]
findings: [JSON array from edge-case-hunter task output, or markdown list if JSON not available]
notes: [1-3 sentence summary]
---END---
```

### 4c: Test Quality Review

```
You are a test quality reviewer assessing whether tests are meaningful or just green.

CRITICAL INSTRUCTIONS:
1. Read the test-review skill: {project-root}/.claude/skills/bmad-testarch-test-review/SKILL.md
2. Follow the workflow instructions exactly.

CONTEXT:
- Story ID: {{story_id}}, Story Name: {{story_name}}
- Story file: {{story_file}}

ALSO RUN TRACEABILITY:
After the test quality review, map tests to acceptance criteria from the story file.
For each AC, verify at least one test covers it.

AUTONOMOUS: YOLO mode. Apply trivial test improvements directly.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED]
quality_score: [0-100]
acs_total: [number of acceptance criteria]
acs_covered: [number with test coverage]
coverage_gaps: [list of uncovered ACs, or "none"]
strengths: [comma-separated]
weaknesses: [comma-separated]
inline_fixes: [number of improvements applied]
findings: [any quality issues as markdown list]
notes: [1-3 sentence summary]
---END---
```

### Collect Results

<action>Wait for all 3 sub-agents to complete. Parse each ---RESULTS--- block.</action>

<action>Merge all findings into `{{unified_findings}}` — a single markdown list with source attribution:
```
## Unified Review Findings

### From Adversarial Review (4a)
{{4a_findings}}

### From Edge Case Hunter (4b)
{{4b_findings}}

### From Test Quality Review (4c)
{{4c_findings}}
```
</action>

<action>Count totals: `{{total_high}}`, `{{total_medium}}`, `{{total_low}}`, `{{total_inline_fixes}}`.</action>

<action>**Orchestrator mandatory-rule cross-check (do NOT delegate to sub-agents):**

Scan ALL LOW findings from all 3 reviewers. For each LOW finding, check if it violates any
mandatory rule from CLAUDE.md (the orchestrator should have read CLAUDE.md during On Activation
and retained the mandatory rules). If a LOW finding matches a mandatory rule -> **upgrade it
to MEDIUM** in the unified findings and increment `{{total_medium}}`. Log: "Upgraded LOW->MEDIUM:
{{finding description}} (matches mandatory rule: {{rule}})."

A missing design token is NOT an excuse to keep hardcoded values at LOW — the token
must be created. "Consistent with existing patterns" is NOT a downgrade when the
existing pattern itself violates a mandatory rule.</action>

<action>Log: "**Step 4 complete.** 3 reviewers finished. Findings: {{total_high}} HIGH, {{total_medium}} MEDIUM, {{total_low}} LOW. {{total_inline_fixes}} inline fixes already applied."</action>

<check if="total_high == 0 AND total_medium == 0">
  <action>Log: "No HIGH or MEDIUM findings. Skipping Step 5 (Batch Fix)."</action>
  <action>Proceed to Step 5b.</action>
</check>

---

## Step 5: Batch Fix

**Goal:** Fix ALL HIGH and MEDIUM findings from Step 4 in a single pass. Loop up to 3 times.

<action>Initialize `batch_fix_loops = 0`, `max_batch_fix_loops = 3`.</action>

### Step 5 — Fix Pass

<action>Spawn a `general-purpose` fix sub-agent:</action>

```
Fix ALL HIGH and MEDIUM severity findings from the parallel review of Story {{story_id}}.

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{architecture_doc}} for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

FINDINGS TO FIX:
{{unified_findings}}

RULES:
1. Fix every HIGH and MEDIUM finding. Document LOW findings but do not fix.
2. For each edge case finding: implement the guard AND write a unit test for the boundary.
3. For missing test coverage gaps: write tests covering the uncovered acceptance criteria.
4. Read CLAUDE.md for all project-specific rules (design tokens, i18n, component patterns, etc.).
5. After all fixes, run tests and type check to confirm nothing broken.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED]
fixes_applied: [number]
tests_added: [number]
tests_passing: [total]
tests_failing: [total]
tsc_clean: [yes|no]
remaining_high: [number of HIGH still unfixed]
remaining_medium: [number of MEDIUM still unfixed]
files_modified: [comma-separated]
notes: [1-2 sentence summary]
---END---
```

<action>Parse results.</action>

<check if="remaining_high == 0 AND remaining_medium == 0 AND tests_failing == 0 AND tsc_clean == 'yes'">
  <action>Log: "**Step 5 complete.** {{fixes_applied}} fixes, {{tests_added}} tests added. All green."</action>
  <action>Proceed to Step 5b.</action>
</check>

<check if="(remaining_high > 0 OR remaining_medium > 0 OR tests_failing > 0) AND batch_fix_loops < max_batch_fix_loops">
  <action>Increment batch_fix_loops.</action>
  <action>Log: "**Step 5 loop-back {{batch_fix_loops}}/{{max_batch_fix_loops}}** — {{remaining_high}} HIGH, {{remaining_medium}} MEDIUM remain."</action>

  <action>Spawn targeted verification sub-agent to confirm what was fixed, identify what remains, then fix remaining issues.</action>

  <goto step="Step 5 — Fix Pass"/>
</check>

<check if="remaining issues AND batch_fix_loops >= max_batch_fix_loops">
  <action>**HALT:** "Step 5 (Batch Fix) exhausted {{max_batch_fix_loops}} loops. {{remaining_high}} HIGH, {{remaining_medium}} MEDIUM remain."</action>
</check>

---

## Step 5b: Second-Opinion Review

**Goal:** Independent second-opinion code review using a configurable external model. Runs after Step 5 so the reviewer sees the code that will actually ship. Report-only — no fixes.

<check if="second_opinion_available == false AND second_opinion_required == true">
  <action>**HALT:** "Step 5b: Second-opinion review unavailable — no API key found. Second-opinion review is mandatory per config."</action>
</check>
<check if="second_opinion_available == false AND second_opinion_required == false">
  <action>Log: "Step 5b: Second-opinion review skipped (provider unavailable, not required)."</action>
  <action>Proceed to Step 6.</action>
</check>

<action>**Generate the post-fix diff.**

`git diff {{pre_story_sha}} HEAD -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.css'`. Store as `{{story_diff_postfix}}`.
If empty -> skip to Step 6.</action>

<action>**Collect implementation file paths.**

Before launching the second-opinion review, the orchestrator builds two lists from the working tree:
1. `{{impl_files}}` — all source files changed since `{{pre_story_sha}}`: `git diff --name-only {{pre_story_sha}} HEAD -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.css' '*.mjs'`
2. `{{test_files}}` — subset of `{{impl_files}}` matching `*.test.*` or `*.spec.*`
</action>

<action>**Launch second-opinion review child process.**

**IMPORTANT:** Use `--output-format json` and `--allowedTools` to restrict the tool set to read-only operations. This prevents wasted turns on permission-denied edit attempts.

```bash
ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic" \
ANTHROPIC_API_KEY="${second_opinion_api_key}" \
claude --model "{{second_opinion_model}}" \
  -p "[prompt below]" \
  --output-format json \
  --allowedTools "Read,Grep,Glob,Bash(git diff:*),Bash(git log:*)" \
  --max-turns 30 > /tmp/second-opinion-5b-review.json 2>&1
```

Prompt:

```
You are a code reviewer. Review the working tree changes for Story {{story_id}} ({{story_name}}) in {{project_root}}.

IMPORTANT RULES:
- DO NOT edit any files. DO NOT fix any code. REPORT ONLY.
- DO NOT run tests. DO NOT execute any build or test commands.
- ONLY use Read, Grep, and Glob tools to examine source code.

STEPS:
1. Read {{project_root}}/CLAUDE.md for project rules
2. Read {{story_file}} for story context and acceptance criteria
3. Read these reference docs:
   - {{architecture_doc}}
   - {{project_root}}/_bmad/core/tasks/review-adversarial-general.xml (adversarial review guidance)
   - {{project_root}}/_bmad/core/tasks/review-edge-case-hunter.xml (edge case review guidance)
4. Read implementation files:
   {{impl_files — one per line, full paths}}
5. Read test files:
   {{test_files — one per line, full paths}}

REVIEW FOCUS:
A) ADVERSARIAL: Architecture compliance, security, hardcoded values, missing tokens, raw errors in UI
B) EDGE CASES: Regex gaps, CSS variable fallbacks, hydration issues, guard clauses, null checks, type coercion
C) TEST QUALITY: Are tests meaningful? Do they cover all acceptance criteria from the story file?

SEVERITY CLASSIFICATION:
- HIGH: Broken functionality, security hole, data loss
- MEDIUM: Architecture violations, accessibility gaps, missing validation, violations of mandatory rules from CLAUDE.md
- LOW: Style, refactoring suggestions

MANDATORY RULE ENFORCEMENT:
Read {project-root}/CLAUDE.md for project-specific mandatory rules. Any finding that violates
a mandatory rule from CLAUDE.md MUST be classified as MEDIUM or higher, regardless of how
minor it appears. Common mandatory-rule categories include: design token discipline, i18n
wrapping, accessibility attributes, directional CSS, touch targets — but defer to whatever
CLAUDE.md actually specifies for this project.

ANTI-DOWNGRADE CHECK:
For EVERY finding classified as LOW, verify it does not violate any mandatory rule from
CLAUDE.md. If it does, upgrade to MEDIUM.

YOUR FINAL OUTPUT must be EXACTLY this format (nothing after ---END---):

---RESULTS---
status: [PASSED|FAILED]

adversarial_high: [number]
adversarial_medium: [number]
adversarial_low: [number]
adversarial_findings: [markdown list — severity, file, line, description]

edge_case_findings_count: [number]
edge_case_findings: [markdown list or JSON array]

test_quality_score: [0-100]
test_acs_total: [number]
test_acs_covered: [number]
test_coverage_gaps: [list or "none"]
test_strengths: [comma-separated]
test_weaknesses: [comma-separated]
test_findings: [markdown list]

second_opinion_high: [total HIGH across all reviewers]
second_opinion_medium: [total MEDIUM across all reviewers]
second_opinion_low: [total LOW across all reviewers]
unified_findings: [merged markdown — all findings from all 3 reviewers with source attribution]
notes: [1-3 sentence summary]
---END---
```
</action>

### Collect Second-Opinion Results

<action>Wait for child process to complete.</action>

<action>Parse the JSON output file (`/tmp/second-opinion-5b-review.json`). Extract the `result` field.
If `result` is empty or the file is missing -> mark as failed.</action>

<action>Parse `---RESULTS---` block from the result text. If not found -> mark as failed.</action>

<action>**Retry on failure** (up to 3 total attempts):
- Re-spawn the child process with the same prompt
- If still failing after 3 attempts -> **HALT:** "Step 5b: Second-opinion review child failed after 3 attempts. Second-opinion review is mandatory."
</action>

<action>Extract per-reviewer findings from the structured output into individual variables for the quality report:
- `{{5ba_findings}}` <- `adversarial_findings`
- `{{5ba_high}}` / `{{5ba_medium}}` / `{{5ba_low}}` <- `adversarial_high` / `adversarial_medium` / `adversarial_low`
- `{{5bb_findings}}` <- `edge_case_findings`
- `{{5bb_findings_count}}` <- `edge_case_findings_count`
- `{{5bc_findings}}` <- `test_findings`
- `{{5bc_quality_score}}` <- `test_quality_score`
- `{{second_opinion_high}}` / `{{second_opinion_medium}}` / `{{second_opinion_low}}` <- totals from output
</action>

<action>Merge into `{{second_opinion_unified_findings}}`:
```
## Second-Opinion Unified Review Findings

### From Second-Opinion Adversarial Review (5b-a)
{{5ba_findings}}

### From Second-Opinion Edge Case Hunter (5b-b)
{{5bb_findings}}

### From Second-Opinion Test Quality Review (5b-c)
{{5bc_findings}}
```
</action>

<action>**Orchestrator mandatory-rule cross-check (do NOT delegate — double-check the child's work):**

Scan ALL LOW findings from the second-opinion output. For each LOW finding, check if it
violates any mandatory rule from CLAUDE.md (the orchestrator should have read CLAUDE.md during
On Activation and retained the mandatory rules). If a LOW finding matches a mandatory rule ->
**upgrade it to MEDIUM** in the unified findings and increment `{{second_opinion_medium}}`.
Log: "Upgraded LOW->MEDIUM: {{finding description}} (matches mandatory rule: {{rule}})."</action>

<action>Store merged findings as `{{second_opinion_findings}}` for Step 5c.</action>

<action>Log: "**Step 5b complete.** Second-opinion 3-stage review finished. Findings: {{second_opinion_high}} HIGH, {{second_opinion_medium}} MEDIUM, {{second_opinion_low}} LOW."</action>

<check if="second_opinion_high == 0 AND second_opinion_medium == 0">
  <action>Proceed to Step 6.</action>
</check>

### Step 5c: Second-Opinion Fix

<action>Initialize `second_opinion_fix_loops = 0`, `max_second_opinion_fix_loops = 3`.</action>

<action>Spawn a `general-purpose` fix sub-agent:

```
Fix ALL HIGH and MEDIUM severity findings from the second-opinion review of Story {{story_id}}.

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{architecture_doc}} for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

FINDINGS TO FIX:
{{second_opinion_findings}}

RULES:
1. Fix every HIGH and MEDIUM finding.
2. For each finding: implement the fix AND write a test covering the fixed behaviour.
3. Read CLAUDE.md for project rules.
4. After all fixes, run tests and type check to confirm nothing broken.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED]
fixes_applied: [number]
tests_added: [number]
tests_passing: [total]
tests_failing: [total]
tsc_clean: [yes|no]
remaining_high: [number of HIGH still unfixed]
remaining_medium: [number of MEDIUM still unfixed]
notes: [1-2 sentence summary]
---END---
```
</action>

<action>Parse results.</action>

<check if="remaining_high == 0 AND remaining_medium == 0 AND tests_failing == 0 AND tsc_clean == 'yes'">
  <action>Log: "**Step 5c complete.** {{fixes_applied}} second-opinion fixes applied. All green."</action>
  <action>Proceed to Step 6.</action>
</check>

<check if="(remaining_high > 0 OR remaining_medium > 0 OR tests_failing > 0) AND second_opinion_fix_loops < max_second_opinion_fix_loops">
  <action>Increment second_opinion_fix_loops.</action>
  <action>Log: "**Step 5c loop-back {{second_opinion_fix_loops}}/{{max_second_opinion_fix_loops}}** — {{remaining_high}} HIGH, {{remaining_medium}} MEDIUM remain."</action>
  <goto step="Step 5c: Second-Opinion Fix"/>
</check>

<check if="remaining issues AND second_opinion_fix_loops >= max_second_opinion_fix_loops">
  <action>**HALT:** "Step 5c (Second-Opinion Fix) exhausted {{max_second_opinion_fix_loops}} loops. {{remaining_high}} HIGH, {{remaining_medium}} MEDIUM remain."</action>
</check>

---

## Step 6: Complementary Review

**Goal:** Business logic and functional review that code reviewers miss. Runs AFTER fixes so code is stable.

<action>Spawn a `general-purpose` Claude Code Task sub-agent:</action>

```
You are running a business/functional review — complementary to the code reviews already done.

The following issues were ALREADY identified and fixed — do NOT re-report:
{{unified_findings}}

Focus EXCLUSIVELY on:
1. BUSINESS LOGIC — Does the implementation solve the business problem?
2. AC VERIFICATION — For each acceptance criterion, can a user achieve the stated outcome?
3. INTEGRATION — How does this interact with existing features? Data flow issues?
4. MISSING IMPLIED REQUIREMENTS — What did the story NOT say that a user would expect?

Do NOT review: code style, naming, architecture patterns, performance micro-opts, test quality.

CONTEXT:
- Story ID: {{story_id}}, Story Name: {{story_name}}
- Story file: {{story_file}}

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{architecture_doc}} for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

INSTRUCTIONS:
1. Read the story file — focus on acceptance criteria and user intent.
2. Read the implementation code to understand behaviour.
3. Walk through each AC as a user.
4. Produce findings. HIGH = breaks user expectations. MEDIUM = degrades experience. LOW = minor gap.

AUTONOMOUS: YOLO mode. Return findings, do not fix.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|PASSED_WITH_CONCERNS|FAILED]
high_count: [number]
medium_count: [number]
low_count: [number]
findings: [detailed list]
notes: [1-3 sentence summary]
---END---
```

<action>Parse results. Store as `{{step6_findings}}`.</action>

<check if="high_count == 0 AND medium_count == 0">
  <action>Log: "**Step 6 complete.** Business review clean."</action>
  <action>Proceed to Step 7.</action>
</check>

### Step 6b: Fix Business Logic Findings

<action>Initialize `step6_fix_loops = 0`, `max_step6_fix_loops = 3`.</action>

<action>Spawn a `general-purpose` fix sub-agent:

```
Fix ALL HIGH and MEDIUM severity findings from the business logic review of Story {{story_id}}.

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{architecture_doc}} for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

FINDINGS TO FIX:
{{step6_findings}}

RULES:
1. Fix every HIGH and MEDIUM finding.
2. These are business logic issues, not code style — focus on correctness and user experience.
3. Write tests covering the fixed behaviour where applicable.
4. Read CLAUDE.md for project rules.
5. After all fixes, run tests and type check to confirm nothing broken.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED]
fixes_applied: [number]
tests_added: [number]
tests_passing: [total]
tests_failing: [total]
tsc_clean: [yes|no]
remaining_high: [number of HIGH still unfixed]
remaining_medium: [number of MEDIUM still unfixed]
notes: [1-2 sentence summary]
---END---
```
</action>

<action>Parse results.</action>

<check if="remaining_high == 0 AND remaining_medium == 0 AND tests_failing == 0 AND tsc_clean == 'yes'">
  <action>Log: "**Step 6b complete.** {{fixes_applied}} business logic fixes applied. All green."</action>
  <action>Proceed to Step 7.</action>
</check>

<check if="(remaining_high > 0 OR remaining_medium > 0 OR tests_failing > 0) AND step6_fix_loops < max_step6_fix_loops">
  <action>Increment step6_fix_loops.</action>
  <action>Log: "**Step 6b loop-back {{step6_fix_loops}}/{{max_step6_fix_loops}}** — {{remaining_high}} HIGH, {{remaining_medium}} MEDIUM remain."</action>
  <goto step="Step 6b: Fix Business Logic Findings"/>
</check>

<check if="remaining issues AND step6_fix_loops >= max_step6_fix_loops">
  <action>**HALT:** "Step 6b (Business Logic Fix) exhausted {{max_step6_fix_loops}} loops. {{remaining_high}} HIGH, {{remaining_medium}} MEDIUM remain."</action>
</check>

---

## Step 7: Documentation

**Goal:** Generate/update API docs and docs-site pages. Runs before commit so docs are included.

<check if="docs_mode from customize.toml == 'skip'">
  <action>Log: "Step 7: Documentation skipped per config."</action>
  <action>Proceed to Step 8.</action>
</check>

<check if="story file contains 'docs_update: none' (grep case-insensitive in story spec)">
  <action>Log: "**Step 7: Story marked `docs_update: none`. Skipping docs-site update.**"</action>
  <action>Proceed to Step 8 (commit).</action>
</check>

<action>Spawn a `general-purpose` documentation sub-agent:</action>

```
You are a Technical Writer creating API documentation for Story {{story_id}}: {{story_name}}.

CRITICAL INSTRUCTIONS:
1. Read the tech writer skill: {project-root}/.claude/skills/bmad-agent-tech-writer/SKILL.md
2. Follow the write-document workflow if available, otherwise use the SKILL.md guidance.
3. Skip the "Discover intent" step — all context is provided below.

CONTENT TO DOCUMENT:
Story {{story_id}}: {{story_name}}

CONTEXT:
- Story file: {{story_file}}
- Docs site directory: {project-root}/{{docs_site_content_path}}/

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{architecture_doc}} for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

SCOPE (replaces discovery step):
- Audience: Developers working on this project
- Purpose: API reference documentation for story deliverables
- Read the story file — identify all files created/modified
- Read EVERY source file to extract TypeScript signatures
- Read existing .mdx files in {{docs_site_content_path}}/ to match style

CREATE/UPDATE .mdx pages with:
- Architecture overview
- Full API Reference: props tables (Type, Default, Description), return values, usage examples
- Constants tables, Key Files table
- Update navigation entries for new pages

AUTONOMOUS: YOLO mode. No interactive discovery — all scope provided above.

VERIFICATION: Re-read each file you wrote to confirm it saved. Count API entries documented.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|FAILED]
pages_created: [comma-separated .mdx paths, or "none"]
pages_updated: [comma-separated .mdx paths, or "none"]
api_entries: [number documented]
notes: [1-3 sentence summary]
---END---
```

<action>Parse results. If no pages created/updated -> log WARNING.</action>

### 7b: Documentation Validation

<check if="no pages were created or updated in Step 7">
  <action>Skip validation — nothing to validate.</action>
</check>

<action>Spawn a `general-purpose` validation sub-agent:</action>

```
You are a documentation quality reviewer validating API docs for Story {{story_id}}: {{story_name}}.

DOCUMENTS TO VALIDATE:
{{pages_created_and_updated}}

FOCUS AREAS:
- API completeness: every exported function/component/hook from story source files has a docs entry
- Props table accuracy: types match actual TypeScript signatures
- Navigation entries exist for all new pages
- Style consistency: matches existing .mdx pages in {{docs_site_content_path}}/
- Code examples: at least one usage example per documented API

CONTEXT:
- Story file: {{story_file}} (source of truth for what was implemented)
- Docs site directory: {project-root}/{{docs_site_content_path}}/

AUTONOMOUS: YOLO mode. Apply trivial fixes directly (typos, formatting, missing table columns).
Report substantive issues (missing APIs, incorrect signatures, structural problems) as findings.

REQUIRED OUTPUT FORMAT:
---RESULTS---
status: [PASSED|PASSED_WITH_CONCERNS|FAILED]
inline_fixes: [number of trivial fixes applied]
findings_count: [number of substantive issues]
findings: [markdown list — severity, file, description, for each finding]
notes: [1-3 sentence summary]
---END---
```

<action>Parse results. If FAILED -> spawn fix sub-agent to address findings (up to 2 loops).</action>
<action>If PASSED or PASSED_WITH_CONCERNS -> proceed.</action>

**Docs generation command** (orchestrator):

<check if="docs_generate_command from customize.toml is set and non-empty">
  <action>Run `{{docs_generate_command}}` to regenerate docs pages.</action>
  <action>Verify generated output exists.</action>
</check>

<check if="docs_generate_command from customize.toml is blank or not set">
  <action>Skip docs generation command — not configured.</action>
</check>

<action>Log: "**Step 7 complete.** Documentation generated."</action>

---

## Step 8: Commit & Push

**Goal:** Stage all changes, commit with proper message, push to remote.

<action>Run `git status` to identify all changes.</action>

<action>Stage specific files (avoid `git add -A`):
- App/package code: stage modified source directories
- Story file: `git add {{story_file}}`
- Sprint status: `git add {{sprint_status_file}}`
- Docs site: stage docs directory if docs were generated
- Quality reports: `git add {{quality_report_location}}/`
</action>

<action>Commit:
```
git commit -m "feat: implement Story {{story_id}} {{story_name}}

Co-Authored-By: Claude <noreply@anthropic.com>"
```
Use `fix:` or `docs:` prefix if more appropriate.</action>

<action>Push: `git push`.</action>

<action>Log: "**Step 8 complete.** Committed and pushed."</action>

---

## Step 9: CI Verification

**Goal:** Poll CI, fix failures if needed. Max 3 loop-backs.

<action>Initialize `ci_loops = 0`, `max_ci_loops = 3`.</action>

### Step 9 — Poll

<action>Get latest CI run: `gh run list --branch main --limit 1 --json databaseId,status,conclusion,createdAt`.</action>

<action>If in_progress or queued -> poll every 30s until complete (max 10 min).</action>

<check if="conclusion == 'success'">
  <action>Log: "**Step 9 passed.** CI green."</action>
  <action>Proceed to Step 10.</action>
</check>

<check if="conclusion == 'failure' AND ci_loops < max_ci_loops">
  <action>Increment ci_loops.</action>
  <action>Log: "**Step 9 loop-back {{ci_loops}}/{{max_ci_loops}}** — reading failure logs."</action>

  <action>Read logs: `gh run view {{run_id}} --log-failed`.</action>

  <action>Spawn fix sub-agent with failure details. After fix, commit, push, re-poll.</action>

  <goto step="Step 9 — Poll"/>
</check>

<check if="conclusion == 'failure' AND ci_loops >= max_ci_loops">
  <action>**HALT:** "Step 9 (CI Verification) failed after {{max_ci_loops}} loops."</action>
</check>

---

## Step 10: Pre-Report Verification

**Goal:** Confirm story is in expected state before generating quality report.

<action>Read {{sprint_status_file}}. Find entry for {{story_id}}. Confirm status is "review" or "in-progress". If already "done", log warning.</action>

<action>Log: "**Step 10 complete.** Proceeding to quality report."</action>

---

## Step 11: Quality Report

**Goal:** Generate consolidated quality report with the canonical `**Overall Gate Status:**` line.

<action>Compute:
- `overall_gate_status`: PASSED (all clean), PASSED_WITH_CONCERNS (LOW findings remain), HALTED (shouldn't reach here)
- `total_loopbacks` = sum of all loop counters (local_verify_loops + batch_fix_loops + second_opinion_fix_loops + step6_fix_loops + ci_loops)
- `total_inline_fixes` = accumulated inline fixes from all steps
</action>

<action>Write report to `{{quality_report_location}}/story-{{story_id}}-quality-report.md`:

```markdown
# Quality Gate Report — Story {{story_id}}: {{story_name}}

**Date:** {{date}}
**LLM:** {{session_model}} + {{second_opinion_model}}
**Story:** {{story_id}} {{story_name}}
**Status:** {{overall_gate_status}}
**Overall Gate Status:** {{overall_gate_status}}
**Total Loop-backs:** {{total_loopbacks}}
**Total Inline Fixes:** {{total_inline_fixes}}

## Summary

| Step | Name | Status | Loops | Inline Fixes |
|------|------|--------|-------|-------------|
| 1 | Create Story | {{step1_status}} | 0 | — |
| 2 | Implement | {{step2_status}} | 0 | — |
| 3 | Local Verification | {{step3_status}} | {{local_verify_loops}} | — |
| 4a | Adversarial Review | {{4a_status}} | — | {{4a_inline}} |
| 4b | Edge Case Hunter | {{4b_status}} | — | {{4b_inline}} |
| 4c | Test Quality | {{4c_status}} | — | {{4c_inline}} |
| 5 | Batch Fix | {{step5_status}} | {{batch_fix_loops}} | {{step5_fixes}} |
| 5b-a | Second-Opinion Adversarial | {{5ba_status}} | — | 0 |
| 5b-b | Second-Opinion Edge Case | {{5bb_status}} | — | 0 |
| 5b-c | Second-Opinion Test Quality | {{5bc_status}} | — | 0 |
| 5c | Second-Opinion Fix | {{step5c_status}} | {{second_opinion_fix_loops}} | {{step5c_fixes}} |
| 6 | Complementary Review | {{step6_status}} | — | — |
| 6b | Business Logic Fix | {{step6b_status}} | {{step6_fix_loops}} | {{step6b_fixes}} |
| 7 | Documentation | {{step7_status}} | — | — |
| 8 | Commit & Push | {{step8_status}} | — | — |
| 9 | CI Verification | {{step9_status}} | {{ci_loops}} | — |
| 10 | Pre-Report Verify | {{step10_status}} | — | — |
| 11 | Quality Report + Done | {{overall_gate_status}} | — | — |

## Adversarial Code Review (Step 4a)

{{4a_findings}}

## Edge Case Analysis (Step 4b)

{{4b_findings}}

## Test Quality Review (Step 4c)

{{4c_findings}}

## Batch Fix Summary (Step 5)

{{step5_summary — fixes applied, tests added, what was resolved}}

## Second-Opinion Adversarial Review (Step 5b-a)

{{5ba_findings}}

## Second-Opinion Edge Case Analysis (Step 5b-b)

{{5bb_findings}}

## Second-Opinion Test Quality Review (Step 5b-c)

{{5bc_findings}}

## Second-Opinion Fix Summary (Step 5c)

{{step5c_summary — fixes applied, or "SKIPPED — no second-opinion findings required fixing"}}

## Complementary Review Findings

{{step6_findings}}

## Lessons & Observations

{{observations about loop-backs, recurring issues, recommendations}}
```
</action>

<action>**Uniqueness constraint:** `**Overall Gate Status:**` must appear exactly once in the file.</action>

<action>Commit: `git add {{quality_report_location}}/story-{{story_id}}-quality-report.md && git commit -m "docs: Story {{story_id}} quality report [skip ci]"`, push.</action>

**Self-verify** (orchestrator):

<action>Re-read the report. Verify:
1. `grep -c '^\*\*Overall Gate Status:\*\*' <path>` returns 1
2. No `_Pending_` or `IN-PROGRESS` in header
3. No `pending` in summary table

If any check fails -> fix inline, re-commit, re-verify once. If still fails -> HALT.</action>

<action>Log: "**Step 11 report complete.** Report: {{quality_report_location}}/story-{{story_id}}-quality-report.md"</action>

### Step 11b: Mark Story Done

<action>**Only mark "done" if quality gate passed.** Read `{{overall_gate_status}}` computed above.</action>

<check if="overall_gate_status == 'PASSED' OR overall_gate_status == 'PASSED_WITH_CONCERNS'">
  <action>Read {{sprint_status_file}}. Find entry for {{story_id}}. Update status to "done".</action>
  <action>Read the story file at {{story_file}}. Update the `Status:` field from its current value to `Status: done`. Replace every unchecked task checkbox (`- [ ]`) with `- [x]`. Save the file.</action>
  <action>Commit: `git add {{sprint_status_file}} {{story_file}} && git commit -m "docs: mark Story {{story_id}} done in sprint-status and story file"`, push.</action>
  <action>Log: "**Step 11 complete.** Story {{story_id}} marked done in both sprint-status and story file."</action>
</check>

<check if="overall_gate_status != 'PASSED' AND overall_gate_status != 'PASSED_WITH_CONCERNS'">
  <action>Log: "**Step 11 complete.** Quality gate status is {{overall_gate_status}} — story remains at 'review' status, NOT marked done."</action>
</check>

---

## Step 12: Pipeline Summary

<action>Present:

```
**Pipeline Complete — Story {{story_id}}: {{story_name}}**

| Step | Status |
|------|--------|
| 1. Create Story | {{step1_status}} |
| 2. Implement | {{step2_status}} |
| 3. Local Verify | {{step3_status}} ({{local_verify_loops}} loops) |
| 4. Parallel Review | {{total_high}} HIGH, {{total_medium}} MEDIUM, {{total_low}} LOW |
| 5. Batch Fix | {{step5_status}} ({{batch_fix_loops}} loops, {{step5_fixes}} fixes) |
| 5b. Second-Opinion Review (3-stage) | {{step5b_status}} ({{second_opinion_high}} HIGH, {{second_opinion_medium}} MEDIUM, {{second_opinion_low}} LOW) |
| 5c. Second-Opinion Fix | {{step5c_status}} ({{second_opinion_fix_loops}} loops) |
| 6. Complementary Review | {{step6_status}} |
| 6b. Business Logic Fix | {{step6b_status}} ({{step6_fix_loops}} loops) |
| 7. Documentation | {{step7_status}} |
| 8. Commit & Push | {{step8_status}} |
| 9. CI Verification | {{step9_status}} ({{ci_loops}} loops) |
| 10. Pre-Report Verify | {{step10_status}} |
| 11. Quality Report + Mark Done | {{overall_gate_status}} |

**Overall: {{overall_gate_status}}**
Quality Report: {{quality_report_location}}/story-{{story_id}}-quality-report.md
```
</action>

<action>Check sprint-status for remaining stories. Suggest next action.</action>
