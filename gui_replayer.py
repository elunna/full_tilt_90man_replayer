import tkinter as tk
from tkinter import filedialog, messagebox
from ft_hand_parser import FullTiltHandParser

class HandReplayerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Full Tilt 90-Man Tournament Replayer")

        # Data
        self.parser = None
        self.hands = []
        self.current_hand_index = None
        self.current_street = None
        self.current_action_index = None

        # GUI elements
        self.build_gui()

    def build_gui(self):
        # File selection
        file_frame = tk.Frame(self.root)
        file_frame.pack(fill='x')
        tk.Button(file_frame, text="Open Hand History", command=self.open_file).pack(side='left')
        self.file_label = tk.Label(file_frame, text="No file loaded")
        self.file_label.pack(side='left', padx=10)

        # Hand selector
        selector_frame = tk.Frame(self.root)
        selector_frame.pack(fill='x')
        tk.Label(selector_frame, text="Select Hand:").pack(side='left')
        self.hand_listbox = tk.Listbox(selector_frame, height=5, exportselection=False)
        self.hand_listbox.pack(side='left', fill='x', expand=True)
        self.hand_listbox.bind('<<ListboxSelect>>', self.on_hand_select)

        # Table display
        table_frame = tk.LabelFrame(self.root, text="Table")
        table_frame.pack(fill='both', padx=10, pady=10)
        self.seat_labels = []
        for seat in range(1, 10):
            f = tk.Frame(table_frame, borderwidth=1, relief="solid")
            f.grid(row=(seat-1)//3, column=(seat-1)%3, padx=5, pady=5, sticky="nsew")
            seat_label = tk.Label(f, text=f"Seat {seat}", font=("Arial", 10, "bold"))
            seat_label.pack()
            player_label = tk.Label(f, text="(empty)", font=("Arial", 10))
            player_label.pack()
            chips_label = tk.Label(f, text="", font=("Arial", 10))
            chips_label.pack()
            self.seat_labels.append( (player_label, chips_label) )

        # Action viewer
        action_frame = tk.LabelFrame(self.root, text="Hand Action")
        action_frame.pack(fill='x', padx=10, pady=5)
        self.street_label = tk.Label(action_frame, text="Street: ")
        self.street_label.pack(anchor='w')
        self.action_label = tk.Label(action_frame, text="Action: ")
        self.action_label.pack(anchor='w')
        nav_frame = tk.Frame(action_frame)
        nav_frame.pack(anchor='w')
        self.prev_button = tk.Button(nav_frame, text="Prev", command=self.prev_action, state='disabled')
        self.prev_button.pack(side='left', padx=2)
        self.next_button = tk.Button(nav_frame, text="Next", command=self.next_action, state='disabled')
        self.next_button.pack(side='left', padx=2)

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
            self.file_label.config(text=f"Loaded: {file_path.split('/')[-1]}")
            self.populate_hand_list()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse file:\n{e}")

    def populate_hand_list(self):
        self.hand_listbox.delete(0, tk.END)
        for i, hand in enumerate(self.hands):
            hand_title = hand['header'][:80]
            self.hand_listbox.insert(tk.END, f"Hand {i+1}: {hand_title}")
        if self.hands:
            self.hand_listbox.selection_set(0)
            self.on_hand_select()

    def on_hand_select(self, event=None):
        sel = self.hand_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.current_hand_index = idx
        hand = self.hands[idx]
        self.display_table(hand)
        self.current_street = 'preflop'
        self.current_action_index = 0
        self.update_action_viewer()
        self.prev_button.config(state='normal')
        self.next_button.config(state='normal')

    def display_table(self, hand):
        # Fill seats 1-9, empty if not present
        seat_map = {p['seat']: p for p in hand['players']}
        for seat in range(1, 10):
            player_label, chips_label = self.seat_labels[seat-1]
            player = seat_map.get(seat)
            if player:
                player_label.config(text=player['name'])
                chips_label.config(text=f"Chips: {player['chips']}")
            else:
                player_label.config(text="(empty)")
                chips_label.config(text="")

    def update_action_viewer(self):
        hand = self.hands[self.current_hand_index]
        # Find current street and action
        streets = ['preflop', 'flop', 'turn', 'river']
        actions = hand['actions'][self.current_street]
        self.street_label.config(text=f"Street: {self.current_street.title()}")
        if actions and 0 <= self.current_action_index < len(actions):
            act = actions[self.current_action_index]
            self.action_label.config(text=f"Action: {act['player']} {act['action']} {act['detail']}")
        else:
            self.action_label.config(text="Action: (no action)")
        # Enable/disable buttons
        self.prev_button.config(state='normal' if self.current_action_index > 0 else 'disabled')
        self.next_button.config(state='normal' if self.current_action_index < len(actions)-1 else 'disabled')

    def next_action(self):
        hand = self.hands[self.current_hand_index]
        actions = hand['actions'][self.current_street]
        if self.current_action_index < len(actions)-1:
            self.current_action_index += 1
            self.update_action_viewer()
        else:
            # Advance street if possible
            streets = ['preflop', 'flop', 'turn', 'river']
            idx = streets.index(self.current_street)
            if idx < len(streets)-1:
                next_street = streets[idx+1]
                if hand['actions'][next_street]:
                    self.current_street = next_street
                    self.current_action_index = 0
                    self.update_action_viewer()

    def prev_action(self):
        if self.current_action_index > 0:
            self.current_action_index -= 1
            self.update_action_viewer()

if __name__ == "__main__":
    root = tk.Tk()
    app = HandReplayerGUI(root)
    root.mainloop()