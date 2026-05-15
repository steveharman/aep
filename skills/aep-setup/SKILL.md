---
name: "aep-setup"
description: Sets up Autonomous Epic Pipeline module in a project. Use when the user requests to 'install aep module', 'configure Autonomous Epic Pipeline', or 'setup Autonomous Epic Pipeline'.
---

# Module Setup

## Overview

Installs and configures a BMad module into a project. Module identity (name, code, version) comes from `./assets/module.yaml`. Collects user preferences and writes them to three files:

- **`{project-root}/_bmad/config.toml`** — shared project config: `[core]` section for project-wide settings (e.g. `output_folder`, `document_output_language`) plus a `[modules.<code>]` section per module with metadata and module-specific values. User-only keys (`user_name`, `communication_language`) are **never** written here.
- **`{project-root}/_bmad/config.user.toml`** — personal settings intended to be gitignored: `user_name`, `communication_language`, and any module variable marked `user_setting: true` in `./assets/module.yaml`. These values live exclusively here.
- **`{project-root}/_bmad/_config/bmad-help.csv`** — registers module capabilities for the help system.

Both config scripts use an anti-zombie pattern — existing entries for this module are removed before writing fresh ones, so stale values never persist.

`{project-root}` is a **literal token** in config values — never substitute it with an actual path. It signals to the consuming LLM that the value is relative to the project root, not the skill root.

## On Activation

1. Read `./assets/module.yaml` for module metadata and variable definitions (the `code` field is the module identifier)
2. Check if `{project-root}/_bmad/config.toml` exists — if it contains a `[modules.<code>]` section for this module, inform the user this is an update
3. Check for legacy per-module configuration at `{project-root}/_bmad/aep/config.yaml` and `{project-root}/_bmad/core/config.yaml` (older bmad format). If either file exists:
   - If `{project-root}/_bmad/config.toml` does **not** yet have a `[modules.aep]` section: this is a **fresh install**. Inform the user that legacy installer config was detected and values will be consolidated into the new TOML format.
   - If `{project-root}/_bmad/config.toml` **already** has a `[modules.aep]` section: this is a **legacy migration**. Inform the user that legacy per-module config was found alongside existing config, and legacy values will be used as fallback defaults.
   - In both cases, legacy per-module config files and directories will be cleaned up after setup.

If the user provides arguments (e.g. `accept all defaults`, `--headless`, or inline values like `second opinion none, docs skip`), map any provided values to config keys, use defaults for the rest, and skip interactive prompting. Still display the full confirmation summary at the end.

## Check Prerequisites

Before collecting configuration, verify that required modules and tools are available. These checks are warnings, not blockers — the user may plan to install missing dependencies later.

**Required BMad modules** — check `{project-root}/_bmad/config.toml` for `[modules.<code>]` sections matching each module code:

| Module | Code | Reason |
|--------|------|--------|
| BMad Core | `core` | Review task templates (adversarial, edge-case) |
| BMM | `bmm` | Stock skills (create-story, dev-story, code-review, tech-writer, agent-dev) |
| TEA | `tea` | Test review and traceability workflows |

For each missing module, warn: "Module `{code}` not found in config. AEP depends on it for {reason}. Install it before running the pipeline."

**Required CLI tools** — check for `gh` (GitHub CLI): run `gh --version`. If not found, warn: "`gh` CLI not found. AEP uses it for CI verification. Install from https://cli.github.com/"

**Required project files** — check for `{project-root}/CLAUDE.md`. If not found, warn: "No CLAUDE.md found at project root. AEP reads project rules from this file at runtime. Create one with your project's toolchain, conventions, and coding standards."

**BMM config fallback** — if the `bmm` module section exists in `{project-root}/_bmad/config.toml` (as `[modules.bmm]`), read its `planning_artifacts` and `implementation_artifacts` values. Use these as defaults for the AEP config questions instead of the module.yaml defaults. Inform the user: "BMM module detected — using its artifact paths as defaults."

**Second-opinion API key** — if `second_opinion_provider` is not `"none"` (check existing config or the default `"deepseek"`), look for the key named `deepseek-api-key` (or the value of `second_opinion_api_key_source` if customized) in `{project-root}/.env.keys`. If not found, warn: "No Deepseek API key found in `.env.keys`. Second-opinion reviews are enabled by default and require this key — the pipeline will halt at Step 5b without it. You can add `deepseek-api-key=<your-key>` to `.env.keys` now, or choose 'none' for the second-opinion question below to disable this feature."

**Nextra docs site** — if the user provides a non-empty `docs_site_content_path`, check for `nextra` in the nearest `package.json` relative to that path. If not found, warn: "Nextra not found near '{{docs_site_content_path}}'. AEP's documentation step generates .mdx pages for Nextra (https://nextra.site). Install Nextra before running the pipeline, or set `docs_mode` to 'skip'."

## Collect Configuration

Use the `AskUserQuestion` tool to present configuration choices as structured, interactive screens. The flow consists of up to 2 screens depending on user choices.

If the user provides arguments (e.g. `accept all defaults`, `--headless`, or inline values), skip interactive prompting — map provided values to config keys, use defaults for the rest.

**Default priority** (highest wins): existing new config values > legacy config values > `./assets/module.yaml` defaults. When legacy configs exist, read them and use matching values as defaults instead of `module.yaml` defaults. Only keys that match the current schema are carried forward — changed or removed keys are ignored.

**Core config** — `user_name`, `communication_language`, `document_output_language`, and `output_folder` are set by BMad Core during its install. Do not ask the user for these values. If core keys are missing from config (e.g. BMad Core was not yet installed), write defaults silently: `user_name = "BMad"`, `communication_language = "English"`, `document_output_language = "English"`, `output_folder = "{project-root}/_bmad-output"`.

### Screen 1 — Artifact paths and feature toggles

Present these three questions in a **single** `AskUserQuestion` call:

**Question 1 — Artifact paths** (header: `Artifacts`)
> "Use standard BMad artifact paths for planning and implementation documents?"

| Option | Description |
|--------|-------------|
| Standard BMad paths (Recommended) | `_bmad-output/planning-artifacts` and `_bmad-output/implementation-artifacts` — or BMM values if detected |
| Customize paths | You'll be asked for specific directory paths next |

If BMM config was detected in Prerequisites, show the BMM-resolved paths in the recommended option's description instead of the module.yaml defaults.

**Question 2 — Second opinion** (header: `2nd opinion`)
> "Enable second-opinion code reviews via an external LLM?"

| Option | Description |
|--------|-------------|
| DeepSeek (Recommended) | Uses DeepSeek V4 Pro for independent code review at Step 5b |
| None | Skip the second-opinion phase entirely |

**Question 3 — Documentation** (header: `Docs mode`)
> "Enable automatic documentation generation after each story?"

| Option | Description |
|--------|-------------|
| Auto (Recommended) | Generate documentation after each story implementation |
| Skip | Disable the documentation step entirely |

#### Screen 1 follow-ups

- **If "Customize paths"** was selected: ask for `planning_artifacts` and `implementation_artifacts` values in a conversational follow-up, showing the resolved defaults in brackets.
- **If "None"** was selected for second opinion: set `second_opinion_provider = "none"`.

### Screen 2 — Docs site configuration (conditional)

**Skip this screen entirely** if `docs_mode` was set to `"skip"` — set both `docs_site_content_path` and `docs_generate_command` to `""`.

Otherwise, present two questions in a **single** `AskUserQuestion` call:

**Question 1 — Docs site path** (header: `Docs path`)
> "Generate Nextra docs-site pages? Specify your content directory path."

| Option | Description |
|--------|-------------|
| No site integration | Only create standalone docs — no Nextra page generation |
| docs/content | Common Nextra content directory location |

The user can type a custom path via the auto-included "Other" option.

**Question 2 — Docs build command** (header: `Docs cmd`)
> "Run a command to regenerate docs pages after writing?"

| Option | Description |
|--------|-------------|
| No command | Pages are written directly — no build step needed |
| npm run docs:build | Common docs build command |

The user can type a custom command via "Other".

### Mapping answers to config keys

| Answer | Config key | Value |
|--------|-----------|-------|
| Standard BMad paths | `planning_artifacts` | resolved default |
| Standard BMad paths | `implementation_artifacts` | resolved default |
| Customize paths | both keys | user-provided values from follow-up |
| DeepSeek | `second_opinion_provider` | `"deepseek"` |
| None | `second_opinion_provider` | `"none"` |
| Auto | `docs_mode` | `"auto"` |
| Skip | `docs_mode` | `"skip"` |
| No site integration | `docs_site_content_path` | `""` |
| docs/content (or Other) | `docs_site_content_path` | selected or typed value |
| No command | `docs_generate_command` | `""` |
| npm run docs:build (or Other) | `docs_generate_command` | selected or typed value |

## Write Files

Write a temp JSON file with the collected answers structured as `{"core": {...}, "module": {...}}` (omit `core` if it already exists). Then run both scripts — they can run in parallel since they write to different files:

```bash
python3 ./scripts/merge-config.py --config-path "{project-root}/_bmad/config.toml" --user-config-path "{project-root}/_bmad/config.user.toml" --module-yaml ./assets/module.yaml --answers {temp-file} --legacy-dir "{project-root}/_bmad"
python3 ./scripts/merge-help-csv.py --target "{project-root}/_bmad/_config/bmad-help.csv" --source ./assets/module-help.csv --legacy-dir "{project-root}/_bmad" --module-code aep
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

After writing config, create any output directories that were configured. For filesystem operations only (such as creating directories), resolve the `{project-root}` token to the actual project root for each path-type value from `config.toml` — this includes `output_folder` and any module variable whose value starts with `{project-root}/`. The paths stored in the config files must continue to use the literal `{project-root}` token; only the directories on disk should use the resolved paths.

For each directory, check whether it already exists before creating it. Track two lists: **created** (directories that did not exist and were created via `mkdir -p`) and **already existed** (directories that were already present). Both lists are used in the confirmation step.

## Cleanup Legacy Directories

AEP is a standalone expansion module — it typically has no legacy installer directories to clean up. Only run cleanup if per-module config files were found during activation (e.g., `{project-root}/_bmad/aep/config.yaml` from a prior install):

```bash
python3 ./scripts/cleanup-legacy.py --bmad-dir "{project-root}/_bmad" --module-code aep --skills-dir "{project-root}/.claude/skills"
```

The script is idempotent — missing directories are not errors. If the script exits non-zero, surface the error and stop.

Check `directories_removed` and `files_removed_count` in the JSON output for the confirmation step. Run `./scripts/cleanup-legacy.py --help` for full usage.

## Confirm

Use the script JSON output to display what was written — config values set (written to `config.toml` under `[modules.aep]` for module values, `[core]` for core settings), user settings written to `config.user.toml` (`user_keys` in result), help entries added, fresh install vs update. If legacy files were deleted, mention the migration. If legacy directories were removed, report the count and list (e.g. "Cleaned up 106 installer package files from bmb/, core/, \_config/ — skills are installed at .claude/skills/"). For directories: only list directories that were newly created under "Directories created". If all directories already existed, say "Output directories already in place — no new directories created." Do not list pre-existing directories as created. Then display the `module_greeting` from `./assets/module.yaml` to the user.

## Outcome

Once the user's `user_name` and `communication_language` are known (from collected input, arguments, or existing config), use them consistently for the remainder of the session: address the user by their configured name and communicate in their configured `communication_language`.
