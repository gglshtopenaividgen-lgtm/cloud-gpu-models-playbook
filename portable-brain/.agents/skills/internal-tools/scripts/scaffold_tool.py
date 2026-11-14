#!/usr/bin/env python3
"""scaffold_tool.py - Scaffolder for MCP servers, Antigravity SDK tools, Chrome MV3 extensions, and skills."""

import argparse
import json
import os
import sys
from pathlib import Path

TEMPLATES = {
    "mcp": {
        "server.py": '''#!/usr/bin/env python3
"""FastMCP Production Server Scaffold."""
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

mcp = FastMCP(name="{name}", dependencies=["pydantic"])

class ExecuteRequest(BaseModel):
    action: str = Field(description="Action verb to execute")
    payload: dict = Field(default_factory=dict, description="Arbitrary payload parameters")

@mcp.tool()
async def execute(req: ExecuteRequest, ctx: Context) -> dict:
    """Executes a managed tool action."""
    await ctx.info(f"Executing {req.action}")
    return {"status": "success", "action": req.action, "result": {}}

if __name__ == "__main__":
    mcp.run(transport="stdio")
'''
    },
    "sdk": {
        "tool_definition.json": '''{
  "name": "{name}",
  "description": "Antigravity SDK Tool definition for {name}",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "input_text": {
        "type": "STRING",
        "description": "Primary input parameter"
      }
    },
    "required": ["input_text"]
  }
}'''
    },
    "chrome": {
        "manifest.json": '''{
  "manifest_version": 3,
  "name": "{name}",
  "version": "1.0.0",
  "description": "Chrome MV3 Extension Scaffold for {name}",
  "permissions": ["storage", "tabs", "debugger"],
  "background": {
    "service_worker": "background.js",
    "type": "module"
  }
}''',
        "background.js": '''// MV3 Service Worker Scaffold
chrome.runtime.onInstalled.addListener(() => {
  console.log("{name} installed.");
});
'''
    },
    "skill": {
        "SKILL.md": '''---
name: {name}
description: "Master instruction set for {name}."
compatibility: Windows 11 PowerShell, Python 3.10+
metadata:
  version: "1.0.0"
  type: "{scope}-skill"
---

# {title}

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE (ZERO-PASSIVE-READING)**:
> Bundled scripts in `scripts/` are **executable software tools**, NOT reading material.
> When this skill is triggered, **EXECUTE the relevant script immediately** via `run_command`.

## 1. Overview
Describe capabilities and invariants for {name}.
'''
    }
}


def main():
    parser = argparse.ArgumentParser(description="Scaffold internal tools, extensions, and skills")
    parser.add_argument("--type", choices=["mcp", "sdk", "chrome", "skill"], required=True)
    parser.add_argument("--name", required=True, help="Name of the tool or skill")
    parser.add_argument("--out", default=None, help="Output directory")
    parser.add_argument("--project", default=None, help="Target project workspace for project-scoped skill")

    args = parser.parse_args()

    clean_name = args.name.lower().replace("_", "-")
    title = clean_name.replace("-", " ").title()

    if args.type == "skill":
        scope = "project" if args.project else "universal"
        if args.project:
            target_dir = Path(f"<USER_HOME>/Desktop/{args.project}/.agents/skills/{clean_name}")
        else:
            target_dir = Path(args.out or f"<BRAIN_ROOT>/.agents/skills/{clean_name}")
    else:
        target_dir = Path(args.out or clean_name)

    target_dir.mkdir(parents=True, exist_ok=True)

    tmpl_files = TEMPLATES.get(args.type, {})
    for filename, content in tmpl_files.items():
        out_file = target_dir / filename
        formatted = content.format(name=clean_name, title=title, scope=scope if args.type == "skill" else "")
        out_file.write_text(formatted, encoding="utf-8")
        print(f"[Scaffold] Created {out_file.resolve()}")

    if args.type == "skill":
        (target_dir / "scripts").mkdir(exist_ok=True)
        (target_dir / "playbooks").mkdir(exist_ok=True)
        print(f"[Scaffold] Created scripts/ and playbooks/ in {target_dir}")

    print(f"\n[Scaffold] Successfully initialized {args.type} at: {target_dir.resolve()}")


if __name__ == "__main__":
    main()
