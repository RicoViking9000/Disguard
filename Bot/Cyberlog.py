import discord
from discord.ext import commands, tasks
import database
import datetime
import asyncio
import os

bot = None
globalLogChannel = discord.TextChannel
imageLogChannel = discord.TextChannel
pauseDelete = 0
serverDelete = None
loading = None

invites = {}
edits = {}
summaries = {}
grabbedSummaries = {}

class MessageEditObject(object):
    def __init__(self, content, message, time):
        self.history = [MessageEditEntry(content, message.content, time)]
        self.message = message
        self.created = message.created_at

    def add(self, before, after, time):
        self.history.append(MessageEditEntry(before, after, time))
    
    def update(self, message):
        self.message = message

class MessageEditEntry(object):
    def __init__(self, before, after, time):
        self.before = before
        self.after = after
        self.time = time

class ServerSummary(object):
    def __init__(self, date):
        self.lastUpdate = date
        self.queue = []
        self.id = 0
        self.smarts = []
        self.sorted = 0 #0: Category, 1: Timestamp
    
    def add(self, mod, classification, timestamp, target, before, after, embed, content=None, reactions=None): #append summary
        self.queue.append(vars(Summary(mod, classification, timestamp, target, before, after, embed, content, reactions)))

    def categorize(self): #sort by category
        self.queue = sorted(self.queue, key = lambda x: x.get('category'))
        self.sorted = 0
    
    def chronologicalize(self): #sort by timestamp
        self.queue = sorted(self.queue, key = lambda x: x.get('timestamp'))
        self.sorted = 1

class Summary(object):
    def __init__(self, mod, classification, timestamp, target, before, after, embed, content=None, reactions=None):
        self.mod = mod #Which module is it under
        self.category = classification #Sticky notes
        self.timestamp = timestamp
        self.target = target
        self.before = before
        self.after = after
        self.embed = embed.to_dict()
        self.content = content
        self.reactions = reactions

class Cyberlog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.summarize.start()
    
    def cog_unload(self):
        self.summarize.cancel()

    @tasks.loop(minutes=15)
    async def summarize(self):
        try:
            global summaries
            global loading
            for server in self.bot.guilds:
                if database.GeneralSummarizeEnabled(server) and (datetime.datetime.now() - summaries.get(str(server.id)).lastUpdate).seconds / 60 > database.GetSummarize(server, summary.get('mod')):
                    e = discord.Embed(title='Server events recap', description='**{} total events**\nFrom {} {} to now\n\n'.format(len(summaries.get(str(server.id)).queue), summaries.get(str(server.id)).lastUpdate.strftime("%b %d, %Y - %I:%M %p"), database.GetNamezone(server)),timestamp=datetime.datetime.utcnow(), color=0x0000FF)
                    keycodes = {0: 'Message edits', 1: 'Message deletions', 2: 'Channel creations', 3: 'Channel edits', 4: 'Channel deletions', 5: 'New members',
                    6: 'Members that left', 7: 'Member unbanned', 8: 'Member updates', 9: 'Username/pfp updates', 10: 'Server updates', 11: 'Role creations', 
                    12: 'Role edits', 13: 'Role deletions', 14: 'Emoji updates', 15: 'Voice Channel updates'}
                    keyCounts = {} #Keycodes holds descriptions of events, keycounts hold respective count of events
                    for a in range(16):
                        keyCounts[a] = 0
                    summaries.get(str(server.id)).categorize()
                    for summary in summaries.get(str(server.id)).queue:
                        if database.SummarizeEnabled(server, summary.get('mod')):
                            keyCounts[summary.get('category')] = keyCounts.get(summary.get('category')) + 1
                    for a, b in keyCounts.items():
                        if b > 0: e.description += '{}: {} events\n'.format(keycodes.get(a), b)
                    e.description+='\n\nPress 🗓 to sort events by timestamp\nPress 📓 to view summary or details'
                    if len(summaries.get(str(server.id)).queue) > 0:
                        m = await database.GetMainLogChannel(server).send(embed=e) #Process smart embeds in the future
                        e.set_footer(text='Event ID: {}'.format(m.id))
                        summaries.get(str(server.id)).id = m.id
                        database.AppendSummary(server, summaries.get(str(server.id)))
                        await m.edit(embed=e)
                        for a in ['🗓', '📓']:
                            await m.add_reaction(a)
                        summaries[str(server.id)] = ServerSummary(datetime.datetime.now())
        except Exception as e: print(e)
        global bot
        for server in bot.guilds:
            try:
                invites[str(server.id)] = await server.invites()
                invites[str(server.id)+"_vanity"] = (await server.vanity_invite()).uses
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        '''[DISCORD API METHOD] Called when message is sent
        Unlike RicoBot, I don't need to spend over 1000 lines of code doing things here in [ON MESSAGE] due to the web dashboard :D'''
        path = "Indexes/{}/{}".format(message.guild.id, message.channel.id)
        try: f = open(path+'/{}.txt'.format(message.id), 'w+')
        except FileNotFoundError: return
        try: f.write(message.author.name+"\n"+str(message.author.id)+"\n"+message.content)
        except UnicodeEncodeError: pass
        try: f.close()
        except: pass
        if message.author.bot:
            return
        if database.GetImageLogPerms(message.guild) and len(message.attachments) > 0:
            path2 = 'Attachments/{}/{}/{}'.format(message.guild.id, message.channel.id, message.id)
            try: os.makedirs(path2)
            except FileExistsError: pass
            for a in message.attachments:
                try: await a.save(path2+'/'+a.filename)
                except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        ej = payload.emoji
        global bot
        global edits
        global loading
        global grabbedSummaries
        channel = bot.get_channel(payload.channel_id)
        try: message = await channel.fetch_message(payload.message_id)
        except: return
        user = bot.get_guild(channel.guild.id).get_member(payload.user_id)
        if user.bot: return
        if len(message.embeds) == 0: return
        if message.author.id != bot.get_guild(channel.guild.id).me.id: return
        e = message.embeds[0]
        f = e.footer.text
        try: fid = f[f.find(':')+2:]
        except: fid = str(message.id)
        me = channel.guild.me
        if str(ej) == 'ℹ':
            if 'Message was edited' in e.title or 'edit details' in e.title or 'event recaps' in e.title:
                try: await message.remove_reaction(ej, user)
                except discord.Forbidden: pass
                eo = edits.get(fid)
                after = eo.message
                details = discord.Embed(title='Message edit details',description='Author: {}\n__Viewing full edited message__'.format(after.author.name),timestamp=datetime.datetime.utcnow(),color=0x0000FF)
                before = eo.history[0].before
                beforeWordList = before.split(" ")
                afterWordList = after.content.split(" ")
                beforeC=''
                afterC=''
                for b in beforeWordList:
                    if b not in afterWordList:
                        beforeC += "**" + b + "** "
                    else:
                        beforeC += b + " "
                for b in afterWordList:
                    if b not in beforeWordList:
                        afterC += "**" + b + "** "
                    else:
                        afterC += b + " "
                details.add_field(name='Previously', value=beforeC, inline=False)
                details.add_field(name='Now', value=afterC, inline=False)
                details.add_field(name='Navigation', value='ℹ - full edited message\n📜 - message edit history\n🗒 - message in context')
                details.set_footer(text='Message ID: {}'.format(after.id))
                await message.edit(content=None,embed=details)
                for rr in ['📜', '🗒']:
                    await message.add_reaction(rr)
            if 'New member' in e.title:
                try: await message.remove_reaction(ej, user)
                except discord.Forbidden: pass
                if len(message.reactions) > 3:
                    for a in ['🤐', '👢', '🔨']:
                        try: await message.remove_reaction(a, me)
                        except discord.Forbidden: pass
                member = user.guild.get_member(int(fid))
                if member is None:
                    return await message.edit(content='Unable to provide statistics due to this member no longer being in this server')
                details=discord.Embed(title="New member",description=member.mention+" ("+member.name+")\n\n__Viewing extra statistics__",timestamp=datetime.datetime.utcnow(),color=0x008000)
                details.add_field(name='Servers I share',value=len([a for a in iter(bot.guilds) if member in a.members]))
                details.add_field(name='Reputation',value='Coming soon')
                details.add_field(name='Account created',value='{0.days} days ago'.format(datetime.datetime.utcnow() - member.created_at))
                details.add_field(name='Navigation',value='ℹ - member statistics\n🔍 - member information\n🕹 - member quick actions')
                details.set_footer(text=e.footer.text)
                await message.edit(content=None,embed=details)
                for a in ['🔍', '🕹']:
                    await message.add_reaction(a)
            await asyncio.sleep(180)
            if 'React with' in e.title or 'event recaps' in e.title or 'Message was edited' in e.title:
                await message.edit(embed=e)
                await message.clear_reactions()
                if 'event recaps' in e.title:
                    for a in ['⬅', '◀', '▶']: await message.add_reaction(a)
                await message.add_reaction('ℹ')
        if str(ej) == '📜':
            if 'edit details' in e.title:
                try: await message.remove_reaction(ej, user)
                except discord.Forbidden: pass
                eo = edits.get(fid)
                after = eo.message
                details = discord.Embed(title='Message edit details',description='Author: {}\n__Viewing message edit history__'.format(after.author.name),timestamp=datetime.datetime.utcnow(),color=0x0000FF)
                details.add_field(name='{} {}'.format((eo.created + datetime.timedelta(hours=database.GetTimezone(message.guild))).strftime("%b %d, %Y - %I:%M %p"), database.GetNamezone(message.guild)), value=eo.history[0].before, inline=False)
                for entry in eo.history:
                    details.add_field(name='{} {}'.format((entry.time + datetime.timedelta(hours=database.GetTimezone(message.guild))).strftime("%b %d, %Y - %I:%M %p"), database.GetNamezone(message.guild)), value=entry.after,inline=False)
                details.add_field(name='Navigation', value='ℹ - full edited message\n📜 - message edit history\n🗒 - message in context')
                details.set_footer(text='Message ID: {}'.format(after.id))
                await message.edit(content=None,embed=details)
        if str(ej) == '🗒':
            if 'edit details' in e.title:
                try: await message.remove_reaction(ej, user)
                except discord.Forbidden: pass
                eo = edits.get(fid)
                after = eo.message
                lst = None
                details = discord.Embed(title='Message edit details',description='Author: {}\n__Viewing message in context (oldest on top)__\nChannel: {}'.format(after.author.name, eo.message.channel.mention),timestamp=datetime.datetime.utcnow(),color=0x0000FF)
                try: 
                    lst = await after.channel.history(limit=1000).flatten()
                except discord.Forbidden:
                    details.description+='\n\nUnable to provide message in context'
                    await message.edit(content=None,embed=details)
                for m in range(len(lst)):
                    if lst[m].id == after.id:
                        for n in reversed(range(m-2,m+3)):
                            if n >= 0:
                                try:
                                    details.add_field(name=lst[n].author.name,value='[{}]({})'.format(lst[n].content, lst[n].jump_url) if len(lst[n].content)>0 else '(No content)',inline=False)
                                except IndexError:
                                    pass
                details.add_field(name='Navigation', value='ℹ - full edited message\n📜 - message edit history\n🗒 - message in context')
                details.set_footer(text='Message ID: {}'.format(after.id))
                await message.edit(content=None,embed=details)
        if str(ej) == '🔍':
            if 'New member' in e.title:
                try: await message.remove_reaction(ej, user)
                except discord.Forbidden: pass
                if len(message.reactions) > 3:
                    for a in ['🤐', '👢', '🔨']:
                        try: await message.remove_reaction(a, me)
                        except discord.Forbidden: pass
                member = message.guild.get_member(int(fid))
                details = discord.Embed(title=e.title, description=member.mention+" ("+member.name+")\n\n__Viewing member information__",timestamp=datetime.datetime.utcnow(),color=0x008000)
                details.set_footer(text=e.footer.text)
                joined=member.joined_at + datetime.timedelta(hours=database.GetTimezone(message.guild))
                created=member.created_at + datetime.timedelta(hours=database.GetTimezone(message.guild))
                details.add_field(name='Joined',value='{} {} ({} days ago)'.format(joined.strftime("%b %d, %Y - %I:%M %p"), database.GetNamezone(message.guild), (datetime.datetime.now()-joined).days))
                details.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y - %I:%M %p"), database.GetNamezone(message.guild), (datetime.datetime.now()-created).days))
                details.add_field(name='Currently',value=member.status+' (Mobile)' if member.is_on_mobile() else member.status)
                details.add_field(name='Top role',value=member.top_role)
                details.add_field(name='Role count',value=len(member.roles))
                details.description+='\n\n**Permissions:** {}'.format(database.StringifyPermissions(member.guild_permissions))
                details.add_field(name='Navigation',value='ℹ - member statistics\n🔍 - member information\n🕹 - member quick actions')
                details.set_thumbnail(url=member.avatar_url)
                await message.edit(content=None,embed=details)
        if str(ej) == '🕹':
            if 'New member' in e.title:
                try: await message.remove_reaction(ej, user)
                except discord.Forbidden: pass
                member = user.guild.get_member(int(fid))
                details = discord.Embed(title=e.title, description=member.mention+" ("+member.name+")\n\n__Viewing member quick actions__",timestamp=datetime.datetime.utcnow(),color=0x008000)
                details.set_footer(text=e.footer.text)
                details.description+='\n\nComing soon: Warn member\n🤐: Mute member\nComing soon: Lock out member\n👢: Kick member\n🔨: Ban member'
                details.add_field(name='Navigation',value='ℹ - member statistics\n🔍 - member information\n🕹 - member quick actions')
                await message.edit(content=None,embed=details)
                for a in ['🤐', '👢', '🔨']:
                    await message.add_reaction(a)
        if str(ej) == '🤐':
            if 'New member' in e.title:
                member = user.guild.get_member(int(fid))
                await message.edit(content='{}, are you sure you would like to mute {} for an indefinite period (until a mod removes it)? Type `yes` within 10s to confirm'.format(user.mention, member.name))
                def checkMute(m): return 'yes' in m.content.lower() and message.channel == m.channel and m.author.id == user.id and database.ManageRoles(user)
                try: result = await bot.wait_for('message',check=checkMute,timeout=10)
                except asyncio.TimeoutError: await message.edit(content=None)
                else: 
                    if result: 
                        muted=False
                        role=None
                        for a in message.guild.roles:
                            if a.name == "RicobotAutoMute": 
                                role=a
                                muted=True
                        if not muted:
                            try:
                                role = await message.guild.create_role(name="RicobotAutoMute", reason="Quickmute")
                                await role.edit(position=message.guild.me.top_role.position - 1)
                                for a in message.guild.channels:
                                    if type(a) is discord.TextChannel:
                                        await a.set_permissions(role, send_messages=False)
                            except discord.Forbidden:
                                muted=False
                        if not muted: 
                            await message.edit(content='Unable to mute {}, please ensure I have manage role permissions'.format(member.name))
                        await member.add_roles(role)
                        await message.edit(content='Successfully muted {}'.format(member.name))
                await message.remove_reaction(ej, user)
        if str(ej) == '👢':
            if 'New member' in e.title:
                member = user.guild.get_member(int(fid))
                await message.edit(content='{}, are you sure you would like to kick {}? Type a reason for the kick within 30s to confirm; to skip a reason, type `none`; to cancel, don\'t send a message'.format(user.mention, member.name))
                def checkKick(m): return 'none' != m.content.lower() and message.channel == m.channel and m.author.id == user.id and database.KickMembers(user)
                try: result = await bot.wait_for('message',check=checkKick,timeout=30)
                except asyncio.TimeoutError: await message.edit(content=None)
                else:
                    try: 
                        await member.kick(reason='{}: {}'.format(result.author.name, result.content))
                        await message.edit(content='Successfully kicked {}'.format(member.name))
                    except discord.Forbidden: await message.edit(content='Unable to kick {}'.format(member.name))
                await message.remove_reaction(ej, user)
        if str(ej) == '🔨':
            if 'New member' in e.title:
                member = user.guild.get_member(int(fid))
                await message.edit(content='{}, are you sure you would like to ban {}? Type a reason for the ban within 30s to confirm; to skip a reason, type `none`; to cancel, don\'t send a message'.format(user.mention, member.name))
                def checkBan(m): return 'none' != m.content.lower() and message.channel == m.channel and m.author.id == user.id and database.BanMembers(user)
                try: result = await bot.wait_for('message',check=checkBan,timeout=30)
                except asyncio.TimeoutError: await message.edit(content=None)
                else:
                    try: 
                        await member.ban(reason='{}: {}'.format(result.author.name, result.content))
                        await message.edit(content='Successfully banned {}'.format(member.name))
                    except discord.Forbidden: await message.edit(content='Unable to ban {}'.format(member.name))
                await message.remove_reaction(ej, user)
        if str(ej) in ['🗓', '📁', '⬅']:
            if 'events recap' in e.title or 'event recaps' in e.title:
                grabbedSummaries[str(message.id)] = database.GetSummary(message.guild, message.id)
                if str(ej) == '🗓':
                    grabbedSummaries[str(message.id)]['queue'] = sorted(grabbedSummaries.get(str(message.id)).get('queue'), key = lambda x: x.get('timestamp'))
                    grabbedSummaries[str(message.id)]['sorted'] = 1
                    e.description = '{} total events'.format(len(grabbedSummaries.get(str(message.id)).get('queue')))
                    e.description+='\n\nPress 📁 to sort events by category\nPress 📓 to view summary or details'
                    await message.clear_reactions()
                    await message.edit(content=None,embed=e)
                    for a in ['📁', '📓']: await message.add_reaction(a)
                else:
                    if 'event recaps' in e.title: 
                        e = discord.Embed(title='Server events recap', description='',timestamp=datetime.datetime.utcnow(), color=0x0000FF)
                        e.set_footer(text='Event ID: {}'.format(message.id))
                    grabbedSummaries[str(message.id)]['queue'] = sorted(grabbedSummaries.get(str(message.id)).get('queue'), key = lambda x: x.get('category'))
                    grabbedSummaries[str(message.id)]['sorted'] = 0
                    summ = grabbedSummaries.get(str(message.id))
                    e.description='**{} total events**\nFrom {} {} to now\n\n'.format(len(summ.get('queue')), summ.get('lastUpdate').strftime("%b %d, %Y - %I:%M %p"), database.GetNamezone(message.guild))
                    keycodes = {0: 'Message edits', 1: 'Message deletions', 2: 'Channel creations', 3: 'Channel edits', 4: 'Channel deletions', 5: 'New members',
                    6: 'Members that left', 7: 'Member unbanned', 8: 'Member updates', 9: 'Username/pfp updates', 10: 'Server updates', 11: 'Role creations', 
                    12: 'Role edits', 13: 'Role deletions', 14: 'Emoji updates', 15: 'Voice Channel updates'}
                    keyCounts = {} #Keycodes holds descriptions of events, keycounts hold respective count of events
                    for a in range(16):
                        keyCounts[a] = 0
                    for summary in summ.get('queue'):    
                        if database.SummarizeEnabled(message.guild, summary.get('mod')) and (datetime.datetime.now() - summ.get('lastUpdate')).seconds * 60 > database.GetSummarize(message.guild, summary.get('mod')):
                            keyCounts[summary.get('category')] = keyCounts.get(summary.get('category')) + 1
                    for a, b in keyCounts.items():
                        if b > 0: e.description += '{}: {} events\n'.format(keycodes.get(a), b)
                    e.description+='\n\nPress 📓 to view summary or details\nPress 🗓 to sort events by timestamp'
                    await message.clear_reactions()
                    await message.edit(content=None,embed=e)
                    for a in ['🗓', '📓']: await message.add_reaction(a)
        if str(ej) == '📓':
            await message.clear_reactions()
            try: 
                queue = grabbedSummaries.get(str(message.id)).get('queue')
                sort = grabbedSummaries.get(str(message.id)).get('sorted')
            except AttributeError: 
                queue = database.GetSummary(message.guild, message.id).get('queue')
                sort = 0
            embed = discord.Embed.from_dict(queue[0].get('embed'))
            template = discord.Embed(title='Server event recaps',description='Sort: Category' if sort is 0 else 'Sort: Timestamp',color=embed.color,timestamp=embed.timestamp)
            template.description+='\n⬅: Back to categories\n◀: Previous log\n▶: Next log'
            template.description+='\n\n__Viewing event 1 of {}__\n\n**{}**\n{}'.format(len(queue),embed.title,embed.description)
            for f in embed.fields: template.add_field(name=f.name, value=f.value, inline=f.inline)
            if len(embed.thumbnail.url) > 1: template.set_thumbnail(url=embed.thumbnail.url)
            if len(embed.image.url) > 1: template.set_image(url=embed.image.url)
            template.set_footer(text=embed.footer.text)
            await message.edit(content=None,embed=template)
            for r in ['⬅', '◀', '▶']: await message.add_reaction(r)
            for rr in queue[0].get('reactions'): await message.add_reaction(rr)
        if str(ej) in ['◀', '▶']:
            try: await message.remove_reaction(ej, user)
            except discord.Forbidden: pass
            if 'Server event recaps' not in e.title: return
            try: 
                queue = grabbedSummaries.get(str(message.id)).get('queue')
                sort = grabbedSummaries.get(str(message.id)).get('sorted')
            except AttributeError: 
                queue = database.GetSummary(message.guild, message.id).get('queue')
                sort = 0
            current = int(e.description[e.description.find('Viewing event')+14:e.description.find('of')-1]) - 1
            if str(ej) == '◀':
                current -= 1
                if current < 0: current = len(queue) - 1 #wrap-around scrolling
            else:
                current += 1
                if current > len(queue) - 1: current = 0 #wrap-around scrolling
            embed = discord.Embed.from_dict(queue[current].get('embed'))
            template = discord.Embed(title='Server event recaps',description='Sort: Category' if sort is 0 else 'Sort: Timestamp',color=embed.color,timestamp=embed.timestamp)
            template.description+='\n⬅: Back to categories\n◀: Previous log\n▶: Next log'
            template.description+='\n\n__Viewing event {} of {}__\n\n**{}**\n{}'.format(current+1,len(queue),embed.title,embed.description)
            for f in embed.fields: template.add_field(name=f.name, value=f.value, inline=f.inline)
            if len(embed.thumbnail.url) > 1: template.set_thumbnail(url=embed.thumbnail.url)
            if len(embed.image.url) > 1: template.set_image(url=embed.image.url)
            template.set_footer(text=embed.footer.text)
            await message.edit(content=None,embed=template)
            reactions = queue[current].get('reactions')
            for r in message.reactions:
                if str(r) not in ['⬅', '◀', '▶']:
                    await message.remove_reaction(r, message.guild.me)
            for rr in reactions:
                await message.add_reaction(rr)     

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or len(reaction.message.embeds) == 0 or reaction.message.author.id != reaction.message.guild.me.id:
            return
        global loading
        reactions = ['ℹ', '📜', '🗓', '📁', '📓']
        if str(reaction) in reactions or str(reaction) == '🗒':
            await reaction.message.edit(content=loading)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        '''[DISCORD API METHOD] Called when raw message is edited'''
        global bot
        global edits
        global loading #We have to get the previous content from indexed message and current from guild.get_message
        c = bot.get_channel(int(payload.data.get('channel_id')))
        try: after = await c.fetch_message(payload.message_id)
        except discord.NotFound: return
        g = bot.get_guild(int(payload.data.get('guild_id')))
        if not database.SimpleGetEnabled(g, 'message'):
            return
        if not database.CheckCyberlogExclusions(after.channel, after.author) or after.author.bot:
            return
        load=discord.Embed(title="Message was edited",description=str(loading),color=0x0000FF)
        embed = load.copy()
        c = database.GetLogChannel(g, 'message')
        if c is None: return
        msg = await c.send(embed=embed)
        before = ""
        path = 'Indexes/{}/{}'.format(payload.data.get('guild_id'), payload.data.get('channel_id'))
        for fl in os.listdir(path):
            if fl == str(payload.message_id)+'.txt':
                f = open(path+'/'+fl, 'r+')
                line = 0
                for l in f:
                    if line == 2:
                        before = l
                        f.close()
                        f = open(path+'/'+fl, 'w')
                        try: f.write(after.author.name+"\n"+str(after.author.id)+"\n"+after.content)
                        except UnicodeEncodeError: pass
                        f.close()
                        break
                    line+=1
                f.close()
        if before == after.content:
            return await msg.delete()
        timestamp = datetime.datetime.utcnow()
        if edits.get(str(payload.message_id)) is None:
            edits[str(payload.message_id)] = MessageEditObject(before, after, timestamp)
        else:
            edits.get(str(payload.message_id)).add(before, after.content, timestamp)
            edits.get(str(payload.message_id)).update(after)
        beforeWordList = before.split(" ")
        afterWordList = after.content.split(" ")
        beforeC = ""
        afterC = ""
        b=0
        while b < len(beforeWordList):
            start=b
            if beforeWordList[b] not in afterWordList:
                if b>2: beforeC+='...'
                for m in reversed(range(1, 3)):
                    if b-m>=0: beforeC+=beforeWordList[b-m]+" "
                beforeC += "**"+beforeWordList[b]+"** "
                m=b+1
                matchCount=0
                matches=[] #Array of T/F depending on if word matches - if word matches, don't bold it
                trueCount=0
                while m < len(beforeWordList):
                    if beforeWordList[m] in afterWordList: 
                        matchCount+=1
                        trueCount+=1
                        matches.append(True)
                    else:
                        matchCount=0
                        matches.append(False)
                    if matchCount == 2:
                        break
                    m+=1
                confirmCount=0
                for match in range(len(matches)):
                    if matches[match]:
                        confirmCount+=1
                        beforeC+=beforeWordList[match+b+1]+" "
                        if confirmCount==trueCount: break
                    else: beforeC+='**'+beforeWordList[match+b+1]+'** '
                if m < len(beforeWordList) - 1:
                    beforeC+='... '
                b=m+1
            if b==start:b+=1
        b=0
        while b < len(afterWordList):
            start=b
            if afterWordList[b] not in beforeWordList:
                if b>2: afterC+='...'
                for m in reversed(range(1, 3)):
                    if b-m>=0: afterC+=afterWordList[b-m]+" "
                afterC += "**"+afterWordList[b]+"** "
                m=b+1
                matchCount=0
                matches=[] #Array of T/F depending on if word matches - if word matches, don't bold it
                trueCount=0
                while m < len(afterWordList):
                    if afterWordList[m] in beforeWordList: 
                        matchCount+=1
                        trueCount+=1
                        matches.append(True)
                    else:
                        matchCount=0
                        matches.append(False)
                    if matchCount == 2:
                        break
                    m+=1
                confirmCount=0
                for match in range(len(matches)):
                    if matches[match]:
                        confirmCount+=1
                        afterC+=afterWordList[match+b+1]+" "
                        if confirmCount==trueCount: break
                    else: afterC+='**'+afterWordList[match+b+1]+'** '
                if m < len(afterWordList) - 1:
                    afterC+='... '
                b=m+1
            if b==start:b+=1
        if len(beforeC) >= 1024: beforeC = 'Message content too long to display here'
        if len(afterC) >= 1024: afterC = 'Message content too long to display here'
        embed.description="Author: "+after.author.mention+" ("+after.author.name+")"
        embed.timestamp=timestamp
        embed.add_field(name="Previously: ", value=beforeC if len(beforeC) > 0 else '(No new content)',inline=False)
        embed.add_field(name="Now: ", value=afterC if len(afterC) > 0 else '(No new content)',inline=False)
        embed.add_field(name="Channel: ", value=str(after.channel.mention))
        embed.add_field(name="Edits are truncated",value="React with ℹ to see more information")
        embed.set_footer(text="Message ID: " + str(after.id))
        embed.set_thumbnail(url=after.author.avatar_url)
        if database.SummarizeEnabled(g, 'message'):
            global summaries
            summaries.get(str(g.id)).add('message', 0, datetime.datetime.now(), after.id, before, after.content, embed, reactions=['ℹ'])
            await msg.delete()
        else:
            try: 
                await msg.edit(embed=embed)
                await msg.add_reaction('ℹ')
            except discord.HTTPException:
                await msg.edit(embed=discord.Embed(title="Message was edited",description='Message content is too long to post here',color=0x0000FF,timestamp=datetime.datetime.utcnow()))

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        '''[DISCORD API METHOD] Called when message is deleted (RAW CONTENT)'''
        global pauseDelete
        global serverDelete
        global loading
        global bot
        global imageLogChannel
        message = None
        g = message.guild if message is not None else bot.get_guild(payload.guild_id)
        c = database.GetLogChannel(g, 'message')
        try: message = payload.cached_message
        except AttributeError:
            message = None
        if message is not None and pauseDelete > 0 and message.guild == serverDelete:
            pauseDelete -= 1
            return
        elif pauseDelete == 0:
            serverDelete = None
        if not database.GetEnabled(g, 'message'):
            return
        embed=discord.Embed(title="Message was deleted",timestamp=datetime.datetime.utcnow(),color=0xff0000)
        embed.set_footer(text="Message ID: {}".format(payload.message_id))
        ma = message.author if message is not None else None
        attachments = []
        path = 'Attachments/{}/{}/{}'.format(payload.guild_id,payload.channel_id, payload.message_id)
        try:
            for fil in os.listdir(path):
                if '.png' in fil or '.jpg' in fil or '.gif' in fil or '.webp' in fil:
                    t = await imageLogChannel.send(file=discord.File(path+'/'+fil, fil))
                    embed.set_image(url=t.attachments[0].url)
                else:
                    attachments.append(discord.File(path+'/'+fil, fil))
        except OSError: attachments = None
        s = None
        if message is not None:
            if not database.CheckCyberlogExclusions(message.channel, message.author) or message.author.bot:
                return
            embed.description="Author: "+message.author.mention+" ("+message.author.name+")\nChannel: "+message.channel.mention+"\nSent: {} {}".format((message.created_at + datetime.timedelta(hours=database.GetTimezone(message.guild))).strftime("%b %d, %Y - %I:%M %p"), database.GetNamezone(message.guild))
            embed.set_thumbnail(url=message.author.avatar_url)
            if attachments is None:
                for ext in ['.png', '.jpg', '.gif', '.webp']:
                    if ext in message.content:
                        if '://' in message.content:
                            url = message.content[message.content.find('http'):message.content.find(ext)+len(ext)+1]
                            embed.set_image(url=url)
            embed.add_field(name="Content",value="(No content)" if message.content is None or len(message.content)<1 else message.content)
        else:
            embed.description="Message is old...\n\n"+str(loading)+" Attempting to retrieve some data..." #Now we have to search the file system
            s = await c.send(embed=embed)
            f=None
            directory = "Indexes/{}/{}".format(payload.guild_id,payload.channel_id)
            for fl in os.listdir(directory):
                if fl == str(payload.message_id)+".txt":
                    f = open(directory+"/"+fl, "r")
                    line = 0
                    authorName = ""
                    authorID = 0
                    messageContent = ""
                    for l in f:
                        if line == 0:
                            authorName = l
                        elif line == 1:
                            authorID = int(l)
                        elif line == 2:
                            messageContent = l
                        line+=1
                    f.close()
                    os.remove(directory+"/"+fl)
                    author = bot.get_guild(payload.guild_id).get_member(authorID)
                    if author is None or author.bot or author not in g.members or not database.CheckCyberlogExclusions(bot.get_channel(payload.channel_id), author):
                        return await s.delete()
                    embed.description=""
                    if author is not None: 
                        embed.description+="Author: "+author.mention+" ("+author.name+")\n"
                        embed.set_thumbnail(url=author.avatar_url)
                    else:
                        embed.description+="Author: "+authorName+"\n"
                        ma = author
                    embed.description+="Channel: "+bot.get_channel(payload.channel_id).mention+"\n"
                    embed.add_field(name="Content",value="(No content)" if messageContent is "" or len(messageContent)<1 else messageContent)
                    for ext in ['.png', '.jpg', '.gif', '.webp']:
                        if ext in messageContent:
                            if '://' in messageContent:
                                url = messageContent[message.content.find('http'):messageContent.find(ext)+len(ext)+1]
                                embed.set_image(url=url)
                    break #the for loop
            if f is None:
                return await s.edit(embed=discord.Embed(title="Message was deleted",description='Unable to provide more information',timestamp=datetime.datetime.utcnow(),color=0xff0000))
        content=None
        if database.GetReadPerms(g, "message"):
            try:
                async for log in g.audit_logs(limit=1):
                    if log.action == discord.AuditLogAction.message_delete and log.target == ma and (datetime.datetime.utcnow() - log.created_at).seconds < 120:
                        if log.action == discord.AuditLogAction.message_delete:
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
            except discord.Forbidden:
                content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
        global summaries
        if s is not None:
            if database.SummarizeEnabled(g, 'message'):  
                summaries.get(str(g.id)).add('message', 1, datetime.datetime.now(), payload.message_id, None, None, embed,content=content)
                await s.delete()
            else:
                await s.edit(content=content,embed=embed,files=attachments)
        else:
            if database.SummarizeEnabled(g, 'message'):
                summaries.get(str(g.id)).add('message', 1, datetime.datetime.now(), payload.message_id, None, None, embed,content=content)
            else:
                await c.send(content=content,embed=embed,files=attachments)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is created'''
        global bot
        content=None
        if database.GetEnabled(channel.guild, "channel"):
            chan = "📜 Text" if type(channel) is discord.TextChannel else None
            chan = "🎙 Voice" if type(channel) is discord.VoiceChannel else chan
            chan = "📂 Category" if type(channel) is discord.CategoryChannel else chan
            embed=discord.Embed(title=chan + " Channel was created", description=channel.mention+" ("+channel.name+")" if type(channel) is discord.TextChannel else channel.name,color=0x008000,timestamp=datetime.datetime.utcnow())
            if type(channel) is not discord.CategoryChannel:
                embed.add_field(name="Category",value=str(channel.category.name))
            if database.GetReadPerms(channel.guild, "channel"):
                try:
                    async for log in channel.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_create:
                            embed.description+="\nCreated by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.set_footer(text="Channel ID: "+str(channel.id))
            if database.SummarizeEnabled(channel.guild, 'channel'):
                summaries.get(str(channel.guild.id)).add('channel', 2, datetime.datetime.now(), channel.id, None, None, embed,content=content)
            else:
                await database.GetLogChannel(channel.guild, "channel").send(content=content,embed=embed)
        if type(channel) is discord.TextChannel:
            path = "Indexes/{}/{}".format(channel.guild.id, channel.id)
            try: os.makedirs(path)
            except FileExistsError: pass
        database.VerifyServer(channel.guild, bot) #Update database to reflect creation. This call is used frequently here. Placed at bottom to avoid delay before logging

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is updated'''
        global bot
        if database.GetEnabled(before.guild, "channel"):
            content=None
            chan = "📜 Text" if type(before) is discord.TextChannel else None
            chan = "🎙 Voice" if type(before) is discord.VoiceChannel else chan
            chan = "📂 Category" if type(before) is discord.CategoryChannel else chan
            embed=discord.Embed(title=chan + " Channel was updated", description=before.mention if type(before) is discord.TextChannel else before.name,color=0x0000FF,timestamp=datetime.datetime.utcnow())
            if database.GetReadPerms(before.guild, "channel"):
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_update:
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.set_footer(text="Channel ID: "+str(before.id))
            if before.name != after.name: 
                embed.add_field(name="Prev name",value=before.name)
                embed.add_field(name="New name",value=after.name)
            if type(before) is discord.TextChannel:
                if before.topic != after.topic:
                    beforeTopic = before.topic if before.topic is not None else "<No topic>"
                    afterTopic = after.topic if after.topic is not None else "<No topic>"
                    embed.add_field(name="Prev topic",value=beforeTopic)
                    embed.add_field(name="New topic",value=afterTopic)
                if before.is_nsfw() != after.is_nsfw():
                    embed.add_field(name="Prev NSFW",value=before.is_nsfw())
                    embed.add_field(name="New NSFW",value=after.is_nsfw())
            elif type(before) is discord.VoiceChannel:
                if before.bitrate != after.bitrate:
                    embed.add_field(name="Prev Bitrate",value=before.bitrate)
                    embed.add_field(name="New Bitrate",value=after.bitrate)
                if before.user_limit != after.user_limit:
                    embed.add_field(name="Prev User limit",value=before.user_limit)
                    embed.add_field(name="New User limit",value=after.user_limit)
            if type(before) is not discord.CategoryChannel and before.category != after.category:
                beforeCat = str(before.category) if before.category is not None else "<No category>"
                afterCat = str(after.category) if after.category is not None else "<No category>"
                embed.add_field(name="Prev category",value=beforeCat)
                embed.add_field(name="New category",value=afterCat)
            if len(embed.fields) > 0:
                if database.SummarizeEnabled(before.guild, 'channel'):
                    summaries.get(str(before.guild.id)).add('channel', 3, datetime.datetime.now(), before.id, None, None, embed,content=content)
                else:
                    await database.GetLogChannel(before.guild, "channel").send(content=content,embed=embed)
        database.VerifyServer(before.guild, bot)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when channel is deleted'''
        global bot
        if database.GetEnabled(channel.guild, "channel"):
            content=None
            chan = "📜 Text" if type(channel) is discord.TextChannel else None
            chan = "🎙 Voice" if type(channel) is discord.VoiceChannel else chan
            chan = "📂 Category" if type(channel) is discord.CategoryChannel else chan
            embed=discord.Embed(title=chan + " Channel was deleted", description=channel.name,color=0xff0000,timestamp=datetime.datetime.utcnow())
            if type(channel) is not discord.CategoryChannel:
                embed.add_field(name="Category",value=str(channel.category.name))
            if database.GetReadPerms(channel.guild, "channel"):
                try:
                    async for log in channel.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_delete:
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.set_footer(text="Channel ID: "+str(channel.id))
            if database.SummarizeEnabled(channel.guild, 'channel'):
                summaries.get(str(channel.guild.id)).add('channel', 4, datetime.datetime.now(), channel.id, None, None, embed,content=content)
            else:
                await database.GetLogChannel(channel.guild, "channel").send(content=content,embed=embed)
        database.VerifyServer(channel.guild, bot)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member joins a server'''
        global bot
        global invites
        if database.GetEnabled(member.guild, "doorguard"):
            newInv = []
            content=None
            count=len(member.guild.members)
            suffix='th'
            if count % 100 in [11, 12, 13]:
                suffix='th'
            elif count%10==1:
                suffix='st'
            elif count%10==2:
                suffix='nd'
            elif count%10==3:
                suffix='rd'
            embed=discord.Embed(title="New member (React with ℹ to see member info)",description=member.mention+" ("+member.name+")\n{}{} member".format(count,suffix),timestamp=datetime.datetime.utcnow(),color=0x008000)
            embed.set_thumbnail(url=member.avatar_url)
            embed.set_footer(text='Member ID: {}'.format(member.id))
            try:
                newInv = await member.guild.invites()
            except discord.Forbidden:
                content="Tip: I can determine who invited new members if I have the <Manage Server> permissions"
                if database.SummarizeEnabled(member.guild, 'doorguard'):
                    summaries.get(str(member.guild.id)).add('doorguard', 5, datetime.datetime.now(), member.id, None, None, embed,content=content,reactions=['ℹ'])
                else:
                    return await database.GetLogChannel(member.guild, 'doorguard').send(content=content,embed=embed)
            #All this below it only works if the bot successfully works with invites
            try:
                for invite in newInv:
                    if invite in invites.get(str(member.guild.id)):
                        for invite2 in invites.get(str(member.guild.id)):
                            if invite2 == invite:
                                if invite.uses > invite2.uses:
                                    embed.add_field(name="Invited by",value=invite.inviter.mention+" ("+invite.inviter.name+")")
                                    break
                if len(embed.fields) == 0: #check vanity invite for popular servers
                    for invite in newInv: #Check for new invites
                        if invite not in invites.get(str(member.guild.id)):
                            if invite.uses > 0:
                                embed.add_field(name="Invited by",value=invite.inviter.mention+" ("+invite.inviter.name+")")
                                break
                    try:
                        invite = await member.guild.vanity_invite()
                        if invite.uses > invites.get(str(member.guild.id)+"_vanity"):
                            embed.add_field(name="Invited by",value=invite.inviter.mention+" ("+invite.inviter.name+")\n{VANITY INVITE}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
            except AttributeError: embed.add_field(name='Invited by',value='N/A')
            invites[str(member.guild.id)] = newInv
            if database.SummarizeEnabled(member.guild, 'doorguard'):
                summaries.get(str(member.guild.id)).add('doorguard', 5, datetime.datetime.now(), member.id, None, None, embed,content=content,reactions=['ℹ'])
            else:
                msg = await database.GetLogChannel(member.guild, "doorguard").send(content=content,embed=embed)
                await msg.add_reaction('ℹ')
        database.VerifyServer(member.guild, bot)
        database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member leaves a server'''
        global bot
        if database.GetEnabled(member.guild, "doorguard"):
            content=None
            embed=None
            if embed is None: 
                embed=discord.Embed(title="Member left",description=member.mention+" ("+member.name+")",timestamp=datetime.datetime.utcnow(),color=0xff0000)
                if database.GetReadPerms(member.guild, 'doorguard'):
                    try:
                        async for log in member.guild.audit_logs(limit=1):
                            if (datetime.datetime.utcnow() - log.created_at).seconds < 10 and log.target == member:
                                if log.action == discord.AuditLogAction.kick:
                                    embed.title = member.name+" was kicked"
                                    embed.description="Kicked by: "+log.user.mention+" ("+log.user.name+")"
                                    embed.add_field(name="Reason",value=log.reason if log.reason is not None else "None provided",inline=True if len(log.reason) < 25 else False)
                                elif log.action == discord.AuditLogAction.ban:
                                    embed.title = member.name+" was banned"
                                    embed.description="Banned by: "+log.user.mention+" ("+log.user.name+")"
                                    embed.add_field(name="Reason",value=log.reason if log.reason is not None else "None provided",inline=True if len(log.reason) < 25 else False)
                    except discord.Forbidden:
                        content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            span = datetime.datetime.utcnow() - member.joined_at
            hours = span.seconds//3600
            minutes = (span.seconds//60)%60
            embed.add_field(name="Here for",value=str(span.days)+" days, "+str(hours)+" hours, "+str(minutes)+" minutes, "+str(span.seconds - hours*3600 - minutes*60)+" seconds")
            embed.set_thumbnail(url=member.avatar_url)
            embed.set_footer(text="User ID: "+str(member.id))
            if database.SummarizeEnabled(member.guild, 'doorguard'):
                summaries.get(str(member.guild.id)).add('doorguard', 6, datetime.datetime.now(), member.id, None, None, embed,content=content)
            else:
                await database.GetLogChannel(member.guild, "doorguard").send(content=content,embed=embed)
        database.VerifyServer(member.guild, bot)
        database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if database.GetEnabled(guild, 'doorguard'):
            embed=discord.Embed(title=user.name+" was unbanned",description="",timestamp=datetime.datetime.utcnow(),color=0x008000)
            content=None
            if database.GetReadPerms(guild, 'doorguard'):
                try:
                    async for log in guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.unban:
                            embed.description = "by "+log.user.mention+" ("+log.user.name+")"
                    async for log in guild.audit_logs(limit=1000):
                        if log.action == discord.AuditLogAction.ban:
                            if log.target == user:
                                span = datetime.datetime.utcnow() - log.created_at
                                hours = span.seconds//3600
                                minutes = (span.seconds//60)%60
                                embed.add_field(name="Banned for",value=str(span.days)+" days, "+str(hours)+" hours, "+str(minutes)+" minutes, "+str(span.seconds - hours*3600 - minutes*60)+" seconds")
                                break
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>\nI also need that permission to determine if a member was kicked/banned"
            embed.set_thumbnail(url=user.avatar_url)
            embed.set_footer(text="User ID: "+str(user.id))
            if database.SummarizeEnabled(guild, 'doorguard'):
                summaries.get(str(guild.id)).add('doorguard', 7, datetime.datetime.now(), user.id, None, None, embed,content=content)
            else:
                await database.GetLogChannel(guild, 'doorguard').send(content=content,embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        '''[DISCORD API METHOD] Called when member changes status/game, roles, or nickname; only the two latter events used with this bot'''
        if (before.nick != after.nick or before.roles != after.roles) and database.GetEnabled(before.guild, "member"):
            content=None
            embed=discord.Embed(title="Member's server attributes updated",description=before.mention+"("+before.name+")",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
            if before.roles != after.roles:
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.member_role_update and (datetime.datetime.utcnow() - log.created_at).seconds < 60 and log.target == before: 
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
                added = []
                removed = []
                for f in after.roles:
                    if f not in before.roles:
                        if f.name != "RicobotAutoMute" and f != before.guild.get_role(database.GetAntiSpamObject(before.guild).get("customRoleID")):
                            added.append(f.name)
                for f in before.roles:
                    if f not in after.roles:
                        if f.name != "RicobotAutoMute" and f != before.guild.get_role(database.GetAntiSpamObject(before.guild).get("customRoleID")) and f in before.guild.roles:
                            removed.append(f.name)
                if len(added) > 0: embed.add_field(name='Role(s) added',value=', '.join(added))
                if len(removed) > 0: embed.add_field(name='Role(s) removed',value=', '.join(removed))
            if before.nick != after.nick:
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.member_update and (datetime.datetime.utcnow() - log.created_at).seconds < 60 and log.target == before: 
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
                oldNick = before.nick if before.nick is not None else "<No nickname>"
                newNick = after.nick if after.nick is not None else "<No nickname>"
                embed.add_field(name="Prev nickname",value=oldNick)
                embed.add_field(name="New nickname",value=newNick)
            embed.set_thumbnail(url=before.avatar_url)
            embed.set_footer(text="Member ID: "+str(before.id))
            if len(embed.fields) > 0:
                if database.SummarizeEnabled(before.guild, 'member'):
                    summaries.get(str(before.guild.id)).add('member', 8, datetime.datetime.now(), before.id, None, None, embed,content=content)
                else:
                    await database.GetLogChannel(before.guild, "member").send(content=content,embed=embed)
        global bot
        database.VerifyUser(before, bot)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        '''[DISCORD API METHOD] Called when a user changes their global username, avatar, or discriminator'''
        servers = []
        global bot
        membObj = None
        for server in bot.guilds: #Since this method doesn't supply a server, we need to get every server this member is a part of, to
            for member in server.members: #log to when they change their username, discriminator, or avatar
                if member.id == before.id:
                    servers.append(server)
                    membObj = member
                    break
        embed=discord.Embed(title="User's global attributes updated",description=after.mention+"("+after.name+")",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
        if before.avatar_url != after.avatar_url:
            if before.avatar_url is not None:
                embed.set_thumbnail(url=before.avatar_url)
            if after.avatar_url is not None:
                embed.set_image(url=after.avatar_url)
            embed.add_field(name="Profile Picture updated",value="Old: Thumbnail to the right\nNew: Image below")
        else:
            embed.set_thumbnail(url=before.avatar_url)
        if before.discriminator != after.discriminator:
            embed.add_field(name="Prev discriminator",value=before.discriminator)
            embed.add_field(name="New discriminator",value=after.discriminator)
        if before.name != after.name:
            embed.add_field(name="Prev username",value=before.name)
            embed.add_field(name="New username",value=after.name)
        embed.set_footer(text="User ID: "+str(after.id))
        for server in servers:
            database.VerifyServer(server, bot)
            if database.GetEnabled(server, "member"):
                if database.SummarizeEnabled(server, 'member'):
                    summaries.get(str(server.id)).add('member', 9, datetime.datetime.now(), before.id, None, None, embed)
                else:
                    await database.GetLogChannel(server, "member").send(embed=embed)
        database.VerifyUser(membObj, bot)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot joins a server'''
        global bot
        global globalLogChannel
        await globalLogChannel.send(embed=discord.Embed(title="Joined server",description=guild.name,timestamp=datetime.datetime.utcnow(),color=0x008000))
        database.VerifyServer(guild, bot)
        for member in guild.members:
            database.VerifyUser(member, bot)
        message=None
        global loading
        content="Thank you for inviting me to your server!\nTo configure me, you can connect your Discord account and enter your server's settings here: `https://disguard.herokuapp.com`\n{}Please wait while I index your server's messages...".format(loading)
        if guild.system_channel is not None:
            try: message = await guild.system_channel.send(content) #Update later to provide more helpful information
            except discord.Forbidden: pass
        if message is None:
            for channel in guild.text_channels:
                if 'general' in channel.name:
                    try: message = await guild.system_channel.send(content) #Update later to provide more helpful information
                    except discord.Forbidden: pass
        for channel in guild.text_channels:
            path = "Indexes/{}/{}".format(guild.id, channel.id)
            try: os.makedirs(path)
            except FileExistsError: pass
            try:
                async for message in channel.history(limit=10000000):
                    if str(message.id)+".txt" in os.listdir(path): break
                    try: f = open(path+"/"+str(message.id)+".txt", "w+")
                    except FileNotFoundError: pass
                    try: f.write(message.author.name+"\n"+str(message.author.id)+"\n"+message.content)
                    except UnicodeEncodeError: pass
                    try: f.close()
                    except: pass
            except discord.Forbidden:
                pass
        await message.edit(content="Thank you for inviting me to your server!\nTo configure me, you can connect your Discord account and enter your server's settings here: `https://disguard.herokuapp.com`")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        global bot
        if database.GetEnabled(before, 'server'):
            embed=discord.Embed(title="Server updated",description="",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
            content=None
            if database.GetReadPerms(before, 'server'):
                try:
                    async for log in before.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.guild_update:
                            embed.description= "By: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            if before.afk_channel != after.afk_channel:
                b4 = before.afk_channel.name if before.afk_channel is not None else "(None)"
                af = after.afk_channel.name if after.afk_channel is not None else "(None)"
                embed.add_field(name="AFK Channel",value=b4+" → "+af)
            if before.afk_timeout != after.afk_timeout:
                embed.add_field(name="AFK Timeout",value=str(before.afk_timeout)+"s → "+str(after.afk_timeout)+"s")
            if before.mfa_level != after.mfa_level:
                b4 = True if before.mfa_level == 1 else False
                af = True if after.mfa_level == 1 else False
                embed.add_field(name="Mods need 2FA",value=b4+" → "+af)
            if before.name != after.name:
                embed.add_field(name="Name",value=before.name+" → "+after.name)
            if before.owner != after.owner:
                embed.add_field(name="Owner",value=before.owner.mention+" → "+after.owner.mention)
            if before.default_notifications != after.default_notifications:
                embed.add_field(name="Default notifications",value=before.default_notifications.name+" → "+after.default_notifications.name)
            if before.explicit_content_filter != after.explicit_content_filter:
                embed.add_field(name="Explicit content filter",value=before.explicit_content_filter.name+" → "+after.explicit_content_filter.name)
            if before.system_channel != after.system_channel:
                b4 = before.system_channel.mention if before.system_channel is not None else "(None)"
                af = after.system_channel.mention if after.system_channel is not None else "(None)"
                embed.add_field(name="System channel",value=b4+" → "+af)
            if before.icon_url != after.icon_url:
                embed.add_field(name='Server icon updated',value='Old: Thumbnail to the right\nNew: Image below')
                embed.set_thumbnail(url=before.icon_url)
                embed.set_image(url=after.icon_url)
            if len(embed.fields) > 0:
                if database.SummarizeEnabled(before, 'server'):
                    summaries.get(str(before.id)).add('server', 10, datetime.datetime.now(), before.id, None, None, embed,content=content)
                else:
                    await database.GetLogChannel(before, 'server').send(content=content,embed=embed)
        database.VerifyServer(after, bot)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot leaves a server'''
        global bot
        global globalLogChannel
        await globalLogChannel.send(embed=discord.Embed(title="Left server",description=guild.name,timestamp=datetime.datetime.utcnow(),color=0xff0000))
        database.VerifyServer(guild, bot)
        for member in guild.members:
            database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is created'''
        global bot
        if database.GetEnabled(role.guild, "role"):
            content=None
            embed=discord.Embed(title="Role created",timestamp=datetime.datetime.utcnow(),description=" ",color=0x008000)
            embed.description="Name: "+role.name if role.name != "new role" else ""
            embed.set_footer(text='Role ID: {}'.format(role.id))
            if database.GetReadPerms(role.guild, "role"):
                try:
                    async for log in role.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.role_create: 
                            embed.description+="\nCreated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            if database.SummarizeEnabled(role.guild, 'role'):
                summaries.get(str(role.guild.id)).add('role', 11, datetime.datetime.now(), role.id, None, None, embed,content=content)
            else:
                await database.GetLogChannel(role.guild, "role").send(content=content,embed=embed)
        database.VerifyServer(role.guild, bot)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is deleted'''
        global bot
        if database.GetEnabled(role.guild, "role"):
            content=None
            embed=discord.Embed(title="Role deleted",description="Role: "+role.name,timestamp=datetime.datetime.utcnow(),color=0xff0000)
            embed.set_footer(text='Role ID: {}'.format(role.id))
            if database.GetReadPerms(role.guild, "role"):
                try:
                    async for log in role.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.role_delete: 
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            if database.SummarizeEnabled(role.guild, 'role'):
                summaries.get(str(role.guild.id)).add('role', 12, datetime.datetime.now(), role.id, None, None, embed,content=content)
            else:
                await database.GetLogChannel(role.guild, "role").send(content=content,embed=embed)
        database.VerifyServer(role.guild, bot)
        for member in role.members:
            database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is updated'''
        global bot
        if database.GetEnabled(before.guild, "role"):
            content=None
            color=0x0000FF if before.color == after.color else after.color
            embed=discord.Embed(title="Role was updated",description="Name: "+ after.name if before.name == after.name else "Name: "+before.name+" → "+after.name,color=color,timestamp=datetime.datetime.utcnow())
            if database.GetReadPerms(before.guild, "role"):
                try:
                    async for log in before.guild.audit_logs(limit=1): #Color too
                            if log.action == discord.AuditLogAction.role_update:
                                embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            if before.color != after.color: embed.description+="\nEmbed color represents new role color"
            embed.description+="\n:warning: "+str(len(after.members))+" members received updated permissions :warning:"
            embed.description+='\n\n**__THIS ROLE HAS THE FOLLOWING UNCHANGED ATTRIBUTES AND PERMISSIONS__**\n{}'.format(', '.join(database.UnchangedPerms(before, after)))
            if before.permissions.administrator != after.permissions.administrator: embed.add_field(name="Admin",value=str(before.permissions.administrator+" → "+after.permissions.administrator),inline=False)
            if before.hoist != after.hoist: embed.add_field(name="Displayed separately",value=str(before.hoist)+" → "+str(after.hoist))
            if before.mentionable != after.mentionable: embed.add_field(name="Mentionable",value=str(before.mentionable)+" → "+str(after.mentionable))
            if before.permissions.create_instant_invite != after.permissions.create_instant_invite: embed.add_field(name="Create invites",value=str(before.permissions.create_instant_invite)+" → "+str(after.permissions.create_instant_invite))
            if before.permissions.kick_members != after.permissions.kick_members: embed.add_field(name="Kick",value=str(before.permissions.kick_members)+" → "+str(after.permissions.kick_members))
            if before.permissions.ban_members != after.permissions.ban_members: embed.add_field(name="Ban",value=str(before.permissions.ban_members)+" → "+str(after.permissions.ban_members))
            if before.permissions.manage_channels != after.permissions.manage_channels: embed.add_field(name="Manage channels",value=str(before.permissions.manage_channels)+" → "+str(after.permissions.manage_channels))
            if before.permissions.manage_guild != after.permissions.manage_guild: embed.add_field(name="Manage server",value=str(before.permissions.manage_guild)+" → "+str(after.permissions.manage_guild))
            if before.permissions.add_reactions != after.permissions.add_reactions: embed.add_field(name="Add reactions",value=str(before.permissions.add_reactions)+" → "+str(after.permissions.add_reactions))
            if before.permissions.view_audit_log != after.permissions.view_audit_log: embed.add_field(name="View audit log",value=str(before.permissions.view_audit_log)+" → "+str(after.permissions.view_audit_log))
            if before.permissions.priority_speaker != after.permissions.priority_speaker: embed.add_field(name="[VC] Priority speaker",value=str(before.permissions.priority_speaker)+" → "+str(after.permissions.priority_speaker))
            if before.permissions.read_messages != after.permissions.read_messages: embed.add_field(name="Read messages",value=str(before.permissions.read_messages)+" → "+str(after.permissions.read_messages))
            if before.permissions.send_messages != after.permissions.send_messages: embed.add_field(name="Send messages",value=str(before.permissions.send_messages)+" → "+str(after.permissions.send_messages))
            if before.permissions.send_tts_messages != after.permissions.send_tts_messages: embed.add_field(name="Use /TTS",value=str(before.permissions.send_tts_messages)+" → "+str(after.permissions.send_tts_messages))
            if before.permissions.manage_messages != after.permissions.manage_messages: embed.add_field(name="Manage messages",value=str(before.permissions.manage_messages)+" → "+str(after.permissions.manage_messages))
            if before.permissions.embed_links != after.permissions.embed_links: embed.add_field(name="Embed URLs",value=str(before.permissions.embed_links)+" → "+str(after.permissions.embed_links))
            if before.permissions.attach_files != after.permissions.attach_files: embed.add_field(name="Attach files",value=str(before.permissions.attach_files)+" → "+str(after.permissions.attach_files))
            if before.permissions.read_message_history != after.permissions.read_message_history: embed.add_field(name="Read message history",value=str(before.permissions.read_message_history)+" → "+str(after.permissions.read_message_history))
            if before.permissions.mention_everyone != after.permissions.mention_everyone: embed.add_field(name="@everyone/@here",value=str(before.permissions.mention_everyone)+" → "+str(after.permissions.mention_everyone))
            if before.permissions.external_emojis != after.permissions.external_emojis: embed.add_field(name="Use global/nitro emotes",value=str(before.permissions.external_emojis)+" → "+str(after.permissions.external_emojis))
            if before.permissions.connect != after.permissions.connect: embed.add_field(name="[VC] Connect",value=str(before.permissions.connect)+" → "+str(after.permissions.connect))
            if before.permissions.speak != after.permissions.speak: embed.add_field(name="[VC] Speak",value=str(before.permissions.speak)+" → "+str(after.permissions.speak))
            if before.permissions.mute_members != after.permissions.mute_members: embed.add_field(name="[VC] Mute others",value=str(before.permissions.mute_members)+" → "+str(after.permissions.mute_members))
            if before.permissions.deafen_members != after.permissions.deafen_members: embed.add_field(name="[VC] Deafen others",value=str(before.permissions.deafen_members)+" → "+str(after.permissions.deafen_members))
            if before.permissions.move_members != after.permissions.move_members: embed.add_field(name="[VC] Move others",value=str(before.permissions.move_members)+" → "+str(after.permissions.move_members))
            if before.permissions.use_voice_activation != after.permissions.use_voice_activation: embed.add_field(name="[VC] Push to talk required",value=str(not(before.permissions.use_voice_activation))+" → "+str(not(after.permissions.use_voice_activation)))
            if before.permissions.change_nickname != after.permissions.change_nickname: embed.add_field(name="Change own nickname",value=str(before.permissions.change_nickname)+" → "+str(after.permissions.change_nickname))
            if before.permissions.manage_nicknames != after.permissions.manage_nicknames: embed.add_field(name="Change other nicknames",value=str(before.permissions.manage_nicknames)+" → "+str(after.permissions.manage_nicknames))
            if before.permissions.manage_roles != after.permissions.manage_roles: embed.add_field(name="Manage roles",value=str(before.permissions.manage_roles)+" → "+str(after.permissions.manage_roles))
            if before.permissions.manage_webhooks != after.permissions.manage_webhooks: embed.add_field(name="Manage webhooks",value=str(before.permissions.manage_webhooks)+" → "+str(after.permissions.manage_webhooks))
            if before.permissions.manage_emojis != after.permissions.manage_emojis: embed.add_field(name="Manage emoji", value=str(before.permissions.manage_emojis)+" → "+str(after.permissions.manage_emojis))
            embed.set_footer(text="Role ID: "+str(before.id))
            if len(embed.fields)>0 or before.name != after.name:
                if database.SummarizeEnabled(before.guild, 'role'):
                    summaries.get(str(before.guild.id)).add('role', 13, datetime.datetime.now(), before.id, None, None, embed,content=content)
                else:
                    await database.GetLogChannel(before.guild, "role").send(content=content,embed=embed)
        database.VerifyServer(before.guild, bot)
        for member in after.members:
            database.VerifyUser(member, bot)
    
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        '''[DISCORD API METHOD] Called when emoji list is updated (creation, update, deletion)'''
        if not database.GetEnabled(guild, "emoji"):
            return
        content=None
        embed=None
        if len(before) > len(after):
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0xff0000)
        elif len(after) > len(before):
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0x008000)
        else:
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
        if database.GetReadPerms(guild, "emoji"):
            try:
                async for log in guild.audit_logs(limit=1):
                    if log.action == discord.AuditLogAction.emoji_delete or log.action==discord.AuditLogAction.emoji_create or log.action==discord.AuditLogAction.emoji_update:
                        embed.description = "By: "+log.user.mention+" ("+log.user.name+")"
                        embed.set_thumbnail(url=log.user.avatar_url)
            except discord.Forbidden:
                content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
        if len(before) > len(after): #Emoji was removed
            embed.title="Emoji removed"
            for emoji in before:
                if emoji not in after:
                    embed.add_field(name=emoji.name,value=str(emoji))
                    embed.set_footer(text="Emoji ID: "+str(emoji.id))
                    embed.set_image(url=emoji.url)
        elif len(after) > len(before): #Emoji was added
            embed.title="Emoji created"
            for emoji in after:
                if emoji not in before:
                    embed.add_field(name=emoji.name,value=str(emoji))
                    embed.set_footer(text="Emoji ID: "+str(emoji.id))
                    embed.set_image(url=emoji.url)
        else: #Emoji was updated
            embed.title="Emoji list updated"
            embed.set_footer(text="")
            for a in range(len(before)):
                if before[a].name != after[a].name:
                    embed.add_field(name=before[a].name+" → "+after[a].name,value=str(before[a]))
                    embed.set_footer(text=embed.footer.text+"Emoji ID: "+str(before[a].id))
                    embed.set_image(url=before[a].url)
        if len(embed.fields)>0:
            if database.SummarizeEnabled(guild, 'emoji'):
                summaries.get(str(guild.id)).add('emoji', 14, datetime.datetime.now(), None, None, None, embed,content=content)
            else:
                await database.GetLogChannel(guild, "emoji").send(content=content,embed=embed)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not database.GetEnabled(member.guild, 'voice'):
            return
        embed=discord.Embed(title="Voice Channel update",description=member.mention,timestamp=datetime.datetime.utcnow(),color=0x0000FF)
        if before.afk != after.afk:
            embed.add_field(name="💤",value="Went AFK (was in "+before.channel.name+")")
        else: #that way, we don't get duplicate logs with AFK and changing channels
            if before.deaf != after.deaf:
                if before.deaf: #member is no longer force deafened
                    embed.add_field(name="🔨 🔊",value="Force undeafened")
                else:
                    embed.add_field(name="🔨 🔇",value="Force deafened")
            if before.mute != after.mute:
                if before.mute: #member is no longer force muted
                    embed.add_field(name="🔨 🗣",value="Force unmuted")
                else:
                    embed.add_field(name="🔨 🤐",value="Force muted")
            if not database.GetReadPerms(member.guild, 'voice'): #this is used to determine mod-only actions for variable convenience since audit logs aren't available
                if before.self_deaf != after.self_deaf:
                    if before.self_deaf:
                        embed.add_field(name="🔊",value="Undeafened")
                    else:
                        embed.add_field(name="🔇",value="Deafened")
                if before.self_mute != after.self_mute:
                    if before.self_mute:
                        embed.add_field(name="🗣",value="Unmuted")
                    else:
                        embed.add_field(name="🤐",value="Muted")
                if before.channel != after.channel:
                    b4 = "{Disconnected}" if before.channel is None else before.channel.name
                    af = "{Disconnected}" if after.channel is None else after.channel.name
                    embed.add_field(name="🔀",value="Channel: "+b4+" → "+af)
        if database.SummarizeEnabled(member.guild, 'voice'):
            summaries.get(str(member.guild.id)).add('voice', 15, datetime.datetime.now(), before.id, None, None, embed)
        else:
            await database.GetLogChannel(member.guild, 'voice').send(embed=embed)

    @commands.command()
    async def pause(self, ctx, *args):
        '''Pause logging or antispam for a duration'''
        global loading
        status = await ctx.send(str(loading) + "Please wait...")
        classify = ''
        duration = 0
        args = [a.lower() for a in args]
        if 'logging' in args:
            if 'logging' != args[0]:
                return
            classify = 'Logging'
        if 'antispam' in args:
            if 'antispam' != args[0]:
                return
            classify = 'Antispam'
        if len(args) == 1:
            await status.edit(content=classify+" was paused by "+ctx.author.name)
            if ctx.channel != database.GetLogChannel(ctx.guild, 'message'):
                await database.GetLogChannel(ctx.guild, 'message').send(classify+" was paused by "+ctx.author.name)
            database.PauseMod(ctx.guild, classify.lower())
            return
        duration = ParsePauseDuration((" ").join(args[1:]))
        embed=discord.Embed(title=classify+" was paused",description="by "+ctx.author.mention+" ("+ctx.author.name+")\n\n"+(" ").join(args[1:]),color=0x008000,timestamp=datetime.datetime.utcnow()+datetime.timedelta(seconds=duration))
        embed.set_footer(text="Logging will resume")
        embed.set_thumbnail(url=ctx.author.avatar_url)
        logged = await database.GetLogChannel(ctx.guild, 'message').send(embed=embed)
        try:
            await logged.pin()
        except discord.Forbidden:
            pass
        await status.edit(content="✅",embed=embed)
        database.PauseMod(ctx.guild, classify.lower())
        await asyncio.sleep(duration)
        database.ResumeMod(ctx.guild, classify.lower())
        try:
            await logged.delete()
        except discord.Forbidden:
            pass
        await database.GetLogChannel(ctx.guild, 'message').send(classify+" was unpaused",delete_after=60*60*24)
    @commands.command()
    async def unpause(self, ctx, *args):
        if len(args) < 1: return await ctx.send("Please provide module `antispam` or `logging` to unpause")
        args = [a.lower() for a in args]
        if 'antispam' in args:
            database.ResumeMod(ctx.guild, 'antispam')
            await ctx.send("✅Successfully resumed antispam moderation")
        if 'logging' in args:
            database.ResumeMod(ctx.guild, 'cyberlog')
            await ctx.send("✅Successfully resumed logging")

def ParsePauseDuration(s: str):
    '''Convert a string into a number of seconds to ignore antispam or logging'''
    args = s.split(' ')                             #convert string into a list, separated by space
    duration = 0                                    #in seconds
    for a in args:                                  #loop through words
        number = ""                                 #each int is added to the end of a number string, to be converted later
        for b in a:                                 #loop through each character in a word
            try:
                c = int(b)                          #attempt to convert the current character to an int
                number+=str(c)                      #add current int, in string form, to number
            except ValueError:                      #if we can't convert character to int... parse the current word
                if b.lower() == "m":                #Parsing minutes
                    duration+=60*int(number)
                elif b.lower() == "h":              #Parsing hours
                    duration+=60*60*int(number)
                elif b.lower() == "d":              #Parsing days
                    duration+=24*60*60*int(number)
    return duration

def AvoidDeletionLogging(messages: int, server: discord.Guild):
    '''Don't log the next [messages] deletions if they belong to particular passed server'''
    global pauseDelete
    global serverDelete
    pauseDelete = messages
    serverDelete = server

def ConfigureSummaries(b):
    global summaries
    for server in b.guilds:
        summaries[str(server.id)] = ServerSummary(datetime.datetime.now())
            
def setup(Bot):
    global bot
    global globalLogChannel
    global loading
    global imageLogChannel
    Bot.add_cog(Cyberlog(Bot))
    bot = Bot
    imageLogChannel = bot.get_channel(534439214289256478)
    globalLogChannel = bot.get_channel(566728691292438538)
    loading = bot.get_emoji(573298271775227914)