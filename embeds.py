from __future__ import annotations

from typing import Union

import discord

from constants import Alignment


class Embed(discord.Embed):
    @classmethod
    def ErrorEmbed(
        cls,
        title: str = "Oh no :')",
        body: str = None,
        footer: str = None,
    ) -> Embed:
        embed = cls(color=16210272, title=title, description=body)
        embed.set_thumbnail(url="https://i.imgur.com/zdNKpCa.png")
        return embed.set_footer(text=footer)

    @classmethod
    def InfoEmbed(cls, title: str = None, body: str = None, footer: str = None) -> Embed:
        embed = cls(color=5888759, title=title, description=body)
        embed.set_thumbnail(url="https://i.imgur.com/QXdm2ew.png")
        return embed.set_footer(text=footer)

    @classmethod
    def SuccessEmbed(cls, title: str = "Success!", body: str = None, footer: str = None) -> Embed:
        embed = cls(color=8121951, title=title, description=body)
        embed.set_thumbnail(url="https://i.imgur.com/IJGz87q.png")
        return embed.set_footer(text=footer)

    @classmethod
    def RandomEmbed(
        cls,
        title: str = "The RNG gods have spoken...",
        body: str = None,
        footer: str = None,
    ) -> Embed:
        embed = cls(color=16758096, title=title, description=body)
        embed.set_thumbnail(url="https://i.imgur.com/ruYBKUP.png")
        return embed.set_footer(text=footer)

    @classmethod
    def LightningEmbed(cls, title: str = "Lightning action!", body: str = None, footer: str = None) -> Embed:
        embed = cls(color=16753639, title=title, description=body)
        embed.set_thumbnail(url="https://i.imgur.com/MCCBLnQ.png")
        return embed.set_footer(text=footer)

    @classmethod
    def RoleCardEmbed(
        cls,
        alignment: Alignment,
        title: str = None,
        body: str = None,
        footer: str = None,
    ):
        color_map = {
            Alignment.TOWN: 8322942,
            Alignment.MAFIA: 16736602,
            Alignment.THIRD_PARTY: 16756053,
        }
        thumb_map = {
            Alignment.TOWN: "https://i.imgur.com/AHp27SP.png",
            Alignment.MAFIA: "https://i.imgur.com/0kYAvbu.png",
            Alignment.THIRD_PARTY: "https://i.imgur.com/RHl3PTB.png",
        }
        embed = cls(color=color_map[alignment], title=title, description=body)
        embed.set_thumbnail(url=thumb_map[alignment])
        return embed.set_footer(text=footer)
