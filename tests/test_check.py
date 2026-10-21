from collections.abc import Sequence

import check
import pytest


def test_every_gate_runs_even_after_a_failure() -> None:
    seen: list[str] = []

    def runner(command: Sequence[str]) -> int:
        seen.append(command[-1])
        return 1 if command[-1] == "fail" else 0

    gates = (("a", ("x", "fail")), ("b", ("x", "ok")))
    assert check.run_gates(gates, runner) == ["a"]
    assert seen == ["fail", "ok"]


def test_list_prints_the_gates(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "documentation: scripts/docs_tool.py check" in out
    assert out.count("\n") == len(check.GATES)
