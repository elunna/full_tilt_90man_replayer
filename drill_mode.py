import json
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def normalize_hand(card1: str, card2: str) -> str:
    """Return canonical key like 'AJo', 'KTs', '77' from two cards like 'As', 'Td'."""
    r1, s1 = card1[0], card1[1]
    r2, s2 = card2[0], card2[1]
    if r1 == r2:
        return f"{r1}{r2}"
    i1, i2 = RANKS.index(r1), RANKS.index(r2)
    hi, lo = (r1, r2) if i1 > i2 else (r2, r1)
    suited = (s1 == s2)
    return f"{hi}{lo}{'s' if suited else 'o'}"


def _expand_plus_token(token: str) -> Set[str]:
    """
    Expand shorthand like:
      - 'TT+' -> {'TT','JJ','QQ','KK','AA'}
      - 'A9s+' -> {'A9s','ATs','AJs','AQs','AKs'}
      - 'K9o+' -> {'K9o','KTo','KJo','KQo','KAo' (invalid, up to 'A' so KAo not a thing)} -> should stop at 'A'
    Note: For offsuit/suited non-pair, we increase the lower rank up to but including 'K' then 'A'.
    """
    out: Set[str] = set()
    if token.endswith('+'):
        base = token[:-1]
        # Pairs like 'TT+'
        if len(base) == 2 and base[0] == base[1]:
            start = RANKS.index(base[0])
            for i in range(start, len(RANKS)):
                r = RANKS[i]
                out.add(f"{r}{r}")
            return out
        # Hands like 'A9s+' or 'K9o+'
        if len(base) == 3 and base[0] != base[1]:
            hi, lo, suited = base[0], base[1], base[2]
            lo_start = RANKS.index(lo)
            # increase low rank until A
            for i in range(lo_start, len(RANKS) - 1):
                next_lo = RANKS[i + 1]
                out.add(f"{hi}{next_lo}{suited}")
            return out
    return {token}


def expand_plus_notation(tokens: List[str]) -> Set[str]:
    """
    Expand a list that may include '+' shorthand and return a set of explicit combos.
    Supported patterns:
      - Pairs: '22+', 'TT+'
      - Suited/offsuit: 'A9s+', 'K9o+'
    """
    expanded: Set[str] = set()
    for t in tokens:
        expanded |= _expand_plus_token(t)
    return expanded


@dataclass
class DrillResult:
    total: int = 0
    correct: int = 0
    start_ts: float = 0.0
    end_ts: float = 0.0


class OpeningRangeDrill:
    """
    Simple raise/fold opening-range drill across random positions.
    """
    POSITIONS = ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB", "BB"]

    def __init__(self, ranges_path: Optional[str] = None, questions: int = 20):
        if ranges_path is None:
            # default to ranges/opening_ranges.json next to this file
            ranges_path = os.path.join(os.path.dirname(__file__), "ranges", "opening_ranges.json")
        self.questions = questions
        self.ranges_path = ranges_path
        self.ranges: Dict[str, Set[str]] = self._load_ranges(ranges_path)
        self._deck: List[str] = []
        self.result = DrillResult()
        self.current: Optional[Dict[str, object]] = None  # {'position', 'hero_cards', 'key', 'answer'}

    def _load_ranges(self, path: str) -> Dict[str, Set[str]]:
        with open(path, "r") as f:
            data = json.load(f)
        expanded: Dict[str, Set[str]] = {}
        for pos, hands in data.items():
            expanded[pos] = expand_plus_notation(hands)
        return expanded

    def _fresh_deck(self) -> None:
        self._deck = [r + s for r in RANKS for s in SUITS]
        random.shuffle(self._deck)

    def _deal(self, n: int) -> List[str]:
        if len(self._deck) < n:
            self._fresh_deck()
        return [self._deck.pop() for _ in range(n)]

    def start(self) -> Dict[str, object]:
        self.result = DrillResult(total=0, correct=0, start_ts=time.time(), end_ts=0.0)
        self._fresh_deck()
        q = self.next_question()
        assert q is not None
        return q

    def next_question(self) -> Optional[Dict[str, object]]:
        if self.result.total >= self.questions:
            return None
        pos = random.choice(self.POSITIONS)
        hero_cards = self._deal(2)
        key = normalize_hand(hero_cards[0], hero_cards[1])
        answer = "raise" if key in self.ranges.get(pos, set()) else "fold"
        self.current = {"position": pos, "hero_cards": hero_cards, "key": key, "answer": answer}
        return self.current

    def submit(self, user_choice: str) -> Tuple[bool, Dict[str, object]]:
        """
        user_choice: 'raise' | 'fold'
        Returns: (correct, current_question_snapshot)
        """
        if self.current is None:
            raise RuntimeError("No active question")
        correct = (user_choice == self.current["answer"])
        if correct:
            self.result.correct += 1
        self.result.total += 1
        # return a copy to avoid external mutation
        return correct, dict(self.current)

    def summary(self) -> Dict[str, object]:
        self.result.end_ts = time.time()
        pct = int(round(100.0 * (self.result.correct / max(1, self.result.total))))
        grade = "A" if pct >= 90 else "B" if pct >= 80 else "C" if pct >= 70 else "D" if pct >= 60 else "F"
        duration_ms = int((self.result.end_ts - self.result.start_ts) * 1000)
        return {
            "total": self.result.total,
            "correct": self.result.correct,
            "percent": pct,
            "grade": grade,
            "duration_ms": duration_ms,
        }
