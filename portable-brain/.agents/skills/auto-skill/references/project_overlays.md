# Project skill overlays

Resolve a single canonical skill for the active project with `--project <root-or-slug> --skill <skill> --markdown`. Use `--workspaces "root1;root2"` when the host supplies multiple workspace paths. The resolver ignores Brain when exactly one registered non-Brain workspace is present. Ambiguous workspace lists require an explicit `--project`. Use `--list --json` for host startup and `--validate-all` to check live overlays across registered projects.

The project owns `.agents/skill_overlays/<skill>.md`. The YAML frontmatter requires `schema_version: 1`, `project`, and `skill`, with optional `settings` and `references`. The frontmatter and body are bounded, and the body is limited to 2,048 bytes. References are project-relative paths and must remain inside the project even when followed through a junction. The same rules apply to settings with type `path`.

Optional `.agents/project_profile.yaml` has `schema_version: 1`, `project`, and `settings`. It provides shared typed values. The resolver projects only settings supported by the selected skill and then applies overlay settings over those values. Setting names and types come from [overlay_schemas.json](overlay_schemas.json). A `verify_cmd` value is a command identifier to look up in project documentation. It never executes as a shell command. Project rules and authorization boundaries still apply.

Inspect ready-to-apply templates with `--install-overlays --project <slug> --dry-run`. Run the same command without `--dry-run` to install missing files when authorized. Existing overlays are preserved. The resolver checks the template's schema and destination before installation. Python requires PyYAML when an overlay or project profile is present.
