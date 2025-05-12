import random
from copy import deepcopy
from typing import Optional

import discord.utils
from discord import TextChannel
from discord.ext import commands
from discord.ext.commands import Context, Cog

from embeds import Embed
from exceptions import ModBotError
from model import GameState
from utils import check_is_mod


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot, game: GameState):
        self.bot = bot
        self.game = game

    @commands.group()
    async def roles(self, ctx: Context):
        if not ctx.invoked_subcommand:
            raise ModBotError("Invalid command used! Use `!roles help` to see available commands.")

    @roles.command()
    async def list(self, ctx: Context):
        if not self.game.rules.open_setup and not ctx.author.guild_permissions.administrator:
            raise ModBotError("This game is closed-setup; only mods can use this command!")
        if not self.game.roles:
            await ctx.send(embed=Embed.ErrorEmbed(body="No roles found!"))
        await ctx.send(embeds=[role.get_rolecard() for role in self.game.roles])

    @roles.command()
    @commands.check(check_is_mod)
    async def rand(self, ctx: Context, dry_run: str = ""):
        if len(self.game.roles) != len(self.game.players):
            raise ModBotError(
                f"The number of players ({len(self.game.players)}) and the number of roles ({len(self.game.roles)}) must be equal!"
            )

        rolecards = []
        rand_sequence = list(range(len(self.game.players)))
        random.shuffle(rand_sequence)
        for role, player_idx in zip(self.game.roles, rand_sequence):
            target_player = self.game.players[player_idx]
            target_player.alive = True
            target_player.role_card = deepcopy(role)
            rolecards.append(role.get_rolecard(fr_name=target_player.fr_name))
        await ctx.send(embeds=rolecards)
        if dry_run != "dry_run":
            await self.send(ctx)

    @roles.command()
    @commands.check(check_is_mod)
    async def send(self, ctx: Context):
        failed_players = []
        for player in self.game.players:
            player_channel = self.find_player_channel(ctx, name=player.fr_name.lower()) or self.find_player_channel(
                ctx, name=player.fr_name
            )
            if not player_channel:
                failed_players.append(player.fr_name)
                continue
            rc_msg = await player_channel.send(embed=player.role_card.get_rolecard(fr_name=player.fr_name))
            await rc_msg.pin()
        if failed_players:
            await ctx.send(
                embed=Embed.ErrorEmbed(
                    body=f"Failed to send rolecards for player(s) {', '.join(failed_players)} because their private channel(s) cannot be found :(\n\n"
                    f"If you have a channel already created, check:\n"
                    f"- is it under the private category?\n"
                    f'- is it private channel (is "read messages" for everyone off)>\n'
                    f"- is the channel name spelt correctly?"
                )
            )
        else:
            await ctx.send(embed=Embed.SuccessEmbed(body=f"All rolecards sent!"))
        return

    def find_player_channel(self, ctx: Context, name: str) -> Optional[TextChannel]:
        private_category = discord.utils.get(ctx.guild.categories, id=self.game.config.private_category)
        if not private_category:
            return None
        player_channel = discord.utils.get(private_category.channels, name=name)
        if player_channel and not player_channel.overwrites[ctx.guild.default_role].read_messages:
            return player_channel
        return None

    @roles.command()
    async def help(self, ctx: Context):
        await ctx.send(
            embed=Embed.InfoEmbed(
                body="### For mods:\n"
                "- `!roles list`: show all rolecards for this game (without player names).\n"
                "- `!roles rand`: randomly assign players to the roles in the setup & sends out rolecards.\n\n"
                "**P.S.** If you want to rand the roles without sending them out (i.e. if you want to check them first), do `!roles rand dry_run`. \n"
                "You can later use `!roles send` seperately to send rolecards out."
            )
        )
