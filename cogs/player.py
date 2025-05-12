import re
from typing import Dict

import attrs
from discord import PermissionOverwrite
from discord.ext import commands
from discord.ext.commands import Context, Cog
from discord.ext.commands._types import BotT
from discord.utils import get

from db_client import get_db
from embeds import Embed
from exceptions import ModBotError
from model import GameState, Player as _Player, Player, Role, RoleCard
from utils import check_sensitive_info, check_is_mod


class Players(commands.Cog):
    def __init__(self, bot: commands.Bot, games: Dict[int, GameState]):
        self.bot = bot
        self.games = games
        self.create_channels = False
        self.db = get_db()

    @commands.group(invoke_without_command=True)
    async def player(self, ctx: Context):
        if not ctx.invoked_subcommand:
            raise ModBotError("Invalid command used! Use `!player help` to see available commands.")

    @player.command()
    @commands.check(check_is_mod)
    async def channel_create(self, ctx: Context, enable: str = ""):
        if enable.lower() == "enable":
            self.create_channels = True
            await ctx.send(embed=Embed.SuccessEmbed(body="Adding new players will now create new private channels!"))
        elif enable.lower() == "disable":
            self.create_channels = False
            await ctx.send(
                embed=Embed.SuccessEmbed(body="Adding new players will no longer create new private channels!")
            )
        else:
            raise ModBotError("Invalid command used! Use `!player help` to see available commands.")

    @player.command()
    async def list(self, ctx: Context):
        alive_players = ""
        dead_players = ""
        for player in self.games[ctx.guild.id].players:
            player_str = f"{player} (<@{player.discord_id}>)\n"
            if player.alive:
                alive_players += player_str
            else:
                dead_players += player_str
        await ctx.send(
            embed=Embed.InfoEmbed(
                title="Players",
                body=f"**Alive Players**:\n{alive_players or 'Everyone is dead >:)'}\n"
                f"**Dead Players**:\n{dead_players or 'Everyone is alive!'}",
            )
        )

    @player.command()
    @commands.check(check_is_mod)
    async def info(self, ctx: Context, fr_name: str = "", override_block: str = ""):
        game = self.games[ctx.guild.id]
        check_sensitive_info(ctx, players=game.players, override_block=override_block)
        if fr_name != "all":
            if not fr_name:
                raise ModBotError("Invalid command!\nUse `!player info <FR name>` or `!player info all`")
            player = game.player_from_fr(fr_name, raise_err=True)
            await ctx.send(embed=player.get_embed())
        else:
            await ctx.send(embeds=[player.get_embed() for player in game.players])

    @player.command()
    @commands.check(check_is_mod)
    async def rolecard(self, ctx: Context, fr_name: str = "", override_block: str = ""):
        game = self.games[ctx.guild.id]
        if not fr_name:
            raise ModBotError(f"Please provide a player name!\ni.e. `!player rolecard <FR name>`")

        query_player = game.player_from_fr(fr_name, raise_err=True)
        if not query_player.role_card:
            raise ModBotError(f"Player {fr_name} does not have a rolecard!")
        if query_player.alive:
            check_sensitive_info(ctx, players=game.players, override_block=override_block, ignore=[query_player])
        await ctx.send(embed=query_player.role_card.get_rolecard(fr_name=query_player.fr_name))

    @player.command()
    @commands.check(check_is_mod)
    async def add(self, ctx: Context, fr_name: str = "", mention: str = ""):
        game = self.games[ctx.guild.id]
        if not (fr_name.isalnum() and re.match(r"<@(\d{17,19})>", mention)):
            raise ModBotError(
                f"Invalid player information detected! Add a player with: \n"
                "`!player add <FR username> <discord mention>`\n\n"
                "(i.e. !player add Stormdreamer <@230331585432387584>)",
            )
        discord_id = int(mention.strip("<@>"))
        self.check_player_stats(fr_name=fr_name, discord_id=discord_id, guild_id=ctx.guild.id)
        new_player = _Player(fr_name=fr_name, discord_id=discord_id)
        game.players.append(new_player)
        game.player_slot_map[fr_name] = new_player
        if self.create_channels:
            await self._create_player_channel(ctx=ctx, player=new_player)
        await self.list(ctx)

    @player.command()
    @commands.check(check_is_mod)
    async def sub(self, ctx: Context, old_player: str = "", new_player: str = "", new_ping: str = ""):
        game = self.games[ctx.guild.id]
        if not (old_player.isalnum() and new_player.isalnum() and re.match(r"<@(\d{17,19})>", new_ping)):
            raise ModBotError(
                f"Invalid player information detected! Sub out a player with: \n"
                "`!player sub <player FR username> <sub FR username> <discord mention>`\n\n"
                "(i.e. !player sub DromSteammer Stormdreamer <@230331585432387584>)",
            )
        player_slot = game.player_from_fr(old_player)
        if not player_slot:
            raise ModBotError(f"Cannot find player '{old_player}' to sub out; make sure the name is correct!")
        discord_id = int(new_ping.strip("<@>"))
        self.check_player_stats(fr_name=new_player, discord_id=discord_id, guild_id=ctx.guild.id)
        player_slot.fr_name = new_player
        player_slot.discord_id = discord_id
        game.player_slot_map[new_player] = player_slot
        if self.create_channels:
            await self._create_player_channel(ctx=ctx, player=player_slot)
        await self.list(ctx)

    @player.command()
    @commands.check(check_is_mod)
    async def set(self, ctx: Context, fr_name: str = "", attr: str = "", val: str = ""):
        game = self.games[ctx.guild.id]
        player = game.player_from_fr(fr_name, raise_err=True)
        if attr == "alive":
            player.alive = True if val.lower() == "true" else False
            await ctx.send(embed=player.get_embed())
        if attr == "flips_as":
            if not player.role_card:
                player.role_card = RoleCard()
            player.role_card.flips_as = Role.from_str(val)
            await ctx.send(embed=player.get_embed())

    @player.command()
    @commands.check(check_is_mod)
    async def kill(self, ctx: Context, fr_name: str = ""):
        game = self.games[ctx.guild.id]
        if not fr_name:
            raise ModBotError(f"A player name must be specified!\ni.e. `!player kill <FR name>")
        player = game.player_from_fr(fr_name, raise_err=True)
        player.alive = False
        await ctx.send(embed=player.get_embed())

    @player.command()
    @commands.check(check_is_mod)
    async def delete(self, ctx: Context, fr_name: str = ""):
        game = self.games[ctx.guild.id]
        if not fr_name:
            raise ModBotError("A player name must be specified!\ni.e. `!player delete <FR name>")
        player = game.player_from_fr(fr_name, raise_err=True)
        game.players.remove(player)
        await self.list(ctx)

    @player.command()
    async def vote(self, ctx: Context):
        raise ModBotError("Did you mean to use `!vote player <FR name>` instead?")

    async def _create_player_channel(self, ctx: Context, player: _Player):
        game = self.games[ctx.guild.id]
        priv_category = get(ctx.guild.categories, id=game.config.private_category)
        perm_overwrites = {
            ctx.guild.default_role: PermissionOverwrite(read_messages=False),
            ctx.guild.get_member(player.discord_id): PermissionOverwrite(read_messages=True),
        }
        player_channel = await ctx.guild.create_text_channel(
            name=player.fr_name.lower(), category=priv_category, overwrites=perm_overwrites
        )
        welcome_msg = await player_channel.send(
            f"Welcome to your personal channel, **{player}**!\n"
            f"Here, you can ask the mod questions, submit your actions, request votecounts, and keep your notes about the game!\n\n"
            f"To request votecounts:\n"
            f"- `!vote count`: get current vote count\n"
            f"- `!vote history <time in FRT>` or `!vote history <link to message>`: get historical vote count at a certain point in time.\n"
            f'  - to get the results formatted in bbcode, add "bbcode" at the end of the command (i.e. `!vote count bbcode`)\n'
            f"To submit actions:\n"
            f"- `!actions view`: see the abilities availalble to you this phase\n"
            f"- `!actions submit <action name> <action targets>`: see the abilities availalble to you this phase\n\n"
            f"Please **do not** screenshot or copy & paste host communication and/or modbot results anywhere else, except bbcode generated from modbot's votecount feature. Good luck! :)"
        )
        await welcome_msg.pin()

    def check_player_stats(self, fr_name: str, discord_id: int, guild_id: int):
        game = self.games[guild_id]
        if game.player_from_fr(fr_name):
            raise ModBotError(f"{fr_name} has already been added as a player!")
        if game.player_from_id(discord_id):
            raise ModBotError(f"<@{discord_id}> has already been added as a player!")

    async def cog_after_invoke(self, ctx: Context[BotT]) -> None:
        player_dict = {
            "players": [attrs.asdict(player) for player in self.games[ctx.guild.id].players],
            "_id": ctx.guild.id,
        }
        await self.db["players"].find_one_and_replace(
            filter={"_id": ctx.guild.id}, replacement=player_dict, upsert=True
        )
        player_slots_dict = {
            name: attrs.asdict(player) for name, player in self.games[ctx.guild.id].player_slot_map.items()
        }
        player_slots_dict["_id"] = ctx.guild.id
        await self.db["player_slots"].find_one_and_replace(
            filter={"_id": ctx.guild.id}, replacement=player_slots_dict, upsert=True
        )

    @Cog.listener("on_ready")
    async def _setup(self):
        plists = self.db["players"].find()
        async for plist in plists:
            guild_id = plist["_id"]
            players = [Player.from_dict(d) for d in plist["players"]]
            self.games[guild_id].players = self.games[guild_id].players or players
        pslotmaps = self.db["player_slots"].find()
        async for pslotmap in pslotmaps:
            guild_id = pslotmap.pop("_id")
            self.games[guild_id].player_slot_map = {
                name: self.games[guild_id].player_from_fr(player["fr_name"]) for name, player in pslotmap.items()
            }

    @player.command()
    async def help(self, ctx: Context):
        await ctx.send(
            embed=Embed.InfoEmbed(
                body="## For mods:\n"
                "- `!player add <FR username> <@mention>`: add player to the game\n"
                "- `!player sub <player FR username> <sub FR username> <discord mention>`: sub out a player\n"
                "- `!player set <FR username> <attribute> <value>`: modify a player's game information\n"
                "- `!player kill <FR username>`: kill a player (sets alive = False).\n"
                "- `!player delete <FR username>`: remove a player from the playerlist entirely.\n"
                "- `!player rolecard <FR username>`: get a player's rolecard\n"
                "- `!player info <FR username>`: get a player's game information\n"
                "- `!player info all`: get all player's game information\n"
                "- `!player channel_create <enable|disable>`: enable / disable channel creation when players are added\n"
                "## For players:\n"
                "- `!player list`: get list of players\n"
            )
        )
