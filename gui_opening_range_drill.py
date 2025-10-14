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

        # Fixed-size window state (lock size once after first render)
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
        self._fit_to_contents()  # Lock window size once after first render

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

        # Header: progress on the left (no position text)
        header = tk.Frame(outer)
        header.pack(fill="x")
        self.progress_var = tk.StringVar(value="Q 0/20")
        tk.Label(header, textvariable=self.progress_var, font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(header, text="").pack(side="left", expand=True)

        # Hand area container
        hand_frame = tk.Frame(outer, pady=24)
        hand_frame.pack(fill="both", expand=True)

        # Centered grid with two columns: Position (col 0) and Cards (col 1)
        self.hand_inner = tk.Frame(hand_frame)
        # pack without fill keeps it centered; expand keeps it in the middle vertically
        self.hand_inner.pack(expand=True)

        subtle_fg = "#666"

        # Row 0: Titles (centered over their respective content columns)
        self.pos_title = tk.Label(self.hand_inner, text="Position", font=("Segoe UI", 10), fg=subtle_fg)
        self.pos_title.grid(row=0, column=0, sticky="n", pady=(0, 4))

        # Row 1: Content
        self.pos_big_var = tk.StringVar(value="")
        self.pos_big_label = tk.Label(self.hand_inner, textvariable=self.pos_big_var, font=("Segoe UI", 36, "bold"))
        self.pos_big_label.grid(row=1, column=0, sticky="n")

        self.card_frame = tk.Frame(self.hand_inner)
        self.card_frame.grid(row=1, column=1, sticky="n", padx=(16, 0))

        # Do not let columns stretch; size to content so the whole block stays centered
        self.hand_inner.grid_columnconfigure(0, weight=0)
        self.hand_inner.grid_columnconfigure(1, weight=0)

        # Controls (no Next, no End — ESC or window close to exit)
        controls = tk.Frame(outer, pady=12)
        controls.pack()
        self.raise_btn = tk.Button(controls, text="Raise", width=12, command=self._on_raise)
        self.raise_btn.grid(row=0, column=0, padx=10)
        self.fold_btn = tk.Button(controls, text="Fold", width=12, command=self._on_fold)
        self.fold_btn.grid(row=0, column=1, padx=10)

        # Note: Removed per-hand textual feedback

    def _fit_to_contents(self):
        """
        Lock the window size ONCE, with a narrower width multiplier to avoid excessive width.
        Subsequent content changes will NOT alter the window size.
        """
        if self._size_locked:
            return
        self.root.update_idletasks()
        req_w = self.root.winfo_reqwidth()
        req_h = self.root.winfo_reqheight()
        # Balanced size
        w = max(560, int(req_w * 1.35))
        h = max(480, int(req_h * 1.50))
        self._fixed_w, self._fixed_h = w, h
        try:
            self.root.geometry(f"{w}x{h}")
        except Exception:
            pass
        try:
            self.root.minsize(w, h)
            self.root.maxsize(w, h)
        except Exception:
            pass
        self.root.resizable(False, False)
        self._size_locked = True

    def _start(self):
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

    def _after_answer(self, correct: bool, q_snapshot):
        # Visual flash on border; no textual feedback and no pause
        self._flash_border("#127A0A" if correct else "#CC0000", ms=200)

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
        correct, snap = self.drill.submit("raise")
        self._after_answer(correct, snap)

    def _on_fold(self):
        if self.answered:
            return
        self.answered = True
        correct, snap = self.drill.submit("fold")
        self._after_answer(correct, snap)

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