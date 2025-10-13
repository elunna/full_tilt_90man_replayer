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
        self.root.bind("<Escape>", self._on_escape)  # ESC to immediately exit

        self.drill = OpeningRangeDrill(questions=questions)
        self.current = None
        self.answered = False
        # Feedback from the PREVIOUS hand:
        # {"correct": bool, "recommended": "raise"|"fold", "position": str, "hand": str}
        self._last_feedback = None

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

        # Persistent card frame to avoid layout shifting between questions
        self.card_frame = tk.Frame(hand_frame)
        self.card_frame.pack()

        # Controls (no Next, no End — ESC or window close to exit)
        controls = tk.Frame(outer, pady=12)
        controls.pack()
        self.raise_btn = tk.Button(controls, text="Raise", width=12, command=self._on_raise)
        self.raise_btn.grid(row=0, column=0, padx=6)
        self.fold_btn = tk.Button(controls, text="Fold", width=12, command=self._on_fold)
        self.fold_btn.grid(row=0, column=1, padx=6)

        # Feedback (for the PREVIOUS hand) BELOW the option buttons
        self.feedback_var = tk.StringVar(value="")
        self.feedback_label = tk.Label(outer, textvariable=self.feedback_var, font=("Segoe UI", 24))
        self.feedback_label.pack(pady=(6, 0))
        self.recommended_var = tk.StringVar(value="")
        self.recommended_label = tk.Label(outer, textvariable=self.recommended_var, font=("Segoe UI", 14))
        self.recommended_label.pack(pady=(4, 0))

    def _fit_to_contents(self):
        """Ensure the window is sized to fit all widgets so nothing is clipped."""
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

        def color_for(card):
            return "#CC0000" if card[1] in RED_SUITS else "#000000"

        # Clear and render cards into the persistent frame
        for w in self.card_frame.winfo_children():
            w.destroy()

        l1 = tk.Label(self.card_frame, text=txt1, font=("Segoe UI", 40), fg=color_for(c1))
        l2 = tk.Label(self.card_frame, text="  ", font=("Segoe UI", 40))
        l3 = tk.Label(self.card_frame, text=txt2, font=("Segoe UI", 40), fg=color_for(c2))
        l1.pack(side="left")
        l2.pack(side="left")
        l3.pack(side="left")
        self._card_labels = [l1, l2, l3]

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