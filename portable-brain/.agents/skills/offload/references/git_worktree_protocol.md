# Git Worktree & Branch Isolation Protocol (`offload`)

`worktree_manager.py` isolates parallel worker edits in external sibling Git worktrees without mutating the primary working tree or risking Windows NTFS junction target deletion.

## 1. Layout & Branch Invariants
- **External sibling worktree root** (never inside the repository):
  `<repo_root.parent>/.worktrees/<repo_name>/<worker_id>/<task_slug>`
  (Overrideable via `--worktrees-root <dir>`; paths inside `<repo_root>` are rejected.)
- **Branch naming**:
  `agent/<worker_id>/<slug>` where `<worker_id>` and `<slug>` are sanitized to lowercase `[a-z0-9_-]`.
- **Windows Git resolution & config**:
  Resolves native Windows `git.exe` via `shutil.which("git")` (excluding Cygwin/WSL/MSYS `/usr/bin/git`), falling back to `C:\Program Files\Git\cmd\git.exe` (and `%LOCALAPPDATA%\Programs\Git\cmd\git.exe`). Each created worktree sets:
  - `core.fileMode false`
  - `core.longpaths true`

## 2. `.worktreeinclude` Hydration
If `<repo_root>/.worktreeinclude` exists, non-empty, non-`#` lines are treated as relative paths/globs inside `<repo_root>` and copied into the new worktree (for ignored local config such as `.env.local`):
- Absolute paths, drive-letter prefixes, `..` traversal segments, symlinks escaping `<repo_root>`, and any `.git` paths are strictly skipped.

## 3. Windows NTFS Junction-Safe Teardown
Before `git worktree remove`, `unlink_ntfs_junctions(wt_path)` walks top-down with `followlinks=False`:
- Detects directory symlinks (`os.path.islink`) and Windows NTFS reparse points (`lstat().st_file_attributes & 0x400`).
- Prunes traversal (`dirs.remove(d)`) before unlinking so shared targets (`node_modules`, `.venv`) are never entered.
- Unlinks only the junction/symlink pointer (`cmd /c rmdir "<junction>"` on Windows for junctions; `os.unlink` for symlinks).

## 4. CLI Subcommands
```bash
# Create isolated worktree + agent/<worker>/<slug> branch + .worktreeinclude hydration
python worktree_manager.py create --repo <path> --worker <id> --task <slug> [--base HEAD] [--worktrees-root <dir>]

# List worktrees
python worktree_manager.py list --repo <path>

# Inspect cleanliness, branch, HEAD, and junctions
python worktree_manager.py status --repo <path> --worker <id> --task <slug>
python worktree_manager.py status --path <wt_path>

# Run verification command inside a worktree
python worktree_manager.py verify --path <wt_path> --cmd "<command>"

# Verify (optional), refuse dirty tree, rebase onto target, merge --ff-only, and clean up (unless --keep)
python worktree_manager.py merge --repo <path> --worker <id> --task <slug> [--into main] [--verify-cmd "..."] [--keep]

# Junction-safe remove
python worktree_manager.py remove --repo <path> --worker <id> --task <slug> [--force]
python worktree_manager.py remove --path <wt_path> [--force]

# Prune stale git worktree metadata and empty .worktrees directories
python worktree_manager.py prune --repo <path> [--worktrees-root <dir>]
```
