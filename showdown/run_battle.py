import importlib
import json
import asyncio
import concurrent.futures
from copy import deepcopy
import logging

import data
from data.helpers import get_standard_battle_sets
import constants
from config import ShowdownConfig
from showdown.engine.evaluate import Scoring
from showdown.battle import Pokemon
from showdown.battle import LastUsedMove
from showdown.battle_modifier import async_update_battle
from showdown.puzzle_runner.puzzle_runner import PuzzleRunner

from showdown.websocket_client import PSWebsocketClient

logger = logging.getLogger(__name__)


def battle_is_finished(battle_tag, msg):
    return (
        msg.startswith(">{}".format(battle_tag)) and
        (constants.WIN_STRING in msg or constants.TIE_STRING in msg) and
        constants.CHAT_STRING not in msg
    )


async def async_pick_move(battle):
    best_move = battle.find_best_move()
    choice = best_move[0]
    if constants.SWITCH_STRING in choice:
        battle.user.last_used_move = LastUsedMove(battle.user.active.name, "switch {}".format(choice.split()[-1]), battle.turn)
    else:
        battle.user.last_used_move = LastUsedMove(battle.user.active.name, choice.split()[2], battle.turn)
    return best_move


async def handle_team_preview(battle, ps_websocket_client):
    battle_copy = deepcopy(battle)
    battle_copy.user.active = Pokemon.get_dummy()
    battle_copy.opponent.active = Pokemon.get_dummy()

    best_move = await async_pick_move(battle_copy)
    size_of_team = len(battle.user.reserve)
    team_list_indexes = list(range(1, size_of_team + 1))
    switch_pokemon = best_move[0].split()[-1]
    for pkmn in battle.user.reserve:
        if pkmn.name == switch_pokemon:
            team_list_indexes.remove(pkmn.index)
            choice_digit = pkmn.index
            break

    message = [f"/team {choice_digit}{"".join(str(x) for x in team_list_indexes)}|{battle.rqid}"]

    await ps_websocket_client.send_message(battle.battle_tag, message)


async def get_battle_tag_and_opponent(ps_websocket_client: PSWebsocketClient):
    while True:
        msg = await ps_websocket_client.receive_message()
        split_msg = msg.split('|')
        first_msg = split_msg[0]
        if 'battle' in first_msg:
            battle_tag = first_msg.replace('>', '').strip()
            user_name = split_msg[-1].replace('☆', '').strip()
            opponent_name = split_msg[4].replace(user_name, '').replace('vs.', '').strip()
            return battle_tag, opponent_name


async def initialize_battle_with_tag(ps_websocket_client: PSWebsocketClient, puzzle_commands, set_request_json=True):
    battle_tag, opponent_name = await get_battle_tag_and_opponent(ps_websocket_client)
    while True:
        msg = await ps_websocket_client.receive_message()
        split_msg = msg.split('|')
        if split_msg[1].strip() == 'request' and split_msg[2].strip():
            user_json = json.loads(split_msg[2].strip('\''))
            user_id = user_json[constants.SIDE][constants.ID]
            opponent_id = constants.ID_LOOKUP[user_id]
            battle = PuzzleRunner(puzzle_commands, battle_tag)
            battle.opponent.name = opponent_id
            battle.opponent.account_name = opponent_name

            if set_request_json:
                battle.request_json = user_json

            return battle, opponent_id, user_json


async def read_messages_until_first_pokemon_is_seen(ps_websocket_client, battle, opponent_id, user_json):
    # keep reading messages until the opponent's first pokemon is seen
    # this is run when starting non team-preview battles
    while True:
        msg = await ps_websocket_client.receive_message()
        if constants.START_STRING in msg:
            split_msg = msg.split(constants.START_STRING)[-1].split('\n')
            for line in split_msg:
                if opponent_id in line and constants.SWITCH_STRING in line:
                    battle.start_non_team_preview_battle(user_json, line)

                elif battle.started:
                    await async_update_battle(battle, line)

            # first move needs to be picked here
            best_move = await async_pick_move(battle)
            await ps_websocket_client.send_message(battle.battle_tag, best_move)

            return


async def start_random_battle(ps_websocket_client: PSWebsocketClient, pokemon_battle_type):
    battle, opponent_id, user_json = await initialize_battle_with_tag(ps_websocket_client)
    battle.battle_type = constants.RANDOM_BATTLE
    battle.generation = pokemon_battle_type[:4]

    await read_messages_until_first_pokemon_is_seen(ps_websocket_client, battle, opponent_id, user_json)

    return battle


async def start_standard_battle(ps_websocket_client: PSWebsocketClient, pokemon_battle_type, puzzle_commands):
    battle, opponent_id, user_json = await initialize_battle_with_tag(ps_websocket_client, puzzle_commands, set_request_json=False)
    battle.battle_type = constants.STANDARD_BATTLE
    battle.generation = pokemon_battle_type[:4]

    if battle.generation in constants.NO_TEAM_PREVIEW_GENS:
        await read_messages_until_first_pokemon_is_seen(ps_websocket_client, battle, opponent_id, user_json)
    else:
        msg = ''
        while constants.START_TEAM_PREVIEW not in msg:
            msg = await ps_websocket_client.receive_message()

        preview_string_lines = msg.split(constants.START_TEAM_PREVIEW)[-1].split('\n')

        opponent_pokemon = []
        for line in preview_string_lines:
            if not line:
                continue

            split_line = line.split('|')
            if split_line[1] == constants.TEAM_PREVIEW_POKE and split_line[2].strip() == opponent_id:
                opponent_pokemon.append(split_line[3])

        battle.initialize_team_preview(user_json, opponent_pokemon, pokemon_battle_type)
        battle.during_team_preview()

        await handle_team_preview(battle, ps_websocket_client)

    return battle


async def start_battle(ps_websocket_client: PSWebsocketClient, pokemon_battle_type, puzzle_commands):
    if "random" in pokemon_battle_type:
        Scoring.POKEMON_ALIVE_STATIC = 30  # random battle benefits from a lower static score for an alive pkmn
        battle = await start_random_battle(ps_websocket_client, pokemon_battle_type)
    else:
        battle = await start_standard_battle(ps_websocket_client, pokemon_battle_type, puzzle_commands)

    await ps_websocket_client.send_message(battle.battle_tag, ["Welcome to this Showdown Puzzle! Have fun!"])

    return battle


async def pokemon_battle(ps_websocket_client: PSWebsocketClient, pokemon_battle_type, puzzle_commands, hints):
    battle = await start_battle(ps_websocket_client, pokemon_battle_type, puzzle_commands)
    n_hints = 0
    while True:
        msg: str = await ps_websocket_client.receive_message()

        try:
            split_message = msg.splitlines()[1].split('|')
            hint_message = split_message[3]
            hint = split_message[1] == 'c' and 'hint' in hint_message and len(hints) != 0
        except Exception as e:
            hint = False

        if battle_is_finished(battle.battle_tag, msg):
            if constants.WIN_STRING in msg:
                winner = msg.split(constants.WIN_STRING)[-1].split('\n')[0].strip()
            else:
                winner = None
            logger.debug("Winner: {}".format(winner))
            await ps_websocket_client.send_message(battle.battle_tag, ["gg"])
            await ps_websocket_client.leave_battle(battle.battle_tag, save_replay=ShowdownConfig.save_replay)
            return winner
        elif '-crit' in msg.split('|'):
            await ps_websocket_client.send_message(battle.battle_tag, ["Critical hit detected - aborting puzzle"])
            await ps_websocket_client.leave_battle(battle.battle_tag, save_replay=ShowdownConfig.save_replay)
        elif hint:
            await ps_websocket_client.send_message(battle.battle_tag, [hints[n_hints % len(hints)]])
            n_hints += 1
        else:
            action_required = await async_update_battle(battle, msg)
            if action_required and not battle.wait:
                best_move = await async_pick_move(battle)
                await ps_websocket_client.send_message(battle.battle_tag, best_move)
