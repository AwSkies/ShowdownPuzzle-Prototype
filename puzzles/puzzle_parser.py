import constants

def parse_tokens(puzzle_text: str):
    tokens = ['']
    i = 0
    for char in puzzle_text:
        if char in constants.TOKENS:
            tokens.append(char)
            tokens.append('')
            i += 2
        else:
            tokens[i] += char
    tokens = [t.strip() for t in tokens]
    while '' in tokens:
        tokens.remove('')
    return tokens

def get_puzzle_commands(puzzle_text: str):
    # TODO: Write rest of parsing from tokens 
    return parse_tokens(puzzle_text)