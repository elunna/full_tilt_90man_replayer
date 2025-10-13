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


class OpeningRangeDrillApp:
    """
    Standalone window that runs a 20-question opening-range Raise/Fold drill.
    Positions are random. No timer. Summary/grade at the end.

    Run with: python gui_opening_range_drill.py
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
        self.card_image_cache = {}
        self.card_back_key = None

        self.drill = OpeningRangeDrill(questions=questions)
        self.current = None
        self.answered = False
        # Feedback from the PREVIOUS hand:
        # {"correct": bool, "recommended": "raise"|"fold", "position": str, "hand": str}
        self._last_feedback = None

        self._build_ui()
        self._start()
        self._fit_to_contents()  # Lock window size once after first render

    # ====== Card image loading/rendering (borrowed pattern from gui_replayer.py) ======
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

        outer = tk.Frame(self.root, padx=12, pady=12)
        outer.pack(fill="both", expand=True)

        # Header: progress + position
        header = tk.Frame(outer)
        header.pack(fill="x")
        self.progress_var = tk.StringVar(value="Q 0/20")
        self.pos_var = tk.StringVar(value="Position: —")
        tk.Label(header, textvariable=self.progress_var, font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(header, text="   ").pack(side="left")
        tk.Label(header, textvariable=self.pos_var, font=("Segoe UI", 12)).pack(side="left")

        # Hand area
        hand_frame = tk.Frame(outer, pady=24)
        hand_frame.pack(fill="both", expand=True)

        # Persistent card frame to avoid layout shifting between questions
        self.card_frame = tk.Frame(hand_frame)
        self.card_frame.pack()

        # Controls (no Next, no End — ESC or window close to exit)
        controls = tk.Frame(outer, pady=12)
        controls.pack()
        self.raise_btn = tk.Button(controls, text="Raise", width=12, command=self._on_raise)
        self.raise_btn.grid(row=0, column=0, padx=10)
        self.fold_btn = tk.Button(controls, text="Fold", width=12, command=self._on_fold)
        self.fold_btn.grid(row=0, column=1, padx=10)

        # Feedback (for the PREVIOUS hand) BELOW the option buttons
        self.feedback_var = tk.StringVar(value="")
        self.feedback_label = tk.Label(outer, textvariable=self.feedback_var, font=("Segoe UI", 24))
        self.feedback_label.pack(pady=(6, 0))
        self.recommended_var = tk.StringVar(value="")
        self.recommended_label = tk.Label(outer, textvariable=self.recommended_var, font=("Segoe UI", 14))
        self.recommended_label.pack(pady=(4, 0))

    def _fit_to_contents(self):
        """
        Lock the window size ONCE to ~75% larger than required content.
        Subsequent content changes will NOT alter the window size.
        """
        if self._size_locked:
            return
        self.root.update_idletasks()
        req_w = self.root.winfo_reqwidth()
        req_h = self.root.winfo_reqheight()
        # Scale by ~75% and apply once
        w = max(640, int(req_w * 1.75))
        h = max(480, int(req_h * 1.75))
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
        self.pos_var.set(f"Position: {q['position']}")

        c1, c2 = q["hero_cards"]

        # Clear and render cards into the persistent frame
        for w in self.card_frame.winfo_children():
            w.destroy()

        # Try image-based rendering first
        p1 = self.get_card_image_sized(c1, self.CARD_W, self.CARD_H)
        p2 = self.get_card_image_sized(c2, self.CARD_W, self.CARD_H)

        if p1 and p2:
            l1 = tk.Label(self.card_frame, image=p1)
            l2 = tk.Label(self.card_frame, text="  ", font=("Segoe UI", 40))
            l3 = tk.Label(self.card_frame, image=p2)
            l1.pack(side="left")
            l2.pack(side="left")
            l3.pack(side="left")
            # Keep references so images don't get garbage-collected
            self._card_imgs = [p1, p2]
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

        # Show feedback from the PREVIOUS hand (if any) below the buttons
        if self._last_feedback is None:
            self.feedback_var.set("")
            self.recommended_var.set("")
        else:
            # First line: "Last hand: {positive or negative feedback}"
            self.feedback_var.set("Last hand: " + ("correct" if self._last_feedback["correct"] else "X"))
            # Second line: "Recommend {action} from {position} with {hand}"
            self.recommended_var.set(
                f"Recommend {self._last_feedback['recommended'].upper()} "
                f"from {self._last_feedback['position']} with {self._last_feedback['hand']}"
            )

        # Enable actions each question
        self.raise_btn.config(state="normal")
        self.fold_btn.config(state="normal")

        # Do NOT change geometry after the initial lock
        if not self._size_locked:
            self._fit_to_contents()

    def _after_answer(self, correct: bool, q_snapshot):
        # Store feedback for display under the NEXT hand
        self._last_feedback = {
            "correct": correct,
            "recommended": q_snapshot["answer"],
            "position": q_snapshot["position"],
            "hand": q_snapshot["key"],
        }

        # Immediately move to the next question (no pause)
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
    app = OpeningRangeDrillApp(questions=20)
    app.run()