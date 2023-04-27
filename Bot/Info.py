'''Holds all code relating to Disguard's info command'''
import collections
import typing
import psutil
import cpuinfo
import utility
import discord
from discord.ext import commands
import asyncio
import aiofiles
import datetime
import emoji
import json
import Cyberlog
import Birthdays
import lightningdb

indexes = 'Indexes'
qlf = '  ' #Two special characters to represent quoteLineFormat
NEWLINE='\n'
newlineQuote = '\n> '

green = (0x008000, 0x66ff66)
blue = (0x0000FF, 0x6666ff)
red = (0xff0000, 0xff6666)
orange = (0xD2691E, 0xffc966)
yellow = (0xffff00, 0xffff66)

class InfoResult(object):
    def __init__(self, obj, mainKey, relevance):
        self.obj = obj
        self.mainKey = mainKey
        self.relevance = relevance

class Info(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.emojis: typing.Dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis
        self.loading = self.emojis['loading']
        self.bot = bot

    # TODO: rewrite command
    @commands.guild_only()
    @commands.hybrid_command(description='Get information about a server object such as a member, role, channel, and more')
    async def info(self, ctx: commands.Context, search: str = ''): #queue system: message, embed, every 3 secs, check if embed is different, edit message to new embed
        arg = search.lower()
        message = await ctx.send('{}Searching'.format(self.loading))
        mainKeys=[]
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        main=discord.Embed(title='Info results viewer', color=yellow[await utility.color_theme(ctx.guild)])
        embeds=[]
        PartialEmojiConverter = commands.PartialEmojiConverter()
        if len(arg) > 0:
            members, roles, channels, emojis = tuple(await asyncio.gather(*[utility.FindMembers(ctx.guild, arg), utility.FindRoles(ctx.guild, arg), utility.FindChannels(ctx.guild, arg), utility.FindEmojis(ctx.guild, arg)]))
            logs, invites, bans, webhooks = None, None, None, None
        else:
            await message.edit(content=f'{self.loading}Loading content')
            members = []
            roles = []
            channels = []
            emojis = []
        relevance = []
        indiv=None
        for m in members:
            mainKeys.append(f'{self.emojis["member"]}{m[0].name}')
            embeds.append(m[0])
            relevance.append(m[1])
        for r in roles:
            mainKeys.append(f'🚩{r[0].name}')
            embeds.append(r[0])
            relevance.append(r[1])
        for c in channels:
            types = {discord.TextChannel: self.emojis['textChannel'], discord.VoiceChannel: self.emojis['voiceChannel'], discord.CategoryChannel: self.emojis['folder']}
            mainKeys.append('{}{}'.format(types.get(type(c)), c[0].name))
            embeds.append(c[0])
            relevance.append(c[1])
        for e in emojis:
            mainKeys.append(f'{e[0]}{e[0].name}')
            embeds.append(e[0])
            relevance.append(e[1])
        if 'server' == arg or 'guild' == arg:
            mainKeys.append('ℹServer information')
            indiv = await self.ServerInfo(ctx.guild, logs, bans, webhooks, invites)
        if 'roles' == arg:
            mainKeys.append('ℹRole list information')
            indiv = await self.RoleListInfo(ctx.guild.roles, logs)
        if any(s==arg for s in ['members', 'people', 'users', 'bots', 'humans']):
            mainKeys.append('ℹMember list information')
            indiv = await self.MemberListInfo(ctx.guild.members)
        if 'channels' == arg:
            mainKeys.append('ℹChannel list information')
            indiv = await self.ChannelListInfo(ctx.guild.channels, logs)
        if 'emoji' == arg or 'emotes' == arg:
            mainKeys.append('ℹEmoji information')
            indiv = await self.EmojiListInfo(ctx.guild.emojis, logs)
        if 'invites' == arg:
            mainKeys.append('ℹInvites information')
            indiv = await self.InvitesListInfo(invites, logs, ctx.guild)
        if 'bans' == arg:
            mainKeys.append('ℹBans information')
            indiv = await self.BansListInfo(bans, logs, ctx.guild)
        if len(arg) == 0:
            await message.edit(content=f'{self.loading}Loading content') 
            mainKeys.append('ℹInformation about you :)')
            indiv = await asyncio.create_task(self.MemberInfo(ctx.author, calculatePosts=False))
        if 'me' == arg:
            await message.edit(content=f'{self.loading}Loading content')
            mainKeys.append('ℹInformation about you :)')
            indiv = await self.MemberInfo(ctx.author)
        if any(s == arg for s in ['him', 'her', 'them', 'it', '^']):
            await message.edit(content='{}Loading content'.format(self.loading))
            def pred(m): return m.author != ctx.guild.me and m.author != ctx.author
            author = sorted([message async for message in ctx.channel.history(limit=100).filter(pred)], key = lambda m: m.created_at, reverse=True)[-1].author
            mainKeys.append(f'ℹInformation about the person above you ({author.name})')
            indiv = await self.MemberInfo(author)
        if 'hardware' == arg:
            mainKeys.append('Information about me')
            indiv = await self.BotInfo(await self.bot.application_info(), ctx.guild)
        #Calculate relevance
        await message.edit(content='{}Loading content'.format(self.loading))
        reactions = ['⬅']
        priority = None
        if len(embeds) > 0 and indiv is None: 
            priority = embeds[relevance.index(max(relevance))]
            indiv=await self.evalInfo(priority, ctx.guild, logs)
            indiv.set_author(name='⭐Best match ({}% relevant)\n(React ⬅ to see all results)'.format(relevance[embeds.index(priority)]))
        else:
            if indiv is not None: 
                indiv.set_author(name='⭐Best match: {}'.format(mainKeys[0]))
            if len(embeds) == 0 and indiv is None: 
                main.description='{}0 results for *{}*, but I\'m still searching advanced results'.format(self.loading, arg)
                reactions = []
                indiv = main.copy()
        if len(arg) == 0: 
            await message.edit(content=None,embed=indiv)
            for i, f in enumerate(indiv.fields):
                if '📜Messages' == f.name: 
                    indiv.set_field_at(i, name=f.name, value=await self.MemberPosts(ctx.author))
                    await message.edit(embed=indiv)
                    break
            await message.add_reaction('🍰')
            def birthdayCheck(r,u): return u == ctx.author and r.message.id == message.id and str(r) == '🍰'
            await self.bot.wait_for('reaction_add',check=birthdayCheck)
            try: await message.delete()
            except: pass
            return await Birthdays.guestBirthdayHandler(self.bot.get_cog('Birthdays'), ctx, ctx.author)
        if len(embeds) > 1 or indiv is not None: 
            await message.edit(content='{}Still working'.format(self.loading), embed=indiv)
        members, roles, channels, inv, emojis = tuple(await asyncio.gather(*[utility.FindMoreMembers(ctx.guild.members, arg), utility.FindMoreRoles(ctx.guild, arg), utility.FindMoreChannels(ctx.guild, arg), utility.FindMoreInvites(ctx.guild, arg), utility.FindMoreEmojis(ctx.guild, arg)]))
        counter = 0
        while counter < 2:
            #print(counter, logs)
            if 'server' == arg or 'guild' == arg:
                mainKeys.append('ℹServer information')
                indiv = await self.ServerInfo(ctx.guild, logs, bans, webhooks, invites)
                # indiv = await self.ServerViewer(ctx.guild)
            if 'roles' == arg:
                mainKeys.append('ℹRole list information')
                indiv = await self.RoleListInfo(ctx.guild.roles, logs)
            if any(s==arg for s in ['members', 'people', 'users', 'bots', 'humans']):
                mainKeys.append('ℹMember list information')
                indiv = await self.MemberListInfo(ctx.guild.members)
            if 'channels' == arg:
                mainKeys.append('ℹChannel list information')
                indiv = await self.ChannelListInfo(ctx.guild.channels, logs)
            if 'emoji' == arg or 'emotes' == arg:
                mainKeys.append('ℹEmoji information')
                indiv = await self.EmojiListInfo(ctx.guild.emojis, logs)
            if 'invites' == arg:
                mainKeys.append('ℹInvites information')
                indiv = await self.InvitesListInfo(invites, logs, ctx.guild)
            if 'bans' == arg:
                mainKeys.append('ℹBans information')
                indiv = await self.BansListInfo(bans, logs, ctx.guild)
            if len(arg) == 0:
                mainKeys.append('ℹInformation about you :)')
                indiv = await asyncio.create_task(self.MemberInfo(ctx.author, calculatePosts=False))
            if 'me' == arg:
                mainKeys.append('ℹInformation about you :)')
                indiv = await self.MemberInfo(ctx.author)
            if any(s == arg for s in ['him', 'her', 'them', 'it']):
                author = sorted([message async for message in ctx.channel.history(limit=100).filter(pred)], key = lambda m: m.created_at, reverse=True)[-1].author
                mainKeys.append('ℹInformation about the person above you ({})'.format(author.name))
                indiv = await self.MemberInfo(author)
            if 'hardware' == arg:
                mainKeys.append('Information about me')
                indiv = await self.BotInfo(await self.bot.application_info(), ctx.guild)
            every=[]
            types = {discord.TextChannel: self.emojis['textChannel'], discord.VoiceChannel: self.emojis['voiceChannel'], discord.CategoryChannel: '📂'}
            for m in members: every.append(InfoResult(m.get('member'), '👤{} - {} ({}% match)'.format(m.get('member').name, m.get('check')[0], m.get('check')[1]), m.get('check')[1]))
            for r in roles: every.append(InfoResult(r.get('role'), '🚩{} - {} ({}% match)'.format(r.get('role').name, r.get('check')[0], r.get('check')[1]), r.get('check')[1]))
            for c in channels: every.append(InfoResult(c.get('channel'), '{}{} - {} ({}% match)'.format(types.get(type(c.get('channel'))), c.get('channel').name, c.get('check')[0], c.get('check')[1]), c.get('check')[1]))
            for i in inv: every.append(InfoResult(i.get('invite'), '💌discord.gg/{} - {} ({}% match)'.format(i.get('invite').code.replace(arg, '**{}**'.format(arg)), i.get('check')[0], i.get('check')[1]), i.get('check')[1]))
            for e in emojis: every.append(InfoResult(e.get('emoji'), '{}{} - {} ({}% match)'.format(e.get('emoji'), e.get('emoji').name, e.get('check')[0], e.get('check')[1]), e.get('check')[1]))
            if arg not in emoji.UNICODE_EMOJI and arg not in [str(emoji.get('emoji')) for emoji in emojis]:
                try:
                    partial = await PartialEmojiConverter.convert(ctx, arg)
                    every.append(InfoResult(partial, f'{partial}{partial.name}', 100))
                except: pass
            if 'server' in arg or 'guild' in arg or arg in ctx.guild.name.lower() or ctx.guild.name.lower() in arg: every.append(InfoResult((await self.ServerInfo(ctx.guild, logs, bans, webhooks, invites)), 'ℹServer information', utility.compareMatch('server', arg)))
            if 'roles' in arg: every.append(InfoResult((await self.RoleListInfo(ctx.guild.roles, logs)), 'ℹRole list information', utility.compareMatch('roles', arg)))
            if any(s in arg for s in ['members', 'people', 'users', 'bots', 'humans']): every.append(InfoResult((await self.MemberListInfo(ctx.guild.members)), 'ℹMember list information', utility.compareMatch('members', arg)))
            if 'channels' in arg: every.append(InfoResult((await self.ChannelListInfo(ctx.guild.channels, logs)), 'ℹChannel list information', utility.compareMatch('channels', arg)))
            if 'emoji' in arg or 'emotes' in arg: every.append(InfoResult((await self.EmojiListInfo(ctx.guild.emojis, logs)), 'ℹEmoji information', utility.compareMatch('emoji', arg)))
            if 'invites' in arg: every.append(InfoResult((await self.InvitesListInfo(invites, logs, ctx.guild)), 'ℹInvites information', utility.compareMatch('invites', arg)))
            if 'bans' in arg: every.append(InfoResult((await self.BansListInfo(bans, logs, ctx.guild)), 'ℹBans information', utility.compareMatch('bans', arg)))
            if any(s in arg for s in ['dev', 'owner', 'master', 'creator', 'author', 'disguard', 'bot', 'you']): every.append(InfoResult((await self.BotInfo(await self.bot.application_info(), ctx.guild)), '{}Information about me'.format(self.bot.get_emoji(569191704523964437)), utility.compareMatch('disguard', arg)))
            every.sort(key=lambda x: x.relevance, reverse=True)
            md = 'Viewing {} - {} of {} results for *{}*{}\n**Type the number of the option to view**\n'
            md2=[]
            used = md.format(1 if len(every) >= 1 else 0, 20 if len(every) >= 20 else len(every), len(every), arg, ' (Arrows to scroll)' if len(every) >= 20 else '')
            main.description=used
            for result in range(len(every)): md2.append('\n{}: {}'.format(result + 1, every[result].mainKey))
            main.description+=''.join(md2[:20])
            #main.set_author(name='{}: {}'.format(ctx.author.name, ctx.author.id),icon_url=ctx.author.avatar_url)
            if len(main.description) > 2048: main.description = main.description[:2048]
            if len(every) == 0 and indiv is None: return await message.edit(embed=main)
            elif len(every) == 1 and counter == 0 and type(every[0].obj) is not discord.Member: 
                temp = await self.evalInfo(every[0].obj, ctx.guild, logs)
                temp.set_author(name='⭐{}% relevant ({})'.format(every[0].relevance, every[0].mainKey))
                await message.edit(embed=temp)
            elif len(reactions) == 0: 
                await message.edit(embed=main)
            elif len(embeds) > 1 or indiv is not None: 
                #pass
                #await asyncio.sleep(5)
                await message.edit(embed=indiv)
            if type(priority) is discord.Member:
                message = await message.channel.fetch_message(message.id)
                for i, f in enumerate(message.embeds[0].fields):
                    if '📜Messages' == f.name: 
                        message.embeds[0].set_field_at(i, name=f.name, value=await self.MemberPosts(every[0].obj))
                        await message.edit(embed=message.embeds[0])
                        break
            if counter == 0:
                try: logs = [log async for log in ctx.guild.audit_logs(limit=None)]
                except: logs = False #signify failure to the end user
                try: invites = await ctx.guild.invites()
                except: invites = False
                try: bans = await ctx.guild.bans()
                except: bans = False
                try: webhooks = await ctx.guild.webhooks()
                except: webhooks = False
            counter += 1
        loadContent = discord.Embed(title='{}Loading {}', color=yellow[await utility.color_theme(ctx.guild)])
        # message = await message.channel.fetch_message(message.id)
        if message.content is not None: await message.edit(content=None)
        past = False
        while not self.bot.is_closed():
            message = await message.channel.fetch_message(message.id)
            if past or (message.embeds[0].author.name and '⭐' in message.embeds[0].author.name): 
                if len(every) > 0: 
                    for r in ['⬅']: await message.add_reaction(r)
                try: desired = ctx.guild.get_member(int(message.embeds[0].footer.text[message.embeds[0].footer.text.find(':') + 1:]))
                except: desired = None
                def checkBday(r, u): return u == desired and not u.bot and r.message.id == message.id and str(r) == '🍰'
                def checkBack(r, u): return u == ctx.author and r.message.id == message.id and str(r) == '⬅'
                if 'member details' in message.embeds[0].title.lower() and desired: await message.add_reaction('🍰')
                d, p = await asyncio.wait([
                    asyncio.create_task(self.bot.wait_for('reaction_add', check=checkBack)),
                    asyncio.create_task(self.bot.wait_for('reaction_add', check=checkBday))
                    ], return_when=asyncio.FIRST_COMPLETED)
                try: r = d.pop().result()
                except: pass
                for f in p: f.cancel()
                if str(r[0]) == '⬅':
                    try: await message.clear_reactions()
                    except: pass
                    await message.edit(embed=main)
                else: 
                    await message.delete()
                    return await Birthdays.guestBirthdayHandler(self.bot.get_cog('Birthdays'), ctx, ctx.author)
            if len(every) >= 20:
                for r in ['◀', '▶']: await message.add_reaction(r)
            def check(m):
                try: return m.author==ctx.author and int(m.content) <= len(every)
                except: return False
            past = False
            def reacCheck(r, u): return str(r) in ['◀', '▶'] and u==ctx.author
            while not past:
                done, pending = await asyncio.wait([
                    asyncio.create_task(self.bot.wait_for('message', check=check, timeout=300)),
                    asyncio.create_task(self.bot.wait_for('reaction_add', check=reacCheck, timeout=300))
                    ], return_when=asyncio.FIRST_COMPLETED)
                try: stuff = done.pop().result()
                except: return
                for future in pending: future.cancel()
                if type(stuff) is tuple:
                    await message.remove_reaction(stuff[0], stuff[1])
                    coords = int(used[used.find('Viewing')+8:used.find('-')-1]), int(used[used.find('-')+2:used.find('of')-1])
                    if str(stuff[0]) == '◀': coords = coords[0] - 20, coords[1] - 20
                    if str(stuff[0]) == '▶': coords = coords[0] + 20, coords[1] + 20
                    if coords[0] < 0: coords = 0, 20 if len(every) > 20 else len(every)
                    if coords[1] > len(every): coords = coords[0], len(every)
                    used = md.format(coords[0], coords[1], len(every), arg, ' (Arrows to scroll)' if len(every) >= 20 else '')+''.join(md2[coords[0]-1:coords[1]])
                    main.description=used
                    await message.edit(embed=main)
                else:
                    past = True
                    try: await message.clear_reactions()
                    except: pass
                    loadContent.title = loadContent.title.format(self.loading, str(every[int(stuff.content) - 1].obj))
                    await message.edit(content=None, embed=loadContent)
                    cyber.AvoidDeletionLogging(stuff)
                    try: await stuff.delete()
                    except: pass
                    await message.edit(content=None,embed=(await self.evalInfo(every[int(stuff.content)-1].obj, ctx.guild, logs)))
                    if type(every[int(stuff.content) - 1].obj) is discord.Member:
                        for i, f in enumerate(message.embeds[0].fields):
                            if '📜Messages' == f.name: 
                                message.embeds[0].set_field_at(i, name=f.name, value=await self.MemberPosts(every[0].obj))
                                await message.edit(embed=message.embeds[0])
                                break
                    await message.add_reaction('⬅')
                    if 'member details' in message.embeds[0].title.lower(): await message.add_reaction('🍰')

    async def ServerInfo(self, s: discord.Guild, logs, bans, hooks, invites):
        '''Formats an embed, displaying stats about a server. Used for ℹ navigation or `info` command'''
        embed=discord.Embed(title=s.name, description='' if s.description is None else '**Server description:** {}\n\n'.format(s.description), timestamp=datetime.datetime.utcnow(), color=yellow[await utility.color_theme(s)])
        mfa = {0: 'No', 1: 'Yes'}
        veri = {'none': 'None', 'low': 'Email', 'medium': 'Email, account age > 5 mins', 'high': 'Email, account 5 mins old, server member for 10 mins', 'extreme': 'Phone number'}
        perks0=['None yet']
        perks1 = ['100 emoji limit, 128kbps bitrate', 'animated server icon, custom server invite background'] #First half doesn't get added to string for later levels
        perks2 = ['150 emoji limit, 256kbps bitrate, 50MB upload limit', 'server banner']
        perks3 = ['250 emoji limit, 384kbps bitrate, 100MB upload limit', 'vanity URL']
        perkDict = {0: 2, 1: 10, 2: 50, 3: '∞'}
        if s.premium_tier==3: perks=[perks3[0], perks3[1],perks2[1],perks1[1]]
        elif s.premium_tier==2: perks=[perks2[0],perks2[1],perks1[1]]
        elif s.premium_tier==1: perks = perks1
        else: perks = perks0
        messages = 0
        for channel in s.text_channels:
            messages += len(await lightningdb.get_channel_messages(channel.id))
        created = s.created_at - datetime.timedelta(hours=utility.daylightSavings())
        txt='{}Text Channels: {}'.format(self.emojis["textChannel"], len(s.text_channels))
        vc='{}Voice Channels: {}'.format(self.emojis['voiceChannel'], len(s.voice_channels))
        cat='{}Category Channels: {}'.format(self.emojis['folder'], len(s.categories))
        embed.description+=('**Channel count:** {}\n{}\n{}\n{}'.format(len(s.channels),cat, txt, vc))
        onlineGeneral = 'Online: {} / {} ({}%)'.format(len([m for m in s.members if m.status != discord.Status.offline]), len(s.members), round(len([m for m in s.members if m.status != discord.Status.offline]) / len(s.members) * 100))
        offlineGeneral = 'Offline: {} / {} ({}%)'.format(len([m for m in s.members if m.status == discord.Status.offline]), len(s.members), round(len([m for m in s.members if m.status == discord.Status.offline]) / len(s.members) * 100))
        online='{}Online: {}'.format(self.emojis["online"], len([m for m in s.members if m.status == discord.Status.online]))
        idle='{}Idle: {}'.format(self.emojis["idle"], len([m for m in s.members if m.status == discord.Status.idle]))
        dnd='{}Do not disturb: {}'.format(self.emojis["dnd"], len([m for m in s.members if m.status == discord.Status.dnd]))
        offline='{}Offline/invisible: {}'.format(self.emojis["offline"], len([m for m in s.members if m.status == discord.Status.offline]))
        embed.description+='\n\n**Member count:** {}{}\n{}'.format(len(s.members),'' if s.max_members is None else '/{}'.format(s.max_members) if s.max_members - len(s.members) < 500 else '','\n'.join([onlineGeneral, offlineGeneral, online, idle, dnd, offline]))
        embed.description+='\n\n**Features:** {}'.format(', '.join(s.features) if len(s.features) > 0 else 'None')
        embed.description+='\n\n**Nitro boosters:** {}/{}, **perks:** {}'.format(s.premium_subscription_count,perkDict.get(s.premium_tier),', '.join(perks))
        #embed.set_thumbnail(url=s.icon_url)
        embed.add_field(name='Created',value=f'{utility.DisguardIntermediateTimestamp(created)} ({utility.DisguardRelativeTimestamp(created)})',inline=False)
        embed.add_field(name='Region',value=str(s.region))
        embed.add_field(name='AFK Timeout',value='{}s --> {}'.format(s.afk_timeout, s.afk_channel))
        if s.max_presences is not None: embed.add_field(name='Max Presences',value='{}'.format(s.max_presences))
        embed.add_field(name='Mods need 2FA',value=mfa.get(s.mfa_level))
        embed.add_field(name='Verification',value=veri.get(str(s.verification_level)))
        embed.add_field(name='Explicit filter',value=s.explicit_content_filter)
        embed.add_field(name='Default notifications',value=str(s.default_notifications)[str(s.default_notifications).find('.')+1:])
        try: embed.add_field(name='Locale',value=s.preferred_locale)
        except: pass
        embed.add_field(name='Audit logs',value=self.loading if logs is None else '🔒Unable to obtain audit logs' if logs is False else len(logs) if logs else 'N/A')
        if s.system_channel is not None: embed.add_field(name='System channel',value='{}: {}'.format(s.system_channel.mention, ', '.join([k[0] for k in (iter(s.system_channel_flags))])))
        embed.add_field(name='Role count',value=len(s.roles) - 1)
        embed.add_field(name='Owner',value=s.owner.mention)
        embed.add_field(name='Banned members',value=self.loading if bans is None else '🔒Unable to obtain server bans' if bans is False else len(bans) if bans else 'N/A')
        embed.add_field(name='Webhooks',value=self.loading if hooks is None else '🔒Unable to obtain webhooks' if hooks is False else len(hooks) if hooks else 'N/A')
        embed.add_field(name='Invites',value=self.loading if invites is None else '🔒Unable to obtain invites' if invites is False else len(invites) if invites else 'N/A')
        embed.add_field(name='Emojis',value='{}/{}'.format(len(s.emojis), s.emoji_limit))
        embed.add_field(name='Messages', value=f'about {messages}')
        embed.set_footer(text='Server ID: {}'.format(s.id))
        return embed

    async def ChannelInfo(self, channel: discord.abc.GuildChannel, invites, pins, logs):
        permString = None
        details = discord.Embed(title=f'{utility.channelEmoji(self, channel)}{channel.name}', description='',color=yellow[await utility.color_theme(channel.guild)], timestamp=datetime.datetime.utcnow())
        details.set_footer(text='Channel ID: {}'.format(channel.id))
        if type(channel) is discord.TextChannel: details.description+=channel.mention
        if type(channel) is not discord.CategoryChannel:
            #details.description+='\n\n**Channels {}**\n{}'.format('without a category' if channel.category is None else 'in category {}'.format(channel.category.name), '\n'.join(['{}'.format('{}{}{}{}'.format('**' if chan==channel else '', types.get(type(chan)), chan.name, '**' if chan==channel else '')) for chan in channel.category.channels]))
            details.description+='\n**Category:** {}'.format('None' if channel.category is None else channel.category.name)
        else: details.description+='\n\n**Channels in this category**\n{}'.format('\n'.join(['{}{}'.format(utility.channelEmoji(self, chan), chan.name) for chan in channel.channels]))
        perms = {}
        formatted = {} #Key (read_messages, etc): {role or member: deny or allow, role or member: deny or allow...}
        temp=[]
        english = {True: '✔', False: '✖'} #Symbols becuase True, False, None is confusing
        for k,v in channel.overwrites.items(): perms.update({k: dict(iter(v))})
        for k,v in perms.items():
            for kk,vv in v.items():
                if vv is not None: 
                    try: formatted.get(kk).update({k: vv})
                    except: formatted.update({kk: {k: vv}})
        for k,v in formatted.items():
            temp.append('{:<60s}'.format(utility.permissionKeys.get(k, f'Unknown Permission ({k})')))
            string='\n'.join(['     {}: {:>{diff}}'.format(kk.name, english.get(vv), diff=25 - len(kk.name)) for kk,vv in iter(v.items())])
            temp.append(string)
            permString = '```Channel permission overwrites\n{}```'.format('\n'.join(temp))
        created=channel.created_at - datetime.timedelta(hours=utility.daylightSavings())
        updated = None
        if logs:
            for log in logs:
                if log.action == discord.AuditLogAction.channel_update and (discord.utils.utcnow() - log.created_at).seconds > 600:
                    if log.target.id == channel.id:
                        updated = log.created_at - datetime.timedelta(hours=utility.daylightSavings())
                        break
        if updated is None: updated = created
        details.add_field(name='Created',value=f'{utility.DisguardIntermediateTimestamp(created)} ({utility.DisguardRelativeTimestamp(created)})')
        details.add_field(name='Last updated',value=f'{utility.DisguardIntermediateTimestamp(updated)} ({utility.DisguardRelativeTimestamp(updated)})' if logs != None else self.loading if logs is None else '🔒Unable to obtain audit logs' if not logs else 'N/A')
        inviteCount = []
        if invites:
            for inv in iter(invites): inviteCount.append(inv.inviter)
        details.add_field(name='Invites to here',value=self.loading if invites is None else '🔒Unable to retrieve invites' if invites is False else 'None' if len(inviteCount) == 0 or not logs else ', '.join(['{} by {}'.format(a[1], a[0].name) for a in iter(collections.Counter(inviteCount).most_common())]))
        if type(channel) is discord.TextChannel:
            details.add_field(name='Topic',value='{}{}'.format('<No topic>' if channel.topic is None or len(channel.topic) < 1 else channel.topic[:100], '' if channel.topic is None or len(channel.topic)<=100 else '...'),inline=False)
            details.add_field(name='Slowmode',value='{}s'.format(channel.slowmode_delay))
            details.add_field(name='Message count',value=len(await lightningdb.get_channel_messages(channel.id)))
            details.add_field(name='NSFW',value=channel.is_nsfw())
            details.add_field(name='News channel?',value=channel.is_news())
            details.add_field(name='Pins count',value=len(pins) if pins else self.loading if pins is False else '🔒Unable to retrieve pins')
        if type(channel) is discord.VoiceChannel:
            details.add_field(name='Bitrate',value='{} kbps'.format(int(channel.bitrate / 1000)))
            details.add_field(name='User limit',value=channel.user_limit)
            details.add_field(name='Members currently in here',value='None' if len(channel.members)==0 else ', '.join([member.mention for member in channel.members]))
        if type(channel) is discord.CategoryChannel:
            details.add_field(name='NSFW',value=channel.is_nsfw())
        return [permString, details]

    async def RoleInfo(self, r: discord.Role, logs):
        #sortedRoles = sorted(r.guild.roles, key = lambda x: x.position, reverse=True)
        #start = r.position - 3
        #if start < 0: start = 0
        created = r.created_at - datetime.timedelta(hours=utility.daylightSavings())
        updated = None
        if logs:
            for log in logs:
                if log.action == discord.AuditLogAction.role_update and (discord.utils.utcnow() - log.created_at).seconds > 600:
                    if log.target.id == r.id:
                        updated = log.created_at - datetime.timedelta(hours=utility.daylightSavings())
                        break
        if updated is None: updated = created
        embed=discord.Embed(title='🚩Role: {}'.format(r.name),description='**Permissions:** {}'.format('Administrator' if r.permissions.administrator else ' • '.join([utility.permissionKeys.get(p[0], f'Unknown Permission ({p[0]})') for p in iter(r.permissions) if p[1]])),timestamp=datetime.datetime.utcnow(),color=r.color)
        #embed.description+='\n**Position**:\n{}'.format('\n'.join(['{0}{1}{0}'.format('**' if sortedRoles[role] == r else '', sortedRoles[role].name) for role in range(start, start+6)]))
        embed.add_field(name='Displayed separately',value=r.hoist)
        embed.add_field(name='Externally managed',value=r.managed)
        embed.add_field(name='Mentionable',value=r.mentionable)
        embed.add_field(name='Created',value=f'{utility.DisguardIntermediateTimestamp(created)} ({utility.DisguardRelativeTimestamp(created)})')
        embed.add_field(name='Last updated',value=f'{utility.DisguardIntermediateTimestamp(updated)} ({utility.DisguardRelativeTimestamp(updated)})' if logs != None else self.loading if logs is None else '🔒Unable to obtain audit logs' if not logs else 'N/A')
        embed.add_field(name='Belongs to',value='{} members'.format(len(r.members)))
        embed.set_footer(text='Role ID: {}'.format(r.id))
        return embed

    async def MemberInfo(self, m: discord.Member, *, addThumbnail=True, calculatePosts=True):
        if calculatePosts: postCount = await self.MemberPosts(m)
        else: postCount = self.loading
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        #tz = timeZone(m.guild)
        #nz = nameZone(m.guild)
        embed=discord.Embed(title='Member details',timestamp=datetime.datetime.utcnow(),color=m.color)
        mA = await Cyberlog.lastActive(m) #The dict (timestamp and reason) when a member was last active
        activeTimestamp = mA.get('timestamp')# + datetime.timedelta(hours=timeZone(m.guild) + 4) #The timestamp value when a member was last active, with adjustments for timezones
        onlineTimestamp = await Cyberlog.lastOnline(m)# + datetime.timedelta(hours=timeZone(m.guild) + 4) #The timestamp value when a member was last online, with adjustments for timezones
        onlineDelta = (datetime.datetime.now() - onlineTimestamp) #the timedelta between now and member's last online appearance
        activeDelta = (datetime.datetime.now() - activeTimestamp) #The timedelta between now and when a member was last active
        units = ['second', 'minute', 'hour', 'day'] #Used in the embed description
        hours, minutes, seconds = activeDelta.seconds // 3600, (activeDelta.seconds // 60) % 60, activeDelta.seconds - (activeDelta.seconds // 3600) * 3600 - ((activeDelta.seconds // 60) % 60)*60
        activeTimes = [seconds, minutes, hours, activeDelta.days] #List of self explanatory values
        hours, minutes, seconds = onlineDelta.seconds // 3600, (onlineDelta.seconds // 60) % 60, onlineDelta.seconds - (onlineDelta.seconds // 3600) * 3600 - ((onlineDelta.seconds // 60) % 60)*60
        onlineTimes = [seconds, minutes, hours, onlineDelta.days]
        activeDisplay = []
        onlineDisplay = []
        offline = self.emojis['offline']
        for i in range(len(activeTimes)):
            if activeTimes[i] != 0: activeDisplay.append('{}{}'.format(activeTimes[i], units[i][0]))
            if onlineTimes[i] != 0: onlineDisplay.append('{}{}'.format(onlineTimes[i], units[i][0]))
        if len(activeDisplay) == 0: activeDisplay = ['0s']
        activities = {discord.Status.online: self.emojis['online'], discord.Status.idle: self.emojis['idle'], discord.Status.dnd: self.emojis['dnd'], discord.Status.offline: self.emojis['offline']}
        lastOnlineString = f'''\nLast online {f"{utility.DisguardRelativeTimestamp(onlineTimestamp)}{f'{NEWLINE}•This member is likely {offline} invisible' if mA['timestamp'] > await Cyberlog.lastOnline(m) and m.status == discord.Status.offline else ''}" if await cyber.privacyEnabledChecker(m, 'profile', 'lastOnline') else '<Feature disabled by user>' if await cyber.privacyVisibilityChecker(m, 'profile', 'lastOnline') else '<Feature set to private by user>'}'''
        embed.description = f'''{activities[m.status]} {m.name} ({m.mention})\n\nLast active {f"{utility.DisguardRelativeTimestamp(activeTimestamp)} ({mA['reason']})" if await cyber.privacyEnabledChecker(m, 'profile', 'lastActive') else '<Feature disabled by user>' if await cyber.privacyVisibilityChecker(m, 'profile', 'lastActive') else '<Feature set to private by user>'}{lastOnlineString if m.status == discord.Status.offline else ""}'''
        if len(m.activities) > 0:
            current=[]
            for act in m.activities:
                try:
                    if act.type is discord.ActivityType.playing: 
                        try: current.append(f'playing {act.name}: {act.details}{(", " + act.state) if act.state is not None else ""}{" (⭐Visible under username)" if act == m.activity else ""}')
                        except AttributeError: current.append(f'playing {act.name}{" (⭐Visible under username)" if act == m.activity else ""}')
                    elif act.type is discord.ActivityType.custom: current.append(f'{act.emoji if act.emoji is not None else ""} {act.name if act.name is not None else ""}{" (⭐Visible under username)" if act == m.activity else ""}')
                    elif act.type is discord.ActivityType.streaming: current.append(f'streaming {act.name}{" (⭐Visible under username)" if act == m.activity else ""}')
                    elif act.type is discord.ActivityType.listening and act.name == 'Spotify': current.append(f'Listening to Spotify{" (⭐Visible under username)" if act == m.activity else ""}\n 🎵 {act.title}\n 👤 {", ".join(act.artists)}\n 💿 {act.album}')
                    elif act.type is discord.ActivityType.watching: current.append(f'watching {act.name}{" (⭐Visible under username)" if act == m.activity else ""}')
                except:
                    current.append('Error parsing activity')
            embed.description+='\n\n • {}'.format('\n • '.join(current))
        embed.description+='\n\n**Roles ({}):** {}\n\n**Permissions:** {}\n\nReact 🍰 to switch to Birthday Information view'.format(len(m.roles) - 1, ' • '.join([r.name for r in reversed(m.roles)]), 'Administrator' if m.guild_permissions.administrator else ' • '.join([utility.permissionKeys.get(p[0], f'Unknown Permission ({p[0]})') for p in iter(m.guild_permissions) if p[1]]))
        boosting = m.premium_since
        joined = m.joined_at - datetime.timedelta(hours=utility.daylightSavings())
        created = m.created_at - datetime.timedelta(hours=utility.daylightSavings())
        if m.voice is None: voice = 'None'
        else:
            voice = '{}{} in {}{}'.format('🔇' if m.voice.mute or m.voice.self_mute else '', '🤐' if m.voice.deaf or m.voice.self_deaf else '','N/A' if m.voice.channel is None else m.voice.channel.name, ', AFK' if m.voice.afk else '')
        if boosting is None: embed.add_field(name='Boosting server',value='Nope')
        else:
            embed.add_field(name='Boosting server',value=f'Since {utility.DisguardRelativeTimestamp(boosting - datetime.timedelta(hours=utility.daylightSavings()))}')
        embed.add_field(name='📆Account created',value=f'{utility.DisguardRelativeTimestamp(created)}') #V1.5
        #embed.add_field(name='📆Account created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nz, (datetime.datetime.now(datetime.timezone.utc)-created).days)) #v2.0
        embed.add_field(name='📆Joined server',value=f'{utility.DisguardRelativeTimestamp(joined)}')
        embed.add_field(name='📜Messages',value=postCount)
        embed.add_field(name='🎙Voice Chat',value=voice)
        # if addThumbnail: embed.set_thumbnail(url=m.avatar_url) #V1.5
        if addThumbnail: embed.set_thumbnail(url=m.avatar.url) #V2.0
        embed.set_footer(text='Member ID: {}'.format(m.id))
        return embed
        
    async def EmojiInfo(self, e: discord.Emoji, owner):
        created = e.created_at - datetime.timedelta(hours=utility.daylightSavings())
        embed = discord.Embed(title=e.name,description=str(e),timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(e.guild)])
        embed.set_image(url=e.url)
        embed.set_footer(text='Emoji ID: {}'.format(e.id))
        embed.add_field(name='Twitch emoji',value=e.managed)
        if owner is not None: embed.add_field(name='Uploaded by',value='{} ({})'.format(owner.mention, owner.name))
        embed.add_field(name='Server',value=e.guild.name)
        embed.add_field(name='📆Created',value=f'{utility.DisguardIntermediateTimestamp(created)} ({utility.DisguardRelativeTimestamp(created)})')
        return embed

    async def PartialEmojiInfo(self, e: discord.PartialEmoji, s: discord.Guild):
        embed=discord.Embed(title=e.name,description=str(e),timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(s)])
        embed.set_image(url=e.url)
        embed.set_footer(text='Emoji ID: {}'.format(e.id))
        return embed

    async def InviteInfo(self, i: discord.Invite, s): #s: server
        embed=discord.Embed(title='Invite details',description=str(i),timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(s)])
        embed.set_thumbnail(url=i.guild.icon.url)
        #expires=discord.utils.utcnow() + datetime.timedelta(seconds=i.max_age) + datetime.timedelta(hours=timeZone(s))
        expires=datetime.datetime.now() + datetime.timedelta(seconds=i.max_age)
        created = i.created_at - datetime.timedelta(hours=utility.daylightSavings())
        embed.add_field(name='📆Created',value=f'{utility.DisguardIntermediateTimestamp(created)} ({utility.DisguardRelativeTimestamp(created)})')
        embed.add_field(name='⏰Expires',value=f'{utility.DisguardRelativeTimestamp(expires)}' if i.max_age > 0 else 'Never')
        embed.add_field(name='Server',value=i.guild.name)
        embed.add_field(name='Channel',value=i.channel.mention)
        embed.add_field(name='Author',value='{} ({})'.format(i.inviter.mention, i.inviter.name))
        embed.add_field(name='Used',value='{}/{} times'.format(i.uses, '∞' if i.max_uses == 0 else i.max_uses))
        embed.set_footer(text='Invite server ID: {}'.format(i.guild.id))
        #In the future, once bot is more popular, integrate server stats from other servers
        return embed

    async def BotInfo(self, app: discord.AppInfo, s: discord.Guild):
        bpg = 1073741824 #Bytes per gig
        embed=discord.Embed(title='About Disguard',description='{0}{1}{0}'.format(self.bot.get_emoji(569191704523964437), app.description),timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(s)])
        embed.description+=f'\n\nDISGUARD HOST SYSTEM INFORMATION\nCPU: {cpuinfo.get_cpu_info().get("brand")}\n•   Usage: {psutil.cpu_percent()}%\n​•   Core count: {psutil.cpu_count(logical=False)} cores, {psutil.cpu_count()} threads\n​​​​​​‍‍‍​​​•   {(psutil.cpu_freq().current / 1000):.2f} GHz current clock speed; {(psutil.cpu_freq().max / 1000):.2f} GHz max clock speed'
        embed.description+=f'\n​RAM: {(psutil.virtual_memory().total / bpg):.1f}GB total ({(psutil.virtual_memory().used / bpg):.1f}GB used, {(psutil.virtual_memory().free / bpg):.1f}GB free)'
        embed.description+=f'\nSTORAGE: {psutil.disk_usage("/").total // bpg}GB total ({psutil.disk_usage("/").used // bpg}GB used, {psutil.disk_usage("/").free // bpg}GB free)'
        embed.set_footer(text='My ID: {}'.format(app.id))
        embed.set_thumbnail(url=app.icon.url)
        embed.add_field(name='Developer',value=app.owner)
        embed.add_field(name='Public Bot',value=app.bot_public)
        embed.add_field(name='In development since',value='March 20, 2019')
        embed.add_field(name='Website with information',value=f'[Disguard Website](https://disguard.netlify.com/ \'https://disguard.netlify.com/\')')
        embed.add_field(name='Servers',value=len(self.bot.guilds))
        embed.add_field(name='Emojis',value=len(self.bot.emojis))
        embed.add_field(name='Users',value=len(self.bot.users))
        return embed

    async def EmojiListInfo(self, emojis, logs):
        '''Prereq: len(emojis) > 0'''
        embed=discord.Embed(title='{}\'s emojis'.format(emojis[0].guild.name),description='Total emojis: {}'.format(len(emojis)),timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(emojis[0].guild)])
        static = [str(e) for e in emojis if not e.animated]
        animated = [str(e) for e in emojis if e.animated]
        if len(static) > 0: embed.add_field(name='Static emojis: {}/{}'.format(len(static), emojis[0].guild.emoji_limit),value=''.join(static)[:1023],inline=False)
        if len(animated) > 0: embed.add_field(name='Animated emojis: {}/{}'.format(len(animated), emojis[0].guild.emoji_limit),value=''.join(animated)[:1023],inline=False)
        if logs: embed.add_field(name='Total emojis ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.emoji_create])))
        elif logs is None: embed.add_field(name='Total emojis ever created',value=self.loading)
        else: embed.add_field(name='Total emojis ever created',value='🔒Unable to obtain audit logs')
        return embed

    async def ChannelListInfo(self, channels, logs):
        '''Prereq: len(channels) > 0'''
        embed=discord.Embed(title='{}\'s channels'.format(channels[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(channels[0].guild)])
        none=['(No category)'] if len([c for c in channels if type(c) is not discord.CategoryChannel and c.category is None]) else []
        none += ['|{}{}'.format(utility.channelEmoji(self, c), c.name) for c in channels if type(c) is not discord.CategoryChannel and c.category is None]
        for chan in channels[0].guild.categories:
            none.append('{}{}'.format(utility.channelEmoji(self, chan), chan.name))
            none+=['|{}{}'.format(utility.channelEmoji(self, c), c.name) for c in chan.channels]
        embed.description='Total channels: {}\n\n{}'.format(len(channels), '\n'.join(none))
        if logs: embed.add_field(name='Total channels ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.channel_create])))
        elif logs is None: embed.add_field(name='Total channels ever created',value=self.loading)
        else: embed.add_field(name='Total channels ever created',value='🔒Unable to obtain audit logs')
        return embed

    async def RoleListInfo(self, roles, logs):
        '''Prereq: len(roles) > 0'''
        embed=discord.Embed(title='{}\'s roles'.format(roles[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(roles[0].guild)])
        embed.description='Total roles: {}\n\n • {}'.format(len(roles), '\n • '.join([r.name for r in roles]))
        embed.add_field(name='Roles displayed separately',value=len([r for r in roles if r.hoist]))
        embed.add_field(name='Mentionable roles',value=len([r for r in roles if r.mentionable]))
        embed.add_field(name='Externally managed roles',value=len([r for r in roles if r.managed]))
        embed.add_field(name='Roles with manage server',value=len([r for r in roles if r.permissions.manage_guild]))
        embed.add_field(name='Roles with administrator',value=len([r for r in roles if r.permissions.administrator]))
        if logs: embed.add_field(name='Total roles ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.role_create])))
        elif logs is None: embed.add_field(name='Total roles ever created',value=self.loading)
        else: embed.add_field(name='Total roles ever created',value='🔒Unable to obtain audit logs')
        return embed

    async def MemberListInfo(self, members):
        embed=discord.Embed(title='{}\'s members'.format(members[0].guild.name),description='',timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(members[0].guild)])
        posts=[]
        for channel in members[0].guild.text_channels:
            posts += [message['author0'] for message in (await lightningdb.get_channel_messages(channel.id)).values()]
        most = ['{} with {}'.format(self.bot.get_user(a[0]).name, a[1]) for a in iter(collections.Counter(posts).most_common(1))][0]
        online=self.emojis['online']
        idle=self.emojis['idle']
        dnd=self.emojis['dnd']
        offline=self.emojis['offline']
        humans='👤Humans: {}'.format(len([m for m in members if not m.bot]))
        bots='🤖Bots: {}\n'.format(len([m for m in members if m.bot]))
        onlineGeneral = 'Online: {} / {} ({}%)'.format(len([m for m in members if m.status != discord.Status.offline]), len(members), round(len([m for m in members if m.status != discord.Status.offline]) / len(members) * 100))
        offlineGeneral = 'Offline: {} / {} ({}%)'.format(len([m for m in members if m.status == discord.Status.offline]), len(members), round(len([m for m in members if m.status == discord.Status.offline]) / len(members) * 100))
        online='{} Online: {}'.format(online, len([m for m in members if m.status == discord.Status.online]))
        idle='{} Idle: {}'.format(idle, len([m for m in members if m.status == discord.Status.idle]))
        dnd='{} Do not disturb: {}'.format(dnd, len([m for m in members if m.status == discord.Status.dnd]))
        offline='{} Offline/invisible: {}'.format(offline, len([m for m in members if m.status == discord.Status.offline]))
        embed.description+='\n\n**Member count:** {}{}\n{}'.format(len(members),'' if members[0].guild.max_members is None else '/{}'.format(members[0].guild.max_members),'\n'.join([humans, bots, onlineGeneral, offlineGeneral, online, idle, dnd, offline]))
        embed.add_field(name='Playing/Listening/Streaming',value=len([m for m in members if len(m.activities) > 0]))
        embed.add_field(name='Members with nickname',value=len([m for m in members if m.nick is not None]))
        embed.add_field(name='On mobile',value=len([m for m in members if m.is_on_mobile()]))
        embed.add_field(name='In voice channel',value=len([m for m in members if m.voice is not None]))
        embed.add_field(name='Most posts',value=most)
        embed.add_field(name='Moderators',value=len([m for m in members if m.guild_permissions.manage_guild]))
        embed.add_field(name='Administrators',value=len([m for m in members if m.guild_permissions.administrator]))
        return embed

    async def InvitesListInfo(self, invites, logs, s: discord.Guild):
        embed=discord.Embed(title=f'{invites[0].guild.name if invites else "This server"}\'s invites', timestamp=datetime.datetime.utcnow(), color=yellow[await utility.color_theme(s)])
        if invites: embed.description='Total invites: {}\n\n • {}'.format(len(invites), '\n • '.join(['discord.gg/**{}**: Goes to {}, created by {}'.format(i.code, i.channel.name, i.inviter.name) for i in invites]))[:2047]
        else: embed.description=f'Total invites: {self.loading if invites is None else "🔒Unable to obtain invites"}'
        if logs: embed.add_field(name='Total invites ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.invite_create])))
        elif logs is None: embed.add_field(name='Total invites ever created',value=self.loading)
        else: embed.add_field(name='Total invites ever created',value='🔒Unable to obtain audit logs')
        return embed

    async def BansListInfo(self, bans, logs, s): #s=server
        embed=discord.Embed(title='{}\'s bans'.format(s.name),timestamp=datetime.datetime.utcnow(),color=yellow[await utility.color_theme(s)])
        embed.description=f'Users currently banned: {len(bans) if bans else self.loading if bans is None else "🔒Missing ban retrieval permissions"}'
        if not logs:
            if logs is None: embed.add_field(name='Banned previously', value=self.loading)
            else: embed.add_field(name='Banned previously', value='🔒Unable to obtain audit logs')
        if not bans and not logs: return embed
        null = embed.copy()
        array = []
        current = []
        for b in bans:
            for l in logs:
                if l.action == discord.AuditLogAction.ban and l.target == b.user:
                    created = l.created_at + datetime.timedelta(hours=self.timeZone(s))
                    array.append('{}: Banned by {} on {} because {}'.format(l.target.name, l.user.name, created.strftime('%m/%d/%Y@%H:%M'), '(No reason specified)' if b.reason is None else b.reason))
                    current.append(b.user)
        other=[]
        for l in logs:
            if l.action == discord.AuditLogAction.ban and l.target not in current:
                created = l.created_at + datetime.timedelta(hours=self.timeZone(s))
                other.append('{}: Banned by {} on {} because {}'.format(l.target.name, l.user.name, created.strftime('%m/%d/%Y@%H:%M'), '(No reason specified)' if l.reason is None else l.reason))
                current.append(b.user)
        for b in bans:
            if b.user not in current: array.append('{}: Banned because {}'.format(b.user.name, '(No reason specified)' if b.reason is None else b.reason))
        embed.add_field(name='Banned now',value='\n'.join(array)[:1023],inline=False)
        if len(array) == 0: 
            null.description='Sparkly clean ban history here!'
            return null
        embed.add_field(name='Banned previously',value='\n\n'.join([' • {}'.format(o) for o in other])[:1023])
        return embed

    async def MemberPosts(self, m: discord.Member):
        return len(await lightningdb.get_messages_by_author(m.id, [channel.id for channel in m.guild.text_channels]))

    async def evalInfo(self, obj, g: discord.Guild, logs):
        if type(obj) is discord.Embed: return obj
        if type(obj) is discord.Member: return await self.MemberInfo(obj, calculatePosts = False)
        if type(obj) is discord.Role: return await self.RoleInfo(obj, logs)
        if type(obj) in [discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]: 
            try: invites = await obj.invites()
            except: invites = False
            try: pins = await obj.pins()
            except: pins = False
            return (await self.ChannelInfo(obj, invites, pins, logs))[1]
        if type(obj) is discord.Emoji: return await self.EmojiInfo(obj, (await obj.guild.fetch_emoji(obj.id)).user)
        if type(obj) is discord.Invite: return await self.InviteInfo(obj, g)
        if type(obj) is discord.PartialEmoji: return await self.PartialEmojiInfo(obj, g)

async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
