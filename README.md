# Autonomous Epic Pipeline (AEP)

Autonomous implementation pipeline that takes epics from backlog to done -- orchestrating story creation, implementation, multi-reviewer quality gates, optional second-opinion reviews, documentation, CI verification, and sprint tracking.

AEP discovers project context from your `CLAUDE.md` and architecture docs at runtime, so it works with **any project** without modification.

## Skills

| Skill | Command | Description |
|-------|---------|-------------|
| **aep-implement-epic** | `/aep-implement-epic <epic-ids>` | Run the full pipeline for one or more epics (e.g. `1` or `1,2,3`) |
| **aep-implement-story** | `/aep-implement-story [story-id]` | Run the 12-step story pipeline: create, implement, verify, review, fix, document, commit, quality report |
| **aep-post-story-quality** | `/aep-post-story-quality [story-id]` | Run a 7-step quality gate on a manually-implemented story |
| **aep-setup** | `/aep-setup` | Configure AEP in your project (run once after install) |

## Installation

### Using the Vercel Skills CLI (recommended)

```bash
# Install all skills to Claude Code
npx skills add streeyt/aep --agent claude-code

# Install all skills to all supported agents
npx skills add streeyt/aep --all

# List available skills first
npx skills add streeyt/aep --list
```

### Manual installation

Copy the skill folders from `skills/` into your project's `.claude/skills/` directory:

```bash
git clone git@github.com:streeyt/aep.git /tmp/aep
cp -r /tmp/aep/skills/aep-* .claude/skills/
```

### After installation

Run the setup skill to configure AEP for your project:

```
/aep-setup
```

This checks prerequisites, collects configuration (artifact paths, etc.), and registers capabilities in the BMad help system.

## Prerequisites

AEP depends on the [BMad framework](https://github.com/bmad-artifacts/bmad-agent) being installed in your project with the following modules:

| Module | Why |
|--------|-----|
| **BMad Core** | Review task templates (adversarial, edge-case) |
| **BMM** (Build, Manage, Monitor) | Stock skills: create-story, dev-story, code-review, tech-writer, agent-dev |
| **TEA** (Test Architecture Enterprise) | Test review and traceability workflows |

Additional requirements:

- **`CLAUDE.md`** at project root with your project's rules, toolchain, and conventions
- **Planning artifacts** (architecture.md, epics.md) in your configured location
- **Sprint status YAML** with story entries
- **GitHub CLI (`gh`)** for CI verification
- **Deepseek API key** (optional) for second-opinion reviews -- configurable via `customize.toml`
- **[Nextra](https://nextra.site)** docs site (optional) -- required if `docs_site_content_path` is configured. Set `docs_mode = "skip"` in `customize.toml` to disable documentation entirely

## How it works

### Dynamic project context

Unlike hardcoded pipelines, AEP reads your project's `CLAUDE.md` and architecture docs at runtime to understand your tech stack, conventions, and review rules. Sub-agent prompts receive this context dynamically, so the same pipeline works for a Next.js dashboard, a Go microservice, or a Python ML project.

### Story pipeline (12 steps)

1. **Create story spec** -- acceptance criteria, implementation constraints, tasks
2. **Implement** -- all tasks with tests, red-green-refactor
3. **Local verification** -- tests + type check before burning reviewer tokens
4. **Parallel review** -- 3 simultaneous reviewers (adversarial, edge-case, test quality)
5. **Batch fix** -- all HIGH/MEDIUM findings in a single pass
6. **Second-opinion review** -- optional independent review via alternative LLM
7. **Second-opinion fix** -- fix any findings from the second opinion
8. **Complementary review** -- business logic and functional review
9. **Documentation** -- API docs and docs-site pages
10. **Commit and push** -- staged commit with proper message
11. **CI verification** -- poll CI, auto-fix failures
12. **Quality report** -- consolidated report, mark story done

### Epic pipeline

Loops the story pipeline across all pending stories in one or more epics. Each story runs in a fresh `claude -p` subprocess for context isolation. Triple-signal verification (sprint status + quality report + CI) confirms completion. Idempotent -- done stories are skipped on re-run.

## Configuration

### customize.toml

Each skill has tuneable parameters via `customize.toml`. Override without editing the skill files by creating:

- **Team overrides:** `_bmad/custom/aep-implement-story.toml`
- **Personal overrides:** `_bmad/custom/aep-implement-story.user.toml`

Key settings for `aep-implement-story`:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_fix_loops` | 3 | Max fix iterations per step |
| `second_opinion_provider` | `"deepseek"` | Provider for second-opinion review (`"deepseek"` or `"none"`) |
| `second_opinion_required` | `true` | Halt if second opinion unavailable? |
| `docs_mode` | `"auto"` | `"auto"` or `"skip"` |
| `docs_site_content_path` | `""` | Path for docs-site pages (blank = skip) |
| `docs_generate_command` | `""` | Command to regenerate story pages (blank = skip) |

## License

MIT
