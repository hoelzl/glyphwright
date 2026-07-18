"""Lockpicking: the minigame that proves the mode interface is general.

A mode is a vocabulary, a handler, and a view; because this one implements
exactly those three things, it inherits determinism, replay, fold
equivalence, enumeration-driven fuzzing, and golden transcripts for free
(design 0003 §10.3). Three pins must click in a row; a slip resets the lock.
"""

from __future__ import annotations

from glyphwright.frames.frame import (
    ActorSummary,
    LockView,
    PromptSpec,
    SemanticFrame,
)
from glyphwright.kernel.commands import Abort, Command, CommandGrammar, Look, Pick
from glyphwright.kernel.events import (
    Event,
    FocusSet,
    MinigameResolved,
    ModePopped,
    ModePushed,
    PinSet,
    PinSlipped,
    TurnAdvanced,
)
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_LOCKPICK, PLAYER, WorldState
from glyphwright.modes import common, messages

NAME = MODE_LOCKPICK

VERBS = frozenset({"pick", "abort", "look"})

PINS = 3
# A pick sets the next pin on d20 >= 9 (60%): a lock that usually opens in a
# handful of turns but keeps its teeth.
_CLICK_AT = 9


def open_events(state: WorldState, target: str) -> tuple[Event, ...]:
    """The events that begin working a lock, for exploration's ``open``."""
    return (ModePushed(mode=NAME), FocusSet(entity=target, detail="0"))


def _lock(state: WorldState) -> tuple[str, int]:
    assert state.focus is not None, "lockpicking always has a focused lock"
    target, detail = state.focus
    return target, int(detail)


def available_commands(state: WorldState) -> CommandGrammar:
    return CommandGrammar(verbs=(("pick", ()), ("abort", ()), ("look", ())))


def handle(
    state: WorldState, command: Command, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    match command:
        case Look():
            return (), rng
        case Pick():
            return _pick(state, rng)
        case Abort():
            return (
                ModePopped(mode=NAME, outcome="abandoned"),
                TurnAdvanced(turn=state.turn + 1),
            ), rng
        case _:
            raise ValueError(f"lockpick cannot handle {command.verb!r}")


def _pick(state: WorldState, rng: Rng) -> tuple[tuple[Event, ...], Rng]:
    target, pins = _lock(state)
    roll, rng = rng.between(1, 20)
    turn = TurnAdvanced(turn=state.turn + 1)
    if roll < _CLICK_AT:
        return (
            PinSlipped(target=target),
            FocusSet(entity=target, detail="0"),
            turn,
        ), rng

    pins += 1
    events: list[Event] = [PinSet(target=target, pins=pins)]
    if pins < PINS:
        events.append(FocusSet(entity=target, detail=str(pins)))
    else:
        events.append(
            MinigameResolved(minigame="lockpick", outcome="opened", target=target)
        )
        events.append(ModePopped(mode=NAME, outcome="opened"))
        events.extend(common.unlock_events(state, target))
    events.append(turn)
    return tuple(events), rng


def view(state: WorldState, events: tuple[Event, ...]) -> SemanticFrame:
    target, pins = _lock(state)
    player_at = state.entity(PLAYER).at()
    assert player_at is not None
    player = state.entity(PLAYER)
    assert player.actor is not None
    return SemanticFrame(
        turn=state.turn,
        mode=NAME,
        viewport=LockView(area=player_at.area, target=target, pins=pins, total=PINS),
        actors=(ActorSummary.of(player, player_at),),
        messages=tuple(
            message for event in events if (message := messages.describe(event))
        ),
        prompt=PromptSpec(kind="command"),
        commands=available_commands(state),
    )
