---
name: add-an-item
description: Add an item to a GlyphWright pack, or a new kind of item to the engine (a new consumable effect, equipment slot rule, or item component), with a test. Use when a world needs a new item or an item needs to do something no item does yet.
---

# Add an item

First decide which of the two you need. An item that heals, or that changes
stats while worn, is content: step 1 only. An item that does anything else is
a new kind, which needs engine code: steps 2 to 5.

## 1. A new item of an existing kind

Add an entity with an `[entity.item]` table and a `consumable` or
`equippable` table, as `potion-minor` and `iron-sword` in the reference world
do; the keys are in the
[pack format](../../../docs/authoring/pack-format.md). Load and play the pack
(the author-a-pack skill), then `take`, `use`, or `equip` it. If you changed
the reference world, run `uv run python tests/regenerate_goldens.py` and
`uv run python tests/regenerate_recordings.py`, and review the golden diff.

## 2. Plan the new kind

Read the [kernel page](../../../docs/knowledge/kernel.md#items-and-stats) and
the [content-pack page](../../../docs/knowledge/content-packs.md) first. Write
down, before any code:

- the component and its keys, and the content rules a pack must satisfy;
- the event its use produces, and what that event does to state;
- when the grammar offers it: item verbs offer only items the command would
  work on.

## 3. Write the test first

Add a test in `tests/test_items.py` on a hand-built room, as the tests there
do: the item is offered, using it emits the event you planned, the state
changes as planned, and it is not offered when it could do nothing. Run it and
watch it fail.

## 4. Implement it

- **The component:** follow "Adding a key or a component" in the
  [content-pack page](../../../docs/knowledge/content-packs.md#adding-a-key-or-a-component).
- **A new event:** follow "Adding a command or an event" in the
  [kernel page](../../../docs/knowledge/kernel.md#adding-a-command-or-an-event).
- **Using it:** extend `usable_items` and `use_item` in
  `src/glyphwright/modes/common.py`, so exploration and battle both offer it.

## 5. Run every gate

```bash
uv run python -m glyphwright.harness.schema       # if a wire shape changed
uv run python -m glyphwright.harness.reference    # if a command changed
uv run python scripts/check.py
```

A new event bumps `EVENT_SCHEMA`, which changes every recorded digest, so
also bump `RULES` in `src/glyphwright/harness/fingerprint.py` and run
`uv run python tests/regenerate_recordings.py`. If the pinned recording fails
for another reason, its message says what to do;
[replay and determinism](../../../docs/knowledge/replay-and-determinism.md#the-rules-revision-and-the-pin)
explains. Done means the check passes.
