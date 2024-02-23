import re
import json
from copy import deepcopy
import logging

import constants
from data import all_move_json
from data import pokedex
from showdown.battle import Pokemon
from showdown.battle import LastUsedMove
from showdown.battle import DamageDealt
from showdown.battle import StatRange
from showdown.engine.helpers import normalize_name
from showdown.engine.helpers import get_pokemon_info_from_condition
from showdown.engine.helpers import calculate_stats
from showdown.engine.find_state_instructions import get_effective_speed
from showdown.engine.damage_calculator import calculate_damage
from showdown.engine.objects import boost_multiplier_lookup


logger = logging.getLogger(__name__)


MOVE_END_STRINGS = {'move', 'switch', 'upkeep', ''}


def can_have_priority_modified(battle, pokemon, move_name):
    return (
        "prankster" in [normalize_name(a) for a in pokedex[pokemon.name][constants.ABILITIES].values()] or
        move_name == "grassyglide" and battle.field == constants.GRASSY_TERRAIN
    )


def can_have_speed_modified(battle, pokemon):
    return (
        (
            pokemon.item is None and
            "unburden" in [normalize_name(a) for a in pokedex[pokemon.name][constants.ABILITIES].values()]
        ) or
        (
            battle.weather == constants.RAIN and
            pokemon.ability is None and
            "swiftswim" in [normalize_name(a) for a in pokedex[pokemon.name][constants.ABILITIES].values()]
        ) or
        (
            battle.weather == constants.SUN and
            pokemon.ability is None and
            "chlorophyll" in [normalize_name(a) for a in pokedex[pokemon.name][constants.ABILITIES].values()]
        ) or
        (
            battle.weather == constants.SAND and
            pokemon.ability is None and
            "sandrush" in [normalize_name(a) for a in pokedex[pokemon.name][constants.ABILITIES].values()]
        ) or
        (
            battle.weather in constants.HAIL_OR_SNOW and
            pokemon.ability is None and
            "slushrush" in [normalize_name(a) for a in pokedex[pokemon.name][constants.ABILITIES].values()]
        ) or
        (
            battle.field == constants.ELECTRIC_TERRAIN and
            pokemon.ability is None and
            "surgesurfer" in [normalize_name(a) for a in pokedex[pokemon.name][constants.ABILITIES].values()]
        ) or
        (
            pokemon.status == constants.PARALYZED and
            pokemon.ability is None and
            "quickfeet" in [normalize_name(a) for a in pokedex[pokemon.name][constants.ABILITIES].values()]
        )
    )


def find_pokemon_in_reserves(pkmn_name, reserves):
    for reserve_pkmn in reserves:
        if pkmn_name.startswith(reserve_pkmn.name) or reserve_pkmn.name.startswith(pkmn_name) or reserve_pkmn.base_name == pkmn_name:
            return reserve_pkmn
    return None


def find_reserve_pokemon_by_nickname(pkmn_nickname, reserves):
    for reserve_pkmn in reserves:
        if pkmn_nickname == reserve_pkmn.nickname:
            return reserve_pkmn
    return None


def is_opponent(battle,  split_msg):
    return not split_msg[2].startswith(battle.user.name)


def get_move_information(m):
    # Given a |move| line from the PS protocol, extract the user of the move and the move object
    try:
        split_move_line = m.split("|")
        return split_move_line[2], all_move_json[normalize_name(split_move_line[3])]
    except KeyError:
        logger.debug("Unknown move {} - using standard 0 priority move".format(normalize_name(m.split('|')[3])))
        return m.split('|')[2], {constants.ID: "unknown", constants.PRIORITY: 0}


def request(battle, split_msg):
    """Update the user's team given the battle JSON in split_msg[2]
       Also updates some battle meta-data such as rqid, force_switch, and wait"""
    if len(split_msg) >= 2:
        battle_json = json.loads(split_msg[2].strip('\''))
        logger.debug("Received battle JSON from server: {}".format(battle_json))
        battle.user.from_json(battle_json)
        battle.rqid = battle_json[constants.RQID]

        if battle_json.get(constants.FORCE_SWITCH):
            battle.force_switch = True
        else:
            battle.force_switch = False

        if battle_json.get(constants.WAIT):
            battle.wait = True
        else:
            battle.wait = False

        if not battle.wait:
            battle.request_json = battle_json


def inactive(battle, split_msg):
    regex_string = "(\d+) sec this turn"
    if split_msg[2].startswith(constants.TIME_LEFT):
        capture = re.search(regex_string, split_msg[2])
        try:
            time_left = int(capture.group(1))
            battle.time_remaining = time_left
            logger.debug("Time left: {}".format(time_left))
        except ValueError:
            logger.warning("{} is not a valid int".format(capture.group(1)))
        except AttributeError:
            logger.warning("'{}' does not match the regex '{}'".format(split_msg[2], regex_string))


def inactiveoff(battle, _):
    battle.time_remaining = None


def switch_or_drag(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
        logger.debug("Opponent has switched - clearing the last used move")
    else:
        side = battle.user
        side.side_conditions[constants.TOXIC_COUNT] = 0

    # check if the pokemon exists in the reserves
    # if it does not, then the newly-created pokemon is used (for formats without team preview)
    nickname = split_msg[2]
    temp_pkmn = Pokemon.from_switch_string(split_msg[3], nickname=nickname)
    pkmn = find_pokemon_in_reserves(temp_pkmn.name, side.reserve)

    if pkmn is None:
        pkmn = battle.user.active
    else:
        pkmn.nickname = temp_pkmn.nickname
        side.reserve.remove(pkmn)

    side.last_used_move = LastUsedMove(
        pokemon_name=None,
        move='switch {}'.format(pkmn.name),
        turn=battle.turn
    )

    # pkmn != active is a special edge-case for Zoroark
    if side.active is not None and pkmn != side.active:
        side.reserve.append(side.active)

    side.active = pkmn


def heal_or_damage(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
        other_side = battle.user
        pkmn = battle.opponent.active
        if len(split_msg) == 5 and split_msg[4] == "[from] move: Revival Blessing":
            nickname = Pokemon.extract_nickname_from_pokemonshowdown_string(split_msg[2])
            pkmn = find_reserve_pokemon_by_nickname(nickname, side.reserve)

        # opponent hp is given as a percentage
        if constants.FNT in split_msg[3]:
            pkmn.hp = 0
        else:
            new_hp_percentage = float(split_msg[3].split('/')[0]) / 100
            pkmn.hp = pkmn.max_hp * new_hp_percentage

    else:
        side = battle.user
        other_side = battle.opponent
        pkmn = battle.user.active
        if len(split_msg) == 5 and split_msg[4] == "[from] move: Revival Blessing":
            nickname = Pokemon.extract_nickname_from_pokemonshowdown_string(split_msg[2])
            pkmn = find_reserve_pokemon_by_nickname(nickname, side.reserve)
        if constants.FNT in split_msg[3]:
            pkmn.hp = 0
        else:
            pkmn.hp = float(split_msg[3].split('/')[0])
            pkmn.max_hp = float(split_msg[3].split('/')[1].split()[0])

    # increase the amount of turns toxic has been active
    if len(split_msg) == 5 and constants.TOXIC in split_msg[3] and '[from] psn' in split_msg[4]:
        side.side_conditions[constants.TOXIC_COUNT] += 1

    if len(split_msg) == 6 and split_msg[4].startswith('[from] item:') and other_side.name in split_msg[5]:
        item = normalize_name(split_msg[4].split('item:')[-1])
        logger.debug("Setting {}'s item to: {}".format(other_side.active.name, item))
        other_side.active.item = item

    # set the ability for the other side (the side not taking damage, '-damage' only)
    if len(split_msg) == 6 and split_msg[4].startswith('[from] ability:') and other_side.name in split_msg[5] and split_msg[1] == '-damage':
        ability = normalize_name(split_msg[4].split('ability:')[-1])
        logger.debug("Setting {}'s ability to: {}".format(other_side.active.name, ability))
        other_side.active.ability = ability

    # set the ability of the side (the side being healed, '-heal' only)
    if len(split_msg) == 6 and constants.ABILITY in split_msg[4] and other_side.name in split_msg[5] and split_msg[1] == '-heal':
        ability = normalize_name(split_msg[4].split(constants.ABILITY)[-1].strip(": "))
        logger.debug("Setting {}'s ability to: {}".format(pkmn.name, ability))
        pkmn.ability = ability

    # give that pokemon an item if this string specifies one
    if len(split_msg) == 5 and constants.ITEM in split_msg[4] and pkmn.item is not None:
        item = normalize_name(split_msg[4].split(constants.ITEM)[-1].strip(": "))
        logger.debug("Setting {}'s item to: {}".format(pkmn.name, item))
        pkmn.item = item


def faint(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    side.active.hp = 0


def move(battle, split_msg):
    if '[from]' in split_msg[-1] and split_msg[-1] != "[from]lockedmove":
        return

    move_name = normalize_name(split_msg[3].strip().lower())

    if is_opponent(battle, split_msg):
        side = battle.opponent
        pkmn = battle.opponent.active
    else:
        side = battle.user
        pkmn = battle.user.active

    # remove volatile status if they have it
    # this is for preparation moves like Phantom Force
    if move_name in pkmn.volatile_statuses:
        logger.debug("Removing volatile status {} from {}".format(move_name, pkmn.name))
        pkmn.volatile_statuses.remove(move_name)

    # add the move to it's moves if it hasn't been seen
    # decrement the PP by one
    # if the move is unknown, do nothing
    move_object = pkmn.get_move(move_name)
    if move_object is None:
        new_move = pkmn.add_move(move_name)
        if new_move is not None:
            new_move.current_pp -= 1
    else:
        move_object.current_pp -= 1
        logger.debug("{} already has the move {}. Decrementing the PP by 1".format(pkmn.name, move_name))

    try:
        category = all_move_json[move_name][constants.CATEGORY]
        logger.debug("Setting {}'s last used move: {}".format(pkmn.name, move_name))
        side.last_used_move = LastUsedMove(
            pokemon_name=pkmn.name,
            move=move_name,
            turn=battle.turn
        )
    except KeyError:
        category = None
        side.last_used_move = LastUsedMove(
            pokemon_name=pkmn.name,
            move=constants.DO_NOTHING_MOVE,
            turn=battle.turn
        )

    # there is nothing special in the protocol for "wish" - it must be extracted here
    if move_name == constants.WISH and 'still' not in split_msg[4]:
        logger.debug("{} used wish - expecting {} health of recovery next turn".format(side.active.name, side.active.max_hp/2))
        side.wish = (2, side.active.max_hp/2)


def boost(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
    else:
        pkmn = battle.user.active

    stat = constants.STAT_ABBREVIATION_LOOKUPS[split_msg[3].strip()]
    amount = int(split_msg[4].strip())

    pkmn.boosts[stat] = min(pkmn.boosts[stat] + amount, constants.MAX_BOOSTS)


def unboost(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
    else:
        pkmn = battle.user.active

    stat = constants.STAT_ABBREVIATION_LOOKUPS[split_msg[3].strip()]
    amount = int(split_msg[4].strip())

    pkmn.boosts[stat] = max(pkmn.boosts[stat] - amount, -1*constants.MAX_BOOSTS)


def status(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
    else:
        pkmn = battle.user.active

    if len(split_msg) > 4 and 'item: ' in split_msg[4]:
        pkmn.item = normalize_name(split_msg[4].split('item:')[-1])

    status_name = split_msg[3].strip()
    logger.debug("{} got status: {}".format(pkmn.name, status_name))
    pkmn.status = status_name


def activate(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
    else:
        pkmn = battle.user.active

    if split_msg[3].lower() == 'move: poltergeist':
        item = normalize_name(split_msg[4])
        logger.debug("{} has the item {}".format(pkmn.name, item))
        pkmn.item = item

    if split_msg[3].lower().startswith("ability: "):
        ability = normalize_name(split_msg[3].split(':')[-1].strip())
        logger.debug("Setting {}'s ability to {}".format(pkmn.name, ability))
        pkmn.ability = ability
    elif split_msg[3].lower().startswith("item: "):
        item = normalize_name(split_msg[3].split(':')[-1].strip())
        logger.debug("Setting {}'s item to {}".format(pkmn.name, item))
        pkmn.item = item


def prepare(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
    else:
        pkmn = battle.user.active

    being_prepared = normalize_name(split_msg[3])
    if being_prepared in pkmn.volatile_statuses:
        logger.warning("{} already has the volatile status {}".format(pkmn.name, being_prepared))
    else:
        pkmn.volatile_statuses.append(being_prepared)


def terastallize(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
    else:
        pkmn = battle.user.active

    pkmn.terastallized = True
    pkmn.types = [normalize_name(split_msg[3])]
    logger.debug("Terastallized {}".format(pkmn.name))


def start_volatile_status(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
        side = battle.opponent
    else:
        pkmn = battle.user.active
        side = battle.user

    volatile_status = normalize_name(split_msg[3].split(":")[-1])

    # for some reason futuresight is sent with the `-start` message
    # `-start` is typically reserved for volatile statuses
    if volatile_status == "futuresight":
        side.future_sight = (3, pkmn.name)
        return

    if volatile_status not in pkmn.volatile_statuses:
        logger.debug("Starting the volatile status {} on {}".format(volatile_status, pkmn.name))
        pkmn.volatile_statuses.append(volatile_status)

    if volatile_status == constants.DYNAMAX:
        pkmn.hp *= 2
        pkmn.max_hp *= 2
        logger.debug("{} started dynamax - doubling their HP to {}/{}".format(pkmn.name, pkmn.hp, pkmn.max_hp))

    if constants.ABILITY in split_msg[3]:
        pkmn.ability = volatile_status

    if len(split_msg) == 6 and constants.ABILITY in normalize_name(split_msg[5]):
        pkmn.ability = normalize_name(split_msg[5].split('ability:')[-1])

    if volatile_status == constants.TYPECHANGE:
        if split_msg[4] == "[from] move: Reflect Type":
            pkmn_name = normalize_name(split_msg[5].split(":")[-1])
            new_types = deepcopy(pokedex[pkmn_name][constants.TYPES])
        else:
            new_types = [normalize_name(t) for t in split_msg[4].split("/")]

        logger.debug("Setting {}'s types to {}".format(pkmn.name, new_types))
        pkmn.types = new_types


def end_volatile_status(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
    else:
        pkmn = battle.user.active

    volatile_status = normalize_name(split_msg[3].split(":")[-1])
    if volatile_status not in pkmn.volatile_statuses:
        logger.warning("Pokemon '{}' does not have the volatile status '{}'".format(pkmn.to_dict(), volatile_status))
    else:
        logger.debug("Removing the volatile status {} from {}".format(volatile_status, pkmn.name))
        pkmn.volatile_statuses.remove(volatile_status)
        if volatile_status == constants.DYNAMAX:
            pkmn.hp /= 2
            pkmn.max_hp /= 2
            logger.debug("{} ended dynamax - halving their HP to {}/{}".format(pkmn.name, pkmn.hp, pkmn.max_hp))


def curestatus(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    pkmn_name = split_msg[2].split(':')[-1].strip()

    if normalize_name(pkmn_name) == side.active.name:
        pkmn = side.active
    else:
        try:
            pkmn = next(filter(lambda x: x.name == normalize_name(pkmn_name), side.reserve))
        except StopIteration:
            logger.warning(
                "The pokemon {} does not exist in the party, defaulting to the active pokemon".format(normalize_name(pkmn_name))
            )
            pkmn = side.active

    pkmn.status = None


def cureteam(battle, split_msg):
    """Cure every pokemon on the opponent's team of it's status"""
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    side.active.status = None
    for pkmn in filter(lambda p: isinstance(p, Pokemon), side.reserve):
        pkmn.status = None


def weather(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    weather_name = normalize_name(split_msg[2].split(':')[-1].strip())
    logger.debug("Weather {} started".format(weather_name))
    battle.weather = weather_name

    if len(split_msg) >= 5 and side.name in split_msg[4]:
        ability = normalize_name(split_msg[3].split(':')[-1].strip())
        logger.debug("Setting {} ability to {}".format(side.active.name, ability))
        side.active.ability = ability


def fieldstart(battle, split_msg):
    """Set the battle's field condition"""
    field_name = normalize_name(split_msg[2].split(':')[-1].strip())

    # trick room shows up as a `-fieldstart` item but is separate from the other fields
    if field_name == constants.TRICK_ROOM:
        logger.debug("Setting trickroom")
        battle.trick_room = True
    else:
        logger.debug("Setting the field to {}".format(field_name))
        battle.field = field_name


def fieldend(battle, split_msg):
    """Remove the battle's field condition"""
    field_name = normalize_name(split_msg[2].split(':')[-1].strip())

    # trick room shows up as a `-fieldend` item but is separate from the other fields
    if field_name == constants.TRICK_ROOM:
        logger.debug("Removing trick room")
        battle.trick_room = False
    else:
        logger.debug("Setting the field to None")
        battle.field = None


def sidestart(battle, split_msg):
    """Set a side effect such as stealth rock or sticky web"""
    condition = split_msg[3].split(':')[-1].strip()
    condition = normalize_name(condition)

    if is_opponent(battle, split_msg):
        logger.debug("Side condition {} starting for opponent".format(condition))
        battle.opponent.side_conditions[condition] += 1
    else:
        logger.debug("Side condition {} starting for bot".format(condition))
        battle.user.side_conditions[condition] += 1


def sideend(battle, split_msg):
    """Remove a side effect such as stealth rock or sticky web"""
    condition = split_msg[3].split(':')[-1].strip()
    condition = normalize_name(condition)

    if is_opponent(battle, split_msg):
        logger.debug("Side condition {} ending for opponent".format(condition))
        battle.opponent.side_conditions[condition] = 0
    else:
        logger.debug("Side condition {} ending for bot".format(condition))
        battle.user.side_conditions[condition] = 0


def swapsideconditions(battle, _):
    user_sc = battle.user.side_conditions
    opponent_sc = battle.opponent.side_conditions
    for side_condition in constants.COURT_CHANGE_SWAPS:
        user_sc[side_condition], opponent_sc[side_condition] = opponent_sc[side_condition], user_sc[side_condition]


def set_item(battle, split_msg):
    """Set the opponent's item"""
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    item = normalize_name(split_msg[3].strip())
    logger.debug("Setting {}'s item to {}".format(side.active.name, item))
    side.active.item = item


def remove_item(battle, split_msg):
    """Remove the opponent's item"""
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    logger.debug("Removing {}'s item".format(side.active.name))
    side.active.item = None


def set_ability(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    for msg in split_msg:
        if constants.ABILITY in normalize_name(msg):
            ability = normalize_name(msg.split(':')[-1])
            logger.debug("Setting {}'s ability to {}".format(side.active.name, ability))
            side.active.ability = ability


def set_opponent_ability_from_ability_tag(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    ability = normalize_name(split_msg[3])
    logger.debug("Setting {}'s ability to {}".format(side.active.name, ability))
    side.active.ability = ability


def form_change(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    base_name = side.active.base_name
    hp_percent = float(side.active.hp) / side.active.max_hp
    previous_moves = side.active.moves
    previous_boosts = side.active.boosts
    previous_status = side.active.status
    previous_item = side.active.item

    new_pokemon = Pokemon.from_switch_string(split_msg[3])
    new_pokemon.moves = previous_moves
    if new_pokemon in side.reserve:
        side.reserve.remove(new_pokemon)

    side.active = new_pokemon
    side.active.hp = hp_percent * side.active.max_hp
    side.active.boosts = previous_boosts
    side.active.status = previous_status
    side.active.item = previous_item

    if side.active.name != "zoroark":
        side.active.base_name = base_name


def zpower(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    logger.debug("{} Used a Z-Move, setting item to None".format(side.active.name))
    side.active.item = None


def clearnegativeboost(battle, split_msg):
    if is_opponent(battle, split_msg):
        pkmn = battle.opponent.active
    else:
        pkmn = battle.user.active

    for stat, value in pkmn.boosts.items():
        if value < 0:
            logger.debug("Setting {}'s {} stat to 0".format(pkmn.name, stat))
            pkmn.boosts[stat] = 0


def clearallboost(battle, _):
    pkmn = battle.user.active
    for stat, value in pkmn.boosts.items():
        if value != 0:
            logger.debug("Setting {}'s {} stat to 0".format(pkmn.name, stat))
            pkmn.boosts[stat] = 0

    pkmn = battle.opponent.active
    for stat, value in pkmn.boosts.items():
        if value != 0:
            logger.debug("Setting {}'s {} stat to 0".format(pkmn.name, stat))
            pkmn.boosts[stat] = 0


def singleturn(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    move_name = normalize_name(split_msg[3].split(':')[-1])
    if move_name in constants.PROTECT_VOLATILE_STATUSES:
        # set to 2 because the `upkeep` function will decrement by 1 on every end-of-turn
        side.side_conditions[constants.PROTECT] = 2
        logger.debug("{} used protect".format(side.active.name))


def upkeep(battle, _):
    if battle.user.side_conditions[constants.PROTECT] > 0:
        battle.user.side_conditions[constants.PROTECT] -= 1
        logger.debug("Setting protect to {} for the bot".format(battle.user.side_conditions[constants.PROTECT]))

    if battle.opponent.side_conditions[constants.PROTECT] > 0:
        battle.opponent.side_conditions[constants.PROTECT] -= 1
        logger.debug("Setting protect to {} for the opponent".format(battle.opponent.side_conditions[constants.PROTECT]))

    if battle.user.wish[0] > 0:
        battle.user.wish = (battle.user.wish[0] - 1, battle.user.wish[1])
        logger.debug("Decrementing wish to {} for the bot".format(battle.user.wish[0]))

    if battle.opponent.wish[0] > 0:
        battle.opponent.wish = (battle.opponent.wish[0] - 1, battle.opponent.wish[1])
        logger.debug("Decrementing wish to {} for the opponent".format(battle.opponent.wish[0]))

    if battle.user.future_sight[0] > 0:
        battle.user.future_sight = (battle.user.future_sight[0] - 1, battle.user.future_sight[1])
        logger.debug("Decrementing future_sight to {} for the bot".format(battle.user.future_sight[0]))

    if battle.opponent.future_sight[0] > 0:
        battle.opponent.future_sight = (battle.opponent.future_sight[0] - 1, battle.opponent.future_sight[1])
        logger.debug("Decrementing future_sight to {} for the opponent".format(battle.opponent.future_sight[0]))


def mega(battle, split_msg):
    if is_opponent(battle, split_msg):
        side = battle.opponent
    else:
        side = battle.user

    side.active.is_mega = True
    logger.debug("Mega-Pokemon: {}".format(side.active.name))


def transform(battle, split_msg):
    if is_opponent(battle, split_msg):
        transformed_into_name = battle.user.active.name

        battle_copy = deepcopy(battle)
        battle.opponent.active.boosts = deepcopy(battle.user.active.boosts)

        battle_copy.user.from_json(battle_copy.request_json)

        if battle_copy.user.active.name == transformed_into_name or battle_copy.user.active.name.startswith(transformed_into_name):
            transformed_into = battle_copy.user.active
        else:
            transformed_into = find_pokemon_in_reserves(transformed_into_name, battle_copy.user.reserve)

        logger.debug("Opponent {} transformed into {}".format(battle.opponent.active.name, battle.user.active.name))
        battle.opponent.active.stats = deepcopy(transformed_into.stats)
        battle.opponent.active.ability = deepcopy(transformed_into.ability)
        battle.opponent.active.moves = deepcopy(transformed_into.moves)
        battle.opponent.active.types = deepcopy(transformed_into.types)

        if constants.TRANSFORM not in battle.opponent.active.volatile_statuses:
            battle.opponent.active.volatile_statuses.append(constants.TRANSFORM)


def turn(battle, split_msg):
    battle.turn = int(split_msg[2])


def noinit(battle, split_msg):
    if split_msg[2] == "rename":
        battle.battle_tag = split_msg[3]
        logger.debug("Renamed battle to {}".format(battle.battle_tag))


def update_battle(battle, msg):
    msg_lines = msg.split('\n')

    action = None
    for i, line in enumerate(msg_lines):
        split_msg = line.split('|')
        if len(split_msg) < 2:
            continue

        action = split_msg[1].strip()

        battle_modifiers_lookup = {
            'request': request,
            'switch': switch_or_drag,
            'faint': faint,
            'drag': switch_or_drag,
            '-heal': heal_or_damage,
            '-damage': heal_or_damage,
            'move': move,
            '-boost': boost,
            '-unboost': unboost,
            '-status': status,
            '-activate': activate,
            '-prepare': prepare,
            '-start': start_volatile_status,
            '-end': end_volatile_status,
            '-curestatus': curestatus,
            '-cureteam': cureteam,
            '-weather': weather,
            '-fieldstart': fieldstart,
            '-fieldend': fieldend,
            '-sidestart': sidestart,
            '-sideend': sideend,
            '-swapsideconditions': swapsideconditions,
            '-item': set_item,
            '-enditem': remove_item,
            '-immune': set_ability,
            '-ability': set_opponent_ability_from_ability_tag,
            'detailschange': form_change,
            'replace': form_change,
            '-formechange': form_change,
            '-transform': transform,
            '-mega': mega,
            '-terastallize': terastallize,
            '-zpower': zpower,
            '-clearnegativeboost': clearnegativeboost,
            '-clearallboost': clearallboost,
            '-singleturn': singleturn,
            'upkeep': upkeep,
            'inactive': inactive,
            'inactiveoff': inactiveoff,
            'turn': turn,
            'noinit': noinit,
        }

        function_to_call = battle_modifiers_lookup.get(action)
        if function_to_call is not None:
            function_to_call(battle, split_msg)

        if action == 'turn':
            return True

    if action in ['inactive', 'updatesearch']:
        return False

    if action != "request":
        return battle.force_switch


async def async_update_battle(battle, msg):
    return update_battle(battle, msg)
