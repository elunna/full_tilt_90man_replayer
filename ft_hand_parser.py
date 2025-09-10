import re
import sys
from typing import List, Dict, Any

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
            'actions': [],
            'summary': {},
        }
        # Updated regex to match your example!
        player_re = re.compile(r"Seat\s+(\d+):\s+(.+?)\s+\(([\d,]+)\)")
        action_re = re.compile(r"^(.+?): (bets|calls|raises|checks|folds)(.*)")
        summary_section = False
        hole_cards_section = False

        for line in lines[1:]:
            if line.startswith('*** HOLE CARDS ***'):
                hole_cards_section = True
            if not hole_cards_section and line.startswith('Seat '):
                m = player_re.match(line)
                if m:
                    hand_info['players'].append({
                        'seat': int(m.group(1)),
                        'name': m.group(2).strip(),
                        'chips': int(m.group(3).replace(',', ''))
                    })
            elif action_re.match(line):
                m = action_re.match(line)
                if m:
                    hand_info['actions'].append({
                        'player': m.group(1),
                        'action': m.group(2),
                        'detail': m.group(3).strip()
                    })
            elif line.startswith('*** SUMMARY ***'):
                summary_section = True
            elif summary_section:
                if ':' in line:
                    k, v = line.split(':', 1)
                    hand_info['summary'][k.strip()] = v.strip()
        return hand_info

    def print_summary(self):
        print(f"Parsed {len(self.hands)} hands.")
        for i, hand in enumerate(self.hands[:3]):
            print(f"\nHand {i+1} header: {hand['header']}")
            print(f"Players: {[p['name'] for p in hand['players']]}")
            print(f"First 5 actions: {hand['actions'][:5]}")
            print(f"Summary: {hand['summary']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ft_hand_parser.py <hand_history_file>")
        sys.exit(1)
    parser = FullTiltHandParser(sys.argv[1])
    parser.parse()
    parser.print_summary()
