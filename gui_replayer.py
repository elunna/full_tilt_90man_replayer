import tkinter as tk
from tkinter import filedialog, messagebox
import math
import re
from ft_hand_parser import FullTiltHandParser
import os

# Optional high-quality PNG loading/resizing via Pillow
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageTk = None
    PIL_AVAILABLE = False

SEATS = 9
CARD_WIDTH = 120
CARD_HEIGHT = 160
SEAT_RADIUS = 44
CARD_OFFSET_PX = 70  # Increased to move cards further inward
# Fixed-size seat rectangles
# - Wide enough for ~20 chars at typical UI font (≈ 240–280px). Choose generous width to avoid truncation.
# - 50% bigger vertically than previous 72px -> 108px.
# - Styled via thick rounded dark gray border.
SEAT_BOX_WIDTH = 280
SEAT_BOX_HEIGHT = 108
SEAT_BORDER_RADIUS = 16
SEAT_BORDER_COLOR = "#2e2e2e"
SEAT_BORDER_WIDTH = 6

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

        # Card image caches
        self.card_image_paths = {}
        self.card_image_cache = {}
        self.card_back_key = None
        self.load_card_images()

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

    # ====== Card image loading/rendering ======
    def load_card_images(self):
        """
        Load all PNG images from ./png into a path map for lazy, sized loading.
        Picks back_blue.png as the default card back if present, otherwise the first 'back*.png'.
        """
        base_dir = os.path.dirname(__file__)
        png_dir = os.path.join(base_dir, "png")
        self.card_image_paths.clear()
        self.card_image_cache.clear()
        self.card_back_key = None

        if not os.path.isdir(png_dir):
            return

        for fname in os.listdir(png_dir):
            if not fname.lower().endswith(".png"):
                continue
            key = os.path.splitext(fname)[0].lower()  # e.g., "ah", "back_blue"
            self.card_image_paths[key] = os.path.join(png_dir, fname)

        # Choose default back
        if "back_blue" in self.card_image_paths:
            self.card_back_key = "back_blue"
        else:
            # pick any 'back...' image if available
            for k in self.card_image_paths.keys():
                if k.startswith("back"):
                    self.card_back_key = k
                    break

    def get_card_image_sized(self, code, width, height):
        """
        Return a PhotoImage for the given card code at the requested size.
        Unknown codes (like '??') or missing assets fall back to the default back image.
        Images are resized to (width x height) via PIL if available, otherwise use tk.PhotoImage unscaled.
        """
        # Normalize desired key
        key = None
        if code and code != "??":
            key = code.lower()
        else:
            key = self.card_back_key

        if not key:
            return None

        cache_key = (key, int(width), int(height))
        if cache_key in self.card_image_cache:
            return self.card_image_cache[cache_key]

        path = self.card_image_paths.get(key)
        if not path:
            return None

        try:
            if PIL_AVAILABLE:
                img = Image.open(path).convert("RGBA")
                img = img.resize((int(width), int(height)), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            else:
                photo = tk.PhotoImage(file=path)
        except Exception:
            return None

        self.card_image_cache[cache_key] = photo
        return photo
    def get_card_image(self, code):
        """
        Return a PhotoImage for the given card code (e.g., 'Ah', 'Kd').
        Unknown codes (like '??') or missing assets fall back to the default back image.
        Images are resized to CARD_WIDTH x CARD_HEIGHT (via PIL if available).
        """
        # Normalize desired key
        key = None
        if code and code != "??":
            key = code.lower()
        else:
            key = self.card_back_key

        # If we still don't have a key, no image is available
        if not key:
            return None

        cache_key = (key, CARD_WIDTH, CARD_HEIGHT)
        if cache_key in self.card_image_cache:
            return self.card_image_cache[cache_key]

        path = self.card_image_paths.get(key)
        if not path:
            return None

        try:
            if PIL_AVAILABLE:
                img = Image.open(path).convert("RGBA")
                img = img.resize((CARD_WIDTH, CARD_HEIGHT), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            else:
                # Fallback: no resize support; image should ideally match target size
                photo = tk.PhotoImage(file=path)
        except Exception:
            return None

        self.card_image_cache[cache_key] = photo
        return photo

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

        # Reveal hero hole cards immediately if available
        # ft_hand_parser stores:
        #   - hand['hero'] as the hero's name
        #   - hand['hole_cards'] as a string like "Ah Kd"
        hero_name = hand.get('hero')
        hole = hand.get('hole_cards')
        if hero_name and hole:
            # Split on whitespace or commas to be robust
            parts = [p.strip() for p in re.split(r'[\s,]+', hole) if p.strip()]
            if len(parts) >= 2:
                self.player_cards[hero_name] = parts[:2]

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
        # Reset cached image refs for this frame to prevent growth
        if hasattr(self, "_canvas_images"):
            self._canvas_images.clear()
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
                # Compute seat rectangle top (used to tuck cards behind the seat)
                seat_top = int(y - SEAT_BOX_HEIGHT // 2)

                if not is_folded:
                    # Draw cards centered on the seat, poking out from behind the seat (only top half visible)
                    cards = self.player_cards.get(player['name'], ['??', '??'])
                    self.draw_cards_poking_from_seat(x, seat_top, cards)

                # Draw player name and chips in a fixed-size rounded rectangle centered at the seat position
                self.draw_seat_label(x, y, r, player['name'], player['chips'], cy)
            else:
                # No seat circle; just indicate empty at the seat position
                self.table_canvas.create_text(x, y, text="(empty)", font=("Arial", 9))

        # Pot area (move down a bit to make room for community cards above)
        pot_radius = int(min(table_a, table_b) * 0.25)
        pot_offset_y = int(min(table_a, table_b) * 0.18)  # push pot down relative to table size
        pot_cy = cy + pot_offset_y
        self.table_canvas.create_oval(
            cx - pot_radius, pot_cy - pot_radius,
            cx + pot_radius, pot_cy + pot_radius,
            fill="#222", outline="#fff", width=3
        )

        # Compute and render pot
        pot_amount = 0
        if hand and self.current_street is not None and self.current_action_index is not None:
            pot_amount = self.compute_pot_upto(hand, self.current_street, self.current_action_index)
        # POT label positioned relative to the moved pot circle
        self.table_canvas.create_text(cx, pot_cy + 24, text="POT", fill="white", font=("Arial", 11, "bold"))
        self.table_canvas.create_text(cx, pot_cy + 44, text=f"${pot_amount:,}", fill="white", font=("Arial", 11))

        # Draw community cards revealed up to the current action (above the pot circle)
        if hand and self.current_street is not None and self.current_action_index is not None:
            board_cards = self.compute_board_upto(hand, self.current_street, self.current_action_index)
            self.draw_community_cards(board_cards, cx, pot_cy, pot_radius)
        
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
        card_width = CARD_WIDTH
        card_height = CARD_HEIGHT

        # For bottom seats, anchor cards upward by half a card height to prevent overlap
        card_anchor_y = y
        if seat_y is not None and cy is not None and seat_y > cy:
            card_anchor_y = y - card_height // 2

        # Nothing to draw
        if not cards:
            return

        # Compute front card position centered on x
        front_left = int(x - card_width // 2)
        front_top = int(card_anchor_y)

        # Overlap offsets for the back card: slightly left and slightly raised
        back_dx = -int(card_width * 0.28)   # shift left ~28% of width
        back_dy = -int(card_height * 0.10)  # raise ~10% of height

        # Helper to draw a single card (image first, fallback to rectangle+text)
        def draw_one(left, top, code):
            img = getattr(self, "get_card_image", None)
            photo = img(code) if callable(img) else None
            if photo is not None:
                self.table_canvas.create_image(left, top, image=photo, anchor="nw")
                # prevent GC of PhotoImage
                if not hasattr(self, "_canvas_images"):
                    self._canvas_images = []
                self._canvas_images.append(photo)
            else:
                # Fallback to simple rectangle + code text
                self.table_canvas.create_rectangle(
                    left, top, left + card_width, top + card_height,
                    fill="#fff", outline="#000", width=2
                )
                self.table_canvas.create_text(
                    left + card_width // 2, top + card_height // 2,
                    text=code, font=("Arial", 18, "bold")
                )

        # If two or more entries, treat the first as the back card and second as the front card
        if len(cards) >= 2:
            back_code = cards[0] if cards[0] else "??"
            front_code = cards[1] if cards[1] else "??"

            # Draw back first so it appears beneath
            draw_one(front_left + back_dx, front_top + back_dy, back_code if back_code != "" else "??")
            draw_one(front_left, front_top, front_code if front_code != "" else "??")
        else:
            # Single card (e.g., unknown second card): draw centered
            code = cards[0] if cards[0] else "??"
            draw_one(front_left, front_top, code if code != "" else "??")

    def draw_cards_poking_from_seat(self, seat_cx, seat_top, cards):
        """
        Draw two cards centered on the seat such that only the top half is visible
        above the seat rectangle (the lower half sits behind the seat).
        The seat rectangle should be drawn AFTER this call to cover the lower half.
        """
        if not cards:
            return
        # Enforce: cards should never take up more than 50% of the width of the seat
        max_card_w = SEAT_BOX_WIDTH // 2
        # Scale card size down if needed to satisfy seat constraint
        scale = min(1.0, max(1, max_card_w) / float(CARD_WIDTH))
        w = int(CARD_WIDTH * scale)
        h = int(CARD_HEIGHT * scale)

        # Front card centered on seat; top positioned so half the card height sits above seat top
        front_left = int(seat_cx - w // 2)
        front_top = int(seat_top - h // 2)

        # Back card slightly left and slightly raised for visual layering
        back_dx = -int(w * 0.20)
        back_dy = -int(h * 0.06)
        back_dx = -int(w * 0.20)
        back_dy = -int(h * 0.06)

        def draw_one(left, top, code):
            # Use sized image for per-seat scaling
            photo = self.get_card_image_sized(code, w, h)
            if photo is not None:
                self.table_canvas.create_image(left, top, image=photo, anchor="nw")
                if not hasattr(self, "_canvas_images"):
                    self._canvas_images = []
                self._canvas_images.append(photo)
            else:
                self.table_canvas.create_rectangle(left, top, left + w, top + h, fill="#fff", outline="#000", width=2)
                self.table_canvas.create_text(left + w // 2, top + h // 2, text=code, font=("Arial", 18, "bold"))

        if len(cards) >= 2:
            back_code = cards[0] if cards[0] else "??"
            front_code = cards[1] if cards[1] else "??"
            # Draw back first so it appears beneath
            draw_one(front_left + back_dx, front_top + back_dy, back_code)
            draw_one(front_left, front_top, front_code)
        else:
            code = cards[0] if cards[0] else "??"

    def draw_seat_label(self, x, y, r, name, chips, cy):
        """Draw a fixed-size rounded black box with thick dark gray border, centered at seat position."""
        # Fixed rectangle centered at (x, y)
        left = int(x - SEAT_BOX_WIDTH // 2)
        top = int(y - SEAT_BOX_HEIGHT // 2)
        right = left + SEAT_BOX_WIDTH
        bottom = top + SEAT_BOX_HEIGHT

        # Rounded seat rectangle (draw first so cards can tuck behind its bottom half)
        self.draw_rounded_rect(left, top, right, bottom,
                               radius=SEAT_BORDER_RADIUS,
                               fill="black",
                               outline=SEAT_BORDER_COLOR,
                               width=SEAT_BORDER_WIDTH)

        # Centered text atop the rectangle
        label_text = f"{name}\n${chips}"
        self.table_canvas.create_text(x, y, text=label_text, font=("Arial", 12, "bold"), fill="white", anchor="center")

    def draw_rounded_rect(self, x1, y1, x2, y2, radius=12, fill="", outline="", width=1):
        """
        Draw a rounded rectangle on the canvas using 4 arcs + 3 rectangles.
        """
        r = max(0, int(radius))
        # Core rectangles (center and sides)
        # Center
        self.table_canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill)
        # Left and right
        self.table_canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=fill)
        # Corner arcs
        # Top-left
        self.table_canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="pieslice", outline=fill, fill=fill)
        # Top-right
        self.table_canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="pieslice", outline=fill, fill=fill)
        # Bottom-right
        self.table_canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="pieslice", outline=fill, fill=fill)
        # Bottom-left
        self.table_canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="pieslice", outline=fill, fill=fill)
        # Border path using 4 arcs + 4 lines to simulate thick rounded border

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

    # ====== Community cards helpers ======
    def compute_board_upto(self, hand, target_street: str, target_action_index: int):
        """
        Determine which community cards should be visible up to the given action index.
        Rule:
          - On flop street: show flop only after the 'board' action on flop has been reached.
          - On turn street: always show flop; show turn only after the 'board' action on turn.
          - On river street: always show flop and turn; show river only after the 'board' action on river.
        """
        board = hand.get('board', {})
        flop = list(board.get('flop', []) or [])
        turn = list(board.get('turn', []) or [])
        river = list(board.get('river', []) or [])

        visible = []
        streets = ['preflop', 'flop', 'turn', 'river']
        s = target_street

        if s == 'preflop':
            return visible
        elif s == 'flop':
            # Include flop only if its 'board' action is within range
            actions = hand['actions'].get('flop', [])
            upto = max(0, min(target_action_index + 1, len(actions)))
            seen_flop_board = any(a.get('action') == 'board' and 'flop' in a.get('detail', '').lower() for a in actions[:upto])
            if seen_flop_board:
                visible.extend(flop)
            return visible
        elif s == 'turn':
            # Flop is already known fully at start of turn
            visible.extend(flop)
            actions = hand['actions'].get('turn', [])
            upto = max(0, min(target_action_index + 1, len(actions)))
            seen_turn_board = any(a.get('action') == 'board' and 'turn' in a.get('detail', '').lower() for a in actions[:upto])
            if seen_turn_board:
                visible.extend(turn)
            return visible
        elif s == 'river':
            # Flop and turn are known at start of river
            visible.extend(flop)
            visible.extend(turn)
            actions = hand['actions'].get('river', [])
            upto = max(0, min(target_action_index + 1, len(actions)))
            seen_river_board = any(a.get('action') == 'board' and 'river' in a.get('detail', '').lower() for a in actions[:upto])
            if seen_river_board:
                visible.extend(river)
            return visible
        return visible

    def draw_community_cards(self, cards, cx, pot_cy, pot_radius):
        """
        Draw the current visible community cards above the pot circle.
        Align to a fixed left anchor so cards don't shift as new ones appear.
        Uses same card image system as hole cards. Falls back to rectangle+text.
        """
        if not cards:
            return
        gap = 14
        w = CARD_WIDTH
        h = CARD_HEIGHT

        # Fixed left anchor based on max 5 community cards so position won't shift as cards are revealed
        max_cards = 5
        full_width = max_cards * w + (max_cards - 1) * gap
        left_anchor = int(cx - full_width / 2)

        # Place cards directly above the top of the pot circle, with a small margin
        top_margin = 10
        top = int((pot_cy - pot_radius) - h - top_margin)

        for i, code in enumerate(cards):
            left = left_anchor + i * (w + gap)
            img = getattr(self, "get_card_image", None)
            photo = img(code) if callable(img) else None
            if photo is not None:
                self.table_canvas.create_image(left, top, image=photo, anchor="nw")
                if not hasattr(self, "_canvas_images"):
                    self._canvas_images = []
                self._canvas_images.append(photo)
            else:
                self.table_canvas.create_rectangle(left, top, left + w, top + h, fill="#fff", outline="#000", width=2)
                self.table_canvas.create_text(left + w // 2, top + h // 2, text=code, font=("Arial", 16, "bold"))

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