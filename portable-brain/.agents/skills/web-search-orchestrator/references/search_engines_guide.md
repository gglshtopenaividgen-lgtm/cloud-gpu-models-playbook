# Web Search Orchestrator: Multi-Engine Search & Provider Configuration Guide

Reference guide for search engine backends, API credentials, and subagent search isolation.

---

## 1. Search Engine Providers

| Engine | Best For | Configuration Source |
|---|---|---|
| **Argon Deep Research** | 20+ source exhaustive dossiers, competitive landscape matrices, complex academic synthesis | Autonomous browser bridge (`127.0.0.1:9229`) with rolling AI Pro profile pool. Zero API keys. |
| **Tavily** | Direct LLM-optimized web search snippets, rapid factual lookups | `TAVILY_API_KEY` via project environment or secret store |
| **Firecrawl** | Deep documentation scraping, recursive web page crawling to clean markdown | `FIRECRAWL_API_KEY` via project environment or secret store |
| **TinyFish** | Ultra-fast lightweight web querying and link extraction | Bundled CLI integration |

---

## 2. CLI Execution Examples

```bash
# Class A: Gemini Web Deep Research dossier
python .agents/skills/web-search-orchestrator/scripts/search_engine.py deep-search "<topic>" -o temp_read/report.md

# Class B: Parallel multi-engine query (Tavily + Firecrawl + TinyFish)
python .agents/skills/web-search-orchestrator/scripts/search_engine.py search "<query>" --engine parallel

# URL Markdown extraction
python .agents/skills/web-search-orchestrator/scripts/search_engine.py fetch "<url>"
```
