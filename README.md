# Showdown Puzzle
A program to make and run Pokémon battle puzzles to run on [Pokemon Showdown](https://pokemonshowdown.com/). The code is based on [pmariglia's Showdown battle-bot](https://github.com/pmariglia/showdown), so huge thanks to them.

The bot can play single battles in generations 3 through 8.


## Getting Started

### Installation

**1. Clone**

Clone the repository with `git clone https://github.com/CapClumsy/ShowdownPuzzle.git`

**2. Install Requirements**

Install the requirements with `pip install -r requirements.txt`.

**3. Configure your [env](./env) file**

Here is a sample:
```
PUZZLE=MyPuzzle
WEBSOCKET_URI=sim.smogon.com:8000
PS_USERNAME=MyUsername
PS_PASSWORD=MyPassword
BOT_MODE=ACCEPT_CHALLENGE
POKEMON_MODE=gen9nationaldexag
RUN_COUNT=100
```

### Run

Run with `python run.py` or double click [`run.py`](./run.py) with the python launcher installed

#### Python version
Developed and tested using Python 3.12.0.

### Configuration
Environment variables are used for configuration.
You may either set these in your environment before running,
or populate them in the [env](./env) file.

The configurations available are:

| Config Name | Type | Required | Description |
|---|:---:|:---:|---|
| **`PUZZLE`** | string | yes | The BattleBot module to use. More on this below in the Battle Bots section |
| **`WEBSOCKET_URI`** | string | yes | The address to use to connect to the Pokemon Showdown websocket |
| **`PS_USERNAME`** | string | yes | Pokemon Showdown username |
| **`PS_PASSWORD`** | string | yes | Pokemon Showdown password  |
| **`BOT_MODE`** | string | yes | The mode the the bot will operate in. Options are `CHALLENGE_USER`, `SEARCH_LADDER`, or `ACCEPT_CHALLENGE` |
| **`POKEMON_MODE`** | string | yes | The type of game this bot will play: `gen8ou`, `gen7randombattle`, etc. |
| **`USER_TO_CHALLENGE`** | string | only if `BOT_MODE` is `CHALLENGE_USER` | If `BOT_MODE` is `CHALLENGE_USER`, this is the name of the user you want your bot to challenge |
| **`RUN_COUNT`** | int | no | The number of games the bot will play before quitting |
| **`ROOM_NAME`** | string | no | If `BOT_MODE` is `ACCEPT_CHALLENGE`, the bot will join this chatroom while waiting for a challenge. |
| **`SAVE_REPLAY`** | boolean | no | Specifies whether or not to save replays of the battles (`True` / `False`) |
| **`LOG_LEVEL`** | string | no | The Python logging level (`DEBUG`, `INFO`, etc.) |

## Make Your Own Puzzles

### Setup

Puzzles are stored in [`puzzles/puzzles`](./puzzles/puzzles). Create a a new folder. The **name of the of the folder is used for the name of the puzzle**. Each folder needs three files (make sure they have no file extension).

1. `puzzle`

The code containing the commands to execute during the battle. More on this below.

2. `team`

Plain text containing the team information in the [PokePaste format](https://pokepast.es/syntax.html). (Select "Upload to PokePaste" from the Showdown teambuilder.)

3. `hints`

Hints you want the bot to give when prompted. Each hint should be separated by a newline. It is okay to leave this file blank, but don't delete it.

### Syntax

Commands found in the `puzzle` file are executed from top to bottom. Every puzzle file must begin with a set switch command to specify the lead Pokemon to send out. During parsing, all arguments for commands (move names, pokemon names) have all spaces and dashes removed and are converted to lowercase. When running, pay attention to the error messages, as the program gives notifications for when there are syntax errors in the code or the requested Pokemon or move name does not exist or is misspelled.

#### Use a move

`+ <move name>`

Use `+` followed by the name of the move

**Example:** Makes the active Pokemon use Splash

```
+ Splash
```

#### Mega Evolve

`+@ <move name>`

Use `@` when selecting a move before a move name to mega evolve when using the move, if possible.

**Example:** Makes the active Pokemon mega evolve and use Fake Out

```
+@ Fake out
```

#### Terastallize

`+# <move name>`

Use `#` when selecting a move before a move name to terastallize when using the move, if possible.

**Example:** Makes the active Pokemon terrastallize and use Tera Blast

```
+# Tera Blast
```

#### Switch

`> <pokemon name>`

Use `>` followed by the name of the Pokemon. Name modifiers such as alternate forms, types, or mega should not be used.

**Example:** Switches to Arcanine

```
> Arcanine
```

#### Set Switch

`(<pokemon name>)`

Whenever a switch is required, such as

- the beginning of a battle
- after fainting
- using moves like U-turn or Volt Switch

the bot needs to know which Pokemon to switch to. Put the name of the Pokemon in between parentheses `()` to specify what Pokemon to switch to when a switch is required. *The first command of every puzzle file must be a set switch command to specify which Pokemon to lead with.*

**Example:** Sets Ninetales as the Pokemon to switch to when the currently active Pokemon faints or uses a switch-out move, or sends out Ninetails as the lead Pokemon if this is the first command of the puzzle/beginning of the battle

```
(Ninetales)
```

**Example:** Switches out to Riolu after the active Pokemon uses U-turn

```
(Riolu)
+ U-turn
```

#### Repeat Until Faint

`[<commands>]`

Put a list of commands between square brackets `[]` to have a Pokemon repeat those commands until they faint. *You must have a switch set for once the Pokemon faints.* You must set the switch before the repeating commands, not after.

**Example:** Makes the active Pokemon use Dragon Pulse until it faints, then sends out Frosmoth

```
(Frosmoth)
[+ Dragon Pulse]
```

**Example:** Makes the active Pokemon alternate between using Thunderbolt and Double team until it faints, then sends out Tinkaton 

```
(Tinkaton)
[
    + Thunderbolt
    + Double Team
]
```

#### Comment

`// comment`

Use `//` to ignore all of the text until the next reserved symbol. They may span multiple lines but cannot contain any of the symbols used for commands.

**Example:**

```
// The solution is for the player to tera normal
(Ampharos)
[+ Shadow claw]
```

### Summary
| Symbol | Name | Usage |
|---|:---:|:---:|
| `+` | Move | `+ <move>` |
| `@` | Mega | `+@ <move>` |
| `#` | Terastallize | `+# <move>` |
| `>` | Switch | `> <pokemon>` |
| `()` | Set switch | `(<pokemon>)` |
| `[]` | Repeat until faint | `[<commands>]` |

### Full Example
As seen in [`puzzles/puzzles/DeoxysRocks/puzzle`](./puzzles/puzzles/DeoxysRocks/puzzle)

```
(Deoxys-Attack)
+ Protect
+ Stealth Rock
(Dracovish)
[+ Extreme Speed]

(Kingambit)
[+ Fishious Rend]

[+ Kowtow Cleave]
```
