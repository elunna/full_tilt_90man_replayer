# (no changes required for session panel)
import re
import sys
import pprint
from typing import List, Dict, Any

# Hand info for each hand
# Small blind
# Big Blind
# ante

class FullTiltHandParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.hands = []

    def parse(self):
        with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
            hand_lines = []
            hand_start_lineno = 1  # track where current hand begins in the file
            for lineno, raw_line in enumerate(f, start=1):
                line = raw_line.rstrip('\n')
                if line.startswith('Full Tilt Poker Game #'):
                    if hand_lines:
                        try:
                            self.hands.append(self.parse_hand(hand_lines))
                        except Exception as e:
                            header_preview = hand_lines[0] if hand_lines else "<no header>"
                            raise RuntimeError(
                                f"Error parsing hand starting at line {hand_start_lineno}: "
                                f"{e}\nHeader: {header_preview}"
                            ) from e
                        hand_lines = []
                    hand_start_lineno = lineno
                hand_lines.append(line)
            if hand_lines:
                try:
                    self.hands.append(self.parse_hand(hand_lines))
                except Exception as e:
                    header_preview = hand_lines[0] if hand_lines else "<no header>"
                    raise RuntimeError(
                        f"Error parsing hand starting at line {hand_start_lineno}: "
                        f"{e}\nHeader: {header_preview}"
                    ) from e

    def parse_hand(self, lines: List[str]) -> Dict[str, Any]:
        hand_info = {
            'header': lines[0] if lines else "",
            'button_seat': None,
            'players': [],
            'actions': {
                'preflop': [],
                'flop': [],
                'turn': [],
                'river': [],
            },
            'summary': {},
            'hero': None,  # Store hero name
            'hole_cards': None,  # Store hero's hole cards
            'board': {'flop': [], 'turn': [], 'river': []},  # Community cards
        }
        player_re = re.compile(r"Seat\s+(\d+):\s+(.+?)\s+\(([\d,]+)\)")
        action_re = re.compile(r"^(.+?) (bets|calls|raises|checks|folds|shows|collected|posts|antes|mucks|wins|is sitting out|has returned)(.*)")
        button_re = re.compile(r"The button is in seat #(\d+)", re.IGNORECASE)
        summary_section = False

        # Track which street we're in
        current_street = 'preflop'
        street_markers = {
            'preflop': '*** HOLE CARDS ***',
            'flop': '*** FLOP ***',
            'turn': '*** TURN ***',
            'river': '*** RIVER ***',
            'summary': '*** SUMMARY ***'
        }

        hole_cards_section = False

        for line in lines[1:]:
            # Dealer button seat (e.g., "The button is in seat #7")
            m_btn = button_re.search(line)
            if m_btn:
                hand_info['button_seat'] = int(m_btn.group(1))
                continue

            if line.startswith(street_markers['flop']):
                # Example: "*** FLOP *** [Ah Kd 7h]"
                current_street = 'flop'
                m = re.search(r'\[([^\]]+)\]', line)
                if m:
                    cards = [c.strip() for c in m.group(1).strip().split() if c.strip()]
                    hand_info['board']['flop'] = cards
                    # Insert synthetic action so replayer steps on board reveal
                    hand_info['actions']['flop'].append({
                        'player': 'Board',
                        'action': 'board',
                        'detail': f"flop [{m.group(1).strip()}]"
                    })
                continue
            elif line.startswith(street_markers['turn']):
                # Example: "*** TURN *** [Ah Kd 7h] [Qc]"
                current_street = 'turn'
                # The last [...] holds the new card
                parts = re.findall(r'\[([^\]]+)\]', line)
                if parts:
                    turn_card = parts[-1].strip()
                    hand_info['board']['turn'] = [c.strip() for c in turn_card.split() if c.strip()]
                    hand_info['actions']['turn'].append({
                        'player': 'Board',
                        'action': 'board',
                        'detail': f"turn [{turn_card}]"
                    })
                continue
            elif line.startswith(street_markers['river']):
                # Example: "*** RIVER *** [Ah Kd 7h Qc] [2d]"
                current_street = 'river'
                parts = re.findall(r'\[([^\]]+)\]', line)
                if parts:
                    river_card = parts[-1].strip()
                    hand_info['board']['river'] = [c.strip() for c in river_card.split() if c.strip()]
                    hand_info['actions']['river'].append({
                        'player': 'Board',
                        'action': 'board',
                        'detail': f"river [{river_card}]"
                    })
                continue
            elif line.startswith(street_markers['summary']):
                summary_section = True
                continue
            elif line.startswith(street_markers['preflop']):
                hole_cards_section = True
                continue

            if hole_cards_section:
                match = re.match(r"Dealt to\s+(.+?)\s+\[(.+?)\]", line)
                if match:
                    hand_info['hero'] = match.group(1).strip()
                    hand_info['hole_cards'] = match.group(2).strip()
                    hole_cards_section = False
                    #print(hand_info['hero'])
                    # print(hand_info['hole_cards'])
                    continue

            if not summary_section and line.startswith('Seat '):
                m = player_re.match(line)
                if m:
                    # Detect "is sitting out" status if present in the seat line
                    sitting_out = ('is sitting out' in line.lower())
                    hand_info['players'].append({
                        'seat': int(m.group(1)),
                        'name': m.group(2).strip(),
                        'chips': int(m.group(3).replace(',', '')),
                        # Optional per-hand initial status
                        'sitting_out': sitting_out
                    })
            elif summary_section:
                if ':' in line:
                    k, v = line.split(':', 1)
                    hand_info['summary'][k.strip()] = v.strip()
            elif action_re.match(line):
                m = action_re.match(line)
                if m:
                    hand_info['actions'][current_street].append({
                        'player': m.group(1),
                        'action': m.group(2),
                        'detail': m.group(3).strip()
                    })
        return hand_info

    def check_voluntary_investment(self, hand_history):
        """
        Check if the hero voluntarily invested money in the hand.
        This excludes posting blinds or antes and folding.
        """
        hero_actions = self.extract_hero_actions(hand_history)
        for action in hero_actions:
            if action in {"bets", "calls", "raises"}:
                return True
        return False
    
    def print_summary(self):
        print(f"Parsed {len(self.hands)} hands.")
        for i, hand in enumerate(self.hands[:3]):
            #print(f"\nHand {i+1} header: {hand['header']}")
            #print(f"Players: {[p['name'] for p in hand['players']]}")
            #print()

            for street in ['preflop', 'flop', 'turn', 'river']:
                pprint.pp(f"{street.title()}")
                for a in hand['actions'][street]:
                    print(f"{a['player']} {a['action']} {a['detail']}")
                # pprint.pp(f"{street.title()} actions: {hand['actions'][street]}")
                print()

            # do we need the summary?
            #pprint.pp(f"Summary: {hand['summary']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ft_hand_parser.py <hand_history_file>")
        sys.exit(1)
    parser = FullTiltHandParser(sys.argv[1])
    parser.parse()
    parser.print_summary()
    for hand in parser.hands:
        print(f"Hero: {hand['hero']}, Hole Cards: {hand['hole_cards']}")
