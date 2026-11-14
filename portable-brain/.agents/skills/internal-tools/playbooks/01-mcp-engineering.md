# Playbook 01: MCP Server Engineering & Multi-Cloud Orchestration

> **Authority on FastMCP (Python), TypeScript MCP SDK, stdio/SSE/Streamable HTTP transports, and Multi-Cloud MCP Operations.**

---

## 1. Stack Selection & Architecture

### Python (Recommended for CLI Tools, AI, Data Science & Systems)
- **Library**: `fastmcp` (or `mcp.server.fastmcp`).
- **Transports**:
  - `stdio`: Default for local agent orchestration. High security, zero network surface, OS pipe-isolated.
  - `sse`: Server-Sent Events over HTTP. Used for network-accessible or containerized servers.
  - `streamable_http`: High-throughput binary and bidirectional streaming.

### TypeScript / Node.js (Recommended for Web, DOM, Cloudflare Workers & DevTools)
- **Library**: `@modelcontextprotocol/sdk`.
- **Transports**: `StdioServerTransport` or `SSEServerTransport`.

---

## 2. FastMCP Production Blueprint (Python)

```python
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import List, Optional

mcp = FastMCP(
    name="production-data-server",
    dependencies=["pydantic", "httpx"]
)

class QueryPayload(BaseModel):
    query: str = Field(description="Search or filter query string")
    limit: int = Field(default=10, ge=1, le=100, description="Max records to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")

@mcp.tool()
async def query_records(payload: QueryPayload, ctx: Context) -> dict:
    """Queries indexed records with pagination and actionable telemetry."""
    await ctx.info(f"Processing query: {payload.query} (limit={payload.limit})")
    
    # 1. Input sanitization & validation
    # 2. Database/API fetch
    # 3. Context-efficient response bundling (never dump raw megabytes!)
    return {
        "results": [],
        "count": 0,
        "offset": payload.offset,
        "limit": payload.limit,
        "has_more": False
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## 3. Core MCP Tool Design Principles

1. **Strict Context Efficiency**: Never dump megabytes of raw JSON or unformatted HTML into tool responses. Always enforce pagination (`offset`, `limit`) and summarize long lists.
2. **Actionable Errors**: When upstream APIs fail (e.g. rate limits, 401 Unauthorized), return actionable recovery steps, links to consoles, or permission flags instead of cryptic stack traces.
3. **Atomic Namespacing**: Use explicit, non-overlapping tool names (e.g. `d1_query`, `r2_put_object`, `aws_lambda_invoke`).
4. **Tool Annotation**: Every argument MUST have a clear description and type constraint (`ge`, `le`, `regex`).

---

## 4. Multi-Cloud MCP Operations Guide

Reference for all pre-configured cloud MCP servers in `<USER_HOME>\.gemini\config\mcp_config.json`:

| Cloud Service | MCP Server Name | Primary Capabilities & Best Practices |
|---|---|---|
| **Cloudflare** | `cloudflare` | • `d1_query`: Query edge SQLite databases.<br>• `r2_list_buckets`, `r2_put_object`: Bulk storage ($0 egress).<br>• `worker_list`, `worker_deploy`: Deploy edge functions.<br>• *Rule*: Use MCP for live queries; write configs with `wrangler.jsonc`. |
| **Appwrite** | `appwrite` | • `appwrite_call_tool`: Manage documents, users, collections, and storage.<br>• *Rule*: Respect collection schemas and auth permissions. |
| **Azure** | `azure` | • Manage Flexible Server PostgreSQL (`Standard_B1ms`), VMs, and Resource Groups.<br>• *Rule*: Zero paid public IPv4 addresses; enforce Cloudflare Tunnels. |
| **AWS** | `aws`, `aws-documentation` | • `call_aws`: Lambda compute, S3 object management.<br>• `search_documentation`: Live AWS official documentation. |
| **GitHub** | `github-mcp-server` | • `get_file_contents`, `create_or_update_file`, `list_commits`, `create_pull_request`.<br>• *Rule*: Always fetch current file SHA before updating. |
| **Chrome DevTools** | `chrome-devtools-mcp` | • `navigate_page`, `take_screenshot`, `list_console_messages`, `list_network_requests`. |
