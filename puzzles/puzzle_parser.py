import constants
import logging

from data import all_move_json, pokedex

logger = logging.getLogger(__name__)

def format_puzzle_error(message: str, location: tuple[int, int], lines: list[str]):
    return f"Error in puzzle file: line {location[0]}, column {location[1]}.\n" + \
        f"{lines[location[0] - 1]}\n" + \
        f"{' ' * (location[1] - 1)}^\n" + message

class PuzzleSyntaxError(SyntaxError):
    def __init__(self, message, location: tuple[int, int], lines: list[str], *args: object) -> None:
        super().__init__(format_puzzle_error(message, location, lines), *args)

class PuzzleError(ValueError):
    def __init__(self, message, location: tuple[int, int], lines: list[str], *args: object) -> None:
        super().__init__(format_puzzle_error(message, location, lines), *args)

class PuzzleParser:
    def __init__(self, puzzle_text: str):
        self.lines = puzzle_text.splitlines()

        logger.debug("Parsing puzzle file...")
        self.parse_puzzle_text(puzzle_text)

        logger.debug("Parsing puzzle tokens...")
        self.commands = self.parse_tokens()

        logger.debug("Validating commands...")
        self.validate_commands(self.commands)

    def parse_puzzle_text(self, puzzle_text: str):
        tokens = [('', (0,0))]
        ln = 1
        col = 1
        i = 0
        for char in puzzle_text:
            if char in constants.TOKENS:
                if tokens[i][0] == '':
                    tokens[i] = (char, (ln,col))
                    i += 1
                else:
                    tokens.append((char, (ln,col)))
                    i += 2
                tokens.append(('', (ln,col + 1)))
            elif tokens[i][0] == '':
                tokens[i] = (char, (ln,col))
            else:
                tokens[i] = (tokens[i][0] + char, tokens[i][1])
            
            if char == '\n':
                ln += 1
                col = 1
            else:
                col += 1
        
        # Strip tokens of newlines and spaces
        tokens = [(t[0].strip(), t[1]) for t in tokens]
        # Remove whitespace tokens that have been stripped
        token_text = [t[0] for t in tokens]
        while '' in token_text:
            tokens.pop(token_text.index(''))
            token_text = [t[0] for t in tokens]

        token_text = [t[0].lower() for t in tokens]
        token_locations = [t[1] for t in tokens]

        self.tokens = token_text
        self.locations = token_locations

    def parse_tokens(self, i = 0, repeat_until_faint = False):
        # Remove comments
        while constants.COMMENT_TOKEN in self.tokens:
            index = self.tokens.index(constants.COMMENT_TOKEN)
            self.tokens.pop(index)
            if self.tokens[index] not in constants.TOKENS:
                self.tokens.pop(index)

        # Remove spaces
        for j in range(len(self.tokens)):
            self.tokens[j] = self.tokens[j].replace(' ', '')
            self.tokens[j] = self.tokens[j].replace('-', '')
        
        commands = []
        try:
            while i < len(self.tokens):
                token = self.tokens[i]
                if token == '+':
                    next = self.tokens[i + 1]
                    modifiers = {
                        'mega': False,
                        'ultra_burst': False,
                        'dynamax': False,
                        'tera': False,
                        'z': False
                    }

                    # If the next token looks like a pokemon name and not another token
                    if next not in constants.MODIFIER_TOKENS:
                        move = next
                        i += 2
                    else:
                        if next == constants.MEGA_TOKEN:
                            modifiers['mega'] = True
                        elif next == constants.TERA_TOKEN:
                            modifiers['tera'] = True
                        move = self.tokens[i + 2]
                        i += 3
                    
                    if move in constants.TOKENS:
                        raise PuzzleSyntaxError(f"Expected a move name, got '{move}' instead", self.locations[i - 1], self.lines)

                    commands.append({
                        'action': constants.MOVE,
                        'move': move,
                        'modifiers': modifiers,
                        'location': self.locations[i - 1]
                    })
                elif token == constants.SWITCH_TOKEN:
                    switch = self.tokens[i + 1]

                    if switch in constants.TOKENS:
                        raise PuzzleSyntaxError(f"Expected a pokemon name, got '{switch}' instead", self.locations[i + 1], self.lines)

                    commands.append({
                        'action': constants.SWITCH,
                        'pokemon': switch,
                        'location': self.locations[i + 1]
                    })

                    i += 2
                elif token == constants.SWITCH_OPEN_BRACKET:
                    if self.tokens[i + 2] == constants.SWITCH_CLOSE_BRACKET:
                        switch = self.tokens[i + 1]
                        
                        if switch in constants.TOKENS:
                            raise PuzzleSyntaxError(f"Expected a pokemon name, got '{switch}' instead", self.locations[i + 1], self.lines)

                        commands.append({
                            'action': constants.SET_SWITCH,
                            'pokemon': switch,
                            'location': self.locations[i + 1]
                        })
                        
                        i += 3
                    elif constants.SWITCH_CLOSE_BRACKET in self.tokens[i + 1:] and \
                        (constants.SWITCH_OPEN_BRACKET not in self.tokens[i + 1:] or self.tokens[i + 1:].index(constants.SWITCH_OPEN_BRACKET) > self.tokens[i + 1:].index(constants.SWITCH_CLOSE_BRACKET)):
                        raise PuzzleSyntaxError(f"'{self.tokens[i + 2]}' unexpected in set switch statement", self.locations[i + 2], self.lines)
                    else:
                        raise PuzzleSyntaxError(f"Missing closing parenthesis '{constants.SWITCH_CLOSE_BRACKET}' for set switch statement", self.locations[i + 2], self.lines)
                elif token == constants.REPEAT_OPEN_BRACKET:
                    if repeat_until_faint:
                        raise PuzzleSyntaxError(f"'{token}' unexpected in repeat until faint loop", self.locations[i], self.lines)
                    else:
                        result = self.parse_tokens(i = i + 1, repeat_until_faint = True)
                        commands.append({
                            'action': constants.REPEAT_UNTIL_FAINT,
                            'commands': result[0]
                        })
                        i = result[1]
                elif token == constants.REPEAT_CLOSE_BRACKET:
                    if repeat_until_faint:
                        return commands, i + 1
                    else:
                        raise PuzzleSyntaxError(f"'{token}' unexpected outside of repeat until faint loop", self.locations[i], self.lines)
                else:
                    raise PuzzleSyntaxError(f"'{token}' unexepected", self.locations[i], self.lines)
        except IndexError as e:
            raise PuzzleSyntaxError("Reached end of file while parsing puzzle", self.locations[-1], self.lines)
        
        return commands

    def validate_commands(self, commands: list[dict], repeating = False):
        if commands[0]['action'] != constants.SET_SWITCH and not repeating:
            raise PuzzleError("First command of each puzzle must be declaring a lead pokemon", self.locations[0], self.lines)
        for command in commands:
            if command['action'] == constants.SWITCH or command['action'] == constants.SET_SWITCH and command['pokemon'] not in pokedex:
                raise PuzzleError(f"'{command['pokemon']}' is not a valid Pokemon", command['location'], self.lines)
            elif command['action'] == constants.MOVE and command['move'] not in all_move_json:
                raise PuzzleError(f"'{command['move']}' is not a valid move", command['location'], self.lines)
            elif command['action'] == constants.REPEAT_UNTIL_FAINT:
                self.validate_commands(command['commands'], repeating=True)

    def get_puzzle_commands(self):
        return self.commands


def get_puzzle_commands(puzzle_text: str) -> list[dict]:
    return PuzzleParser(puzzle_text).get_puzzle_commands()