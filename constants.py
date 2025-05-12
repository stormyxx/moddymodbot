from enum import Enum

import pytz

FR_TZ = pytz.timezone("US/Pacific")
TIME_FORMAT = "%-d %b %Y %H:%M:%S FRT"

OK_EMOJI = "<:ok:1297854432763056140>"


class Alignment:
    TOWN = "Town"
    MAFIA = "Mafia"
    THIRD_PARTY = "3P"


class Modifier:
    FACTIONAL = "FACTIONAL"
    LIGHTNING = "LIGHTNING"
    PASSIVE = "PASSIVE"
    DAY = "DAY"


class Phase:
    DAY = "Day"
    NIGHT = "Night"


class SideEffect:
    PEW_PEW = "Pew Pew"


WINCON_MAP = {
    Alignment.TOWN: "You win when all mafia members have been eliminated, and there is at least one town-aligned member alive.",
    Alignment.MAFIA: "You win when the mafia make up half of the remaining players alive, or when nothing can prevent this.",
    Alignment.THIRD_PARTY: "You are neither aligned with the town or mafia, and have your own wincon to fulfil.",
}
