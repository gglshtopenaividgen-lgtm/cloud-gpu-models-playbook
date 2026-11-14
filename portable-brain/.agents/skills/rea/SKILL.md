---
name: rea
description: "Reverse Engineer Anything (REA): Deep binary disassembly, decompilation, Electron/JS deobfuscation, Android APKs, .NET assemblies, WASM, and live runtime observation using the REA engine."
compatibility: Windows 11 PowerShell, Linux bash, macOS, Node.js 22+, Java 17+
metadata:
  version: "1.0.0"
  type: "universal-skill"
  scope: "Universal"
---

# REA: Reverse Engineer Anything

> **One Framework for Reverse Engineering Across Binaries, Applications, and Runtime Behavior**  
> **Source Repository**: `https://github.com/morluto/rea` (morluto/rea)  
> **CLI Engine**: `npx -y rea-agents@latest` | Helper: `python .../rea/scripts/rea_runner.py`

---

## 1. Execution-First Mandate & Subagent Isolation

> [!IMPORTANT]
> ⛔ **SUBAGENT ISOLATION FOR HEAVY ANALYSIS**:
> Reverse engineering tasks (decompilation, AST tree extraction, full-binary xref walks) generate **tens of thousands of tokens of disassembly and pseudocode**.
> **NEVER run full decompilations or large AST traces directly in the parent conversation**.
> ALWAYS spawn a dedicated subagent (`TypeName='self'`) to run the REA CLI, inspect the evidence, and return ONLY a high-density synthesized finding to the parent session.

Universal runner command:
```bash
python <BRAIN_ROOT>\.agents\skills\rea\scripts\rea_runner.py <command> [args...]
# Or directly via npx:
npx -y rea-agents@latest <command> [args...] --json
```

---

## 2. Modality Routing Truth Table

Route your investigation based on the target artifact:

| Artifact Target | Primary REA Tool | Key Arguments / Flags | Host Requirement |
|---|---|---|---|
| **JavaScript / Electron App** | `analyze-javascript-application` | `<path_to_app_or_asar> [--source-path main.js]` | Node.js 22+ (Ready) |
| **Obfuscated JS / Web Bundle** | `recover-javascript-sources` | `<path> --additional-paths ...` | Node.js 22+ (Ready) |
| **Native Executable / DLL / SO** | `analyze-native-binary` | `<binary_path>` | Ghidra / Hopper / IDA |
| **Focused Function Decompilation** | `analyze-function` | `<binary_path> --symbol <name>` | Disassembler engine |
| **Offline ELF Layout & Mitigations**| `inspect-binary-layout` | `<elf_path>` | Python pwntools |
| **Windows PE Resources & Icons** | `inspect-pe-resources` | `<exe_or_dll_path>` | Portable (No engine needed) |
| **Android APK Package & Manifest**| `inspect-android-package` | `<apk_path>` | Java 17+ (Ready) |
| **Android Method Decompilation** | `inspect-android-method` | `<apk_path> --class <FQN> --method <name>` | Headless JADX JAR |
| **Managed Code (.NET / CLI)** | `inspect-managed-artifact` | `<dll_or_exe_path>` | Portable (No engine needed) |
| **Managed P/Invoke Validation** | `verify-managed-native-boundaries`| `<managed_dll> --native <native_dll>` | Portable |
| **WebAssembly (.wasm)** | `inspect-wasm-artifact` | `<wasm_path>` | WABT 1.0.42 |
| **EVM Bytecode (Smart Contracts)** | `inspect-evm-interface` | `<hex_or_raw_file>` | Portable |
| **Network Captures (HAR / MITM)** | `inspect-web-network-capture` | `<har_file_path>` | Portable |
| **Live Browser / CDP Target** | `inspect-web-page` | `--cdp-endpoint http://127.0.0.1:9222` | Loopback Chrome CDP |
| **Linux Core Dump / Crash** | `inspect-recorded-crash` | `<core_dump_path>` | GDB / pwndbg |

---

## 3. Evidence & Verification Protocol

REA operates on an **Evidence-First Verification Standard**:
1. **Never Hallucinate Decompilation**: Only report pseudocode, symbol names, and signatures returned directly by the disassembler or AST deobfuscator.
2. **Stable Evidence IDs**: Every analysis generates an `evidence_id`. Cite this ID when chaining follow-up queries:
   ```bash
   npx -y rea-agents@latest inspect-analysis-view --evidence-id <id> --facet value_flow_operations
   ```
3. **Cross-Validation**: Validate static observations against runtime traces:
   - For JavaScript: Combine `analyze-javascript-application` with `observe-javascript-runtime`.
   - For Native: Combine `analyze-native-binary` with `observe-native-calls`.
4. **Unknown Scopes**: When dependencies, dynamic reflection, or stripped symbols prevent conclusive decompilation, explicitly log the unknown scope rather than guessing.

---

## 4. Subdocumentation Matrix

For detailed workflows and engine-specific guides, refer to:
* **[references/cli-commands-reference.md](references/cli-commands-reference.md)**: Full syntax for all 45+ CLI commands.
* **[references/javascript-applications.md](references/javascript-applications.md)**: Electron ASAR extraction, IPC channel tracing, and AST recovery.
* **[references/native-and-artifacts.md](references/native-and-artifacts.md)**: Native binaries, Ghidra configuration, Hopper bridge, and ELF layouts.
* **[references/android-applications.md](references/android-applications.md)**: Headless JADX decompilation, APK manifest extraction, and ADB.
* **[references/evidence-workflows.md](references/evidence-workflows.md)**: Evidence tracking, unknown registries, and behavioral comparisons.
* **[references/runtime-observation.md](references/runtime-observation.md)**: Passive Chrome CDP and Electron runtime observation.
* **[references/connection-and-recovery.md](references/connection-and-recovery.md)**: Provider setup and troubleshooting.
