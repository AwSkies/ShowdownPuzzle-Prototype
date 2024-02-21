import logging
import constants

from .helpers import format_decision
from showdown.battle import Battle;

logger = logging.getLogger(__name__)

class PuzzleRunner(Battle):
    def __init__(self, commands, *args, **kwargs):
        super(PuzzleRunner, self).__init__(*args, **kwargs)
        self.commands = commands

    def find_best_move(self):
        options = self.get_all_options()[0]

        moves = []
        switches = []
        for option in options:
            if option.startswith(constants.SWITCH_STRING + " "):
                switches.append(option)
            else:
                moves.append(option)

        # TODO: Make choices based on commands
        if self.force_switch or not moves:
            return format_decision(self, switches[0])
        else:
            return format_decision(self, moves[0])
