import logging

import constants

from showdown.battle import Battle
from showdown.engine.objects import StateMutator
from showdown.engine.select_best_move import pick_safest
from showdown.engine.select_best_move import get_payoff_matrix


logger = logging.getLogger(__name__)


def format_decision(battle: Battle, decision, switch = False, **kwargs):
    '''Formats a decision for communication with Pokemon-Showdown'''

    if switch:
        switch_pokemon = decision
        verify = f"{constants.SWITCH_STRING} {switch_pokemon}"
        if switch_pokemon in [pkmn.name for pkmn in battle.user.reserve]:
            message = f"/{constants.SWITCH_STRING} {switch_pokemon}"
        else:
            raise ValueError(f"Tried to switch to: {switch_pokemon}")
    else:
        message = "/choose move {}".format(decision)
        verify = decision
        for flag in kwargs:
            if flag == 'mega' and kwargs['mega'] and battle.user.active.can_mega_evo:
                message += f" {constants.MEGA}"
            elif flag == 'ultra_burst' and kwargs['ultra_burst'] and battle.user.active.can_ultra_burst:
                message += f" {constants.ULTRA_BURST}"
            if flag == 'dynamax' and kwargs['dynamax'] and battle.user.active.can_dynamax:
                message += f" {constants.DYNAMAX}"
            elif flag == 'tera' and kwargs['tera'] and battle.user.active.can_terastallize:
                message += f" {constants.TERASTALLIZE}"
            if flag == 'z' and kwargs['z'] and battle.user.active.get_move(decision).can_z:
                message += f" {constants.ZMOVE}"

    # Verify that the decision being made is a valid option
    if verify not in battle.get_all_options()[0]:
        raise ValueError(f"{verify} is not a valid option at this time")

    return [message, str(battle.rqid)]


def prefix_opponent_move(score_lookup, prefix):
    new_score_lookup = dict()
    for k, v in score_lookup.items():
        bot_move, opponent_move = k
        new_opponent_move = "{}_{}".format(opponent_move, prefix)
        new_score_lookup[(bot_move, new_opponent_move)] = v

    return new_score_lookup


def pick_safest_move_from_battles(battles):
    all_scores = dict()
    for i, b in enumerate(battles):
        state = b.create_state()
        mutator = StateMutator(state)
        user_options, opponent_options = b.get_all_options()
        logger.debug("Searching through the state: {}".format(mutator.state))
        scores = get_payoff_matrix(mutator, user_options, opponent_options, prune=True)

        prefixed_scores = prefix_opponent_move(scores, str(i))
        all_scores = {**all_scores, **prefixed_scores}

    decision, payoff = pick_safest(all_scores, remove_guaranteed=True)
    bot_choice = decision[0]
    logger.debug("Safest: {}, {}".format(bot_choice, payoff))
    return bot_choice


def pick_safest_move_using_dynamic_search_depth(battles):
    """
    Dynamically decides how far to look into the game.

    This requires a strong computer to be able to search 3/4 turns ahead.
    Using a pypy interpreter will also result in better performance.

    """
    all_scores = dict()
    num_battles = len(battles)

    if num_battles > 1:
        search_depth = 2

        for i, b in enumerate(battles):
            state = b.create_state()
            mutator = StateMutator(state)
            user_options, opponent_options = b.get_all_options()
            logger.debug("Searching through the state: {}".format(mutator.state))
            scores = get_payoff_matrix(mutator, user_options, opponent_options, depth=search_depth, prune=True)
            prefixed_scores = prefix_opponent_move(scores, str(i))
            all_scores = {**all_scores, **prefixed_scores}

    elif num_battles == 1:
        search_depth = 3

        b = battles[0]
        state = b.create_state()
        mutator = StateMutator(state)
        user_options, opponent_options = b.get_all_options()

        num_user_options = len(user_options)
        num_opponent_options = len(opponent_options)
        options_product = num_user_options * num_opponent_options
        if options_product < 20 and num_user_options > 1 and num_opponent_options > 1:
            logger.debug("Low options product, looking an additional depth")
            search_depth += 1

        logger.debug("Searching through the state: {}".format(mutator.state))
        logger.debug("Options Product: {}".format(options_product))
        logger.debug("My Options: {}".format(user_options))
        logger.debug("Opponent Options: {}".format(opponent_options))
        logger.debug("Search depth: {}".format(search_depth))
        all_scores = get_payoff_matrix(mutator, user_options, opponent_options, depth=search_depth, prune=True)

    else:
        raise ValueError("less than 1 battle?: {}".format(battles))

    decision, payoff = pick_safest(all_scores, remove_guaranteed=True)
    bot_choice = decision[0]
    logger.debug("Safest: {}, {}".format(bot_choice, payoff))
    logger.debug("Depth: {}".format(search_depth))
    return bot_choice
