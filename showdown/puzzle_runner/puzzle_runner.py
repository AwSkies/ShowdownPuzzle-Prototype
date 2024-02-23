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
        self.default_switch: str

    def find_best_move(self):
        # Setting lead pokemon
        if self.n_commands == 0 and self.commands[0]['action'] == constants.SET_SWITCH:
            self.default_switch = self.commands[0]['pokemon']
        
        # Check if we are being forced to switch
        if self.force_switch or all(option.startswith(constants.SWITCH_STRING) for option in self.get_all_options()[0]):
            # If this Pokemon just fainted
            if self.user.active.hp <= 0:
                self.repeat_until_faint = False
            return format_decision(self, self.default_switch, switch = True)
        elif self.repeat_until_faint:
            return self.evaluate_repeated_commands()
        else:
            return self.evaluate_normal_commands()
        
    def evaluate_normal_commands(self):
        result = self.evaluate_commands(self.commands[self.n_commands:])
        self.n_commands += result[0]
        return result[1]
    
    def evaluate_repeated_commands(self):
        # Evaluate commands from the current index forward, repeating when it gets through to the end
        # Concatenate the entire list with the trimmed list in case it ends with a set switch command and needs to loop back around to the beginning to use the first move
        result = self.evaluate_commands(self.repeated_commands[(self.n_repeated_commands % len(self.repeated_commands)):] + self.repeated_commands)
        self.n_repeated_commands += result[0]
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
            elif command['action'] == constants.REPEAT_UNTIL_FAINT:
                self.repeat_until_faint = True
                self.n_repeated_commands = 0
                self.repeated_commands = command['commands']
                return n, self.evaluate_repeated_commands()