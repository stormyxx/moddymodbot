from typing import List

from discord import Message
from discord.ext.commands import Context

from embeds import Embed
from exceptions import ModBotError
from model import Player


async def send_error_and_delete(message: Message, error_msg: str, delay: int = 10):
    await message.delete(delay=delay)
    await message.reply(
        embed=Embed.ErrorEmbed(body=error_msg, footer=f"This message will be deleted in {delay} seconds."),
        delete_after=delay,
        mention_author=False,
    )


def check_sensitive_info(ctx: Context, players: List[Player], override_block: str, ignore: List[Player] = None):
    ignore_ids = {player.discord_id for player in ignore} if ignore else set()
    channel_members = {member.id for member in ctx.channel.members if member.id not in ignore_ids}
    if override_block != "override" and any(player.discord_id in channel_members for player in players if player.alive):
        raise ModBotError(
            "Player info contains sensitive information (and there are alive players that can see this chat)!\n"
            f"Display it anyway? Try: `{ctx.message.content} override`",
        )


def check_is_mod(ctx: Context):
    return ctx.author.guild_permissions.administrator


def truncate_str(s: str, n: int = 60) -> str:
    s = s.replace("\n", "")
    return f"{s[:n]}..." if len(s) > n else s
