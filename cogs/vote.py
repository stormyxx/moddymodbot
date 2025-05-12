from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Optional
import re

import attrs
import dateutil
import discord
import pytz
from attrs import define
from dateutil.parser import ParserError
from discord import Message, app_commands
from discord.ext import commands
from discord.ext.commands import Context, Cog

from constants import FR_TZ, TIME_FORMAT, OK_EMOJI, Phase
from db_client import get_db
from embeds import Embed
from exceptions import VoteError, ModBotError
from model import GameState, Player, GamePhase
from utils import send_error_and_delete, check_is_mod


@define
class VoteSnapshot:
    time_utc: datetime
    votes: Dict[str, List[str]]
    phase: GamePhase

    @classmethod
    def from_dict(cls, d):
        return cls(time_utc=pytz.utc.localize(d["time_utc"]), votes=d["votes"], phase=GamePhase(**d["phase"]))


class Vote(commands.Cog):
    def __init__(self, bot: commands.Bot, games: dict[int, GameState]):
        self.bot: commands.Bot = bot
        self.games: dict[int, GameState] = games
        self.enabled: bool = True
        self.votes: Dict[int, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        self.vote_history: Dict[int, List[VoteSnapshot]] = defaultdict(list)

        self.ctx_menu = app_commands.ContextMenu(
            name="Get Votecount",
            callback=self.get_votecount_menu,
        )
        self.bot.tree.add_command(self.ctx_menu)
        self.db = get_db()

    @commands.group()
    async def vote(self, ctx: Context):
        if not ctx.invoked_subcommand:
            raise ModBotError("Invalid command used! Use `!vote help` to see available commands.")

    @vote.command()
    @commands.check(check_is_mod)
    async def enable(self, ctx: Context):
        self.enabled = True
        await ctx.send(embed=Embed.SuccessEmbed(body="Voting is now enabled!"))

    @vote.command()
    @commands.check(check_is_mod)
    async def disable(self, ctx: Context):
        self.enabled = False
        await ctx.send(embed=Embed.SuccessEmbed(body="Voting is now disabled!"))

    @vote.command()
    @commands.check(check_is_mod)
    async def clear(self, ctx: Context):
        self.votes[ctx.guild.id] = defaultdict(list)
        await ctx.send(embed=Embed.SuccessEmbed(body="Votes cleared successfully!"))
        await self.on_vote(guild_id=ctx.guild.id, msg_time=ctx.message.created_at)

    @vote.command(aliases=["p"])
    async def player(self, ctx: Context, player: str = ""):
        voter = self.games[ctx.guild.id].player_from_id(discord_id=ctx.author.id)
        target = self.games[ctx.guild.id].player_from_fr(fr_name=player)
        self._check_vote(ctx, voter=voter, target=target, target_required=True)
        self._remove_vote(self.votes[ctx.guild.id], voter.fr_name)
        self.votes[ctx.guild.id][target.fr_name].append(voter.fr_name)
        await ctx.message.add_reaction(OK_EMOJI)
        await self.on_vote(guild_id=ctx.guild.id, msg_time=ctx.message.created_at)

    @vote.command()
    async def unvote(self, ctx: Context):
        voter = self.games[ctx.guild.id].player_from_id(discord_id=ctx.author.id)
        self._check_vote(ctx, voter=voter, target_required=False)
        self._remove_vote(self.votes[ctx.guild.id], voter.fr_name)
        await ctx.message.add_reaction(OK_EMOJI)
        await self.on_vote(guild_id=ctx.guild.id, msg_time=ctx.message.created_at)

    @vote.command()
    async def sleep(self, ctx: Context):
        voter = self.games[ctx.guild.id].player_from_id(discord_id=ctx.author.id)
        self._check_vote(ctx, voter=voter, target_required=False)
        if not self.games[ctx.guild.id].rules.sleep_enabled:
            raise ModBotError("Sleep / no elim is not an option in this game!")
        self._remove_vote(self.votes[ctx.guild.id], voter.fr_name)
        self.votes[ctx.guild.id]["Sleep / No Elim"].append(voter.fr_name)
        await ctx.message.add_reaction(OK_EMOJI)
        await self.on_vote(guild_id=ctx.guild.id, msg_time=ctx.message.created_at)

    @vote.command()
    @commands.check(check_is_mod)
    async def remove(self, ctx: Context, player: str):
        self._remove_vote(self.votes[ctx.guild.id], player)
        await ctx.send(embed=Embed.SuccessEmbed(body="Vote successfully removed!"))
        await self.on_vote(guild_id=ctx.guild.id, msg_time=ctx.message.created_at)

    @vote.command()
    async def count(self, ctx: Context, format_bbcode: str = ""):
        game = self.games[ctx.guild.id]
        if (
            not ctx.author.guild_permissions.administrator
            and ctx.channel.category.id not in game.config.vc_allowed_categories
        ):
            raise ModBotError("Vote count can only be done in game-related private channels (unless you are an admin)!")
        if format_bbcode.lower() == "bbcode":
            await ctx.send(
                f"```[b]Current Vote Count ({game.phase})[/b]: \n{self._compose_votecount(self.votes[ctx.guild.id], game.player_slot_map, format_bbcode=True)}```"
            )
        else:
            await ctx.send(
                embed=Embed.InfoEmbed(
                    body=f"## Current Vote Count ({game.phase}):\n{self._compose_votecount(self.votes[ctx.guild.id], game.player_slot_map)}"
                )
            )

    @vote.command()
    async def history(self, ctx: Context, *, msg_or_time: str = ""):
        if (
            not ctx.author.guild_permissions.administrator
            and ctx.channel.category.id not in self.games[ctx.guild.id].config.vc_allowed_categories
        ):
            raise ModBotError(
                "Vote history can only be done in game-related private channels (unless you are an admin)!"
            )
        format_bbcode = False
        if msg_or_time.endswith(" bbcode"):
            msg_or_time = msg_or_time.removesuffix(" bbcode")
            format_bbcode = True
        if msg_or_time.startswith("https://discord.com"):
            channel_pat = re.findall(r"https://discord.com/channels/(\d+)/(\d+)/(\d+)", msg_or_time)
            if not channel_pat:
                raise ModBotError(
                    "Invalid message link provided!\nTry double-checking that you linked the correct message."
                )
            guild_id, channel_id, msg_id = channel_pat[0]
            try:
                channel = ctx.bot.get_channel(int(channel_id))
                msg = await channel.fetch_message(int(msg_id))
            except Exception as e:
                await send_error_and_delete(
                    ctx.message,
                    error_msg=f"Something went wrong! Try double-checking that you linked the correct message.\n"
                    f"If this is not expected, report this with the following error message: \n"
                    f"**[{type(e)}]**: {str(e)}",
                    delay=30,
                )
                return
            msg_time = msg.created_at
        else:
            msg_time_frt = None
            for date_format in ["%B %d, %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                try:
                    msg_time_frt = datetime.strptime(msg_or_time, date_format)
                except ValueError:
                    pass
            if not msg_time_frt:
                try:
                    msg_time_frt = dateutil.parser.parse(msg_or_time)
                except ParserError:
                    await send_error_and_delete(
                        ctx.message,
                        f"You must provide a valid time (in FRT), or link a message to get the votecount as of that point!\n\n"
                        f"**Examples**:\n"
                        f"- !vote history January 01, 2024 00:30:00\n "
                        f"- !vote history 2024-01-01 00:30:00\n "
                        f"- !vote history https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{ctx.message.id}\n\n"
                        f'You can get a message link by clicking "More" on the message > "Copy Message Link".',
                        delay=30,
                    )
                    return
            msg_time_frt = FR_TZ.localize(msg_time_frt)
            msg_time = msg_time_frt.astimezone(pytz.utc)
        vote_snapshot = self.get_vote_snapshot(guild_id=ctx.guild.id, msg_time=msg_time)
        vote_count_hist = vote_snapshot.votes
        if format_bbcode:
            await ctx.send(
                "```"
                f"[b]Historical Vote Count ({vote_snapshot.phase}):[/b]\n"
                f"{self._compose_votecount(vote_count_hist, self.games[ctx.guild.id].player_slot_map, format_bbcode=True)}\n"
                f"[sup]vote count shown is as of {msg_time.astimezone(FR_TZ).strftime(TIME_FORMAT)}.[/sup]"
                f"```"
            )
        else:
            await ctx.send(
                embed=Embed.InfoEmbed(
                    body=f"## Historical Vote Count ({vote_snapshot.phase}):\n{self._compose_votecount(vote_count_hist, self.games[ctx.guild.id].player_slot_map)}",
                    footer=f"vote count shown is as of {msg_time.astimezone(FR_TZ).strftime(TIME_FORMAT)}.",
                )
            )

    @vote.command()
    @commands.check(check_is_mod)
    async def restore(self, ctx: Context):
        game_phase = GamePhase(Phase.DAY, num=1)
        self.votes[ctx.guild.id] = defaultdict(list)
        self.vote_history[ctx.guild.id] = [
            VoteSnapshot(time_utc=datetime(2020, 1, 1, tzinfo=pytz.utc), votes={}, phase=game_phase)
        ]
        vote_channel = ctx.guild.get_channel(self.games[ctx.guild.id].config.vote_channel)
        async for msg in vote_channel.history(oldest_first=True):
            if msg.content.startswith("!vote p"):
                voter = self.games[ctx.guild.id].player_from_id(discord_id=msg.author.id)
                target_fr = msg.content.removeprefix("!vote player ").removeprefix("!vote p ")
                target = self.games[ctx.guild.id].player_from_fr(fr_name=target_fr)
                self._remove_vote(self.votes[ctx.guild.id], voter.fr_name)
                self.votes[ctx.guild.id][target.fr_name].append(voter.fr_name)
                self.vote_history[ctx.guild.id].append(
                    VoteSnapshot(msg.created_at, deepcopy(self.votes[ctx.guild.id]), game_phase)
                )
            if msg.content.startswith("!phase next") and msg.author.guild_permissions.administrator:
                game_phase = game_phase.next()
                self.votes[ctx.guild.id] = defaultdict(list)
        await self.on_vote(ctx.guild.id, ctx.message.created_at)
        await self.count(ctx)

    async def get_votecount_menu(self, interaction: discord.Interaction, message: discord.Message):
        vote_snapshot = self.get_vote_snapshot(guild_id=interaction.guild_id, msg_time=message.created_at)
        await interaction.response.send_message(
            embed=Embed.InfoEmbed(
                body=f"## Historical Vote Count ({vote_snapshot.phase}):\n{self._compose_votecount(vote_snapshot.votes, self.games[interaction.guild_id].player_slot_map)}",
                footer=f"vote count shown is as of {message.created_at.astimezone(FR_TZ).strftime(TIME_FORMAT)}.",
            ),
            ephemeral=interaction.channel.category.id
            not in self.games[interaction.guild_id].config.vc_allowed_categories,
        )

    @vote.command()
    async def help(self, ctx: Context):
        await ctx.send(
            embed=Embed.InfoEmbed(
                body="## For mods:\n"
                "- `!vote enable`: enable voting\n"
                "- `!vote disable`: disable voting\n"
                "- `!vote clear`: clear all votes\n"
                "- `!vote remove <FR name>`: remove the vote of a specified player.\n"
                "## For players:\n"
                "- `!vote player <FR name>` or `!vote p <FR name>`: vote for a player with their FR username (case insensitive).\n"
                "- `!vote unvote`: retract your vote.\n"
                "- `!vote sleep`: vote to sleep / no elim.\n"
                "- `!vote count`: get the current vote count.\n"
                "- `!vote history <time in FRT>`: get the historical vote count as of the provided time.\n"
                "- `!vote history <link to discord message>`: get the historical vote count as of the provided message's send time.\n\n"
                '> P.S. You can add an extra argument "bbcode" to `!vote history` and `!vote count` to get vote count formatted with FR bbcode! (i.e. `!vote count bbcode`, `!vote history <time> bbcode`)\n'
                f"\n Voting is currently **{'en' if self.enabled else 'dis'}abled**.\n",
            )
        )

    @Cog.listener("on_message")
    async def warn(self, message: Message):
        if (
            message.channel.id == self.games[message.guild.id].config.vote_channel
            and not message.author.bot
            and not message.author.guild_permissions.administrator
        ):
            if not (message.author.bot or message.content.startswith("!vote ")):
                await send_error_and_delete(
                    message,
                    "Only `!vote` commands should be used in the voting channel!",
                )

    @Cog.listener("on_phase_change")
    async def on_phase_change(self, ctx: Context, old_phase: GamePhase, new_phase: GamePhase):
        if new_phase.phase == Phase.DAY:
            self.enabled = True
        if new_phase.phase == Phase.NIGHT:
            self.enabled = False
        embed = Embed.InfoEmbed(
            body=f"## {old_phase} Final Vote Count:\n{self._compose_votecount(self.votes[ctx.guild.id], player_slot_map=self.games[ctx.guild.id].player_slot_map)}",
            footer=f"It is now {new_phase}! Votes have been cleared and {'en' if self.enabled else 'dis'}abled.",
        )
        self.votes[ctx.guild.id] = defaultdict(list)
        await self.on_vote(guild_id=ctx.guild.id, msg_time=ctx.message.created_at)
        await ctx.send(embed=embed)

    @Cog.listener("on_phase_update")
    async def on_phase_update(self, ctx: Context):
        await self.on_vote(guild_id=ctx.guild.id, msg_time=ctx.message.created_at)

    @Cog.listener("on_ready")
    async def _setup(self):
        votes = self.db["votes"].find()
        async for vc in votes:
            guild_id = vc.pop("_id")
            self.votes[guild_id] = defaultdict(list, vc)
            await self._update_votecount(self.games[guild_id], guild_id)
        vote_histories = self.db["vote_history"].find()
        async for vh in vote_histories:
            guild_id = vh["_id"]
            self.vote_history[guild_id] = [VoteSnapshot.from_dict(h) for h in vh["history"]]

    @staticmethod
    def _remove_vote(votes: Dict[str, List[str]], voter: str):
        for target, voters in votes.items():
            if voter in voters:
                voters.remove(voter)

    def _check_vote(
        self,
        ctx: Context,
        voter: Player,
        target: Optional[Player] = None,
        target_required: bool = False,
    ):
        if not self.enabled:
            raise VoteError("Voting is currently disabled!")

        if ctx.channel.id != self.games[ctx.guild.id].config.vote_channel:
            raise VoteError(f"Votes can only be submitted in <#{self.games[ctx.guild.id].config.vote_channel}>!")

        if not voter or not voter.alive:
            raise VoteError("Only (alive) players are allowed to use this command!")

        if target_required and (not target or not target.alive):
            raise VoteError(f"The player you have selected is not a valid vote target!")

    async def _update_votecount(self, game: GameState, guild_id: int):
        vc_embed = Embed.InfoEmbed(
            body=f"## {game.phase} Vote Count:\n{self._compose_votecount(self.votes[guild_id], self.games[guild_id].player_slot_map)}",
            footer=f"last updated at {datetime.now(tz=FR_TZ).strftime(TIME_FORMAT)}",
        )
        vc_channel = self.bot.get_channel(game.config.vc_channel)
        vc_msg = None
        async for msg in vc_channel.history(oldest_first=True):
            if msg.author.id == self.bot.user.id:
                vc_msg = msg
                break
        if not vc_msg:
            await vc_channel.send(embed=vc_embed)
        else:
            await vc_msg.edit(embed=vc_embed)

    @staticmethod
    def _compose_votecount(
        votes: Dict[str, List[str]], player_slot_map: Dict[str, Player], format_bbcode: bool = False
    ) -> str:
        res = ""
        ordered_votes = []
        for target, voters in votes.items():
            ordered_votes.append((len(voters), target, voters))
        ordered_votes = sorted(ordered_votes, reverse=True)
        for count, target, voters in ordered_votes:
            if not voters:
                continue
            if format_bbcode:
                target = player_slot_map[target]._fr_name_bbcode if target != "Sleep / No Elim" else "Sleep / No Elim"
                voter_list = ", ".join(player_slot_map[voter]._fr_name_bbcode for voter in voters)
                res += f"[b]{target} ({count})[/b]: {voter_list}\n"
            else:
                res += f"**{target} ({count})**: {', '.join(voters)}\n"
        return res or "No votes yet!"

    def get_vote_snapshot(self, guild_id: int, msg_time: datetime):
        idx = 0
        vote_history = self.vote_history[guild_id]
        for vote_snapshot in vote_history:
            if vote_snapshot.time_utc > msg_time:
                break
            idx += 1
        if not vote_history or idx == 0:
            return VoteSnapshot(time_utc=msg_time, votes={}, phase=self.games[guild_id].phase)
        return vote_history[idx - 1]

    async def on_vote(self, guild_id: int, msg_time: datetime, update_votecount: bool = True):
        game = self.games[guild_id]
        self.vote_history[guild_id].append(VoteSnapshot(msg_time, deepcopy(self.votes[guild_id]), game.phase))
        if update_votecount:
            await self._update_votecount(game=game, guild_id=guild_id)
        await self.db["votes"].find_one_and_replace(
            {"_id": guild_id}, self.votes[guild_id] | {"_id": guild_id}, upsert=True
        )
        await self.db["vote_history"].find_one_and_replace(
            {"_id": guild_id},
            {"_id": guild_id, "history": [attrs.asdict(hist) for hist in self.vote_history[guild_id]]},
            upsert=True,
        )
