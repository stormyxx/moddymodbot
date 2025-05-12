import re
from typing import Dict

import attrs
from discord.ext import commands
from discord.ext.commands import Context, Cog
from discord.ext.commands._types import BotT

from constants import Phase
from db_client import DBClient, get_db
from embeds import Embed
from exceptions import ModBotError
from model import GameState, GamePhase
from utils import check_is_mod


class Phases(commands.Cog):
    def __init__(self, bot: commands.Bot, games: Dict[int, GameState]):
        self.bot: commands.Bot = bot
        self.games: Dict[int, GameState] = games
        self.db = get_db()

    @commands.group(invoke_without_command=True)
    async def phase(self, ctx: Context):
        raise ModBotError("Invalid command used! Use `!vote help` to see available commands.")

    @phase.command()
    @commands.check(check_is_mod)
    async def next(self, ctx: Context):
        game = self.games[ctx.guild.id]
        old_phase = game.phase
        game.phase = game.phase.next()
        self.bot.dispatch("phase_change", ctx, old_phase, game.phase)
        # the success message is handled in vote cog

    @phase.command()
    @commands.check(check_is_mod)
    async def set(self, ctx: Context, *, phase: str = ""):
        game = self.games[ctx.guild.id]
        if not re.match(r"(d|day|n|night) ?(\d{1,2})", phase.lower()):
            raise ModBotError(
                "Invalid phase given!\n\n"
                "Examples:\n"
                "- `!phase set d1`\n"
                "- `!phase set Night 2\n"
                "- `!phase set Day 5"
            )
        game.phase = GamePhase(
            phase=Phase.DAY if "d" in phase.lower() else Phase.NIGHT,
            num=int("".join(c for c in phase if c.isnumeric())),
        )
        await ctx.send(embed=Embed.SuccessEmbed(body=f"It is now **{game.phase}**!"))
        self.bot.dispatch("phase_update", ctx)

    @phase.command()
    async def help(self, ctx: Context):
        await ctx.send(
            embed=Embed.InfoEmbed(
                body="### For mods:\n"
                "- `!phase next`: change the phase to the next phase, clear all votes, and en/disable voting.\n"
                "- `!phase set <phase>`: set the current phase of the game."
            )
        )

    @Cog.listener("on_ready")
    async def _setup(self):
        phases = self.db["phases"].find()
        async for phase in phases:
            guild_id = phase.pop("_id")
            self.games[guild_id].phase = GamePhase(**phase)
        await self.bot.get_channel(1267309740891963508).send("Bot restarted!")

    async def cog_after_invoke(self, ctx: Context[BotT]) -> None:
        guild_id = ctx.guild.id
        await self.db["phases"].find_one_and_replace(
            filter={"_id": guild_id},
            replacement=attrs.asdict(self.games[guild_id].phase) | {"_id": guild_id},
            upsert=True,
        )
