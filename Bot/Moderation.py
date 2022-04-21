import collections
import typing
import discord
from discord.ext import commands
import database
import datetime
import Cyberlog #Used to prevent delete logs upon purging
import asyncio
import os
import traceback
import copy
import json

filters = {}
loading = None
newline = '\n'
qlf = '  '

blue = (0x0000FF, 0x6666ff)
orange = (0xD2691E, 0xffc966)

class PurgeObject(object):
    def __init__(self, message=None, botMessage=None, limit=100, author=[], contains=None, startsWith=None, endsWith=None, links=None, invites=None, images=None, embeds=None, mentions=None, bots=None, channel=[], files=None, reactions=None, appMessages=None, startDate=None, endDate=None, caseSensitive=False, cleanup=False, anyMatch=False):
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
        self.caseSensitive=caseSensitive
        self.cleanup = cleanup #delete user's message after?
        self.anyMatch = anyMatch #if true, purge if it matches any filter, else, purge if it matches all filters
        self.purgeCount = 0
        self.purgeStat = {0: 0, 1: 0, 2: 0}
        self.lastUpdate = None

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emojis = self.bot.get_cog('Cyberlog').emojis
        self.roleCache = {}
        self.permissionsCache = {}

    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    @commands.command()
    async def warmup(self, ctx: commands.Context, arg: str):
        '''A command to set the duration a member must remain in the server before chatting'''
        duration, unit = arg[:-1], arg[-1]
        # define multipliers to convert higher units into seconds
        if duration != '0':
            minutes = 60
            hours = 60 * minutes
            days = 24 * hours
            weeks = 7 * days
            # define relational dictionary
            conversion = {'s': 1, 'm': minutes, 'h': hours, 'd': days, 'w': weeks},
            units = {'s': 'second', 'm': 'minute', 'h': 'hour', 'd': 'day', 'w': 'week'}
            # now, set the final amount in seconds
            warmup = int(duration) * conversion[unit]
        else: warmup = 0
        await database.SetWarmup(ctx.guild, warmup)
        embed = discord.Embed(title='Warmup', description=f'Updated server antispam policy: Members must be in the server for **{duration} {units[unit]}{"s" if duration != 1 else ""}** before chatting')
        # view = WarmupActionView(self.bot)
        # await ctx.send(embed=embed, view=view)
        await ctx.send(embed=embed)

    @commands.has_guild_permissions(manage_channels=True)
    @commands.command()
    async def lock(self, ctx, member: discord.Member, *, reason=''):
        status = await ctx.send(f'{loading}Locking...')
        messages = []
        for c in ctx.guild.channels:
            try:
                if c.type[0] == 'text': await c.set_permissions(member, read_messages=False)
                elif c.type[0] == 'voice': await c.set_permissions(member, connect=False)
            except (discord.Forbidden, discord.HTTPException) as e: messages.append(f'Error editing channel permission overwrites for {c.name}: {e.text}')
        if len(reason) > 0:
            try: await member.send(f'You have been restricted from accessing channels in {ctx.guild.name}{f" because {reason}" if len(reason) > 0 else ""}')
            except (discord.Forbidden, discord.HTTPException) as e: messages.append(f'Error DMing {member.name}: {e.text}')
        await status.edit(content=f'{member.name} is now locked and cannot access any server channels{f" because {reason}" if len(reason) > 0 else ""}\n' + (f'Notes: {newline.join(messages)}' if len(messages) > 0 else ''))

    @commands.has_guild_permissions(manage_channels=True)
    @commands.command()
    async def unlock(self, ctx, member: discord.Member):
        status = await ctx.send(f'{loading}Unlocking...')
        for c in ctx.guild.channels: await c.set_permissions(member, overwrite=None)
        errorMessage = None
        try: await member.send(f'You may now access channels again in {ctx.guild.name}')
        except (discord.Forbidden, discord.HTTPException) as e: errorMessage = f'Unable to notify {member.name} by DM because {e.text}'
        await status.edit(content=f'{member.name} is now unlocked and can access channels again.{f"{newline}{newline}{errorMessage}" if errorMessage else ""}')

    @commands.has_guild_permissions(manage_roles=True, manage_channels=True)
    @commands.command()
    async def mute(self, ctx, members: commands.Greedy[discord.Member], duration=None, *, reason=''):
        '''Mutes the specified member(s) for a specified amount of time, if given
           Preliminary for v0.2.25.1 - very basic interface, snappy, takes members or list of members, no fancy UI, expand later by 0.2.26
        '''
        if len(members) == 0: return await ctx.send(f'{self.emojis["alert"]} | Please specify at least one member to mute\nFormat: `{self.bot.lightningLogging[ctx.guild.id]["prefix"]}mute [list of members to mute] [duration:optional] [reason:optional]`\nAcceptable arguments for member: [ID, Mention, name#discrim, name, nickname]\nDuration: 3d = 3 days, 6h30m = 6 hours 30 mins, etc. s=sec, m=min, h=hour, d=day, w=week, mo=month, y=year')
        if duration: duration = ParseDuration(duration)
        embed = discord.Embed(title=f'{self.emojis["muted"]}Muting {len(members)} member{"s" if len(members) != 1 else ""} for {duration if duration else "∞"}s', description=f"{self.emojis['loading']}\n", color=orange[self.colorTheme(ctx.guild)])
        message = await ctx.send(embed=embed)
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        results = await self.muteMembers(members, ctx.author, duration=duration, reason=reason)
        def nestMore(array):
            return f'\n'.join([f'{newline}{qlf}{qlf}{i}' for i in array]) if len(array) > 1 else f'{array[0]}' if len(array) == 1 else ''
        embed.description = '\n\n'.join([f'''{m}:\n{newline.join([f"{qlf}{k}: {newline.join([f'{qlf}{nestMore(v)}'])}" for k, v in n.items()])}''' if len(n) > 0 else '' for m, n in results.items()])
        embed.title = embed.title.replace('Muting', 'Mute')
        await message.edit(embed=embed)

    @commands.has_guild_permissions(manage_roles=True, manage_channels=True)
    @commands.command()
    async def unmute(self, ctx, members: commands.Greedy[discord.Member], *, reason=''):
        '''Unmuted the specified members'''
        if len(members) == 0: return await ctx.send(f'{self.emojis["alert"]} | Please specify at least one member to unmute\nFormat: `{self.bot.lightningLogging[ctx.guild.id]["prefix"]}unmute [list of members to unmute] [reason:optional]`\nAcceptable arguments for member: [ID, Mention, name#discrim, name, nickname]')
        embed = discord.Embed(title=f'{self.emojis["unmuted"]}Unmuting {len(members)} member{"s" if len(members) != 1 else ""}', description=f"{self.emojis['loading']}\n", color=orange[self.colorTheme(ctx.guild)])
        message = await ctx.send(embed=embed)
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        results = await self.unmuteMembers(members, ctx.author, {}, reason=reason)
        def nestMore(array):
            return f'\n'.join([f'{newline}{qlf}{qlf}{i}' for i in array]) if len(array) > 1 else f'{array[0]}' if len(array) == 1 else ''
        embed.description = '\n\n'.join([f'''{m}:\n{newline.join([f"{qlf}{k}: {newline.join([f'{qlf}{nestMore(v)}'])}" for k, v in n.items()])}''' if len(n) > 0 else '' for m, n in results.items()])
        embed.title = embed.title.replace('Unmuting', 'Unmute')
        await message.edit(embed=embed)

    @commands.has_guild_permissions(kick_members=True)
    @commands.command()
    async def kick(self, ctx, members: commands.Greedy[discord.Member], *, reason=''):
        '''Kicks the specified members'''
        if len(members) == 0: return await ctx.send(f'{self.emojis["alert"]} | Please specify at least one member to kick\nFormat: `{self.bot.lightningLogging[ctx.guild.id]["prefix"]}kick [list of members to kick] [reason:optional]`\nAcceptable arguments for member: [ID, Mention, name#discrim, name, nickname]')
        await ctx.trigger_typing()
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        embed = discord.Embed(title=f'👢Kick {len(members)} member{"s" if len(members) != 1 else ""}', description='', color=orange[self.colorTheme(ctx.guild)])
        for m in members:
            try: 
                if await database.ManageServer(m): raise Exception("You cannot kick a moderator")
                await m.kick(reason=reason)
                embed.description += f'{self.emojis["greenCheck"]} | Succesfully kicked {m}\n'
            except Exception as e: embed.description += f'{self.emojis["alert"]} | Error kicking {m}: {e}\n'
        await ctx.send(embed=embed)

    @commands.has_guild_permissions(ban_members=True)
    @commands.command()
    async def ban(self, ctx, users: commands.Greedy[typing.Union[discord.User, int]], deleteMessageDays: typing.Optional[int] = 0, *, reason=''):
        '''Bans the specified members'''
        if len(users) == 0: return await ctx.send(f'{self.emojis["alert"]} | Please specify at least one user to ban\nFormat: `{self.bot.lightningLogging[ctx.guild.id]["prefix"]}ban [list of users to ban] [deleteMessageDays:optional[int] = 0 ▷ must be 0 <= x <= 7] [reason:optional]`\nAcceptable arguments for user: [ID, Mention, name#discrim, name]\nUse a user\'s ID if you want to ban someone not in this server\n\nExample: `.ban {self.bot.user.mention} 5 Muted me for spamming` Would ban Disguard, delete its message sent within the past 5 days, with the reason "Muted me for spamming"')
        users = await self.UserProcessor(users)
        await ctx.trigger_typing()
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        embed = discord.Embed(title=f'{self.emojis["ban"]}Ban {len(users)} user{"s" if len(users) != 1 else ""}', description='', color=orange[self.colorTheme(ctx.guild)])
        for m in users:
            try: 
                member = ctx.guild.get_member(m.id)
                if member and await database.ManageServer(member): raise Exception("You cannot ban a moderator")
                await ctx.guild.ban(m, delete_message_days=deleteMessageDays, reason=reason)
                embed.description += f'{self.emojis["greenCheck"]} | Succesfully banned {m}\n'
            except Exception as e: embed.description += f'{self.emojis["alert"]} | Error banning {m}: {e}\n'
        await ctx.send(embed=embed)

    @commands.has_guild_permissions(ban_members=True)
    @commands.command()
    async def unban(self, ctx, users: commands.Greedy[typing.Union[discord.User, int]], *, reason=''):
        if len(users) == 0: return await ctx.send(f'{self.emojis["alert"]} | Please specify at least one user to unban\nFormat: `{self.bot.lightningLogging[ctx.guild.id]["prefix"]}unban [list of users to unban] [reason:optional]`\nAcceptable arguments for user: [ID, Mention, name#discrim, name]\nID is the only argument guaranteed to work, as that would be the only way I can retrieve a User not in any of my servers')
        users = await self.UserProcessor(users)
        await ctx.trigger_typing()
        reason = f'👮‍♂️: {ctx.author}\n{reason}'
        embed = discord.Embed(title=f'{self.emojis["unban"]}Unban {len(users)} user{"s" if len(users) != 1 else ""}', description='', color=orange[self.colorTheme(ctx.guild)])
        for u in users:
            try: 
                await ctx.guild.unban(u, reason=reason)
                embed.description += f'{self.emojis["greenCheck"]} | Succesfully unbanned {u}\n'
            except Exception as e: embed.description += f'{self.emojis["alert"]} | Error unbanning {u}: {e}\n'
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    @commands.command()
    async def purge(self, ctx, *args):
        '''Purge messages'''
        global filters
        current = copy.deepcopy(PurgeObject())
        filters[ctx.guild.id] = current
        if not GetManageMessagePermissions(ctx.guild.me) and ('purge:true' in args or len(args) == 1):
            return await ctx.send('I am unable to execute the purge command as I don\'t have manage message permissions')
            #await ctx.send('Temporarily bypassing permission restrictions')
        if len(args) < 1:
            timeout=discord.Embed(title='Purge command',description='Timed out')
            path = 'Indexes/{}/{}'
            cancel=discord.Embed(title='Purge command',description='Cancelled')
            url='https://cdn.discordapp.com/emojis/605060517861785610.gif'
            embed=discord.Embed(title='Purge command',description='Welcome to the interactive purge command! You\'ll be taken through a setup walking you through the purging features I have.\n\n',timestamp=datetime.datetime.utcnow(),color=blue[self.colorTheme(ctx.guild)])
            embed.description+='First, what channel(s) are you thinking of purging? Make sure the channel(s) are hyperlinked. To purge from this channel ({}), type `here`, to purge from all text channels, type `all`'.format(ctx.channel.mention)
            embed.set_footer(text='Type cancel to cancel the command. Timeout is 120s')
            embed.set_author(name='Waiting for input')
            message = await ctx.send(embed=embed)
            current.botMessage = message
            current.mentions = ctx.message
            messages = []
            def channels(m): return m.channel == ctx.channel and m.author==ctx.author and (len(m.channel_mentions) > 0 or any(s in m.content.lower() for s in ['a', 'h', 'cancel']))
            try: post = await self.bot.wait_for('message',check=channels, timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait')
            await message.edit(embed=embed)
            embed.set_author(name='Waiting for input')
            channels = []
            if len(post.channel_mentions) > 0: channels += post.channel_mentions
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'h' in post.content.lower(): channels.append(ctx.channel)
            if 'a' in post.content.lower(): channels = ctx.guild.text_channels
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            counts = []
            for channel in channels:
                with open(f'Indexes/{channel.guild.id}/{channel.id}.json') as f: counts.append(len(json.load(f).keys()))
            total = sum(counts)
            current.channel=channels
            embed.description='Ok cool, {} for a total of {} messages BTW.\n\nWould you like me to index the channel(s) you selected to let you know how many messages match your filters as we progress through setup? This may take a long time if the channel(s) has/have lots of messages. If it takes longer than 5 minutes, I\'ll tag you when I\'m done. Type `yes` or `no`'.format(', '.join(['{} has {} posts'.format(channels[c].mention, counts[c]) for c in range(len(channels))]), total)
            await message.edit(embed=embed)
            def index(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content.lower() for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=index,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            now = datetime.datetime.utcnow()
            embed.set_author(name='Please wait',icon_url=url)
            if 'y' in post.content:
                embed.set_author(name='Indexing messages',icon_url=url)
                #await indexMessages(message, embed, total, channels)
                loadingBar = ["o-------------------", "-o------------------", "--o-----------------", "---o----------------", "----o---------------", "-----o--------------", "------o-------------", "-------o------------", "--------o-----------", "---------o----------", "----------o---------", "-----------o--------", "------------o-------", "-------------o------", "--------------o-----", "---------------o----", "----------------o---", "-----------------o--", "------------------o-", "-------------------o"]
                embed.description='0/{} messages, 0/{} channels\n\n0% {}\n\n0 messages per second, Time remaining: N/A'.format(total, len(channels), loadingBar[0])
                await message.edit(embed=embed)
                messages = []
                status={'c': 0, 'm': 0, 'last': 0}
                lastUpdate = datetime.datetime.now()
                for c in channels:
                    status['c']+=1
                    async for m in c.history(limit=None):
                        status['m']+=1
                        if (datetime.datetime.now() - lastUpdate).seconds > 3:
                            embed.description='{}/{} messages, {}/{} channels\n\n{}% {}'.format(status.get('m'),total, status.get('c'),len(channels), 100*round(status.get('m')/total, 2), loadingBar[round(19 * (round((status.get('m') / total), 2)))] if status.get('m') < total else loadingBar[19])
                            embed.description+='\n\n{} messages per second, Time remaining: {}'.format(round((status.get('m') - status.get('last')) / 3), ETA(status.get('m'), round((status.get('m') - status.get('last')) / 3), total))
                            await message.edit(embed=embed)
                            lastUpdate = datetime.datetime.now()
                            status['last'] = status.get('m')
                        messages.append(m)
            embed.set_author(name='Waiting for input')
            embed.set_footer(text='Type cancel to cancel the command. Timeout is 120s')
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            if (datetime.datetime.utcnow() - now).seconds / 60 > 5: await ctx.channel.send('{}, I\'m done indexing'.format(ctx.author.mention),delete_after=10)
            embed.description='Next up, are you interested in purging messages containing certain text? Type `yes` to be taken to setup for those options or `no` to move on and skip this part.'
            await message.edit(embed=embed)
            def textCondition(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content.lower() for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=textCondition,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            embed.set_author(name='Waiting for input')
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'n' in post.content.lower():
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
                embed.add_field(name='Messages to be purged',value=0)
            if 'y' in post.content.lower():
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
                embed.description='Would you like to purge only messages containing certain text? Type the text to check for or `skip` to skip this step.'
                await message.edit(embed=embed)
                def contains(m): return m.channel == ctx.channel and m.author==ctx.author
                try: post = await self.bot.wait_for('message',check=contains,timeout=120)
                except asyncio.TimeoutError: return await message.edit(embed=timeout)
                embed.set_author(name='Please wait',icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
                if 'skip' not in post.content.lower(): current.contains=post.content
                if messages: embed.add_field(name='Messages to be purged',value=len([m for m in messages if PurgeFilter(m)]))
                embed.set_author(name='Waiting for input')
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
                if current.contains is not None: 
                    embed.description='Right now, messages matching the filter will be purged regardless of capitalization. Would you like the filter to be case sensitive and only purge messages matching the capitalization you specified? Type `yes` or `no`'
                    await message.edit(embed=embed)
                    def caseSen(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content.lower() for s in ['y', 'n', 'cancel'])
                    try: post = await self.bot.wait_for('message',check=caseSen,timeout=120)
                    except asyncio.TimeoutError: return await message.edit(embed=timeout)
                    embed.set_author(name='Please wait',icon_url=url)
                    await message.edit(embed=embed)
                    embed.set_author(name='Waiting for input')
                    if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
                    if 'y' in post.content.lower(): current.caseSensitive = True
                    if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                    try:
                        self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                        await post.delete()
                    except: pass
                embed.description='Would you like to purge only messages that *start with* a certain text sequence? (Type a text sequence or `skip`)'
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
                embed.set_author(name='Waiting for input',icon_url=url)
                await message.edit(embed=embed)
                def startsWith(m): return m.channel == ctx.channel and m.author==ctx.author
                try: post = await self.bot.wait_for('message',check=startsWith,timeout=120)
                except asyncio.TimeoutError: return await message.edit(embed=timeout)
                embed.set_author(name='Please wait',icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
                if 'skip' not in post.content.lower(): current.startsWith = post.content
                if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                embed.description='Would you like to purge only messages that *end with* a certain text sequence? (Type a text sequence or `skip`)'
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
                embed.set_author(name='Waiting for input',icon_url=url)
                await message.edit(embed=embed)
                def endsWith(m): return m.channel == ctx.channel and m.author==ctx.author
                try: post = await self.bot.wait_for('message',check=endsWith,timeout=120)
                except asyncio.TimeoutError: return await message.edit(embed=timeout)
                embed.set_author(name='Please wait',icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
                if 'skip' not in post.content.lower(): current.endsWith = post.content
                if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                embed.set_author(name='Waiting for input')
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
            embed.description='Would you like to purge only messages belonging to bots/humans? Type `bots` to purge only bot messages, `humans` to purge only human messages, and `both` to purge any messages'
            await message.edit(embed=embed)
            def bots(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['bots', 'h', 'both', 'cancel'])
            try: post = await self.bot.wait_for('message',check=bots,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            elif 'bots' in post.content.lower(): current.bots=0
            elif 'both' in post.content.lower(): current.bots=2
            elif 'human' in post.content.lower(): current.bots=1
            if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input')
            embed.description='Would you like to purge only messages belonging to a certain author or set of authors? Enter comma and space (`, `) separated usernames, IDs, or mentions, or type `skip`'
            await message.edit(embed=embed)
            def author(m): return m.channel == ctx.channel and m.author==ctx.author
            try: post = await self.bot.wait_for('message',check=author,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            embed.description=''
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            embed.description=''
            if 'skip' not in post.content.lower(): 
                if ',' in post.content: ppl = ', '.split(post.content)
                else: ppl = [post.content]
                mem = []
                for p in ppl:
                    try:
                        result = self.bot.get_cog('Cyberlog').FindMember(ctx.guild, p)
                        if result is not None: mem.append(result)
                    except Exception as e: print(e)
                current.author = mem
                embed.description='I matched these message authors: {}.\n'.format(', '.join([m.name for m in mem]))
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
                if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description+='Would you like to purge only messages that contains URLs? Type yes/no'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)
            def links(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=links,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'y' in post.content.lower(): current.links=True
            if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description='Would you like to purge only messages that contain discord.gg invites? (yes/no)'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)
            def invites(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=invites,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'y' in post.content.lower(): current.invites=True
            if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description='Would you like to purge only messages that contain attachments? Type `image` to purge messages with *image* attachments, `file` to purge messages with *non image* attachments, `both` to purge messages with any external attachments, or `skip` to skip this step'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)
            def images(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['i', 'f', 'b', 'cancel', 'skip'])
            try: post = await self.bot.wait_for('message',check=images,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'skip' not in post.content.lower():
                if 'f' in post.content.lower(): current.files=True #F first cuz 'file' has an 'i' in it
                elif 'i' in post.content.lower(): current.images=True
                elif 'b' in post.content.lower():
                    current.files=True
                    current.images=True
            if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description='Would you like to purge only messages that contain embeds? This only applies to messages sent by bots. (Yes/no)'
            embed.set_author(name='Waiting for input')
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            await message.edit(embed=embed)
            def embeds(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=embeds,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'y' in post.content.lower(): current.embeds=True
            if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description='Would you like to purge only messages that contain member mentions e.g. @person? (Yes/no)'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)
            def mentions(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=mentions,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'y' in post.content.lower(): current.mentions=True
            if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description='Would you like to purge only messages that have reactions on them?'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)
            def reactions(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=reactions,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'y' in post.content.lower(): current.reactions=True
            if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description='Would you like to purge only messages that contain activity messages (Spotify invites, Game invites, etc)?'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)
            def activity(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=activity,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'y' in post.content.lower(): current.appMessages=True
            if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description='Are you interested in purging messages that were posted before, during, or after a certain date? Type `yes` to enter setup for these options or `no` to skip this part'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input')
            await message.edit(embed=embed)
            def dates(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['y', 'n', 'cancel'])
            try: post = await self.bot.wait_for('message',check=dates,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'y' in post.content.lower():
                embed.description='Would you like to purge only messages were posted *after* a certain date? Type `skip` or a date in a format matching `Feb 1, 2019` or `2/1/19`'
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
                embed.set_author(name='Waiting for input',icon_url=url)
                await message.edit(embed=embed)
                def after(m): return m.channel == ctx.channel and m.author==ctx.author
                try: post = await self.bot.wait_for('message',check=after,timeout=120)
                except asyncio.TimeoutError: return await message.edit(embed=timeout)
                embed.set_author(name='Please wait',icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
                current.startDate=ConvertToDatetime(post.content)
                if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
                embed.description='Would you like to purge only messages posted *before* a certain date? Type `skip` or a date in a format matching `Feb 1, 2019` or `2/1/19`. If you want to target a single day for the purge, set this to the day before what you used in the previous step'
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                    await post.delete()
                except: pass
                embed.set_author(name='Waiting for input',icon_url=url)
                await message.edit(embed=embed)
                def before(m): return m.channel == ctx.channel and m.author==ctx.author
                try: post = await self.bot.wait_for('message',check=before,timeout=120)
                except asyncio.TimeoutError: return await message.edit(embed=timeout)
                embed.set_author(name='Please wait',icon_url=url)
                await message.edit(embed=embed)
                if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
                current.endDate=ConvertToDatetime(post.content)
                if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            embed.description='Finally, how many messages would you like me to purge? Type `skip` to purge all messages matching the filter'
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            embed.set_author(name='Waiting for input',icon_url=url)
            await message.edit(embed=embed)
            def count(m): return m.channel == ctx.channel and m.author==ctx.author
            try: post = await self.bot.wait_for('message',check=count,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            embed.set_author(name='Please wait',icon_url=url)
            await message.edit(embed=embed)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            if 'skip' in post.content.lower():
                limited=False 
                current.limit=None
                if messages: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            else: 
                current.limit=int(post.content)
                limited=True
                if messages: embed.set_field_at(0, name='Messages to be purged', value='Up to {}'.format(current.limit))
            embed.description=''
            embed.set_author(name='One sec...',icon_url=url)
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            await message.edit(embed=embed)
            embed.description='__Filters:__\nCount: {} messages\n'.format('∞' if current.limit is None else current.limit)
            embed.description+=PreDesc(ctx.guild)
            if messages and not limited: embed.set_field_at(0, name='Messages to be purged', value=len([m for m in messages if PurgeFilter(m)]))
            elif messages and limited: embed.set_field_at(0, name='Messages to be purged', value='Up to {}'.format(current.limit))
            embed.set_author(name='Waiting for input',icon_url=url)
            embed.description+='\n\nIf you are ready to purge, type `purge`, otherwise type `cancel`'
            await message.edit(embed=embed)
            def ready(m): return m.channel == ctx.channel and m.author==ctx.author and any(s in m.content for s in ['purge', 'cancel'])
            try: post = await self.bot.wait_for('message',check=ready,timeout=120)
            except asyncio.TimeoutError: return await message.edit(embed=timeout)
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            limit = current.limit
            embed.description='Scanned 0/{}\nPurged 0/{}'.format(len(messages) if messages else total, limit)
            embed.set_author(name='Purging messages',icon_url=url)
            embed.set_footer(text='This will take longer than other bots\' purge commands because Disguard uses a custom purge method due to limitations with Discord\'s built in one :/')
            await message.edit(embed=embed)
            started = datetime.datetime.now()
            lastUpdate = datetime.datetime.now()
            counter = 0
            if messages:
                for post in messages:
                    counter+=1
                    if current.limit == 0: break #Reached purge limit
                    if (datetime.datetime.now() - lastUpdate).seconds > 3:
                        embed.description='Scanned {}/{}\nPurged {}/{}'.format(counter, len(messages), current.purgeStat.get(2), limit)
                        await message.edit(embed=embed)
                        lastUpdate = datetime.datetime.now()
                    result = await self.SuperPurge(post)
                    if result == 0: current.purgeStat[0]+=1 #Didn't pass the filter
                    elif result==1: current.purgeStat[1]+=1 #Can't delete for whatever reason
                    else: 
                        current.purgeStat[2]+=1 #2 = successful deletion
                        if current.limit is not None: current.limit-=1
            else:
                for c in channels:
                    async for post in c.history(limit=None):
                        counter+=1
                        if current.limit == 0: break
                        if (datetime.datetime.now() - lastUpdate).seconds > 3:
                            embed.description='Scanned {}/{}\nPurged {}/{}'.format(counter, total, current.purgeStat.get(2), limit)
                            elapsed = datetime.datetime.now() - started
                            if elapsed.seconds < 60: embed.description+='\nTime taken: {} seconds'.format(elapsed.seconds)
                            else: embed.description+='\nTime taken: {} minutes'.format(round(elapsed.seconds / 60))
                            await message.edit(embed=embed)
                            lastUpdate = datetime.datetime.now()
                        result = await self.SuperPurge(post)
                        if result == 0: current.purgeStat[0]+=1 #Didn't pass the filter
                        elif result==1: current.purgeStat[1]+=1 #Can't delete for whatever reason
                        else: 
                            current.purgeStat[2]+=1 #2 = successful deletion
                            if current.limit is not None: current.limit-=1
            timeTaken = datetime.datetime.now() - started
            embed.set_author(name='Thanks for purging!', icon_url='https://cdn.discordapp.com/emojis/569191704523964437.png')
            maximum = '∞' if limit is None else limit
            embed.description='Purged {} out of {} requested messages ({}%)\n'.format(current.purgeStat.get(2), maximum, '∞' if maximum == '∞' else round(current.purgeStat.get(2) / maximum * 100))
            embed.description+='Purged {} out of {} possible messages ({}%)\n'.format(current.purgeStat.get(2), len(messages), '∞' if message is None else round(current.purgeStat.get(2) / len(messages) * 100))
            if timeTaken.seconds < 60: embed.description+='Time taken: {} seconds'.format(timeTaken.seconds)
            else: embed.description+='Time taken: {} minutes'.format(round(timeTaken.seconds / 60))
            embed.set_footer(text='If you have feedback, head to bit.ly/2disguard to find more information')
            if len(embed.fields) > 0: embed.remove_field(0)
            return await message.edit(embed=embed)
        current.botMessage = await ctx.send(str(loading)+"Parsing filters...")
        actuallyPurge = False
        current.channel.append(ctx.channel)
        current.message = ctx.message
        for arg in args:
            meat = arg[arg.find(":")+1:].strip()
            body = arg.lower()
            if "count" in body: current.limit = int(meat)
            elif "purge" in body: actuallyPurge = True if "true" in meat.lower() else False
            elif "author" in body: current.author.append(ctx.guild.get_member_named(meat))
            elif "contains" in body: current.contains = meat
            elif "startswith" in body: current.startsWith = meat
            elif "endswith" in body: current.endsWith = meat
            elif "links" in body: current.links = True if "true" in meat.lower() else False
            elif "invites" in body: current.invites = True if "true" in meat.lower() else False
            elif "images" in body: current.images = True if "true" in meat.lower() else False
            elif "embeds" in body: current.embeds = True if "true" in meat.lower() else False
            elif "mentions" in body: current.mentions = True if "true" in meat.lower() else False
            elif "bots" in body: current.bots = 0 if "true" in meat.lower() else False
            elif "channel" in body: current.channel[0] = ctx.message.channel_mentions[0] if len(ctx.message.channel_mentions) > 0 else ctx.channel
            elif "attachments" in body: current.files = True if "true" in meat.lower() else False
            elif "reactions" in body: current.reactions = True if "true" in meat.lower() else False
            elif "external_messages" in body: current.appMessages = True if "true" in meat.lower() else False
            elif "after" in body: current.startDate = ConvertToDatetime(meat)
            elif "before" in body: current.endDate = ConvertToDatetime(meat)
            else:
                try: 
                    current.limit = int(body) #for example, .purge 10 wouldn't fall into the above categories, but is used due to rapid ability
                except:
                    current = None
                    return await ctx.send("I don't think **"+body+"** is a number... please try again, or use the website documentation for filters")
                actuallyPurge = True
            current.limit += 2
        if actuallyPurge:
            await current.botMessage.edit(content=str(loading)+"Purging...")
            Cyberlog.beginPurge(ctx.guild)
            messages = await current.channel[0].purge(limit=current.limit, check=PurgeFilter, before=current.endDate, after=current.startDate)
            Cyberlog.endPurge(ctx.guild)
            await current.botMessage.edit(content="**Successfully purged "+str(len(messages) - 1)+" messages :ok_hand:**",delete_after=5)
        else:
            await current.botMessage.edit(content=str(loading)+"Indexing... please be patient")
            count = 0
            async for message in current.channel[0].history(limit=current.limit, before=current.endDate, after=current.startDate):
                if PurgeFilter(message): count += 1
            embed=discord.Embed(title="Purge pre-scan",description="__Filters:__\nLimit: "+str(current.limit)+" messages\n{}".format(PreDesc(ctx.guild)),color=blue[self.colorTheme(ctx.guild)], timestamp=datetime.datetime.utcnow())
            embed.set_footer(text="To actually purge, copy & paste your command message, but add 'purge:true' to the filters")
            embed.description+="\n**"+str(count)+" messages matched the filters**"
            await current.botMessage.edit(content=None,embed=embed)
        current = None

    async def SuperPurge(self, m: discord.Message):
        if not PurgeFilter(m): return 0
        try:
            self.bot.get_cog('Cyberlog').AvoidDeletionLogging(m) 
            await m.delete()
        except: return 1
        return 2
    
    def colorTheme(self, s: discord.Guild):
        return self.bot.lightningLogging[s.id]['colorTheme']

    async def UserProcessor(self, users):
        returnQueue = []
        for user in users:
            if type(user) is discord.User: returnQueue.append(user)
            else:
                try: returnQueue.append(await self.bot.fetch_user(user))
                except discord.NotFound: pass
        return returnQueue

    async def muteMembers(self, members, author, *, duration=None, reason=None, harsh=False, waitToUnmute=True, muteRole=None):
        '''Applies automated mute to the given member, returning a status tuple (bool:success, string explanation)'''
        '''Harsh: If True, apply permission overwrites to each channel for this member in addition to for the mute role'''
        # Vars
        g = members[0].guild
        results = {'Notes': []} #0 holds notes
        #First: Check if we have an automute role stored
        if not muteRole:
            muteRole = g.get_role(self.bot.lightningLogging[g.id]['antispam'].get('automuteRole', 0))
            #If we don't have a mute role, we gotta make one
            if not muteRole:
                try: muteRole = await g.create_role(name='Disguard AutoMute', reason='This role will be used when Disguard needs to mute a member. As long as this role exists, its ID will be stored in my database. You may edit the name of this role as you wish.')
                except Exception as e: 
                    results['Notes'].append(f'{self.emojis["alert"]} | Unable to mute member{"s" if len(members) != 1 else ""} - error during AutoMute role creation: {type(e).__name__}: {e}')
                    return results
                asyncio.create_task(database.SetMuteRole(g, muteRole))
        #Move the mute role's position to the position right below Disguard's top role, if it's not already there
        if muteRole.position < g.me.top_role.position - 1:
            try: await muteRole.edit(position=g.me.top_role.position - 1)
            except Exception as e: results['Notes'].append(f'Unable to move the AutoMute role higher in the rolelist, please do this manually: {type(e).__name__}: {e}')
        #Check all channels to make sure the overwrites are correct, along with removing member permissions from the channel
        permissionsTaken = collections.defaultdict(dict)
        memberRolesTaken = {}
        for c in g.text_channels:
            if c.overwrites_for(muteRole).send_messages != False:
                try: asyncio.create_task(c.set_permissions(muteRole, send_messages=False))
                except Exception as e: results['Notes'].append(f'{self.emojis["alert"]} | #{c.name} (🚩{muteRole.name}): `{type(e).__name__}: {e}`')
            for m in members:
                results[m] = {'Channel Permission Overwrites': [], 'Add Mute Role': [], 'Cache/Data Management': []}
                if harsh and c.overwrites_for(m).send_messages != False:
                    try: 
                        asyncio.create_task(c.set_permissions(m, send_messages=False))
                        permissionsTaken[str(m.id)][str(c.id)] = (c.overwrites.get(m).pair()[0].value, c.overwrites.get(m).pair()[1].value) if c.overwrites.get(m) else (0, 0)
                    except Exception as e: results[m]['Channel Permission Overwrites'].append(f'{self.emojis["alert"]} | #{c.name}: `{type(e).__name__}: {e}`')
                elif not harsh and c.overwrites_for(m):
                    try: 
                        asyncio.create_task(c.set_permissions(m, overwrite=None))
                        permissionsTaken[str(m.id)][str(c.id)] = (c.overwrites.get(m).pair()[0].value, c.overwrites.get(m).pair()[1].value) if c.overwrites.get(m) else (0, 0)
                    except Exception as e: results[m]['Channel Permission Overwrites'].append(f'{self.emojis["alert"]} | #{c.name}: {type(e).__name__}: {e}')
                if len(results[m]['Channel Permission Overwrites']) == 0: results[m]['Channel Permission Overwrites'].append(f'{self.emojis["greenCheck"]}')
        #Since we're removing most of the member's roles to enforce this mute, we need to keep track of the changes
        muteTimedEvents = {}
        for m in members:
            try:
                memberRolesTaken[m.id] = [r for r in m.roles if r.id != g.default_role.id]
                self.roleCache[f'{m.guild.id}_{m.id}'] = memberRolesTaken[m.id]
                self.permissionsCache[f'{m.guild.id}_{m.id}'] = permissionsTaken[str(m.id)]
                try:
                    #if muteRole.position > author.top_role.position:
                    #    raise discord.Forbidden("Your top role is below the mute role; operation aborted")
                    if author.top_role.position < m.top_role.position:
                        raise discord.Forbidden("You can't mute someone with a higher role than you")
                    await m.edit(roles=[muteRole], reason=reason)
                    results[m]['Add Mute Role'].append(f'{self.emojis["greenCheck"]}')
                except Exception as e: results[m]['Add Mute Role'].append(f'{self.emojis["alert"]} | `{type(e).__name__}: {e}`')
                if duration:
                    muteTimedEvents[m.id] = {'type': 'mute', 'target': m.id, 'flavor': reason, 'role': muteRole.id, 'roleList': [r.id for r in memberRolesTaken[m.id]], 'permissionsTaken': permissionsTaken[str(m.id)], 'expires': datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)}
                    asyncio.create_task(database.AppendTimedEvent(g, muteTimedEvents[m.id]))
                results[m]['Cache/Data Management'].append(f'{self.emojis["greenCheck"]}')
            except Exception as e: results[m]['Cache/Data Management'].append(f'{self.emojis["alert"]} | `{type(e).__name__}: {e}`')
        asyncio.create_task(database.SetMuteCache(m.guild, members, memberRolesTaken))
        asyncio.create_task(database.SetPermissionsCache(m.guild, members, permissionsTaken))
        if duration and waitToUnmute: asyncio.create_task(self.waitToUnmute(members, author, muteTimedEvents, datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)))
        return results

    async def waitToUnmute(self, members, author, events, expires, reason=None):
        await discord.utils.sleep_until(expires)
        await self.unmuteMembers(members, author, events, reason=reason)

    async def unmuteMembers(self, members, author, events, reason=None):
        #Note: Possibly make use of discord.Object to reduce iteration counts and running time
        results = {}
        removedRoles = {}
        removedOverwrites = {}
        for m in members: 
            try:
                results[m] = {'Cache/Data Management': [], 'Remove Mute Role': [], 'Channel Permission Overwrites': []}
                try:
                    #if muteRole.position > author.top_role.position:
                    #    raise discord.Forbidden("Your top role is below the mute role; operation aborted")
                    if author.top_role.position < m.top_role.position:
                        raise discord.Forbidden("You can't unmute someone with a higher role than you")
                    await m.edit(roles=removedRoles, reason=reason)
                    results[m]['Remove Mute Role'].append(f'{self.emojis["greenCheck"]}')
                except Exception as e: results[m]['Remove Mute Role'].append(f'{self.emojis["alert"]} | `{type(e)}: {e}`')
                if events and events.get(m.id): asyncio.create_task(database.RemoveTimedEvent(m.guild, events[m.id]))
                removedRoles[m.id] = copy.deepcopy(self.roleCache.get(f'{m.guild.id}_{m.id}')) or [m.guild.get_role(r) for r in self.bot.get_cog('Cyberlog').getServerMember(m).get('roleCache', [])]
                removedOverwrites[m.id] = copy.deepcopy(self.permissionsCache.get(f'{m.guild.id}_{m.id}', {})) or self.bot.get_cog('Cyberlog').getServerMember(m).get('permissionsCache', {})
                if self.roleCache.get(f'{m.guild.id}_{m.id}'): self.roleCache.pop(f'{m.guild.id}_{m.id}')
                if self.permissionsCache.get(f'{m.guild.id}_{m.id}'): self.permissionsCache.pop(f'{m.guild.id}_{m.id}')
                results[m]['Cache/Data Management'].append(f'{self.emojis["greenCheck"]}')
            except Exception as e: results[m]['Cache/Data Management'].append(f'{self.emojis["alert"]} | `{type(e)}: {e}`')
        asyncio.create_task(database.SetMuteCache(m.guild, members, []))
        asyncio.create_task(database.SetPermissionsCache(m.guild, members, []))
        for c in m.guild.text_channels:
            for m in members:
                try:
                    if m.id in [o.id for o in c.overwrites.keys()] and str(c.id) not in removedOverwrites[m.id].keys(): asyncio.create_task(c.set_permissions(m, overwrite=None))
                    elif str(c.id) in removedOverwrites[m.id].keys(): 
                        currentOverwrite = removedOverwrites[m.id].get(str(c.id), (0, 0))
                        asyncio.create_task(c.set_permissions(m, overwrite=discord.PermissionOverwrite.from_pair(discord.Permissions(currentOverwrite[0]), discord.Permissions(currentOverwrite[1]))))
                    if len(results[m]['Channel Permission Overwrites']) == 0: results[m]['Channel Permission Overwrites'].append(f'{self.emojis["greenCheck"]}')
                except Exception as e: 
                    results[m]['Channel Permission Overwrites'].append(f'{self.emojis["alert"]} | `{type(e)}: {e}`')
        return results

def PurgeFilter(m: discord.Message):
    '''Used to determine if a message should be purged'''
    current = filters.get(m.guild.id)
    if m.pinned: 
        return False
    if m.id == current.botMessage.id:
        return False
    if current.contains is not None:
        if not current.caseSensitive:
            if current.contains.lower() not in m.content.lower(): return False
        else:
            if current.contains not in m.content: return False
    if len(current.author) > 0: 
        if not any(a == m.author for a in current.author): return False
    if current.startsWith is not None:
        if not m.content.startswith(current.startsWith):
            return False
    if current.endsWith is not None:
        if not m.content.endswith(current.endsWith):
            return False
    if current.links is True:
        if "https://" not in m.content and "http://" not in m.content:
            return False
    if current.invites is True:
        if "discord.gg/" not in m.content:
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
        if current.bots == 0: #Purge only bot messages
            if not m.author.bot: return False
        if current.bots == 1: #Purge only human messages
            if m.author.bot: return False
    if current.files is True:
        if len(m.attachments) < 1 or m.attachments[0].width is not None:
            return False
    if current.reactions is True:
        if len(m.reactions) < 1:
            return False
    if current.appMessages is True:
        if m.activity is None:
            return False
    if current.startDate is not None and m.created_at < current.startDate: return False
    if current.endDate is not None and m.created_at > current.endDate: return False
    return True


def PreDesc(g: discord.Guild):
    current = filters.get(g.id)
    desc=''
    if len(current.author) > 0: desc += "Author(s): {}\n".format(', '.join([a.name for a in current.author]))
    if len(current.channel) > 0: desc += "In channel(s): {}\n".format(', '.join([c.mention for c in current.channel]))
    if current.contains is not None: desc += "Contains: "+current.contains+"\n"
    if current.startsWith is not None: desc += "Starts with: "+current.startsWith+"\n"
    if current.endsWith is not None: desc += "Ends with: "+current.endsWith+"\n"
    if current.startDate is not None: desc += "Posted after: "+current.startDate.strftime("%b %d, %Y")+"\n"
    if current.endDate is not None: desc += "Posted before: "+current.endDate.strftime("%b %d, %Y")+"\n"
    if current.links is True: desc += "Contains URLs\n"
    if current.invites is True: desc += "Contains server invites\n"
    if current.images is True: desc += "Contains Images\n"
    if current.embeds is True: desc += "Contains URLs\n"
    if current.mentions is True: desc += "Contains @mentions\n"
    if current.bots == 0: desc += "Authored by bots\n"
    elif current.bots == 1: desc += "Authored by humans\n"
    if current.files is True: desc += "Contains files\n"
    if current.reactions is True: desc += "Contains reactions\n"
    if current.appMessages is True: desc += "Contains external invites (e.g. Spotify)\n"
    return desc

def ETA(current, rate, total):
    quotient = round((total - current) / rate)
    if quotient > 60: return '{} minutes'.format(quotient / 60)
    else: return '{} seconds'.format(quotient)


def GetManageMessagePermissions(member: discord.Member):
    for role in member.roles:
        if role.permissions.manage_messages or role.permissions.administrator:
            return True
    return False

def ConvertToDatetime(string: str):
    try:
        return datetime.datetime.strptime(string, "%b %d, %Y")
    except:
        try:
            return datetime.datetime.strptime(string, "%m/%d/%y")
        except:
            pass
    return None

def ParseDuration(string):
    numbers = '1234567890'
    startIndex = 0
    i = 0
    duration = 0
    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800, 'mo': 2628000, 'y': 31536000}
    while i < len(string):
        if string[i] not in numbers:
            duration += int(string[startIndex:i]) * multipliers[string[i].lower()]
            startIndex = i
        i += 1
    if len(string) > 0 and duration == 0:
        try: duration += int(string)
        except: pass
    return duration

def setup(bot):
    global loading
    bot.add_cog(Moderation(bot))
    loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')
