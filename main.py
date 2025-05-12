import os
from collections import defaultdict

import discord
import yaml
from discord.ext import commands
from discord.ext.commands import Context, errors

from cogs.actions import Actions
from cogs.phase import Phases
from cogs.player import Players
from cogs.rand import Random
from cogs.roles import Roles
from cogs.vote import Vote
from cogs.help import Help
from db_client import DBClient
from exceptions import ModBotError
from model import GameState, Config, Rules, Player, RoleCard
from utils import send_error_and_delete


class ModBot(commands.Bot):

    async def setup_hook(self) -> None:
        print(f"Logged in as: {self.user}")
        await self.add_cog(phase)
        await self.add_cog(player)
        # await self.add_cog(roles)
        await self.add_cog(vote)
        # await self.add_cog(actions)
        await self.add_cog(random)
        # await self.add_cog(help)
        await self.tree.sync()

    async def on_command_error(self, context: Context, exception: errors.CommandError, /) -> None:
        if isinstance(exception, errors.CommandInvokeError) and isinstance(exception.original, ModBotError):
            await send_error_and_delete(context.message, exception.original.msg)
        elif isinstance(exception, errors.CheckFailure):
            await send_error_and_delete(context.message, "Only mods can use this command!")
        else:
            raise exception


with open("config.yaml", "r") as stream:
    config = yaml.safe_load(stream)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = ModBot(
    command_prefix="!",
    intents=intents,
    activity=discord.Game("mafia >:)"),  # Use !help if stuck!"),
)
gamestates = defaultdict(lambda: GameState())
gamestates[config["guild_id"]] = GameState(
    config=Config(**config["server_config"]),
    players=([Player.from_dict(p) for p in config.get("players", [])]),
    rules=Rules(**config.get("rules", {})),
    roles=[RoleCard.from_dict(rc) for rc in config.get("roles", [])] or None,
)


phase = Phases(bot=bot, games=gamestates)
player = Players(bot=bot, games=gamestates)
# roles = Roles(bot=bot, games=gamestates)
vote = Vote(bot=bot, games=gamestates)
# actions = Actions(bot=bot, games=gamestates)
random = Random()
# help = Help(phase=phase, player=player, roles=roles, vote=vote, actions=actions, random=random)

bot.remove_command("help")
token = os.environ["TOKEN"]
bot.run(token)
