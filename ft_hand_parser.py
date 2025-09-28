# Updated content of ft_hand_parser.py

# Add your updated code here

class FullTiltHandParser:
    def __init__(self):
        self.hero_name = None
        self.hero_hole_cards = None

    def parse_hand(self, hand_history):
        # Existing parsing logic...
        # New logic to extract hero details
        self.hero_name = self.extract_hero_name(hand_history)
        self.hero_hole_cards = self.extract_hero_hole_cards(hand_history)

    def extract_hero_name(self, hand_history):
        # Logic to extract hero name
        return "Hero Name"

    def extract_hero_hole_cards(self, hand_history):
        # Logic to extract hero hole cards
        return ["Card1", "Card2"]