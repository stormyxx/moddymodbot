import random
from typing import Dict, List, Callable, Optional

import discord
from attr import define
from discord import PermissionOverwrite, app_commands
from discord.ext import commands
from discord.ext.commands import Context, Cog

from constants import Modifier, SideEffect
from embeds import Embed
from exceptions import ModBotError
from model import GameState, Player, Action, GamePhase
from utils import check_sensitive_info, check_is_mod, truncate_str


@define
class ActionSubmission:
    action: Action
    targets: List[Player]

    def format_targets(self) -> str:
        return ", ".join(target.fr_name for target in self.targets)


class Actions(commands.Cog):
    def __init__(self, bot: commands.Bot, game: GameState):
        self.bot = bot
        self.game = game
        self.action_submissions: Dict[str, ActionSubmission] = {}
        self.action_post: Optional[int] = None
        self.side_effect_map: Dict[SideEffect, Callable] = {SideEffect.PEW_PEW: self.pew}

    group = app_commands.Group(name="actions", description="...")

    @commands.group()
    async def actions(self, ctx: Context):
        if not ctx.invoked_subcommand:
            raise ModBotError(
                "Invalid command used! Use `!actions help` to see available commands.",
            )

    @actions.command()
    @commands.check(check_is_mod)
    async def list(self, ctx: Context, override_block=""):
        check_sensitive_info(ctx, self.game.players, override_block)
        await ctx.send(
            embed=Embed.InfoEmbed(
                title=f"{self.game.phase} Action Submissions",
                body=self.format_actions(self.game, self.action_submissions),
            )
        )

    @actions.command()
    @commands.check(check_is_mod)
    async def clear(self, ctx: Context):
        self.action_post = None
        self.action_submissions = {}
        await ctx.send(embed=Embed.SuccessEmbed(body="Actions cleared successfully!"))

    @actions.command()
    async def view(self, ctx: Context, fr_name="", override_block=""):
        if fr_name and not ctx.author.guild_permissions.administrator:
            raise ModBotError(
                "Only mods are allowed to use `!actions view <FR name>`!\n"
                "If you are a player, use `!actions view` to get your available actions."
            )
        if (
            ctx.channel.category.id != self.game.config.private_category
            and not ctx.author.guild_permissions.administrator
        ):
            raise ModBotError("`!actions view` can only be used in private channels!")
        target_player = self.game.player_from_id(ctx.author.id)
        if not target_player and not fr_name:
            raise ModBotError(
                "Only players can use `!actions view`!\n"
                "If you are a mod, use `!actions view <FR name>` to get the actions of a player."
            )
        elif not target_player and fr_name:
            target_player = self.game.player_from_fr(fr_name)
            if not target_player:
                raise ModBotError(f"{fr_name} is not a valid player!")
            check_sensitive_info(ctx, self.game.players, override_block=override_block, ignore=[target_player])
        if not target_player.role_card:
            raise ModBotError(f"{target_player} has no rolecard yet! Have you `!roles rand`ed yet?")

        available_actions_str = target_player.role_card.format_available_actions(self.game.phase.phase)
        curr_action = self.action_submissions.get(target_player.fr_name)
        if curr_action:
            curr_action_str = f"You are currently using **{curr_action.action.name}**{' on ' + curr_action.format_targets() if curr_action.targets else ''}."
        else:
            curr_action_str = ""
        embed = Embed.InfoEmbed(
            title=f"{target_player.fr_name}'s Actions",
            body=f"{available_actions_str}\n\n" f"It is now **{self.game.phase.phase}** phase." f"\n{curr_action_str}",
        )
        await ctx.send(embed=embed)

    @actions.command(aliases=["use", "sub"])
    async def submit(self, ctx: Context, action_name: str = "", *, targets: str = ""):
        player = self.game.player_from_id(ctx.author.id)
        if not player or not player.alive:
            raise ModBotError(f"Only (alive) players can submit actions!")
        if (
            ctx.channel.category.id != self.game.config.private_category
            or ctx.channel.name.lower() != player.fr_name.lower()
        ):
            raise ModBotError(f"You can only submit actions in your private channel!")
        if not action_name:
            raise ModBotError(f"An action must be provided!\n`!action submit <action> <targets>`")
        if not player.role_card:
            raise ModBotError(f"No rolecard found! Cannot submit actions :(\nHas the mod `!roles rand`ed yet?")
        action = player.role_card.get_action_from_name(action_name)
        if not action:
            raise ModBotError(
                f"Action '{action_name}' not found!\n Use `!actions view` to see the actions available to you."
            )
        if not action.can_use_in_phase(self.game.phase.phase):
            raise ModBotError(f"Action '{action_name}' cannot be used in {self.game.phase.phase} phase!")
        targets = targets.split()
        if len(targets) != action.targets:
            raise ModBotError(
                f"Action {action.name} requires {action.targets} targets, but only {len(targets)} were given!"
            )
        for target in targets:
            target_player = self.game.player_from_fr(target)
            if not target_player:
                raise ModBotError(
                    f"Action target '{target}' cannot be found! Please enter their FR name (case insensitive).\n"
                    f"Use `!player list` to see a list of players."
                )
            if not target_player.alive:
                raise ModBotError(
                    f"Action target '{target}' is not alive! You can only target alive players.\n"
                    f"Use `!player list` to see a list of players."
                )
            if target_player == player and not action.self_targetable:
                raise ModBotError(f"You cannot target yourself with this action!")
        action_sub = ActionSubmission(action=action, targets=[self.game.player_from_fr(target) for target in targets])
        if Modifier.LIGHTNING not in action.modifiers:
            self.action_submissions[player.fr_name] = action_sub
        await ctx.send(
            embed=Embed.SuccessEmbed(
                body=f"Action **{action.name}** submitted on target(s) {action_sub.format_targets()} for {self.game.phase}!"
            )
        )
        await self.on_submit(ctx, player=player, action_sub=action_sub)

    async def on_submit(self, ctx: Context, player: Player, action_sub: ActionSubmission):
        action, targets = action_sub.action, action_sub.targets
        if action.side_effect:
            for side_eff in action.side_effect:
                side_eff_callable = self.side_effect_map.get(side_eff)
                if side_eff_callable:
                    await side_eff_callable(ctx, player=player, action_sub=action_sub)
        actions_channel = await self.get_create_actions_channel(ctx)
        if Modifier.LIGHTNING in action.modifiers:
            await actions_channel.send(
                embed=Embed.InfoEmbed(
                    title="Lightning Action!",
                    body=f"**{player}** has used **{action.name}**{(' on ' + action_sub.format_targets()) if targets else ''}!",
                )
            )
            self.deplete_action_shots(action, player.actions)
        else:
            embed = Embed.InfoEmbed(
                title=f"{self.game.phase} Action Submissions",
                body=self.format_actions(self.game, self.action_submissions),
            )
            if not self.action_post:
                msg = await actions_channel.send(embed=embed)
                self.action_post = msg.id
            else:
                msg = await actions_channel.fetch_message(self.action_post)
                await msg.edit(embed=embed)

    async def pew(self, ctx: Context, player: Player, action_sub: ActionSubmission):
        target = action_sub.targets[0]
        announce_channel = await self.get_create_announce_channel(ctx)
        reveals_shooter = bool(random.randint(0, 1))
        await announce_channel.send(
            embed=Embed.LightningEmbed(
                title="A shot rings out!",
                body=f"{player if reveals_shooter else 'A player'} pew-pews {target}!\n"
                f"{target} was **{target.flips_as}**.",
            )
        )
        target.alive = False

    @staticmethod
    def format_actions(game: GameState, actions: Dict[str, ActionSubmission]) -> str:
        body = ""
        for fr_name, action in actions.items():
            player = game.player_from_fr(fr_name)
            body += f"{player} uses **{action.action.name}**{' on ' + action.format_targets()}\n"
        return body

    @staticmethod
    def deplete_action_shots(action: Action, actions: List[Action]) -> None:
        if action.shots is None:
            return
        action.shots -= 1
        if action.shots == 0:
            actions.remove(action)

    async def get_create_announce_channel(self, ctx: Context):
        announce_channel = self.bot.get_channel(self.game.config.announce_channel)
        if not announce_channel:
            perm_overwrites = {ctx.guild.default_role: PermissionOverwrite(send_messages=False)}
            announce_channel = await ctx.guild.create_text_channel(name="announcements", overwrites=perm_overwrites)
            self.game.config.announce_channel = announce_channel.id
        return announce_channel

    async def get_create_actions_channel(self, ctx: Context):
        actions_channel = self.bot.get_channel(self.game.config.actions_channel)
        if not actions_channel:
            perm_overwrites = {ctx.guild.default_role: PermissionOverwrite(read_messages=False)}
            actions_channel = await ctx.guild.create_text_channel(name="action-submissions", overwrites=perm_overwrites)
            self.game.config.actions_channel = actions_channel.id
        return actions_channel

    @Cog.listener("on_phase_change")
    async def on_phase_change(self, ctx: Context, old_phase: GamePhase, new_phase: GamePhase):
        for fr_name, action in self.action_submissions.items():
            player = self.game.player_from_fr(fr_name)
            self.deplete_action_shots(action.action, player.actions)
        self.action_post = None
        self.action_submissions = {}

    @actions.command()
    async def help(self, ctx: Context):
        await ctx.send(
            embed=Embed.InfoEmbed(
                body="### For mods:\n"
                "- `!actions view <FR name>`: see the actions available to a player in the current phase.\n"
                "- `!actions list`: see all actions submitted in the current phase.\n"
                "- `!actions clear`: clear all actions submitted for the current phase.\n"
                "### For players:\n"
                "- `!actions view`: see the actions available to you in the current phase.\n"
                "- `!actions submit <action name> <target(s)>` or `!actions use <action name> <target(s)>`: submit action.\n"
            )
        )

    @group.command(name="submit", description="Submit an action.")
    async def slash_submit(
        self, interaction: discord.Interaction, action: str, target: str, target_2: Optional[str]
    ) -> None:
        ctx = await self.bot.get_context(interaction)
        targets = f" ".join(target for target in [target, target_2] if target)
        try:
            await self.submit(ctx, action_name=action, targets=targets)
        except ModBotError as e:
            await interaction.response.send_message(embed=Embed.ErrorEmbed(body=f"{e.msg}"), ephemeral=True)

    @slash_submit.autocomplete("action")
    async def _get_action_options(self, interaction: discord.Interaction, current: str):
        player = self.game.player_from_id(interaction.user.id)
        if not (player and player.role_card):
            return [app_commands.Choice(name=f"No rolecard found :(", value="invalid action")]
        available_actions = player.role_card.get_available_actions(self.game.phase.phase)
        if not available_actions:
            return [app_commands.Choice(name=f"No available abilities this phase :(", value="invalid action")]
        return [
            app_commands.Choice(name=truncate_str(f"{action.name} - {action.desc}"), value=action.name)
            for action in available_actions
        ]

    @slash_submit.autocomplete("target")
    @slash_submit.autocomplete("target_2")
    async def _get_target_options(self, interaction: discord.Interaction, current: str):
        player = self.game.player_from_id(interaction.user.id)
        if not (player and player.role_card):
            return [app_commands.Choice(name="No rolecard found :(", value="invalid target")]
        excluded_players = set()
        if not player.role_card.get_action_from_name(interaction.namespace.action).self_targetable:
            excluded_players.add(player.fr_name)
        return [
            app_commands.Choice(name=player.fr_name, value=player.fr_name)
            for player in self.game.players
            if player.alive and player.fr_name not in excluded_players
        ]
