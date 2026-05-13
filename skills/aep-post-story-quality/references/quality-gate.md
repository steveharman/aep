# Post-Story Quality Gate (Autonomous) — Instructions

> **Mode:** This workflow runs autonomously using Claude Code Task subagents.
> Each subagent gets a fresh context window (mimicking the manual version's recommendation).
> The orchestrator evaluates results, handles loop-backs (max {{max_loopbacks_per_step}} per step), and produces the quality report.
> **HALT rule:** If any step with loop-back logic still fails after {{max_loopbacks_per_step}} loop-backs, the workflow HALTs entirely — it does NOT skip to the next step.
> **Targeted verification:** On loop-back, steps run a lightweight verification subagent (not a full re-run) that checks specific fixes and scans for regressions.

---

## Project Context (loaded during On Activation)

The orchestrator and every spawned sub-agent operate using project context discovered during
SKILL.md On Activation. The following variables are resolved from config:

- `{{sprint_status_file}}` — sprint status YAML
- `{{story_location}}` — story spec files directory
- `{{quality_report_location}}` — quality report output directory
- `{{planning_artifacts}}` — planning documents root
- `{{implementation_artifacts}}` — implementation documents root

Project-specific rules, toolchain, test commands, and conventions are captured in
`{{project_context}}` (built by reading CLAUDE.md and architecture.md during On Activation).
Sub-agent prompts inject this context block rather than hardcoding project details.

---

## Pre-Flight: Verify Dependencies

<action>**Check required files.** Verify each exists. Collect any missing into `{{missing_deps}}`:

| File | Required by |
|------|------------|
| `{project-root}/_bmad/core/tasks/review-adversarial-general.xml` | Step 1 (code review) |
| `{project-root}/_bmad/core/tasks/review-edge-case-hunter.xml` | Step 1b (edge-case analysis) |
| `{project-root}/_bmad/core/tasks/workflow.xml` | Steps 4a, 4b (workflow engine) |
| `{project-root}/.claude/skills/bmad-qa-generate-e2e-tests/SKILL.md` | Step 2 (QA automation) |
| `{project-root}/.claude/skills/bmad-testarch-test-review/SKILL.md` | Step 4a (test review) |
| `{project-root}/.claude/skills/bmad-testarch-trace/SKILL.md` | Step 4b (traceability) |
| `{project-root}/CLAUDE.md` | All steps (project context) |
| `{{sprint_status_file}}` | Story discovery and status |
</action>

<check if="missing_deps is not empty">
  <action>**HALT:**

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

<action>**Check docs-site prerequisites** (only when `docs_mode` from customize.toml is not `"skip"` AND `docs_site_content_path` is configured and non-empty).

1. Verify `{project-root}/{{docs_site_content_path}}/` exists on disk. If missing -> **HALT:** "Docs site content path '{{docs_site_content_path}}' does not exist. Either create the directory, update `docs_site_content_path` in customize.toml, or set `docs_mode = \"skip\"` to disable documentation."
2. Check for Nextra installation: look for `nextra` in the nearest `package.json` to `{{docs_site_content_path}}` (e.g. `apps/docs-site/package.json`). If not found -> **HALT:** "AEP's documentation step requires Nextra (https://nextra.site). No `nextra` dependency found near '{{docs_site_content_path}}'. Either install Nextra or set `docs_mode = \"skip\"` in customize.toml."

If `docs_site_content_path` is blank or `docs_mode` is `"skip"`, skip this check entirely.
</action>

---

## Step 0: Identify Story

<check if="story_id is already set (non-empty)">
  **Fast path — skip discovery.** Derive variables directly:
  <action>Set `epic_num` from the story_id prefix (e.g. "2-7" -> epic_num = "2").</action>
  <action>Glob for the story file: `{{story_location}}/story-{{story_id}}*.md`. Read its title line to set `story_name`.</action>
  <action>Load `{{sprint_status_file}}` for context.</action>
</check>

<check if="story_id is NOT set (empty)">
  <action>Ask the user which story was just completed.</action>
  <action>Set `story_id` from their answer. Derive `epic_num` from the prefix.</action>
  <action>Glob for the story file and read its title line to set `story_name`.</action>
  <action>Load `{{sprint_status_file}}` for context.</action>
</check>

<action>Determine the relevant app/package(s) for this story by reading the story file's Tasks
and File List. The story file indicates which parts of the codebase are affected.
Store as `{{story_scope}}` (may be a comma-separated list when the story spans multiple packages).</action>

<action>Create the output file from the template, resolving the story_id in the filename. Output path: `{{quality_report_location}}/story-{{story_id}}-quality-report.md`.</action>

<action>Rewrite the output file section headers to match the optimized step structure:
- Step 1: Code Review (unchanged)
- Step 1b: Edge Case Analysis (NEW — exhaustive path/boundary tracing with fix loop-back)
- Step 2: QA Automation Test (unchanged)
- Step 3: rename from "Adversarial Review" to "Complementary Review"; change Command to "Custom Prompt (business/functional focus)"; remove Agent line
- Steps 4+5: merge into "Step 4: Test Quality & Traceability" with sub-sections "### 4a: Test Review (TEA)" and "### 4b: Traceability Check (TEA)"; add Loop-backs lines for both 4a and 4b
- Old Step 6 -> "Step 5: Documentation" (renumber)
- Old Steps 7+8 -> "Step 6: CI Verification & Sprint Status" (merge; add Sprint Status fields: Story Marked Done, Sprint Progress)
- Add "Step 7: Finalize Report" (just a header, content is the Summary section)
- Update the Summary table to: Steps 1, 1b, 2-6 plus sub-rows for 4a/4b, and a Step 7 row for Finalize
</action>

<action>Log to user: "Starting Autonomous Post-Story Quality Gate for **Story {{story_id}}: {{story_name}}** (scope: {{story_scope}}). All 7 steps will run automatically with subagents."</action>

<action>Initialize loop-back counters: step_1_loops=0, step_1b_loops=0, step_2_loops=0, step_3_loops=0, step_4a_loops=0, step_4b_loops=0, step_6_loops=0.</action>
<action>Initialize inline fix counter: total_inline_fixes=0.</action>
<action>Initialize findings accumulators: step_1_findings="", step_1b_findings="".</action>
<action>Enter YOLO mode for the remainder of the workflow — all template-output saves proceed without user confirmation.</action>

---

## Step 1: Code Review

**Goal:** Adversarial code review that challenges quality, architecture compliance, security, performance, and project-specific conventions. Run this first so the code is stable before generating additional tests.

<check if="step_1_loops == 0">
  <action>Spawn a `general-purpose` Claude Code Task subagent with the following prompt:</action>

```
You are running an autonomous code review as part of a quality gate.

CRITICAL INSTRUCTIONS:
1. Read the adversarial review task: {project-root}/_bmad/core/tasks/review-adversarial-general.xml
2. Follow its instructions exactly.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{planning_artifacts}}/architecture.md for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

ALSO CONSIDER (passed to task's also_consider input):
Focus areas beyond general adversarial analysis:
- Architecture compliance (tokens, patterns from ref docs)
- Security: auth checks, multi-tenancy scoping, input validation
- Performance: unbounded queries, N+1 patterns
- Error handling: raw errors in UI, missing fallbacks
- Project-specific mandatory rules from CLAUDE.md (design system discipline,
  i18n requirements, accessibility standards, CSS conventions, security posture —
  defer to whatever CLAUDE.md actually specifies for this project)

SEVERITY CLASSIFICATION:
- HIGH: Broken functionality, security hole, data loss
- MEDIUM: Architecture violations, accessibility gaps, missing validation, violations of mandatory rules from CLAUDE.md
- LOW: Style, refactoring, nice-to-haves

MANDATORY RULE ENFORCEMENT:
Read {project-root}/CLAUDE.md for project-specific mandatory rules. Any finding that violates
a mandatory rule from CLAUDE.md MUST be classified as MEDIUM or higher, regardless of how
minor it appears.

AUTONOMOUS: YOLO mode. Fix HIGH issues directly (they are urgent). Report MEDIUM+LOW
findings in your output — do NOT fix them here. The dedicated loop-back fix agent
will fix all MEDIUM findings in a single coordinated pass.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
issues_found: [number]
issues_fixed: [number]
issues_remaining: [number]
severity_high: [number]
severity_medium: [number]
severity_low: [number]
inline_fixes: [number of issues fixed within this sub-agent execution]
llm_used: Claude
loopbacks: 0
findings_summary: [detailed list of all findings with severities, one per line]
notes: [1-3 sentence summary of findings and fixes]
---END---
```
</check>

<check if="step_1_loops > 0">
  <action>Spawn a `general-purpose` TARGETED VERIFICATION subagent with the following prompt:</action>

```
You are running a TARGETED VERIFICATION of code review fixes (loop-back {{step_1_loops}}).

This is NOT a full code review. A full review already ran and found issues that were fixed.
Your job is to verify the fixes and check for regressions — nothing more.

PREVIOUS FINDINGS:
{{step_1_findings}}

INSTRUCTIONS:
1. For each previously identified issue, check if the fix was applied correctly.
2. Verify fixes don't introduce new problems (regressions).
3. Do a brief scan of changed files for any obvious new issues.
4. Do NOT re-review the entire codebase — only examine the fixes and their immediate context.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

AUTONOMOUS BEHAVIOR:
- Run in YOLO mode — skip all confirmations.
- If you find regressions or incomplete fixes, fix them directly.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
issues_found: [number of new/regression issues]
issues_fixed: [number fixed in this pass]
issues_remaining: [number still unresolved]
severity_high: [number]
severity_medium: [number]
severity_low: [number]
llm_used: Claude
inline_fixes: [number of issues fixed within this verification pass]
loopbacks: {{step_1_loops}}
findings_summary: [what was verified, what regressions found if any]
notes: [1-3 sentence summary]
---END---
```
</check>

<action>Parse the subagent's returned results from the ---RESULTS--- block.</action>
<action>Update step_1_findings accumulator with the findings_summary from the results.</action>
<action>Add inline_fixes to total_inline_fixes.</action>

<check if="issues_remaining > 0 AND step_1_loops < max_loopbacks_per_step">
  <action>Increment step_1_loops. Log: "Step 1 loop-back {{step_1_loops}}/{{max_loopbacks_per_step}} — spawning fix subagent, then targeted verification."</action>
  <action>Spawn a `general-purpose` fix subagent with prompt: "Fix the following code review issues for Story {{story_id}}: {{step_1_findings}}. Read the story file at {{story_location}}/story-{{story_id}}*.md for context. Fix all remaining issues. Run tests using the project's test runner as specified in CLAUDE.md. Run linting and type checking as specified in CLAUDE.md."</action>
  <goto step="Step 1"/>
</check>

<check if="issues_remaining > 0 AND step_1_loops >= max_loopbacks_per_step">
  <action>Mark Step 1 as FAILED in the quality report.</action>
  <template-output>Update Step 1 in the quality report with FAILED status, loop-back count, and remaining issues.</template-output>
  <action>**HALT** — Code review failed after {{max_loopbacks_per_step}} loop-backs with {{issues_remaining}} unresolved issues. Save partial report and stop workflow.</action>
  <action>Present HALT summary to user: "Quality gate HALTED at Step 1 (Code Review). {{issues_remaining}} issues remain after {{step_1_loops}} loop-backs. Partial report saved."</action>
</check>

<template-output>Update Step 1 in the quality report with the subagent's results.</template-output>

---

## Step 1b: Edge Case Analysis

**Goal:** Exhaustive path and boundary condition analysis that COMPLEMENTS Step 1's adversarial code review. Step 1 is attitude-driven (cynical skeptic); this step is method-driven (mechanical path tracer). It walks every branching path, guard clause, null check, overflow boundary, type coercion edge, and concurrency window — reporting ONLY paths that lack an explicit guard. Run after Step 1 so the code is already cleaned up, and before Step 2 so any new guards are in place before tests are generated.

<check if="step_1b_loops == 0">
  <action>Generate the diff of this story's changes for the edge-case-hunter to analyze. Run: `git diff HEAD~1 -- '*.ts' '*.tsx' '*.js' '*.jsx'` (adjust HEAD~N if the story spans multiple commits — use `git log` to determine the right range). Save the diff output as `step_1b_diff`.</action>
  <action>Spawn a `general-purpose` Claude Code Task subagent with the following prompt:</action>

```
You are running an exhaustive edge case analysis as part of a quality gate.

CRITICAL INSTRUCTIONS:
1. Read the edge-case-hunter task file at: {project-root}/_bmad/core/tasks/review-edge-case-hunter.xml
2. Follow ALL instructions in the task file EXACTLY as written.

CONTENT TO REVIEW:
Analyze the following diff of Story {{story_id}} ({{story_name}}):

{{step_1b_diff}}

ALSO CONSIDER:
- The story's acceptance criteria (read the story file at
  {{story_location}}/story-{{story_id}}*.md)
- Any guard code that was added by Step 1 (Code Review) — verify those guards are complete

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{planning_artifacts}}/architecture.md for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

PROJECT-SPECIFIC CHECKS:
Read {project-root}/CLAUDE.md for project-specific review rules. Apply all mandatory rules
found there. Common categories include: design system discipline, i18n requirements,
accessibility standards, CSS conventions, security posture — but defer to whatever CLAUDE.md
actually specifies for this project.

SCOPE RULES:
- This is a DIFF review — scan only the diff hunks and list boundaries that are directly
  reachable from the changed lines and lack an explicit guard in the diff.
- Do NOT review unchanged code outside the diff unless the diff explicitly references it.

AUTONOMOUS BEHAVIOR:
- Run in YOLO mode — skip all confirmations.
- Execute the edge-case-hunter task exactly as specified.
- Return the JSON array of findings as described in the task's output-format.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
findings_count: [number of unhandled edge cases found]
findings_json: [the complete JSON array output from the edge-case-hunter task]
notes: [1-3 sentence summary of the analysis]
---END---
```
</check>

<check if="step_1b_loops > 0">
  <action>Spawn a `general-purpose` TARGETED VERIFICATION subagent with the following prompt:</action>

```
You are running a TARGETED VERIFICATION of edge case fixes (loop-back {{step_1b_loops}}).

This is NOT a full edge case analysis. The full analysis already ran and found unhandled
boundary conditions. A fix subagent implemented guards and wrote unit tests for them.
Your job is to verify the fixes are correct and the tests pass — nothing more.

PREVIOUS FINDINGS:
{{step_1b_findings}}

INSTRUCTIONS:
1. Read the edge-case-hunter task file at: {project-root}/_bmad/core/tasks/review-edge-case-hunter.xml
2. For each previously identified edge case, check if a guard was implemented correctly.
3. Verify the unit tests for each guard exist and exercise the boundary condition.
4. Run tests using the project's test runner as specified in CLAUDE.md.
   Scope tests to the relevant app/package if the project supports scoped test runs.
5. Do a brief re-scan of ONLY the files that were modified by the fix subagent for any
   new unhandled paths introduced by the fixes themselves.
6. Do NOT re-analyze the entire diff — only examine the fixes and their immediate context.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

AUTONOMOUS BEHAVIOR:
- Run in YOLO mode — skip all confirmations.
- If you find incomplete fixes or missing tests, fix them directly.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
findings_count: [number of remaining or new unhandled edge cases]
findings_json: [JSON array of any remaining findings, or empty array []]
tests_passing: [yes|no]
inline_fixes: [number of issues fixed within this verification pass]
notes: [1-3 sentence summary]
---END---
```
</check>

<action>Parse the subagent's returned results from the ---RESULTS--- block.</action>
<action>Update step_1b_findings accumulator with the findings_json from the results.</action>
<action>Append step_1b_findings summary to step_1_findings so downstream steps (Step 3 Complementary Review) know what edge cases were already covered.</action>

<check if="step_1b_loops > 0">
  <action>Add inline_fixes to total_inline_fixes.</action>
</check>

<check if="findings_count > 0 AND step_1b_loops < max_loopbacks_per_step">
  <action>Increment step_1b_loops. Log: "Step 1b loop-back {{step_1b_loops}}/{{max_loopbacks_per_step}} — spawning fix subagent to implement guards and unit tests, then targeted verification."</action>
  <action>Spawn a `general-purpose` fix subagent with the following prompt:

"Fix unhandled edge cases for Story {{story_id}}.

The edge case analysis found the following unhandled boundary conditions:
{{step_1b_findings}}

INSTRUCTIONS:
1. Read the story file at {{story_location}}/story-{{story_id}}*.md for context.
2. For EACH finding in the JSON array:
   a. Implement the guard described in the `guard_snippet` field at the `location` specified.
   b. Write a unit test that exercises the boundary condition described in `trigger_condition`.
      The test MUST trigger the exact condition (e.g., pass null, pass empty array, pass max-length string)
      and verify the guard produces the expected behavior (e.g., throws typed error, returns empty result, clamps value).
   c. Follow existing test patterns in the relevant app/package as specified in CLAUDE.md.
3. After implementing ALL guards and tests, run tests using the project's test runner as specified
   in CLAUDE.md. Scope tests to the relevant app/package if the project supports scoped test runs.
4. If any tests fail, fix them before returning.

IMPORTANT: Every guard MUST have a corresponding test. Do not implement a guard without testing it."
  </action>
  <goto step="Step 1b"/>
</check>

<check if="findings_count > 0 AND step_1b_loops >= max_loopbacks_per_step">
  <action>Mark Step 1b as FAILED in the quality report.</action>
  <template-output>Update Step 1b in the quality report with FAILED status, loop-back count, and remaining findings.</template-output>
  <action>**HALT** — Edge case analysis failed after {{max_loopbacks_per_step}} loop-backs with {{findings_count}} unhandled edge cases remaining. Save partial report and stop workflow.</action>
  <action>Present HALT summary to user: "Quality gate HALTED at Step 1b (Edge Case Analysis). {{findings_count}} unhandled edge cases remain after {{step_1b_loops}} loop-backs. Partial report saved."</action>
</check>

<template-output>Update Step 1b in the quality report with the subagent's results.</template-output>

---

## Step 2: QA Automation Test

**Goal:** Generate automated tests for the code just implemented in this story. Run after code review so tests target stable, reviewed code.

<check if="step_2_loops == 0">
  <action>Spawn a `general-purpose` Claude Code Task subagent with the following prompt:</action>

```
You are running autonomous QA test generation as part of a quality gate.

CRITICAL INSTRUCTIONS:
1. Read the QA test generation skill: {project-root}/.claude/skills/bmad-qa-generate-e2e-tests/SKILL.md
2. Follow its Execution section (Steps 0-5). Skip interactive On Activation steps (greeting, user prompts) — operate autonomously.
3. For Step 1 (Identify Features), auto-discover from the story file's acceptance criteria and file list instead of asking the user.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{planning_artifacts}}/architecture.md for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

Focus on code implemented for this story.

AUTONOMOUS BEHAVIOR:
- Run in YOLO mode — skip all confirmations and user prompts.
- Auto-discover features to test from the story file's File List and acceptance criteria.
- Generate and run all tests without asking for user input.
- Run tests using the project's test runner as specified in CLAUDE.md.
  Scope tests to the relevant app/package if the project supports scoped test runs.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
tests_generated: [number]
tests_passing: [number]
tests_failing: [number]
test_files: [comma-separated list of test file paths]
notes: [1-3 sentence summary of tests generated and any issues]
---END---
```
</check>

<check if="step_2_loops > 0">
  <action>Spawn a `general-purpose` TARGETED VERIFICATION subagent with the following prompt:</action>

```
You are verifying that test fixes resolved failures (loop-back {{step_2_loops}}).

This is NOT a full QA generation re-run. Tests were already generated but some failed.
A fix subagent attempted to fix them. Your job is to run the tests and confirm they pass.

INSTRUCTIONS:
1. Run tests using the project's test runner as specified in CLAUDE.md.
   Scope tests to the relevant app/package if the project supports scoped test runs.
2. If any tests still fail, attempt to fix them directly.
3. Run tests again to confirm.
4. Do NOT generate new tests — only fix existing failing ones.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
tests_generated: 0
tests_passing: [number]
tests_failing: [number]
test_files: [comma-separated list of test file paths that were fixed, or "none"]
notes: [1-3 sentence summary]
---END---
```
</check>

<action>Parse the subagent's returned results.</action>

<check if="tests_failing > 0 AND step_2_loops < max_loopbacks_per_step">
  <action>Increment step_2_loops. Log: "Step 2 loop-back {{step_2_loops}}/{{max_loopbacks_per_step}} — spawning fix subagent for failing tests, then targeted verification."</action>
  <action>Spawn a `general-purpose` fix subagent with prompt: "Fix failing tests for Story {{story_id}}. {{tests_failing}} tests are failing. Run tests using the project's test runner as specified in CLAUDE.md to see the failures, then fix the test code or the implementation code as appropriate. Run tests again to confirm fixes work."</action>
  <goto step="Step 2"/>
</check>

<check if="tests_failing > 0 AND step_2_loops >= max_loopbacks_per_step">
  <action>Mark Step 2 as FAILED in the quality report.</action>
  <template-output>Update Step 2 in the quality report with FAILED status and failing test count.</template-output>
  <action>**HALT** — QA automation failed after {{max_loopbacks_per_step}} loop-backs with {{tests_failing}} tests still failing. Save partial report and stop workflow.</action>
  <action>Present HALT summary to user: "Quality gate HALTED at Step 2 (QA Automation). {{tests_failing}} tests still failing after {{step_2_loops}} loop-backs. Partial report saved."</action>
</check>

<template-output>Update Step 2 in the quality report with the subagent's results.</template-output>

---

## Step 3: Complementary Review

**Goal:** Business logic and functional review that COMPLEMENTS (not duplicates) Step 1's code review. This step focuses exclusively on business correctness, user-facing behavior, and integration concerns — areas that a code-quality review typically misses.

<action>Spawn a `general-purpose` Claude Code Task subagent with the following prompt:</action>

```
You are running a COMPLEMENTARY business/functional review as part of a quality gate.

IMPORTANT: A thorough CODE QUALITY review (Step 1) and an exhaustive EDGE CASE ANALYSIS
(Step 1b) have already been completed. The following issues were already identified and
addressed — DO NOT re-examine these areas:

--- STEP 1 FINDINGS (already covered) ---
{{step_1_findings}}
--- END STEP 1 FINDINGS ---

--- STEP 1b EDGE CASE FINDINGS (already covered) ---
{{step_1b_findings}}
--- END STEP 1b FINDINGS ---

Your review must focus EXCLUSIVELY on areas that code review does NOT cover:

1. BUSINESS LOGIC CORRECTNESS — Does the implementation correctly solve the business problem?
   Walk through the acceptance criteria as a USER, not as a code reviewer.
2. FUNCTIONAL AC VERIFICATION — For each acceptance criterion, can a user actually achieve the
   stated outcome? Think user journeys, not code paths.
3. INTEGRATION CONCERNS — How does this story's implementation interact with existing features?
   Are there data flow issues, race conditions at the feature level, or state management gaps?
4. DATA FLOW EDGE CASES — What happens with empty data, maximum data, concurrent users,
   timezone boundaries, currency edge cases, rate-limit responses, etc.?
5. MISSING IMPLIED REQUIREMENTS — What did the story NOT say that a reasonable user would expect?
   (e.g., loading states, empty states, error feedback, keyboard navigation, screen-reader
   announcements)

DO NOT review: code style, naming, architecture patterns, security headers, performance
micro-optimizations, test quality — these are Step 1's domain.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{planning_artifacts}}/architecture.md for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

INSTRUCTIONS:
1. Read the story file completely — focus on acceptance criteria and user intent.
2. Read the implemented code to understand behavior (not style).
3. For each acceptance criterion, mentally walk through the user experience.
4. Produce at least 3 findings (can be LOW severity observations if quality is high).
5. Classify each finding: HIGH (breaks user expectations), MEDIUM (degrades experience), LOW (minor gap).

AUTONOMOUS BEHAVIOR:
- Run in YOLO mode — skip all confirmations.
- Fix HIGH severity issues directly if possible.
- For MEDIUM/LOW issues, document them but do not fix unless trivial.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|PASSED_WITH_CONCERNS|FAILED]
total_issues: [number]
high_count: [number]
medium_count: [number]
low_count: [number]
inline_fixes: [number of HIGH/MEDIUM issues fixed directly by sub-agent]
findings_summary: [detailed summary of all findings with severities]
notes: [1-3 sentence overall assessment]
---END---
```

<action>Parse the subagent's returned results.</action>
<action>Add inline_fixes to total_inline_fixes.</action>

<check if="high_count > 0 AND step_3_loops < max_loopbacks_per_step">
  <action>Increment step_3_loops. Log: "Step 3 loop-back {{step_3_loops}}/{{max_loopbacks_per_step}} — spawning fix subagent for HIGH severity business/functional issues, then re-evaluating."</action>
  <action>Spawn a `general-purpose` fix subagent with prompt: "Fix the following HIGH severity business/functional issues found during complementary review of Story {{story_id}}: {{findings_summary}}. Read the story file at {{story_location}}/story-{{story_id}}*.md for context. Fix all HIGH severity issues. Run tests using the project's test runner as specified in CLAUDE.md after fixing to confirm nothing is broken."</action>
  <goto step="Step 3"/>
</check>

<check if="high_count > 0 AND step_3_loops >= max_loopbacks_per_step">
  <action>Mark Step 3 as FAILED in the quality report.</action>
  <template-output>Update Step 3 with FAILED status and remaining HIGH severity issues.</template-output>
  <action>**HALT** — Complementary review failed after {{max_loopbacks_per_step}} loop-backs with {{high_count}} HIGH severity issues remaining. Save partial report and stop workflow.</action>
  <action>Present HALT summary to user: "Quality gate HALTED at Step 3 (Complementary Review). {{high_count}} HIGH severity issues remain after {{step_3_loops}} loop-backs. Partial report saved."</action>
</check>

<template-output>Update Step 3 in the quality report with the subagent's results.</template-output>

---

## Step 4: Test Quality & Traceability

**Goal:** Parallel assessment of test quality (4a) and requirements traceability (4b). Both must pass.

<action>Spawn BOTH subagents concurrently. Do NOT wait for 4a to finish before starting 4b.</action>

### Step 4a: Test Review (TEA)

<check if="step_4a_loops == 0">
  <action>Spawn a `general-purpose` Claude Code Task subagent with the following prompt:</action>

```
You are running an autonomous test quality review as part of a quality gate.

CRITICAL INSTRUCTIONS:
1. Read the FULL workflow engine file at: {project-root}/_bmad/core/tasks/workflow.xml
2. Read its entire contents — this is the CORE OS for executing workflows.
3. Execute the workflow at: {project-root}/.claude/skills/bmad-testarch-test-review/workflow.yaml
4. Pass the yaml path as 'workflow-config' parameter to the workflow.xml instructions.
5. Follow workflow.xml instructions EXACTLY.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md
- Review the tests related to this story.

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{planning_artifacts}}/architecture.md for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

AUTONOMOUS BEHAVIOR:
- Run in YOLO mode — skip all confirmations and user prompts.
- Complete the full test review producing a quality score (0-100).
- Apply any recommended fixes automatically.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
quality_score: [0-100]
strengths: [comma-separated list]
weaknesses: [comma-separated list]
inline_fixes: [number of test improvements applied]
fixes_applied: [description of any fixes made, or "none"]
notes: [1-3 sentence summary of test quality assessment]
---END---
```
</check>

<check if="step_4a_loops > 0">
  <action>Spawn a `general-purpose` TARGETED VERIFICATION subagent with the following prompt:</action>

```
You are verifying test quality improvements (loop-back {{step_4a_loops}}).

A fix subagent has improved test quality. Verify the improvements are effective.

PREVIOUS WEAKNESSES: {{step_4a_weaknesses}}

INSTRUCTIONS:
1. Re-evaluate ONLY the previously identified weaknesses — do not run a full test review.
2. Check if each weakness has been addressed.
3. Produce an updated quality score.
4. If new weaknesses emerged from the fixes, note them.
5. Run tests using the project's test runner as specified in CLAUDE.md.
   Scope tests to the relevant app/package if the project supports scoped test runs.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
quality_score: [0-100]
strengths: [comma-separated list]
weaknesses: [comma-separated list]
inline_fixes: [number of test improvements applied]
fixes_applied: [description of fixes verified]
notes: [1-3 sentence summary]
---END---
```
</check>

### Step 4b: Traceability Check (TEA)

<check if="step_4b_loops == 0">
  <action>Spawn a `general-purpose` Claude Code Task subagent with the following prompt:</action>

```
You are running an autonomous traceability check as part of a quality gate.

CRITICAL INSTRUCTIONS:
1. Read the FULL workflow engine file at: {project-root}/_bmad/core/tasks/workflow.xml
2. Read its entire contents — this is the CORE OS for executing workflows.
3. Execute the workflow at: {project-root}/.claude/skills/bmad-testarch-trace/workflow.yaml
4. Pass the yaml path as 'workflow-config' parameter to the workflow.xml instructions.
5. Follow workflow.xml instructions EXACTLY.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

AUTONOMOUS BEHAVIOR:
- Run in YOLO mode — skip all confirmations and user prompts.
- Map tests to acceptance criteria from the story file.
- Produce a gate decision: PASS, CONCERNS, FAIL, or WAIVED.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
gate_decision: [PASS|CONCERNS|FAIL|WAIVED]
acs_total: [number of acceptance criteria]
acs_covered: [number with test coverage]
coverage_summary: [brief coverage description]
gaps: [list of gaps if any, or "none"]
notes: [1-3 sentence summary]
---END---
```
</check>

<check if="step_4b_loops > 0">
  <action>Spawn a `general-purpose` TARGETED VERIFICATION subagent with the following prompt:</action>

```
You are verifying that traceability gaps have been closed (loop-back {{step_4b_loops}}).

A fix subagent wrote tests to cover missing acceptance criteria. Verify coverage is now complete.

PREVIOUS GAPS: {{step_4b_gaps}}

INSTRUCTIONS:
1. For each previously identified gap, check if a test now covers it.
2. Run tests using the project's test runner as specified in CLAUDE.md.
   Scope tests to the relevant app/package if the project supports scoped test runs.
3. Produce an updated gate decision.
4. Do NOT re-map the entire traceability matrix — only verify the gaps.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
gate_decision: [PASS|CONCERNS|FAIL|WAIVED]
acs_total: [number of acceptance criteria]
acs_covered: [number with test coverage]
coverage_summary: [brief coverage description]
gaps: [list of remaining gaps if any, or "none"]
notes: [1-3 sentence summary]
---END---
```
</check>

<action>Wait for BOTH subagents to complete. Parse results from each.</action>
<action>Add Step 4a inline_fixes to total_inline_fixes.</action>

**Step 4a loop-back logic:**

<check if="quality_score < 70 AND step_4a_loops < max_loopbacks_per_step">
  <action>Increment step_4a_loops. Log: "Step 4a loop-back {{step_4a_loops}}/{{max_loopbacks_per_step}} — spawning fix subagent for test quality."</action>
  <action>Save step_4a_weaknesses from the results weaknesses field.</action>
  <action>Spawn a `general-purpose` fix subagent with prompt: "Improve test quality for Story {{story_id}}. The test review scored {{quality_score}}/100. Weaknesses identified: {{step_4a_weaknesses}}. Read the story file at {{story_location}}/story-{{story_id}}*.md for context. Address the weaknesses — improve test structure, assertions, coverage, naming, and patterns. Run tests using the project's test runner as specified in CLAUDE.md after improvements to confirm they pass."</action>
  <goto step="Step 4" note="Only 4a re-runs; if 4b already passed, skip its subagent spawn."/>
</check>

<check if="quality_score < 70 AND step_4a_loops >= max_loopbacks_per_step">
  <action>Mark Step 4a as FAILED in the quality report.</action>
  <template-output>Update Step 4a with FAILED status, score, and remaining weaknesses.</template-output>
  <action>**HALT** — Test review failed after {{max_loopbacks_per_step}} loop-backs with score {{quality_score}}/100 (threshold: 70). Save partial report and stop workflow.</action>
  <action>Present HALT summary to user: "Quality gate HALTED at Step 4a (Test Review). Score {{quality_score}}/100 after {{step_4a_loops}} loop-backs. Partial report saved."</action>
</check>

**Step 4b loop-back logic:**

<check if="gate_decision == 'FAIL' AND step_4b_loops < max_loopbacks_per_step">
  <action>Increment step_4b_loops. Log: "Step 4b loop-back {{step_4b_loops}}/{{max_loopbacks_per_step}} — spawning fix subagent for traceability gaps."</action>
  <action>Save step_4b_gaps from the results gaps field.</action>
  <action>Spawn a `general-purpose` fix subagent with prompt: "Write missing tests for Story {{story_id}} to close traceability gaps. Gaps identified: {{step_4b_gaps}}. Read the story file at {{story_location}}/story-{{story_id}}*.md for the acceptance criteria. Write tests that cover the missing acceptance criteria. Follow existing test patterns in the relevant app/package as specified in CLAUDE.md. Run tests using the project's test runner as specified in CLAUDE.md after writing to confirm they pass."</action>
  <goto step="Step 4" note="Only 4b re-runs; if 4a already passed, skip its subagent spawn."/>
</check>

<check if="gate_decision == 'FAIL' AND step_4b_loops >= max_loopbacks_per_step">
  <action>Mark Step 4b as FAILED in the quality report.</action>
  <template-output>Update Step 4b with FAILED status and remaining gaps.</template-output>
  <action>**HALT** — Traceability check failed after {{max_loopbacks_per_step}} loop-backs with gate decision FAIL. Gaps: {{step_4b_gaps}}. Save partial report and stop workflow.</action>
  <action>Present HALT summary to user: "Quality gate HALTED at Step 4b (Traceability). Gate decision FAIL after {{step_4b_loops}} loop-backs. Partial report saved."</action>
</check>

<template-output>Update Step 4 in the quality report with both 4a and 4b results.</template-output>

---

## Step 5: Documentation

**Goal:** Ensure all code and features from this story are properly documented. Runs BEFORE CI so doc changes are included in the commit.

<check if="docs_mode from customize.toml is 'skip'">
  <action>Log: "Step 5 skipped — docs_mode is set to 'skip' in customize.toml."</action>
  <template-output>Update Step 5 in the quality report with SKIPPED status.</template-output>
  <goto step="Step 6"/>
</check>

**DOCUMENTATION TARGETS:**
1. **Docs site pages (`{{docs_site_content_path}}`)** — If `{{docs_site_content_path}}` is configured, create or update pages with full API reference for every exported component, hook, type, and function the story introduces or changes. This is the PRIMARY documentation deliverable.
2. **Internal docs** — Update internal documentation only if new patterns or conventions were introduced.

<action>Spawn a `general-purpose` Claude Code Task subagent with the following prompt:</action>

```
You are acting as a Technical Writer creating API documentation for a completed story.

CONTEXT:
- Story ID: {{story_id}}
- Story Name: {{story_name}}
- Story scope: {{story_scope}}
- Story file: {{story_location}}/story-{{story_id}}*.md

PROJECT CONTEXT:
{{project_context}}

BINDING RULES:
Read {project-root}/CLAUDE.md for all project rules, toolchain, naming conventions, and coding standards.
Read {{planning_artifacts}}/architecture.md for architecture decisions and constraints.
Treat rules from these documents as binding constraints.

DOCS SITE TARGET: {{docs_site_content_path}}
(If this path is blank, skip docs-site page generation and focus on internal docs only.)

INSTRUCTIONS:
1. Read the story file completely to understand what was implemented.
2. Read the story's File List to identify all files created/modified across the relevant
   app/package(s).
3. Read EVERY source file that was created or modified — you need the actual TypeScript
   interfaces, props types, function signatures, and exported constants.
4. If docs_site_content_path is configured:
   a. Read existing documentation files under {{docs_site_content_path}} to understand the
      style and structure. Match the existing pattern.
   b. Read any navigation configuration files (e.g. _meta.ts, sidebar config) for current entries.
   c. Identify index/category pages. When this story introduces a new component, hook, utility,
      or route, add a short stub entry to the matching index page: 2-3 lines describing the
      addition + an "Added in Story {{story_id}}" note + a cross-reference link to the
      feature-scoped page. Skipping index-page stubs is a Step 5 FAILURE even if the feature
      page is complete.
   d. For each major feature area, create or update a feature-scoped page containing:
      - Architecture overview — how the feature works, design decisions
      - API Reference section — for EVERY exported component, hook, function, type, and constant:
        - Full props/options table with Type, Default, and Description columns
        - Return value table (for hooks/functions)
        - Usage example with import statement
        - Behaviour notes (edge cases, accessibility, theming, animations)
      - Constants tables — every exported constant with value and description
      - Key Files table — mapping files to their purpose
      - Update navigation config to include any new pages.
5. Update internal project documentation ONLY if new patterns, conventions, or architecture
   decisions were introduced.

DO NOT write shallow overview pages. The documentation must contain enough detail that a
developer can use every API without reading source code.

AUTONOMOUS BEHAVIOR:
- Do not ask for user input — make documentation decisions independently.
- Read the actual source code to extract accurate type signatures — do NOT guess or fabricate.
- If a documentation page already exists for this feature area, UPDATE it with new API entries
  rather than creating a duplicate.

VERIFICATION (you MUST do this before reporting results):
- For each documentation file you created/updated, re-read it from disk to confirm it was saved.
- Confirm navigation config files include entries for all new pages.
- Count the number of API entries (components, hooks, functions, types, constants) documented.

REQUIRED OUTPUT FORMAT (return EXACTLY this structure):
---RESULTS---
status: [PASSED|FAILED]
docs_site_pages_updated: [comma-separated list of file paths, or "none"]
docs_site_pages_created: [comma-separated list of file paths, or "none"]
index_pages_stubbed: [comma-separated list of index files updated with stubs, or "n/a" if story introduced no new components/hooks/utilities/routes]
api_entries_documented: [number of components/hooks/functions/types/constants documented]
internal_docs_updated: [comma-separated list of file paths, or "none"]
notes: [1-3 sentence summary of documentation changes]
---END---
```

<action>Parse the subagent's returned results.</action>

<check if="docs_site_content_path is configured AND docs_site_pages_updated == 'none' AND docs_site_pages_created == 'none'">
  <action>**FAIL Step 5** — No docs-site pages were created or updated. Every story MUST produce API documentation.</action>
  <action>Log: "Step 5 FAILED: No docs-site pages were written. Re-running documentation subagent."</action>
  <action>Re-spawn the documentation subagent with the same prompt. If it fails again, mark Step 5 as FAILED.</action>
</check>

<check if="api_entries_documented is 0 or very low relative to files created">
  <action>**FAIL Step 5** — API reference is missing or incomplete. Re-run documentation subagent.</action>
</check>

<check if="the story added new components/hooks/utilities/routes AND index_pages_stubbed == 'none'">
  <action>**FAIL Step 5** — Index pages were not updated with stubs for the new additions. Re-run the documentation subagent emphasising the index-stub requirement.</action>
</check>

**Docs Generation** (runs in orchestrator — not a subagent):

<check if="docs_generate_command is configured in customize.toml">
  <action>Run `{{docs_generate_command}}` to regenerate pages from story spec files. This ensures the newly created/updated story appears in the docs site.</action>
  <action>Verify the story's page was generated. If the generator does not yet support this epic, log a WARNING (do not FAIL).</action>
</check>

**Docs Site Verification** (runs in orchestrator — not a subagent):

<check if="docs_site_content_path is configured">
  <action>Verify docs-site API reference files exist on disk: glob for `{{docs_site_content_path}}/**/*` and confirm new/updated files are present.</action>
  <action>Verify navigation config files have entries for all new pages.</action>
  <action>Run the docs-site build command as specified in CLAUDE.md to verify all content is valid.</action>
  <check if="docs-site build failed">
    <action>Read the build error output and fix the issue.</action>
    <action>Re-run the build to confirm the fix.</action>
  </check>
</check>

<action>Set docs_status based on the outcome: "verified" if files exist and build passed, "fixed" if a fix was needed, "skipped" if docs_site_content_path is not configured, or "failed" if documentation is missing or broken.</action>

<template-output>Update Step 5 in the quality report with the subagent's results and docs_status. Include docs-site pages created/updated, API entries count, and internal docs updates.</template-output>

---

## Step 6: CI Verification & Sprint Status

**Goal:** Confirm sprint status, commit all code, and verify CI passes. This step runs directly in the orchestrator (not a subagent) because it requires sequential git/gh CLI operations.

**Inline Sprint Status Check** (runs BEFORE commit so it's included in the single push):

<action>Read the sprint status file at `{{sprint_status_file}}`.</action>
<action>Check if Story {{story_id}} is marked as "done". If not, update its status to "done" and save the file.</action>
<action>Record: story_marked_done = [yes|already_done], sprint_progress = [brief summary from file].</action>

**Pre-commit checks (run from repo root):**

<action>Run pre-commit checks as specified in CLAUDE.md (typically lint, typecheck, and any
project-specific extraction/generation commands).</action>

**Commit & Push:**

<action>Stage all modified and new files related to Story {{story_id}}. Use `git status` to identify changes, then `git add` specific files (avoid `git add -A`). This includes code, tests, docs, and the sprint status update.</action>
<action>Commit with message: `feat: implement Story {{story_id}} {{story_name}}` (or `fix:` / `docs:` as appropriate based on the changes). Include `Co-Authored-By: Claude <noreply@anthropic.com>` in the commit.</action>
<action>Push to the remote repository: `git push`.</action>
<action>Poll CI status using `gh run list --branch main --limit 1 --json status,conclusion,databaseId` until the run completes (check every 30 seconds, max 10 minutes).</action>
<action>Once CI completes, capture: commit hash, CI run ID, pass/fail status, and test counts from `gh run view`. CI runs the project's configured pipeline. Check for pass/fail conclusion.</action>

<check if="CI failed AND step_6_loops < max_loopbacks_per_step">
  <action>Increment step_6_loops. Log: "Step 6 loop-back {{step_6_loops}}/{{max_loopbacks_per_step}} — reading CI failure logs and fixing."</action>
  <action>Read CI failure logs: `gh run view [run_id] --log-failed`.</action>
  <action>Analyze failures and fix the issues locally.</action>
  <action>Run tests locally to verify the fix using the project's test runner as specified in CLAUDE.md.</action>
  <goto step="Step 6"/>
</check>

<check if="CI failed AND step_6_loops >= max_loopbacks_per_step">
  <action>Mark Step 6 as FAILED in the quality report.</action>
  <template-output>Update Step 6 with FAILED status and CI failure details.</template-output>
  <action>**HALT** — CI verification failed after {{max_loopbacks_per_step}} loop-backs. Save partial report and stop workflow.</action>
  <action>Present HALT summary to user: "Quality gate HALTED at Step 6 (CI Verification). CI pipeline still failing after {{step_6_loops}} loop-backs. Partial report saved."</action>
</check>

<template-output>Update Step 6 in the quality report with commit hash, CI status, test results, sprint status fields.</template-output>

---

## Step 7: Finalize Report

<action>Complete the Summary table in the quality report using collected data from all steps. The table must include an "Inline Fixes" column:

```
| Step | Name | Status | Loop-backs | Inline Fixes |
```

Populate inline fix counts from the accumulated values for steps 1, 1b, 3, and 4a. Steps that don't track inline fixes (2, 4b, 5, 6) show 0 or "---".</action>
<action>Calculate total loop-backs: step_1_loops + step_1b_loops + step_2_loops + step_3_loops + step_4a_loops + step_4b_loops + step_6_loops.</action>
<action>Calculate total inline fixes: total_inline_fixes (already accumulated during steps 1, 1b, 3, 4a).</action>
<action>Determine overall gate status:
  - **PASSED** — all steps passed with 0 loop-backs
  - **PASSED** — all steps passed (some loop-backs were needed but all resolved)
  - **PASSED WITH CONCERNS** — all steps passed but complementary review found medium/low concerns that were noted but not fixed
  - **HALTED** — a step failed after max loop-backs (this case is handled by the HALT logic above and the workflow would not reach this step)
</action>
<action>Generate a lessons/observations summary based on:
  - Which steps required loop-backs and why
  - Which steps applied inline fixes (issues fixed within sub-agent execution before returning results)
  - Any patterns or recurring issues observed across steps
  - Recommendations for future stories
</action>

<template-output>Finalize the quality report with the summary table (including Inline Fixes column), total loop-backs, total inline fixes, overall status, and lessons.</template-output>

<action>Save the completed report to: `{{quality_report_location}}/story-{{story_id}}-quality-report.md`</action>

<action>Commit and push the quality report (this is a docs-only change, so skip CI):
  `git add {{quality_report_location}}/story-{{story_id}}-quality-report.md`
  Commit with message: `docs: finalize Story {{story_id}} quality gate report [skip ci]`
  Include `Co-Authored-By: Claude <noreply@anthropic.com>` in the commit.
  `git push`
</action>

Present the final summary to the user:
- Overall gate status (PASSED / PASSED WITH CONCERNS)
- Total loop-backs across all steps
- **Total Inline Fixes:** {{total_inline_fixes}}
- Key observations
- Reminder: if this is the last story in an epic, consider running a retrospective next
- Otherwise: proceed to creating the next story
</content>
</invoke>