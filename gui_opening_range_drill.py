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

    def __init__(self, master: Optional[tk.Tk] = None, questions: int = 20):
        self._own_root = master is None
        self.root = master or tk.Tk()
        self.root.title("Opening Range Drill (Raise/Fold)")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.drill = OpeningRangeDrill(questions=questions)
        self.current = None
        self.answered = False

        self._build_ui()
        self._start()
        self._fit_to_contents()

    def _build_ui(self):
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

        # persistent card frame to avoid layout shifting between questions
        # and allow Tk to compute the required size correctly.
        self.card_frame = tk.Frame(hand_frame)
        self.card_frame.pack()

        # Feedback
        self.feedback_var = tk.StringVar(value="")
        self.feedback_label = tk.Label(outer, textvariable=self.feedback_var, font=("Segoe UI", 12))
        self.feedback_label.pack()

        # Controls
        controls = tk.Frame(outer, pady=8)
        controls.pack()

        self.raise_btn = tk.Button(controls, text="Raise", width=12, command=self._on_raise)
        self.raise_btn.grid(row=0, column=0, padx=6)

        self.fold_btn = tk.Button(controls, text="Fold", width=12, command=self._on_fold)
        self.fold_btn.grid(row=0, column=1, padx=6)

        self.next_btn = tk.Button(controls, text="Next", width=12, command=self._on_next, state="disabled")
        self.next_btn.grid(row=0, column=2, padx=6)

        self.end_btn = tk.Button(controls, text="End Drill", width=12, command=self._on_end)
        self.end_btn.grid(row=0, column=3, padx=6)

        # Footer: reveal key/recommendation after answering
        self.key_var = tk.StringVar(value="")
        self.key_label = tk.Label(outer, textvariable=self.key_var, font=("Segoe UI", 10), fg="#666666")
        self.key_label.pack(pady=(8, 0))

    def _fit_to_contents(self):
        """
        Ensure the window is sized to fit all widgets so nothing is clipped,
        and prevent shrinking below the content size.
        """
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())

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
        txt1 = render_card_text(c1)
        txt2 = render_card_text(c2)

        # Color red for hearts/diamonds
        def color_for(card):
            return "#CC0000" if card[1] in RED_SUITS else "#000000"

        # Clear previous card labels and render into the persistent frame
        for w in self.card_frame.winfo_children():
            w.destroy()

        l1 = tk.Label(self.card_frame, text=txt1, font=("Segoe UI", 40), fg=color_for(c1))
        l2 = tk.Label(self.card_frame, text="  ", font=("Segoe UI", 40))
        l3 = tk.Label(self.card_frame, text=txt2, font=("Segoe UI", 40), fg=color_for(c2))
        l1.pack(side="left")
        l2.pack(side="left")
        l3.pack(side="left")
        # track current labels if needed later
        self._card_labels = [l1, l2, l3]

        self.feedback_var.set("")
        self.key_var.set("")
        self.raise_btn.config(state="normal")
        self.fold_btn.config(state="normal")
        self.next_btn.config(state="disabled")
        # Recalculate min size in case fonts or platform metrics differ
        self._fit_to_contents()

    def _after_answer(self, correct: bool, q_snapshot):
        self.answered = True
        self.raise_btn.config(state="disabled")
        self.fold_btn.config(state="disabled")
        self.next_btn.config(state="normal")

        msg = "Correct!" if correct else "Incorrect"
        color = "#127A0A" if correct else "#CC0000"
        self.feedback_var.set(msg)
        self.feedback_label.config(fg=color)
        # Reveal the normalized key and ground-truth
        self.key_var.set(f"Hand key: {q_snapshot['key']} • Recommended: {q_snapshot['answer'].upper()}")

    def _on_raise(self):
        if self.answered:
            return
        correct, snap = self.drill.submit("raise")
        self._after_answer(correct, snap)

    def _on_fold(self):
        if self.answered:
            return
        correct, snap = self.drill.submit("fold")
        self._after_answer(correct, snap)

    def _on_next(self):
        q = self.drill.next_question()
        if q is None:
            self._show_summary()
            return
        self._render_question(q)

    def _on_end(self):
        self._show_summary()

    def _show_summary(self):
        summary = self.drill.summary()
        msg = (
            f"Opening Range Drill complete!\n\n"
            f"Score: {summary['correct']} / {summary['total']}  ({summary['percent']}%)\n"
            f"Grade: {summary['grade']}\n"
        )
        messagebox.showinfo("Drill Summary", msg, parent=self.root)

    def _on_close(self):
        self.root.destroy()

    def run(self):
        if self._own_root:
            self.root.mainloop()


if __name__ == "__main__":
    app = OpeningRangeDrillApp(questions=20)
    app.run()