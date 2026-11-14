# Self-Contained Google Spark & Gemini Deep Research Prompt Template

Use this template whenever formulating research prompts for **Google Spark** (no filesystem access) or **Gemini Deep Research**:

---

```markdown
# 🔬 RESEARCH BRIEF: [Topic / System Name]

## 1. ARCHITECTURAL OBJECTIVE
[Concise 2-sentence summary of the mathematical, architectural, or algorithm optimization problem to solve.]

## 2. HARD INFRASTRUCTURE CONSTRAINTS & BOUNDARIES
- **Runtime Environment**: [e.g., Cloudflare Workers V8 Isolate (30s hard timeout, 128MB RAM) / Next.js 15 App Router / Node.js 22].
- **Cost Guardrails**: 100% Free Tier (Azure PostgreSQL `Standard_B1ms`, 0 Public IPv4s, AWS Lambda 1M req/mo).
- **Latency Budget**: Time-To-First-Token (TTFT) < [e.g. 400ms], Total Execution < [e.g. 2500ms].
- **Network Invariant**: VM ingress exclusively via Cloudflare Tunnels; egress to LLM APIs via residential Anycast IPs.

## 3. EXACT CONTEXT PAYLOADS & SCHEMAS
```typescript
// [Insert Relevant TypeScript Interfaces, Enums, or Types]
```

```sql
-- [Insert Relevant PostgreSQL / Supabase Table Schemas]
```

## 4. TARGET QUESTIONS & TRADE-OFF EVALUATIONS
1. **Mathematical & Algorithmic Design**:
   - [e.g., How should we calculate adaptive Spaced Repetition stability decay parameters given sparse user telemetry?]
2. **Streaming & Buffer Protocol**:
   - [e.g., Compare Web Audio AudioWorklet vs. ScriptProcessorNode vs. raw Web Worker buffer streaming for real-time 10-band PEQ.]
3. **Trade-Off Matrix Analysis**:
   - Evaluate Approach A vs Approach B across:
     * Memory overhead (KB).
     * Cold start latency (ms).
     * Token consumption & context window efficiency.
     * Resilience against network disconnection/reconnects.

## 5. REQUIRED OUTPUT FORMAT
- Deliver complete, executable algorithms or TypeScript interfaces.
- Provide a comparative trade-off matrix table with quantitative ratings.
- Provide concrete pseudo-code / state machine diagrams.
```
