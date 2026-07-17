"""Dialogue: a conversation as an ordinary mode (design 0003 §10.2).

The tree is content on the speaker's entity; this mode walks it. Lines and
choices are events, the cursor is ``FocusSet``, and ``choose N`` is the whole
vocabulary — so a conversation replays, folds, and fuzzes like everything
else.
"""

from __future__ import annotations

from glyphwright.frames.frame import (
    ActorSummary,
    DialogueView,
    PromptSpec,
    SemanticFrame,
)
from glyphwright.kernel.commands import Choose, Command, CommandGrammar, Look
from glyphwright.kernel.events import (
    ChoiceOffered,
    DialogueLine,
    Event,
    FlagSet,
    FocusSet,
    ModePopped,
    ModePushed,
    TurnAdvanced,
)
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_DIALOGUE, PLAYER, WorldState
from glyphwright.modes import messages
from glyphwright.world.entities import Dialogue

NAME = MODE_DIALOGUE

VERBS = frozenset({"choose", "look"})


def _tree(state: WorldState) -> tuple[str, Dialogue]:
    assert state.focus is not None, "dialogue mode always has a focused speaker"
    speaker, _ = state.focus
    dialogue = state.entity(speaker).dialogue
    assert dialogue is not None, "the focused speaker carries the tree"
    return speaker, dialogue


def _current_choices(state: WorldState) -> tuple[str, ...]:
    _, dialogue = _tree(state)
    assert state.focus is not None
    node = dialogue.node(state.focus[1])
    return tuple(choice.text for choice in node.choices)


def open_events(state: WorldState, speaker: str) -> tuple[Event, ...]:
    """The events that start a conversation, for exploration's ``talk``."""
    dialogue = state.entity(speaker).dialogue
    assert dialogue is not None, "the grammar only offers speakers with trees"
    node = dialogue.node(dialogue.root)
    return (
        ModePushed(mode=NAME),
        FocusSet(entity=speaker, detail=node.id),
        DialogueLine(speaker=speaker, text=node.line),
        ChoiceOffered(speaker=speaker, choices=tuple(c.text for c in node.choices)),
    )


def available_commands(state: WorldState) -> CommandGrammar:
    numbers = tuple(str(i + 1) for i in range(len(_current_choices(state))))
    return CommandGrammar(verbs=(("choose", (numbers,)), ("look", ())))


def handle(
    state: WorldState, command: Command, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    match command:
        case Look():
            return (), rng
        case Choose(choice=number):
            return _choose(state, int(number)), rng
        case _:
            raise ValueError(f"dialogue cannot handle {command.verb!r}")


def _choose(state: WorldState, number: int) -> tuple[Event, ...]:
    speaker, dialogue = _tree(state)
    assert state.focus is not None
    node = dialogue.node(state.focus[1])
    choice = node.choices[number - 1]

    events: list[Event] = []
    if choice.sets_flag is not None and not state.flags.get(choice.sets_flag):
        events.append(FlagSet(flag=choice.sets_flag, value=True))
    if choice.next is None:
        events.append(ModePopped(mode=NAME, outcome="done"))
    else:
        next_node = dialogue.node(choice.next)
        events.extend(
            (
                FocusSet(entity=speaker, detail=next_node.id),
                DialogueLine(speaker=speaker, text=next_node.line),
                ChoiceOffered(
                    speaker=speaker,
                    choices=tuple(c.text for c in next_node.choices),
                ),
            )
        )
    events.append(TurnAdvanced(turn=state.turn + 1))
    return tuple(events)


def view(state: WorldState, events: tuple[Event, ...]) -> SemanticFrame:
    speaker, dialogue = _tree(state)
    assert state.focus is not None
    node = dialogue.node(state.focus[1])
    player_at = state.entity(PLAYER).at()
    assert player_at is not None
    return SemanticFrame(
        turn=state.turn,
        mode=NAME,
        viewport=DialogueView(
            area=player_at.area,
            speaker=speaker,
            text=node.line,
            choices=tuple(choice.text for choice in node.choices),
        ),
        actors=_actors(state, speaker),
        messages=tuple(
            message for event in events if (message := messages.describe(event))
        ),
        prompt=PromptSpec(kind="choice"),
        commands=available_commands(state),
    )


def _actors(state: WorldState, speaker: str) -> tuple[ActorSummary, ...]:
    summaries = []
    for entity_id in sorted({PLAYER, speaker}):
        entity = state.entity(entity_id)
        at = entity.at()
        if entity.actor is None or at is None:
            continue
        summaries.append(
            ActorSummary(
                id=entity.id,
                name=entity.actor.name,
                hp=entity.actor.hp,
                max_hp=entity.actor.max_hp,
                at=at,
                statuses=entity.statuses.ids() if entity.statuses else (),
            )
        )
    return tuple(summaries)
