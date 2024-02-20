import logging

from puzzles.load_puzzle import load_puzzle
from showdown.battle import Battle;

logger = logging.getLogger(__name__)

class BattleBot(Battle):
    def __init__(self, puzzle_name, *args, **kwargs):
        super(BattleBot, self).__init__(*args, **kwargs)
        puzzle_text = load_puzzle(puzzle_name)
        logger.debug("Parsing puzzle")
        # Parse puzzle

    def find_best_move(self):
        logger.debug("Finding best move lol")
        return super().find_best_move()