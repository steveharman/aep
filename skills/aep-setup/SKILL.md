---
name: "aep-setup"
description: Sets up Autonomous Epic Pipeline module in a project. Use when the user requests to 'install aep module', 'configure Autonomous Epic Pipeline', or 'setup Autonomous Epic Pipeline'.
---

# Module Setup

## Overview

Installs and configures a BMad module into a project. Module identity (name, code, version) comes from `./assets/module.yaml`. Collects user preferences and writes them to three files:

- **`{project-root}/_bmad/config.yaml`** — shared project config: core settings at root (e.g. `output_folder`, `document_output_language`) plus a section per module with metadata and module-specific values. User-only keys (`user_name`, `communication_language`) are **never** written here.
- **`{project-root}/_bmad/config.user.yaml`** — personal settings intended to be gitignored: `user_name`, `communication_language`, and any module variable marked `user_setting: true` in `./assets/module.yaml`. These values live exclusively here.
- **`{project-root}/_bmad/module-help.csv`** — registers module capabilities for the help system.

Both config scripts use an anti-zombie pattern — existing entries for this module are removed before writing fresh ones, so stale values never persist.

`{project-root}` is a **literal token** in config values — never substitute it with an actual path. It signals to the consuming LLM that the value is relative to the project root, not the skill root.

## On Activation

1. Read `./assets/module.yaml` for module metadata and variable definitions (the `code` field is the module identifier)
2. Check if `{project-root}/_bmad/config.yaml` exists — if a section matching the module's code is already present, inform the user this is an update
3. Check for per-module configuration at `{project-root}/_bmad/aep/config.yaml` and `{project-root}/_bmad/core/config.yaml`. If either file exists:
   - If `{project-root}/_bmad/config.yaml` does **not** yet have a section for this module: this is a **fresh install**. Inform the user that installer config was detected and values will be consolidated into the new format.
   - If `{project-root}/_bmad/config.yaml` **already** has a section for this module: this is a **legacy migration**. Inform the user that legacy per-module config was found alongside existing config, and legacy values will be used as fallback defaults.
   - In both cases, per-module config files and directories will be cleaned up after setup.

If the user provides arguments (e.g. `accept all defaults`, `--headless`, or inline values like `user name is BMad, I speak Swahili`), map any provided values to config keys, use defaults for the rest, and skip interactive prompting. Still display the full confirmation summary at the end.

## Check Prerequisites

Before collecting configuration, verify that required modules and tools are available. These checks are warnings, not blockers — the user may plan to install missing dependencies later.

**Required BMad modules** — check `{project-root}/_bmad/config.yaml` for sections matching each module code:

| Module | Code | Reason |
|--------|------|--------|
| BMad Core | `core` | Review task templates (adversarial, edge-case) |
| BMM | `bmm` | Stock skills (create-story, dev-story, code-review, tech-writer, agent-dev) |
| TEA | `tea` | Test review and traceability workflows |

For each missing module, warn: "Module `{code}` not found in config. AEP depends on it for {reason}. Install it before running the pipeline."

**Required CLI tools** — check for `gh` (GitHub CLI): run `gh --version`. If not found, warn: "`gh` CLI not found. AEP uses it for CI verification. Install from https://cli.github.com/"

**Required project files** — check for `{project-root}/CLAUDE.md`. If not found, warn: "No CLAUDE.md found at project root. AEP reads project rules from this file at runtime. Create one with your project's toolchain, conventions, and coding standards."

**BMM config fallback** — if the `bmm` section exists in `{project-root}/_bmad/config.yaml`, read its `planning_artifacts` and `implementation_artifacts` values. Use these as defaults for the AEP config questions instead of the module.yaml defaults. Inform the user: "BMM module detected — using its artifact paths as defaults."

**Second-opinion API key** — if `second_opinion_provider` is not `"none"` (check existing config or the default `"deepseek"`), look for the key named `deepseek-api-key` (or the value of `second_opinion_api_key_source` if customized) in `{project-root}/.env.keys`. If not found, warn: "No Deepseek API key found in `.env.keys`. Second-opinion reviews are enabled by default and require this key — the pipeline will halt at Step 5b without it. You can add `deepseek-api-key=<your-key>` to `.env.keys` now, or choose 'none' for the second-opinion question below to disable this feature."

**Nextra docs site** — if the user provides a non-empty `docs_site_content_path`, check for `nextra` in the nearest `package.json` relative to that path. If not found, warn: "Nextra not found near '{{docs_site_content_path}}'. AEP's documentation step generates .mdx pages for Nextra (https://nextra.site). Install Nextra before running the pipeline, or set `docs_mode` to 'skip'."

## Collect Configuration

Ask the user for values. Show defaults in brackets. Present all values together so the user can respond once with only the values they want to change (e.g. "change language to Swahili, rest are fine"). Never tell the user to "press enter" or "leave blank" — in a chat interface they must type something to respond.

**Default priority** (highest wins): existing new config values > legacy config values > `./assets/module.yaml` defaults. When legacy configs exist, read them and use matching values as defaults instead of `module.yaml` defaults. Only keys that match the current schema are carried forward — changed or removed keys are ignored.

**Core config** (only if no core keys exist yet): `user_name` (default: BMad), `communication_language` and `document_output_language` (default: English — ask as a single language question, both keys get the same answer), `output_folder` (default: `{project-root}/_bmad-output`). Of these, `user_name` and `communication_language` are written exclusively to `config.user.yaml`. The rest go to `config.yaml` at root and are shared across all modules.

**Module config**: Read each variable in `./assets/module.yaml` that has a `prompt` field. Ask using that prompt with its default value (or legacy value if available).

## Write Files

Write a temp JSON file with the collected answers structured as `{"core": {...}, "module": {...}}` (omit `core` if it already exists). Then run both scripts — they can run in parallel since they write to different files:

```bash
python3 ./scripts/merge-config.py --config-path "{project-root}/_bmad/config.yaml" --user-config-path "{project-root}/_bmad/config.user.yaml" --module-yaml ./assets/module.yaml --answers {temp-file} --legacy-dir "{project-root}/_bmad"
python3 ./scripts/merge-help-csv.py --target "{project-root}/_bmad/module-help.csv" --source ./assets/module-help.csv --legacy-dir "{project-root}/_bmad" --module-code aep
```

Both scripts output JSON to stdout with results. If either exits non-zero, surface the error and stop. The scripts automatically read legacy config values as fallback defaults, then delete the legacy files after a successful merge. Check `legacy_configs_deleted` and `legacy_csvs_deleted` in the output to confirm cleanup.

Run `./scripts/merge-config.py --help` or `./scripts/merge-help-csv.py --help` for full usage.

## Write Customize Overrides

After writing config, check if any collected answers have `customize_toml: true` in `./assets/module.yaml` and differ from the skill's built-in `customize.toml` defaults. If so, write override files:

For each unique target in `customize_targets`, create `{project-root}/_bmad/custom/<target>.toml` (or update it if it already exists). Write collected values under the `[workflow]` section. Only write keys whose values differ from the skill's default `customize.toml`.

Example — if the user set `docs_site_content_path = "apps/docs-site/content"` and `docs_mode = "auto"` (which is the default), only `docs_site_content_path` would be written:

```toml
[workflow]
docs_site_content_path = "apps/docs-site/content"
```

**Provider/required coupling:** if `second_opinion_provider` is `"none"`, always write `second_opinion_required = false` alongside it in the same override file, regardless of what the user said or the default. This prevents a contradictory state where the provider is disabled but the pipeline treats it as mandatory and halts.

If all values match defaults, skip creating the override file.

## Create Output Directories

After writing config, create any output directories that were configured. For filesystem operations only (such as creating directories), resolve the `{project-root}` token to the actual project root and create each path-type value from `config.yaml` that does not yet exist — this includes `output_folder` and any module variable whose value starts with `{project-root}/`. The paths stored in the config files must continue to use the literal `{project-root}` token; only the directories on disk should use the resolved paths. Use `mkdir -p` or equivalent to create the full path.

## Cleanup Legacy Directories

AEP is a standalone expansion module — it typically has no legacy installer directories to clean up. Only run cleanup if per-module config files were found during activation (e.g., `{project-root}/_bmad/aep/config.yaml` from a prior install):

```bash
python3 ./scripts/cleanup-legacy.py --bmad-dir "{project-root}/_bmad" --module-code aep --skills-dir "{project-root}/.claude/skills"
```

The script is idempotent — missing directories are not errors. If the script exits non-zero, surface the error and stop.

Check `directories_removed` and `files_removed_count` in the JSON output for the confirmation step. Run `./scripts/cleanup-legacy.py --help` for full usage.

## Confirm

Use the script JSON output to display what was written — config values set (written to `config.yaml` at root for core, module section for module values), user settings written to `config.user.yaml` (`user_keys` in result), help entries added, fresh install vs update. If legacy files were deleted, mention the migration. If legacy directories were removed, report the count and list (e.g. "Cleaned up 106 installer package files from bmb/, core/, \_config/ — skills are installed at .claude/skills/"). Then display the `module_greeting` from `./assets/module.yaml` to the user.

## Outcome

Once the user's `user_name` and `communication_language` are known (from collected input, arguments, or existing config), use them consistently for the remainder of the session: address the user by their configured name and communicate in their configured `communication_language`.
