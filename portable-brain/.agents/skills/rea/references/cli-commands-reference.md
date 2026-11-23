# REA CLI & Tools Reference

> **Comprehensive Command Matrix for REA (Reverse Engineer Anything)**  
> **Source**: `./.agents\skills\rea\references\cli-commands-reference.md`

---

## 1. Execution Modes

REA can be invoked instantly without persistent installation via `npx`:
```bash
# General CLI Command:
npx -y rea-agents@latest <command> [args] [--json]

# MCP Stdio Server (for agents):
npx -y rea-agents@latest --mcp

# Setup agent hooks and MCP registrations:
npx -y rea-agents@latest setup
```

---

## 2. Command Catalog by Target Modality

### A. JavaScript & Electron Applications
* **`analyze-javascript-application <path> [--json]`**: Analyzes extracted trees or ASAR bundles. Discovers modules, imports, IPC channels, and Electron main/renderer boundaries.
* **`recover-javascript-sources <path>`**: Recovers readable JavaScript modules using Wakaru/Babel AST deobfuscation with verified SHA-256 provenance.
* **`observe-javascript-runtime`**: Passively connects to Node.js / Electron V8 Inspector targets (`127.0.0.1:9229`).
* **`reconcile-javascript-runtime`**: Cross-verifies static AST findings with runtime heap and network observations.

### B. Native Binaries (PE, ELF, Mach-O, DOS)
* **`analyze-native-binary <file>`**: Full disassembly and decompilation using configured engine (Ghidra, Hopper, IDA Pro).
* **`analyze-function <file> --symbol <name>`**: Generates pseudocode, assembly, basic blocks, callers, callees, and value-flow ops.
* **`inspect-binary-layout <elf>`**: Offline static ELF analysis using pwntools (sections, symbols, mitigations: NX, ASLR, Canary).
* **`inspect-pe-resources <exe/dll>`**: Extracts embedded PE resources, icons, manifest XMLs, and version stamps.
* **`inspect-native-load-image`**: Verifies loaded native image headers and entry points.
* **`observe-native-calls <macho>`**: Launches Mach-O under LLDB and records function and Objective-C entries.
* **`inspect-recorded-crash <core>`**: Inspects historical Linux core dump registers, notes, and signals via GDB/pwndbg.

### C. Android Applications (APK & Device)
* **`inspect-android-package <apk>`**: Inspects manifest, permissions, activities, providers, and exports via headless JADX.
* **`inspect-android-class <apk> --class <FQN>`**: Decompiles an Android class and lists members and method signatures.
* **`inspect-android-method <apk> --class <FQN> --method <name>`**: Decompiles specific method bytecode into Java.
* **`trace-android-references <apk> --method <name>`**: Identifies incoming static call sites and cross-references.
* **`list-adb-devices` / `list-adb-packages` / `read-adb-logcat`**: Interacts with live emulators or hardware devices.

### D. Managed Code (.NET / Mono)
* **`inspect-managed-artifact <dll/exe>`**: Inspects PE/CLI metadata without executing code.
* **`inspect-managed-members <dll/exe>`**: Recovers CIL instruction streams, types, and member signatures.
* **`inspect-managed-native-boundaries <dll/exe>`**: Maps P/Invoke and native C++ pinvoke declarations.
* **`verify-managed-native-boundaries <dll/exe>`**: Validates P/Invoke bindings against export tables of native DLLs.

### E. Web, Network, WASM & EVM
* **`inspect-web-page`**: Passively inspects open Chrome pages over loopback CDP (`http://127.0.0.1:9222`).
* **`inspect-web-network-capture <har>`**: Parses HAR captures, extracts API calls and payloads without re-fetching.
* **`inspect-wasm-artifact <wasm>`**: Validates sections, imports, exports, and decompiles to WAT using WABT.
* **`inspect-evm-interface <hex/bytecode>`**: Disassembles EVM bytecode, infers function selectors and state mutability.
