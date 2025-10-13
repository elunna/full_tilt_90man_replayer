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

        # Auto-advance state must be initialized before any rendering occurs
        self._advance_after_id: Optional[str] = None
        self._raise_defaults = None
        self._fold_defaults = None

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

        # Persistent card frame to avoid layout shifting between questions
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

        # Capture default button styles for later reset (themes may ignore)
        self._raise_defaults = {
            "bg": self.raise_btn.cget("bg"),
            "fg": self.raise_btn.cget("fg"),
            "activebackground": self.raise_btn.cget("activebackground") if "activebackground" in self.raise_btn.keys() else None,
        }
        self._fold_defaults = {
            "bg": self.fold_btn.cget("bg"),
            "fg": self.fold_btn.cget("fg"),
            "activebackground": self.fold_btn.cget("activebackground") if "activebackground" in self.fold_btn.keys() else None,
        }

        # End Drill button (no Next button; auto-advance is used)
        self.end_btn = tk.Button(controls, text="End Drill", width=12, command=self._on_end)
        self.end_btn.grid(row=0, column=2, padx=6)

        # Footer: reveal key/recommendation after answering
        self.key_var = tk.StringVar(value="")
        self.key_label = tk.Label(outer, textvariable=self.key_var, font=("Segoe UI", 10), fg="#666666")
        self.key_label.pack(pady=(8, 0))

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

        self.feedback_var.set("")
        self.key_var.set("")
        self.raise_btn.config(state="normal")
        self.fold_btn.config(state="normal")
        self._reset_button_styles()
        self._cancel_pending_advance()
        self._fit_to_contents()

    def _color_button(self, btn: tk.Button, bg: str, fg: str = "white"):
        """Best-effort button color change (some themes may ignore)."""
        try:
            btn.config(bg=bg, fg=fg)
            if "activebackground" in btn.keys():
                btn.config(activebackground=bg)
        except Exception:
            pass

    def _reset_button_styles(self):
        if self._raise_defaults:
            try:
                self.raise_btn.config(bg=self._raise_defaults["bg"], fg=self._raise_defaults["fg"])
                if self._raise_defaults.get("activebackground") and "activebackground" in self.raise_btn.keys():
                    self.raise_btn.config(activebackground=self._raise_defaults["activebackground"])
            except Exception:
                pass
        if self._fold_defaults:
            try:
                self.fold_btn.config(bg=self._fold_defaults["bg"], fg=self._fold_defaults["fg"])
                if self._fold_defaults.get("activebackground") and "activebackground" in self.fold_btn.keys():
                    self.fold_btn.config(activebackground=self._fold_defaults["activebackground"])
            except Exception:
                pass

    def _cancel_pending_advance(self):
        if self._advance_after_id is not None:
            try:
                self.root.after_cancel(self._advance_after_id)
            except Exception:
                pass
            self._advance_after_id = None

    def _advance_next(self):
        self._advance_after_id = None
        q = self.drill.next_question()
        if q is None:
            self._show_summary()
            return
        self._render_question(q)

    def _after_answer(self, correct: bool, q_snapshot, clicked_btn: Optional[tk.Button] = None):
        self.answered = True
        self.raise_btn.config(state="disabled")
        self.fold_btn.config(state="disabled")

        # If the caller didn't specify which button was clicked, fall back to the recommended action's button.
        if clicked_btn is None:
            clicked_btn = self.raise_btn if q_snapshot.get("answer") == "raise" else self.fold_btn

        # Visual feedback only: highlight the clicked action and pause
        if correct:
            self._color_button(clicked_btn, "#127A0A", "white")  # green
            delay = 1000
        else:
            self._color_button(clicked_btn, "#CC0000", "white")  # red
            delay = 2000

        # Keep text feedback minimal; reveal key and recommendation for learning
        self.feedback_var.set("")
        self.feedback_label.config(fg="#000000")
        self.key_var.set(f"Hand key: {q_snapshot['key']} • Recommended: {q_snapshot['answer'].upper()}")

        # Schedule auto-advance
        self._cancel_pending_advance()
        self._advance_after_id = self.root.after(delay, self._advance_next)

    def _on_raise(self):
        if self.answered:
            return
        correct, snap = self.drill.submit("raise")
        self._after_answer(correct, snap, self.raise_btn)

    def _on_fold(self):
        if self.answered:
            return
        correct, snap = self.drill.submit("fold")
        self._after_answer(correct, snap, self.fold_btn)

    def _on_end(self):
        self._cancel_pending_advance()
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
        self._cancel_pending_advance()
        self.root.destroy()

    def run(self):
        if self._own_root:
            self.root.mainloop()


if __name__ == "__main__":
    app = OpeningRangeDrillApp(questions=20)
    app.run()