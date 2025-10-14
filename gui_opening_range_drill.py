import os
import tkinter as tk
from tkinter import messagebox
from typing import Optional

try:
    from PIL import Image, ImageTk  # noqa: F401
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageTk = None
    PIL_AVAILABLE = False

from drill_mode import OpeningRangeDrill

SUIT_SYM = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
RED_SUITS = {"h", "d"}


def render_card_text(card: str) -> str:
    """Turn 'As' into 'A♠'."""
    return f"{card[0]}{SUIT_SYM.get(card[1], card[1])}"


class ModeSelectApp:
    """
    Simple launcher to select which drill mode to run.
    For now, only Opening Range (Raise/Fold) is available; others are placeholders.
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Poker Drills - Select Mode")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", lambda e: self._on_close())

        self._build_ui()
        self._drill_app = None

    def _build_ui(self):
        outer = tk.Frame(self.root, padx=16, pady=16)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer, text="Select a Drill Mode", font=("Segoe UI", 16, "bold")
        ).pack(pady=(0, 12))

        grid = tk.Frame(outer)
        grid.pack()

        # Opening Range (implemented)
        tk.Button(
            grid, text="Opening Range (Raise/Fold)", width=28, command=self._start_opening_range
        ).grid(row=0, column=0, padx=8, pady=6)

        # Future modes: disabled for now
        tk.Button(
            grid, text="Facing Raises (Coming soon)", width=28, state="disabled"
        ).grid(row=1, column=0, padx=8, pady=6)

        tk.Button(
            grid, text="Defend Big Blind (Coming soon)", width=28, state="disabled"
        ).grid(row=2, column=0, padx=8, pady=6)

        tk.Button(
            grid, text="Isolate Limpers (Coming soon)", width=28, state="disabled"
        ).grid(row=3, column=0, padx=8, pady=6)

        tk.Button(
            grid, text="Blind vs Blind (Coming soon)", width=28, state="disabled"
        ).grid(row=4, column=0, padx=8, pady=6)

        # Size this launcher modestly
        self.root.update_idletasks()
        w = max(420, self.root.winfo_reqwidth() + 20)
        h = max(240, self.root.winfo_reqheight() + 20)
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(w, h)
        self.root.resizable(False, False)

    def _clear_root_children(self):
        for w in self.root.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

    def _start_opening_range(self):
        # Unbind launcher Escape so the drill can own it.
        try:
            self.root.unbind("<Escape>")
        except Exception:
            pass
        # Clear launcher UI and hand over to the drill app in the same root
        self._clear_root_children()
        self._drill_app = OpeningRangeDrillApp(master=self.root, questions=20)
        # Do not call run(); drill app will not own mainloop since we passed a master.

    def _on_close(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


class OpeningRangeDrillApp:
    """
    Standalone window that runs a 20-question opening-range Raise/Fold drill.
    Positions are random. No timer. Summary/grade at the end.
    """

    CARD_W = 150
    CARD_H = 210

    def __init__(self, master: Optional[tk.Tk] = None, questions: int = 20):
        self._own_root = master is None
        self.root = master or tk.Tk()
        self.root.title("Opening Range Drill (Raise/Fold)")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", self._on_escape)  # ESC to immediately exit

        # Initial sizing state (set once, but allow user resizing afterward)
        self._size_locked = False
        self._fixed_w = None
        self._fixed_h = None

        # Card image caches (reused from replayer design)
        self.card_image_paths = {}
        our_dir = os.path.dirname(__file__)
        self.png_dir = os.path.join(our_dir, "png")
        self.card_image_cache = {}
        self.card_back_key = None

        self.drill = OpeningRangeDrill(questions=questions)
        self.current = None
        self.answered = False

        # Build UI and start
        self._build_ui()
        self._start()
        self._fit_to_contents()  # Set an initial size; let user resize as needed

    # ====== Card image loading/rendering (borrowed pattern from gui_replayer.py) ======
    def load_card_images(self):
        """
        Load all PNG images from ./png into a path map for lazy, sized loading.
        Picks back_blue.png as the default card back if present, otherwise the first 'back*.png'.
        """
        self.card_image_paths.clear()
        self.card_image_cache.clear()
        self.card_back_key = None

        if not os.path.isdir(self.png_dir):
            return

        for fname in os.listdir(self.png_dir):
            if not fname.lower().endswith(".png"):
                continue
            key = os.path.splitext(fname)[0].lower()  # e.g., "ah", "back_blue"
            self.card_image_paths[key] = os.path.join(self.png_dir, fname)

        # Choose default back
        if "back_blue" in self.card_image_paths:
            self.card_back_key = "back_blue"
        else:
            for k in self.card_image_paths.keys():
                if k.startswith("back"):
                    self.card_back_key = k
                    break

    def get_card_image_sized(self, code: str, width: int, height: int):
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

    # ====== UI ======
    def _build_ui(self):
        self.load_card_images()

        # Chrome frame we can flash as the "window border"
        self.chrome = tk.Frame(self.root, bg=self.root.cget("bg"), padx=4, pady=4)
        self.chrome.pack(fill="both", expand=True)
        self._chrome_default_bg = self.chrome.cget("bg")

        outer = tk.Frame(self.chrome, padx=12, pady=12)
        outer.pack(fill="both", expand=True)

        # Header: progress on the left
        header = tk.Frame(outer)
        header.pack(fill="x")
        self.progress_var = tk.StringVar(value="Q 0/20")
        tk.Label(header, textvariable=self.progress_var, font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(header, text="").pack(side="left", expand=True)

        # Hand area container
        hand_frame = tk.Frame(outer, pady=16)
        hand_frame.pack(fill="both", expand=True)

        # Right-side running summary panel
        self._build_summary_panel(hand_frame)

        # Left column: holds the centered content and the buttons below it
        left_col = tk.Frame(hand_frame)
        left_col.pack(side="left", fill="both", expand=True)

        # Centered grid with two columns: Position (col 0) and Cards (col 1)
        self.hand_inner = tk.Frame(left_col)
        self.hand_inner.pack(pady=(0, 8))  # small gap above buttons area

        subtle_fg = "#666"

        # Row 0: Title (centered over the position column)
        self.pos_title = tk.Label(self.hand_inner, text="Position", font=("Segoe UI", 10), fg=subtle_fg)
        self.pos_title.grid(row=0, column=0, sticky="n", pady=(0, 4))

        # Row 1: Content (Position + Cards)
        self.pos_big_var = tk.StringVar(value="")
        self.pos_big_label = tk.Label(self.hand_inner, textvariable=self.pos_big_var, font=("Segoe UI", 36, "bold"))
        self.pos_big_label.grid(row=1, column=0, sticky="n")

        self.card_frame = tk.Frame(self.hand_inner)
        self.card_frame.grid(row=1, column=1, sticky="n", padx=(16, 0))

        # Do not let columns stretch; size to content so the whole block stays centered
        self.hand_inner.grid_columnconfigure(0, weight=0)
        self.hand_inner.grid_columnconfigure(1, weight=0)

        # Controls (moved below the content, centered in available space)
        self.buttons_row = tk.Frame(left_col)
        self.buttons_row.pack(pady=(24, 0))

        buttons_inner = tk.Frame(self.buttons_row)
        buttons_inner.pack()

        # Big, bordered, UNIFORM-SIZE action buttons
        # Wrap each button in a black frame to simulate a thick border cross-platform
        uniform_width_chars = 12  # same width for both buttons

        raise_border = tk.Frame(buttons_inner, bg="black")
        raise_border.grid(row=0, column=0, padx=12)
        self.raise_btn = tk.Button(
            raise_border,
            text="Raise",
            font=("Segoe UI", 22, "bold"),
            relief="raised",
            bd=0,
            padx=28,
            pady=16,
            width=uniform_width_chars,
            cursor="hand2",
            command=self._on_raise,
        )
        self.raise_btn.pack(padx=6, pady=6)

        fold_border = tk.Frame(buttons_inner, bg="black")
        fold_border.grid(row=0, column=1, padx=12)
        self.fold_btn = tk.Button(
            fold_border,
            text="Fold",
            font=("Segoe UI", 22, "bold"),
            relief="raised",
            bd=0,
            padx=28,
            pady=16,
            width=uniform_width_chars,  # same width as Raise
            cursor="hand2",
            command=self._on_fold,
        )
        self.fold_btn.pack(padx=6, pady=6)

        # Note: Removed the separate bottom controls row

    def _build_summary_panel(self, parent):
        """Create the running summary panel on the right side."""
        # Let the summary panel expand so the user can reveal all columns by resizing
        self.summary_panel = tk.Frame(parent)
        self.summary_panel.pack(side="right", fill="both", expand=True)

        title = tk.Label(self.summary_panel, text="Summary", font=("Segoe UI", 12, "bold"))
        title.pack(pady=(0, 6))

        # Scrollable list area (expand to consume available width/height)
        self.summary_canvas = tk.Canvas(self.summary_panel, highlightthickness=0)
        self.summary_scroll = tk.Scrollbar(self.summary_panel, orient="vertical", command=self.summary_canvas.yview)
        self.summary_canvas.configure(yscrollcommand=self.summary_scroll.set)

        self.summary_canvas.pack(side="left", fill="both", expand=True)
        self.summary_scroll.pack(side="right", fill="y")

        self.summary_inner = tk.Frame(self.summary_canvas)
        # Keep a handle to the window so we can stretch it with the canvas width
        self.summary_window_id = self.summary_canvas.create_window((0, 0), window=self.summary_inner, anchor="nw")

        # Header row (subtle)
        hdr_fg = "#666"
        header_row = tk.Frame(self.summary_inner)
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        labels = ["#", "Position", "Hand", "Correct", "You"]
        widths = [3, 9, 6, 8, 8]
        for i, (txt, w) in enumerate(zip(labels, widths)):
            tk.Label(header_row, text=txt, font=("Segoe UI", 9, "bold"), fg=hdr_fg, width=w, anchor="w").grid(
                row=0, column=i, padx=(0 if i == 0 else 8, 0), sticky="w"
            )

        self._summary_next_row = 1  # next grid row index after header

        # Keep scrollregion and inner width synced with canvas size
        def on_inner_configure(_event=None):
            self.summary_canvas.configure(scrollregion=self.summary_canvas.bbox("all"))
            # Also ensure the inner frame matches the current canvas width (prevents horizontal clipping)
            try:
                self.summary_canvas.itemconfigure(self.summary_window_id, width=self.summary_canvas.winfo_width())
            except Exception:
                pass

        def on_canvas_configure(event):
            try:
                self.summary_canvas.itemconfigure(self.summary_window_id, width=event.width)
            except Exception:
                pass

        self.summary_inner.bind("<Configure>", on_inner_configure)
        self.summary_canvas.bind("<Configure>", on_canvas_configure)

    def _add_summary_entry(self, idx: int, position: str, hand: str, correct_action: str, your_action: str, correct: bool):
        """Append a colored row to the summary list."""
        row_bg = "#dff6dd" if correct else "#fde7e9"  # greenish / reddish subtle
        row_fg = "#0f6d31" if correct else "#a4262c"

        row = tk.Frame(self.summary_inner, bg=row_bg)
        row.grid(row=self._summary_next_row, column=0, sticky="ew", pady=2)
        self._summary_next_row += 1

        # columns: #, position, hand, correct, you
        values = [f"{idx:02d}", position, hand, correct_action.upper(), your_action.upper()]
        widths = [3, 9, 6, 8, 8]

        for i, (val, w) in enumerate(zip(values, widths)):
            lbl = tk.Label(
                row,
                text=val,
                font=("Segoe UI", 10),
                width=w,
                anchor="w",
                bg=row_bg,
                fg=row_fg if i in (0, 3, 4) else "#000",
            )
            lbl.grid(row=0, column=i, padx=(0 if i == 0 else 8, 0), sticky="w")

    def _reset_summary_panel(self):
        """Clear all summary rows (keep header)."""
        for child in list(self.summary_inner.children.values()):
            # Keep the first child (header_row) which we placed at grid row 0
            try:
                info = child.grid_info()
                if info and int(info.get("row", 1)) > 0:
                    child.destroy()
            except Exception:
                pass
        self._summary_next_row = 1

    def _fit_to_contents(self):
        """
        Set an initial window size based on content, but allow the user to resize freely.
        Also set a minimum window size so the cards and summary don't get clipped to unusable sizes.
        """
        if self._size_locked:
            return
        self.root.update_idletasks()

        # Good starting size that accommodates the summary panel
        req_w = self.root.winfo_reqwidth()
        req_h = self.root.winfo_reqheight()
        w = max(900, int(req_w * 1.30))
        h = max(600, int(req_h * 1.40))

        try:
            self.root.geometry(f"{w}x{h}")
        except Exception:
            pass

        # Compute a reasonable minimum size:
        # - Ensure both cards fully visible + a small gap and position column
        # - Ensure a practical minimum width for the summary panel
        cards_min_w = self.CARD_W * 2 + 16
        pos_min_w = 160
        summary_min_w = 320
        margin = 120  # padding, chrome, controls, internal gaps

        min_w = cards_min_w + pos_min_w + summary_min_w + margin
        min_h = self.CARD_H + 240  # header + labels + buttons + margins

        try:
            self.root.minsize(min_w, min_h)
        except Exception:
            pass

        # Allow free resizing now
        self.root.resizable(True, True)
        self._size_locked = True

    def _start(self):
        self._reset_summary_panel()
        q = self.drill.start()
        self._render_question(q)

    def _render_question(self, q):
        self.current = q
        self.answered = False
        total = self.drill.questions
        done = self.drill.result.total  # answered so far
        self.progress_var.set(f"Q {done + 1}/{total}")

        # Update the big position label text
        self.pos_big_var.set(q["position"])

        # Render cards
        c1, c2 = q["hero_cards"]
        for w in self.card_frame.winfo_children():
            w.destroy()

        p1 = self.get_card_image_sized(c1, self.CARD_W, self.CARD_H)
        p2 = self.get_card_image_sized(c2, self.CARD_W, self.CARD_H)

        if p1 and p2:
            l1 = tk.Label(self.card_frame, image=p1)
            l2 = tk.Label(self.card_frame, text="  ", font=("Segoe UI", 40))
            l3 = tk.Label(self.card_frame, image=p2)
            l1.pack(side="left")
            l2.pack(side="left")
            l3.pack(side="left")
            self._card_imgs = [p1, p2]  # prevent GC
            self._card_labels = [l1, l2, l3]
        else:
            # Fallback to text rendering if images not available
            def color_for(card):
                return "#CC0000" if card[1] in RED_SUITS else "#000000"
            txt1 = render_card_text(c1)
            txt2 = render_card_text(c2)
            l1 = tk.Label(self.card_frame, text=txt1, font=("Segoe UI", 40), fg=color_for(c1))
            l2 = tk.Label(self.card_frame, text="  ", font=("Segoe UI", 40))
            l3 = tk.Label(self.card_frame, text=txt2, font=("Segoe UI", 40), fg=color_for(c2))
            l1.pack(side="left")
            l2.pack(side="left")
            l3.pack(side="left")
            self._card_labels = [l1, l2, l3]
            self._card_imgs = []

        # Enable actions each question
        self.raise_btn.config(state="normal")
        self.fold_btn.config(state="normal")

        if not self._size_locked:
            self._fit_to_contents()

    def _flash_border(self, color: str, ms: int = 200):
        """Flash the chrome frame as visual feedback without pausing progression."""
        try:
            self.chrome.config(bg=color)
            self.root.after(ms, lambda: self.chrome.config(bg=self._chrome_default_bg))
        except Exception:
            pass

    def _after_answer(self, correct: bool, q_snapshot, your_action: str):
        # Visual flash on border; no textual feedback and no pause
        self._flash_border("#127A0A" if correct else "#CC0000", ms=200)

        # Append to running summary
        idx = self.drill.result.total  # after submit, this is the answered count (1-based)
        self._add_summary_entry(
            idx=idx,
            position=q_snapshot["position"],
            hand=q_snapshot["key"],
            correct_action=q_snapshot["answer"],
            your_action=your_action,
            correct=correct,
        )

        # Immediately move to the next question
        q = self.drill.next_question()
        if q is None:
            self._show_summary()
            return
        self._render_question(q)

    def _on_raise(self):
        if self.answered:
            return
        self.answered = True
        your_action = "raise"
        correct, snap = self.drill.submit(your_action)
        self._after_answer(correct, snap, your_action)

    def _on_fold(self):
        if self.answered:
            return
        self.answered = True
        your_action = "fold"
        correct, snap = self.drill.submit(your_action)
        self._after_answer(correct, snap, your_action)

    def _show_summary(self):
        summary = self.drill.summary()
        msg = (
            f"Opening Range Drill complete!\n\n"
            f"Score: {summary['correct']} / {summary['total']}  ({summary['percent']}%)\n"
            f"Grade: {summary['grade']}\n"
        )
        messagebox.showinfo("Drill Summary", msg, parent=self.root)
        # Exit immediately after showing the summary
        self._on_close()

    def _on_escape(self, event=None):
        self._on_close()

    def _on_close(self):
        self.root.destroy()

    def run(self):
        if self._own_root:
            self.root.mainloop()


if __name__ == "__main__":
    # Start with a mode selector so future modes can plug in easily.
    launcher = ModeSelectApp()
    launcher.run()