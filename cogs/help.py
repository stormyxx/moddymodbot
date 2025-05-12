from discord.ext import commands
from discord.ext.commands import Context

from cogs.actions import Actions
from cogs.phase import Phases
from cogs.rand import Random
from cogs.roles import Roles
from cogs.vote import Vote
from cogs.player import Players
from embeds import Embed


class Help(commands.Cog):
    def __init__(self, phase: Phases, player: Players, roles: Roles, vote: Vote, actions: Actions, random: Random):
        self.phase = phase
        self.player = player
        self.roles = roles
        self.vote = vote
        self.actions = actions
        self.random = random

    @commands.group()
    async def help(self, ctx: Context):
        if not ctx.invoked_subcommand:
            await ctx.send(
                embed=Embed.InfoEmbed(
                    title="Moddy Modbot Supported Modules",
                    body="- **player**: (for mods) deals with matters with the playerlist.\n"
                    "- **roles**: (for mods) deal with matters of rolecards & role assignments.\n"
                    "- **phase**: (for mods) modify / switch game phases.\n"
                    "- **vote**: cast votes and query votecounts.\n"
                    "- **actions**: submit game actions.\n"
                    "- **random**: ask the bot to randomize things for you.\n"
                    "use `!<module name> help` (i.e. `!vote help`) for a list of commands for that module.",
                )
            )

    @help.command()
    async def player(self, ctx: Context):
        await self.player.help(ctx)

    @help.command()
    async def roles(self, ctx: Context):
        await self.roles.help(ctx)

    @help.command()
    async def phase(self, ctx: Context):
        await self.phase.help(ctx)

    @help.command()
    async def vote(self, ctx: Context):
        await self.vote.help(ctx)

    @help.command()
    async def actions(self, ctx: Context):
        await self.actions.help(ctx)

    @help.command()
    async def random(self, ctx: Context):
        await self.random.help(ctx)