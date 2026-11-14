# Universal Search Protocol & Subagent Research Invariant

> **MANDATORY INVARIANT FOR ALL AGENTS & SESSIONS**  
> **Prevents Search Neglect, Eliminates Context Bloat, and Standardizes Frontier Escalation**

---

## 1. Zero Search Neglect Invariant
- **Never Guess When Information Can Be Verified**: Whenever encountering new libraries, breaking API changes, recent cloud updates, unexplained error codes, or unfamiliar third-party schemas, agents MUST proactively search.
- **Forbidden Assumptions**: Never assume API endpoints or SDK methods exist without verifying live documentation or running search checks.

---

## 2. Mandatory Subagent Search Isolation
- **Context Bloat Prevention**: Searching, fetching pages, and parsing web content consumes massive token budgets and pollutes the active session context with irrelevant HTML/JSON noise.
- **Rule**: Whenever performing exploratory web searches, comparative architecture lookups, or multi-page documentation scrapes, **ALWAYS spawn a dedicated search subagent first**:
  - Spawn with: `invoke_subagent(TypeName='self', Role='Web Search Specialist', Prompt='...')`
  - The subagent operates with fresh context, runs multi-query searches, evaluates source credibility, and drills down into URLs.
  - The subagent returns **ONLY** a clean, high-density technical briefing directly answering the parent agent's inquiry.
  - **Zero Raw HTML Dumps**: Never dump raw web pages or unparsed search pagination into the parent conversation.

---

## 3. Multi-Tier Search Escalation Hierarchy
All searches must utilize the multi-tier search engine (`web-search-orchestrator`):
1. **Tier 1 — TinyFish CLI**: Zero-cost, live web search and clean markdown page extraction (`tinyfish search query`, `tinyfish fetch content get`).
2. **Tier 2 — Tavily Search API**: Semantic Q&A search with answer synthesis and domain restriction.
3. **Tier 3 — Firecrawl API**: Full JavaScript stealth scraping for dynamic SPAs and anti-bot protected sites.
4. **Tier 4 — Native Tools**: Built-in `search_web` and `read_url_content`.
5. **Tier 5 — Gemini Deep Research Fallback**: Multi-topic, exhaustive research.

---

## 4. Frontier Escalation to Gemini Deep Research
When a research inquiry is too vast for single-query APIs (e.g. comprehensive 2026 model benchmarks, multi-platform SDK comparisons, or complex cross-cloud architecture patterns):
1. **Subagent Formulates the Prompt**: Generate a structured, high-effort prompt using `gemini_deep_research.py`.
2. **Format Requirement**: Specifically mandate maximum search effort, cross-source verification, structured Markdown tables, copy-pasteable configuration code, and strict elimination of conversational/marketing fluff.
3. **Prompt the Developer**: Ask the developer to execute the prompt in Gemini Deep Research (Google AI Pro account) and paste back the raw technical dossier.
4. **Ingest to Memory**: Store the verified findings in the active project's `context/` and `hermes_global_memory.db`.

---

## 5. Mandatory Script Execution (Zero-Passive-Reading Rule)
- **Skills are Executable Software Runbooks, NOT Static Reading Material**:
  - When told to search or use a skill that has bundled scripts (`scripts/`), agents **MUST EXECUTE THE SCRIPT** using `run_command` on turn 1:
    ```powershell
    python <BRAIN_ROOT>\.agents\skills\web-search-orchestrator\scripts\search_engine.py search "<query>" --engine parallel
    ```
  - **STRICT PROHIBITION**: NEVER call `view_file` on `search_engine.py` or describe what the code does instead of running it. Execute the command, inspect live results, and deliver facts.
  - **Cross-Project Invocations**: Universal skill scripts in `<BRAIN_ROOT>\.agents\skills\<skill>\scripts\` can and must be executed from ANY project workspace by calling their absolute path.
  - **Parallel Search Execution**: Always use `--engine parallel` to run TinyFish and Tavily concurrently, returning aggregated intelligence in <1-2 seconds.

