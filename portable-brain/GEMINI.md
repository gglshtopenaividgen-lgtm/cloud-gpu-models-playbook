# Autonomous Tool & Central Brain Preservation Policy

## 1. Autonomous Tool & MCP Execution Policy
- The agent has full, pre-approved authorization to execute all tools and MCP tools (including GitHub, AWS, Azure, Cloudflare, Appwrite, Chrome DevTools, Sequential Thinking, etc.) autonomously without asking for confirmation.
- The agent has full permission to read any public URL, fetch API documentation, and make HTTP requests as needed.
- Never ask the user for permission or confirmation before invoking an MCP tool, running read/write commands, or inspecting web content. Proceed directly to execution.

## 2. Central Brain Workspace Preservation Policy
- `<BRAIN_ROOT>` is the permanent central multi-project knowledge base.
- **NEVER OVERWRITE OR DELETE** existing files or directories in `<BRAIN_ROOT>` with single-project data.
- **ALWAYS MERGE & APPEND** when adding new project notes, ideas, mistakes, resources, or memory.
- `<BRAIN_ROOT>` is a Git repository. Always commit updates to Git.

## 3. Autonomous Turn-1 Auto-Skill Routing & Project Isolation Invariant
- **Turn-1 Auto-Skill Mandate**: On EVERY prompt or task, evaluate task requirements and autonomously activate the matching skill BEFORE writing code or designing plans. Never wait for `/auto-skill` or user prompts.
- **Universal vs Project Scope**:
  - Universal Skills (`brain/.agents/skills/`) are authorized across all projects.
  - Project-Specific Skills are authorized ONLY within their designated workspace.
  - NEVER load, reference, or execute skills from Project A when working in Project B.
  - Deliverables belong strictly in `<active-project>/temp_read/`. Never write project files to `brain/` root or foreign projects.

