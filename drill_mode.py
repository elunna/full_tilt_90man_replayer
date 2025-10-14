import json
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Any

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


def _canon_token(tok: str) -> str:
    """
    Canonicalize a range token to match normalize_hand() output style:
    - Pairs are like 'TT'
    - Non-pairs are like 'K8o' or 'AJs' (upper-case ranks, lower-case suitedness)
    """
    t = tok.strip()
    if len(t) == 2:
        return t.upper()
    if len(t) == 3:
        return t[0].upper() + t[1].upper() + t[2].lower()
    return t


def _expand_plus_token(token: str) -> Set[str]:
    """
    Expand shorthand like:
      - 'TT+'  -> {'TT','JJ','QQ','KK','AA'}
      - 'A9s+' -> {'A9s','ATs','AJs','AQs','AKs'}
      - 'K9o+' -> {'K9o','KTo','KJo','KQo'}  (offsuit up to just below 'K' high)
    """
    out: Set[str] = set()
    t = token.strip()
    if not t.endswith('+'):
        return { _canon_token(t) }

    base = _canon_token(t[:-1])

    # Pairs like 'TT+'
    if len(base) == 2 and base[0] == base[1]:
        start = RANKS.index(base[0])
        for i in range(start, len(RANKS)):
            r = RANKS[i]
            out.add(f"{r}{r}")
        return out

    # Suited/off-suit hands like 'A9s+' or 'K9o+'
    if len(base) == 3 and base[0] != base[1] and base[2] in ('s', 'o'):
        hi, lo, suited = base[0], base[1], base[2]
        hi_idx = RANKS.index(hi)
        lo_idx = RANKS.index(lo)

        # Always include the base hand itself (e.g., include 'K8o' in 'K8o+')
        out.add(base)

        # Increase the low rank up to the rank just below the high rank.
        # This avoids generating pairs (e.g., 'KKo') and avoids crossing to 'A' when hi != 'A'.
        max_lo_idx = hi_idx - 1  # e.g., for 'K', this is 'Q'; for 'A', this is 'K'
        for i in range(lo_idx + 1, max_lo_idx + 1):
            next_lo = RANKS[i]
            out.add(f"{hi}{next_lo}{suited}")
        return out

    # Fallback: return the canonicalized token as-is
    return { base }


def expand_plus_notation(tokens: List[str]) -> Set[str]:
    """Expand a list that may include '+' shorthand and return a set of explicit combos."""
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


@dataclass
class DrillConfig:
    """Represents one drill discovered from a JSON file."""
    title: str
    actions: Tuple[str, str]  # (in_range_action, out_of_range_action) e.g., ("raise","fold")
    positions: Dict[str, List[str]]  # position -> list of tokens, e.g., ["77+","AJs",...]
    source_path: str


def discover_drills(ranges_dir: Optional[str] = None) -> List[DrillConfig]:
    """
    Scan the ranges directory for *.json, read 'drill_title' and 'actions',
    and collect the remaining top-level keys as positions.

    Backward compatible: if 'drill_title'/'actions' are missing, a title is
    derived from the filename and actions default to ('raise','fold').
    """
    base = ranges_dir or os.path.join(os.path.dirname(__file__), "ranges")
    drills: List[DrillConfig] = []
    if not os.path.isdir(base):
        return drills

    for fname in os.listdir(base):
        if not fname.lower().endswith(".json"):
            continue
        fpath = os.path.join(base, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            continue

        # Read metadata
        title = data.get("drill_title") or os.path.splitext(fname)[0].replace("_", " ").title()
        actions_list = data.get("actions") or ["raise", "fold"]
        # Normalize to two actions
        if not isinstance(actions_list, list) or len(actions_list) < 2:
            actions_list = ["raise", "fold"]
        actions = (str(actions_list[0]).lower(), str(actions_list[1]).lower())

        # Collect positions from any non-meta top-level keys
        positions: Dict[str, List[str]] = {}
        for k, v in data.items():
            if k in ("drill_title", "actions"):
                continue
            if isinstance(v, list):
                positions[k] = v

        # Skip empty drills
        if not positions:
            continue

        drills.append(DrillConfig(title=title, actions=actions, positions=positions, source_path=fpath))
    return drills


class OpeningRangeDrill:
    """
    Raise/fold style drill (or any two-action drill) driven by a DrillConfig.
    Determines the 'in-range' action by checking whether hero's hand is in
    the configured open range for the dealt position.
    """

    def __init__(self, config: DrillConfig, questions: int = 20):
        self.config = config
        self.questions = questions
        self.result = DrillResult()
        self._expanded_by_pos: Dict[str, Set[str]] = {
            pos: expand_plus_notation(tokens) for pos, tokens in config.positions.items()
        }
        self._positions: List[str] = list(self._expanded_by_pos.keys())
        self._current_q: Optional[Dict[str, Any]] = None
        self._rng = random.Random()

    def _deal_two(self) -> Tuple[str, str]:
        ranks = list(RANKS)
        suits = list(SUITS)
        # Simple 52-card sample without replacement
        deck = [r + s for r in ranks for s in suits]
        c1 = self._rng.choice(deck)
        deck.remove(c1)
        c2 = self._rng.choice(deck)
        return c1.upper(), c2.upper()

    def _make_question(self) -> Dict[str, Any]:
        pos = self._rng.choice(self._positions)
        c1, c2 = self._deal_two()
        key = normalize_hand(c1, c2)
        in_range = key in self._expanded_by_pos[pos]
        in_action, out_action = self.config.actions
        answer = in_action if in_range else out_action
        return {
            "position": pos,
            "hero_cards": (c1, c2),
            "key": key,
            "answer": answer,
        }

    def start(self) -> Dict[str, Any]:
        self.result = DrillResult(total=0, correct=0, start_ts=time.time(), end_ts=0.0)
        self._current_q = self._make_question()
        return self._current_q

    def submit(self, user_action: str) -> Tuple[bool, Dict[str, Any]]:
        """Return (correct, snapshot_of_current_question)."""
        if not self._current_q:
            raise RuntimeError("No active question")
        snap = dict(self._current_q)  # shallow copy
        correct = (user_action.lower() == snap["answer"])
        self.result.total += 1
        if correct:
            self.result.correct += 1
        return correct, snap

    def next_question(self) -> Optional[Dict[str, Any]]:
        if self.result.total >= self.questions:
            self.result.end_ts = time.time()
            self._current_q = None
            return None
        self._current_q = self._make_question()
        return self._current_q

    def summary(self) -> Dict[str, Any]:
        total = max(1, self.result.total)
        pct = int(round(100.0 * self.result.correct / total))
        grade = (
            "A" if pct >= 90 else
            "B" if pct >= 80 else
            "C" if pct >= 70 else
            "D" if pct >= 60 else
            "F"
        )
        return {"correct": self.result.correct, "total": self.result.total, "percent": pct, "grade": grade}