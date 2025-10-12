import tkinter as tk
from tkinter import filedialog, messagebox
import math
import re
from ft_hand_parser import FullTiltHandParser
import os
import traceback
import sqlite3

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
SEAT_BORDER_COLOR = "#808080"
SEAT_BORDER_WIDTH = 6
DEALER_BTN_RADIUS = 30
DEALER_BTN_MARGIN = 6
# Action flash overlay duration (milliseconds)
ACTION_FLASH_MS = 1000
INFO_PLACEHOLDER = "—"

def get_hero_result(hand, hero=None):
    vpip = False
    # Scan all actions for hero wins or ties
    for street in ['preflop', 'flop', 'turn', 'river']:
        for act in hand['actions'][street]:
            if act.get('player') != hero:
                continue
            action = (act.get('action') or '').lower()
            detail = (act.get('detail') or '').lower()
            # Win (handle both 'wins' and 'collected')
            if action in ('wins', 'collected'):
                return 1
            # Split pot detection (various phrasings)
            if action.startswith('ties for') or 'ties for the pot' in detail or 'ties for the side pot' in detail:
                return 1
            # Check VPIP
            if action in ('bets', 'calls', 'raises'):
                vpip = True
                # Don't return yet; hero might still win later on another street
                # Break inner loop to move to the next street
                #break
    return -1 if vpip else 0

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
        self.sitting_out_players = set()
        self._last_action_index = None

        # Notes / DB state
        self._db = None
        self._db_path = None
        self.notes_dirty = False
        self._loading_notes = False
        self.notes_text = None
        self.mistakes_text = None
        # Hand selector markers for notes
        self.hand_note_markers = {}
        # Geometry cache for selector to place/update markers
        self._selector_box_w = 26
        self._selector_box_h = 52
        self._selector_gap = 4
        self._selector_y_base = 20
        
        # Info panel state
        self.info_blinds_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.info_ante_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.info_bounty_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.info_pot_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.info_handno_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.info_pot_odds_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.info_street_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.info_truebb_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.info_pot_odds_player_var = tk.StringVar(value=INFO_PLACEHOLDER)
        # Session/tournament-wide info panel state
        self.session_room_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.session_game_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.session_date_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.session_hand_var = tk.StringVar(value=INFO_PLACEHOLDER)
        self.session_table_var = tk.StringVar(value=INFO_PLACEHOLDER)
        # Reuse bounty var for the session panel (moved from Info)
        # self.info_bounty_var already defined above

        # Stack display mode (Chips, BB, True BB, M)
        self.stack_view_mode = tk.StringVar(value="Chips")
        # Transient per-seat action overlay state:
        # {'name': <player_name>, 'text': <overlay_text>}
        self.seat_action_flash = None
        self._seat_action_flash_after = None

        # Initialize database for notes
        self._init_db()
        
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
        """Bind arrow keys: Left/Right = hands; Up/Down = actions."""
        # Global save shortcut for notes
        try:
            self.root.bind_all("<Control-s>", lambda e: self.save_current_hand_notes())
            self.root.bind_all("<Command-s>", lambda e: self.save_current_hand_notes())  # macOS
        except Exception:
            pass
        # Hands
        self.root.bind("<Left>", lambda e: self.navigate_hands(-1))  # previous hand
        self.root.bind("<Right>", lambda e: self.navigate_hands(1))  # next hand
        # Actions
        self.root.bind("<Up>", lambda e: self.prev_action())         # previous action
        self.root.bind("<Down>", lambda e: self.next_action())       # next action
        # New shortcuts (unchanged):
        # - Ctrl+Left: jump to beginning of current hand
        self.root.bind("<Control-Up>", lambda e: self.jump_to_hand_start())
        # - Ctrl+Right: jump to end of current hand
        self.root.bind("<Control-Down>", lambda e: self.jump_to_hand_end())
        # - Ctrl+Up: jump to last hand; Ctrl+Down: jump to first hand
        self.root.bind("<Control-Right>", lambda e: (self.select_hand(len(self.hands) - 1) if self.hands else None))
        self.root.bind("<Control-Left>", lambda e: (self.select_hand(0) if self.hands else None))
        
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

        # Info panel (top of right side)
        info_title = tk.Label(right_frame, text="Info")
        info_title.pack(pady=(10, 0))
        info_frame = tk.Frame(right_frame)
        info_frame.pack(fill='x', padx=10, pady=(0, 6))
        # Rows: Hand #, (Blinds + Ante on same row), Pot, Pot odds
        # Make column 1 expandable so right-side fields can align to the right.
        try:
            info_frame.columnconfigure(1, weight=1)
            # Optional: keep rightmost column fixed
            info_frame.columnconfigure(3, weight=0)
        except Exception:
            pass
        # Hand number (tournament index, starting from 1)
        tk.Label(info_frame, text="Hand:").grid(row=0, column=0, sticky="w")
        tk.Label(info_frame, textvariable=self.info_handno_var).grid(row=0, column=1, sticky="w")
        # Street (aligned right on same row as Hand #)
        tk.Label(info_frame, text="Street:").grid(row=0, column=2, sticky="e")
        tk.Label(info_frame, textvariable=self.info_street_var).grid(row=0, column=3, sticky="e")

        # Blinds + Ante on same row
        tk.Label(info_frame, text="Blinds:").grid(row=1, column=0, sticky="w")
        tk.Label(info_frame, textvariable=self.info_blinds_var).grid(row=1, column=1, sticky="w")
        # True BB directly below Blinds
        tk.Label(info_frame, text="True BB:").grid(row=2, column=0, sticky="w")
        tk.Label(info_frame, textvariable=self.info_truebb_var).grid(row=2, column=1, sticky="w")
        # Remaining rows (Ante is appended into the Blinds line when present)
        tk.Label(info_frame, text="Pot:").grid(row=3, column=0, sticky="w")
        tk.Label(info_frame, textvariable=self.info_pot_var).grid(row=3, column=1, sticky="w")
        tk.Label(info_frame, text="Pot odds:").grid(row=4, column=0, sticky="w")
        tk.Label(info_frame, textvariable=self.info_pot_odds_var).grid(row=4, column=1, sticky="w")
        # Player name for pot odds, aligned right on the same line
        self.pot_odds_player_label = tk.Label(info_frame, textvariable=self.info_pot_odds_player_var)
        self.pot_odds_player_label.grid(row=4, column=3, sticky="e")

        # SPR (Stack-to-Pot Ratio) — for Hero only, shown below Pot odds
        tk.Label(info_frame, text="SPR:").grid(row=5, column=0, sticky="w")
        # Ensure the variable exists even if created elsewhere
        try:
            self.info_spr_var
        except AttributeError:
            self.info_spr_var = tk.StringVar(value=INFO_PLACEHOLDER)
        tk.Label(info_frame, textvariable=self.info_spr_var).grid(row=5, column=1, sticky="w")
        # PTS (Pot-to-Stack %) — for Hero only, aligned right of SPR
        tk.Label(info_frame, text="PTS:").grid(row=5, column=2, sticky="e")
        try:
            self.info_pts_var
        except AttributeError:
            self.info_pts_var = tk.StringVar(value=INFO_PLACEHOLDER)
        tk.Label(info_frame, textvariable=self.info_pts_var).grid(row=5, column=3, sticky="e")

        # Session/Tournament panel (room/game/date/hand/table/bounty)
        session_title = tk.Label(right_frame, text="Session")
        session_title.pack(pady=(6, 0))
        session_frame = tk.Frame(right_frame)
        session_frame.pack(fill='x', padx=10, pady=(0, 6))
        # Allow right-aligned fields on same row by expanding column 1
        try:
            session_frame.columnconfigure(1, weight=1)
            session_frame.columnconfigure(3, weight=0)
        except Exception:
            pass
        # Row 0: Room (left) and Game (right on same line)
        tk.Label(session_frame, text="Room:").grid(row=0, column=0, sticky="w")
        tk.Label(session_frame, textvariable=self.session_room_var).grid(row=0, column=1, sticky="w")
        tk.Label(session_frame, text="Game:").grid(row=0, column=2, sticky="e")
        tk.Label(session_frame, textvariable=self.session_game_var).grid(row=0, column=3, sticky="e")
        # Remaining rows (remove Hand # and Table #; move Bounty up)
        tk.Label(session_frame, text="Date:").grid(row=1, column=0, sticky="w")
        tk.Label(session_frame, textvariable=self.session_date_var).grid(row=1, column=1, sticky="w")
        tk.Label(session_frame, text="Bounty:").grid(row=2, column=0, sticky="w")
        tk.Label(session_frame, textvariable=self.info_bounty_var).grid(row=2, column=1, sticky="w")

        # Hand playback display (right side, pushed down by Info)
        action_info_label = tk.Label(right_frame, text="Hand Playback")
        action_info_label.pack(pady=(6,0))
        # Scrollable Hand Playback area; reduce height so Info + Session panels remain visible
        playback_container = tk.Frame(right_frame)
        playback_container.pack(fill='both', padx=10, pady=(0,10), expand=True)
        playback_scroll = tk.Scrollbar(playback_container, orient='vertical')
        playback_scroll.pack(side='right', fill='y')
        self.action_info_text = tk.Text(
            playback_container,
            height=14,  # reduced from 30 to avoid pushing panels off-screen
            width=48,
            wrap='word',
            state='disabled',
            bg="#f6f6f6",
            font=("Consolas", 11),
            yscrollcommand=playback_scroll.set
        )
        self.action_info_text.pack(side='left', fill='both', expand=True)
        playback_scroll.config(command=self.action_info_text.yview)


        # Notes panel (below Hand Playback)
        notes_title = tk.Label(right_frame, text="Notes")
        notes_title.pack(pady=(0, 0))

        notes_frame = tk.Frame(right_frame)
        notes_frame.pack(fill='x', padx=10, pady=(0, 10))

        # Layout: Notes label + 2-row text, Mistakes label + 2-row text, then Save/Clear buttons
        try:
            notes_frame.columnconfigure(0, weight=1)
            notes_frame.columnconfigure(1, weight=0)
            notes_frame.columnconfigure(2, weight=0)
        except Exception:
            pass

        tk.Label(notes_frame, text="Notes").grid(row=0, column=0, sticky="w")
        self.notes_text = tk.Text(notes_frame, height=2, width=48, wrap='word')
        self.notes_text.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 6))

        tk.Label(notes_frame, text="Mistakes").grid(row=2, column=0, sticky="w")
        self.mistakes_text = tk.Text(notes_frame, height=2, width=48, wrap='word')
        self.mistakes_text.grid(row=3, column=0, columnspan=3, sticky="we", pady=(0, 6))

        save_btn = tk.Button(notes_frame, text="Save (Ctrl+S)", command=self.save_current_hand_notes)
        save_btn.grid(row=4, column=1, sticky="e", padx=(0, 6))
        clear_btn = tk.Button(notes_frame, text="Clear", command=self.clear_notes)
        clear_btn.grid(row=4, column=2, sticky="e")

        # Mark notes as dirty on edit
        def _bind_dirty(widget):
            if widget is None:
                return
            try:
                widget.bind("<KeyRelease>", self.on_notes_changed)
            except Exception:
                pass
        _bind_dirty(self.notes_text)
        _bind_dirty(self.mistakes_text)

    # Bottom bar: hand selector and controls
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(side='bottom', fill='x', pady=(4,4))

        # Hand selector row
        self.hand_selector_frame = tk.Frame(bottom_frame)
        self.hand_selector_frame.pack(side='top', fill='x', padx=(0,10))
        self.hand_selector_canvas = tk.Canvas(self.hand_selector_frame, height=72, bg="#ddd", highlightthickness=0)
        self.hand_selector_canvas.pack(side='top', fill='x', expand=True)
        self.hand_boxes = []

        # Navigation controls (replay controls) - now under hand selector
        controls_frame = tk.Frame(bottom_frame)
        controls_frame.pack(side='top', fill='x', pady=(2,0))
        # CD-style navigation: First, Prev, Next, Last
        self.first_button = tk.Button(controls_frame, text="|<", command=self.jump_to_hand_start, state='disabled', width=5)
        self.first_button.pack(side='left', padx=2)
        self.prev_button = tk.Button(controls_frame, text="Prev", command=self.prev_action, state='disabled', width=8)
        self.prev_button.pack(side='left', padx=2)
        self.next_button = tk.Button(controls_frame, text="Next", command=self.next_action, state='disabled', width=8)
        self.next_button.pack(side='left', padx=2)
        self.last_button = tk.Button(controls_frame, text=">|", command=self.jump_to_hand_end, state='disabled', width=5)
        self.last_button.pack(side='left', padx=2)

        # Stack display mode controls (centered radio buttons with larger targets)
        # Use a dedicated frame and place() to center within controls_frame without disrupting left-aligned widgets.
        stack_mode_frame = tk.Frame(controls_frame)
        # Center horizontally at the top of the controls bar
        stack_mode_frame.place(relx=0.5, rely=0.0, anchor='n')

        tk.Label(stack_mode_frame, text="Stacks:", font=("Arial", 11, "bold")).pack(side='left', padx=(6, 8))

        # Keep references to radios for style updates
        self._stack_radio_buttons = {}
        def _make_stack_radio(text, value):
            rb = tk.Radiobutton(
                stack_mode_frame, text=text, variable=self.stack_view_mode, value=value,
                indicatoron=0,  # render as a button for larger click target
                font=("Arial", 12), padx=14, pady=6,  # roughly 3x larger than default
                bd=2, relief='ridge', highlightthickness=0, takefocus=0,
                activebackground="#ececec", selectcolor="#dddddd"
            )
            rb.pack(side='left', padx=12, pady=2)
            self._stack_radio_buttons[value] = rb
            return rb

        _make_stack_radio("Chips",   "Chips")
        _make_stack_radio("BB",      "BB")
        _make_stack_radio("tBB",     "True BB")  # value remains "True BB" internally
        _make_stack_radio("M",       "M")

        # React to selection changes: restyle radios and repaint seat labels
        def _on_stack_mode_change(*_args):
            self._update_stack_mode_styles()
            self.update_table_canvas()
        self.stack_view_mode.trace_add('write', _on_stack_mode_change)
        # Apply initial styling
        self._update_stack_mode_styles()

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
            # Build heroes list safely per hand
            self.heroes = []
            for hand in self.hands:
                hero = (hand or {}).get('hero')
                self.heroes.append(hero)
            self.file_label.config(text=f"Loaded: {os.path.basename(file_path)}")
            self.populate_hand_selector()
        except Exception as e:
            tb = traceback.format_exc()
            self._show_error_dialog(
                "Error",
                f"Failed to parse file:\n{e}",
                details=tb
            )

    def _show_error_dialog(self, title: str, message: str, details: str = ""):
        """
        Show a modal error dialog with optional scrollable details (e.g., stack trace).
        """
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.grab_set()

        # Main message
        lbl = tk.Label(dlg, text=message, anchor="w", justify="left")
        lbl.pack(fill="x", padx=10, pady=(10, 5))

        # Optional details area
        if details:
            frame = tk.Frame(dlg)
            frame.pack(fill="both", expand=True, padx=10, pady=5)
            txt = tk.Text(frame, wrap="none", height=20, width=100)
            txt.insert("1.0", details)
            txt.config(state="disabled")
            vsb = tk.Scrollbar(frame, orient="vertical", command=txt.yview)
            hsb = tk.Scrollbar(frame, orient="horizontal", command=txt.xview)
            txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            txt.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)

            btns = tk.Frame(dlg)
            btns.pack(fill="x", padx=10, pady=(0, 10))

            def copy_details():
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(details)
                except Exception:
                    pass

            tk.Button(btns, text="Copy details", command=copy_details).pack(side="left")
            tk.Button(btns, text="Close", command=dlg.destroy).pack(side="right")
        else:
            tk.Button(dlg, text="Close", command=dlg.destroy).pack(pady=(0, 10))

        # Center the dialog relative to the root window
        try:
            dlg.update_idletasks()
            w = dlg.winfo_width()
            h = dlg.winfo_height()
            x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
            dlg.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def populate_hand_selector(self):
        self.hand_selector_canvas.delete("all")
        self.hand_boxes.clear()
        self.hand_note_markers.clear()
        # Keep original width; double the height, and leave room above for tick labels
        box_w = 26
        box_h = 52
        gap = 4
        # Move boxes down so we have space to draw number ticks above them
        y = 20

        # Cache geometry for later updates of '#' markers
        self._selector_box_w = box_w
        self._selector_box_h = box_h
        self._selector_gap = gap
        self._selector_y_base = y

        # Pre-compute which hands have notes in DB (by Game #)
        hand_ids = []
        for hand in self.hands:
            header = (hand or {}).get('header') or ""
            meta = self._extract_session_info(header)
            hand_ids.append(meta.get("hand_no") or "")
        hands_with_notes = self._hands_with_notes_set(hand_ids) if hand_ids else set()
        
        for i, hand in enumerate(self.hands):
            hero = self.heroes[i] if i < len(self.heroes) else (hand.get('hero') if hand else None)
            result = get_hero_result(hand, hero)
            color = "#a9a9a9"
            if result > 0:
                color = "#66cc66"
            elif result < 0:
                color = "#e76c6c"
            x = i * (box_w + gap) + gap
            rect_id = self.hand_selector_canvas.create_rectangle(
                x, y, x + box_w, y + box_h, fill=color, outline="#333", width=1
            )
            self.hand_selector_canvas.tag_bind(rect_id, "<Button-1>", lambda e, idx=i: self.select_hand(idx))
            self.hand_boxes.append(rect_id)

        # Markers every 10 hands (above the boxes), label 10, 20, 30, ... (omit 1)
        for i in range(9, len(self.hands), 10):  # zero-based index 9 => hand #10
            mx = i * (box_w + gap) + gap + (box_w // 2)
            # small tick just above the boxes
            self.hand_selector_canvas.create_line(mx, y - 12, mx, y - 4, fill="#666", width=1)
            # hand number label above the tick
            self.hand_selector_canvas.create_text(mx, y - 16, text=str(i + 1), fill="#555", font=("Arial", 8))

        total_width = len(self.hands) * (box_w + gap) + gap
        # Allow extra vertical space to include tick labels above the boxes
        self.hand_selector_canvas.config(scrollregion=(0, 0, total_width, y + box_h + 12))
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
        # Auto-save notes for the currently selected hand (if any changes)
        try:
            prev_idx = getattr(self, 'current_hand_index', None)
        except Exception:
            prev_idx = None
        if prev_idx is not None and 0 <= prev_idx < len(self.hands):
            self.maybe_auto_save_notes_for_hand(prev_idx)

        self.current_hand_index = idx
        hand = self.hands[idx]
        self.folded_players = set()
        # Initialize sitting-out players from seat info for this hand
        try:
            self.sitting_out_players = {
                p['name'] for p in hand['players'] if p.get('sitting_out')
            }
        except Exception:
            self.sitting_out_players = set()
        self.player_cards = {p['name']: ['??', '??'] for p in hand['players']}
        self.current_street = 'preflop'
        self.current_action_index = 0
        self._last_action_index = None

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

        # Update session/tournament panel (constant across the tournament/file)
        self.update_session_panel()

        # Process antes and blinds at the start of the hand
        self.process_initial_forced_bets(hand)

        self.display_action_history()
        for i, rect_id in enumerate(self.hand_boxes):
            if i == idx:
                self.hand_selector_canvas.itemconfig(rect_id, width=5, outline="#222")
            else:
                self.hand_selector_canvas.itemconfig(rect_id, width=1, outline="#333")

        # Load notes for the newly selected hand
        self.load_notes_for_current_hand()
        # Update '#' markers for previous and current hands (in case auto-save changed presence)
        if prev_idx is not None and 0 <= prev_idx < len(self.hands):
            self._update_hand_note_marker(prev_idx)
        if idx is not None and 0 <= idx < len(self.hands):
            self._update_hand_note_marker(idx)
        
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
        
        if action in ('checks', 'folds', 'shows', 'mucks', 'collected', 'wins', 'is sitting out', 'has returned'):
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

        # Compute live chip stacks up to the current action, so seat chip counts reflect
        # bets/calls/raises/blinds/antes and winnings, both when stepping forward and back.
        stacks_map = {p['name']: p.get('chips', 0) for p in hand['players']} if hand else {}
        if hand and self.current_street is not None and self.current_action_index is not None:
            try:
                stacks_map = self.compute_stacks_upto(
                    hand,
                    self.current_street,
                    self.current_action_index
                )
            except Exception:
                pass

        flash = self.seat_action_flash  # e.g., {'name': 'Player1', 'text': 'BET'}
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
                if flash and flash.get('name') == player['name']:
                    # Show the transient action overlay instead of name/chips
                    self.draw_seat_action_overlay(x, y, flash.get('text', '').upper())
                else:
                    # If player is sitting out, replace chip display with "sitting out"
                    if player['name'] in self.sitting_out_players:
                        chip_display = "sitting out"
                    else:
                        # Dynamic, up-to-now stack for this player, formatted via current display mode
                        chips_now = stacks_map.get(player['name'], player.get('chips', 0))
                        try:
                            chip_display = self._format_stack_display(chips_now, hand)
                        except Exception:
                            chip_display = chips_now

                    self.draw_seat_label(x, y, r, player['name'], chip_display, cy)

            else:
                # Draw an empty seat rectangle (no text) so all seats are visible by default
                self.draw_empty_seat(x, y)

            # Draw dealer button if this seat holds the button for the current hand
            if hand and hand.get('button_seat') == seat:
                # Place the dealer disc slightly toward the table center from the seat
                # so it sits visually "next to" the player box without clipping.
                self.draw_dealer_button(x, y, cx, cy)

        # Pot area anchor (used for community card placement and pot text below them)
        pot_radius = int(min(table_a, table_b) * 0.25)
        pot_offset_y = int(min(table_a, table_b) * 0.18)  # anchor point similar to prior pot circle center
        pot_cy = cy + pot_offset_y

        # Compute pot size (state up to the current action)
        pot_amount = 0
        if hand and self.current_street is not None and self.current_action_index is not None:
            pot_amount = self.compute_pot_upto(hand, self.current_street, self.current_action_index)

        # Draw community cards revealed up to the current action
        board_cards = []
        if hand and self.current_street is not None and self.current_action_index is not None:
            board_cards = self.compute_board_upto(hand, self.current_street, self.current_action_index)
            self.draw_community_cards(board_cards, cx, pot_cy, pot_radius)

        # Place the POT label and amount just below the community cards
        # Use the same positioning math as draw_community_cards to find the bottom edge
        top_margin = 10
        w = CARD_WIDTH
        h = CARD_HEIGHT
        cards_top = int((pot_cy - pot_radius) - h - top_margin)
        cards_bottom = cards_top + h
        # Slightly larger fonts and extra spacing between label and amount
        pot_label_y = cards_bottom + 8
        amount_y = pot_label_y + 42  # extra padding between "POT" and the amount
        self.table_canvas.create_text(
            cx, pot_label_y, text="POT", fill="white", font=("Arial", 13, "bold")
        )
        self.table_canvas.create_text(
            cx, amount_y, text=f"${pot_amount:,}", fill="white", font=("Arial", 14, "bold")
        )
        
        # Compute and draw current street bet/contribution markers
        if hand and self.current_street is not None and self.current_action_index is not None:
            non_ante_contrib, ante_contrib = self.compute_street_contrib_upto(
                hand, self.current_street, self.current_action_index
            )
            # If showdown has started, clear any existing bets by skipping bet markers
            try:
                showdown_reached = self.has_showdown_upto(hand, self.current_street, self.current_action_index)
            except Exception:
                showdown_reached = False
            if not showdown_reached:
                # Draw blind/bet/call/raise markers (green)
                self.draw_bet_markers(non_ante_contrib, seat_positions, seat_map, cx, cy)
            # Ante markers (brown, slightly more center)
            # Draw ante markers (brown, slightly more center)
            self.draw_ante_markers(ante_contrib, seat_positions, seat_map, cx, cy)
            # Draw winnings markers (gold) accumulated up to the current action
            try:
                winnings_map = self.compute_winnings_upto(hand, self.current_street, self.current_action_index)
                self.draw_winnings_markers(winnings_map, seat_positions, seat_map, cx, cy)
            except Exception:
                pass

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
        # Only prefix with $ for numeric chip values; for status strings like "sitting out" don't add $.
        if isinstance(chips, (int, float)):
            chips_str = f"${chips}"
        else:
            chips_str = str(chips)
        label_text = f"{name}\n{chips_str}"
        # Ensure the text itself is centered within the seat (for multi-line text as well)
        self.table_canvas.create_text(
            x, y, text=label_text, font=("Arial", 12, "bold"), fill="white", anchor="center", justify="center"
        )
    def draw_seat_action_overlay(self, x, y, text):
        """Draw a fixed-size rounded black box with bold, large overlay text (e.g., BET, CALL)."""
        left = int(x - SEAT_BOX_WIDTH // 2)
        top = int(y - SEAT_BOX_HEIGHT // 2)
        right = left + SEAT_BOX_WIDTH
        bottom = top + SEAT_BOX_HEIGHT

        # Background same as occupied seat
        self.draw_rounded_rect(left, top, right, bottom,
                               radius=SEAT_BORDER_RADIUS,
                               fill="black",
                               outline=SEAT_BORDER_COLOR,
                               width=SEAT_BORDER_WIDTH)
        # Big overlay text
        overlay = text.upper() if text else ""
        self.table_canvas.create_text(x, y, text=overlay, font=("Arial", 20, "bold"), fill="#ffffff", anchor="center")

    def draw_empty_seat(self, x, y):
        """Draw a fixed-size rounded seat rectangle with no text."""
        left = int(x - SEAT_BOX_WIDTH // 2)
        top = int(y - SEAT_BOX_HEIGHT // 2)
        right = left + SEAT_BOX_WIDTH
        bottom = top + SEAT_BOX_HEIGHT

        # Rounded seat rectangle (same style as occupied seats)
        self.draw_rounded_rect(
            left, top, right, bottom,
            radius=SEAT_BORDER_RADIUS,
            fill="",
            outline=SEAT_BORDER_COLOR,
            width=SEAT_BORDER_WIDTH
        )

    def draw_dealer_button(self, seat_x, seat_y, cx, cy, radius=DEALER_BTN_RADIUS):
        """
        Draw a small white dealer button with a capital 'D' near the given seat position.
        Positioned slightly toward the table center so it doesn't clip outside the table.
        """
        # Position fraction toward center; smaller fraction keeps it close to the seat
        bx, by = self.get_centerward_position_fraction(seat_x, seat_y, cx, cy, fraction=0.18)
        r = int(radius)
        # White disc with dark outline
        self.table_canvas.create_oval(
            bx - r, by - r, bx + r, by + r,
            fill="#ffffff", outline="#222222", width=2
        )
        # 'D' label centered on the disc
        self.table_canvas.create_text(
            bx, by,
            text="D", fill="#000000",
            font=("Arial", 12, "bold")
        )

    # ====== Action flash control ======

    def draw_rounded_rect(self, x1, y1, x2, y2, radius=12, fill="", outline="", width=1):
        """
        Draw a rounded rectangle on the canvas using 4 arcs + 3 rectangles.
        """
        r = max(0, int(radius))
        # Fill shape (only if a fill color is provided)
        if fill:
            # Core rectangles (center and sides)
            # Center
            self.table_canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill)
            # Left and right
            self.table_canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=fill)
            # Corner arcs as pieslices to make the filled corners
            # Top-left
            self.table_canvas.create_arc(
                x1, y1, x1 + 2 * r, y1 + 2 * r,
                start=90, extent=90, style="pieslice", outline=fill, fill=fill
            )
            # Top-right
            self.table_canvas.create_arc(
                x2 - 2 * r, y1, x2, y1 + 2 * r,
                start=0, extent=90, style="pieslice", outline=fill, fill=fill
            )
            # Bottom-right
            self.table_canvas.create_arc(
                x2 - 2 * r, y2 - 2 * r, x2, y2,
                start=270, extent=90, style="pieslice", outline=fill, fill=fill
            )
            # Bottom-left
            self.table_canvas.create_arc(
                x1, y2 - 2 * r, x1 + 2 * r, y2,
                start=180, extent=90, style="pieslice", outline=fill, fill=fill
            )

        # Border path using arcs + lines for a visible rounded outline
        if outline and width > 0:
            # Corner arcs (outline only)
            self.table_canvas.create_arc(
                x1, y1, x1 + 2 * r, y1 + 2 * r,
                start=90, extent=90, style="arc", outline=outline, width=width
            )
            self.table_canvas.create_arc(
                x2 - 2 * r, y1, x2, y1 + 2 * r,
                start=0, extent=90, style="arc", outline=outline, width=width
            )
            self.table_canvas.create_arc(
                x2 - 2 * r, y2 - 2 * r, x2, y2,
                start=270, extent=90, style="arc", outline=outline, width=width
            )
            self.table_canvas.create_arc(
                x1, y2 - 2 * r, x1 + 2 * r, y2,
                start=180, extent=90, style="arc", outline=outline, width=width
            )
            # Straight edges
            self.table_canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=width)
            self.table_canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=width)
            self.table_canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=width)
            self.table_canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=width)

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

    def _extract_returned_to_name(self, detail: str):
        """
        For 'uncalled' actions, extract the recipient's name from patterns like:
          'Uncalled bet of 445 returned to joehiro'
        Returns the extracted name (str) or None if not present.
        """
        if not detail:
            return None
        m = re.search(r"returned\s+to\s+(.+)$", detail, flags=re.IGNORECASE)
        if not m:
            return None
        name = m.group(1).strip()
        name = re.sub(r"[.\s]+$", "", name)  # trim trailing punctuation/whitespace
        return name
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
            if action in ('checks', 'folds', 'shows', 'mucks', 'collected', 'wins', 'is sitting out', 'has returned'):
                return
            # Money-adding actions
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
                # Money-returning action(s)
                if action == 'uncalled':
                    # Return chips to the bettor: subtract from pot and reduce that player's street contrib
                    amt = self._extract_first_amount(detail)
                    pot -= amt
                    # Determine recipient (use explicit player if present; else parse from detail)
                    recipient = player or self._extract_returned_to_name(detail)
                    if recipient:
                        prev = contrib.get(recipient, 0)
                        contrib[recipient] = max(0, prev - amt)
                else:
                    # Any other verbs can be added here if they appear
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

    def compute_stacks_upto(self, hand, target_street: str, target_action_index: int):
        """
        Recompute each player's chip stack from the start of the hand up to and including
        the given action index on the target street.
        Rules:
          - Start from the 'chips' value in the Seat lines for this hand.
          - Subtract for money put in the pot:
              posts (blinds), antes, bets, calls, and the delta of 'raises to'.
          - Add for money taken from the pot: 'wins' and 'collected'.
          - Return for uncalled bets: 'uncalled' adds back to stack and reduces that street's contrib.
          - For 'raises to', use per-street non-ante contribution to derive the delta.
        Returns: dict {player_name: live_stack}
        """
        # Initialize stacks from hand's seat info
        stacks = {p['name']: int(p.get('chips', 0)) for p in hand.get('players', [])}
        streets = ['preflop', 'flop', 'turn', 'river']

        def sub_from_stack(name: str, amt: int):
            if not name or name == 'Board' or amt <= 0:
                return
            stacks[name] = stacks.get(name, 0) - amt

        def add_to_stack(name: str, amt: int):
            if not name or name == 'Board' or amt <= 0:
                return
            stacks[name] = stacks.get(name, 0) + amt

        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if not actions:
                if s == target_street:
                    break
                continue

            # Track per-street non-ante contribution for 'raises to' delta semantics
            street_non_ante = {p['name']: 0 for p in hand.get('players', [])}

            if s == target_street:
                upto = max(0, min((target_action_index or 0) + 1, len(actions)))
                rng = range(upto)
            else:
                rng = range(len(actions))

            for i in rng:
                act = actions[i]
                action = (act.get('action') or '').lower()
                player = act.get('player')
                detail = act.get('detail', '') or ''

                if action in ('checks', 'folds', 'shows', 'mucks', 'is sitting out', 'has returned'):
                    continue

                if action == 'posts':
                    amt = self._extract_first_amount(detail)
                    sub_from_stack(player, amt)
                    street_non_ante[player] = street_non_ante.get(player, 0) + amt
                elif action == 'antes':
                    amt = self._extract_first_amount(detail)
                    sub_from_stack(player, amt)  # antes do reduce stack
                elif action == 'bets':
                    amt = self._extract_first_amount(detail)
                    sub_from_stack(player, amt)
                    street_non_ante[player] = street_non_ante.get(player, 0) + amt
                elif action == 'calls':
                    amt = self._extract_first_amount(detail)
                    sub_from_stack(player, amt)
                    street_non_ante[player] = street_non_ante.get(player, 0) + amt
                elif action == 'raises':
                    target_total = self._extract_raise_to_amount(detail)
                    prev = street_non_ante.get(player, 0)
                    delta = max(0, target_total - prev)
                    sub_from_stack(player, delta)
                    street_non_ante[player] = prev + delta
                elif action in ('wins', 'collected'):
                    amt = self._extract_first_amount(detail)
                    add_to_stack(player, amt)
                elif action == 'uncalled':
                    # Return the uncalled portion to the bettor and reduce their displayed contribution
                    amt = self._extract_first_amount(detail)
                    # Determine recipient (bettor)
                    recipient = player or self._extract_returned_to_name(detail)
                    if recipient:
                        add_to_stack(recipient, amt)
                        prev = street_non_ante.get(recipient, 0)
                        street_non_ante[recipient] = max(0, prev - amt)
                        
            if s == target_street:
                break

        return stacks

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
            if action in ('checks', 'folds', 'shows', 'mucks', 'collected', 'wins', 'is sitting out', 'has returned'):
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
            elif action == 'uncalled':
                # Reduce the bettor's displayed street contribution by the uncalled amount
                amt = self._extract_first_amount(detail)
                name = player or self._extract_returned_to_name(detail)
                if name:
                    non_ante[name] = max(0, non_ante.get(name, 0) - amt)
        return non_ante, antes

    def has_showdown_upto(self, hand, target_street: str, target_action_index: int) -> bool:
        """
        Return True if any showdown-indicative action ('shows', 'mucks', 'wins', 'collected')
        has occurred up to and including target_action_index on target_street.
        Earlier streets are processed fully.
        """
        showdown_actions = {'shows', 'mucks', 'wins', 'collected'}
        streets = ['preflop', 'flop', 'turn', 'river']
        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if not actions:
                if s == target_street:
                    break
                continue
            if s == target_street:
                upto = max(0, min((target_action_index or 0) + 1, len(actions)))
                rng = range(upto)
            else:
                rng = range(len(actions))
            for i in rng:
                a = actions[i]
                if (a.get('action') or '').lower() in showdown_actions:
                    return True
            if s == target_street:
                break
        return False

    def compute_winnings_upto(self, hand, target_street: str, target_action_index: int):
        """
        Accumulate per-player winnings up to and including target_action_index on the target street.
        Includes both 'wins' and 'collected' actions, summing amounts across main and side pots.
        Returns: dict {player_name: total_won_int}
        """
        winnings = {p['name']: 0 for p in hand.get('players', [])}
        streets = ['preflop', 'flop', 'turn', 'river']
        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if not actions:
                if s == target_street:
                    break
                continue
            if s == target_street:
                upto = max(0, min((target_action_index or 0) + 1, len(actions)))
                rng = range(upto)
            else:
                rng = range(len(actions))
            for i in rng:
                act = actions[i]
                a = (act.get('action') or '').lower()
                if a in ('wins', 'collected'):
                    player = act.get('player')
                    if not player or player == 'Board':
                        continue
                    amt = self._extract_first_amount(act.get('detail', '') or '')
                    winnings[player] = winnings.get(player, 0) + max(0, amt)
            if s == target_street:
                break
        # Remove zero entries for cleaner rendering
        return {k: v for k, v in winnings.items() if v > 0}

    def draw_winnings_markers(self, winnings_map, seat_positions, seat_map, cx, cy):
        """
        Draw winnings as chip markers near each player's seat.
        Use a gold color and place slightly closer to the seat than bet markers to avoid overlap.
        """
        name_to_seat = {pdata['name']: seat for seat, pdata in seat_map.items()}
        for name, amount in winnings_map.items():
            seat = name_to_seat.get(name)
            if not seat or amount <= 0:
                continue
            sx, sy = seat_positions[seat - 1]
            wx, wy = self.get_centerward_position_fraction(sx, sy, cx, cy, fraction=0.22)
            r = 26
            # Gold-like fill with dark outline
            self.table_canvas.create_oval(wx - r, wy - r, wx + r, wy + r, fill="#ffd700", outline="#7a5a00", width=2)
            self.table_canvas.create_text(wx, wy, text=f"{amount:,}", fill="#000", font=("Arial", 9, "bold"))

    def compute_sitting_out_upto(self, hand, target_street: str, target_action_index: int):
        """
        Determine which players are currently sitting out up to and including target_action_index
        on target_street. Earlier streets are processed fully.
        Starts from any players marked 'sitting_out' in the seat info for this hand,
        then applies 'is sitting out' / 'has returned' actions.
        """
        sitting = set()
        try:
            for p in hand.get('players', []):
                if p.get('sitting_out'):
                    sitting.add(p['name'])
        except Exception:
            pass

        streets = ['preflop', 'flop', 'turn', 'river']
        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if not actions:
                if s == target_street:
                    break
                continue
            if s == target_street:
                upto = max(0, min((target_action_index or 0) + 1, len(actions)))
                rng = range(upto)
            else:
                rng = range(len(actions))
            for i in rng:
                a = actions[i]
                act = (a.get('action') or '').lower()
                name = a.get('player')
                if not name or name == 'Board':
                    continue
                if act == 'is sitting out':
                    sitting.add(name)
                elif act == 'has returned':
                    sitting.discard(name)
            if s == target_street:
                break
        return sitting

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

    def compute_folded_players_upto(self, hand, target_street: str, target_action_index: int):
        """
        Return a set of players who have folded up to and including target_action_index
        on target_street. Earlier streets are processed fully.
        This is used to correctly restore fold state when stepping backward.
        """
        folded = set()
        streets = ['preflop', 'flop', 'turn', 'river']
        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if not actions:
                if s == target_street:
                    break
                continue

            if s == target_street:
                upto = max(0, min(target_action_index + 1, len(actions)))
                rng = range(upto)
            else:
                rng = range(len(actions))

            for i in rng:
                act = actions[i]
                if act.get('player') and act.get('player') != 'Board' and act.get('action') == 'folds':
                    folded.add(act['player'])
            if s == target_street:
                break
        return folded

    def compute_shown_cards_upto(self, hand, target_street: str, target_action_index: int):
        """
        Return a dict of {player: [card1, card2]} for players who have shown their hole cards
        up to and including target_action_index on target_street. Earlier streets are processed fully.
        Only the first 'shows' instance per player that contains bracketed hole cards is used.
        """
        shown = {}
        streets = ['preflop', 'flop', 'turn', 'river']
        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if not actions:
                if s == target_street:
                    break
                continue

            if s == target_street:
                upto = max(0, min(target_action_index + 1, len(actions)))
                rng = range(upto)
            else:
                rng = range(len(actions))

            for i in rng:
                act = actions[i]
                if act.get('action') != 'shows':
                    continue
                player = act.get('player')
                if not player or player == 'Board':
                    continue
                # Keep only the first 'shows' with bracketed hole cards
                if player not in shown:
                    cards = self._extract_shown_cards(act.get('detail', '') or '')
                    if cards:
                        shown[player] = cards
            if s == target_street:
                break
        return shown

    def _extract_shown_cards(self, detail: str):
        """
        Extract two hole cards from a 'shows' detail string like: 'shows [9s Jd]'.
        Returns a list like ['9s','jd'] or None if not present.
        """
        if not detail:
            return None
        m = re.search(r"\[([^\]]+)\]", detail)
        if not m:
            return None
        inner = m.group(1).strip()
        toks = [t.strip() for t in re.split(r"\s+", inner) if t.strip()]
        # Filter to card-like tokens (rank+suit)
        cards = []
        for t in toks:
            if re.match(r"^(?:[2-9]|10|[tTjJqQkKaA])[shdcSHDC]$", t) or re.match(r"^[2-9tTjJqQkKaA][shdcSHDC]$", t):
                cards.append(t.lower())
            if len(cards) >= 2:
                break
        return cards if len(cards) >= 2 else None

    def compute_shown_cards_upto(self, hand, target_street: str, target_action_index: int):
        """
        Return a dict of {player: [card1, card2]} for players who have shown their hole cards
        up to and including target_action_index on target_street. Earlier streets are processed fully.
        Only the first 'shows' instance per player that contains bracketed hole cards is used.
        """
        shown = {}
        streets = ['preflop', 'flop', 'turn', 'river']
        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if not actions:
                if s == target_street:
                    break
                continue

            if s == target_street:
                upto = max(0, min(target_action_index + 1, len(actions)))
                rng = range(upto)
            else:
                rng = range(len(actions))

            for i in rng:
                act = actions[i]
                if act.get('action') != 'shows':
                    continue
                player = act.get('player')
                if not player or player == 'Board':
                    continue
                # Keep only the first 'shows' with bracketed hole cards
                if player not in shown:
                    cards = self._extract_shown_cards(act.get('detail', '') or '')
                    if cards:
                        shown[player] = cards
            if s == target_street:
                break
        return shown

    def _extract_shown_cards(self, detail: str):
        """
        Extract two hole cards from a 'shows' detail string like: 'shows [9s Jd]'.
        Returns a list like ['9s','jd'] or None if not present.
        """
        if not detail:
            return None
        m = re.search(r"\[([^\]]+)\]", detail)
        if not m:
            return None
        inner = m.group(1).strip()
        toks = [t.strip() for t in re.split(r"\s+", inner) if t.strip()]
        # Filter to card-like tokens (rank+suit)
        cards = []
        for t in toks:
            if re.match(r"^(?:[2-9]|10|[tTjJqQkKaA])[shdcSHDC]$", t) or re.match(r"^[2-9tTjJqQkKaA][shdcSHDC]$", t):
                cards.append(t.lower())
            if len(cards) >= 2:
                break
        return cards if len(cards) >= 2 else None

    def _extract_mucked_cards_from_summary(self, hand):
        """
        From the SUMMARY section seat lines, extract mucked hole cards.
        Returns dict {player_name: [card1, card2]} for any 'mucked [..]' entries.
        Example seat line: 'Seat 4: fade2night (big blind) mucked [3s 6d] - a pair of Threes'
        """
        out = {}
        summary = hand.get('summary', {}) or {}
        for _k, v in summary.items():
            if not v:
                continue
            m = re.search(r"^\s*([^:]+?)\s*(?:\([^)]*\))?\s*mucked\s*\[([^\]]+)\]", v, flags=re.IGNORECASE)
            if not m:
                continue
            name = m.group(1).strip()
            inner = m.group(2).strip()
            toks = [t.strip().lower() for t in re.split(r"\s+", inner) if t.strip()]
            if len(toks) >= 2:
                out[name] = toks[:2]
        return out

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
        # Street and action info moved/removed from bottom row (street now in Info panel)

        # Flash seat overlay for this action (for player actions only, not board)
        if actions and 0 <= self.current_action_index < len(actions):
            act = actions[self.current_action_index]
            if act.get('player') and act['player'] != 'Board':
                txt = self._action_to_overlay_text(act.get('action'))
                if txt:
                    self.show_action_flash(act['player'], txt)

        # Recompute folded players based on the state immediately BEFORE the current action.
        # This ensures that when you backtrack to a fold action, the player's cards are restored
        # (fold not yet applied at the current action index).
        prev_idx = max(-1, (self.current_action_index or 0) - 1)
        try:
            self.folded_players = self.compute_folded_players_upto(
                hand, self.current_street, prev_idx
            )
        except Exception:
            self.folded_players = set()

        # Compute sitting-out state immediately BEFORE the current action,
        # so stepping backward to a sit-out action shows the player as active (not yet applied).
        prev_idx_for_state = max(-1, (self.current_action_index or 0) - 1)
        try:
            self.sitting_out_players = self.compute_sitting_out_upto(
                hand, self.current_street, prev_idx_for_state
            )
        except Exception:
            # Fall back to just seat info
            try:
                self.sitting_out_players = {
                    p['name'] for p in hand.get('players', []) if p.get('sitting_out')
                }
            except Exception:
                self.sitting_out_players = set()

        # If stepping forward and the CURRENT action toggles sit-out state, apply immediately
        last_idx = getattr(self, "_last_action_index", None)
        if actions and 0 <= self.current_action_index < len(actions):
            cur_act = actions[self.current_action_index]
            cur_name = cur_act.get('player')
            cur_action = (cur_act.get('action') or '').lower()
            if last_idx is not None and self.current_action_index > last_idx and cur_name and cur_name != 'Board':
                if cur_action == 'is sitting out':
                    self.sitting_out_players.add(cur_name)
                elif cur_action == 'has returned':
                    self.sitting_out_players.discard(cur_name)

        # Rebuild visible hole cards based on hero info and any prior 'shows' before the current action.
        # Start with all unknowns.
        try:
            self.player_cards = {p['name']: ['??', '??'] for p in hand['players']}
        except Exception:
            self.player_cards = {}
        # Reveal hero hole cards if available
        hero_name = hand.get('hero')
        hole = hand.get('hole_cards')
        if hero_name and hole:
            parts = [p.strip() for p in re.split(r'[\s,]+', hole) if p.strip()]
            if len(parts) >= 2:
                self.player_cards[hero_name] = [parts[0], parts[1]]
        # Apply shown cards up to BEFORE the current action
        prev_idx_for_show = max(-1, (self.current_action_index or 0) - 1)
        try:
            shown_map = self.compute_shown_cards_upto(hand, self.current_street, prev_idx_for_show)
            for name, cards in shown_map.items():
                self.player_cards[name] = cards
        except Exception:
            pass
        # If the CURRENT action is a 'shows', apply it immediately so the reveal happens on this action
        if actions and 0 <= self.current_action_index < len(actions):
            cur_act = actions[self.current_action_index]
            if cur_act.get('action') == 'shows' and cur_act.get('player') not in (None, 'Board'):
                now_cards = self._extract_shown_cards(cur_act.get('detail', '') or '')
                if now_cards:
                    self.player_cards[cur_act['player']] = now_cards

        # Rebuild visible hole cards based on hero info and any prior 'shows' before the current action.
        # Start with all unknowns.
        try:
            self.player_cards = {p['name']: ['??', '??'] for p in hand['players']}
        except Exception:
            self.player_cards = {}
        # Reveal hero hole cards if available
        hero_name = hand.get('hero')
        hole = hand.get('hole_cards')
        if hero_name and hole:
            parts = [p.strip() for p in re.split(r'[\s,]+', hole) if p.strip()]
            if len(parts) >= 2:
                self.player_cards[hero_name] = [parts[0], parts[1]]
        # Apply shown cards up to BEFORE the current action
        prev_idx_for_show = max(-1, (self.current_action_index or 0) - 1)
        try:
            shown_map = self.compute_shown_cards_upto(hand, self.current_street, prev_idx_for_show)
            for name, cards in shown_map.items():
                self.player_cards[name] = cards
        except Exception:
            pass
        # If the CURRENT action is a 'shows', apply it immediately so the reveal happens on this action
        if actions and 0 <= self.current_action_index < len(actions):
            cur_act = actions[self.current_action_index]
            if cur_act.get('action') == 'shows' and cur_act.get('player') not in (None, 'Board'):
                now_cards = self._extract_shown_cards(cur_act.get('detail', '') or '')
                if now_cards:
                    self.player_cards[cur_act['player']] = now_cards

        # Apply mucked cards (from SUMMARY) once a player takes the 'mucks' action at showdown.
        # Persist these cards for the remainder of the hand replay.
        try:
            mucked_from_summary = self._extract_mucked_cards_from_summary(hand)
            # Players who have already mucked before the current action
            mucks_before = set()
            for i in range(max(0, prev_idx_for_show + 1)):
                a = actions[i]
                if a.get('action') == 'mucks' and a.get('player'):
                    mucks_before.add(a['player'])
            for name in mucks_before:
                if name in mucked_from_summary:
                    self.player_cards[name] = mucked_from_summary[name]
            # If CURRENT action is 'mucks', reveal immediately
            if actions and 0 <= self.current_action_index < len(actions):
                cur_act = actions[self.current_action_index]
                if cur_act.get('action') == 'mucks':
                    name = cur_act.get('player')
                    if name and name in mucked_from_summary:
                        self.player_cards[name] = mucked_from_summary[name]
        except Exception:
            pass

        # If stepping forward and the CURRENT action is a fold, apply it immediately so
        # the player's cards disappear while showing the FOLD action and flash.
        last_idx = getattr(self, "_last_action_index", None)
        if actions and 0 <= self.current_action_index < len(actions):
            cur_act = actions[self.current_action_index]
            if (
                    last_idx is not None
                    and self.current_action_index > last_idx
                    and cur_act.get('action') == 'folds'
                    and cur_act.get('player') not in (None, 'Board')
            ):
                self.folded_players.add(cur_act['player'])
        
        self.prev_button.config(state='normal' if self.current_action_index > 0 else 'disabled')
        self.next_button.config(state='normal' if self.has_next_action() else 'disabled')
        # Refresh table to update pot and bet markers
        self.update_table_canvas()
        self.display_action_history()
        # Update info panel (blinds/ante/pot/pot odds)
        self.update_info_panel()
        self._last_action_index = self.current_action_index

        # Update CD-style button states based on current position
        try:
            hand = self.hands[self.current_hand_index]
        except Exception:
            hand = None
        if hand:
            # First button disabled only if we're at very first action overall
            first_s, first_i = self._get_first_action_pos(hand)
            at_first = (self.current_street == first_s and (self.current_action_index or 0) <= first_i)
            self.first_button.config(state='disabled' if at_first else 'normal')
            # Last button disabled only if we're at very last action overall
            last_s, last_i = self._get_last_action_pos(hand)
            at_last = (self.current_street == last_s and (self.current_action_index or 0) >= last_i)
            self.last_button.config(state='disabled' if at_last else 'normal')
        else:
            self.first_button.config(state='disabled')
            self.last_button.config(state='disabled')

    # ====== Jump helpers (beginning/end of hand) ======
    def _get_first_action_pos(self, hand):
        """
        Return (street_name, action_index) for the first action in the hand.
        If no actions exist, default to ('preflop', 0).
        """
        streets = ['preflop', 'flop', 'turn', 'river']
        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if actions:
                return s, 0
        return 'preflop', 0

    def _get_last_action_pos(self, hand):
        """
        Return (street_name, action_index) for the last action in the hand.
        If no actions exist, default to ('preflop', 0).
        """
        streets = ['preflop', 'flop', 'turn', 'river']
        last_s = None
        last_i = 0
        for s in streets:
            actions = hand.get('actions', {}).get(s, []) or []
            if actions:
                last_s = s
                last_i = len(actions) - 1
        if last_s is None:
            return 'preflop', 0
        return last_s, last_i

    def jump_to_hand_start(self):
        """Jump to the first action of the current hand."""
        if not self.hands or self.current_hand_index is None:
            return
        hand = self.hands[self.current_hand_index]
        s, i = self._get_first_action_pos(hand)
        self.current_street = s
        self.current_action_index = i
        self.update_action_viewer()

    def jump_to_hand_end(self):
        """Jump to the last action of the current hand."""
        if not self.hands or self.current_hand_index is None:
            return
        hand = self.hands[self.current_hand_index]
        s, i = self._get_last_action_pos(hand)
        self.current_street = s
        self.current_action_index = i
        self.update_action_viewer()

    def display_action_history(self):
        if not self.hands or self.current_hand_index is None:
            return
        hand = self.hands[self.current_hand_index]
        lines = []
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

    def _action_to_overlay_text(self, action: str) -> str:
        """
        Map action keywords to seat overlay text. Return "" for actions we don't flash.
        """
        if not action:
            return ""
        a = action.lower()
        mapping = {
            'bets': 'BET',
            'calls': 'CALL',
            'raises': 'RAISE',
            'checks': 'CHECK',
            'folds': 'FOLD',
            'shows': 'SHOWS',
            'mucks': 'MUCKS',
            'is sitting out': 'SIT OUT',
            'has returned': 'RETURNED',
            'wins': 'WINS',
            'collected': 'WINS',
            # Intentionally exclude 'posts' and 'antes' to avoid flashing on forced bets
        }
        return mapping.get(a, "")

    def show_action_flash(self, player_name: str, overlay_text: str):
        """
        Show a transient action overlay in the player's seat, then clear after ACTION_FLASH_MS.
        """
        # Cancel any existing scheduled clear
        if self._seat_action_flash_after is not None:
            try:
                self.root.after_cancel(self._seat_action_flash_after)
            except Exception:
                pass
            self._seat_action_flash_after = None

        # Set flash state and repaint
        self.seat_action_flash = {'name': player_name, 'text': overlay_text}
        self.update_table_canvas()

        # Schedule clear
        self._seat_action_flash_after = self.root.after(ACTION_FLASH_MS, self.clear_action_flash)

    def clear_action_flash(self):
        """Clear any transient action overlay and repaint."""
        self.seat_action_flash = None
        if self._seat_action_flash_after is not None:
            try:
                self.root.after_cancel(self._seat_action_flash_after)
            except Exception:
                pass
            self._seat_action_flash_after = None
        self.update_table_canvas()

    # ====== Info panel helpers ======
    def _compute_true_bb(self, hand):
        """
        True BB = (sum of all antes and blinds at the very start of the hand) * 2/3.
        We scan preflop actions from the top, summing consecutive 'posts' and 'antes'
        until the first non-forced-bet action appears.
        Returns an integer number of chips, or None if unavailable.
        """
        try:
            actions_pf = hand.get('actions', {}).get('preflop', []) or []
            forced_sum = 0
            for a in actions_pf:
                act = (a.get('action') or '').lower()
                if act in ('posts', 'antes'):
                    forced_sum += self._extract_first_amount(a.get('detail', '') or '')
                else:
                    break
            if forced_sum <= 0:
                return None
            return int(round((forced_sum * 2) / 3.0))
        except Exception:
            return None
    def _fmt_amount(self, amt):
        try:
            return f"${amt:,}"
        except Exception:
            return f"${amt}"

    def _update_stack_mode_styles(self):
        """
        Visually emphasize the selected stack view mode:
          - Selected: bold label, thicker solid border.
          - Unselected: normal label, ridge border.
        """
        try:
            selected = self.stack_view_mode.get()
        except Exception:
            selected = "Chips"
        buttons = getattr(self, "_stack_radio_buttons", {}) or {}
        for value, rb in buttons.items():
            if not isinstance(rb, tk.Radiobutton):
                continue
            if value == selected:
                rb.config(font=("Arial", 12, "bold"), bd=3, relief="solid")
            else:
                rb.config(font=("Arial", 12, "normal"), bd=2, relief="ridge")

    def _format_stack_display(self, chips_value, hand):
        """
        Format a player's stack according to the selected display mode:
          - Chips: "$<chips>"
          - BB:    "<stack/bb> BB"
          - True BB: "<stack/true_bb> tBB"
          - M:     "<stack / (SB + BB + Ante*players)> M"
        Falls back to "$<chips>" if inputs are unavailable.
        """
        # Non-numeric or special strings (e.g., "sitting out") pass through unchanged
        if not isinstance(chips_value, (int, float)):
            return str(chips_value)

        # Mode detection (default to "Chips" if anything goes wrong)
        try:
            mode = self.stack_view_mode.get()
        except Exception:
            mode = "Chips"

        if mode == "Chips":
            return f"${chips_value}"

        # Blinds/ante from preflop actions
        sb, bb, ante = self._extract_blinds_antes(hand)

        if mode == "BB":
            if bb and bb > 0:
                return f"{(chips_value / bb):.1f} BB"
            return f"${chips_value}"

        if mode == "True BB":
            try:
                tbb = self._compute_true_bb(hand)
            except Exception:
                tbb = None
            if tbb and tbb > 0:
                return f"{(chips_value / tbb):.1f} tBB"
            return f"${chips_value}"

        if mode == "M":
            players_count = len((hand or {}).get('players', []) or [])
            denom = (sb or 0) + (bb or 0) + (ante or 0) * players_count
            if denom > 0:
                return f"{(chips_value / denom):.1f} M"
            return f"${chips_value}"

        return f"${chips_value}"

    def _extract_blinds_antes(self, hand):
        """
        Derive small/big blinds and ante amounts from preflop actions.
        Returns (sb, bb, ante) as ints or None if not seen.
        """
        sb = bb = ante = None
        for act in hand.get('actions', {}).get('preflop', []):
            action = act.get('action')
            detail = (act.get('detail') or "").lower()
            if action == 'posts':
                if sb is None and 'small blind' in detail:
                    sb = self._extract_first_amount(detail)
                elif bb is None and 'big blind' in detail:
                    bb = self._extract_first_amount(detail)
            elif action == 'antes':
                # Tournament antes are typically uniform; take first seen
                if ante is None:
                    ante = self._extract_first_amount(detail)
        return sb, bb, ante

    def _extract_bounty_from_header(self, header: str):
        """
        Extract KO bounty amount from a tournament header line.
        Expected pattern examples:
          - "$3 + $0.30 KO Sit & Go"  -> returns "$0.30"
          - "$5 + $1 Knockout"        -> returns "$1" (handles 'Knockout' too)
        Returns a string like "$0.30" if found, else None.
        """
        if not header:
            return None
        # Look for: $<buyin> + $<bounty> (KO|Knockout)
        m = re.search(
            r"\$\s*\d+(?:\.\d{1,2})?\s*\+\s*\$(\d+(?:\.\d{1,2})?)\s*(?:KO|Knockout)\b",
            header,
            flags=re.IGNORECASE
        )
        if m:
            bounty_val = m.group(1)
            # Normalize to two decimals if needed
            if '.' in bounty_val:
                parts = bounty_val.split('.')
                bounty_val = f"{parts[0]}.{(parts[1] + '00')[:2]}"
            return f"${bounty_val}"
        return None
    
    def update_info_panel(self):
        """
        Populate Info panel:
          - Blinds: SB/BB
          - Ante
          - Hand number (tournament index)
          - Pot: pot before the current action
          - Pot odds: for the current actor (to call amount / (pot + to call))
        """
        # Defaults
        self.info_handno_var.set(INFO_PLACEHOLDER)
        self.info_blinds_var.set(INFO_PLACEHOLDER)
        self.info_ante_var.set(INFO_PLACEHOLDER)
        self.info_pot_var.set(INFO_PLACEHOLDER)
        self.info_truebb_var.set(INFO_PLACEHOLDER)
        self.info_pot_odds_var.set(INFO_PLACEHOLDER)
        self.info_street_var.set(INFO_PLACEHOLDER)
        self.info_pot_odds_player_var.set("")
        self.info_pts_var.set(INFO_PLACEHOLDER)

        if not self.hands or self.current_hand_index is None or self.current_street is None:
            # nothing to display
            return
        hand = self.hands[self.current_hand_index]
        # Street name (Info panel, row with Hand #)
        try:
            self.info_street_var.set(self.current_street.title() if self.current_street else INFO_PLACEHOLDER)
        except Exception:  # safety: current_street might be None
            self.info_street_var.set(INFO_PLACEHOLDER)

        # Hand number (current index + 1)
        self.info_handno_var.set(str(self.current_hand_index + 1))
        # Blinds / Ante
        sb, bb, ante = self._extract_blinds_antes(hand)
        blinds_text = INFO_PLACEHOLDER
        if sb is not None or bb is not None:
            left = self._fmt_amount(sb) if sb is not None else "?"
            right = self._fmt_amount(bb) if bb is not None else "?"
            blinds_text = f"{left}/{right}"
            # Append ante inline if present: "Blinds: $SB/$BB, Ante $X"
            if ante is not None:
                blinds_text += f", Ante {self._fmt_amount(ante)}"
        self.info_blinds_var.set(blinds_text)
        # Ante is now displayed inline with Blinds; keep the separate var unused
        # to avoid showing a placeholder elsewhere.
        self.info_ante_var.set("")

        # True BB (2/3 of all forced bets at start of hand).
        # Only applicable when antes are in play; otherwise show "N/A".
        if ante is None or ante <= 0:
            self.info_truebb_var.set("N/A")
        else:
            try:
                true_bb = self._compute_true_bb(hand)
                if true_bb is None:
                    self.info_truebb_var.set("N/A")
                else:
                    self.info_truebb_var.set(self._fmt_amount(true_bb))
            except Exception:
                self.info_truebb_var.set("N/A")


        # Pot before current action index
        # Use previous action index so the pot reflects the state the actor is facing
        prev_idx = max(-1, (self.current_action_index or 0) - 1)

        # Ensure initial pot includes all forced bets (antes + blinds) on preflop.
        # When a hand is first loaded, prev_idx will be -1, which would omit forced bets.
        # Bump prev_idx to the index of the last leading forced bet so the Info panel
        # shows the correct initial pot immediately.
        if self.current_street == 'preflop':
            actions_pf = hand.get('actions', {}).get('preflop', [])
            forced_end_idx = -1
            for i, a in enumerate(actions_pf):
                if a.get('action') in ('posts', 'antes'):
                    forced_end_idx = i
                else:
                    break
            if prev_idx < forced_end_idx:
                prev_idx = forced_end_idx

        try:
            pot_before = self.compute_pot_upto(hand, self.current_street, prev_idx)
        except Exception:
            pot_before = 0
        self.info_pot_var.set(self._fmt_amount(pot_before))

        # Helper(s) for SPR (Stack-to-Pot Ratio) — computed for the Hero only.
        # Uses effective_stack / pot_amount where "effective stack" follows:
        # - If exactly 2 active players: lesser of the two remaining stacks.
        # - If >2 active players and Hero is the smallest: Hero's remaining stack.
        # - Otherwise take the average of all active stacks; if Hero is the largest, exclude Hero from that average.
        def _detect_hero_name(h):
            try:
                # Common patterns for hero detection
                if isinstance(h.get('hero', None), str):
                    return h.get('hero')
                players = h.get('players', [])
                for p in players or []:
                    if isinstance(p, dict):
                        if p.get('is_hero') or p.get('hero'):
                            return p.get('name') or p.get('player')
                # Fallback to instance attribute if present
                return getattr(self, 'hero_name', None)
            except Exception:
                return getattr(self, 'hero_name', None)

        def _starting_stacks(h):
            stacks = {}
            # Dict form: {"Alice": 1500, "Bob": 1800, ...}
            if isinstance(h.get('stacks'), dict):
                for n, amt in h.get('stacks', {}).items():
                    try:
                        stacks[n] = float(amt)
                    except Exception:
                        pass
                if stacks:
                    return stacks
            # Players list form: [{"name": "...", "stack": ...}, ...]
            players = h.get('players', [])
            for p in players or []:
                if isinstance(p, dict):
                    name = p.get('name') or p.get('player')
                    if not name:
                        continue
                    stack = p.get('stack', None)
                    if stack is None:
                        stack = p.get('chips', None)
                    if stack is None:
                        stack = p.get('starting_stack', None)
                    try:
                        if stack is not None:
                            stacks[name] = float(stack)
                    except Exception:
                        pass
            return stacks

        def _street_order(actions_by_street):
            # Normalize and order known streets; only include present keys, respecting typical order.
            present = list(actions_by_street.keys() or [])
            order_names = ['preflop', 'pre-flop', 'pre flop', 'flop', 'turn', 'river', 'showdown']
            ordered = []
            for want in order_names:
                for k in present:
                    if isinstance(k, str) and k.lower() == want:
                        if k not in ordered:
                            ordered.append(k)
            # Append any remaining keys in original order, if not already included
            for k in present:
                if k not in ordered:
                    ordered.append(k)
            return ordered

        def _total_contrib_and_folds_upto(h, street_key, upto_idx):
            """
            Aggregate total contributed chips per player across all streets up to
            and including upto_idx on street_key. Also track folds.
            """
            by_street = h.get('actions', {}) or {}
            contrib = {}
            folded = set()
            order = _street_order(by_street)
            # Helper for adding/subtracting
            def add_amt(d, k, v):
                d[k] = d.get(k, 0.0) + float(v)
            for sk in order:
                acts = by_street.get(sk, []) or []
                last_idx = len(acts) - 1
                if sk == street_key:
                    last_idx = upto_idx
                if last_idx < 0:
                    if sk == street_key:
                        break
                    else:
                        continue
                for i in range(0, min(last_idx, len(acts) - 1) + 1):
                    a = acts[i] or {}
                    p = a.get('player')
                    if not p or p == 'Board':
                        continue
                    t = str(a.get('type', '')).lower()
                    # detect amount-like fields
                    amt = a.get('amount', None)
                    if amt is None:
                        # try common fields
                        for k in ('bet', 'raise_to', 'posted', 'ante'):
                            if a.get(k) is not None:
                                amt = a.get(k)
                                break
                    # fold tracking
                    if t == 'fold':
                        folded.add(p)
                    # uncalled/returned chips reduce contribution
                    if 'uncalled' in t or 'return' in t:
                        try:
                            if amt is not None:
                                add_amt(contrib, p, -abs(float(amt)))
                        except Exception:
                            pass
                        continue
                    # chip-committing actions
                    if amt is not None and t not in ('win', 'collect'):
                        try:
                            add_amt(contrib, p, abs(float(amt)))
                        except Exception:
                            pass
                if sk == street_key:
                    break
            return contrib, folded

        def _remaining_stacks_upto(h, street_key, upto_idx):
            base = _starting_stacks(h)
            contrib, folded = _total_contrib_and_folds_upto(h, street_key, upto_idx)
            remain = {}
            for p, s in base.items():
                left = s - float(contrib.get(p, 0.0))
                remain[p] = left if left > 0 else 0.0
            return remain, folded

        def _effective_stack_for_hero(remain_map, folded_set, hero_name):
            # Active players: not folded and with chips remaining
            active = [p for p, s in remain_map.items() if s > 0 and p not in folded_set]
            if hero_name is None or hero_name not in remain_map or hero_name not in active:
                return None
            hero_stack = remain_map.get(hero_name, 0.0)
            others = [remain_map[p] for p in active if p != hero_name]
            if len(active) < 2 or hero_stack <= 0:
                return None
            if len(active) == 2:
                # heads-up: effective = lesser of two stacks
                other_stack = others[0] if others else 0.0
                return min(hero_stack, other_stack)
            # 3+ players
            min_other = min(others) if others else 0.0
            max_other = max(others) if others else 0.0
            if hero_stack <= min_other:
                return hero_stack
            if hero_stack >= max_other:
                # exclude hero from average
                return (sum(others) / len(others)) if others else None
            # otherwise average of all active stacks (including hero)
            return (hero_stack + sum(others)) / (len(others) + 0)  # len(active)

        def _set_spr_for_state(h, street_key, upto_idx, pot_amount):
            try:
                hero = _detect_hero_name(h)
                remain_map, folded_set = _remaining_stacks_upto(h, street_key, upto_idx)
                eff = _effective_stack_for_hero(remain_map, folded_set, hero)
                pot_amt = float(pot_amount)
                # SPR (hero-only): effective stack / pot
                if eff is None or eff <= 0 or pot_amt <= 0:
                    self.info_spr_var.set(INFO_PLACEHOLDER)
                else:
                    spr = (eff / pot_amt)
                    self.info_spr_var.set(f"{spr:.2f}")
                # PTS (hero-only): percent the pot represents of HERO's remaining stack
                hero_stack = None
                if hero and (hero in remain_map) and (hero not in folded_set):
                    try:
                        hero_stack = float(remain_map.get(hero, 0.0))
                    except Exception:
                        hero_stack = None
                if hero_stack is None or hero_stack <= 0:
                    self.info_pts_var.set(INFO_PLACEHOLDER)
                else:
                    # If pot is 0, show 0.0%
                    pts_pct = (pot_amt / hero_stack) * 100.0 if pot_amt >= 0 else 0.0
                    self.info_pts_var.set(f"{pts_pct:.1f}%")
            except Exception:
                self.info_spr_var.set(INFO_PLACEHOLDER)
                self.info_pts_var.set(INFO_PLACEHOLDER)

        # Pot odds for current actor (if applicable)
        actions = hand.get('actions', {}).get(self.current_street, []) or []
        if not actions:
            self.info_pot_odds_var.set(INFO_PLACEHOLDER)
            self.info_pot_odds_player_var.set("")
            # Update SPR for hero using current pot (no further actions on this street yet)
            _set_spr_for_state(hand, self.current_street, -1, pot_before)
            return

        # We want pot odds for the NEXT action, based on the state AFTER the current action.
        # Determine the index representing "now" state (apply current action if any),
        # and then find the next player to act on this street.
        cur_idx = self.current_action_index if self.current_action_index is not None else -1
        if cur_idx >= len(actions):
            cur_idx = len(actions) - 1

        # Compute pot for next actor (state after current action)
        try:
            pot_for_next = self.compute_pot_upto(hand, self.current_street, max(-1, cur_idx))
        except Exception:
            pot_for_next = pot_before  # fallback to previously computed pot_before

        # Compute street contributions up to and including current index (state after current action)
        try:
            contrib_after, _ = self.compute_street_contrib_upto(hand, self.current_street, max(-1, cur_idx))
        except Exception:
            contrib_after = {}

        # Find the next player action on this street
        next_actor = None
        next_idx = cur_idx + 1
        while next_idx < len(actions):
            a = actions[next_idx]
            p = a.get('player')
            if p and p != 'Board':
                next_actor = p
                break
            next_idx += 1

        if not next_actor:
            self.info_pot_odds_var.set(INFO_PLACEHOLDER)
            self.info_pot_odds_player_var.set("")
            # Even if no next actor, still update SPR for hero at this state.
            _set_spr_for_state(hand, self.current_street, max(-1, cur_idx), pot_for_next)
            return

        # Facing call for next actor = max contribution - that player's contribution
        highest = 0
        if contrib_after:
            try:
                highest = max(contrib_after.values())
            except Exception:
                highest = 0
        actor_paid = contrib_after.get(next_actor, 0)
        to_call = max(0, highest - actor_paid)

        if to_call > 0:
            # Break-even equity: to_call / (pot_for_next + to_call)
            denom = pot_for_next + to_call
            odds = (to_call / denom) if denom > 0 else 0.0
            pct = f"{(odds * 100):.1f}%"
            # Offer ratio as pot:call -> x-to-1, i.e., pot_for_next / to_call
            ratio = (pot_for_next / to_call) if to_call > 0 else 0.0
            ratio_str = f"{ratio:.1f}-to-1"
            # Display format split across columns:
            #   col1: "x-to-1 [y%]" (left)
            #   col3: player name (right)
            # Inline the actor name after the % to avoid shifting right-aligned columns
            # when names of different lengths appear.
            self.info_pot_odds_var.set(f"{ratio_str} [{pct}] {next_actor}")
            self.info_pot_odds_player_var.set("")
        else:
            # No call required -> N/A
            self.info_pot_odds_var.set("N/A")
            self.info_pot_odds_player_var.set("")

        # Update SPR for hero using the pot for the next state on this street.
        _set_spr_for_state(hand, self.current_street, max(-1, cur_idx), pot_for_next)

    # ====== Notes / SQLite helpers ======
    def _init_db(self):
        """
        Initialize a central SQLite database at ~/.full_tilt_90man_replayer/notes.sqlite3
        with a notes table keyed by Game # (hand_id).
        """
        try:
            home = os.path.expanduser("~")
            db_dir = os.path.join(home, ".full_tilt_90man_replayer")
            os.makedirs(db_dir, exist_ok=True)
            self._db_path = os.path.join(db_dir, "notes.sqlite3")
            self._db = sqlite3.connect(self._db_path)
            self._db.execute("""
                             CREATE TABLE IF NOT EXISTS notes (
                                                                  hand_id   TEXT PRIMARY KEY,
                                                                  note      TEXT,
                                                                  mistakes  TEXT,
                                                                  updated_at TEXT DEFAULT (datetime('now'))
                                 )
                             """)
            self._db.commit()
        except Exception as e:
            # Non-fatal; notes features will be disabled if DB init fails
            self._db = None
            try:
                print(f"Failed to initialize notes DB: {e}")
            except Exception:
                pass

    def _db_conn(self):
        return self._db

    def _get_hand_id_for_index(self, hand_index):
        try:
            if hand_index is None or hand_index < 0 or hand_index >= len(self.hands):
                return ""
            hand = self.hands[hand_index]
            header = (hand or {}).get('header') or ""
            meta = self._extract_session_info(header)
            return meta.get("hand_no") or ""
        except Exception:
            return ""

    def _current_hand_id(self):
        return self._get_hand_id_for_index(getattr(self, 'current_hand_index', None))

    def _load_notes_from_db(self, hand_id):
        """
        Return (note, mistakes) strings for a given hand_id. Empty strings if not found.
        """
        try:
            conn = self._db_conn()
            if not conn or not hand_id:
                return "", ""
            cur = conn.execute("SELECT note, mistakes FROM notes WHERE hand_id = ?", (hand_id,))
            row = cur.fetchone()
            if not row:
                return "", ""
            note_val = row[0] if row[0] is not None else ""
            mistakes_val = row[1] if row[1] is not None else ""
            return str(note_val), str(mistakes_val)
        except Exception:
            return "", ""

    def _save_notes_to_db(self, hand_id, note, mistakes):
        """
        Upsert the notes record for hand_id. If both fields are empty, deletes the record.
        """
        try:
            conn = self._db_conn()
            if not conn or not hand_id:
                return
            n = (note or "").strip()
            m = (mistakes or "").strip()
            if n == "" and m == "":
                conn.execute("DELETE FROM notes WHERE hand_id = ?", (hand_id,))
                conn.commit()
                return
            conn.execute(
                """
                INSERT INTO notes (hand_id, note, mistakes, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(hand_id) DO UPDATE SET
                    note = excluded.note,
                                                mistakes = excluded.mistakes,
                                                updated_at = excluded.updated_at
                """,
                (hand_id, n, m),
            )
            conn.commit()
        except Exception:
            pass

    def _hand_has_note_in_db(self, hand_id):
        """
        True if there is a non-empty note or mistakes saved for hand_id.
        """
        try:
            conn = self._db_conn()
            if not conn or not hand_id:
                return False
            cur = conn.execute("SELECT note, mistakes FROM notes WHERE hand_id = ?", (hand_id,))
            row = cur.fetchone()
            if not row:
                return False
            n = (row[0] or "").strip()
            m = (row[1] or "").strip()
            return (n != "") or (m != "")
        except Exception:
            return False

    def _hands_with_notes_set(self, hand_ids):
        """
        Given a list of hand_ids, return a set of those that have non-empty records.
        """
        out = set()
        try:
            conn = self._db_conn()
            if not conn:
                return out
            # Filter empties
            ids = [hid for hid in (hand_ids or []) if hid]
            if not ids:
                return out
            # Build a parameterized IN clause
            q_marks = ",".join(["?"] * len(ids))
            cur = conn.execute(f"SELECT hand_id, note, mistakes FROM notes WHERE hand_id IN ({q_marks})", ids)
            for hand_id, note, mistakes in cur.fetchall() or []:
                n = (note or "").strip()
                m = (mistakes or "").strip()
                if (n != "") or (m != ""):
                    out.add(hand_id)
        except Exception:
            return out
        return out

    def on_notes_changed(self, _event=None):
        if self._loading_notes:
            return
        self.notes_dirty = True

    def load_notes_for_current_hand(self):
        """
        Load notes for the currently selected hand into the Notes and Mistakes text widgets.
        """
        if not (self.notes_text and self.mistakes_text):
            return
        hand_id = self._current_hand_id()
        note_val, mistakes_val = self._load_notes_from_db(hand_id)
        self._loading_notes = True
        try:
            self.notes_text.delete("1.0", tk.END)
            self.notes_text.insert("1.0", note_val or "")
            self.mistakes_text.delete("1.0", tk.END)
            self.mistakes_text.insert("1.0", mistakes_val or "")
            self.notes_dirty = False
        finally:
            self._loading_notes = False

    def save_current_hand_notes(self):
        """
        Explicit save button action.
        """
        hand_id = self._current_hand_id()
        if not hand_id:
            return
        note_val = ""
        mistakes_val = ""
        if self.notes_text:
            note_val = self.notes_text.get("1.0", "end-1c")
        if self.mistakes_text:
            mistakes_val = self.mistakes_text.get("1.0", "end-1c")
        self._save_notes_to_db(hand_id, note_val, mistakes_val)
        self.notes_dirty = False
        # Update marker for current hand
        idx = getattr(self, 'current_hand_index', None)
        if idx is not None:
            self._update_hand_note_marker(idx)

    def clear_notes(self):
        """
        Clear both fields and remove the record immediately.
        """
        if self.notes_text:
            self.notes_text.delete("1.0", tk.END)
        if self.mistakes_text:
            self.mistakes_text.delete("1.0", tk.END)
        hand_id = self._current_hand_id()
        if hand_id:
            try:
                conn = self._db_conn()
                if conn:
                    conn.execute("DELETE FROM notes WHERE hand_id = ?", (hand_id,))
                    conn.commit()
            except Exception:
                pass
        self.notes_dirty = False
        # Update marker for current hand
        idx = getattr(self, 'current_hand_index', None)
        if idx is not None:
            self._update_hand_note_marker(idx)

    def maybe_auto_save_notes_for_hand(self, hand_index):
        """
        Auto-save notes if dirty when switching away from a hand.
        Uses the current content of the Note/Mistakes widgets and saves them under the hand_index provided.
        """
        if not self.notes_dirty:
            return
        hand_id = self._get_hand_id_for_index(hand_index)
        if not hand_id:
            self.notes_dirty = False
            return
        note_val = ""
        mistakes_val = ""
        if self.notes_text:
            note_val = self.notes_text.get("1.0", "end-1c")
        if self.mistakes_text:
            mistakes_val = self.mistakes_text.get("1.0", "end-1c")
        self._save_notes_to_db(hand_id, note_val, mistakes_val)
        self.notes_dirty = False

    def _update_hand_note_marker(self, idx):
        """
        Add or remove the '#' marker for a given hand index depending on DB state.
        """
        if idx is None or idx < 0 or idx >= len(self.hands):
            return
        # Remove existing marker if present
        old = self.hand_note_markers.pop(idx, None)
        if old:
            try:
                self.hand_selector_canvas.delete(old)
            except Exception:
                pass
        # Recreate if needed
        hand_id = self._get_hand_id_for_index(idx)
        if not (hand_id and self._hand_has_note_in_db(hand_id)):
            return
        # Compute rectangle top-left for this index
        x = idx * (self._selector_box_w + self._selector_gap) + self._selector_gap
        y = self._selector_y_base
        try:
            mark_id = self.hand_selector_canvas.create_text(
                x + 4, y + 4, text="#", fill="#111", font=("Arial", 12, "bold"), anchor="nw"
            )
            self.hand_note_markers[idx] = mark_id
        except Exception:
            pass

    def on_close(self):
        """
        Save notes if dirty and close the application.
        """
        try:
            # Auto-save current hand's notes if dirty
            cur_idx = getattr(self, 'current_hand_index', None)
            if cur_idx is not None:
                self.maybe_auto_save_notes_for_hand(cur_idx)
        except Exception:
            pass
        try:
            if self._db:
                self._db.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _extract_session_info(self, header: str):
        """
        Extract session/tournament metadata from the hand header line.
        Returns dict with keys: room, game, date, hand_no, table_no, bounty
        Falls back to INFO_PLACEHOLDER-like empty strings if not found.
        """
        if not header:
            header = ""
        room = ""
        hand_no = ""
        table_no = ""
        date_str = ""
        game = ""
        # Room (prefix before "Game #")
        m = re.match(r"^\s*(.+?)\s+Game\s*#", header, flags=re.IGNORECASE)
        if m:
            room = m.group(1).strip()
        # Hand number after "Game #"
        m = re.search(r"Game\s*#\s*([0-9]+)", header, flags=re.IGNORECASE)
        if m:
            hand_no = m.group(1).strip()
        # Table number like "Table 4" (first occurrence)
        m = re.search(r"\bTable\s+([A-Za-z0-9\-]+)", header, flags=re.IGNORECASE)
        if m:
            table_no = m.group(1).strip()
        # Date in YYYY/MM/DD or YYYY-MM-DD
        m_all = re.findall(r"\b(\d{4}[/-]\d{2}[/-]\d{2})\b", header)
        if m_all:
            date_str = m_all[-1]  # take the last date-like token
        # Game: pick a segment (split by ' - ') that looks like a poker game name
        candidates = [seg.strip() for seg in header.split(" - ") if seg.strip()]
        game_keywords = ("hold", "omaha", "stud", "razz", "limit", "draw", "hilo", "hi/lo", "eight-or-better")
        for seg in candidates:
            s = seg.lower()
            if any(k in s for k in game_keywords):
                game = seg
                break
        # Bounty from header
        bounty = self._extract_bounty_from_header(header) or ""
        return {
            "room": room or "",
            "game": game or "",
            "date": date_str or "",
            "hand_no": hand_no or "",
            "table_no": table_no or "",
            "bounty": bounty or "",
        }

    def update_session_panel(self):
        """
        Populate the Session panel beneath Info:
          - Room, Game, Date, Hand #, Table #, Bounty
        """
        # Defaults
        self.session_room_var.set(INFO_PLACEHOLDER)
        self.session_game_var.set(INFO_PLACEHOLDER)
        self.session_date_var.set(INFO_PLACEHOLDER)
        self.session_hand_var.set(INFO_PLACEHOLDER)
        self.session_table_var.set(INFO_PLACEHOLDER)
        self.info_bounty_var.set(INFO_PLACEHOLDER)

        if not self.hands or self.current_hand_index is None:
            return
        try:
            hand = self.hands[self.current_hand_index]
        except Exception:
            return
        header = hand.get('header') or ""
        meta = self._extract_session_info(header)
        # Set values (use placeholder if empty)
        self.session_room_var.set(meta.get("room") or INFO_PLACEHOLDER)
        self.session_game_var.set(meta.get("game") or INFO_PLACEHOLDER)
        self.session_date_var.set(meta.get("date") or INFO_PLACEHOLDER)
        self.session_hand_var.set(meta.get("hand_no") or INFO_PLACEHOLDER)
        self.session_table_var.set(meta.get("table_no") or INFO_PLACEHOLDER)
        self.info_bounty_var.set(meta.get("bounty") or INFO_PLACEHOLDER)

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