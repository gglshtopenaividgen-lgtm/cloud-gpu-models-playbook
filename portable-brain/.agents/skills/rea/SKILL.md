---
name: rea
description: "Reverse Engineer Anything (REA): Deep binary disassembly, decompilation, Electron/JS deobfuscation, Android APKs, .NET assemblies, WASM, and live runtime observation using the REA engine."
---

# REA: Reverse Engineer Anything

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/rea.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill rea`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. Subagents MUST be used for heavy decompilations (`TypeName='self'`).

Universal reverse engineering framework covering binaries, web/Electron bundles, mobile APKs, bytecode, and live runtime behavior.

---

## 1. Modality Routing Truth Table

| Target Artifact | Primary REA Tool | Key Arguments / Flags | Host Requirement |
|:---|:---|:---|:---|
| **JavaScript / Electron App** | `analyze-javascript-application` | `<path_to_app_or_asar> [--source-path main.js]` | Node.js 22+ (Ready) |
| **Obfuscated JS / Web Bundle**| `recover-javascript-sources` | `<path> --additional-paths ...` | Node.js 22+ (Ready) |
| **Native Executable / DLL / SO**| `analyze-native-binary` | `<binary_path>` | Ghidra / Hopper / IDA |
| **Focused Function Decompile** | `analyze-function` | `<binary_path> --symbol <name>` | Disassembler engine |
| **Offline ELF Layout / Mitigations**| `inspect-binary-layout` | `<elf_path>` | Python pwntools |
| **Windows PE Resources & Icons**| `inspect-pe-resources` | `<exe_or_dll_path>` | Portable (No engine needed) |
| **Android APK Package & Manifest**| `inspect-android-package` | `<apk_path>` | Java 17+ (Ready) |
| **Android Method Decompilation**| `inspect-android-method` | `<apk_path> --class <FQN> --method <name>` | Headless JADX JAR |
| **Managed Code (.NET / CLI)** | `inspect-managed-artifact` | `<dll_or_exe_path>` | Portable |
| **WebAssembly (.wasm)** | `inspect-wasm-artifact` | `<wasm_path>` | WABT 1.0.42 |
| **EVM Bytecode (Smart Contracts)**| `inspect-evm-interface` | `<hex_or_raw_file>` | Portable |
| **Network Captures (HAR / MITM)**| `inspect-web-network-capture` | `<har_file_path>` | Portable |
| **Live Browser / CDP Target** | `inspect-web-page` | `--cdp-endpoint http://127.0.0.1:9222` | Loopback Chrome CDP |

---

## 2. Core CLI Commands

```bash
# 1. Instant local help and command matrix (0ms)
python .agents/skills/rea/scripts/rea_runner.py --help

# 2. Deobfuscate JavaScript / Webpack bundle
python .agents/skills/rea/scripts/rea_runner.py recover-javascript-sources bundle.js --out-dir recovered/

# 3. Inspect Windows PE or DLL headers
python .agents/skills/rea/scripts/rea_runner.py inspect-pe-resources target.exe

# 4. Inspect Android APK manifest and permissions
python .agents/skills/rea/scripts/rea_runner.py inspect-android-package app.apk
```

---

## 3. References & Deep Guides

- [JavaScript & Electron Applications](references/javascript-applications.md)
- [Native Binaries & Artifacts](references/native-and-artifacts.md)
- [Android Applications](references/android-applications.md)
- [Runtime Observation](references/runtime-observation.md)
- [Evidence Workflows](references/evidence-workflows.md)
- [CLI Commands Reference](references/cli-commands-reference.md)
- [Connection & Recovery](references/connection-and-recovery.md)