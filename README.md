# Full Tilt 90-Man Replayer

This repository contains tools for parsing and replaying Full Tilt Poker 90-man Sit & Go tournament hand histories, with special support for knockout (KO) tournaments.

## Features

- Parse Full Tilt hand histories into structured data
- Easily extendable for visualization or analysis
- Focus on KO/bounty tournament mechanics

## Getting Started

1. Place your Full Tilt Poker hand history text files in the project directory.
2. Run the parser to extract structured data for each hand.

## Example

Run the parser script:

```bash
python ft_hand_parser.py FT20110126\ \$3\ +\ \$0.30\ KO\ Sit\ \&\ Go\ \(214713178\),\ No\ Limit\ Hold'em_1.txt
```

## License

MIT License