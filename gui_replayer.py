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

def get_hero_result(hand, hero=None):
    vpip = False
    # Scan all actions for hero wins or ties
    for street in ['preflop', 'flop', 'turn', 'river']:
        for act in hand['actions'][street]:
            if act['player'] != hero:
                continue
            # Win
            if act['action'] == 'wins':
                return 1
            # Split pot detection
            if act['player'] == hero and (
                'ties for the side pot' in act.get('detail', '') or
                'ties for the pot' in act.get('detail', '') or
                act['action'].startswith('ties for')
            ):
                return 1
            # Check VPIP
            if act['action'] in ('bets', 'calls', 'raises'):
                vpip = True
                break
    return -1 if vpip else 0;

class HandReplayerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Full Tilt 90-Man Tournament Replayer")

        self.parser = None
        self.hands = []
        self.heroes = [] # Shouldn't this just be a single field?
        self.current_hand_index = 0
        self.current_street = None
        self.current_action_index = None
        self.folded_players = set()
        self.player_cards = {}

        self.hand_boxes = []
        self.build_gui()

        # Bind arrow keys for navigation
        self.bind_keys()

    def bind_keys(self):
        """Bind arrow keys to navigation methods."""
        self.root.bind("<Left>", lambda e: self.prev_action())
        self.root.bind("<Right>", lambda e: self.next_action())
        self.root.bind("<Down>", lambda e: self.navigate_hands(-1))
        self.root.bind("<Up>", lambda e: self.navigate_hands(1))
        
    def prev_action(self):
        """Navigate to the previous action."""
        if self.current_action_index > 0:
            self.current_action_index -= 1
            self.update_action_viewer()
        else:
            # Logic for moving to the previous street (if applicable)
            pass

    def next_action(self):
        """Navigate to the next action."""
        if self.current_action_index < len(self.hands[self.current_hand_index]['actions'][self.current_street]) - 1:
            self.current_action_index += 1
            self.update_action_viewer()
        else:
            # Logic for moving to the next street (if applicable)
            pass

    def navigate_hands(self, direction):
        """Navigate through hands."""
        new_index = self.current_hand_index + direction
        if 0 <= new_index < len(self.hands):
            self.select_hand(new_index)

    def select_hand(self, idx):
        """Select a hand by index."""
        self.current_hand_index = idx
        # Logic to update the display for the selected hand
        pass
    
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

    def get_centerward_position_fraction(self, seat_x, seat_y, cx, cy, fraction=0.6):
        """Return a point that lies `fraction` of the way from the seat toward the table center."""
        return (seat_x + (cx - seat_x) * fraction, seat_y + (cy - seat_y) * fraction)

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
                hero = self.hands[1]['hero']
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
            result = get_hero_result(hand, self.hands[self.current_hand_index]['hero'])
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

        # Process antes and blinds at the start of the hand
        self.process_initial_forced_bets(hand)

        self.display_action_history()
        for i, rect_id in enumerate(self.hand_boxes):
            if i == idx:
                self.hand_selector_canvas.itemconfig(rect_id, width=3, outline="#222")
            else:
                self.hand_selector_canvas.itemconfig(rect_id, width=1, outline="#333")

    def process_initial_forced_bets(self, hand):
        """
        Process posting of antes and blinds using the existing process_action logic.
        Ensure all actions are replayed and displayed correctly upon loading a hand.
        Stop at the BB post to allow the first player action to be played.
        """
        # Copy the actions to ensure we don't modify the original hand data
        preflop_actions = list(hand['actions'].get('preflop', []))

        # Reset contributions and pot for this hand
        self.pot = 0
        self.player_contributions = {p['name']: 0 for p in hand['players']}

        # Process forced bets sequentially
        for act in preflop_actions:
            if act['action'] in ('posts', 'antes'):
                # Replay the action
                self.process_action(act, self.player_contributions)

                # Check if this is the BB post
                if "big blind" in act['detail'].lower():
                    break  # Stop processing at the BB post

                # Update the current action index and display the state
                self.current_action_index += 1
                self.update_action_viewer()
                self.update_table_canvas()

        # Debugging: Log the final state
        #print(f"Pot after forced bets: {self.pot}")
        #print(f"Player contributions: {self.player_contributions}")
        #print(f"Remaining actions: {hand['actions']['preflop']}")
    def process_action(self, act, contrib):
        """
        Handles a single action, updating pot and contributions.
        Notes:
          - Antes add to the pot but do NOT count toward the street contribution.
          - Blinds (posts) add to both the pot and street contribution.
        """
        action = act['action']
        detail = act.get('detail', '')
        player = act['player']
        
        if action in ('checks', 'folds', 'shows', 'mucks', 'collected', 'wins'):
            return
        if action == 'posts':
            # Blinds and similar forced posts: count in both pot and street contribution
            amt = self._extract_first_amount(detail)
            self.pot += amt
            contrib[player] = contrib.get(player, 0) + amt
        elif action == 'antes':
            # Antes: pot only, excluded from street contribution
            amt = self._extract_first_amount(detail)
            self.pot += amt
        elif action == 'bets':
            amt = self._extract_first_amount(detail)
            self.pot += amt
            contrib[player] = contrib.get(player, 0) + amt
        elif action == 'calls':
            amt = self._extract_first_amount(detail)
            self.pot += amt
            contrib[player] = contrib.get(player, 0) + amt
        elif action == 'raises':
            target_total = self._extract_raise_to_amount(detail)
            prev = contrib.get(player, 0)
            delta = max(0, target_total - prev)
            self.pot += delta
            contrib[player] = prev + delta

    def add_to_pot(self, player, amount):
        """
        Updates the pot and player contributions for forced bets.
        """
        self.pot = getattr(self, 'pot', 0) + amount
        self.player_contributions = getattr(self, 'player_contributions', {})
        self.player_contributions[player] = self.player_contributions.get(player, 0) + amount

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

        # Pot area
        pot_radius = int(min(table_a, table_b) * 0.25)
        self.table_canvas.create_oval(
            cx - pot_radius, cy - pot_radius,
            cx + pot_radius, cy + pot_radius,
            fill="#222", outline="#fff", width=3
        )

        # Compute and render pot
        pot_amount = 0
        if hand and self.current_street is not None and self.current_action_index is not None:
            pot_amount = self.compute_pot_upto(hand, self.current_street, self.current_action_index)
        # Smaller POT label to match other font sizes, with amount below it
        self.table_canvas.create_text(cx, cy - 8, text="POT", fill="white", font=("Arial", 11, "bold"))
        self.table_canvas.create_text(cx, cy + 12, text=f"${pot_amount:,}", fill="white", font=("Arial", 11))

        # Compute and draw current street bet/contribution markers
        if hand and self.current_street is not None and self.current_action_index is not None:
            non_ante_contrib, ante_contrib = self.compute_street_contrib_upto(
                hand, self.current_street, self.current_action_index
            )
            # Draw blind/bet/call/raise markers (green)
            self.draw_bet_markers(non_ante_contrib, seat_positions, seat_map, cx, cy)
            # Draw ante markers (brown, slightly more center)
            self.draw_ante_markers(ante_contrib, seat_positions, seat_map, cx, cy)

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

    # ====== Pot and contribution helpers ======

    def _extract_first_amount(self, text: str) -> int:
        """
        Extract the first integer amount from a detail string (e.g., 'bets 100', 'posts the ante 25').
        Returns 0 if not found.
        """
        if not text:
            return 0
        m = re.search(r'(\d[\d,]*)', text)
        if not m:
            return 0
        return int(m.group(1).replace(',', ''))

    def _extract_raise_to_amount(self, text: str) -> int:
        """
        Extract the target 'to' amount from a raise string (e.g., 'raises to 300').
        Falls back to first number if pattern not found.
        """
        if not text:
            return 0
        m = re.search(r'raises\s+to\s+(\d[\d,]*)', text)
        if m:
            return int(m.group(1).replace(',', ''))
        # Fallback
        return self._extract_first_amount(text)

    def compute_pot_upto(self, hand, target_street: str, target_action_index: int) -> int:
        """
        Recompute pot from the start of the hand up to and including the given action index
        on the target street. Handles:
          - posts (blinds) [counted in pot AND street contributions]
          - antes [counted in pot ONLY, not in street contributions]
          - bets
          - calls
          - raises (using 'raises to' delta based on per-street contribution)
        """
        pot = 0
        streets = ['preflop', 'flop', 'turn', 'river']

        # Helper: process one action with street contribution tracking
        def process_action(act, contrib):
            nonlocal pot
            action = act['action']
            detail = act.get('detail', '')
            player = act['player']
            if action in ('checks', 'folds', 'shows', 'mucks', 'collected', 'wins'):
                return
            if action == 'posts' or action == 'antes':
                # Includes blinds and antes
                amt = self._extract_first_amount(detail)
                pot += amt
                contrib[player] = contrib.get(player, 0) + amt
            elif action == 'bets':
                amt = self._extract_first_amount(detail)
                pot += amt
                contrib[player] = contrib.get(player, 0) + amt
            elif action == 'calls':
                amt = self._extract_first_amount(detail)
                pot += amt
                contrib[player] = contrib.get(player, 0) + amt
            elif action == 'raises':
                target_total = self._extract_raise_to_amount(detail)
                prev = contrib.get(player, 0)
                delta = max(0, target_total - prev)
                pot += delta
                contrib[player] = prev + delta
            else:
                # Any other money-adding verbs can be added here if they appear
                pass

        for s in streets:
            # Reset per-street contributions (for correct 'raises to' semantics)
            street_contrib = {p['name']: 0 for p in hand['players']}
            actions = hand['actions'][s]
            if not actions:
                if s == target_street:
                    break
                continue

            if s == target_street:
                # Process up to current index inclusive
                upto = max(0, min(target_action_index + 1, len(actions)))
                for i in range(upto):
                    process_action(actions[i], street_contrib)
                break
            else:
                # Process entire street
                for act in actions:
                    process_action(act, street_contrib)

        return pot

    def compute_street_contrib_upto(self, hand, target_street: str, target_action_index: int):
        """
        Compute per-player contribution for the target street only,
        up to and including target_action_index.

        Returns a tuple: (non_ante_contrib, ante_contrib)
          - non_ante_contrib: blinds, bets, calls, raises
          - ante_contrib: antes only
        """
        non_ante = {p['name']: 0 for p in hand['players']}
        antes = {p['name']: 0 for p in hand['players']}
        actions = hand['actions'].get(target_street, [])
        upto = max(0, min(target_action_index + 1, len(actions)))
        for i in range(upto):
            act = actions[i]
            action = act['action']
            detail = act.get('detail', '')
            player = act['player']
            if action in ('checks', 'folds', 'shows', 'mucks', 'collected', 'wins'):
                continue
            if action == 'posts':
                amt = self._extract_first_amount(detail)
                non_ante[player] = non_ante.get(player, 0) + amt
            elif action == 'antes':
                amt = self._extract_first_amount(detail)
                antes[player] = antes.get(player, 0) + amt
            elif action == 'bets':
                amt = self._extract_first_amount(detail)
                non_ante[player] = non_ante.get(player, 0) + amt
            elif action == 'calls':
                amt = self._extract_first_amount(detail)
                non_ante[player] = non_ante.get(player, 0) + amt
            elif action == 'raises':
                target_total = self._extract_raise_to_amount(detail)
                prev = non_ante.get(player, 0)
                delta = max(0, target_total - prev)
                non_ante[player] = prev + delta
        return non_ante, antes

    def draw_bet_markers(self, contrib_map, seat_positions, seat_map, cx, cy):
        """
        Draw a small chip circle toward the center for each player's current street contribution.
        Excludes antes.
        """
        # Build name->seat index map for placement
        name_to_seat = {}
        for seat, pdata in seat_map.items():
            name_to_seat[pdata['name']] = seat

        for name, amount in contrib_map.items():
            if amount <= 0:
                continue
            seat = name_to_seat.get(name)
            if not seat:
                continue
            sx, sy = seat_positions[seat - 1]
            # Position further toward the center than hole cards
            bx, by = self.get_centerward_position_fraction(sx, sy, cx, cy, fraction=0.30)

            # Draw chip circle and amount
            r = 25
            self.table_canvas.create_oval(bx - r, by - r, bx + r, by + r, fill="#70f040", outline="#222", width=2)
            # Keep the text small to fit typical amounts
            self.table_canvas.create_text(bx, by, text=f"{amount:,}", fill="#000", font=("Arial", 9, "bold"))

    def draw_ante_markers(self, ante_map, seat_positions, seat_map, cx, cy):
        """
        Draw ante markers slightly closer to the center, in a brown color.
        """
        # Build name->seat index map for placement
        name_to_seat = {}
        for seat, pdata in seat_map.items():
            name_to_seat[pdata['name']] = seat

        for name, amount in ante_map.items():
            if amount <= 0:
                continue
            seat = name_to_seat.get(name)
            if not seat:
                continue
            sx, sy = seat_positions[seat - 1]

            # Slightly closer to the center than bet markers
            ax, ay = self.get_centerward_position_fraction(sx, sy, cx, cy, fraction=0.38)

            r = 22
            # Brown fill with dark outline for contrast
            self.table_canvas.create_oval(ax - r, ay - r, ax + r, ay + r, fill="#a0522d", outline="#3a2415", width=2)
            self.table_canvas.create_text(ax, ay, text=f"{amount:,}", fill="#fff", font=("Arial", 9, "bold"))
    # ====== UI updates and navigation ======

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
        # Refresh table to update pot and bet markers
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