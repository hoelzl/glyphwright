# Handover — GlyphWright implementation per design 0003

Active multi-session implementation state. Read `docs/agent/design/0003-glyphwright-design.md`
first; it is authoritative over this file. Update this document whenever a slice starts,
finishes, or a decision worth carrying across sessions is made. Retire entries once the
information is recorded in design docs, knowledge bundle, or code.

## Current state (2026-07-17)

| Slice (0003 §18) | Status |
| --- | --- |
| 1 — Walking skeleton | **Done** (kernel, GridSpace, move/look/wait, plain + JSONL frontends, `glyphwright.api`, committed schemas, fingerprint; 82 tests green) |
| 2 — Items and stats | **In progress** (this session) |
| 3 — Battle | Not started |
| 4 — Rooms and portals | Not started |
| 5 — TUI | Not started |
| 6 — Dialogue and one minigame | Not started |

TermVerify-side work (direct adapter, PTY golden) is deliberately not in this repository
yet; adapter placement is open (0003 §20.5) and will be decided when the adapter is built.

## Workflow contract for sessions

- Work on a feature branch; open a PR when a slice (or coherent sub-slice) is green.
- Run an adversarial review on the PR before merging; fix confirmed findings, then merge.
- Full local gate before any PR: pytest with coverage, ruff check, ruff format --check,
  mypy strict, pre-commit (both stages). Commands are in `AGENTS.md`.
- Strict TDD for behavior changes (AGENTS.md completion contract).

## Slice 2 plan and decisions

Scope (0003 §18.2): inventory, `take`/`use`/`equip`, stat pipeline with provenance,
`:query … --explain`.

Decisions taken by the implementing agent (owner delegated open choices):

1. **`use` is arity-1 in slice 2** (`use <item>`, self-targeted). The design's
   `use X on self` surface syntax arrives when battle introduces other targets;
   keeping one argument keeps the grammar→line→parse round trip uniform.
2. **Equipment model:** equipped items stay in the inventory; an `Equipment` component
   maps slot → item id. `equip` into an occupied slot replaces (event carries what was
   replaced); no separate unequip verb yet.
3. **Consumables are destroyed on use:** `ItemUsed(consumed=True)` removes the item
   entity in the fold.
4. **New event types extend `glyphwright.event/1` additively** (enum of `type` widened,
   new optional fields). Pre-1.0 additive widening does not bump the tag; the committed
   schema files change deliberately in the same PR.
5. **Meta-channel in slice 2 ships `:query <path> [--explain]`, `:seed`, `:frame --json`**;
   `:events --since`, `:save`/`:load` are deferred until a consumer needs them
   (snapshots already exist via the API).
6. **Stat pipeline lives in `effects/stats.py`**: base → additive → multiplicative →
   clamps; every modifier carries provenance (source id + kind). Equipment is the only
   modifier source in slice 2; statuses/perks arrive with battle.

## Next steps

1. Finish slice 2 (see task breakdown in session, or re-derive from §18.2).
2. Slice 3 — battle: menu battle first, shared scheduler (§5.5, ADR-004), then tactics
   arena reusing GridSpace. Statuses/perks hook into the event fold (§9.3).
3. Slice 4 — rooms and portals: `RoomGraphSpace`, mixed-world reference pack.
   `C:\Users\tc\Programming\TypeScript\Projects\Riches` may be browsed for room-mode
   inspiration/assets (owner note: not authoritative, no 1-1 replication).
4. Slice 5 — TUI (decide Textual vs hand-rolled with a spike, §20.1).
5. Slice 6 — dialogue + one minigame.
