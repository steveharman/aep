#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Merge AEP module configuration into _bmad/config.toml and config.user.toml.

Reads a module.yaml definition and a JSON answers file, then writes or updates
the shared config.toml ([modules.aep] section) and config.user.toml (user
settings). Uses text-based section editing to preserve existing content and
comments — only the [modules.aep] section is removed and re-appended.

Legacy migration: when --legacy-dir is provided, reads old per-module YAML
config files from {legacy-dir}/{module-code}/config.yaml and
{legacy-dir}/core/config.yaml. Matching values serve as fallback defaults
(answers override them). After a successful merge, the legacy config.yaml
files are deleted. Only the current module and core directories are touched.

Exit codes: 0=success, 1=validation error, 2=runtime error
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: pyyaml is required (PEP 723 dependency)", file=sys.stderr)
    sys.exit(2)


# Core keys that live under [core] in config.toml
_CORE_KEYS = frozenset(
    {"user_name", "communication_language", "document_output_language", "output_folder"}
)

# Core keys that belong exclusively in config.user.toml
_CORE_USER_KEYS = ("user_name", "communication_language")

# Metadata keys written under [modules.<code>] alongside variable values
_META_KEYS = ("name", "description")
_META_KEY_VERSION = "version"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge AEP module config into _bmad/config.toml with text-based editing."
    )
    parser.add_argument(
        "--config-path",
        required=True,
        help="Path to the target _bmad/config.toml file",
    )
    parser.add_argument(
        "--module-yaml",
        required=True,
        help="Path to the module.yaml definition file",
    )
    parser.add_argument(
        "--answers",
        required=True,
        help="Path to JSON file with collected answers",
    )
    parser.add_argument(
        "--user-config-path",
        required=True,
        help="Path to the target _bmad/config.user.toml file",
    )
    parser.add_argument(
        "--legacy-dir",
        help="Path to _bmad/ directory to check for legacy per-module YAML config files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress to stderr",
    )
    return parser.parse_args()


# ── TOML helpers ──────────────────────────────────────────────────────────

# Minimal TOML parser for config.toml — handles sections with key-value pairs.
# Does not handle nested inline tables, arrays of tables, or multiline strings.
# Sufficient for bmad v6 config.toml / config.user.toml format.

_SECTION_RE = re.compile(r"^\[([^\]]+)\]")
_KV_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*(.+)")


def _parse_toml_value(raw: str) -> object:
    """Parse a single TOML value into a Python object."""
    raw = raw.strip()
    # Boolean
    if raw == "true":
        return True
    if raw == "false":
        return False
    # Integer
    try:
        return int(raw)
    except ValueError:
        pass
    # Float
    try:
        return float(raw)
    except ValueError:
        pass
    # Basic string (double-quoted)
    if raw.startswith('"') and raw.endswith('"'):
        inner = raw[1:-1]
        # Unescape common escapes
        inner = inner.replace('\\"', '"')
        inner = inner.replace('\\\\', '\\')
        inner = inner.replace('\\n', '\n')
        return inner
    # Bare string (no quotes) — TOML allows bare keys but values need quotes
    # Treat as raw string
    return raw


def parse_toml(text: str) -> dict:
    """Parse TOML text into {section: {key: value}} dict.

    Returns a flat dict mapping section names to their key-value pairs.
    Top-level keys (before any section) go under the empty string key ''.
    """
    result = {}
    current_section = ""
    for line in text.splitlines():
        stripped = line.strip()
        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue
        # Section header
        m = _SECTION_RE.match(stripped)
        if m:
            current_section = m.group(1)
            if current_section not in result:
                result[current_section] = {}
            continue
        # Key-value pair
        m = _KV_RE.match(stripped)
        if m:
            key = m.group(1)
            value = _parse_toml_value(m.group(2))
            if current_section not in result:
                result[current_section] = {}
            result[current_section][key] = value
    return result


def section_exists(text: str, section_name: str) -> bool:
    """Check if a TOML section header exists in the text."""
    header = f"[{section_name}]"
    for line in text.splitlines():
        if line.strip() == header:
            return True
    return False


def get_section_keys(text: str, section_name: str) -> dict:
    """Get key-value pairs from a specific TOML section."""
    parsed = parse_toml(text)
    return parsed.get(section_name, {})


def remove_section(text: str, section_name: str) -> str:
    """Remove a TOML section and all its key-value lines from text.

    Finds `[section_name]` and deletes through the next section header or EOF.
    Only matches exact section headers (e.g. `[modules.aep]`), not subsections
    like `[modules.aep.foo]`.
    """
    header = f"[{section_name}]"
    lines = text.splitlines(keepends=True)
    result = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == header:
            in_section = True
            continue
        if in_section:
            # Stop at next section header or end of sections we're removing
            if stripped.startswith("[") and stripped.endswith("]"):
                in_section = False
                result.append(line)
            # else: skip lines inside the removed section
        else:
            result.append(line)
    return "".join(result)


def remove_user_key(text: str, key: str) -> str:
    """Remove all lines setting a given key from TOML text."""
    lines = text.splitlines(keepends=True)
    prefix = f"{key} = "
    result = [line for line in lines if not line.strip().startswith(prefix)]
    return "".join(result)


def format_toml_value(value) -> str:
    """Format a Python value for TOML output."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # Escape backslashes and double quotes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'


def build_section_lines(section_name: str, data: dict) -> list[str]:
    """Build TOML lines for a section header + key-value pairs."""
    lines = [f"[{section_name}]\n"]
    for key, value in data.items():
        if value is not None:
            lines.append(f"{key} = {format_toml_value(value)}\n")
    return lines


def append_section(text: str, section_name: str, data: dict) -> str:
    """Append a TOML section to the end of text.

    Ensures exactly one blank line before the new section if the text doesn't
    already end with a blank line.
    """
    if not data:
        return text
    new_lines = build_section_lines(section_name, data)
    if text and not text.endswith("\n\n"):
        if text.endswith("\n"):
            text += "\n"
        else:
            text += "\n\n"
    return text + "".join(new_lines)


def write_text(path: str, text: str) -> None:
    """Write text to file, creating parent directories as needed."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)


# ── Legacy YAML config migration ─────────────────────────────────────────

def load_yaml_file(path: str) -> dict:
    """Load a YAML file, returning empty dict if file doesn't exist."""
    file_path = Path(path)
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f)
    return content if content else {}


def load_legacy_values(
    legacy_dir: str, module_code: str, module_yaml: dict, verbose: bool = False
) -> tuple[dict, dict, list]:
    """Read legacy per-module YAML config files.

    Reads {legacy_dir}/core/config.yaml and {legacy_dir}/{module_code}/config.yaml.
    Only returns values whose keys match the current schema.

    Returns:
        (legacy_core, legacy_module, files_found)
    """
    legacy_core: dict = {}
    legacy_module: dict = {}
    files_found: list = []

    core_path = Path(legacy_dir) / "core" / "config.yaml"
    if core_path.exists():
        core_data = load_yaml_file(str(core_path))
        files_found.append(str(core_path))
        for k, v in core_data.items():
            if k in _CORE_KEYS:
                legacy_core[k] = v
        if verbose:
            print(f"Legacy core config: {list(legacy_core.keys())}", file=sys.stderr)

    mod_path = Path(legacy_dir) / module_code / "config.yaml"
    if mod_path.exists():
        mod_data = load_yaml_file(str(mod_path))
        files_found.append(str(mod_path))
        for k, v in mod_data.items():
            if k in _CORE_KEYS:
                if k not in legacy_core:
                    legacy_core[k] = v
            elif k in module_yaml and isinstance(module_yaml[k], dict):
                legacy_module[k] = v
        if verbose:
            print(f"Legacy module config: {list(legacy_module.keys())}", file=sys.stderr)

    return legacy_core, legacy_module, files_found


def apply_legacy_defaults(answers: dict, legacy_core: dict, legacy_module: dict) -> dict:
    """Apply legacy values as fallback defaults under the answers.

    Legacy values fill in any key not already present in answers.
    Explicit answers always win.
    """
    merged = dict(answers)
    if legacy_core:
        core = merged.get("core", {})
        filled = dict(legacy_core)
        filled.update(core)
        merged["core"] = filled
    if legacy_module:
        mod = merged.get("module", {})
        filled = dict(legacy_module)
        filled.update(mod)
        merged["module"] = filled
    return merged


def cleanup_legacy_configs(
    legacy_dir: str, module_code: str, verbose: bool = False
) -> list:
    """Delete legacy per-module config.yaml files for this module and core only."""
    deleted = []
    for subdir in (module_code, "core"):
        legacy_path = Path(legacy_dir) / subdir / "config.yaml"
        if legacy_path.exists():
            if verbose:
                print(f"Deleting legacy config: {legacy_path}", file=sys.stderr)
            legacy_path.unlink()
            deleted.append(str(legacy_path))
    return deleted


# ── Metadata extraction ───────────────────────────────────────────────────

def extract_module_metadata(module_yaml: dict) -> dict:
    """Extract non-variable metadata fields from module.yaml for the TOML section."""
    meta = {}
    for k in _META_KEYS:
        if k in module_yaml:
            meta[k] = module_yaml[k]
    meta[_META_KEY_VERSION] = module_yaml.get("version")
    return meta


def apply_result_templates(
    module_yaml: dict, module_answers: dict, verbose: bool = False
) -> dict:
    """Apply result templates from module.yaml to transform raw answer values."""
    transformed = {}
    for key, value in module_answers.items():
        var_def = module_yaml.get(key)
        if (
            isinstance(var_def, dict)
            and "result_template" in var_def
            and "{project-root}" not in str(value)
        ):
            template = var_def["result_template"]
            transformed[key] = template.replace("{value}", str(value))
            if verbose:
                print(
                    f"Applied result_template for '{key}': {value} → {transformed[key]}",
                    file=sys.stderr,
                )
        else:
            transformed[key] = value
    return transformed


# ── User settings extraction ──────────────────────────────────────────────

def extract_user_settings(module_yaml: dict, answers: dict) -> dict:
    """Collect settings that belong in config.user.toml.

    Includes user_name and communication_language from core answers, plus any
    module variable whose definition contains user_setting: true.
    """
    user_settings = {}
    core_answers = answers.get("core", {})
    for key in _CORE_USER_KEYS:
        if key in core_answers and core_answers[key]:
            user_settings[key] = core_answers[key]

    module_answers = answers.get("module", {})
    for var_name, var_def in module_yaml.items():
        if isinstance(var_def, dict) and var_def.get("user_setting") is True:
            if var_name in module_answers and module_answers[var_name]:
                user_settings[var_name] = module_answers[var_name]

    return user_settings


# ── JSON helper ────────────────────────────────────────────────────────────

def load_json_file(path: str) -> dict:
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Load inputs
    module_yaml = load_yaml_file(args.module_yaml)
    if not module_yaml:
        print(f"Error: Could not load module.yaml from {args.module_yaml}", file=sys.stderr)
        sys.exit(1)

    # Answers are always JSON (written by the skill as a temp JSON file)
    answers_path = Path(args.answers)
    if answers_path.suffix in (".yaml", ".yml"):
        answers = load_yaml_file(args.answers)
    else:
        answers = load_json_file(args.answers)
    module_code = module_yaml.get("code")
    if not module_code:
        print("Error: module.yaml must have a 'code' field", file=sys.stderr)
        sys.exit(1)

    section_name = f"modules.{module_code}"

    if args.verbose:
        print(f"Module code: {module_code}", file=sys.stderr)
        print(f"Config section: [{section_name}]", file=sys.stderr)
        print(f"Config path: {args.config_path}", file=sys.stderr)
        print(f"Answers keys: core={list(answers.get('core', {}).keys())}, module={list(answers.get('module', {}).keys())}", file=sys.stderr)

    # ── Legacy migration: read old per-module YAML configs ──────────────
    legacy_files_found = []
    if args.legacy_dir:
        legacy_core, legacy_module, legacy_files_found = load_legacy_values(
            args.legacy_dir, module_code, module_yaml, args.verbose
        )
        if legacy_core or legacy_module:
            answers = apply_legacy_defaults(answers, legacy_core, legacy_module)
            if args.verbose:
                print("Applied legacy values as fallback defaults", file=sys.stderr)

    # ── Build module section data ───────────────────────────────────────
    module_section = extract_module_metadata(module_yaml)
    module_answers = apply_result_templates(
        module_yaml, answers.get("module", {}), args.verbose
    )
    module_section.update(module_answers)

    if args.verbose:
        print(f"Module section keys: {list(module_section.keys())}", file=sys.stderr)

    # ── Update config.toml ─────────────────────────────────────────────
    config_text = ""
    config_path = Path(args.config_path)
    if config_path.exists():
        config_text = config_path.read_text(encoding="utf-8")

    # Anti-zombie: remove existing [modules.<code>] section
    config_text = remove_section(config_text, section_name)

    # Append new module section
    config_text = append_section(config_text, section_name, module_section)

    # Ensure [core] exists with defaults, but only if core is completely missing
    # (never overwrite an existing [core] section — BMad Core owns it)
    core_answers = answers.get("core", {})
    if core_answers and not section_exists(config_text, "core"):
        shared_core = {k: v for k, v in core_answers.items() if k not in _CORE_USER_KEYS}
        if shared_core:
            config_text = append_section(config_text, "core", shared_core)
            if args.verbose:
                print("Core section missing — added defaults", file=sys.stderr)

    write_text(str(config_path), config_text)
    if args.verbose:
        print(f"Wrote config to {config_path}", file=sys.stderr)

    # ── Update config.user.toml ────────────────────────────────────────
    user_settings = extract_user_settings(module_yaml, answers)
    user_path = Path(args.user_config_path)
    user_text = ""
    if user_path.exists():
        user_text = user_path.read_text(encoding="utf-8")

    if user_settings:
        # Core user keys (user_name, communication_language) go under [core] if
        # it doesn't already exist in user config. If [core] is present, BMad Core
        # already set these — don't overwrite. Module user settings (if any) are
        # appended at top level.
        core_user = {k: v for k, v in user_settings.items() if k in _CORE_USER_KEYS}
        module_user = {k: v for k, v in user_settings.items() if k not in _CORE_USER_KEYS}

        if core_user and not section_exists(user_text, "core"):
            user_text = append_section(user_text, "core", core_user)
        else:
            # Strip these from result since we didn't actually write them
            user_settings = {k: v for k, v in user_settings.items() if k in module_user}

        if module_user:
            for key in module_user:
                user_text = remove_user_key(user_text, key)
            if user_text and not user_text.endswith("\n"):
                user_text += "\n"
            for key, value in module_user.items():
                user_text += f"{key} = {format_toml_value(value)}\n"

        write_text(str(user_path), user_text)
        if args.verbose:
            print(f"Wrote user config to {user_path}", file=sys.stderr)

    # ── Legacy cleanup ─────────────────────────────────────────────────
    legacy_deleted = []
    if args.legacy_dir:
        legacy_deleted = cleanup_legacy_configs(args.legacy_dir, module_code, args.verbose)

    # ── Output result ──────────────────────────────────────────────────
    result = {
        "status": "success",
        "config_path": str(config_path.resolve()),
        "user_config_path": str(user_path.resolve()),
        "module_code": module_code,
        "core_updated": bool(answers.get("core")),
        "module_keys": list(module_section.keys()),
        "user_keys": list(user_settings.keys()),
        "legacy_configs_found": legacy_files_found,
        "legacy_configs_deleted": legacy_deleted,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
