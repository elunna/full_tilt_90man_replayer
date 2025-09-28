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
            for line in f:
                if line.startswith('Full Tilt Poker Game #'):
                    if hand_lines:
                        self.hands.append(self.parse_hand(hand_lines))
                        hand_lines = []
                hand_lines.append(line.rstrip('\n'))
            if hand_lines:
                self.hands.append(self.parse_hand(hand_lines))

    def parse_hand(self, lines: List[str]) -> Dict[str, Any]:
        hand_info = {
            'header': lines[0] if lines else "",
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
        }
        player_re = re.compile(r"Seat\s+(\d+):\s+(.+?)\s+\(([\d,]+)\)")
        action_re = re.compile(r"^(.+?) (bets|calls|raises|checks|folds|shows|collected|posts|antes|mucks|wins)(.*)")
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
            if line.startswith(street_markers['flop']):
                current_street = 'flop'
                continue
            elif line.startswith(street_markers['turn']):
                current_street = 'turn'
                continue
            elif line.startswith(street_markers['river']):
                current_street = 'river'
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
                    hand_info['players'].append({
                        'seat': int(m.group(1)),
                        'name': m.group(2).strip(),
                        'chips': int(m.group(3).replace(',', ''))
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
