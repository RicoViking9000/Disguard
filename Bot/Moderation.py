import asyncio
import collections
import copy
import datetime
import re
import traceback
import typing
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import Cyberlog  # Used to prevent delete logs upon purging
import database
import lightningdb
import utility

filters = {}
loading = None
NEWLINE = '\n'
qlf = '  '

blue = (0x0000FF, 0x6666FF)
orange = (0xD2691E, 0xFFC966)
units = {'s': 'second', 'm': 'minute', 'h': 'hour', 'd': 'day', 'w': 'week', 'mo': 'month', 'y': 'year'}


class PurgeObject(object):
    def __init__(
        self,
        message=None,
        botMessage=None,
        limit=100,
        author=[],
        contains=None,
        startsWith=None,
        endsWith=None,
        links=None,
        invites=None,
        images=None,
        embeds=None,
        mentions=None,
        bots=None,
        channel=[],
        files=None,
        reactions=None,
        appMessages=None,
        startDate=None,
        endDate=None,
        caseSensitive=False,
        cleanup=False,
        anyMatch=False,
    ):
        self.message = message
        self.botMessage = botMessage
        self.limit = limit
        self.author = author
        self.contains = contains
        self.startsWith = startsWith
        self.endsWith = endsWith
        self.links = links
        self.invites = invites
        self.images = images
        self.embeds = embeds
        self.mentions = mentions
        self.bots = bots
        self.channel = channel
        self.files = files
        self.reactions = reactions
        self.appMessages = appMessages
        self.startDate = startDate
        self.endDate = endDate
        self.caseSensitive = caseSensitive
        self.cleanup = cleanup  # delete user's message after?
        self.anyMatch = anyMatch  # if true, purge if it matches any filter, else, purge if it matches all filters
        self.purgeCount = 0
        self.purgeStat = {0: 0, 1: 0, 2: 0}
        self.lastUpdate = None


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis = self.bot.get_cog('Cyberlog').emojis
        self.roleCache = {}
        self.permissionsCache = {}

        # context menus
        self.bot.tree.add_command(app_commands.ContextMenu(name='Toggle Channel Lockout', callback=self.context_lock))

    @commands.hybrid_group(fallback='moderation_command_info')
    async def bulk(self, ctx: commands.Context):
        """
        Bulk moderation commands
        """
        pass

    @commands.hybrid_command(description='Sets the duration members must remain in the server before being able to chat')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def warmup(self, ctx: commands.Context, duration: str):
        """
        Set the duration members must wait in the server before being able to chat
        --------------------------------
        Parameters:
        duration: str
            The duration of time members must wait before being able to chat
        """
        duration, int_arg, unit = utility.ParseDuration(duration)
        await database.SetWarmup(ctx.guild, duration)
        embed = discord.Embed(
            title='Warmup',
            description=f'Updated server antispam policy: Members must be in the server for **{int_arg} {unit}** before chatting',
            color=orange[await utility.color_theme(ctx.guild)],
        )
        view = WarmupActionView(self.bot)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, member: discord.Member, reason: Optional[str] = ''):
        """
        Locks out the specified member, preventing them from accessing any channels
        --------------------------------
        Parameters:
        member: discord.Member
            The member to lock out
        reason: str, optional
            The reason for locking out the member
        """
        await ctx.send(await self.lock_handler(ctx, member, reason))

    async def context_lock(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(thinking=True)
        channels_to_check = [
            channel for channel in interaction.guild.channels if channel.type in [discord.ChannelType.text, discord.ChannelType.voice]
        ]
        channels_locked_out = []
        for channel in channels_to_check:
            if channel.type == discord.ChannelType.text:
                if not channel.permissions_for(member).read_messages:
                    channels_locked_out.append(channel)
            elif channel.type == discord.ChannelType.voice:
                if not channel.permissions_for(member).connect:
                    channels_locked_out.append(channel)
        if channels_locked_out / channels_to_check > 0.5:
            # unlock
            return await interaction.response.send_message(await self.unlock_handler(interaction, member))
        else:
            # lockout
            return await interaction.response.send_message(await self.lock_handler(interaction, member))

    async def lock_handler(self, ctx: commands.Context | discord.Interaction, member: discord.Member, reason: Optional[str] = ''):
        messages = []
        for c in ctx.guild.channels:
            try:
                if c.type[0] == discord.ChannelType.text:
                    await c.set_permissions(member, read_messages=False, reason=audit_log_reason(ctx.author, reason))
                elif c.type[0] == discord.ChannelType.voice:
                    await c.set_permissions(member, connect=False, reason=audit_log_reason(ctx.author, reason))
            except (discord.Forbidden, discord.HTTPException) as e:
                messages.append(f'Error editing channel permission overwrites for {c.name}: {e.text}')
        if len(reason) > 0:
            try:
                await member.send(
                    f'[Moderation: lockout] A moderator has restricted you from accessing channels in {ctx.guild.name}{f" because {reason}" if len(reason) > 0 else ""}.'
                )
            except (discord.Forbidden, discord.HTTPException) as e:
                messages.append(f'Error DMing {member.display_name}: {e.text}')
        return f'{member.display_name} is now locked and cannot access any server channels{f" because {reason}" if len(reason) > 0 else ""}\n' + (
            f'Notes: {NEWLINE.join(messages)}' if messages else ''
        )

    @bulk.command(name='lock')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def bulk_lock(
        self,
        ctx: commands.Context,
        member: discord.Member,
        member2: Optional[discord.Member] = None,
        member3: Optional[discord.Member] = None,
        member4: Optional[discord.Member] = None,
        member5: Optional[discord.Member] = None,
        member6: Optional[discord.Member] = None,
        member7: Optional[discord.Member] = None,
        member8: Optional[discord.Member] = None,
        member9: Optional[discord.Member] = None,
        member10: Optional[discord.Member] = None,
        reason: Optional[str] = '',
    ):
        """
        Locks out the specified members, preventing them from accessing any channels
        --------------------------------
        Parameters:
        member: discord.Member
            The member to lock out
        reason: str, optional
            The reason for locking out the members
        """
        await ctx.interaction.response.defer(thinking=True)
        members = list(filter(lambda m: m, [member, member2, member3, member4, member5, member6, member7, member8, member9, member10]))
        messages = []
        successful = []
        for member in members:
            for c in ctx.guild.channels:
                try:
                    if c.type[0] == 'text':
                        await c.set_permissions(member, read_messages=False, reason=audit_log_reason(ctx.author, reason))
                    elif c.type[0] == 'voice':
                        await c.set_permissions(member, connect=False, reason=audit_log_reason(ctx.author, reason))
                    successful.append(member)
                except (discord.Forbidden, discord.HTTPException) as e:
                    messages.append(f'Error editing channel permission overwrites for {c.name}: {e.text}')
            if len(reason) > 0:
                try:
                    await member.send(
                        f'You have been restricted from accessing channels in {ctx.guild.name}{f" because {reason}" if len(reason) > 0 else ""}'
                    )
                except (discord.Forbidden, discord.HTTPException, AttributeError) as e:
                    messages.append(f'Error DMing {member.display_name}: {e.text}')
        await ctx.send(
            content=f'{len(successful)} members [{[", ".join([str(member) for member in successful])]}] are now locked and cannot access any server channels{f" because {reason}" if len(reason) > 0 else ""}\n'
            + (f'Notes: {NEWLINE.join(messages)}' if messages else '')
        )

    @commands.hybrid_command(description='Unlocks the specified member: allows them to access all channels again')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, member: discord.Member, reason: Optional[str] = ''):
        """
        Unlocks the specified member: allows them to access all channels again
        --------------------------------
        Parameters:
        member: discord.Member
            The member to unlock
        reason: str, optional
            The reason for unlocking the member
        """
        await ctx.interaction.response.defer(thinking=True)
        await ctx.send(await self.unlock_handler(ctx, member, reason))

    async def unlock_handler(self, ctx: commands.Context | discord.Interaction, member: discord.Member, reason: Optional[str] = ''):
        for c in ctx.guild.channels:
            await c.set_permissions(member, overwrite=None, reason=audit_log_reason(ctx.author, reason))
        errorMessage = None
        try:
            await member.send(f'You may now access channels again in {ctx.guild.name}')
        except (discord.Forbidden, discord.HTTPException) as e:
            errorMessage = f'Unable to notify {member.display_name} by DM because {e.text}'
        return f'{member.display_name} is now unlocked and can access channels again{f"{NEWLINE}{NEWLINE}{errorMessage}" if errorMessage else ""}'

    @bulk.command(name='unlock')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def bulk_unlock(
        self,
        ctx: commands.Context,
        member: discord.Member,
        member2: Optional[discord.Member] = None,
        member3: Optional[discord.Member] = None,
        member4: Optional[discord.Member] = None,
        member5: Optional[discord.Member] = None,
        member6: Optional[discord.Member] = None,
        member7: Optional[discord.Member] = None,
        member8: Optional[discord.Member] = None,
        member9: Optional[discord.Member] = None,
        member10: Optional[discord.Member] = None,
        reason: Optional[str] = '',
    ):
        """
        Unlocks the specified members: allows them to access all channels again
        --------------------------------
        Parameters:
        member: discord.Member
            The member to unlock
        reason: str, optional
            The reason for unlocking the members
        """
        await ctx.interaction.response.defer(thinking=True)
        members = list(filter(lambda m: m, [member, member2, member3, member4, member5, member6, member7, member8, member9, member10]))
        for member in members:
            for c in ctx.guild.channels:
                await c.set_permissions(member, overwrite=None, reason=audit_log_reason(ctx.author, reason))
            errorMessage = None
            try:
                await member.send(f'You may now access channels again in {ctx.guild.name}')
            except (discord.Forbidden, discord.HTTPException) as e:
                errorMessage = f'Unable to notify {member.display_name} by DM because {e.text}'
        await ctx.send(
            content=f'{len(members)} members [{[", ".join(str(member) for member in members)]}] are now unlocked and can access channels again{f"{NEWLINE}{NEWLINE}{errorMessage}" if errorMessage else ""}'
        )

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True, manage_channels=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, duration: typing.Optional[str] = '', reason: typing.Optional[str] = ''):
        """
        Mutes the specified member for a specified amount of time, if given
        --------------------------------
        Parameters:
        member: discord.Member
            The member to mute
        duration: str
            The duration to mute the member for
        reason: str
            The reason for muting the member

        """
        await ctx.interaction.response.defer(thinking=True)
        duration, int_arg, unit = utility.ParseDuration(duration)
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        results = await self.muteMembers([member], ctx.author, duration=duration, reason=reason)

        def nestMore(array):
            return '\n'.join([f'{NEWLINE}{qlf}{qlf}{i}' for i in array]) if len(array) > 1 else f'{array[0]}' if len(array) == 1 else ''

        embed = discord.Embed(title=f'{self.emojis["muted"]}Mute 1 member', color=orange[await utility.color_theme(ctx.guild)])
        embed.description = f'Member: {member}\nDuration: {int_arg if duration else "∞"} {unit if duration else ""}'
        embed.description += '\n\n'.join(
            [
                f"""{m}:\n{NEWLINE.join([f"{qlf}{k}: {NEWLINE.join([f'{qlf}{nestMore(v)}'])}" for k, v in n.items()])}""" if len(n) > 0 else ''
                for m, n in results.items()
            ]
        )
        await ctx.send(embed=embed)

    @bulk.command(name='mute')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True, manage_channels=True)
    async def bulk_mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        member2: Optional[discord.Member] = None,
        member3: Optional[discord.Member] = None,
        member4: Optional[discord.Member] = None,
        member5: Optional[discord.Member] = None,
        member6: Optional[discord.Member] = None,
        member7: Optional[discord.Member] = None,
        member8: Optional[discord.Member] = None,
        member9: Optional[discord.Member] = None,
        member10: Optional[discord.Member] = None,
        duration: typing.Optional[str] = '',
        reason: typing.Optional[str] = '',
    ):
        """
        Mutes the specified member(s) for a specified amount of time, if given
        --------------------------------
        Parameters:
        member: discord.Member
            The member to mute
        duration: str
            The duration to mute the members for
        reason: str
            The reason for muting the members
        """
        await ctx.interaction.response.defer(thinking=True)
        duration, int_arg, unit = utility.ParseDuration(duration)
        members = list(filter(lambda m: m, [member, member2, member3, member4, member5, member6, member7, member8, member9, member10]))
        embed = discord.Embed(title=f'{self.emojis["muted"]}Mute {len(members)} members', color=orange[await utility.color_theme(ctx.guild)])
        embed.description = (
            f'Members: {", ".join(str(member) for member in members)}\nDuration: {int_arg if duration else "∞"} {unit if duration else ""}'
        )
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        results = await self.muteMembers(members, ctx.author, duration=duration, reason=reason)

        def nestMore(array):
            return '\n'.join([f'{NEWLINE}{qlf}{qlf}{i}' for i in array]) if len(array) > 1 else f'{array[0]}' if len(array) == 1 else ''

        embed.description += '\n\n'.join(
            [
                f"""{m}:\n{NEWLINE.join([f"{qlf}{k}: {NEWLINE.join([f'{qlf}{nestMore(v)}'])}" for k, v in n.items()])}""" if len(n) > 0 else ''
                for m, n in results.items()
            ]
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True, manage_channels=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, reason: typing.Optional[str] = ''):
        """
        Unmutes the specified member
        --------------------------------
        Parameters:
        members: discord.Member
            The member to unmute
        reason: str
            The reason for unmuting the member
        """
        await ctx.interaction.response.defer(thinking=True)
        embed = discord.Embed(title=f'{self.emojis["unmuted"]}Unmute {member}', color=orange[await utility.color_theme(ctx.guild)])
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        results = await self.unmuteMembers([member], ctx.author, {}, reason=reason)

        def nestMore(array):
            return '\n'.join([f'{NEWLINE}{qlf}{qlf}{i}' for i in array]) if len(array) > 1 else f'{array[0]}' if len(array) == 1 else ''

        embed.description = '\n\n'.join(
            [
                f"""{m}:\n{NEWLINE.join([f"{qlf}{k}: {NEWLINE.join([f'{qlf}{nestMore(v)}'])}" for k, v in n.items()])}""" if len(n) > 0 else ''
                for m, n in results.items()
            ]
        )
        await ctx.send(embed=embed)

    @bulk.command(name='unmute')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True, manage_channels=True)
    async def bulk_unmute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        member2: Optional[discord.Member] = None,
        member3: Optional[discord.Member] = None,
        member4: Optional[discord.Member] = None,
        member5: Optional[discord.Member] = None,
        member6: Optional[discord.Member] = None,
        member7: Optional[discord.Member] = None,
        member8: Optional[discord.Member] = None,
        member9: Optional[discord.Member] = None,
        member10: Optional[discord.Member] = None,
        reason: typing.Optional[str] = '',
    ):
        """
        Unmutes the specified member(s)
        --------------------------------
        Parameters:
        member: discord.Member
            The members to unmute
        reason: str
            The reason for unmuting the members
        """

        await ctx.interaction.response.defer(thinking=True)
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        members = list(filter(lambda m: m, [member, member2, member3, member4, member5, member6, member7, member8, member9, member10]))
        results = await self.unmuteMembers(members, ctx.author, {}, reason=reason)

        def nestMore(array):
            return '\n'.join([f'{NEWLINE}{qlf}{qlf}{i}' for i in array]) if len(array) > 1 else f'{array[0]}' if len(array) == 1 else ''

        embed = discord.Embed(
            title=f'{self.emojis["unmuted"]}Unmute {len(members)} members',
            description=f'Members: {", ".join(str(member) for member in members)}\n',
            color=orange[await utility.color_theme(ctx.guild)],
        )
        embed.description = '\n\n'.join(
            [
                f"""{m}:\n{NEWLINE.join([f"{qlf}{k}: {NEWLINE.join([f'{qlf}{nestMore(v)}'])}" for k, v in n.items()])}""" if len(n) > 0 else ''
                for m, n in results.items()
            ]
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_guild_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, reason: str = ''):
        """
        Kicks the specified member from the server
        --------------------------------
        Parameters:
        member: discord.Member
            The member to kick
        reason: str
            The reason for kicking the member
        """
        await ctx.interaction.response.defer(thinking=True)
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        embed = discord.Embed(title=f'👢Kick {member}', description='', color=orange[await utility.color_theme(ctx.guild)])
        try:
            if await utility.ManageServer(member):
                raise Exception('You cannot kick a moderator')
            await member.kick(reason=reason)
            embed.description += f'{self.emojis["greenCheck"]} | Succesfully kicked {member}\n'
        except Exception as e:
            embed.description += f'{self.emojis["alert"]} | Error kicking {member}: {e}\n'
        await ctx.send(embed=embed)

    @bulk.command(name='kick')
    @commands.guild_only()
    @commands.has_guild_permissions(kick_members=True)
    async def bulk_kick(
        self,
        ctx: commands.Context,
        member: discord.Member,
        member2: Optional[discord.Member] = None,
        member3: Optional[discord.Member] = None,
        member4: Optional[discord.Member] = None,
        member5: Optional[discord.Member] = None,
        member6: Optional[discord.Member] = None,
        member7: Optional[discord.Member] = None,
        member8: Optional[discord.Member] = None,
        member9: Optional[discord.Member] = None,
        member10: Optional[discord.Member] = None,
        reason: typing.Optional[str] = '',
    ):
        """
        Kicks the specified member(s) from the server
        --------------------------------
        Parameters:
        member: discord.Member
            The member to kick
        reason: str
            The reason for kicking the members
        """
        await ctx.interaction.response.defer(thinking=True)
        embed = discord.Embed(title=f'👢Kick {member}', description='', color=orange[await utility.color_theme(ctx.guild)])
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        members = list(filter(lambda m: m, [member, member2, member3, member4, member5, member6, member7, member8, member9, member10]))
        for member in members:
            try:
                if await utility.ManageServer(member):
                    raise Exception('You cannot kick a moderator')
                await member.kick(reason=reason)
                embed.description += f'{self.emojis["greenCheck"]} | Succesfully kicked {member}\n'
            except Exception as e:
                embed.description += f'{self.emojis["alert"]} | Error kicking {member}: {e}\n'
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    async def ban(
        self,
        ctx: commands.Context,
        user: discord.User,
        duration: typing.Optional[str] = '',
        delete_message_days: typing.Optional[int] = 0,
        reason: typing.Optional[str] = '',
    ):
        """
        Bans a specified user currently in the server
        --------------------------------
        Parameters:
        user: discord.User
            The user to ban
        duration: str
            The duration to ban the user for
        delete_message_days: int
            This user's messages sent over the past X days will be deleted
        reason: str
            The reason for banning the user
        """
        await ctx.interaction.response.defer(thinking=True)
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        embed = discord.Embed(title=f'{self.emojis["ban"]}Ban {user}', description='', color=orange[await utility.color_theme(ctx.guild)])
        try:
            member = ctx.guild.get_member(user.id)
            if member and await utility.ManageServer(member):
                raise Exception('You cannot ban a moderator')
            await ctx.guild.ban(member, delete_message_days=delete_message_days, reason=reason)
            if duration:
                duration = utility.ParseDuration(duration)
                event = {
                    'type': 'ban',
                    'flavor': reason,
                    'target': member.id,
                    'expires': discord.utils.utcnow() + datetime.timedelta(seconds=duration),
                }
                await database.AppendTimedEvent(ctx.guild, event)
            embed.description += f'{self.emojis["greenCheck"]} | Succesfully banned {member}\n'
        except Exception as e:
            embed.description += f'{self.emojis["alert"]} | Error banning {member}: {e}\n'
        await ctx.send(embed=embed)

    @bulk.command(name='ban')
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    async def bulk_ban(
        self,
        ctx: commands.Context,
        user: discord.User,
        user2: Optional[discord.User] = None,
        user3: Optional[discord.User] = None,
        user4: Optional[discord.User] = None,
        user5: Optional[discord.User] = None,
        user6: Optional[discord.User] = None,
        user7: Optional[discord.User] = None,
        user8: Optional[discord.User] = None,
        user9: Optional[discord.User] = None,
        user10: Optional[discord.User] = None,
        duration: typing.Optional[str] = '',
        delete_message_days: typing.Optional[int] = 0,
        reason: typing.Optional[str] = '',
    ):
        """
        Bans the specified users currently in the server
        --------------------------------
        Parameters:
        user: discord.User
            The user to ban
        duration: str
            The duration to ban the user for
        delete_message_days: int
            This user's messages sent over the past X days will be deleted
        reason: str
            The reason for banning the user
        """
        await ctx.interaction.response.defer(thinking=True)
        embed = discord.Embed(title=f'{self.emojis["ban"]}Ban {user}', description='', color=orange[await utility.color_theme(ctx.guild)])
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        users = list(filter(lambda u: u, [user, user2, user3, user4, user5, user6, user7, user8, user9, user10]))
        for user in users:
            try:
                member = ctx.guild.get_member(user.id)
                if member and await utility.ManageServer(member):
                    raise Exception('You cannot ban a moderator')
                await ctx.guild.ban(member, delete_message_days=delete_message_days, reason=reason)
                if duration:
                    duration = utility.ParseDuration(duration)
                    event = {
                        'type': 'ban',
                        'flavor': reason,
                        'target': member.id,
                        'expires': discord.utils.utcnow() + datetime.timedelta(seconds=duration),
                    }
                    await database.AppendTimedEvent(ctx.guild, event)
                embed.description += f'{self.emojis["greenCheck"]} | Succesfully banned {member}\n'
            except Exception as e:
                embed.description += f'{self.emojis["alert"]} | Error banning {member}: {e}\n'
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    async def shadowban(self, ctx: commands.Context, user_id: str, duration: typing.Optional[str] = '', reason: typing.Optional[str] = ''):
        """
        Bans a user (by ID) not currently in the server
        --------------------------------
        Parameters:
        user_id: int
            The ID of the user to ban
        duration: str
            The duration to ban the user for
        reason: str
            The reason for banning the user
        """
        await ctx.interaction.response.defer(thinking=True)
        user = await self.bot.fetch_user(int(user_id))
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        embed = discord.Embed(title=f'{self.emojis["ban"]}Shadowban {user}', description='', color=orange[await utility.color_theme(ctx.guild)])
        try:
            member = ctx.guild.get_member(user.id)
            if member and await utility.ManageServer(member):
                raise Exception('You cannot ban a moderator')
            await ctx.guild.ban(user, delete_message_days=0, reason=reason)
            if duration:
                duration = utility.ParseDuration(duration)
                event = {'type': 'ban', 'flavor': reason, 'target': user.id, 'expires': discord.utils.utcnow() + datetime.timedelta(seconds=duration)}
                await database.AppendTimedEvent(ctx.guild, event)
            embed.description += f'{self.emojis["greenCheck"]} | Succesfully shadowbanned {user.display_name}\n`{reason}`'
        except Exception as e:
            embed.description += f'{self.emojis["alert"]} | Error shadowbanning {member}: {e}\n'
        await ctx.send(embed=embed)

    @bulk.command(name='shadowban')
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    async def bulk_shadowban(
        self,
        ctx: commands.Context,
        user_id: str,
        user_id2: Optional[str] = None,
        user_id3: Optional[str] = None,
        user_id4: Optional[str] = None,
        user_id5: Optional[str] = None,
        user_id6: Optional[str] = None,
        user_id7: Optional[str] = None,
        user_id8: Optional[str] = None,
        user_id9: Optional[str] = None,
        user_id10: Optional[str] = None,
        duration: typing.Optional[str] = '',
        reason: typing.Optional[str] = '',
    ):
        """
        Bans multiple users (by ID) not currently in the server
        --------------------------------
        Parameters:
        user_id: int
            The ID of the user to ban
        duration: str
            The duration to ban the user for
        reason: str
            The reason for banning the user
        """
        await ctx.interaction.response.defer(thinking=True)
        embed = discord.Embed(title=f'{self.emojis["ban"]}Shadowban {user_id}', description='', color=orange[await utility.color_theme(ctx.guild)])
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        user_ids = list(filter(lambda u: u, [user_id, user_id2, user_id3, user_id4, user_id5, user_id6, user_id7, user_id8, user_id9, user_id10]))
        for user_id in user_ids:
            try:
                user = await self.bot.fetch_user(int(user_id))
                member = ctx.guild.get_member(user.id)
                if member and await utility.ManageServer(member):
                    raise Exception('You cannot ban a moderator')
                await ctx.guild.ban(user, delete_message_days=0, reason=reason)
                if duration:
                    duration = utility.ParseDuration(duration)
                    event = {
                        'type': 'ban',
                        'flavor': reason,
                        'target': user.id,
                        'expires': discord.utils.utcnow() + datetime.timedelta(seconds=duration),
                    }
                    await database.AppendTimedEvent(ctx.guild, event)
                embed.description += f'{self.emojis["greenCheck"]} | Succesfully shadowbanned {user.display_name}\n`{reason}`'
            except Exception as e:
                embed.description += f'{self.emojis["alert"]} | Error shadowbanning {member}: {e}\n'
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user: str, reason: typing.Optional[str] = ''):
        """
        Unbans the specified member
        --------------------------------
        Parameters:
        user: str
            Search the server's banned members for the user to unban
        reason: str
            The reason for unbanning the user
        """
        await ctx.interaction.response.defer(thinking=True)
        user = await self.bot.fetch_user(int(user))
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        embed = discord.Embed(title=f'{self.emojis["unban"]}Unban {user}', description='', color=orange[await utility.color_theme(ctx.guild)])
        try:
            await ctx.guild.unban(user, reason=reason)
            embed.description += f'{self.emojis["greenCheck"]} | Succesfully unbanned {user}\n`{reason}`'
        except Exception as e:
            embed.description += f'{self.emojis["alert"]} | Error unbanning {user}: {e}\n'
        await ctx.send(embed=embed)

    @bulk.command(name='unban')
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    async def bulk_unban(
        self,
        ctx: commands.Context,
        user: str,
        user2: Optional[str] = None,
        user3: Optional[str] = None,
        user4: Optional[str] = None,
        user5: Optional[str] = None,
        user6: Optional[str] = None,
        user7: Optional[str] = None,
        user8: Optional[str] = None,
        user9: Optional[str] = None,
        user10: Optional[str] = None,
        reason: typing.Optional[str] = '',
    ):
        """
        Unbans multiple members
        --------------------------------
        Parameters:
        user: str
            Search the server's banned members for the user to unban
        reason: str
            The reason for unbanning the user
        """
        await ctx.interaction.response.defer(thinking=True)
        embed = discord.Embed(title=f'{self.emojis["unban"]}Unban {user}', description='', color=orange[await utility.color_theme(ctx.guild)])
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        users = list(filter(lambda u: u, [user, user2, user3, user4, user5, user6, user7, user8, user9, user10]))
        for user in users:
            try:
                user = await self.bot.fetch_user(int(user))
                await ctx.guild.unban(user, reason=reason)
                embed.description += f'{self.emojis["greenCheck"]} | Succesfully unbanned {user}\n`{reason}`'
            except Exception as e:
                embed.description += f'{self.emojis["alert"]} | Error unbanning {user}: {e}\n'
        await ctx.send(embed=embed)

    """Autocompletes"""

    @warmup.autocomplete('duration')
    @mute.autocomplete('duration')
    @bulk_mute.autocomplete('duration')
    @ban.autocomplete('duration')
    @bulk_ban.autocomplete('duration')
    @shadowban.autocomplete('duration')
    @bulk_shadowban.autocomplete('duration')
    async def duration_autocomplete(self, interaction: discord.Interaction, argument: str):
        if argument:
            hasNumber = re.search(r'\d', argument)
            hasLetter = re.search(r'\D', argument)
            if hasLetter:
                index = hasLetter.start()
            else:
                index = len(argument)
            letters = argument[index:].strip(' ')
            if hasNumber:
                return [
                    app_commands.Choice(
                        name=f'{argument[:index]} {units[unit] if int(argument[:index]) == 1 else f"{units[unit]}s"}',
                        value=f'{argument[:index]}{unit}',
                    )
                    for unit in units.keys()
                    if (units[unit].startswith(letters) if hasLetter else True)
                ]
        return []

    @unban.autocomplete('user')
    @bulk_unban.autocomplete('user')
    async def unban_autocomplete(self, interaction: discord.Interaction, argument: str):
        argument = argument.lower()
        try:
            banned_users: list[discord.User] = [ban.user async for ban in interaction.guild.bans()]
        except discord.Forbidden:
            banned_users = []
        if argument:
            return [
                app_commands.Choice(name=f'{user}', value=str(user.id))
                for user in banned_users
                if argument in user.name.lower() or argument in str(user.id)
            ][:25]
        else:
            return [app_commands.Choice(name=f'{user}', value=str(user.id)) for user in banned_users][:25]

    @shadowban.autocomplete('user_id')
    @bulk_shadowban.autocomplete('user_id')
    async def shadowban_autocomplete(self, interaction: discord.Interaction, argument: str):
        try:
            user = await self.bot.fetch_user(int(argument))
            return [app_commands.Choice(name=f'{user}', value=str(user.id))]
        except:
            return []

    @commands.hybrid_command(description='Purge messages')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, args: str = ''):
        """Purge messages"""
        global filters
        current = copy.deepcopy(PurgeObject())
        filters[ctx.guild.id] = current
        if not GetManageMessagePermissions(ctx.guild.me) and ('purge:true' in args or len(args) == 1):
            return await ctx.send("I am unable to execute the purge command as I don't have manage message permissions")
            # await ctx.send('Temporarily bypassing permission restrictions')
        if len(args) < 1:
            timeout = discord.Embed(title='Purge command', description='Timed out')
            cancel = discord.Embed(title='Purge command', description='Cancelled')
            url = 'https://cdn.discordapp.com/emojis/605060517861785610.gif'
            embed = discord.Embed(
                title='Purge command',
                description="Welcome to the interactive purge command! You'll be taken through a setup walking you through the purging features I have.\n\n",
                color=blue[await utility.color_theme(ctx.guild)],
            )
            embed.description += 'First, what channel(s) are you thinking of purging? Make sure the channel(s) are hyperlinked. To purge from this channel ({}), type `here`, to purge from all text channels, type `all`'.format(
                ctx.channel.mention
            )
            embed.set_footer(text='Type cancel to cancel the command. Timeout is 120s')
            embed.set_author(name='Waiting for input')
            message = await ctx.send(embed=embed)
            current.botMessage = message
            current.mentions = ctx.message
            messages = []

            def check_channels(m):
                return (
                    m.channel == ctx.channel
                    and m.author == ctx.author
                    and (len(m.channel_mentions) > 0 or any(s in m.content.lower() for s in ['a', 'h', 'cancel']))
                )

            try:
                post = await self.bot.wait_for('message', check=check_channels, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait')
            await message.edit(embed=embed)
            embed.set_author(name='Waiting for input')
            channels = []
            if len(post.channel_mentions) > 0:
                channels += post.channel_mentions
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'h' in post.content.lower():
                channels.append(ctx.channel)
            if 'a' in post.content.lower():
                channels = ctx.guild.text_channels
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            counts = []
            indexing_enabled = (await utility.get_server(ctx.guild)).get('cyberlog').get('indexing')
            if indexing_enabled:
                for channel in channels:
                    try:
                        counts.append(len(await lightningdb.get_channel_messages(channel.id)))
                    except KeyError:
                        # no indexes
                        continue
            total = sum(counts)
            current.channel = channels
            embed.description = "Ok cool, {} for a total of {} messages BTW.\n\nWould you like me to index the channel(s) you selected to let you know how many messages match your filters as we progress through setup? This may take a long time if the channel(s) has/have lots of messages. If it takes longer than 5 minutes, I'll tag you when I'm done. Type `yes` or `no`".format(
                ', '.join(['{} has {} posts'.format(channels[c].mention, counts[c]) for c in range(len(channels))]), total
            )
            await message.edit(embed=embed)

            def index(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content.lower() for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=index, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            now = discord.utils.utcnow()
            embed.set_author(name='Please wait', icon_url=url)
            if 'y' in post.content:
                embed.set_author(name='Indexing messages', icon_url=url)
                # await indexMessages(message, embed, total, channels)
                loadingBar = [
                    'o-------------------',
                    '-o------------------',
                    '--o-----------------',
                    '---o----------------',
                    '----o---------------',
                    '-----o--------------',
                    '------o-------------',
                    '-------o------------',
                    '--------o-----------',
                    '---------o----------',
                    '----------o---------',
                    '-----------o--------',
                    '------------o-------',
                    '-------------o------',
                    '--------------o-----',
                    '---------------o----',
                    '----------------o---',
                    '-----------------o--',
                    '------------------o-',
                    '-------------------o',
                ]
                embed.description = '0/{} messages, 0/{} channels\n\n0% {}\n\n0 messages per second, Time remaining: N/A'.format(
                    total, len(channels), loadingBar[0]
                )
                await message.edit(embed=embed)
                messages = []
                status = {'c': 0, 'm': 0, 'last': 0}
                lastUpdate = datetime.datetime.now()
                for c in channels:
                    status['c'] += 1
                    async for m in c.history(limit=None):
                        status['m'] += 1
                        if (datetime.datetime.now() - lastUpdate).seconds > 3:
                            embed.description = '{}/{} messages, {}/{} channels\n\n{}% {}'.format(
                                status.get('m'),
                                total,
                                status.get('c'),
                                len(channels),
                                100 * round(status.get('m') / total, 2),
                                loadingBar[round(19 * (round((status.get('m') / total), 2)))] if status.get('m') < total else loadingBar[19],
                            )
                            embed.description += '\n\n{} messages per second, Time remaining: {}'.format(
                                round((status.get('m') - status.get('last')) / 3),
                                ETA(status.get('m'), round((status.get('m') - status.get('last')) / 3), total),
                            )
                            await message.edit(embed=embed)
                            lastUpdate = datetime.datetime.now()
                            status['last'] = status.get('m')
                        messages.append(m)
            embed.set_author(name='Waiting for input')
            embed.set_footer(text='Type cancel to cancel the command. Timeout is 120s')
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            if (discord.utils.utcnow() - now).seconds / 60 > 5:
                await ctx.channel.send("{}, I'm done indexing".format(ctx.author.mention), delete_after=10)
            embed.description = 'Next up, are you interested in purging messages containing certain text? Type `yes` to be taken to setup for those options or `no` to move on and skip this part.'
            await message.edit(embed=embed)

            def textCondition(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content.lower() for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=textCondition, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            embed.set_author(name='Waiting for input')
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'n' in post.content.lower():
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
                embed.add_field(name='Messages to be purged', value=0)
            if 'y' in post.content.lower():
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
                embed.description = (
                    'Would you like to purge only messages containing certain text? Type the text to check for or `skip` to skip this step.'
                )
                await message.edit(embed=embed)

                def contains(m):
                    return m.channel == ctx.channel and m.author == ctx.author

                try:
                    post = await self.bot.wait_for('message', check=contains, timeout=120)
                except asyncio.TimeoutError:
                    return await message.edit(embed=timeout)
                embed.set_author(name='Please wait', icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower():
                    return await message.edit(embed=cancel)
                if 'skip' not in post.content.lower():
                    current.contains = post.content
                if messages:
                    embed.add_field(name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                embed.set_author(name='Waiting for input')
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
                if current.contains is not None:
                    embed.description = 'Right now, messages matching the filter will be purged regardless of capitalization. Would you like the filter to be case sensitive and only purge messages matching the capitalization you specified? Type `yes` or `no`'
                    await message.edit(embed=embed)

                    def caseSen(m):
                        return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content.lower() for s in ['y', 'n', 'cancel'])

                    try:
                        post = await self.bot.wait_for('message', check=caseSen, timeout=120)
                    except asyncio.TimeoutError:
                        return await message.edit(embed=timeout)
                    embed.set_author(name='Please wait', icon_url=url)
                    await message.edit(embed=embed)
                    embed.set_author(name='Waiting for input')
                    if 'cancel' in post.content.lower():
                        return await message.edit(embed=cancel)
                    if 'y' in post.content.lower():
                        current.caseSensitive = True
                    if messages:
                        embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                    try:
                        self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                        await post.delete()
                    except:
                        pass
                embed.description = (
                    'Would you like to purge only messages that *start with* a certain text sequence? (Type a text sequence or `skip`)'
                )
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
                embed.set_author(name='Waiting for input', icon_url=url)
                await message.edit(embed=embed)

                def startsWith(m):
                    return m.channel == ctx.channel and m.author == ctx.author

                try:
                    post = await self.bot.wait_for('message', check=startsWith, timeout=120)
                except asyncio.TimeoutError:
                    return await message.edit(embed=timeout)
                embed.set_author(name='Please wait', icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower():
                    return await message.edit(embed=cancel)
                if 'skip' not in post.content.lower():
                    current.startsWith = post.content
                if messages:
                    embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                embed.description = 'Would you like to purge only messages that *end with* a certain text sequence? (Type a text sequence or `skip`)'
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
                embed.set_author(name='Waiting for input', icon_url=url)
                await message.edit(embed=embed)

                def endsWith(m):
                    return m.channel == ctx.channel and m.author == ctx.author

                try:
                    post = await self.bot.wait_for('message', check=endsWith, timeout=120)
                except asyncio.TimeoutError:
                    return await message.edit(embed=timeout)
                embed.set_author(name='Please wait', icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower():
                    return await message.edit(embed=cancel)
                if 'skip' not in post.content.lower():
                    current.endsWith = post.content
                if messages:
                    embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                embed.set_author(name='Waiting for input')
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
            embed.description = 'Would you like to purge only messages belonging to bots/humans? Type `bots` to purge only bot messages, `humans` to purge only human messages, and `both` to purge any messages'
            await message.edit(embed=embed)

            def bots(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['bots', 'h', 'both', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=bots, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            elif 'bots' in post.content.lower():
                current.bots = 0
            elif 'both' in post.content.lower():
                current.bots = 2
            elif 'human' in post.content.lower():
                current.bots = 1
            if messages:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input')
            embed.description = 'Would you like to purge only messages belonging to a certain author or set of authors? Enter comma and space (`, `) separated usernames, IDs, or mentions, or type `skip`'
            await message.edit(embed=embed)

            def author(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                post = await self.bot.wait_for('message', check=author, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            embed.description = ''
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            embed.description = ''
            if 'skip' not in post.content.lower():
                if ',' in post.content:
                    ppl = ', '.split(post.content)
                else:
                    ppl = [post.content]
                mem = []
                for p in ppl:
                    try:
                        result = self.bot.get_cog('Cyberlog').FindMember(ctx.guild, p)
                        if result is not None:
                            mem.append(result)
                    except Exception as e:
                        print(e)
                current.author = mem
                embed.description = 'I matched these message authors: {}.\n'.format(', '.join([m.name for m in mem]))
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
                if messages:
                    embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description += 'Would you like to purge only messages that contains URLs? Type yes/no'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)

            def links(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=links, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'y' in post.content.lower():
                current.links = True
            if messages:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description = 'Would you like to purge only messages that contain discord.gg invites? (yes/no)'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)

            def invites(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=invites, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'y' in post.content.lower():
                current.invites = True
            if messages:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description = 'Would you like to purge only messages that contain attachments? Type `image` to purge messages with *image* attachments, `file` to purge messages with *non image* attachments, `both` to purge messages with any external attachments, or `skip` to skip this step'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)

            def images(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['i', 'f', 'b', 'cancel', 'skip'])

            try:
                post = await self.bot.wait_for('message', check=images, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'skip' not in post.content.lower():
                if 'f' in post.content.lower():
                    current.files = True  # F first cuz 'file' has an 'i' in it
                elif 'i' in post.content.lower():
                    current.images = True
                elif 'b' in post.content.lower():
                    current.files = True
                    current.images = True
            if messages:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description = 'Would you like to purge only messages that contain embeds? This only applies to messages sent by bots. (Yes/no)'
            embed.set_author(name='Waiting for input')
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            await message.edit(embed=embed)

            def embeds(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=embeds, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'y' in post.content.lower():
                current.embeds = True
            if messages:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description = 'Would you like to purge only messages that contain member mentions e.g. @person? (Yes/no)'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)

            def mentions(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=mentions, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'y' in post.content.lower():
                current.mentions = True
            if messages:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description = 'Would you like to purge only messages that have reactions on them?'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)

            def reactions(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=reactions, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'y' in post.content.lower():
                current.reactions = True
            if messages:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description = 'Would you like to purge only messages that contain activity messages (Spotify invites, Game invites, etc)?'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)

            def activity(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=activity, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'y' in post.content.lower():
                current.appMessages = True
            if messages:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description = 'Are you interested in purging messages that were posted before, during, or after a certain date? Type `yes` to enter setup for these options or `no` to skip this part'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)

            def dates(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=dates, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'y' in post.content.lower():
                embed.description = 'Would you like to purge only messages were posted *after* a certain date? Type `skip` or a date in a format matching `Feb 1, 2019` or `2/1/19`'
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
                embed.set_author(name='Waiting for input', icon_url=url)
                await message.edit(embed=embed)

                def after(m):
                    return m.channel == ctx.channel and m.author == ctx.author

                try:
                    post = await self.bot.wait_for('message', check=after, timeout=120)
                except asyncio.TimeoutError:
                    return await message.edit(embed=timeout)
                embed.set_author(name='Please wait', icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower():
                    return await message.edit(embed=cancel)
                current.startDate = ConvertToDatetime(post.content)
                if messages:
                    embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                embed.description = 'Would you like to purge only messages posted *before* a certain date? Type `skip` or a date in a format matching `Feb 1, 2019` or `2/1/19`. If you want to target a single day for the purge, set this to the day before what you used in the previous step'
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                    await post.delete()
                except:
                    pass
                embed.set_author(name='Waiting for input', icon_url=url)
                await message.edit(embed=embed)

                def before(m):
                    return m.channel == ctx.channel and m.author == ctx.author

                try:
                    post = await self.bot.wait_for('message', check=before, timeout=120)
                except asyncio.TimeoutError:
                    return await message.edit(embed=timeout)
                embed.set_author(name='Please wait', icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower():
                    return await message.edit(embed=cancel)
                current.endDate = ConvertToDatetime(post.content)
                if messages:
                    embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description = 'Finally, how many messages would you like me to purge? Type `skip` to purge all messages matching the filter'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            embed.set_author(name='Waiting for input', icon_url=url)
            await message.edit(embed=embed)

            def count(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                post = await self.bot.wait_for('message', check=count, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            embed.set_author(name='Please wait', icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            if 'skip' in post.content.lower():
                limited = False
                current.limit = None
                if messages:
                    embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            else:
                current.limit = int(post.content)
                limited = True
                if messages:
                    embed.set_field_at(0, name='Messages to be purged', value='Up to {}'.format(current.limit))
            embed.description = ''
            embed.set_author(name='One sec...', icon_url=url)
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            await message.edit(embed=embed)
            embed.description = '__Filters:__\nCount: {} messages\n'.format('∞' if current.limit is None else current.limit)
            embed.description += PreDesc(ctx.guild)
            if messages and not limited:
                embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            elif messages and limited:
                embed.set_field_at(0, name='Messages to be purged', value='Up to {}'.format(current.limit))
            embed.set_author(name='Waiting for input', icon_url=url)
            embed.description += '\n\nIf you are ready to purge, type `purge`, otherwise type `cancel`'
            await message.edit(embed=embed)

            def ready(m):
                return m.channel == ctx.channel and m.author == ctx.author and any(s in m.content for s in ['purge', 'cancel'])

            try:
                post = await self.bot.wait_for('message', check=ready, timeout=120)
            except asyncio.TimeoutError:
                return await message.edit(embed=timeout)
            if 'cancel' in post.content.lower():
                return await message.edit(embed=cancel)
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post)
                await post.delete()
            except:
                pass
            limit = current.limit
            embed.description = 'Scanned 0/{}\nPurged 0/{}'.format(len(messages) if messages else total, limit)
            embed.set_author(name='Purging messages', icon_url=url)
            embed.set_footer(
                text="This will take longer than other bots' purge commands because Disguard uses a custom purge method due to limitations with Discord's built in one :/"
            )
            await message.edit(embed=embed)
            started = datetime.datetime.now()
            lastUpdate = datetime.datetime.now()
            counter = 0
            if messages:
                for post in messages:
                    counter += 1
                    if current.limit == 0:
                        break  # Reached purge limit
                    if (datetime.datetime.now() - lastUpdate).seconds > 3:
                        embed.description = 'Scanned {}/{}\nPurged {}/{}'.format(counter, len(messages), current.purgeStat.get(2), limit)
                        await message.edit(embed=embed)
                        lastUpdate = datetime.datetime.now()
                    result = await self.SuperPurge(post)
                    if result == 0:
                        current.purgeStat[0] += 1  # Didn't pass the filter
                    elif result == 1:
                        current.purgeStat[1] += 1  # Can't delete for whatever reason
                    else:
                        current.purgeStat[2] += 1  # 2 = successful deletion
                        if current.limit is not None:
                            current.limit -= 1
            else:
                for c in channels:
                    async for post in c.history(limit=None):
                        counter += 1
                        if current.limit == 0:
                            break
                        if (datetime.datetime.now() - lastUpdate).seconds > 3:
                            embed.description = 'Scanned {}/{}\nPurged {}/{}'.format(counter, total, current.purgeStat.get(2), limit)
                            elapsed = datetime.datetime.now() - started
                            if elapsed.seconds < 60:
                                embed.description += '\nTime taken: {} seconds'.format(elapsed.seconds)
                            else:
                                embed.description += '\nTime taken: {} minutes'.format(round(elapsed.seconds / 60))
                            await message.edit(embed=embed)
                            lastUpdate = datetime.datetime.now()
                        result = await self.SuperPurge(post)
                        if result == 0:
                            current.purgeStat[0] += 1  # Didn't pass the filter
                        elif result == 1:
                            current.purgeStat[1] += 1  # Can't delete for whatever reason
                        else:
                            current.purgeStat[2] += 1  # 2 = successful deletion
                            if current.limit is not None:
                                current.limit -= 1
            timeTaken = datetime.datetime.now() - started
            embed.set_author(name='Thanks for purging!', icon_url='https://cdn.discordapp.com/emojis/569191704523964437.png')
            maximum = '∞' if limit is None else limit
            embed.description = 'Purged {} out of {} requested messages ({}%)\n'.format(
                current.purgeStat.get(2), maximum, '∞' if maximum == '∞' else round(current.purgeStat.get(2) / maximum * 100)
            )
            embed.description += 'Purged {} out of {} possible messages ({}%)\n'.format(
                current.purgeStat.get(2), len(messages), '∞' if message is None else round(current.purgeStat.get(2) / len(messages) * 100)
            )
            if timeTaken.seconds < 60:
                embed.description += 'Time taken: {} seconds'.format(timeTaken.seconds)
            else:
                embed.description += 'Time taken: {} minutes'.format(round(timeTaken.seconds / 60))
            embed.set_footer(text='If you have feedback, head to bit.ly/2disguard to find more information')
            if len(embed.fields) > 0:
                embed.remove_field(0)
            return await message.edit(embed=embed)
        current.botMessage = await ctx.send(str(loading) + 'Parsing filters...')
        actuallyPurge = False
        current.channel.append(ctx.channel)
        current.message = ctx.message
        for arg in args:
            meat = arg[arg.find(':') + 1 :].strip()
            body = arg.lower()
            if 'count' in body:
                current.limit = int(meat)
            elif 'purge' in body:
                actuallyPurge = True if 'true' in meat.lower() else False
            elif 'author' in body:
                current.author.append(ctx.guild.get_member_named(meat))
            elif 'contains' in body:
                current.contains = meat
            elif 'startswith' in body:
                current.startsWith = meat
            elif 'endswith' in body:
                current.endsWith = meat
            elif 'links' in body:
                current.links = True if 'true' in meat.lower() else False
            elif 'invites' in body:
                current.invites = True if 'true' in meat.lower() else False
            elif 'images' in body:
                current.images = True if 'true' in meat.lower() else False
            elif 'embeds' in body:
                current.embeds = True if 'true' in meat.lower() else False
            elif 'mentions' in body:
                current.mentions = True if 'true' in meat.lower() else False
            elif 'bots' in body:
                current.bots = 0 if 'true' in meat.lower() else False
            elif 'channel' in body:
                current.channel[0] = ctx.message.channel_mentions[0] if len(ctx.message.channel_mentions) > 0 else ctx.channel
            elif 'attachments' in body:
                current.files = True if 'true' in meat.lower() else False
            elif 'reactions' in body:
                current.reactions = True if 'true' in meat.lower() else False
            elif 'external_messages' in body:
                current.appMessages = True if 'true' in meat.lower() else False
            elif 'after' in body:
                current.startDate = ConvertToDatetime(meat)
            elif 'before' in body:
                current.endDate = ConvertToDatetime(meat)
            else:
                try:
                    current.limit = int(body)  # for example, .purge 10 wouldn't fall into the above categories, but is used due to rapid ability
                except:
                    current = None
                    return await ctx.send(
                        "I don't think **" + body + '** is a number... please try again, or use the website documentation for filters'
                    )
                actuallyPurge = True
            current.limit += 2
        if actuallyPurge:
            await current.botMessage.edit(content=str(loading) + 'Purging...')
            Cyberlog.beginPurge(ctx.guild)
            messages = await current.channel[0].purge(limit=current.limit, check=PurgeFilter, before=current.endDate, after=current.startDate)
            Cyberlog.endPurge(ctx.guild)
            await current.botMessage.edit(content='**Successfully purged ' + str(len(messages) - 1) + ' messages :ok_hand:**', delete_after=5)
        else:
            await current.botMessage.edit(content=str(loading) + 'Indexing... please be patient')
            count = 0
            async for message in current.channel[0].history(limit=current.limit, before=current.endDate, after=current.startDate):
                if PurgeFilter(message):
                    count += 1
            embed = discord.Embed(
                title='Purge pre-scan',
                description='__Filters:__\nLimit: ' + str(current.limit) + ' messages\n{}'.format(PreDesc(ctx.guild)),
                color=blue[await utility.color_theme(ctx.guild)],
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text="To actually purge, copy & paste your command message, but add 'purge:true' to the filters")
            embed.description += '\n**' + str(count) + ' messages matched the filters**'
            await current.botMessage.edit(content=None, embed=embed)
        current = None

    async def SuperPurge(self, m: discord.Message):
        if not PurgeFilter(m):
            return 0
        try:
            self.bot.get_cog('Cyberlog').AvoidDeletionLogging(m)
            await m.delete()
        except:
            return 1
        return 2

    async def UserProcessor(self, users):
        returnQueue = []
        for user in users:
            if type(user) is discord.User:
                returnQueue.append(user)
            else:
                try:
                    returnQueue.append(await self.bot.fetch_user(user))
                except discord.NotFound:
                    pass
        return returnQueue

    async def muteMembers(
        self,
        members: typing.List[discord.Member],
        author: discord.Member,
        *,
        duration: int = 0,
        reason: str = '',
        harsh=False,
        waitToUnmute=True,
        muteRole=None,
    ):
        """
        Applies automated mute to the given member, returning a status tuple (bool:success, string explanation)
        --------------------
        Parameters:
        members: List[discord.Member]
            The list of members to mute
        author: discord.Member
            The member initiating the mute
        duration: int, optional
            The duration of the mute, in seconds. If 0, the mute will be permanent
        reason: str, optional
            The reason for the mute
        harsh: bool, optional
            If True, apply permission overwrites to each channel for this member in addition to for the mute role
        waitToUnmute: bool, optional
            If True, the bot will add a loop to unmute the member after the duration has passed
        muteRole: discord.Role, optional
            The role to apply to the member. If not provided, the bot will use its default Disguard AutoMute role
        """
        """Harsh: If True, apply permission overwrites to each channel for this member in addition to for the mute role"""
        # Vars
        g = members[0].guild
        results = {'Notes': []}  # 0 holds notes
        # First: Check if we have an automute role stored
        if not muteRole:
            muteRole = g.get_role((await utility.get_server(g))['antispam'].get('automuteRole', 0))
            # If we don't have a mute role, we gotta make one
            if not muteRole:
                try:
                    muteRole = await g.create_role(
                        name='Disguard AutoMute',
                        reason='This role will be used when Disguard needs to mute a member. As long as this role exists, its ID will be stored in my database. You may edit the name of this role as you wish.',
                    )
                except Exception as e:
                    results['Notes'].append(
                        f'{self.emojis["alert"]} | Unable to mute member{"s" if len(members) != 1 else ""} - error during AutoMute role creation: {type(e).__name__}: {e}'
                    )
                    return results
                asyncio.create_task(database.SetMuteRole(g, muteRole), name='mute SetMuteRole')
        # Move the mute role's position to the position right below Disguard's top role, if it's not already there
        if muteRole.position < g.me.top_role.position - 1:
            try:
                await muteRole.edit(position=g.me.top_role.position - 1)
            except Exception as e:
                results['Notes'].append(f'Unable to move the AutoMute role higher in the rolelist, please do this manually: {type(e).__name__}: {e}')
        # Check all channels to make sure the overwrites are correct, along with removing member permissions from the channel
        permissionsTaken = collections.defaultdict(dict)
        memberRolesTaken = {}
        for c in g.text_channels:
            if c.overwrites_for(muteRole).send_messages is not False:
                try:
                    asyncio.create_task(c.set_permissions(muteRole, send_messages=False), name='mute set_permissions for muteRole')
                except Exception as e:
                    results['Notes'].append(f'{self.emojis["alert"]} | #{c.name} (🚩{muteRole.name}): `{type(e).__name__}: {e}`')
            for m in members:
                results[m] = {'Channel Permission Overwrites': [], 'Add Mute Role': [], 'Cache/Data Management': []}
                if harsh and c.overwrites_for(m).send_messages is not False:
                    try:
                        asyncio.create_task(c.set_permissions(m, send_messages=False), name='mute set_permissions for member')
                        permissionsTaken[str(m.id)][str(c.id)] = (
                            (c.overwrites.get(m).pair()[0].value, c.overwrites.get(m).pair()[1].value) if c.overwrites.get(m) else (0, 0)
                        )
                    except Exception as e:
                        results[m]['Channel Permission Overwrites'].append(f'{self.emojis["alert"]} | #{c.name}: `{type(e).__name__}: {e}`')
                elif not harsh and c.overwrites_for(m):
                    try:
                        asyncio.create_task(c.set_permissions(m, overwrite=None), name='mute set_permissions for member')
                        permissionsTaken[str(m.id)][str(c.id)] = (
                            (c.overwrites.get(m).pair()[0].value, c.overwrites.get(m).pair()[1].value) if c.overwrites.get(m) else (0, 0)
                        )
                    except Exception as e:
                        results[m]['Channel Permission Overwrites'].append(f'{self.emojis["alert"]} | #{c.name}: {type(e).__name__}: {e}')
                if len(results[m]['Channel Permission Overwrites']) == 0:
                    results[m]['Channel Permission Overwrites'].append(f'{self.emojis["greenCheck"]}')
        # Since we're removing most of the member's roles to enforce this mute, we need to keep track of the changes
        muteTimedEvents = {}
        for m in members:
            try:
                memberRolesTaken[m.id] = [r for r in m.roles if r.id != g.default_role.id]
                self.roleCache[f'{m.guild.id}_{m.id}'] = memberRolesTaken[m.id]
                self.permissionsCache[f'{m.guild.id}_{m.id}'] = permissionsTaken[str(m.id)]
                try:
                    # if muteRole.position > author.top_role.position:
                    #    raise discord.Forbidden("Your top role is below the mute role; operation aborted")
                    if author.top_role.position < m.top_role.position:
                        raise discord.Forbidden("You can't mute someone with a higher role than you")
                    await m.edit(roles=[muteRole], reason=reason)
                    results[m]['Add Mute Role'].append(f'{self.emojis["greenCheck"]}')
                except Exception as e:
                    results[m]['Add Mute Role'].append(f'{self.emojis["alert"]} | `{type(e).__name__}: {e}`')
                if duration:
                    muteTimedEvents[m.id] = {
                        'type': 'mute',
                        'target': m.id,
                        'flavor': reason,
                        'role': muteRole.id,
                        'roleList': [r.id for r in memberRolesTaken[m.id]],
                        'permissionsTaken': permissionsTaken[str(m.id)],
                        'timestamp': discord.utils.utcnow(),
                        'expires': discord.utils.utcnow() + datetime.timedelta(seconds=duration),
                    }
                    asyncio.create_task(database.AppendTimedEvent(g, muteTimedEvents[m.id]), name='mute AppendTimedEvent')
                results[m]['Cache/Data Management'].append(f'{self.emojis["greenCheck"]}')
            except Exception as e:
                results[m]['Cache/Data Management'].append(f'{self.emojis["alert"]} | `{type(e).__name__}: {e}`')
        asyncio.create_task(database.SetMuteCache(m.guild, members, memberRolesTaken), name='mute SetMuteCache')
        asyncio.create_task(database.SetPermissionsCache(m.guild, members, permissionsTaken), name='mute SetPermissionsCache')
        if duration and waitToUnmute:
            asyncio.create_task(
                self.waitToUnmute(members, author, muteTimedEvents, discord.utils.utcnow() + datetime.timedelta(seconds=duration)),
                name='mute waitToUnmute',
            )
        return results

    async def waitToUnmute(self, members, author, events, expires, reason=None):
        await discord.utils.sleep_until(expires)
        await self.unmuteMembers(members, author, events, reason=reason)

    async def unmuteMembers(self, members: list[discord.Member], author: discord.Member, events, reason=None):
        # Note: Possibly make use of discord.Object to reduce iteration counts and running time
        results = {}
        removedRoles = {}
        removedOverwrites = {}
        for m in members:
            try:
                results[m] = {'Cache/Data Management': [], 'Restore Roles': [], 'Channel Permission Overwrites': []}
                try:
                    # if muteRole.position > author.top_role.position:
                    #    raise discord.Forbidden("Your top role is below the mute role; operation aborted")
                    removedRoles[m.id] = copy.deepcopy(self.roleCache.get(f'{m.guild.id}_{m.id}')) or [
                        m.guild.get_role(r) for r in (await utility.getServerMember(m)).get('roleCache', [])
                    ]
                    removedOverwrites[m.id] = copy.deepcopy(self.permissionsCache.get(f'{m.guild.id}_{m.id}', {})) or (
                        await utility.getServerMember(m)
                    ).get('permissionsCache', {})
                    if author.top_role.position < m.top_role.position:
                        raise discord.Forbidden("You can't unmute someone with a higher role than you")
                    await m.edit(roles=removedRoles[m.id], reason=reason)
                    results[m]['Restore Roles'].append(f'{self.emojis["greenCheck"]}')
                except Exception:
                    traceback.print_exc()
                if events and events.get(m.id):
                    asyncio.create_task(database.RemoveTimedEvent(m.guild, events[m.id]), name='unmute RemoveTimedEvent')
                if self.roleCache.get(f'{m.guild.id}_{m.id}'):
                    self.roleCache.pop(f'{m.guild.id}_{m.id}')
                if self.permissionsCache.get(f'{m.guild.id}_{m.id}'):
                    self.permissionsCache.pop(f'{m.guild.id}_{m.id}')
                results[m]['Cache/Data Management'].append(f'{self.emojis["greenCheck"]}')
            except Exception as e:
                results[m]['Cache/Data Management'].append(f'{self.emojis["alert"]} | `{type(e)}: {e}`')
        asyncio.create_task(database.SetMuteCache(m.guild, members, []), name='unmute SetMuteCache')
        asyncio.create_task(database.SetPermissionsCache(m.guild, members, []), name='unmute SetPermissionsCache')
        for c in m.guild.text_channels:
            for m in members:
                try:
                    if m.id in [o.id for o in c.overwrites.keys()] and str(c.id) not in removedOverwrites[m.id].keys():
                        asyncio.create_task(c.set_permissions(m, overwrite=None))
                    elif str(c.id) in removedOverwrites[m.id].keys():
                        currentOverwrite = removedOverwrites[m.id].get(str(c.id), (0, 0))
                        asyncio.create_task(
                            c.set_permissions(
                                m,
                                overwrite=discord.PermissionOverwrite.from_pair(
                                    discord.Permissions(currentOverwrite[0]), discord.Permissions(currentOverwrite[1])
                                ),
                            ),
                            name='unmute set_permissions',
                        )
                    if len(results[m]['Channel Permission Overwrites']) == 0:
                        results[m]['Channel Permission Overwrites'].append(f'{self.emojis["greenCheck"]}')
                except Exception as e:
                    results[m]['Channel Permission Overwrites'].append(f'{self.emojis["alert"]} | `{type(e)}: {e}`')
        return results


def PurgeFilter(m: discord.Message):
    """Used to determine if a message should be purged"""
    current = filters.get(m.guild.id)
    if m.pinned:
        return False
    if m.id == current.botMessage.id:
        return False
    if current.contains is not None:
        if not current.caseSensitive:
            if current.contains.lower() not in m.content.lower():
                return False
        else:
            if current.contains not in m.content:
                return False
    if len(current.author) > 0:
        if not any(a == m.author for a in current.author):
            return False
    if current.startsWith is not None:
        if not m.content.startswith(current.startsWith):
            return False
    if current.endsWith is not None:
        if not m.content.endswith(current.endsWith):
            return False
    if current.links is True:
        if 'https://' not in m.content and 'http://' not in m.content:
            return False
    if current.invites is True:
        if 'discord.gg/' not in m.content:
            return False
    if current.images is True:
        if len(m.attachments) < 1:
            return False
        else:
            if m.attachments[0].width is None:
                return False
    if current.embeds is True:
        if len(m.embeds) < 1 and not m.author.bot:
            return False
    if current.mentions is True:
        if len(m.mentions) < 1:
            return False
    if current.bots is not None:
        if current.bots == 0:  # Purge only bot messages
            if not m.author.bot:
                return False
        if current.bots == 1:  # Purge only human messages
            if m.author.bot:
                return False
    if current.files is True:
        if len(m.attachments) < 1 or m.attachments[0].width is not None:
            return False
    if current.reactions is True:
        if len(m.reactions) < 1:
            return False
    if current.appMessages is True:
        if m.activity is None:
            return False
    if current.startDate is not None and m.created_at < current.startDate:
        return False
    if current.endDate is not None and m.created_at > current.endDate:
        return False
    return True


def PreDesc(g: discord.Guild):
    current = filters.get(g.id)
    desc = ''
    if len(current.author) > 0:
        desc += 'Author(s): {}\n'.format(', '.join([a.name for a in current.author]))
    if len(current.channel) > 0:
        desc += 'In channel(s): {}\n'.format(', '.join([c.mention for c in current.channel]))
    if current.contains is not None:
        desc += 'Contains: ' + current.contains + '\n'
    if current.startsWith is not None:
        desc += 'Starts with: ' + current.startsWith + '\n'
    if current.endsWith is not None:
        desc += 'Ends with: ' + current.endsWith + '\n'
    if current.startDate is not None:
        desc += 'Posted after: ' + current.startDate.strftime('%b %d, %Y') + '\n'
    if current.endDate is not None:
        desc += 'Posted before: ' + current.endDate.strftime('%b %d, %Y') + '\n'
    if current.links is True:
        desc += 'Contains URLs\n'
    if current.invites is True:
        desc += 'Contains server invites\n'
    if current.images is True:
        desc += 'Contains Images\n'
    if current.embeds is True:
        desc += 'Contains URLs\n'
    if current.mentions is True:
        desc += 'Contains @mentions\n'
    if current.bots == 0:
        desc += 'Authored by bots\n'
    elif current.bots == 1:
        desc += 'Authored by humans\n'
    if current.files is True:
        desc += 'Contains files\n'
    if current.reactions is True:
        desc += 'Contains reactions\n'
    if current.appMessages is True:
        desc += 'Contains external invites (e.g. Spotify)\n'
    return desc


def ETA(current, rate, total):
    quotient = round((total - current) / rate)
    if quotient > 60:
        return '{} minutes'.format(quotient / 60)
    else:
        return '{} seconds'.format(quotient)


def GetManageMessagePermissions(member: discord.Member):
    for role in member.roles:
        if role.permissions.manage_messages or role.permissions.administrator:
            return True
    return False


def ConvertToDatetime(string: str):
    try:
        return datetime.datetime.strptime(string, '%b %d, %Y')
    except:
        try:
            return datetime.datetime.strptime(string, '%m/%d/%y')
        except:
            pass
    return None


def audit_log_reason(user: discord.User, reason: str):
    return f'{user}: {reason}'


async def setup(bot):
    global loading
    await bot.add_cog(Moderation(bot))
    loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')


class WarmupActionView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @discord.ui.button(label='Apply to existing members')
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.edit_message(view=self)
        antispam = (await utility.get_server(interaction.guild)).get('antispam')
        warmup = antispam.get('warmup', 0)
        embed = interaction.message.embeds[0]
        muted = 0
        for member in interaction.guild.members:
            serverAge: datetime.datetime = discord.utils.utcnow() - member.joined_at
            if serverAge.second < warmup:
                muteTime = (member.joined_at + datetime.timedelta(seconds=warmup)) - discord.utils.utcnow()
                if muteTime > discord.utils.utcnow():
                    await self.bot.get_cog('Moderation').muteMembers(
                        [member],
                        member.guild.me,
                        duration=muteTime,
                        reason=f'[Antispam: Warmup] This new member will be able to begin chatting at {utility.DisguardStandardTimestamp(discord.utils.utcnow() + muteTime)}.',
                    )
                    muted += 1
        embed.description += f'\n\nApplied filters and muted {muted} members for now'
        await interaction.message.edit(embed=embed, view=self)
