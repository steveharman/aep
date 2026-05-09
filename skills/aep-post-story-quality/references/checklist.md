# Post-Story Quality Gate (Autonomous) — Validation Checklist

Use this checklist to validate that the autonomous quality gate executed correctly for a story. Project-specific toolchain, test commands, and conventions are sourced from CLAUDE.md and customize.toml.

## Pre-Gate (Step 0)
- [ ] Story ID and name correctly identified
- [ ] Story file loaded from `{{story_location}}` and reviewed for acceptance criteria
- [ ] Sprint status loaded from `{{sprint_status_file}}` for context
- [ ] Story scope resolved from the story file's Tasks and File List
- [ ] Output file created from template with section headers rewritten to 7-step structure
- [ ] Loop-back counters initialized: step_1_loops, step_1b_loops, step_2_loops, step_3_loops, step_4a_loops, step_4b_loops, step_6_loops
- [ ] Findings accumulators initialized: step_1_findings, step_1b_findings
- [ ] YOLO mode activated after user confirmation

## Step 1: Code Review
- [ ] First run: subagent spawned with code-review workflow
- [ ] Subagent prompt includes project context and binding rules from CLAUDE.md and architecture.md
- [ ] Subagent prompt includes project-specific checks derived from CLAUDE.md
- [ ] Loop-back: TARGETED VERIFICATION subagent spawned (not full re-run)
- [ ] Subagent returned structured ---RESULTS--- block
- [ ] Results parsed: status, issues found/fixed/remaining, severities, findings_summary
- [ ] step_1_findings accumulator updated with findings_summary
- [ ] Fix subagent spawned before loop-back (fix -> verify pattern), runs tests/lint/typecheck as specified in CLAUDE.md
- [ ] Loop-back triggered if issues_remaining > 0 (max {{max_loopbacks_per_step}})
- [ ] HALT triggered if issues remain after max loop-backs
- [ ] Quality report Step 1 updated

## Step 1b: Edge Case Analysis
- [ ] Diff generated via `git diff HEAD~1 -- '*.ts' '*.tsx' '*.js' '*.jsx'` and passed as `step_1b_diff`
- [ ] First run: edge-case-hunter subagent spawned with diff and project-specific boundary checks from CLAUDE.md
- [ ] Loop-back: TARGETED VERIFICATION subagent spawned (checks specific guards, runs tests)
- [ ] Subagent returned structured ---RESULTS--- block with `findings_json`
- [ ] step_1b_findings accumulator updated and appended to step_1_findings for downstream steps
- [ ] Fix subagent spawned if findings_count > 0 — implements guard + writes a unit test for each finding using the project's test framework
- [ ] Loop-back triggered if findings_count > 0 (max {{max_loopbacks_per_step}})
- [ ] HALT triggered if findings remain after max loop-backs
- [ ] Quality report Step 1b updated

## Step 2: QA Automation Test
- [ ] First run: subagent spawned with qa-automate workflow
- [ ] Subagent prompted to use the project's test stack as specified in CLAUDE.md
- [ ] Loop-back: TARGETED VERIFICATION subagent spawned (runs tests, not full QA workflow)
- [ ] Subagent returned structured ---RESULTS--- block
- [ ] Results parsed: tests generated, passing/failing counts, file paths
- [ ] Fix subagent spawned if tests_failing > 0 (before loop-back), runs tests as specified in CLAUDE.md
- [ ] Loop-back triggered if tests_failing > 0 (max {{max_loopbacks_per_step}})
- [ ] HALT triggered if tests still failing after max loop-backs
- [ ] Quality report Step 2 updated

## Step 3: Complementary Review
- [ ] Subagent spawned with CUSTOM business/functional prompt (NOT review-adversarial-general.xml)
- [ ] Prompt includes step_1_findings AND step_1b_findings so prior ground is NOT re-covered
- [ ] Review focuses on: business logic, functional AC verification, integration concerns, data flow edges, missing implied requirements (loading/empty states, keyboard nav, screen-reader announcements)
- [ ] Minimum 3 findings produced
- [ ] Subagent returned structured ---RESULTS--- block
- [ ] Results parsed: issue counts by severity, findings summary
- [ ] Fix subagent spawned if HIGH severity issues found (before loop-back); runs tests as specified in CLAUDE.md
- [ ] Loop-back triggered if HIGH severity issues persist (max {{max_loopbacks_per_step}})
- [ ] HALT triggered if HIGH severity persists after max loop-backs
- [ ] Quality report Step 3 updated

## Step 4: Test Quality & Traceability (Parallel)
- [ ] Both 4a and 4b subagents spawned CONCURRENTLY
- [ ] On loop-back, only the failing sub-step re-runs (passing sub-step skipped)

### Step 4a: Test Review (TEA)
- [ ] First run: subagent spawned with testarch-test-review workflow; context includes project test stack from CLAUDE.md
- [ ] Loop-back: TARGETED VERIFICATION subagent spawned (checks specific weaknesses, not full review); runs tests
- [ ] Results parsed: quality score, strengths, weaknesses
- [ ] Fix subagent spawned if score < 70 (before loop-back); runs tests
- [ ] Loop-back triggered if score still < 70 (max {{max_loopbacks_per_step}})
- [ ] HALT triggered if score remains < 70 after max loop-backs

### Step 4b: Traceability Check (TEA)
- [ ] First run: subagent spawned with testarch-trace workflow
- [ ] Loop-back: TARGETED VERIFICATION subagent spawned (checks specific gaps, not full trace); runs tests
- [ ] Results parsed: gate decision, coverage, gaps
- [ ] Fix subagent spawned if gate == FAIL (before loop-back); writes tests following patterns from CLAUDE.md
- [ ] Loop-back triggered if gate still FAIL (max {{max_loopbacks_per_step}})
- [ ] HALT triggered if FAIL persists after max loop-backs

- [ ] Quality report Step 4 updated with both 4a and 4b results

## Step 5: Documentation
- [ ] docs_mode checked from customize.toml — step skipped if set to "skip"
- [ ] Subagent spawned with technical writer instructions targeting `{{docs_site_content_path}}`
- [ ] If docs_site_content_path is configured: subagent verifies navigation config entries and updates index pages with stubs for new components/hooks/utilities/routes
- [ ] Runs BEFORE CI step (so doc changes are included in commit)
- [ ] Subagent returned structured ---RESULTS--- block
- [ ] Results parsed: documents updated/created, index_pages_stubbed, api_entries_documented
- [ ] FAIL trigger if docs_site_content_path is configured but no docs-site pages were written; FAIL trigger if index pages were not stubbed when new APIs were added
- [ ] docs_generate_command run if configured in customize.toml
- [ ] Story page existence verified (warning, not fail, if generator does not yet support the epic)
- [ ] Docs-site build runs cleanly (if applicable)
- [ ] Quality report Step 5 updated with docs_status

## Step 6: CI Verification & Sprint Status
- [ ] Executed directly in orchestrator (not subagent)
- [ ] Inline sprint status check runs BEFORE commit: `{{sprint_status_file}}` read
- [ ] Story {{story_id}} confirmed marked as done (or already was)
- [ ] Pre-commit checks run as specified in CLAUDE.md (typically lint, typecheck, and project-specific extraction/generation commands)
- [ ] All files staged (code, tests, docs, sprint status) and committed in ONE commit
- [ ] Pushed to remote (single push -> single CI run)
- [ ] CI pipeline polled via `gh run list --branch main` until completion
- [ ] CI pass/fail status captured
- [ ] Loop-back triggered if CI failed (max {{max_loopbacks_per_step}})
- [ ] CI failure logs read via `gh run view --log-failed` and issues fixed on loop-back
- [ ] HALT triggered if CI still fails after max loop-backs
- [ ] Quality report Step 6 updated with CI results AND sprint status

## Step 7: Finalize Report
- [ ] Summary table completed with all step statuses, loop-back counts, and inline-fix counts
- [ ] Summary table includes sub-rows for 4a and 4b
- [ ] Total loop-backs calculated: step_1 + step_1b + step_2 + step_3 + step_4a + step_4b + step_6
- [ ] Total inline fixes accumulated from steps 1, 1b, 3, 4a
- [ ] Overall gate status determined (PASSED / PASSED WITH CONCERNS / HALTED)
- [ ] Lessons and observations auto-generated
- [ ] Quality report saved to `{{quality_report_location}}/story-{{story_id}}-quality-report.md`
- [ ] Report committed with `[skip ci]` in message (docs-only, no CI trigger)
- [ ] Report pushed (does NOT trigger a second CI run)
- [ ] Final summary presented to user
- [ ] Next action identified (next story or retrospective)
