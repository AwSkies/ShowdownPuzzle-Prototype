import random
import os
from .puzzle_parser import get_puzzle_commands
from .team_converter import export_to_packed

PUZZLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzles")

def load_file(name, kind):
    if name is None:
        return 'null'

    path = os.path.join(PUZZLE_DIR, f"{name}", f"{kind}")
    if os.path.isdir(path):
        file_names = list()
        for f in os.listdir(path):
            full_path = os.path.join(path, f)
            if os.path.isfile(full_path) and not f.startswith('.'):
                file_names.append(full_path)
        file_path = random.choice(file_names)

    elif os.path.isfile(path):
        file_path = path
    else:
        raise ValueError("Path must be file or dir: {}".format(name))

    with open(file_path, 'r') as f:
        text = f.read()
    return text

def load_team(name):
    return export_to_packed(load_file(name, "team"))

def load_puzzle(name):
    return get_puzzle_commands(load_file(name, "puzzle"))

def load_hints(name):
    return load_file(name, "hints").splitlines()