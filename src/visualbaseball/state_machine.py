from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class GameState:
    inning: int = 0
    inning_half: str = ""
    balls: int = 0
    strikes: int = 0
    outs: int = 0
    runner_1b_id: str = ""
    runner_2b_id: str = ""
    runner_3b_id: str = ""
    away_score: int = 0
    home_score: int = 0

    def snapshot(self) -> dict:
        result = asdict(self)
        result.update({
            "base_state": self.base_state,
            "base_state_code": self.base_state_code,
            "re24_state_code": self.re24_state_code,
            "re288_state_code": self.re288_state_code,
        })
        return result

    @property
    def base_state(self) -> str:
        return "".join(("1" if self.runner_1b_id else "-", "2" if self.runner_2b_id else "-", "3" if self.runner_3b_id else "-"))

    @property
    def base_state_code(self) -> int:
        return (1 if self.runner_1b_id else 0) + (2 if self.runner_2b_id else 0) + (4 if self.runner_3b_id else 0)

    @property
    def re24_state_code(self) -> int:
        return self.base_state_code * 3 + self.outs

    @property
    def re288_state_code(self) -> int:
        return ((self.re24_state_code * 4 + self.balls) * 3 + self.strikes)

    def begin_half(self, inning: int, inning_half: str) -> None:
        self.inning, self.inning_half = inning, inning_half
        self.balls = self.strikes = self.outs = 0
        self.set_bases({})

    def set_bases(self, bases: dict | None) -> None:
        bases = bases or {}
        for json_key, state_key in (("b1", "runner_1b_id"), ("b2", "runner_2b_id"), ("b3", "runner_3b_id")):
            runner = bases.get(json_key) or {}
            setattr(self, state_key, str(runner.get("id") or ""))

    def apply_non_terminal_pitch(self, code: str) -> None:
        code = (code or "").upper()
        if code == "B":
            self.balls = min(3, self.balls + 1)
        elif code in {"S", "T", "V"}:
            self.strikes = min(2, self.strikes + 1)
        elif code in {"F", "W"} and self.strikes < 2:
            self.strikes += 1
