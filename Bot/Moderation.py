import discord
from discord.ext import commands
import database
import datetime
import Cyberlog #Used to prevent delete logs upon purging
import asyncio
import os
import traceback

filters = {}
loading = None

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

    @commands.has_guild_permissions(manage_channels=True)
    @commands.command()
    async def unlock(self, ctx, member: discord.Member):
        status = await ctx.send(f'{loading}Unlocking...')
        for c in ctx.guild.text_channels: await c.set_permissions(m, overwrite=None)
        await status.edit(content=f'{m.name} is now unlocked and can access channels again.')

    @commands.command()
    async def purge(self, ctx, *args):
        '''Purge messages'''
        global current
        global loading
        global filters
        filters[ctx.guild.id] = PurgeObject()
        current = filters.get(ctx.guild.id)
        if not (GetManageMessagePermissions(ctx.author) and GetManageMessagePermissions(ctx.guild.me)) and ('purge:true' in args or len(args) == 1):
            return await ctx.send("Both you and I must have Manage Message permissions to utilize the purge command")
            #await ctx.send('Temporarily bypassing permission restrictions')
        if len(args) < 1:
            #return await ctx.send('Please refer to my help site for usage. THis is a placeholder message; interactive command will be out soon')
            timeout=discord.Embed(title='Purge command',description='Timed out')
            path = 'Indexes/{}/{}'
            cancel=discord.Embed(title='Purge command',description='Cancelled')
            url='https://cdn.discordapp.com/emojis/605060517861785610.gif'
            embed=discord.Embed(title='Purge command',description='Welcome to the interactive purge command! You\'ll be taken through a setup walking you through the purging features I have.\n\n',timestamp=datetime.datetime.utcnow(),color=discord.Color.blue())
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
            if 'h' in post.content.lower(): channels.append(ctx.channel)
            if 'a' in post.content.lower(): channels = ctx.guild.text_channels
            if 'cancel' in post.content.lower(): return await message.edit(embed=cancel)
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(post) 
                await post.delete()
            except: pass
            counts = [len(os.listdir(path.format(channel.guild.id, channel.id))) for channel in channels]
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
        try:
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
                embed=discord.Embed(title="Purge pre-scan",description="__Filters:__\nLimit: "+str(current.limit)+" messages\n{}".format(PreDesc(ctx.guild)),color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
                embed.set_footer(text="To actually purge, copy & paste your command message, but add 'purge:true' to the filters")
                embed.description+="\n**"+str(count)+" messages matched the filters**"
                await current.botMessage.edit(content=None,embed=embed)
            current = None
        except Exception as e:
            await ctx.send("Error - send this to my dev to decode:\n"+str(e))

    async def SuperPurge(self, m: discord.Message):
        if not PurgeFilter(m): return 0
        try:
            self.bot.get_cog('Cyberlog').AvoidDeletionLogging(m) 
            await m.delete()
        except: return 1
        return 2

def PurgeFilter(m: discord.Message):
    '''Used to determine if a message should be purged'''
    current = filters.get(m.guild.id)
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

def setup(bot):
    global loading
    bot.add_cog(Moderation(bot))
    loading = bot.get_emoji(573298271775227914)
