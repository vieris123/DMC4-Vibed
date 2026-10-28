# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **game reverse engineering workspace** targeting **Devil May Cry 4 (DirectX 9)** (`DevilMayCry4_DX9.exe`). The IDA Pro database files (`.i64`, `.id0`, `.id1`, `.id2`, `.nam`, `.til`) in this directory are the primary artifacts. Claude connects to a live IDA Pro session via the `ida-pro-mcp` MCP server and can decompile, disassemble, rename, comment, and annotate the binary directly.

## Prerequisites

IDA Pro must be running with the MCP plugin active before any analysis tools will work:

1. Open `DevilMayCry4_DX9.exe` (or the `.i64` database) in IDA Pro
2. Press **Ctrl+Alt+M** to start the MCP server (or go to Edit → Plugins → MCP)
3. Verify the server is up at `http://127.0.0.1:13337/mcp`

The MCP proxy server (`C:\Tools\MCP_dev\ida-pro-mcp\src\ida_pro_mcp\server.py`) is launched automatically by Claude Code via `.mcp.json`. It auto-discovers running IDA instances and routes tool calls to the correct one.

## MCP Server

| Server | Transport | Purpose |
|--------|-----------|---------|
| `ida-pro-mcp` | stdio → HTTP `127.0.0.1:13337` | Controls the live IDA Pro session |

Key tools available (grouped by purpose):

- **Overview:** `survey_binary`, `list_funcs`, `list_globals`, `imports`
- **Analysis:** `decompile`, `disasm`, `basic_blocks`, `callgraph`, `callees`, `func_profile`, `analyze_batch`
- **Navigation:** `lookup_funcs`, `find`, `find_bytes`, `find_regex`, `xref_query`, `xrefs_to`
- **Annotation:** `set_comments`, `rename`, `set_type`, `infer_types`, `declare_type`, `enum_upsert`
- **Mutation:** `patch_asm`, `patch`, `define_func`, `define_code`, `undefine`
- **Memory:** `get_bytes`, `get_int`, `get_string`, `get_global_value`
- **Stack/Types:** `stack_frame`, `declare_stack`, `type_query`, `type_inspect`
- **Scripting:** `py_eval`, `py_exec_file` (IDAPython)
- **Utility:** `int_convert` — converts between hex/decimal/binary

## Project Goal

The overarching objective is to **decouple `sMediator`'s per-player members** from the singleton to enable multiplayer support. Analysis should focus on classifying each field as per-player state vs. globally shared state, and mapping every access site that will need refactoring.

## MT Framework Engine Conventions

The engine uses a strict naming prefix system:

| Prefix | Meaning | Examples |
|--------|---------|---------|
| `Mt` | Math / base library types | `MtMatrix`, `MtVector3` |
| `s` | Singleton structs | `sMediator`, `sCollision`, `sSave` |
| `c` | Component classes (embedded in owners) | `cPlParamSave`, `cMousePointerCtrl` |
| `u` | Unit / game-object classes | `uPlayer`, `uActor` |

Methods use PascalCase (`setCallback`, `getInstance`). Do **not** introduce names that follow this convention for placeholder names — use `lowercase_underscore` instead so temporaries are visually distinct.

### MtDTI System

Every class has a DTI (Data Type Info) object registered at startup via `sub_8B69B0(size, parent)`. The DTI object layout:

- `[+0]` — pointer to constructor function
- `[+4]` — pointer to destructor / factory function

The DTI global for a class (e.g., `dword_E57F78` for `sMediator`) is set to the address of the class's DTI object after registration. Singleton instance pointers live separately (e.g., `sMediator::mpInstance`).

### Instance Vtable Layout (non-singleton classes)

The instance vtable (stored at `instance[+0]`, labeled `vtable_ClassName`) has a fixed slot layout inherited from `MtObject`:

| Vtable offset | Slot | Role |
|---------------|------|------|
| +0x10 | 4 | `getDTI()` — returns class DTI |
| +0x14 | 5 | `init()` — initialization |
| +0x18 | 6 | lifetime loop (per-frame tick) |
| +0x78 | 30 | `behaviour()` — game logic |
| last entry | — | destructor |

Slots +0x00–+0x0C (0–3) are earlier MtObject base virtuals not yet mapped.

### IDA Workflow Notes

- **Always verify a function is defined before calling `decompile`** — if IDA shows `<no function>` in disassembly, use `define_func` first. Decompile will silently fail on undefined code regions.
- **Ask before broad structural digs** — for open-ended exploration (vtable walking, large xref sweeps), check with the user on scope first.
- **`py_eval` for mass analysis** — use IDAPython scripts via `py_eval` to walk xrefs, scan instruction patterns, or batch-extract call-site arguments rather than calling `decompile`/`disasm` in a loop.

## Naming Conventions for Discovered Functions

Functions that haven't been given final names use the `ClassName::placeholder_name` scheme:

- Folder: the `::` separator creates a folder in IDA's Functions window (e.g., `sCollision::`)
- Sub-prefix: lowercase with underscore describes role, **not** MT Framework style
- These are explicitly temporary — rename to proper MT Framework names once purpose is confirmed

**Established folders:**

| Folder | Slot | Role |
|--------|------|------|
| `sCollision::collNarrow_*` | +0x40 (ecx) | Narrowphase geometry test |
| `sCollision::collBounds_*` | +0x44 | Broadphase bounding volume compute |
| `sCollision::collStore_*` | +0x48 | Hit result commit |

## Key Types Analyzed

### `sCollision` (0x50DFB0 — `sCollision::setCallback`)

Initializes a 3-slot collision dispatch triple stored in the struct:
- `+0x00–0x3F`: `MtMatrix` (4×4 float, initialized to Identity)
- `+0x40`: func1 / ecx — narrowphase test callback
- `+0x44`: func2 — broadphase bounds callback (inverts world matrix, outputs AABB)
- `+0x48`: func3 — hit commit callback (copies result fields)
- `+0x4C`: param_4
- `+0x50`: filter
- `+0x54`: flags (byte)

138 call sites use 15 unique triples covering ~10 shape types. The dominant shape (105/138) is the capsule/line-sweep used for character hitboxes.

### `sMediator` (2032 bytes, singleton)

Central game-session coordinator. Constructor: `0x410360` (sets vtable). Full init: `sub_48F580`.

Known field layout from the init function:

| Offset | Type / Value | Notes |
|--------|-------------|-------|
| +0x00 | vtable (`off_BA8B90`) | main vtable |
| +0x04 | `CRITICAL_SECTION` (24 bytes) | threading |
| +0x20 | `bool mInit` | |
| +0x24 | `uPlayer* mpPlayer` | **per-player** |
| +0x30 | embedded sub-object | vtable `off_BA8BB0` at +0x30? |
| +0x80 | embedded sub-object | vtable `off_B9C6C0` at +0x80 |
| +0xB0 | `uActor* mpBoss` | per-session |
| +0x148 | sub-object vtable `off_B9A974` | |
| +0x353 | byte from `sSave::mpInstance+0xB8` | difficulty/save-slot |
| +0x280–0x350 | score/timer float arrays (1024.0f init) | **per-player** |
| +0x4B0–0x4AC | `CRITICAL_SECTION`? | sub-object |
| +0x4B0 | sub-object vtable `off_BA8BF0` | |
| +0x4C0–0x4CF | enum items: TextureResolution, Quality, FrameRate | **global** |
| +0x4BC–0x7D8 | 200-DWORD zeroed table | entity/combo tracking |
| +0x7DC | = 4 | |

Sub-components registered separately: `cPlParamSave` (128 B, **per-player**), `cBenchmarkFpsRecord` (1244 B, global), `cMousePointerCtrl` (12 B, per-player).

## Analysis Methodology

1. **Start with overview** — `survey_binary` for a quick orientation; `list_funcs` + `imports` to map the attack surface
2. **Decompile first** — inspect Hex-Rays output thoroughly before acting; don't rely on stale or incorrect existing comments
3. **Improve readability in the database** — rename variables/functions to descriptive names, fix pointer types, array sizes, and struct layouts
4. **Deep-dive to disassembly** when decompiler output is ambiguous or omits low-level behavior
5. **Comment extensively** — document *why*, not just what; inline comments for non-obvious behavior
6. **Document findings** — write results to `RE/<topic>.md` files organized by subject area

### Critical Constraints

- **NEVER convert number bases yourself** — always use the `int_convert` MCP tool for hex ↔ decimal ↔ binary conversions
- **Derive conclusions from analysis**, not assumptions — no guessing based on game knowledge alone
- Use `analyze_batch` or `analyze_component` for deep multi-function analysis rather than calling `decompile` repeatedly in isolation

## Documentation Structure

Store all reverse engineering findings under `RE/`:

```
RE/
  <topic>_findings.md    # per-topic analysis results
  <component>.md         # structural / architectural notes
```

Save the IDA database after significant annotation sessions using `idb_save`.

## Multi-Instance / Agent Workflows

If running coordinated analysis with multiple agents, see `C:\Tools\MCP_dev\ida-pro-mcp\AGENT.md` for the full worker protocol (registration, polling loop, checkpoint protocol, cross-agent coordination). The `mcp-comms` server runs at `http://127.0.0.1:8765/mcp` when active.
