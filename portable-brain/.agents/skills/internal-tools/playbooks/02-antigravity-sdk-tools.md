# Playbook 02: Antigravity SDK Tool Engineering

> **Authority on Native IDE Tool Schemas, Component Registry Compatibility, and Subagent Delegation.**

---

## 1. Antigravity Tool Declaration & Architecture

In the Google Antigravity runtime (`language_server.exe`), tools are registered as native schema definitions and executed either via deterministic local commands or RPC handlers.

### Tool Declaration Schema
```json
{
  "name": "custom_data_analyzer",
  "description": "Analyzes structured log data and outputs an actionable telemetry summary.",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "log_path": {
        "type": "STRING",
        "description": "Absolute path to the log file on disk."
      },
      "max_entries": {
        "type": "INTEGER",
        "description": "Maximum entries to parse (default 100)."
      }
    },
    "required": ["log_path"]
  }
}
```

---

## 2. Invariant: Language Server Registry Compatibility

> [!CAUTION]
> **The 1-Second Subagent Crash Defect**:
> Antigravity's internal build (`language_server.exe`) fails when spawning subagents configured with missing tools:
> `failed to construct executor: failed to resolve components: unknown component: tool "skill_search" not found in registry`.
> **Rules for Tool Developers**:
> 1. NEVER declare hard dependencies on internal unexported tools (e.g. `skill_search`).
> 2. When creating custom subagents dynamically via `define_subagent()`, always set:
>    - `enable_write_tools: true`
>    - `enable_mcp_tools: true`
> 3. Provide fully self-contained tool implementations that execute deterministically without relying on runtime hacks.

---

## 3. Dynamic Subagent Creation Standard

When a task requires specialized execution in a separate conversation context:

```python
# Definition pattern
define_subagent(
    Name="perf_analyzer",
    Description="Analyzes CPU/RAM profiles and returns optimization recommendations.",
    SystemPrompt="""You are a Systems Performance Specialist.
Follow these invariants:
1. Maintain documentation integrity.
2. Deliver code changes directly to temp_read/.
3. Verify all scripts with live runtime checks.""",
    EnableWriteTools=True,
    EnableMCPTools=True,
    EnableSubagentTools=False
)

# Invocation pattern
sub_id = invoke_subagent(
    TypeName="perf_analyzer",
    Role="Performance Profiler",
    Prompt="Profile the latency of the API router and save the report to temp_read/perf_report.md"
)
```
