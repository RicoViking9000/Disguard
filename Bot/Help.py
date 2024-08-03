"""Cog that contains Discord help code."""

import textwrap

import discord
from discord.ext import commands

import Support
import utility

# =============================================================================


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis: dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis

    @commands.hybrid_command()
    async def help(self, ctx: commands.Context, *, command: str = None):
        """
        Get help with using Disguard's various features
        Parameters
        ----------
        command : str, optional
            (optional) The command or module to get help for
        """
        if command:
            embed = discord.Embed(
                title=f'Help with {command}',
                description=self.bot.get_command(command).help,
                color=utility.YELLOW[await utility.color_theme(ctx.guild) if ctx.guild else 1],
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title='Help with Disguard',
                description=textwrap.dedent("""
                For help with command usage, refer to the `Commands guide` linked below, or rerun this command while setting the `command` argument to what you're looking for.
                \nHave an issue or questions about the bot?
                • Join Disguard's server to chat with the development team
                • Open a support ticket with the button below
                """),
                color=utility.YELLOW[await utility.color_theme(ctx.guild) if ctx.guild else 1],
            )
            await ctx.send(embed=embed, view=self.HelpCommandView(self.bot, ctx))

    @help.autocomplete('command')
    async def help_autocomplete(self, interaction: discord.Interaction, argument: str):
        return [
            discord.app_commands.Choice(name=command.name, value=command.name)
            for command in self.bot.commands
            if argument.lower() in command.name or not argument
        ][:25]

    class HelpCommandView(discord.ui.View):
        def __init__(self, bot: commands.Bot, ctx: commands.Context):
            super().__init__()
            self.bot = bot
            self.ctx = ctx
            self.add_item(discord.ui.Button(label='Commands guide', style=discord.ButtonStyle.gray, url='https://disguard.netlify.app/commands'))
            self.add_item(discord.ui.Button(label='Support server', style=discord.ButtonStyle.gray, url='https://discord.gg/xSGujjz'))
            self.add_item(self.CreateTicketButton(ctx, bot))

        class CreateTicketButton(discord.ui.Button):
            def __init__(self, ctx: commands.Context, bot: commands.Bot):
                super().__init__(label='Create a support ticket', style=discord.ButtonStyle.gray, emoji='🎟')
                self.ctx = ctx
                self.bot = bot

            async def callback(self, interaction: discord.Interaction):
                support: Support.Support = self.bot.get_cog('Support')
                if support:
                    await interaction.response.send_modal(Support.SupportModal(self.ctx, self.bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
