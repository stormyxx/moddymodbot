import random

from discord.ext import commands
from discord.ext.commands import Context

from embeds import Embed
from exceptions import ModBotError


class Random(commands.Cog):
    @commands.group()
    async def random(self, ctx: Context):
        if not ctx.invoked_subcommand:
            raise ModBotError("Invalid command used! Use `!random help` to see available commands.")

    @random.command()
    async def choose(self, ctx: Context, *choices: str):
        choice = random.choice(choices)
        await ctx.send(
            embed=Embed.RandomEmbed(
                body=f"Your result is: **{choice}**",
            )
        )

    @random.command()
    async def number(self, ctx: Context, lower: int, upper: int):
        choice = random.randint(lower, upper)
        await ctx.send(
            embed=Embed.RandomEmbed(
                body=f"Your result is: **{choice}**",
            )
        )

    @random.command()
    async def help(self, ctx: Context):
        await ctx.send(
            embed=Embed.InfoEmbed(
                body="### Random Commands:\n"
                "- `!random choose <option 1> <option 2> <...>`: select one item from the list with equal probability.\n"
                "- `!random number <min> <max>`: select a number between min and max (both inclusive)."
            )
        )
