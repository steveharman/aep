# Autonomous Epic Pipeline — Orchestrator Workflow v2

**Role:** Loop `/aep-implement-story` across pending stories in one or more epics, clearing context between stories via fresh `claude -p` sub-processes.

> **Contract with inner workflow:**
> 1. `claude -p "/aep-implement-story <N>-<X>"` runs the full pipeline end-to-end.
> 2. On success, sprint-status shows the story as `done`.
> 3. On success, a quality report exists containing `**Overall Gate Status:** PASSED` or `PASSED_WITH_CONCERNS`.
> 4. On success, CI passed for a non-`[skip ci]` commit touching the story's code.
>
> If all three signals agree, the story is complete. Otherwise halt and alert the user.

---

## Resolved Paths

- `{{sprint_status_file}}` — resolved from config during On Activation
- `{{story_location}}` — resolved from config during On Activation
- `{{quality_report_location}}` — resolved from config during On Activation
- `{{epics_source}}` — resolved from config during On Activation

---

## Inputs

**Required:** `<epic-ids>`

- `<epic-ids>` — one or more epic identifiers, comma-separated. Case-insensitive.

Examples:
```
/aep-implement-epic 1
/aep-implement-epic 1,2,3
/aep-implement-epic 2
```

---

## Step 1: Validate Inputs

**Goal:** Confirm target epics exist and have work remaining.

<action>Parse the input. Extract `{{epic_ids_raw}}` (comma-separated string).</action>

<action>Read `{{sprint_status_file}}`. If missing → **HALT:** "Sprint-status file not found."</action>

<action>Parse `{{epic_ids_raw}}` into a list. For each:
- Lowercase, strip any `epic-` prefix, then prepend `epic-`.
- Store as `{{epic_keys}}` list (e.g. `["epic-1", "epic-2", "epic-3"]`).
- Store bare ids as `{{epic_ids}}` list (e.g. `["1", "2", "3"]`).
</action>

<action>For each epic key, validate:
- Present in `development_status` → if not, **HALT:** "Epic `{{key}}` not found in sprint-status."
- Not already `done` → if done, skip with log: "Epic `{{key}}` already done, skipping."
</action>

<action>If ALL epics are done → **HALT:** "All specified epics are already done."</action>

### Step 1b: Epic Sequence Gate

**Goal:** Prevent out-of-order epic execution. All earlier epics must be `done` before the requested epic(s) can run.

<action>Collect every `epic-*` key from `development_status` (excluding retrospectives). These appear in file order, which is the canonical execution sequence.</action>

<action>Identify the **lowest requested epic** — the first epic in file order whose key is in `{{epic_keys}}`.</action>

<action>Scan all `epic-*` keys that appear **before** the lowest requested epic in file order. For each:
- If status is `done` → OK, continue.
- If status is `backlog` or `in-progress` → collect into `{{blocking_epics}}`.
</action>

<action>If `{{blocking_epics}}` is non-empty → **HALT:**

```
**Epic sequence violation.**

Cannot start epic {{lowest_requested_id}} — earlier epic(s) are not done:
{{for each blocker: - epic-{{id}}: {{status}}}}

Epics must be completed in order. Either:
1. Run the blocking epic(s) first: `/aep-implement-epic {{blocker_ids}}`
2. Manually mark them done if already complete: update `{{sprint_status_file}}`
```
</action>

---

## Step 2: Build Epic Queue

**Goal:** For each epic, enumerate pending stories. Present the overall plan.

<action>For each non-done epic in `{{epic_keys}}`, scan `development_status` in file order:

- Collect story keys matching `^{{epic_id}}-\d+-` (exclude the epic key itself and retrospective).
- Extract story_id from leading prefix (e.g. `1-2-setup-auth-middleware` → `1-2`).
- Split into `already_done` and `pending` lists.
</action>

<action>If an epic has zero pending stories → log: "All stories in `{{key}}` done. Epic status may need updating." Skip it.</action>

<action>Present plan:

```
**Epic Pipeline Plan**

{{for each epic}}
Epic {{epic_id}} — {{pending.length}} pending, {{already_done.length}} done
  Pending: {{pending story_ids, comma-separated}}
  Skipping: {{already_done story_ids, comma-separated}}
{{end for}}

Total: {{total_pending}} stories to process across {{epic_count}} epics.
Each story runs in a fresh Claude Code session via `claude -p`.
Stories run strictly sequentially. On any failure, the pipeline halts.

Estimated time: 20–60 minutes per story.
```
</action>

---

## Step 3: Process Stories

**Goal:** Run each pending story through the inner pipeline. Verify completion. Halt on failure.

<action>Initialize: `completed_this_run = []`, `current_epic_idx = 0`.</action>

<for-each epic in non-done epic queue>
  <for-each story in pending stories for this epic>

  ### Step 3a: Invoke Inner Workflow

  <action>Log: "**[{{global_index}}/{{total_pending}}] Starting story `{{story_id}}` (epic {{epic_id}}) — fresh session.**"</action>

  <action>Invoke via Bash with `run_in_background: true`:
  ```
  claude -p --dangerously-skip-permissions "/aep-implement-story {{story_id}}

{{project_context}}

CONTEXT FROM EPIC ORCHESTRATOR:
- Sprint status file: {{sprint_status_file}}
- Story location: {{story_location}}
- Quality report location: {{quality_report_location}}
- Epics source: {{epics_source}}"
  ```

  **Why `run_in_background`:** A full story pipeline takes 20–60 min. Foreground Bash times out at 10 min.

  **Why `--dangerously-skip-permissions`:** `claude -p` is non-interactive — no human to approve prompts. The subprocess does NOT inherit parent approvals. Without this flag it halts at the first file write.
  </action>

  ### Step 3b: Wait for Completion

  <action>Poll until the background process exits. Give brief status updates every 5–10 min.</action>

  ### Step 3b-watchdog: Hung Process Detection

  **Context:** `claude -p` subprocesses occasionally hang after completing all work. The process never exits, but all deliverables are committed and pushed.

  <action>If the background task notification has not arrived and **more than 10 minutes** have passed since the last git commit for this story, run the triple-signal check (Step 3c) early.

  If all three signals pass (status=done, report=PASSED/PASSED_WITH_CONCERNS, CI=PASSED):
  1. Log: "**Watchdog: subprocess hung post-completion. All 3 signals pass. Killing process.**"
  2. Kill the subprocess via `kill <pid>`.
  3. Proceed to the COMPLETE outcome path — do NOT treat the kill as a failure.

  If signals do NOT all pass, continue waiting — the process is still working.</action>

  ### Step 3c: Triple-Signal Verification

  **Signal 1 — Sprint Status:**
  <action>Re-read `{{sprint_status_file}}`. Look up story slug. Store `{{post_status}}`.</action>

  **Signal 2 — Quality Report:**
  <action>Check `{{quality_report_location}}/story-{{story_id}}-quality-report.md`. If exists, grep for `**Overall Gate Status:** <value>` (accept both "Overall Gate Status" and "Overall Status" for backwards compat). Store `{{report_status}}`. If missing → `{{report_status}} = MISSING`.</action>

  **Signal 3 — CI Verification:**
  <action>
  1. Find latest commit touching this story: `git log --oneline -10 -- '{{story_location}}/{{story_slug}}.md'`
  2. Check commit message for `[skip ci]`. If present → `{{ci_signal}} = SKIPPED`.
  3. If no `[skip ci]`, find the CI run for that SHA via `gh run list --commit <sha>`.
  4. Check the overall run conclusion:
     ```bash
     gh run list --commit <sha> --json databaseId,conclusion --jq '.[0].conclusion'
     ```
     - conclusion == "success" → `{{ci_signal}} = PASSED`
     - conclusion == "failure" → `{{ci_signal}} = FAILED`
     - no run found → `{{ci_signal}} = MISSING`
  </action>

  **Determine outcome:**
  - **COMPLETE** if and only if: `post_status == 'done'` AND `report_status IN ('PASSED', 'PASSED_WITH_CONCERNS')` AND `ci_signal == 'PASSED'`
  - **FAILED** otherwise

  <check if="outcome == 'COMPLETE'">
    <action>Log: "**Story `{{story_id}}` complete.** status=`{{post_status}}`, report=`{{report_status}}`, CI=`{{ci_signal}}`"</action>
    <action>Append to `completed_this_run`. Continue to next story.</action>
  </check>

  <check if="outcome == 'FAILED'">
    <action>**HALT the pipeline.** Log:

    ```
    **Pipeline HALTED at story `{{story_id}}` (epic {{epic_id}}).**

    Signals:
    - sprint-status: `{{post_status}}` (expected `done`)
    - quality report: `{{report_status}}` (expected `PASSED` or `PASSED_WITH_CONCERNS`)
    - CI: `{{ci_signal}}` (expected `PASSED`)

    Progress:
    - Completed this run: {{completed_this_run.length}} — {{ids}}
    - Remaining: {{remaining}} stories

    To resume: `/aep-implement-epic {{epic_ids_raw}}`
    Done stories are skipped automatically.
    ```
    </action>
    <action>**END workflow. Do NOT attempt further stories.**</action>
  </check>

  </for-each>

  <action>Log: "**Epic {{epic_id}} complete.** All {{stories.length}} stories done."</action>

</for-each>

---

## Step 4: Grand Summary

<action>Present:

```
**Epic Pipeline Complete**

| Epic | Stories Processed | Already Done | Total |
|------|------------------|-------------|-------|
{{for each epic: | {{epic_id}} | {{processed}} | {{skipped}} | {{total}} |}}

**Total:** {{completed_this_run.length}} stories processed, 0 failed.

Next steps:
- Verify epic-level statuses in `{{sprint_status_file}}`
- Consider running a retrospective for completed epics
```
</action>

---

## Failure Modes & Recovery

| Failure | Recovery |
|---------|----------|
| Unknown epic | HALT at Step 1 — user corrects input |
| Earlier epic not done | HALT at Step 1b — run blocking epic(s) first or manually mark done |
| All epics done | HALT at Step 1 — nothing to do |
| Story pipeline halts mid-way | HALT at Step 3c — signals disagree. Fix manually, re-run. |
| `claude -p` crashes | HALT at Step 3c — no status update or report. Same recovery. |
| CI fails for a story | HALT at Step 3c — inner workflow should fix, but if not caught, outer detects. |
| Inner workflow skips commit/push | HALT at Step 3c — Signal 3 catches missing CI run. |
| `claude -p` hangs post-completion | Step 3b-watchdog detects via triple-signal, kills process, continues. |

**Idempotency:** Re-running with same args is always safe. Done stories are skipped.
