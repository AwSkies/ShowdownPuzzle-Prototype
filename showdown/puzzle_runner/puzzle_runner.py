import logging
import constants

from .helpers import format_decision
from showdown.battle import Battle;

logger = logging.getLogger(__name__)

class PuzzleRunner(Battle):
    def __init__(self, commands, *args, **kwargs):
        super(PuzzleRunner, self).__init__(*args, **kwargs)
        self.commands = commands
        self.n_commands = 0
        self.repeated_commands: list[dict]
        self.n_repeated_commands = 0
        self.repeat_until_faint = False

    def find_best_move(self):
        if self.commands[self.n_commands]['action'] == constants.REPEAT_UNTIL_FAINT:
            self.repeat_until_faint = True
            self.n_repeated_commands = 0
            self.repeated_commands = self.commands[self.n_commands]['commands']

        if self.force_switch:
            # If this Pokemon just fainted
            if self.user.active.hp <= 0:
                self.repeat_until_faint = False
            return format_decision(self, self.default_switch, switch = True)
        elif self.repeat_until_faint:
            # Evaluate commands from the current index forward, repeating when it gets through to the end
            # Concatenate the entire list with the trimmed list in case it ends with a set switch command and needs to loop back around to the beginning to use the first move
            result = self.evaluate_commands(self.repeated_commands[(self.n_repeated_commands % len(self.repeated_commands)):] + self.repeated_commands)
            self.n_repeated_commands += result[0]
            return result[1]
        else:
            result = self.evaluate_commands(self.commands[self.n_commands:])
            self.n_commands += result[0]
            return result[1]

    def evaluate_commands(self, commands):
        n = 0
        for command in commands:
            n += 1
            if command['action'] == constants.MOVE:
                return n, format_decision(self, command['move'], **command['modifiers'])
            elif command['action'] == constants.SWITCH:
                return n, format_decision(self, command['pokemon'], switch = True)
            elif command['action'] == constants.SET_SWITCH:
                self.default_switch = command['pokemon']

