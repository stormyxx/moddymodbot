from __future__ import annotations
from typing import List, Optional, Dict

from attr import define, Factory, frozen

from constants import Alignment, Modifier, SideEffect, WINCON_MAP, Phase
from embeds import Embed
from exceptions import ModBotError


@define
class Role:
    alignment: Optional[Alignment] = None
    role: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict) -> Optional[Role]:
        return cls(**d) if d else None

    @classmethod
    def from_str(cls, s: str) -> Role:
        role = cls()
        if s.lower().startswith("town "):
            role.alignment = Alignment.TOWN
            s = s.removeprefix("Town ").removeprefix("town ")
        if s.lower().startswith("mafia "):
            role.alignment = Alignment.MAFIA
            s = s.removeprefix("Mafia ").removeprefix("mafia ")
        if s.lower().startswith("3p "):
            role.alignment = Alignment.THIRD_PARTY
            s = s.removeprefix("3P ").removeprefix("3p ")
        role.role = s
        return role

    def __str__(self) -> str:
        return f"{self.alignment or ''} {self.role or ''}".strip()


@define
class Action:
    name: str
    desc: str = ""
    modifiers: List[Modifier] = Factory(list)
    shots: Optional[int] = None
    targets: int = 1
    self_targetable: bool = False
    side_effect: Optional[List[SideEffect]] = None

    @classmethod
    def from_dict(cls, d: Dict) -> Action:
        return cls(**d)

    def can_use_in_phase(self, phase: Phase) -> bool:
        if phase == Phase.DAY:
            return Modifier.PASSIVE not in self.modifiers and (
                Modifier.DAY in self.modifiers or Modifier.LIGHTNING in self.modifiers
            )
        elif phase == Phase.NIGHT:
            return Modifier.PASSIVE not in self.modifiers and Modifier.DAY not in self.modifiers
        else:
            return False

    def __str__(self) -> str:
        modifiers = "".join(f"[{modifier}]" for modifier in self.modifiers)
        if self.shots:
            modifiers += f"[{self.shots}-SHOT]"
        return f"**{modifiers}{' ' if modifiers else ''}{self.name}**: {self.desc}"


@define
class RoleCard:
    role: Optional[Role] = None
    flips_as: Optional[Role] = None
    actions: List[Action] = Factory(list)

    def __attrs_post_init__(self):
        if self.role and not self.flips_as:
            self.flips_as = self.role

    @classmethod
    def from_dict(cls, d: Dict) -> Optional[RoleCard]:
        if not d:
            return None
        d["role"] = Role.from_dict(d.get("role"))
        d["flips_as"] = Role.from_dict(d.get("flips_as"))
        d["actions"] = [Action.from_dict(a) for a in d.get("actions", [])]
        return cls(**d)

    def get_rolecard(self, fr_name: str = "PLAYER") -> Embed:
        body = f"Welcome, **{fr_name}**! You are a **{self.role}**.\n\n"
        if not self.actions:
            body += "You have no abilities; your only power is your voice and your vote."
        else:
            body += f"You have the following abilit{'y' if len(self.actions)==1 else 'ies'} at your disposal:\n"
            body += "\n".join(f"- {action}" for action in self.actions)
        body += f"\n\n{WINCON_MAP[self.role.alignment]}"
        return Embed.RoleCardEmbed(alignment=self.role.alignment, body=body)

    def get_action_from_name(self, name: str) -> Optional[Action]:
        for action in self.actions:
            if action.name.lower() == name.lower():
                return action

    def get_available_actions(self, phase: Phase) -> List[Action]:
        return [a for a in self.actions if a.can_use_in_phase(phase)]

    def format_available_actions(self, phase: Phase) -> str:
        actions = self.get_available_actions(phase)
        if actions:
            body = "You may use the following actions this phase:\n"
            body += "\n".join(f"- {a}" for a in actions)
            return body

        else:
            return "You have no active abilties available this phase :')"


@define
class Player:
    fr_name: str
    discord_id: int
    alive: bool = True
    role_card: Optional[RoleCard] = None

    @classmethod
    def from_dict(cls, d: Dict) -> Player:
        d["role_card"] = RoleCard.from_dict(d.get("role_card"))
        return cls(**d)

    def get_embed(self) -> Embed:
        if self.role and self.role.alignment:
            embed = Embed.RoleCardEmbed(alignment=self.role.alignment, title=f"Player Info: {self.fr_name}")
        else:
            embed = Embed.InfoEmbed(title=f"Player Info: {self.fr_name}")
        for field in ["fr_name", "discord_id", "alive"]:
            val = self.__getattribute__(field)
            if field == "discord_id":
                val = f"<@{val}>"
            embed.add_field(name=field_to_name(field), value=val)
        if self.role_card:
            for field in ["role", "flips_as"]:
                val = self.__getattribute__(field)
                embed.add_field(name=field_to_name(field), value=val)
            embed.add_field(name="\t", value="\t")
            embed.add_field(
                name="Actions",
                value="\n".join([f"- {action}" for action in self.actions]),
                inline=False,
            )
        return embed

    @property
    def _fr_name_bbcode(self) -> str:
        if not self.alive and self.flips_as:
            if self.flips_as.alignment == Alignment.TOWN:
                return f"[color=green]{self.fr_name}[/color]"
            if self.flips_as.alignment == Alignment.MAFIA:
                return f"[color=red]{self.fr_name}[/color]"
            if self.flips_as.alignment == Alignment.THIRD_PARTY:
                return f"[color=grey]{self.fr_name}[/color]"
        return self.fr_name

    def __str__(self) -> str:
        return self.fr_name

    @property
    def flips_as(self) -> Optional[Role]:
        return self.role_card.flips_as if self.role_card else None

    @property
    def role(self) -> Optional[Role]:
        return self.role_card.role if self.role_card else None

    @property
    def actions(self) -> List[Action]:
        return self.role_card.actions if self.role_card else []


@define
class Config:
    private_category: int
    vote_channel: int
    vc_channel: int
    vc_allowed_categories: list[int] = None
    announce_channel: int = None
    actions_channel: int = None

    def __attrs_post_init__(self):
        self.vc_allowed_categories = self.vc_allowed_categories or [self.private_category]


@define
class Rules:
    sleep_enabled: bool = True
    open_setup: bool = False


@frozen
class GamePhase:
    phase: Phase
    num: int

    def __str__(self):
        return f"{self.phase} {self.num}"

    def next(self) -> GamePhase:
        if self.phase == Phase.DAY:
            return GamePhase(Phase.NIGHT, self.num)
        else:
            return GamePhase(Phase.DAY, self.num + 1)


@define
class GameState:
    config: Config = Config(private_category=0, vote_channel=0, vc_channel=0)
    phase: GamePhase = GamePhase(phase=Phase.DAY, num=1)
    players: List[Player] = Factory(list)
    roles: Optional[List[RoleCard]] = None
    player_slot_map: Dict[str, Player] = None
    rules: Rules = Rules()

    def __attrs_post_init__(self):
        self.player_slot_map = {p.fr_name: p for p in self.players}

    def player_from_fr(self, fr_name: str, raise_err: bool = False) -> Optional[Player]:
        for player in self.players:
            if player.fr_name.lower() == fr_name.lower():
                return player
        if raise_err:
            raise ModBotError(f"Player with FR name: {fr_name} cannot be found!")
        return None

    def player_from_id(self, discord_id: int) -> Optional[Player]:
        for player in self.players:
            if player.discord_id == discord_id:
                return player
        return None


def field_to_name(field: str) -> str:
    acronyms = ["FR", "ID"]
    split_field = field.split("_")
    name = " ".join(w.title() if w.upper() not in acronyms else w.upper() for w in split_field)
    return name
