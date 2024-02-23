import constants

def parse_puzzle_text(puzzle_text: str):
    tokens = ['']
    i = 0
    for char in puzzle_text:
        if char in constants.TOKENS:
            tokens.append(char)
            tokens.append('')
            i += 2
        else:
            tokens[i] += char
    
    # Strip tokens of newlines and spaces
    tokens = [t.strip() for t in tokens]
    # Remove whitespace tokens that have been stripped
    while '' in tokens:
        tokens.remove('')

    return [t.lower() for t in tokens]

def parse_tokens(tokens: list[str], i = 0, repeat_until_faint = False):
    # Remove comments
    while constants.COMMENT_TOKEN in tokens:
        index = tokens.index(constants.COMMENT_TOKEN)
        tokens.pop(index)
        if tokens[index] not in constants.TOKENS:
            tokens.pop(index)
    
    commands = []
    try:
        while i < len(tokens):
            token = tokens[i]
            if token == '+':
                next = tokens[i + 1]
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
                    move = tokens[i + 2]
                    i += 3 
                
                if move in constants.TOKENS:
                    raise SyntaxError(f"Expected a move name, got '{move}' instead")

                commands.append({
                    'action': constants.MOVE,
                    'move': move,
                    'modifiers': modifiers
                })
            elif token == constants.SWITCH_TOKEN:
                switch = tokens[i + 1]
                i += 2
                if switch in constants.TOKENS:
                    raise SyntaxError(f"Expected a pokemon name, got '{switch}' instead")

                commands.append({
                    'action': constants.SWITCH,
                    'pokemon': switch
                })
            elif token == constants.SWITCH_OPEN_BRACKET:
                if tokens[i + 2] == constants.SWITCH_CLOSE_BRACKET:
                    switch = tokens[i + 1]
                    i += 3
                    if switch in constants.TOKENS:
                        raise SyntaxError(f"Pokemon name expected, got '{switch}' instead")

                    commands.append({
                        'action': constants.SET_SWITCH,
                        'pokemon': switch
                    })
                else:
                    raise SyntaxError(f"Missing closing parenthesis '{constants.SWITCH_CLOSE_BRACKET}' when setting default switch")
            elif token == constants.REPEAT_OPEN_BRACKET:
                if repeat_until_faint:
                    raise SyntaxError(f"'{token}' unexpected in repeat until faint loop")
                else:
                    result = parse_tokens(tokens, i = i + 1, repeat_until_faint = True)
                    commands.append({
                        'action': constants.REPEAT_UNTIL_FAINT,
                        'commands': result[0]
                    })
                    i = result[1]
            elif token == constants.REPEAT_CLOSE_BRACKET:
                if repeat_until_faint:
                    return commands, i + 1
                else:
                    raise SyntaxError(f"'{token} unexpected outside of repeat until faint loop")
            else:
                raise SyntaxError(f"'{token}' unexepected")
    except IndexError as e:
        raise SyntaxError("Reached end of file while parsing")
    
    return commands

def validate_commands(commands: list[dict]):
    if commands[0]['action'] != constants.SET_SWITCH:
        raise ValueError("First command of each puzzle must be declaring a lead pokemon")
    # TODO: Use data to check that names are valid?

def get_puzzle_commands(puzzle_text: str):
    commands = parse_tokens(parse_puzzle_text(puzzle_text))
    validate_commands(commands)
    return commands