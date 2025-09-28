import tkinter as tk
from tkinter import filedialog, messagebox
import math
import re
from ft_hand_parser import FullTiltHandParser

SEATS = 9
CARD_WIDTH = 60
CARD_HEIGHT = 80
SEAT_RADIUS = 44
CARD_OFFSET_PX = 70  # Increased to move cards further inward

def detect_hero_in_hand(hand):
    """Parse lines in HOLE CARDS section, look for 'Dealt to {player name}'."""
    if 'raw_lines' in hand:
        lines = hand['raw_lines']
    else:
        lines = [hand['header']]
        for street in ['preflop', 'flop', 'turn', 'river']:
            for act in hand['actions'][street]:
                lines.append(f"{act['player']} {act['action']} {act['detail']}")
    hero = None
    in_hole_cards = False
    for line in lines:
        if "*** HOLE CARDS ***" in line:
            in_hole_cards = True
            continue
        if in_hole_cards:
            m = re.match(r"Dealt to\s+(.+?)\s+\[", line)
            if m:
                hero = m.group(1).strip()
                break
        if in_hole_cards and line.startswith("***"):
            break
    return hero

def get_hero_result(hand, hero=None):
    if not hero:
        hero = detect_hero_in_hand(hand)
    if not hero:
        return 0
    # Scan all actions for hero wins or ties
    for street in ['preflop', 'flop', 'turn', 'river']:
        for act in hand['actions'][street]:
            # Win
            if act['action'] == 'wins' and act['player'] == hero:
                return 1
            # Split pot detection
            if act['player'] == hero and (
                'ties for the side pot' in act.get('detail', '') or
                'ties for the pot' in act.get('detail', '') or
                act['action'].startswith('ties for')
            ):
                return 1
    return -1

class HandReplayerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Full Tilt 90-Man Tournament Replayer")

        self.parser = None
        self.hands = []
        self.heroes = []
        self.current_hand_index = None
        self.current_street = None
        self.current_action_index = None
        self.folded_players = set()
        self.player_cards = {}

        self.hand_boxes = []
        self.build_gui()

    def build_gui(self):
        # Top: main content area (left: table; right: hand playback)
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill='both', expand=True)

        # Table (left side)
        left_frame = tk.Frame(main_frame)
        left_frame.pack(side='left', fill='both', expand=True)

        # Hand Playback (right side)
        right_frame = tk.Frame(main_frame)
        right_frame.pack(side='right', fill='y')

        # File selection (top of left frame)
        file_frame = tk.Frame(left_frame)
        file_frame.pack(fill='x')
        tk.Button(file_frame, text="Open Hand History", command=self.open_file).pack(side='left')
        self.file_label = tk.Label(file_frame, text="No file loaded")
        self.file_label.pack(side='left', padx=10)

        # Table display using Canvas (fills available space)
        self.canvas_frame = tk.Frame(left_frame)
        self.canvas_frame.pack(padx=10, pady=10, fill='both', expand=True)
        self.table_canvas = tk.Canvas(self.canvas_frame, width=1000, height=600, bg="green")
        self.table_canvas.pack(fill='both', expand=True)
        self.table_canvas.bind('<Configure>', self.on_canvas_resize)

        # Hand playback/info display (right side, fills right)
        action_info_label = tk.Label(right_frame, text="Hand Playback")
        action_info_label.pack(pady=(10,0))
        self.action_info_text = tk.Text(right_frame, height=30, width=48, wrap='word', state='disabled', bg="#f6f6f6", font=("Consolas", 11))
        self.action_info_text.pack(fill='both', padx=10, pady=(0,10), expand=True)

        # Bottom bar: hand selector and controls
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(side='bottom', fill='x', pady=(4,4))

        # Hand selector row
        selector_label = tk.Label(bottom_frame, text="Select Hand:")
        selector_label.pack(side='top', anchor='w', padx=(10,0))
        self.hand_selector_frame = tk.Frame(bottom_frame)
        self.hand_selector_frame.pack(side='top', fill='x', padx=(0,10))
        self.hand_selector_canvas = tk.Canvas(self.hand_selector_frame, height=32, bg="#ddd", highlightthickness=0)
        self.hand_selector_canvas.pack(side='top', fill='x', expand=True)
        self.hand_boxes = []

        # Navigation controls (replay controls) - now under hand selector
        controls_frame = tk.Frame(bottom_frame)
        controls_frame.pack(side='top', fill='x', pady=(2,0))
        self.prev_button = tk.Button(controls_frame, text="Prev", command=self.prev_action, state='disabled', width=8)
        self.prev_button.pack(side='left', padx=2)
        self.next_button = tk.Button(controls_frame, text="Next", command=self.next_action, state='disabled', width=8)
        self.next_button.pack(side='left', padx=2)
        self.street_label = tk.Label(controls_frame, text="Street: ")
        self.street_label.pack(side='left', padx=10)
        self.action_label = tk.Label(controls_frame, text="Action: ")
        self.action_label.pack(side='left', padx=10)

    def get_seat_positions(self, seats, cx, cy, a, b):
        positions = []
        for i in range(seats):
            angle = (2 * math.pi * i) / seats - math.pi / 2
            x = cx + a * math.cos(angle)
            y = cy + b * math.sin(angle)
            positions.append((x, y))
        return positions

    def get_card_position(self, seat_x, seat_y, cx, cy, offset_px):
        # Increase inward offset for bottom seats by ~10px to prevent overlap
        if seat_y > cy:  # Bottom half of table
            offset_px += 10
        
        dx = cx - seat_x
        dy = cy - seat_y
        dist = math.hypot(dx, dy)
        if dist == 0:
            return seat_x, seat_y
        nx = dx / dist
        ny = dy / dist
        card_x = seat_x + nx * offset_px
        card_y = seat_y + ny * offset_px
        return card_x, card_y

    def on_canvas_resize(self, event):
        self.update_table_canvas()

    def open_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Full Tilt Hand History",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return
        try:
            self.parser = FullTiltHandParser(file_path)
            self.parser.parse()
            self.hands = self.parser.hands
            self.heroes = []
            for hand in self.hands:
                hero = detect_hero_in_hand(hand)
                self.heroes.append(hero)
            self.file_label.config(text=f"Loaded: {file_path.split('/')[-1]}")
            self.populate_hand_selector()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse file:\n{e}")

    def populate_hand_selector(self):
        self.hand_selector_canvas.delete("all")
        self.hand_boxes.clear()
        box_size = 26
        gap = 4
        y = 3
        for i, hand in enumerate(self.hands):
            hero = self.heroes[i] if i < len(self.heroes) else None
            result = get_hero_result(hand, hero)
            color = "#a9a9a9"
            if result > 0:
                color = "#66cc66"
            elif result < 0:
                color = "#e76c6c"
            x = i * (box_size + gap) + gap
            rect_id = self.hand_selector_canvas.create_rectangle(x, y, x + box_size, y + box_size, fill=color, outline="#333", width=1)
            self.hand_selector_canvas.tag_bind(rect_id, "<Button-1>", lambda e, idx=i: self.select_hand(idx))
            self.hand_boxes.append(rect_id)
        total_width = len(self.hands) * (box_size + gap) + gap
        self.hand_selector_canvas.config(scrollregion=(0,0,total_width,box_size+2*gap))
        if total_width > self.hand_selector_canvas.winfo_width():
            if not hasattr(self, 'selector_scroll'):
                self.selector_scroll = tk.Scrollbar(self.hand_selector_frame, orient='horizontal', command=self.hand_selector_canvas.xview)
                self.selector_scroll.pack(fill='x')
                self.hand_selector_canvas.config(xscrollcommand=self.selector_scroll.set)
        else:
            if hasattr(self, 'selector_scroll'):
                self.selector_scroll.pack_forget()
        if self.hands:
            self.select_hand(0)

    def select_hand(self, idx):
        self.current_hand_index = idx
        hand = self.hands[idx]
        self.folded_players = set()
        self.player_cards = {p['name']: ['??', '??'] for p in hand['players']}
        self.current_street = 'preflop'
        self.current_action_index = 0
        self.update_table_canvas()
        self.update_action_viewer()
        self.display_action_history()
        for i, rect_id in enumerate(self.hand_boxes):
            if i == idx:
                self.hand_selector_canvas.itemconfig(rect_id, width=3, outline="#222")
            else:
                self.hand_selector_canvas.itemconfig(rect_id, width=1, outline="#333")

    def update_table_canvas(self):
        self.table_canvas.delete("all")
        width = self.table_canvas.winfo_width()
        height = self.table_canvas.winfo_height()
        cx = width // 2
        cy = height // 2
        table_a = int(0.43 * width)
        table_b = int(0.39 * height)
        self.table_canvas.create_oval(
            cx - table_a, cy - table_b,
            cx + table_a, cy + table_b,
            fill="#005500", outline="#333", width=4
        )
        seat_positions = self.get_seat_positions(SEATS, cx, cy, table_a, table_b)
        hand = self.hands[self.current_hand_index] if self.hands and self.current_hand_index is not None else None
        seat_map = {p['seat']: p for p in hand['players']} if hand else {}

        for seat in range(1, SEATS + 1):
            x, y = seat_positions[seat - 1]
            r = SEAT_RADIUS
            player = seat_map.get(seat)
            if player:
                is_folded = player['name'] in self.folded_players
                color = "#bbb" if is_folded else "#ffd700"
                self.table_canvas.create_oval(
                    x - r, y - r, x + r, y + r,
                    fill=color, outline="#222", width=2
                )

                # Draw player name and chips in a black box with white text
                self.draw_seat_label(x, y, r, player['name'], player['chips'], cy)

                if not is_folded:
                    # Move cards further inward toward center
                    card_x, card_y = self.get_card_position(x, y, cx, cy, CARD_OFFSET_PX)
                    cards = self.player_cards.get(player['name'], ['??', '??'])
                    self.draw_cards(card_x, card_y, cards, y, cy)
            else:
                self.table_canvas.create_oval(
                    x - r, y - r, x + r, y + r,
                    fill="#444", outline="#222", width=2
                )
                self.table_canvas.create_text(x, y, text="(empty)", font=("Arial", 9))
        pot_radius = int(min(table_a, table_b) * 0.25)
        self.table_canvas.create_oval(
            cx - pot_radius, cy - pot_radius,
            cx + pot_radius, cy + pot_radius,
            fill="#222", outline="#fff", width=3
        )
        self.table_canvas.create_text(cx, cy, text="POT", fill="white", font=("Arial", int(pot_radius * 0.6), "bold"))

    def draw_cards(self, x, y, cards, seat_y=None, cy=None):
        gap = 7
        card_width = CARD_WIDTH
        card_height = CARD_HEIGHT
        
        # For bottom seats, anchor cards upward by half a card height to prevent overlap
        card_anchor_y = y
        if seat_y is not None and cy is not None and seat_y > cy:
            card_anchor_y = y - card_height // 2
        
        for i, card in enumerate(cards):
            cx = x - card_width // 2 + i * (card_width + gap) // 2
            cy_card = card_anchor_y
            self.table_canvas.create_rectangle(
                cx, cy_card, cx + card_width, cy_card + card_height, fill="#fff", outline="#000", width=2
            )
            self.table_canvas.create_text(cx + card_width // 2, cy_card + card_height // 2, text=card, font=("Arial", 15, "bold"))

    def draw_seat_label(self, x, y, r, name, chips, cy):
        """Draw a black box with white text for player info above or below the seat."""
        is_bottom = y > cy
        anchor = 'n' if is_bottom else 's'
        margin = 8
        pad_x = 6
        pad_y = 4

        label_text = f"{name}\n${chips}"
        tx = x
        ty = y + r + margin if is_bottom else y - r - margin

        # Create the text first to measure bbox, then draw a rectangle behind it.
        text_id = self.table_canvas.create_text(
            tx, ty, text=label_text, font=("Arial", 11), fill="white", anchor=anchor
        )
        x1, y1, x2, y2 = self.table_canvas.bbox(text_id)
        rect_id = self.table_canvas.create_rectangle(
            x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y,
            fill="black", outline="#fff", width=1
        )
        # Ensure the rectangle is behind the text
        self.table_canvas.tag_lower(rect_id, text_id)

    def update_action_viewer(self):
        hand = self.hands[self.current_hand_index]
        streets = ['preflop', 'flop', 'turn', 'river']
        actions = hand['actions'][self.current_street]
        self.street_label.config(text=f"Street: {self.current_street.title()}")
        if actions and 0 <= self.current_action_index < len(actions):
            act = actions[self.current_action_index]
            self.action_label.config(text=f"Action: {act['player']} {act['action']} {act['detail']}")
        else:
            self.action_label.config(text="Action: (no action)")
        self.prev_button.config(state='normal' if self.current_action_index > 0 else 'disabled')
        self.next_button.config(state='normal' if self.has_next_action() else 'disabled')
        if actions and 0 <= self.current_action_index < len(actions):
            act = actions[self.current_action_index]
            if act['action'] == 'folds':
                self.folded_players.add(act['player'])
                self.update_table_canvas()
        self.display_action_history()

    def display_action_history(self):
        if not self.hands or self.current_hand_index is None:
            return
        hand = self.hands[self.current_hand_index]
        lines = []
        lines.append(hand['header'])
        lines.append("="*28)
        streets = ['preflop', 'flop', 'turn', 'river']
        for street in streets:
            actions = hand['actions'][street]
            if actions:
                lines.append(f"{street.title()}:")
                if street == self.current_street:
                    idx = self.current_action_index
                    for i, act in enumerate(actions):
                        prefix = "-> " if i == idx else "   "
                        lines.append(f"{prefix}{act['player']} {act['action']} {act['detail']}")
                    break
                else:
                    for act in actions:
                        lines.append(f"   {act['player']} {act['action']} {act['detail']}")
        self.action_info_text.config(state='normal')
        self.action_info_text.delete(1.0, tk.END)
        self.action_info_text.insert(tk.END, "\n".join(lines))
        self.action_info_text.config(state='disabled')

    def has_next_action(self):
        hand = self.hands[self.current_hand_index]
        streets = ['preflop', 'flop', 'turn', 'river']
        actions = hand['actions'][self.current_street]
        if self.current_action_index < len(actions) - 1:
            return True
        idx = streets.index(self.current_street)
        for next_idx in range(idx + 1, len(streets)):
            next_street = streets[next_idx]
            if hand['actions'][next_street]:
                return True
        return False

    def next_action(self):
        hand = self.hands[self.current_hand_index]
        streets = ['preflop', 'flop', 'turn', 'river']
        actions = hand['actions'][self.current_street]
        if self.current_action_index < len(actions) - 1:
            self.current_action_index += 1
            self.update_action_viewer()
        else:
            idx = streets.index(self.current_street)
            next_street_found = False
            for next_idx in range(idx + 1, len(streets)):
                next_street = streets[next_idx]
                if hand['actions'][next_street]:
                    self.current_street = next_street
                    self.current_action_index = 0
                    self.update_action_viewer()
                    next_street_found = True
                    break
            if not next_street_found:
                self.next_button.config(state='disabled')

    def prev_action(self):
        hand = self.hands[self.current_hand_index]
        streets = ['preflop', 'flop', 'turn', 'river']
        actions = hand['actions'][self.current_street]
        if self.current_action_index > 0:
            self.current_action_index -= 1
            self.update_action_viewer()
        else:
            idx = streets.index(self.current_street)
            prev_street_found = False
            for prev_idx in range(idx - 1, -1, -1):
                prev_street = streets[prev_idx]
                prev_actions = hand['actions'][prev_street]
                if prev_actions:
                    self.current_street = prev_street
                    self.current_action_index = len(prev_actions) - 1
                    self.update_action_viewer()
                    prev_street_found = True
                    break
            if not prev_street_found:
                self.prev_button.config(state='disabled')

if __name__ == "__main__":
    root = tk.Tk()
    app = HandReplayerGUI(root)
    root.mainloop()