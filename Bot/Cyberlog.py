import discord
from discord.ext import commands, tasks
import database
import datetime
import asyncio
import os
import collections
import traceback

bot = None
globalLogChannel = discord.TextChannel
imageLogChannel = discord.TextChannel
pauseDelete = 0
serverDelete = None
loading = None
summarizeOn=False

invites = {}
edits = {}
permstrings = {}
summaries = {}
grabbedSummaries = {}
indexed = {}
info = {}

yellow=0xffff00
green=0x008000
red=0xff0000
blue=0x0000FF

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
    def __init__(self, queue=[]):
        self.queue = queue
        self.summarized = []
        self.id = 0
        self.smarts = []
        self.sorted = 0 #0: Category, 1: Timestamp
    
    def add(self, mod, classification, timestamp, data, embed, content=None, reactions=[]): #append summary
        self.queue.append(vars(Summary(mod, classification, timestamp, data, embed, content, reactions)))

    def categorize(self): #sort by category
        self.queue = sorted(self.queue, key = lambda x: x.get('category'))
        self.sorted = 0
    
    def chronologicalize(self): #sort by timestamp
        self.queue = sorted(self.queue, key = lambda x: x.get('timestamp'))
        self.sorted = 1

class Summary(object):
    def __init__(self, mod, classification, timestamp, data, embed, content=None, reactions=None):
        self.mod = mod #Which module is it under
        self.category = classification #Sticky notes
        self.timestamp = timestamp
        self.data = data
        self.embed = embed.to_dict()
        self.content = content
        self.reactions = reactions

class InfoResult(object):
    def __init__(self, main=None, embeds=[], id=0):
        self.main = main
        self.embeds = embeds
        self.id = id
        self.current = None #Currently viewing embed

class Cyberlog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.summarize.start()
        self.DeleteAttachments.start()
    
    def cog_unload(self):
        self.summarize.cancel()
        self.DeleteAttachments.cancel()

    @tasks.loop(minutes=30)
    async def summarize(self):
        if summarizeOn:
            try:
                global summaries
                global loading
                for server in self.bot.guilds:
                    if await database.GeneralSummarizeEnabled(server):
                        s = summaries.get(str(server.id))
                        s.categorize()
                        q = s.queue
                        if len(q) == 0: return
                        keep = [a for a in q if (datetime.datetime.utcnow() - await database.GetLastUpdate(server, a.get('mod'))).seconds / 60 > await database.GetSummarize(server, a.get('mod'))]
                        discard = [a for a in q if a not in keep] #Discards move on to the new ServerSummary event, since these events will be posted later
                        mods = list(collections.Counter([a.get('mod') for a in keep]).keys())
                        e = discord.Embed(title='Server events recap', description='**{} total events**\nFrom {} {} to now\n\n'.format(len(keep), await database.GetOldestUpdate(server, mods).strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(server)),timestamp=datetime.datetime.utcnow(), color=0x0000FF)
                        #keycodes = {0: 'Message edits', 1: 'Message deletions', 2: 'Channel creations', 3: 'Channel edits', 4: 'Channel deletions', 5: 'New members',
                        #6: 'Members that left', 7: 'Member unbanned', 8: 'Member updates', 9: 'Username/pfp updates', 10: 'Server updates', 11: 'Role creations', 
                        #12: 'Role edits', 13: 'Role deletions', 14: 'Emoji updates', 15: 'Voice Channel updates'}
                        keyCounts = {} #Keycodes holds descriptions of events, keycounts hold respective count of events
                        for a in range(16):
                            keyCounts[a] = 0
                        for summary in keep:
                            if await database.SummarizeEnabled(server, summary.get('mod')): #Keeping this down here instead of in keep algorithm prevents stray events
                                keyCounts[summary.get('category')] = keyCounts.get(summary.get('category')) + 1
                        #for a, b in keyCounts.items():
                        #    if b > 0: e.description += '{}: {} events\n'.format(keycodes.get(a), b)
                        for a in discord.Embed.from_dict(Summarize(keep, keyCounts)[0]).fields: e.add_field(name=a.name,value=a.value)
                        e.description+='\n\nPress 🗓 to sort events by timestamp\nPress 📓 to view summary or details'
                        if len(keep) > 0:
                            m = await (await database.GetMainLogChannel(server)).send(embed=e) #Process smart embeds in the future
                            e.set_footer(text='Event ID: {}'.format(m.id))
                            s.id = m.id
                            await database.AppendSummary(server, s)
                            await m.edit(embed=e)
                            for a in ['🗓', '📓']:
                                await m.add_reaction(a)
                            summaries[str(server.id)] = ServerSummary(queue=discard)
            except Exception as e: traceback.print_exc() #print('Error: {}\n{}'.format(e, vars(s)))
        global bot
        for server in bot.guilds:
            try:
                invites[str(server.id)] = await server.invites()
                try: invites[str(server.id)+"_vanity"] = (await server.vanity_invite()).uses
                except: pass
            except Exception as e:
                print('Invite management error: Server {}\n{}'.format(server.name, e))

    @tasks.loop(hours=24)
    async def DeleteAttachments(self):
        try:
            removal=[]
            for server in bot.guilds:
                for channel in server.text_channels:
                    try:
                        path='Attachments/{}/{}'.format(server.id, channel.id)
                        for fl in os.listdir(path):
                            with open('Indexes/{}/{}/{}.txt'.format(server.id, channel.id, fl)) as f:
                                for line, content in enumerate(f):
                                    if line==0: timestamp=datetime.datetime.strptime(content, '%b %d, %Y - %I:%M %p')
                            if (datetime.datetime.utcnow() - timestamp).days > 30:
                                removal.append(path+fl)
                    except: pass
            for path in removal: os.removedirs(path)
        except Exception as e: print('Fail: {}'.format(e))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        '''[DISCORD API METHOD] Called when message is sent
        Unlike RicoBot, I don't need to spend over 1000 lines of code doing things here in [ON MESSAGE] due to the web dashboard :D'''
        await asyncio.sleep(2)
        path = "Indexes/{}/{}".format(message.guild.id, message.channel.id)
        try: f = open('{}/{}_{}.txt'.format(path, message.id, message.author.id), "w+")
        except FileNotFoundError: return
        try: f.write('{}\n{}\n{}'.format(message.created_at.strftime('%b %d, %Y - %I:%M %p'), message.author.name, message.content))
        except UnicodeEncodeError: pass
        try: f.close()
        except: pass
        if message.author.bot:
            return
        if await database.GetImageLogPerms(message.guild) and len(message.attachments) > 0:
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
        oldReac = message.reactions
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
            if 'Channel' in e.title:
                try: await message.clear_reactions()
                except discord.Forbidden: pass
                channel = bot.get_channel(int(fid))
                if channel is None: return await message.edit(content='Unable to provide channel information; it was probably deleted')
                result = await ChannelInfo(channel, None if type(channel) is discord.CategoryChannel else await channel.invites(), None if type(channel) is not discord.TextChannel else await channel.pins(), await message.guild.audit_logs(limit=None).flatten())
                await message.edit(content=result[0],embed=result[1])
            if 'Server updated' in e.title:
                try: await message.clear_reactions()
                except discord.Forbidden: pass
                await message.edit(content='Embed will retract in 3 minutes',embed=await ServerInfo(message.guild, await message.guild.audit_logs(limit=None).flatten(), await message.guild.bans(), await message.guild.webhooks(), await message.guild.invites()))
            if 'Role was updated' in e.title:
                try: await message.clear_reactions()
                except discord.Forbidden: pass
                role = message.guild.get_role(int(fid))
                if role is None: return await message.edit(content='Unable to provide role information; it was probably deleted')
                await message.edit(content='Embed will retract in 3 minutes',embed=await RoleInfo(role, await role.guild.audit_logs(limit=None).flatten()))
            await asyncio.sleep(180)
            if message.embeds[0] != e:
                if 'React with' in e.title or 'event recaps' in e.title or 'Message was edited' in e.title or 'Channel was updated' in e.title:
                    await message.edit(content=None,embed=e)
                    await message.clear_reactions()
                    for r in oldReac: await message.add_reaction(r)
        if str(ej) == '🇵':
            if 'Channel was updated' in e.title:
                try: await message.remove_reaction(ej, user)
                except discord.Forbidden: pass
                if len(message.content) < 2: content=permstrings.get(int(e.author.name[e.author.name.find(':')+2:]))
                else: content = None
                await message.edit(content=content)
        if str(ej) == '📜':
            if 'edit details' in e.title:
                try: await message.remove_reaction(ej, user)
                except discord.Forbidden: pass
                eo = edits.get(fid)
                after = eo.message
                details = discord.Embed(title='Message edit details',description='Author: {}\n__Viewing message edit history__'.format(after.author.name),timestamp=datetime.datetime.utcnow(),color=0x0000FF)
                details.add_field(name='{} {}'.format((eo.created + datetime.timedelta(hours=await database.GetTimezone(message.guild))).strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(message.guild)), value=eo.history[0].before, inline=False)
                for entry in eo.history:
                    details.add_field(name='{} {}'.format((entry.time + datetime.timedelta(hours=await database.GetTimezone(message.guild))).strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(message.guild)), value=entry.after,inline=False)
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
                joined=member.joined_at + datetime.timedelta(hours=await database.GetTimezone(message.guild))
                created=member.created_at + datetime.timedelta(hours=await database.GetTimezone(message.guild))
                details.add_field(name='Joined',value='{} {} ({} days ago)'.format(joined.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(message.guild), (datetime.datetime.utcnow()-joined).days))
                details.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(message.guild), (datetime.datetime.utcnow()-created).days))
                details.add_field(name='Currently',value='{}{}'.format('📱' if member.is_on_mobile() else '', member.status))
                details.add_field(name='Top role',value=member.top_role)
                details.add_field(name='Role count',value=len(member.roles))
                details.description+='\n\n**Permissions:** {}'.format(', '.join(await database.StringifyPermissions(member.guild_permissions)))
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
                canManage = await database.ManageRoles(user)
                def checkMute(m): return 'yes' in m.content.lower() and message.channel == m.channel and m.author.id == user.id and canManage
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
                canKick = await database.KickMembers(user)
                def checkKick(m): return 'none' != m.content.lower() and message.channel == m.channel and m.author.id == user.id and canKick
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
                canBan = await database.BanMembers(user)
                def checkBan(m): return 'none' != m.content.lower() and message.channel == m.channel and m.author.id == user.id and canBan
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
                grabbedSummaries[str(message.id)] = await database.GetSummary(message.guild, message.id)
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
                    e.description='**{} total events**\nFrom {} {} to now\n\n'.format(len(summ.get('queue')), summ.get('lastUpdate').strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(message.guild))
                    keycodes = {0: 'Message edits', 1: 'Message deletions', 2: 'Channel creations', 3: 'Channel edits', 4: 'Channel deletions', 5: 'New members',
                    6: 'Members that left', 7: 'Member unbanned', 8: 'Member updates', 9: 'Username/pfp updates', 10: 'Server updates', 11: 'Role creations', 
                    12: 'Role edits', 13: 'Role deletions', 14: 'Emoji updates', 15: 'Voice Channel updates'}
                    keyCounts = {} #Keycodes holds descriptions of events, keycounts hold respective count of events
                    for a in range(16):
                        keyCounts[a] = 0
                    for summary in summ.get('queue'):    
                        if await database.SummarizeEnabled(message.guild, summary.get('mod')) and (datetime.datetime.now() - summ.get('lastUpdate')).seconds * 60 > await database.GetSummarize(message.guild, summary.get('mod')):
                            keyCounts[summary.get('category')] = keyCounts.get(summary.get('category')) + 1
                    for a, b in keyCounts.items():
                        if b > 0: e.description += '{}: {} events\n'.format(keycodes.get(a), b)
                    e.description+='\n\nPress 📓 to view summary or details\nPress 🗓 to sort events by timestamp'
                    await message.clear_reactions()
                    await message.edit(content=None,embed=e)
                    for a in ['🗓', '📓']: await message.add_reaction(a)
            if str(ej) == '⬅' and message.id in list(info.keys()):
                if not user.id == int(info.get(message.id).main.author.name[info.get(message.id).main.author.name.find(':')+2:]):
                    return
                try: await message.clear_reactions()
                except: pass
                await message.edit(embed=info.get(message.id).main)
                def check(m):
                    try: return m.author==user and int(m.content) <= len(info.get(message.id).embeds)
                    except: return False
                try: message2 = await bot.wait_for('message',check=check,timeout=120)
                except: return
                await message.edit(content=loading)
                AvoidDeletionLogging(1, message.guild)
                try: await message2.delete()
                except: AvoidDeletionLogging(0, None)
                await message.edit(content=None,embed=info.get(message.id).embeds[int(message2.content)-1])
                await message.add_reaction('⬅')
        if str(ej) == '📓':
            await message.clear_reactions()
            try: 
                queue = grabbedSummaries.get(str(message.id)).get('queue')
                sort = grabbedSummaries.get(str(message.id)).get('sorted')
            except AttributeError: 
                queue = await database.GetSummary(message.guild, message.id).get('queue')
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
                queue = await database.GetSummary(message.guild, message.id).get('queue')
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
        if not await database.SimpleGetEnabled(g, 'message'):
            return
        if not await database.CheckCyberlogExclusions(after.channel, after.author) or after.author.bot:
            return
        load=discord.Embed(title="Message was edited (React with ℹ to see details)",description=str(loading),color=0x0000FF)
        embed = load.copy()
        c = await database.GetLogChannel(g, 'message')
        if c is None: return
        #msg = await c.send(embed=embed)
        before = ""
        path = 'Indexes/{}/{}'.format(payload.data.get('guild_id'), payload.data.get('channel_id'))
        for fl in os.listdir(path):
            if fl == '{}_{}.txt'.format(payload.message_id, after.author.id):
                f = open(path+'/'+fl, 'r+')
                for line, l in enumerate(f): #Line is line number, l is line content
                    if line == 2:
                        before = l
                        try: f.write('{}\n{}\n{}'.format(after.created_at.strftime('%b %d, %Y - %I:%M %p'), after.author.name, after.content))
                        except UnicodeEncodeError: pass
                        break
                f.close()
        if before == after.content:
            return #await msg.delete()
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
        embed.add_field(name="Previously: ", value='[{}]({} \'Jump to message ;)\')'.format(beforeC if len(beforeC) > 0 else '(No new content)', after.jump_url),inline=False)
        embed.add_field(name="Now: ", value='[{}]({} \'Jump to message ;)\')'.format(afterC if len(afterC) > 0 else '(No new content)', after.jump_url),inline=False)
        embed.add_field(name="Channel: ", value=str(after.channel.mention))
        embed.set_footer(text="Message ID: " + str(after.id))
        embed.set_thumbnail(url=after.author.avatar_url)
        data = {'author': after.author.id, 'name': after.author.name, 'server': after.guild.id, 'message': after.id}
        if await database.SummarizeEnabled(g, 'message'):
            global summaries
            summaries.get(str(g.id)).add('message', 0, datetime.datetime.now(), data, embed, reactions=['ℹ'])
            #await msg.delete()
        else:
            try: 
                msg = await c.send(embed=embed)
                await msg.add_reaction('ℹ')
            except discord.HTTPException:
                await c.send(embed=discord.Embed(title="Message was edited",description='Message content is too long to post here',color=0x0000FF,timestamp=datetime.datetime.utcnow()))

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
        c = await database.GetLogChannel(g, 'message')
        try: 
            message = payload.cached_message
            data = {'author': message.author.id, 'name': message.author.name, 'server': g.id}
        except AttributeError:
            message = None
        if message is not None and pauseDelete > 0 and message.guild == serverDelete:
            pauseDelete -= 1
            return
        elif pauseDelete == 0:
            serverDelete = None
        if not await database.GetEnabled(g, 'message'):
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
        #s = None
        if message is not None:
            if not await database.CheckCyberlogExclusions(message.channel, message.author) or message.author.bot:
                return
            embed.description="Author: "+message.author.mention+" ("+message.author.name+")\nChannel: "+message.channel.mention+"\nSent: {} {}".format((message.created_at + datetime.timedelta(hours=await database.GetTimezone(message.guild))).strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(message.guild))
            embed.set_thumbnail(url=message.author.avatar_url)
            if len(embed.image.url) < 1:
                for ext in ['.png', '.jpg', '.gif', '.webp']:
                    if ext in message.content:
                        if '://' in message.content:
                            url = message.content[message.content.find('http'):message.content.find(ext)+len(ext)+1]
                            embed.set_image(url=url)
            embed.add_field(name="Content",value="(No content)" if message.content is None or len(message.content)<1 else message.content)
        else:
            embed.description="Message is old...\n\n"+str(loading)+" Attempting to retrieve some data..." #Now we have to search the file system
            #s = await c.send(embed=embed)
            f=None
            directory = "Indexes/{}/{}".format(payload.guild_id,payload.channel_id)
            for fl in os.listdir(directory):
                if str(payload.message_id) in fl:
                    f = open(directory+"/"+fl, "r")
                    authorID = int(fl[fl.find('_')+1:fl.find('.')])
                    for line, l in enumerate(f): #like before, line is line number, l is line content
                        if line == 0:
                            created = datetime.datetime.strptime(l.strip(), '%b %d, %Y - %I:%M %p') + datetime.timedelta(hours=await database.GetTimezone(bot.get_guild(payload.guild_id)))
                        elif line == 1:
                            authorName = l
                        elif line == 2:
                            messageContent = l
                    f.close()
                    os.remove(directory+"/"+fl)
                    author = bot.get_guild(payload.guild_id).get_member(authorID)
                    data = {'author': authorID, 'name': authorName, 'server': payload.guild_id, message: payload.message_id}
                    if author is None or author.bot or author not in g.members or not await database.CheckCyberlogExclusions(bot.get_channel(payload.channel_id), author):
                        return
                    embed.description=""
                    if author is not None: 
                        embed.description+="Author: "+author.mention+" ("+author.name+")\n"
                        embed.set_thumbnail(url=author.avatar_url)
                    else:
                        embed.description+="Author: "+authorName+"\n"
                        ma = author
                    embed.description+="Channel: "+bot.get_channel(payload.channel_id).mention+"\n"
                    embed.description+='Sent: {} {}\n'.format(created.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(bot.get_guild(payload.guild_id)))
                    embed.add_field(name="Content",value="(No content)" if messageContent is "" or len(messageContent)<1 else messageContent)
                    for ext in ['.png', '.jpg', '.gif', '.webp']:
                        if ext in messageContent:
                            if '://' in messageContent:
                                url = messageContent[message.content.find('http'):messageContent.find(ext)+len(ext)+1]
                                embed.set_image(url=url)
                    break #the for loop
            if f is None:
                return await c.send(embed=discord.Embed(title="Message was deleted",description='Unable to provide more information',timestamp=datetime.datetime.utcnow(),color=0xff0000))
        content=None
        if await database.GetReadPerms(g, "message"):
            try:
                async for log in g.audit_logs(limit=1):
                    if log.action == discord.AuditLogAction.message_delete and log.target == ma and (datetime.datetime.utcnow() - log.created_at).seconds < 10:
                        embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
            except discord.Forbidden:
                content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
        global summaries
        #if s is not None:
        #    if database.SummarizeEnabled(g, 'message'):  
        #        summaries.get(str(g.id)).add('message', 1, datetime.datetime.now(), data, embed,content=content)
        #        await s.delete()
        #    else:
        #        await s.edit(content=content,embed=embed,files=attachments)
        #else:
        if await database.SummarizeEnabled(g, 'message'):
            summaries.get(str(g.id)).add('message', 1, datetime.datetime.now(), data, embed,content=content)
        else:
            try: await c.send(content=content,embed=embed,files=attachments)
            except: await c.send(content='An attachment to this message is too big to send',embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is created'''
        global bot
        content=None
        if await database.GetEnabled(channel.guild, "channel"):
            data = {'channel': channel.id, 'name': channel.name, 'server': channel.guild.id}
            if type(channel) is discord.TextChannel:
                chan = "📜 Text"
                data['type'] = '📜'
            elif type(channel) is discord.VoiceChannel:
                chan = "🎙 Voice"
                data['type'] = '🎙'
            else:
                chan = "📂 Category"
                data['type'] = '📂'
            embed=discord.Embed(title=chan + " Channel was created", description=channel.mention+" ("+channel.name+")" if type(channel) is discord.TextChannel else channel.name,color=0x008000,timestamp=datetime.datetime.utcnow())
            if type(channel) is not discord.CategoryChannel:
                embed.add_field(name="Category",value=str(channel.category.name))
            if await database.GetReadPerms(channel.guild, "channel"):
                try:
                    async for log in channel.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_create:
                            embed.description+="\nCreated by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.set_footer(text="Channel ID: "+str(channel.id))
            if await database.SummarizeEnabled(channel.guild, 'channel'):
                summaries.get(str(channel.guild.id)).add('channel', 2, datetime.datetime.now(), data, embed,content=content)
            else:
                await (await database.GetLogChannel(channel.guild, "channel")).send(content=content,embed=embed)
        if type(channel) is discord.TextChannel:
            path = "Indexes/{}/{}".format(channel.guild.id, channel.id)
            try: os.makedirs(path)
            except FileExistsError: pass
            await database.VerifyServer(channel.guild, bot)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is updated'''
        global bot
        if await database.GetEnabled(before.guild, "channel"):
            content=None
            data = {'channel': before.id, 'server': before.guild.id, 'oldName': before.name, 'newName': after.name}
            if type(before) is discord.TextChannel:
                chan = "📜 Text"
                data['type'] = '📜'
            elif type(before) is discord.VoiceChannel:
                chan = "🎙 Voice"
                data['type'] = '🎙'
            else:
                chan = "📂 Category"
                data['type'] = '📂'
            embed=discord.Embed(title=chan + " Channel was updated", description=before.mention if type(before) is discord.TextChannel else before.name,color=0x0000FF,timestamp=datetime.datetime.utcnow())
            embed.description+=' (Press ℹ to view channel details)'
            reactions = ['ℹ']
            if await database.GetReadPerms(before.guild, "channel"):
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_update:
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>\n"
            embed.set_footer(text="Channel ID: "+str(before.id))
            if abs(before.position - after.position) > 1 and before.category == after.category:
                array = []
                cats = [c for c in before.guild.channels if type(c) is discord.CategoryChannel]
                rough = []
                ignore = []
                for cat in cats:
                    for c in range(len(cat.channels)):
                        channel = cat.channels[c]
                        if type(channel) is discord.VoiceChannel:
                            if channel.category != after.category:
                                ignore.append(channel)
                            else:
                                if c == 0: cat.channels[c].position = cat.channels[c+1].position - 1
                                else: cat.channels[c].position = cat.channels[c-1].position + 1
                    rough.extend([chan for chan in cat.channels if chan not in ignore])
                sort = sorted([c for c in rough], key = lambda x: x.position)
                channels = [channel for channel in sort if channel.category == after.category]
                #for voice... manually set .position to +1 or -1 of the textchannel before/after it
                for c in range(channels[0].position, channels[-1].position+1): array.append('{}{}'.format('~~{}{}~~{}\n'.format(data.get('type'), before.name, '❌') if c==before.position else '', '{}{}'.format('📜' if type(sort[c]) is discord.TextChannel else '🎙', '**{}**{}'.format(sort[c].name, '↩') if sort[c].id == before.id else sort[c].name)))
                embed.description+='\n\n**Channel position updated**\n{}'.format('\n'.join(array))
            if before.overwrites != after.overwrites:
                b4 = {} #Before perms
                af = {} #After perms
                temp=[]
                english = {True: '✔', None: '➖', False: '✖'} #Symbols becuase True, False, None is confusing
                for k,v in before.overwrites.items(): b4.update({k: dict(iter(v))})
                for k,v in after.overwrites.items(): af.update({k: dict(iter(v))})
                for k,v in af.items():
                    if before.overwrites_for(k) != after.overwrites_for(k): temp.append('{:-<60s}'.format(k.name))
                    for kk,vv in v.items():
                        if b4.get(k) is None: #for example, a new overwrite for role/member was created
                            for kkk in list(v.keys()):
                                b4[k] = {kkk: None}
                        if not set({kk: vv}.items()).issubset(b4.get(k).items()):
                            string2 = '{0:^3}'.format(english.get(vv)) #Set these to 15 if all else fails and increase now/prev spacing
                            temp.append('     {0:<25} |{1:>8}{2:>{diff}}{3:>10}'.format('{}:'.format(kk), string2, '|', english.get(b4.get(k).get(kk)), diff=4 if '➖' in string2 else 5))
                permstrings[len(permstrings)] = '```Permission overwrites updated  |  {0:^10}|{1:^20}\n{2}```'.format('Now', 'Previously', '\n'.join(temp))
                embed.add_field(name='Permission overwrites updated',value='Press 🇵 to show/hide')
                reactions.append('🇵')
                embed.set_author(name='Perm ID: {}'.format(len(permstrings) - 1))
            if before.name != after.name: 
                embed.add_field(name="Prev name",value=before.name)
                embed.add_field(name="New name",value=after.name)
            if type(before) is discord.TextChannel:
                if before.topic != after.topic:
                    beforeTopic = before.topic if before.topic is not None and len(before.topic) > 0 else "<No topic>"
                    afterTopic = after.topic if after.topic is not None and len(after.topic) > 0 else "<No topic>"
                    embed.add_field(name="Prev topic",value=beforeTopic)
                    embed.add_field(name="New topic",value=afterTopic)
                    data['oldTopic'] = beforeTopic
                    data['newTopic'] = afterTopic
                if before.is_nsfw() != after.is_nsfw():
                    embed.add_field(name="Prev NSFW",value=before.is_nsfw())
                    embed.add_field(name="New NSFW",value=after.is_nsfw())
                    data['oldNsfw'] = before.is_nsfw()
                    data['newNsfw'] = after.is_nsfw()
                if before.slowmode_delay != after.slowmode_delay:
                    embed.add_field(name='Prev slowmode',value='{}'.format(before.slowmode_delay if before.slowmode_delay > 0 else 'Disabled'))
                    embed.add_field(name='New slowmode',value='{}'.format(after.slowmode_delay if after.slowmode_delay > 0 else 'Disabled'))
                    data['oldSlowmode'] = before.slowmode_delay
                    data['newSlowmode'] = after.slowmode_delay
            elif type(before) is discord.VoiceChannel:
                if before.bitrate != after.bitrate:
                    embed.add_field(name="Prev Bitrate",value=before.bitrate)
                    embed.add_field(name="New Bitrate",value=after.bitrate)
                    data['oldBitrate'] = before.bitrate
                    data['newBitrate'] = after.bitrate
                if before.user_limit != after.user_limit:
                    embed.add_field(name="Prev User limit",value=before.user_limit)
                    embed.add_field(name="New User limit",value=after.user_limit)
                    data['oldLimit'] = before.user_limit
                    data['newLimit'] = after.user_limit
            if type(before) is not discord.CategoryChannel and before.category != after.category:
                beforeCat = str(before.category) if before.category is not None else "<No category>"
                afterCat = str(after.category) if after.category is not None else "<No category>"
                embed.add_field(name="Prev category",value=beforeCat)
                embed.add_field(name="New category",value=afterCat)
                data['oldCategory'] = beforeCat
                data['newCategory'] = afterCat
            if len(embed.fields) > 0 or 'position' in embed.description or 'overwrites' in embed.description:
                if await database.SummarizeEnabled(before.guild, 'channel'):
                    summaries.get(str(before.guild.id)).add('channel', 3, datetime.datetime.now(), data, embed,content=content, reactions=reactions)
                else:
                    message = await (await database.GetLogChannel(before.guild, "channel")).send(content=content,embed=embed)
                    for reaction in reactions: await message.add_reaction(reaction)
        if type(before) is discord.TextChannel and before.name != after.name: await database.VerifyServer(after.guild, bot)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when channel is deleted'''
        global bot
        if await database.GetEnabled(channel.guild, "channel"):
            content=None
            data = {'channel': channel.name, 'id': channel.id, 'server': channel.guild.id}
            if type(channel) is discord.TextChannel:
                chan = "📜 Text"
                data['type'] = '📜'
            elif type(channel) is discord.VoiceChannel:
                chan = "🎙 Voice"
                data['type'] = '🎙'
            else:
                chan = "📂 Category"
                data['type'] = '📂'
            embed=discord.Embed(title=chan + " Channel was deleted", description=channel.name,color=0xff0000,timestamp=datetime.datetime.utcnow())
            if type(channel) is not discord.CategoryChannel:
                embed.add_field(name="Category",value=str(channel.category.name))
            if await database.GetReadPerms(channel.guild, "channel"):
                try:
                    async for log in channel.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_delete:
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.set_footer(text="Channel ID: "+str(channel.id))
            if await database.SummarizeEnabled(channel.guild, 'channel'):
                summaries.get(str(channel.guild.id)).add('channel', 4, datetime.datetime.now(), data, embed,content=content)
            else:
                await (await database.GetLogChannel(channel.guild, "channel")).send(content=content,embed=embed)
        if type(channel) is discord.TextChannel: await database.VerifyServer(channel.guild, bot)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member joins a server'''
        global bot
        global invites
        if await database.GetEnabled(member.guild, "doorguard"):
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
            data = {'name': member.name, 'id': member.id, 'server': member.guild.id}
            embed.set_footer(text='Member ID: {}'.format(member.id))
            try:
                newInv = await member.guild.invites()
            except discord.Forbidden:
                content="Tip: I can determine who invited new members if I have the <Manage Server> permissions"
                if await database.SummarizeEnabled(member.guild, 'doorguard'):
                    return summaries.get(str(member.guild.id)).add('doorguard', 5, datetime.datetime.now(), member.id, data, embed,content=content,reactions=['ℹ'])
                else:
                    return await (await database.GetLogChannel(member.guild, 'doorguard')).send(content=content,embed=embed)
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
            if await database.SummarizeEnabled(member.guild, 'doorguard'):
                summaries.get(str(member.guild.id)).add('doorguard', 5, datetime.datetime.now(), data, embed,content=content,reactions=['ℹ'])
            else:
                msg = await (await database.GetLogChannel(member.guild, "doorguard")).send(content=content,embed=embed)
                await msg.add_reaction('ℹ')
        await database.VerifyServer(member.guild, bot)
        await database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member leaves a server'''
        global bot
        if await database.GetEnabled(member.guild, "doorguard"):
            await asyncio.sleep(1)
            content=None
            embed=None
            if embed is None: 
                embed=discord.Embed(title="Member left",description=member.mention+" ("+member.name+")",timestamp=datetime.datetime.utcnow(),color=0xff0000)
                data = {'id': member.id, 'name': member.name, 'type': 'Leave', 'server': member.guild.id}
                if await database.GetReadPerms(member.guild, 'doorguard'):
                    try:
                        async for log in member.guild.audit_logs(limit=1):
                            if log.target == member:
                                if log.action == discord.AuditLogAction.kick:
                                    embed.title = member.name+" was kicked"
                                    embed.description="Kicked by: "+log.user.mention+" ("+log.user.name+")"
                                    data['type'] = 'Kick'
                                    embed.add_field(name="Reason",value=log.reason if log.reason is not None else "None provided",inline=True if log.reason is not None and len(log.reason) < 25 else False)
                                elif log.action == discord.AuditLogAction.ban:
                                    embed.title = member.name+" was banned"
                                    embed.description="Banned by: "+log.user.mention+" ("+log.user.name+")"
                                    data['type'] = 'Ban'
                                    embed.add_field(name="Reason",value=log.reason if log.reason is not None else "None provided",inline=True if log.reason is not None and len(log.reason) < 25 else False)
                    except discord.Forbidden:
                        content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            span = datetime.datetime.utcnow() - member.joined_at
            hours = span.seconds//3600
            minutes = (span.seconds//60)%60
            embed.add_field(name="Here for",value=str(span.days)+" days, "+str(hours)+" hours, "+str(minutes)+" minutes, "+str(span.seconds - hours*3600 - minutes*60)+" seconds")
            embed.set_thumbnail(url=member.avatar_url)
            embed.set_footer(text="User ID: "+str(member.id))
            if await database.SummarizeEnabled(member.guild, 'doorguard'):
                summaries.get(str(member.guild.id)).add('doorguard', 6, datetime.datetime.now(), data, embed,content=content)
            else:
                await (await database.GetLogChannel(member.guild, "doorguard")).send(content=content,embed=embed)
        await database.VerifyServer(member.guild, bot)
        await database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if await database.GetEnabled(guild, 'doorguard'):
            embed=discord.Embed(title=user.name+" was unbanned",description="",timestamp=datetime.datetime.utcnow(),color=0x008000)
            content=None
            data = {'member': user.id, 'name': user.name, 'server': guild.id}
            if await database.GetReadPerms(guild, 'doorguard'):
                try:
                    async for log in guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.unban:
                            embed.description = "by "+log.user.mention+" ("+log.user.name+")"
                    async for log in guild.audit_logs(limit=None):
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
            if await database.SummarizeEnabled(guild, 'doorguard'):
                summaries.get(str(guild.id)).add('doorguard', 7, datetime.datetime.now(), data, embed,content=content)
            else:
                await (await database.GetLogChannel(guild, 'doorguard')).send(content=content,embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        '''[DISCORD API METHOD] Called when member changes status/game, roles, or nickname; only the two latter events used with this bot'''
        if (before.nick != after.nick or before.roles != after.roles) and await database.GetEnabled(before.guild, "member"):
            content=None
            data = {'member': before.id, 'name': before.name, 'server': before.guild.id}
            embed=discord.Embed(title="Member's server attributes updated",description=before.mention+"("+before.name+")",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
            if before.roles != after.roles:
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.member_role_update: 
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
                added = []
                removed = []
                for f in after.roles:
                    if f not in before.roles:
                        if f.name != "RicobotAutoMute" and f != before.guild.get_role(await database.GetAntiSpamObject(before.guild).get("customRoleID")):
                            added.append(f.name)
                for f in before.roles:
                    if f not in after.roles:
                        if f.name != "RicobotAutoMute" and f != before.guild.get_role(await database.GetAntiSpamObject(before.guild).get("customRoleID")) and f in before.guild.roles:
                            removed.append(f.name)
                if len(added) > 0: 
                    embed.add_field(name='Role(s) added',value=', '.join(added))
                    data['newRoles'] = len(added)
                if len(removed) > 0: 
                    embed.add_field(name='Role(s) removed',value=', '.join(removed))
                    data['oldRoles'] = len(removed)
                beforePerms = [p[0] for p in iter(before.guild_permissions) if p[1]]
                afterPerms = [p[0] for p in iter(after.guild_permissions) if p[1]]
                if beforePerms != afterPerms:
                    lost = [p for p in beforePerms if p not in afterPerms]
                    gained = [p for p in afterPerms if p not in beforePerms]
                    if len(lost) > 0: embed.description+='\n\n**Lost permissions: **{}'.format(', '.join(lost))
                    if len(gained) > 0: embed.description+='\n\n**Gained permissions: **{}'.format(', '.join(gained))
            if before.nick != after.nick:
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.member_update and log.target == before: 
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
                oldNick = before.nick if before.nick is not None else "<No nickname>"
                newNick = after.nick if after.nick is not None else "<No nickname>"
                embed.add_field(name="Prev nickname",value=oldNick)
                embed.add_field(name="New nickname",value=newNick)
                data['oldNick'] = oldNick, data['newNick'] = newNick
            embed.set_thumbnail(url=before.avatar_url)
            embed.set_footer(text="Member ID: "+str(before.id))
            if len(embed.fields) > 0:
                if await database.SummarizeEnabled(before.guild, 'member'):
                    summaries.get(str(before.guild.id)).add('member', 8, datetime.datetime.now(), data, embed,content=content)
                else:
                    await (await database.GetLogChannel(before.guild, "member")).send(content=content,embed=embed)
        global bot
        await database.VerifyUser(before, bot)

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
        data = {'member': before.id, 'oldName': before.name, 'newName': after.name}
        if before.avatar_url != after.avatar_url:
            data['pfp'] = True
            if before.avatar_url is not None:
                embed.set_thumbnail(url=before.avatar_url)
            if after.avatar_url is not None:
                embed.set_image(url=after.avatar_url)
            embed.add_field(name="Profile Picture updated",value="Old: Thumbnail to the right\nNew: Image below")
        else:
            embed.set_thumbnail(url=before.avatar_url)
        if before.discriminator != after.discriminator:
            data['discrim'] = True
            embed.add_field(name="Prev discriminator",value=before.discriminator)
            embed.add_field(name="New discriminator",value=after.discriminator)
        if before.name != after.name:
            embed.add_field(name="Prev username",value=before.name)
            embed.add_field(name="New username",value=after.name)
        embed.set_footer(text="User ID: "+str(after.id))
        for server in servers:
            data['server'] = server.id
            await database.VerifyServer(server, bot)
            if await database.GetEnabled(server, "member"):
                if await database.SummarizeEnabled(server, 'member'):
                    summaries.get(str(server.id)).add('member', 9, datetime.datetime.now(), data, embed)
                else:
                    await (await database.GetLogChannel(server, "member")).send(embed=embed)
        await database.VerifyUser(membObj, bot)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot joins a server'''
        global bot
        global globalLogChannel
        await globalLogChannel.send(embed=discord.Embed(title="Joined server",description=guild.name,timestamp=datetime.datetime.utcnow(),color=0x008000))
        await database.VerifyServer(guild, bot)
        for member in guild.members:
            await database.VerifyUser(member, bot)
        post=None
        global loading
        content="Thank you for inviting me to your server!\nTo configure me, you can connect your Discord account and enter your server's settings here: <https://disguard.herokuapp.com>\n{}Please wait while I index your server's messages...".format(loading)
        if guild.system_channel is not None:
            try: post = await guild.system_channel.send(content) #Update later to provide more helpful information
            except discord.Forbidden: pass
        if post is None:
            for channel in guild.text_channels:
                if 'general' in channel.name:
                    try: post = await channel.send(content) #Update later to provide more helpful information
                    except discord.Forbidden: pass
        for channel in guild.text_channels:
            path = "Indexes/{}/{}".format(guild.id, channel.id)
            try: os.makedirs(path)
            except FileExistsError: pass
            try: 
                async for message in channel.history(limit=None):
                    if '{}_{}.txt'.format(message.id, message.author.id) in os.listdir(path): break
                    try: f = open('{}/{}_{}.txt'.format(path, message.id, message.author.id), "w+")
                    except FileNotFoundError: pass
                    try: f.write('{}\n{}\n{}'.format(message.created_at.strftime('%b %d, %Y - %I:%M %p'), message.author.name, message.content))
                    except UnicodeEncodeError: pass
                    try: f.close()
                    except: pass
            except discord.Forbidden: pass
        indexed[guild.id] = True
        try: await message.edit(content="Thank you for inviting me to your server!\nTo configure me, you can connect your Discord account and enter your server's settings here: <https://disguard.herokuapp.com>")
        except: pass

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        global bot
        if await database.GetEnabled(before, 'server'):
            embed=discord.Embed(title="Server updated (React with ℹ to view server details)",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
            content=None
            data = {'server': before.id}
            if await database.GetReadPerms(before, 'server'):
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
                data['oldAfkChan'] = 0 if before.afk_channel is None else before.afk_channel.id
                data['newAfkChan'] = 0 if after.afk_channel is None else after.afk_channel.id
                embed.add_field(name="AFK Channel",value=b4+" → "+af)
            if before.afk_timeout != after.afk_timeout:
                data['oldAfkTime'] = before.afk_timeout, data['newAfkTime'] = after.afk_channel.id
                embed.add_field(name="AFK Timeout",value=str(before.afk_timeout)+"s → "+str(after.afk_timeout)+"s")
            if before.mfa_level != after.mfa_level:
                b4 = True if before.mfa_level == 1 else False
                af = True if after.mfa_level == 1 else False
                data['oldMfa'] = before.mfa_level, data['newMfa'] = after.mfa_level
                embed.add_field(name="Mods need 2FA",value=b4+" → "+af)
            if before.name != after.name:
                data['oldName'] = before.name, data['newName'] = after.name
                embed.add_field(name="Name",value=before.name+" → "+after.name)
            if before.owner != after.owner:
                data['oldOwner'] = before.owner.id, data['newOwner'] = after.owner.id
                embed.add_field(name="Owner",value=before.owner.mention+" → "+after.owner.mention)
            if before.default_notifications != after.default_notifications:
                data['oldNotif'] = before.default_notifications.name, data['newNotif'] = after.default_notifications.name
                embed.add_field(name="Default notifications",value=before.default_notifications.name+" → "+after.default_notifications.name)
            if before.explicit_content_filter != after.explicit_content_filter:
                data['oldFilter'] = before.explicit_content_filter.name, data['newFilter'] = after.explicit_content_filter.name
                embed.add_field(name="Explicit content filter",value=before.explicit_content_filter.name+" → "+after.explicit_content_filter.name)
            if before.system_channel != after.system_channel:
                data['oldSysChan'] = before.system_channel.id, data['newSysChan'] = after.system_channel.id
                b4 = before.system_channel.mention if before.system_channel is not None else "(None)"
                af = after.system_channel.mention if after.system_channel is not None else "(None)"
                embed.add_field(name="System channel",value=b4+" → "+af)
            if before.icon_url != after.icon_url:
                data['pfp'] = True
                embed.add_field(name='Server icon updated',value='Old: Thumbnail to the right\nNew: Image below')
                embed.set_thumbnail(url=before.icon_url)
                embed.set_image(url=after.icon_url)
            if len(embed.fields) > 0:
                reactions = ['ℹ']
                if await database.SummarizeEnabled(before, 'server'):
                    summaries.get(str(before.id)).add('server', 10, datetime.datetime.now(), data, embed,content=content, reactions=reactions)
                else:
                    message = await (await database.GetLogChannel(before, 'server')).send(content=content,embed=embed)
                    for r in reactions: await message.add_reaction(r)
        await database.VerifyServer(after, bot)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot leaves a server'''
        global bot
        global globalLogChannel
        await globalLogChannel.send(embed=discord.Embed(title="Left server",description=guild.name,timestamp=datetime.datetime.utcnow(),color=0xff0000))
        await database.VerifyServer(guild, bot)
        for member in guild.members:
            await database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is created'''
        global bot
        if await database.GetEnabled(role.guild, "role"):
            content=None
            data = {'role': role.id, 'name': role.name, 'server': role.guild.id}
            embed=discord.Embed(title="🚩Role created",timestamp=datetime.datetime.utcnow(),description=" ",color=0x008000)
            embed.description="Name: "+role.name if role.name != "new role" else ""
            embed.set_footer(text='Role ID: {}'.format(role.id))
            if await database.GetReadPerms(role.guild, "role"):
                try:
                    async for log in role.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.role_create: 
                            embed.description+="\nCreated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            if await database.SummarizeEnabled(role.guild, 'role'):
                summaries.get(str(role.guild.id)).add('role', 11, datetime.datetime.now(), data, embed,content=content)
            else:
                await (await database.GetLogChannel(role.guild, "role")).send(content=content,embed=embed)
        await database.VerifyServer(role.guild, bot)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is deleted'''
        global bot
        if await database.GetEnabled(role.guild, "role"):
            data = {'role': role.id, 'name': role.name, 'server': role.guild.id}
            content=None
            embed=discord.Embed(title="🚩Role deleted",description="Role: "+role.name,timestamp=datetime.datetime.utcnow(),color=0xff0000)
            embed.set_footer(text='Role ID: {}'.format(role.id))
            if await database.GetReadPerms(role.guild, "role"):
                try:
                    async for log in role.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.role_delete: 
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.description+="\n:warning: "+str(len(role.members))+" members lost this role :warning:"
            if await database.SummarizeEnabled(role.guild, 'role'):
                summaries.get(str(role.guild.id)).add('role', 12, datetime.datetime.now(), data, embed,content=content)
            else:
                await (await database.GetLogChannel(role.guild, "role")).send(content=content,embed=embed)
        await database.VerifyServer(role.guild, bot)
        for member in role.members:
            await database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is updated'''
        global bot
        if await database.GetEnabled(before.guild, "role"):
            content=None
            data = {'server': before.guild.id, 'role': before.id, 'oldName': before.name, 'newName': after.name}
            color=0x0000FF if before.color == after.color else after.color
            embed=discord.Embed(title="🚩Role was updated (React with ℹ to view role details)",description="Name: "+ after.name if before.name == after.name else "Name: "+before.name+" → "+after.name,color=color,timestamp=datetime.datetime.utcnow())
            if await database.GetReadPerms(before.guild, "role"):
                try:
                    async for log in before.guild.audit_logs(limit=1): #Color too
                            if log.action == discord.AuditLogAction.role_update:
                                embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            if before.color != after.color: 
                embed.description+="\nEmbed color represents new role color"
                data['color'] = True
            if before.permissions != after.permissions: embed.description+="\n:warning: "+str(len(after.members))+" members received updated permissions :warning:"
            if before.permissions.administrator != after.permissions.administrator: 
                embed.add_field(name="Admin",value="{} → {}".format(before.permissions.administrator, after.permissions.administrator),inline=False)
                data['admin'] = True
            if before.hoist != after.hoist: embed.add_field(name="Displayed separately",value=str(before.hoist)+" → "+str(after.hoist))
            if before.mentionable != after.mentionable: 
                embed.add_field(name="Mentionable",value=str(before.mentionable)+" → "+str(after.mentionable))
                data['mention'] = True
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
                reactions = ['ℹ']
                if await database.SummarizeEnabled(before.guild, 'role'):
                    summaries.get(str(before.guild.id)).add('role', 13, datetime.datetime.now(), data, embed,content=content, reactions=reactions)
                else:
                    message = await (await database.GetLogChannel(before.guild, "role")).send(content=content,embed=embed)
                    for reac in reactions: await message.add_reaction(reac)
        if before.name != after.name: await database.VerifyServer(after.guild, bot)
        for member in after.members:
            await database.VerifyUser(member, bot)
    
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        '''[DISCORD API METHOD] Called when emoji list is updated (creation, update, deletion)'''
        if not await database.GetEnabled(guild, "emoji"):
            return
        content=None
        embed=None
        data = {'server': guild.id}
        if len(before) > len(after):
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0xff0000)
        elif len(after) > len(before):
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0x008000)
        else:
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
        if await database.GetReadPerms(guild, "emoji"):
            try:
                async for log in guild.audit_logs(limit=1):
                    if log.action == discord.AuditLogAction.emoji_delete or log.action==discord.AuditLogAction.emoji_create or log.action==discord.AuditLogAction.emoji_update:
                        embed.description = "By: "+log.user.mention+" ("+log.user.name+")"
                        embed.set_thumbnail(url=log.user.avatar_url)
            except discord.Forbidden:
                content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
        if len(before) > len(after): #Emoji was removed
            embed.title="Emoji removed"
            data['removed'] = [{'emoji': a.id, 'name': a.name} for a in before if a not in after]
            for emoji in before:
                if emoji not in after:
                    embed.add_field(name=emoji.name,value=str(emoji))
                    embed.set_footer(text="Emoji ID: "+str(emoji.id))
                    embed.set_image(url=emoji.url)
        elif len(after) > len(before): #Emoji was added
            embed.title="Emoji created"
            data['added'] = [{'emoji': a.id, 'name': a.name} for a in after if a not in before]
            for emoji in after:
                if emoji not in before:
                    embed.add_field(name=emoji.name,value=str(emoji))
                    embed.set_footer(text="Emoji ID: "+str(emoji.id))
                    embed.set_image(url=emoji.url)
        else: #Emoji was updated
            embed.title="Emoji list updated"
            data['updated'] = [{'emoji': before[a].id, 'oldName': before[a].name, 'newName': after[a].name} for a in range(len(before))]
            embed.set_footer(text="")
            for a in range(len(before)):
                if before[a].name != after[a].name:
                    embed.add_field(name=before[a].name+" → "+after[a].name,value=str(before[a]))
                    embed.set_footer(text=embed.footer.text+"Emoji ID: "+str(before[a].id))
                    embed.set_image(url=before[a].url)
        if len(embed.fields)>0:
            if await database.SummarizeEnabled(guild, 'emoji'):
                summaries.get(str(guild.id)).add('emoji', 14, datetime.datetime.now(), data, embed,content=content)
            else:
                await (await database.GetLogChannel(guild, "emoji")).send(content=content,embed=embed)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not await database.GetEnabled(member.guild, 'voice'):
            return
        embed=discord.Embed(title="Voice Channel update",description=member.mention,timestamp=datetime.datetime.utcnow(),color=0x0000FF)
        data = {'server': member.guild.id, 'member': member.id, 'name': member.name, 'oldChannel': before.channel.id, 'newChannel': after.channel.id}
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
            if not await database.GetReadPerms(member.guild, 'voice'): #this is used to determine mod-only actions for variable convenience since audit logs aren't available
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
                    b4 = "(Disconnected)" if before.channel is None else before.channel.name
                    af = "(Disconnected)" if after.channel is None else after.channel.name
                    embed.add_field(name="🔀",value="Channel: "+b4+" → "+af)
        if len(embed.fields) < 1: return
        if await database.SummarizeEnabled(member.guild, 'voice'):
            summaries.get(str(member.guild.id)).add('voice', 15, datetime.datetime.now(), data, embed)
        else:
            await (await database.GetLogChannel(member.guild, 'voice')).send(embed=embed)

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
            if ctx.channel != await database.GetLogChannel(ctx.guild, 'message'):
                await (await database.GetLogChannel(ctx.guild, 'message')).send(classify+" was paused by "+ctx.author.name)
            await database.PauseMod(ctx.guild, classify.lower())
            return
        duration = ParsePauseDuration((" ").join(args[1:]))
        embed=discord.Embed(title=classify+" was paused",description="by "+ctx.author.mention+" ("+ctx.author.name+")\n\n"+(" ").join(args[1:]),color=0x008000,timestamp=datetime.datetime.utcnow()+datetime.timedelta(seconds=duration))
        embed.set_footer(text="Logging will resume")
        embed.set_thumbnail(url=ctx.author.avatar_url)
        logged = await (await database.GetLogChannel(ctx.guild, 'message')).send(embed=embed)
        try:
            await logged.pin()
        except discord.Forbidden:
            pass
        await status.edit(content="✅",embed=embed)
        await database.PauseMod(ctx.guild, classify.lower())
        await asyncio.sleep(duration)
        await database.ResumeMod(ctx.guild, classify.lower())
        try:
            await logged.delete()
        except discord.Forbidden:
            pass
        await (await database.GetLogChannel(ctx.guild, 'message')).send(classify+" was unpaused",delete_after=60*60*24)
    @commands.command()
    async def unpause(self, ctx, *args):
        if len(args) < 1: return await ctx.send("Please provide module `antispam` or `logging` to unpause")
        args = [a.lower() for a in args]
        if 'antispam' in args:
            await database.ResumeMod(ctx.guild, 'antispam')
            await ctx.send("✅Successfully resumed antispam moderation")
        if 'logging' in args:
            await database.ResumeMod(ctx.guild, 'cyberlog')
            await ctx.send("✅Successfully resumed logging")
    
    @commands.command()
    async def info(self, ctx, *args): #queue system: message, embed, every 3 secs, check if embed is different, edit message to new embed
        import emoji
        arg = ' '.join([a.lower() for a in args])
        carg = ' '.join([a for a in args])
        message = await ctx.send(loading)
        try:
            infoViewer = InfoResult(id=message.id)
            mainKeys=[]
            main=discord.Embed(title='Info results viewer',color=yellow,timestamp=datetime.datetime.utcnow())
            embeds=[]
            MemberConverter = commands.MemberConverter()
            RoleConverter = commands.RoleConverter()
            CatChannelConverter = commands.CategoryChannelConverter()
            TextChannelConverter = commands.TextChannelConverter()
            VoiceChannelConverter = commands.VoiceChannelConverter()
            PartialEmojiConverter = commands.PartialEmojiConverter()
            members = [m for m in ctx.guild.members if arg in m.name.lower() or m.name.lower() in arg]
            roles = [r for r in ctx.guild.roles if arg in r.name.lower() or r.name.lower() in arg]
            channels = [c for c in ctx.guild.channels if arg in c.name.lower() or c.name.lower() in arg]
            for m in ctx.guild.members:
                try: 
                    if await MemberConverter.convert(ctx, carg) == m: members.extend(m)
                except: pass
            for r in ctx.guild.roles:
                try:
                    if await RoleConverter.convert(ctx, carg) == r: roles.extend(r)
                except: pass
            for c in ctx.guild.channels:
                try:
                    if await CatChannelConverter.convert(ctx, carg) == c: channels.extend(c)
                except: pass
                try:
                    if await TextChannelConverter.convert(ctx, carg) == c: channels.extend(c)
                except: pass
                try:
                    if await VoiceChannelConverter.convert(ctx, carg) == c: channels.extend(c)
                except: pass
            try: logs = await ctx.guild.audit_logs(limit=None).flatten()
            except: logs = None
            try: invites = await ctx.guild.invites()
            except: invites = None
            try: bans = await ctx.guild.bans()
            except: pass
            for m in members:
                e = await MemberInfo(m)
                mainKeys.append('👮{}'.format(m.name))
                embeds.append(e)
            for r in roles:
                e = await RoleInfo(r, logs)
                mainKeys.append('🚩{}'.format(r.name))
                embeds.append(e)
            for c in channels:
                types = {discord.TextChannel: '📜', discord.VoiceChannel: '🎙', discord.CategoryChannel: '📂'}
                e = await ChannelInfo(c, [] if type(c) is discord.CategoryChannel else await c.invites(), None if type(c) is not discord.TextChannel else await c.pins(), logs)[1]
                mainKeys.append('{}{}'.format(types.get(type(c)), c.name))
                embeds.append(e)
            for i in invites:
                if i.code.lower() in arg.lower() or arg.lower() in i.code.lower():
                    mainKeys.append('💌{}'.format(i.url))
                    embeds.append(await InviteInfo(i, ctx.guild))
            for em in bot.emojis:
                if em.name.lower() in arg.lower() or arg.lower() in em.name.lower():
                    mainKeys.append('{}{}'.format(em,em.name))
                    try: 
                        owner = await ctx.guild.fetch_emoji(em.id)
                        owner = owner.user
                    except: owner=None
                    embeds.append(await EmojiInfo(em,owner))
            if arg not in emoji.UNICODE_EMOJI and arg not in [str(emoji) for emoji in bot.emojis]:
                try: 
                    partial = await PartialEmojiConverter.convert(ctx, arg)
                    mainKeys.append('{}{}'.format(partial, partial.name))
                    embeds.append(await PartialEmojiInfo(partial))
                except: pass
            if 'server' in arg or 'guild' in arg or arg in ctx.guild.name.lower() or ctx.guild.name.lower() in arg:
                mainKeys.append('ℹServer information')
                try: hooks = await ctx.guild.webhooks()
                except: hooks = None
                embeds.append(await ServerInfo(ctx.guild, logs, bans, hooks, invites))
            if 'roles' in arg:
                mainKeys.append('ℹRole list information')
                embeds.append(await RoleListInfo(ctx.guild.roles, logs))
            if 'members' in arg or 'people' in arg or 'users' in arg or 'bots' in arg:
                mainKeys.append('ℹMember list information')
                embeds.append(await MemberListInfo(ctx.guild.members))
            if 'channels' in arg:
                mainKeys.append('ℹChannel list information')
                embeds.append(await ChannelListInfo(ctx.guild.channels, logs))
            if 'emoji' in arg or 'emotes' in arg:
                mainKeys.append('ℹEmoji information')
                embeds.append(await EmojiListInfo(ctx.guild.emojis, logs))
            if 'invites' in arg:
                mainKeys.append('ℹInvites information')
                embeds.append(await InvitesListInfo(invites, logs))
            if 'bans' in arg:
                mainKeys.append('ℹBans information')
                embeds.append(await BansListInfo(bans, logs, ctx.guild))
            if 'dev' in arg or 'owner' in arg or 'master' in arg or 'creator' in arg or 'author' in arg or 'disguard' in arg or 'bot' in arg:
                mainKeys.append('{}Information about me'.format(bot.get_emoji(569191704523964437)))
                embeds.append(await BotInfo(await bot.application_info()))
            main.description='**{} RESULTS** for *{}*\n**Type the number of the option to view**\n'.format(len(embeds), arg)
            for result in range(len(mainKeys)):
                main.description+='\n{}: {}'.format(result + 1, mainKeys[result])
            main.set_footer(text='ID: {}'.format(message.id))
            main.set_author(name='{}: {}'.format(ctx.author.name, ctx.author.id),icon_url=ctx.author.avatar_url)
            infoViewer.main = main
            infoViewer.embeds = embeds
            info[message.id] = infoViewer
            if len(embeds) == 0: return await message.edit(content=None,embed=main)
            elif len(embeds) == 1: await message.edit(content=None,embed=embeds[0])
            else: await message.edit(content=None,embed=main)
        except Exception as e: return await message.edit(content='An error occured while searching, please send this to my dev: \n{}'.format(e))
        def check(m):
            try: return m.author==ctx.author and int(m.content) <= len(embeds)
            except: return False
        try: message2 = await bot.wait_for('message',check=check,timeout=120)
        except: return
        await message.edit(content=loading)
        AvoidDeletionLogging(1, message.guild)
        try: await message2.delete()
        except: AvoidDeletionLogging(0, None)
        await message.edit(content=None,embed=embeds[int(message2.content)-1])
        await message.add_reaction('⬅')

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
        summaries[str(server.id)] = ServerSummary()

async def ServerInfo(s: discord.Guild, logs, bans, hooks, invites):
    '''Formats an embed, displaying stats about a server. Used for ℹ navigation or `info` command'''
    embed=discord.Embed(title=s.name,description='' if s.description is None else '**Server description:** {}\n\n'.format(s.description),timestamp=datetime.datetime.utcnow(),color=yellow)
    online=bot.get_emoji(606534231631462421)
    idle=bot.get_emoji(606534231610490907)
    dnd=bot.get_emoji(606534231576805386)
    offline=bot.get_emoji(606534231492919312)
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
    for chan in s.text_channels:
        path = "Indexes/{}/{}".format(s.id, chan.id)
        messages+=len(os.listdir(path))
    created = s.created_at
    txt='{}Text Channels: {}'.format('📜', len(s.text_channels))
    vc='{}Voice Channels: {}'.format('🎙', len(s.voice_channels))
    cat='{}Category Channels: {}'.format('📂', len(s.categories))
    embed.description+=('**Channel count:** {}\n{}\n{}\n{}'.format(len(s.channels),cat, txt, vc))
    online='{}Online: {}'.format(online, len([m for m in s.members if m.status == discord.Status.online]))
    idle='{}Idle: {}'.format(idle, len([m for m in s.members if m.status == discord.Status.idle]))
    dnd='{}Do not disturb: {}'.format(dnd, len([m for m in s.members if m.status == discord.Status.dnd]))
    offline='{}Offline/invisible: {}'.format(offline, len([m for m in s.members if m.status == discord.Status.offline]))
    embed.description+='\n\n**Member count:** {}{}\n{}'.format(len(s.members),'' if s.max_members is None else '/{}'.format(s.max_members),'\n'.join([online, idle, dnd, offline]))
    embed.description+='\n\n**Features:** {}'.format(', '.join(s.features) if len(s.features) > 0 else 'None')
    embed.description+='\n\n**Nitro boosters:** {}/{}, **perks:** {}'.format(s.premium_subscription_count,perkDict.get(s.premium_tier),', '.join(perks))
    #embed.set_thumbnail(url=s.icon_url)
    embed.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(s), (datetime.datetime.utcnow()-created).days),inline=False)
    embed.add_field(name='Region',value=str(s.region))
    embed.add_field(name='AFK Timeout',value='{}s --> {}'.format(s.afk_timeout, s.afk_channel))
    if s.max_presences is not None: embed.add_field(name='Max Presences',value='{} (BETA)'.format(s.max_presences))
    embed.add_field(name='Mods need 2FA',value=mfa.get(s.mfa_level))
    embed.add_field(name='Verification',value=veri.get(str(s.verification_level)))
    embed.add_field(name='Explicit filter',value=s.explicit_content_filter)
    embed.add_field(name='Default notifications',value=str(s.default_notifications)[str(s.default_notifications).find('.')+1:])
    try: embed.add_field(name='Locale',value=s.preferred_locale)
    except: pass
    embed.add_field(name='Audit logs',value=0 if logs is None else len(logs))
    if s.system_channel is not None: embed.add_field(name='System channel',value='{}: {}'.format(s.system_channel.mention, ', '.join([k[0] for k in (iter(s.system_channel.flags))])))
    embed.add_field(name='Role count',value=len(s.roles) - 1)
    embed.add_field(name='Owner',value=s.owner.mention)
    embed.add_field(name='Banned members',value=0 if bans is None else len(bans))
    embed.add_field(name='Webhooks',value=0 if hooks is None else len(hooks))
    embed.add_field(name='Invites',value=0 if invites is None else len(invites))
    embed.add_field(name='Emojis',value='{}/{}'.format(len(s.emojis), s.emoji_limit))
    embed.add_field(name='Messages', value='about {}'.format(messages))
    embed.set_footer(text='Server ID: {}'.format(s.id))
    return embed

async def ChannelInfo(channel: discord.abc.GuildChannel, invites, pins, logs):
    permString = None
    types = {discord.TextChannel: '📜', discord.VoiceChannel: '🎙', discord.CategoryChannel: '📂'}
    details = discord.Embed(title='{}{}'.format(types.get(type(channel)),channel.name), description='',color=yellow, timestamp=datetime.datetime.utcnow())
    details.set_footer(text='Channel ID: {}'.format(channel.id))
    if type(channel) is not discord.CategoryChannel:
        #details.description+='\n\n**Channels {}**\n{}'.format('without a category' if channel.category is None else 'in category {}'.format(channel.category.name), '\n'.join(['{}'.format('{}{}{}{}'.format('**' if chan==channel else '', types.get(type(chan)), chan.name, '**' if chan==channel else '')) for chan in channel.category.channels]))
        details.description+='\n**Category:** {}'.format('None' if channel.category is None else channel.category.name)
    else: details.description+='\n\n**Channels in this category**\n{}'.format('\n'.join(['{}{}'.format(types.get(type(chan)), chan.name) for chan in channel.channels]))
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
        temp.append('{:<60s}'.format(k))
        string='\n'.join(['     {}: {:>{diff}}'.format(kk.name, english.get(vv), diff=25 - len(kk.name)) for kk,vv in iter(v.items())])
        temp.append(string)
        permString = '```Channel permission overwrites\n{}```'.format('\n'.join(temp))
    created=channel.created_at + datetime.timedelta(hours=await database.GetTimezone(channel.guild))
    updated = None
    for log in logs:
        if log.action == discord.AuditLogAction.channel_update and (datetime.datetime.utcnow() - log.created_at).seconds > 600:
            if log.target == channel:
                updated = log.created_at + datetime.timedelta(hours=await database.GetTimezone(channel.guild))
                break
    if updated is None: updated = created
    details.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(channel.guild), (datetime.datetime.utcnow()-created).days))
    details.add_field(name='Last updated',value='{}'.format('{} {} ({} days ago)'.format(updated.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(channel.guild), (datetime.datetime.utcnow()-updated).days)))
    inviteCount = []
    for inv in iter(invites): inviteCount.append(inv.inviter)
    details.add_field(name='Invites to here',value='None' if len(inviteCount) is 0 else ', '.join(['{} by {}'.format(a[1], a[0].name) for a in iter(collections.Counter(inviteCount).most_common())]))
    if type(channel) is discord.TextChannel:
        details.add_field(name='Topic',value='{}{}'.format('<No topic>' if channel.topic is None or len(channel.topic) < 1 else channel.topic[:100], '' if channel.topic is None or len(channel.topic)<=100 else '...'),inline=False)
        details.add_field(name='Slowmode',value='{}s'.format(channel.slowmode_delay))
        details.add_field(name='Message count',value=str(loading))
        details.add_field(name='NSFW',value=channel.is_nsfw())
        details.add_field(name='News channel?',value='{} (I think this is beta)'.format(channel.is_news()))
        details.add_field(name='Pins count',value=len(pins))
    if type(channel) is discord.VoiceChannel:
        details.add_field(name='Bitrate',value='{} kbps'.format(int(channel.bitrate / 1000)))
        details.add_field(name='User limit',value=channel.user_limit)
        details.add_field(name='Members currently in here',value='None' if len(channel.members)==0 else ', '.join([member.mention for member in channel.members]))
    if type(channel) is discord.CategoryChannel:
        details.add_field(name='NSFW',value=channel.is_nsfw())
    if type(channel) is discord.TextChannel:
        path = "Indexes/{}/{}".format(channel.guild.id, channel.id)
        count = len(os.listdir(path))
        details.set_field_at(5, name='Message count',value='about {}'.format(count))
    return [permString, details]

async def RoleInfo(r: discord.Role, logs):
    #sortedRoles = sorted(r.guild.roles, key = lambda x: x.position, reverse=True)
    #start = r.position - 3
    #if start < 0: start = 0
    created = r.created_at + datetime.timedelta(hours=await database.GetTimezone(r.guild))
    updated = None
    for log in logs:
        if log.action == discord.AuditLogAction.role_update and (datetime.datetime.utcnow() - log.created_at).seconds > 600:
            if log.target == r:
                updated = log.created_at + datetime.timedelta(hours=await database.GetTimezone(r.guild))
                break
    if updated is None: updated = created
    embed=discord.Embed(title='🚩Role: {}'.format(r.name),description='**Permissions:** {}'.format('Administrator' if r.permissions.administrator else ', '.join([p[0] for p in iter(r.permissions) if p[1]])),timestamp=datetime.datetime.utcnow(),color=r.color)
    #embed.description+='\n**Position**:\n{}'.format('\n'.join(['{0}{1}{0}'.format('**' if sortedRoles[role] == r else '', sortedRoles[role].name) for role in range(start, start+6)]))
    embed.add_field(name='Displayed separately',value=r.hoist)
    embed.add_field(name='Externally managed',value=r.managed)
    embed.add_field(name='Mentionable',value=r.mentionable)
    embed.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(r.guild), (datetime.datetime.utcnow()-created).days))
    embed.add_field(name='Last updated',value='{}'.format('{} {} ({} days ago)'.format(updated.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(r.guild), (datetime.datetime.utcnow()-updated).days)))
    embed.add_field(name='Belongs to',value='{} members'.format(len(r.members)))
    embed.set_footer(text='Role ID: {}'.format(r.id))
    return embed

async def MemberInfo(m: discord.Member):
    embed=discord.Embed(title='Member details',timestamp=datetime.datetime.utcnow(),color=yellow)
    online=bot.get_emoji(606534231631462421)
    idle=bot.get_emoji(606534231610490907)
    dnd=bot.get_emoji(606534231576805386)
    offline=bot.get_emoji(606534231492919312)
    activities = {discord.Status.online: online, discord.Status.idle: idle, discord.Status.dnd: dnd, discord.Status.offline: offline}
    embed.description='{}{} {}'.format(activities.get(m.status), m.mention, '' if m.nick is None else 'aka {}'.format(m.nick))
    if len(m.activities) > 0:
        current=[]
        for act in m.activities:
            if act.type is discord.ActivityType.playing: current.append('playing {}'.format(act.name))
            elif act.type is discord.ActivityType.streaming: current.append('streaming {}'.format(act.name))
            elif act.type is discord.ActivityType.listening and act.name == 'Spotify': current.append('listening to {} by {}'.format(act.title, ', '.join(act.artists)))
        embed.description+='\n\n • {}'.format('\n • '.join(current))
    embed.description+='\n\n**Member\'s highest role is {} and they have the following permissions:** {}'.format(m.top_role.name,'Administrator' if m.guild_permissions.administrator else ', '.join([p[0] for p in iter(m.guild_permissions) if p[1]]))
    boosting = m.premium_since
    joined = m.joined_at + datetime.timedelta(hours=await database.GetTimezone(m.guild))
    created = m.created_at + datetime.timedelta(hours=await database.GetTimezone(m.guild))
    if m.voice is None: voice = 'None'
    else:
        voice = '{}{} in {}{}'.format('🔇' if m.voice.mute or m.voice.self_mute else '', '🤐' if m.voice.deaf or m.voice.self_deaf else '','N/A' if m.voice.channel is None else m.voice.channel.name, ', AFK' if m.voice.afk else '')
    if boosting is None: embed.add_field(name='Boosting server',value='Nope :(')
    else:
        boosting += datetime.timedelta(hours=await database.GetTimezone(m.guild))
        embed.add_field(name='Boosting server',value='{}'.format('Since {} {} ({} days ago)'.format(boosting.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(m.guild), (datetime.datetime.utcnow()-boosting).days)))
    embed.add_field(name='Account created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(m.guild), (datetime.datetime.utcnow()-created).days))
    embed.add_field(name='Joined server',value='{} {} ({} days ago)'.format(joined.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(m.guild), (datetime.datetime.utcnow()-joined).days))
    embed.add_field(name='Posts',value=MemberPosts(m))
    embed.add_field(name='Roles',value='{}: {}'.format(len(m.roles),', '.join([role.name for role in m.roles])))
    embed.add_field(name='🎙',value=voice)
    embed.set_thumbnail(url=m.avatar_url)
    embed.set_footer(text='Member ID: {}'.format(m.id))
    return embed
    
async def EmojiInfo(e: discord.Emoji, owner):
    created = e.created_at + datetime.timedelta(hours=await database.GetTimezone(e.guild))
    embed = discord.Embed(title=e.name,description=str(e),timestamp=datetime.datetime.utcnow(),color=yellow)
    embed.set_image(url=e.url)
    embed.set_footer(text='Emoji ID: {}'.format(e.id))
    embed.add_field(name='Twitch emoji',value=e.managed)
    if owner is not None: embed.add_field(name='Uploaded by',value='{} ({})'.format(owner.mention, owner.name))
    embed.add_field(name='Server',value=e.guild.name)
    embed.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(e.guild), (datetime.datetime.utcnow()-created).days))
    return embed

async def PartialEmojiInfo(e: discord.PartialEmoji):
    embed=discord.Embed(title=e.name,description=str(e),timestamp=datetime.datetime.utcnow(),color=yellow)
    embed.set_image(url=e.url)
    embed.set_footer(text='Emoji ID: {}'.format(e.id))
    return embed

async def InviteInfo(i: discord.Invite, s): #s: server
    embed=discord.Embed(title='Invite details',description=str(i),timestamp=datetime.datetime.utcnow(),color=yellow)
    embed.set_thumbnail(url=i.guild.icon_url)
    expires=datetime.datetime.utcnow() + datetime.timedelta(seconds=i.max_age)
    created = i.created_at + datetime.timedelta(hours=await database.GetTimezone(s))
    embed.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(s), (datetime.datetime.utcnow()-created).days))
    embed.add_field(name='Expires',value='{} {}'.format(expires.strftime("%b %d, %Y - %I:%M %p"), await database.GetNamezone(s)))
    embed.add_field(name='Server',value=i.guild.name)
    embed.add_field(name='Channel',value=i.guild.name)
    embed.add_field(name='Used',value='{}/{} times'.format(i.uses, '∞' if i.max_uses is 0 else i.max_uses))
    embed.set_footer(text='Invite server ID: {}'.format(i.guild.id))
    #In the future, once bot is more popular, integrate server stats from other servers
    return embed

async def BotInfo(app):
    embed=discord.Embed(title='About Disguard',description='{0}{1}{0}'.format(bot.get_emoji(569191704523964437), app.description),timestamp=datetime.datetime.utcnow(),color=yellow)
    embed.set_footer(text='My ID: {}'.format(app.id))
    embed.set_thumbnail(url=app.icon_url)
    embed.add_field(name='Developer',value=app.owner)
    embed.add_field(name='Public Bot',value=app.bot_public)
    embed.add_field(name='In development since',value='Around March 28, 2019')
    embed.add_field(name='Currently hosted on',value='Raspberry Pi (3)')
    embed.add_field(name='Website with information',value='[{}]({})'.format('Disguard website', 'https://disguard.netlify.com/'))
    embed.add_field(name='Servers',value=len(bot.guilds))
    embed.add_field(name='Emojis',value=len(bot.emojis))
    embed.add_field(name='Users',value=len(bot.users))
    return embed

async def EmojiListInfo(emojis, logs):
    '''Prereq: len(emojis) > 0'''
    embed=discord.Embed(title='{}\'s emojis'.format(emojis[0].guild.name),description='Total emojis: {}'.format(len(emojis)),timestamp=datetime.datetime.utcnow(),color=yellow)
    static = [str(e) for e in emojis if not e.animated]
    animated = [str(e) for e in emojis if e.animated]
    if len(static) > 0: embed.add_field(name='Static emojis: {}/{}'.format(len(static), emojis[0].guild.emoji_limit),value=''.join(static),inline=False)
    if len(animated) > 0: embed.add_field(name='Animated emojis: {}/{}'.format(len(animated), emojis[0].guild.emoji_limit),value=''.join(animated),inline=False)
    if logs is not None: embed.add_field(name='Total emojis ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.emoji_create])))
    return embed

async def ChannelListInfo(channels, logs):
    '''Prereq: len(channels) > 0'''
    codes = {discord.TextChannel: '📜', discord.VoiceChannel: '🎙', discord.CategoryChannel: '📂'}
    embed=discord.Embed(title='{}\'s channels'.format(channels[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow)
    none=['(No category)']
    none += ['   {}{}'.format(codes.get(c.type), c.name) for c in channels if type(c) is not discord.CategoryChannel and c.category is None]
    for chan in channels[0].guild.categories:
        none.append('{}{}'.format(codes.get(chan.type), chan.name))
        none+=['   {}{}'.format(codes.get(c.type), c.name) for c in chan.channels]
    embed.description='Total channels: {}\n\n{}'.format(len(channels), '\n'.join(none))
    if logs is not None: embed.add_field(name='Total channels ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.channel_create])))
    return embed

async def RoleListInfo(roles, logs):
    '''Prereq: len(roles) > 0'''
    embed=discord.Embed(title='{}\'s roles'.format(roles[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow)
    embed.description='Total roles: {}\n\n • {}'.format(len(roles), '\n • '.join([r.name for r in roles]))
    embed.add_field(name='Roles displayed separately',value=len([r for r in roles if r.hoist]))
    embed.add_field(name='Mentionable roles',value=len([r for r in roles if r.mentionable]))
    embed.add_field(name='Externally managed roles',value=len([r for r in roles if r.managed]))
    embed.add_field(name='Roles with manage server',value=len([r for r in roles if r.permissions.manage_guild]))
    embed.add_field(name='Roles with administrator',value=len([r for r in roles if r.permissions.administrator]))
    if logs is not None: embed.add_field(name='Total roles ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.role_create])))
    return embed

async def MemberListInfo(members):
    embed=discord.Embed(title='{}\'s members'.format(members[0].guild.name),description='',timestamp=datetime.datetime.utcnow(),color=yellow)
    posts=[]
    for channel in members[0].guild.text_channels:
        path = "Indexes/{}/{}".format(members[0].guild.id, channel.id)
        for f in os.listdir(path):
            posts.append(int(f[f.find('_')+1:f.find('.')]))
    most = ['{} with {}'.format(bot.get_user(a[0]).name, a[1]) for a in iter(collections.Counter(posts).most_common(1))][0]
    online=bot.get_emoji(606534231631462421)
    idle=bot.get_emoji(606534231610490907)
    dnd=bot.get_emoji(606534231576805386)
    offline=bot.get_emoji(606534231492919312)
    humans='👮Humans: {}'.format(len([m for m in members if not m.bot]))
    bots='🤖Bots: {}\n'.format(len([m for m in members if m.bot]))
    online='{}Online: {}'.format(online, len([m for m in members if m.status == discord.Status.online]))
    idle='{}Idle: {}'.format(idle, len([m for m in members if m.status == discord.Status.idle]))
    dnd='{}Do not disturb: {}'.format(dnd, len([m for m in members if m.status == discord.Status.dnd]))
    offline='{}Offline/invisible: {}'.format(offline, len([m for m in members if m.status == discord.Status.offline]))
    embed.description+='\n\n**Member count:** {}{}\n{}'.format(len(members),'' if members[0].guild.max_members is None else '/{}'.format(members[0].guild.max_members),'\n'.join([humans, bots, online, idle, dnd, offline]))
    embed.add_field(name='Playing/Listening/Streaming',value=len([m for m in members if len(m.activities) > 0]))
    embed.add_field(name='Members with nickname',value=len([m for m in members if m.nick is not None]))
    embed.add_field(name='On mobile',value=len([m for m in members if m.is_on_mobile()]))
    embed.add_field(name='In voice channel',value=len([m for m in members if m.voice is not None]))
    embed.add_field(name='Most posts',value=most)
    embed.add_field(name='Moderators',value=len([m for m in members if m.guild_permissions.manage_guild]))
    embed.add_field(name='Administrators',value=len([m for m in members if m.guild_permissions.administrator]))
    return embed

async def InvitesListInfo(invites, logs):
    embed=discord.Embed(title='{}\'s invites'.format(invites[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow)
    embed.description='Total invites: {}\n\n • {}'.format(len(invites), '\n • '.join(['discord.gg/**{}**: Goes to {}, created by {}'.format(i.code, i.channel.name, i.inviter.name) for i in invites]))
    if logs is not None: embed.add_field(name='Total invites ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.invite_create])))
    return embed

async def BansListInfo(bans, logs, s): #s=server
    embed=discord.Embed(title='{}\'s bans'.format(s.name),timestamp=datetime.datetime.utcnow(),color=yellow)
    embed.description='Users currently banned: {}'.format(len(bans))
    if len(bans) == 0: return embed
    array = []
    current = []
    if logs is not None:
        for b in bans:
            for l in logs:
                if l.action == discord.AuditLogAction.ban and l.target == b.user:
                    created = l.created_at + datetime.timedelta(hours=await database.GetTimezone(s))
                    array.append('{}: {} banned on {} because {}'.format(l.target.name, l.user.name, created.strftime('%m/%d/y@%H:%M'), '(No reason specified)' if b.reason is None else b.reason))
                    current.append(b.user)
        other=[]
        for l in logs:
            if l.action == discord.AuditLogAction.ban and l.target not in current:
                created = l.created_at + datetime.timedelta(hours=await database.GetTimezone(s))
                other.append('{}: {} banned on {} because {}'.format(l.target.name, l.user.name, created.strftime('%m/%d/y@%H:%M'), '(No reason specified)' if l.reason is None else l.reason))
    else:
        for b in bans:
            array.append('{}: Banned because {}'.format(b.user.name, '(No reason specified)' if b.reason is None else b.reason))
    embed.add_field(name='Banned now',value='\n'.join(array),inline=False)
    if logs is not None: embed.add_field(name='Banned previously',value='\n'.join(other))
    return embed


def Summarize(queue, keycounts):
    '''Returns a nice summary of what's happened in a server. Parses through before/after, etc'''
    global bot
    categories = {} #Dict of queue list index : category elements to prevent indexing over queue multiple times
    counts = {} #Dict of keycount range index : queue indexes of this category to prevent indexing over queue multiple times. Places in queue where this happens
    embeds = []
    embed = discord.Embed()
    for q in range(len(queue)): categories[q] = queue[q].get('category')
    for q in range(16): counts[q] = [a for a, b in categories.items() if b == q]
    #Vars - a: 0-15; b: number of occurences, c: indexing through list of indexes to the queue for this occurence to prevent indexing through queue every time
    for a, b in keycounts.items(): #Iterate through category/count in keycounts, similar to the main summarize task
        if b > 0:
            t1 = [] #Various target variables, declared here to save space. Used for author/content, etc in embed formatting. Temp variables
            t2, t3, t4, t5, t6, t7, t8, s = [], [], [], [], [], [], [], []
            if len(embed.fields) > 6:
                embeds.append(embed.to_dict())
                embed = discord.Embed()
            if a in [0, 1]: #Very similar format between message edits and message deletions. Commentation will be for edits, but it's the same thing
                for c in counts[a]: #t1: Author names, t2: Author IDs, t3: Used author IDs
                    t1.append(queue[c].get('data').get('name')) #Appends name
                    t2.append(queue[c].get('data').get('author')) #Appends ID
                for c in range(len(t1)): #Iterates through all names; every message edit occurence
                    if t2[c] not in t3: #If this person's ID isn't already in the list of authors of edited message, then add an occurence
                        s.append('{} by {}'.format(t2.count(t2[c]), t1[c])) #Example: 5 by RicoViking9000#2395
                        t3.append(t2[c]) #Add ID to list to avoid duplicates
                if len(t1) > 7: string = '{} and {} more by {} more people'.format(', '.join(s[:7]), len(t1) - 7, len(collections.Counter(t2[7:]).values()))
                else: string = ', '.join(s) #If fewer than 8 occurences, simply join them with a comma
                embed.add_field(name='Message {}'.format('Edits' if a == 0 else 'Deletions'),value=string)
            if a == 2:
                for c in counts[a]: #t1: Channel IDs, t2: Channel types, t3: Channel names, t4: used IDs
                    t1.append(queue[c].get('data').get('channel'))
                    t2.append(queue[c].get('data').get('type'))
                    t3.append(queue[c].get('data').get('name'))
                for c in range(len(t1)):
                    s.append('{}{}{}{}'.format(t2[c], '~~' if bot.get_channel(t1[c]) is None else '', bot.get_channel(t1[c]).mention if t2[c] == '📜' and bot.get_channel(t1[c]) is not None else t3[c], '~~' if bot.get_channel(t1[c]) is None else '')) #Mention channel if it's text, strikethru if deleted since
                    t4.append(t1[c])
                string = ', '.join(s)
                if len(t1) > 7: 
                    string += ' & {} more'.format(len(t1) - len(t4))
                    if [bot.get_channel(c) for c in t1].count(None) > 0: #If channels were deleted since creation... count of indexes where bot can't find channel
                        string+=', incl. {} deleted since creation'.format([bot.get_channel(c) for c in t1].count(None))
                embed.add_field(name='Channel Creations',value=string)
            if a == 3:
                v = {True: 'on', False: 'off'} #Used for NSFW, on/off is better than True/False
                for c in counts[a]:  #t1: channel ID, t2: channel type, t3: old channel name, t4: changes, t5: used quickkey channel IDs
                    t1.append(queue[c].get('data').get('channel'))
                    t2.append(queue[c].get('data').get('type'))
                    t3.append(queue[c].get('data').get('oldName'))
                    t4.append({'name': queue[c].get('data').get('oldName') != queue[c].get('data').get('newName'),
                    'topic': queue[c].get('data').get('oldTopic') != queue[c].get('data').get('newTopic'),
                    'slowmode': queue[c].get('data').get('oldSlowmode') != queue[c].get('data').get('newSlowmode'),
                    'nsfw': queue[c].get('data').get('oldNsfw') != queue[c].get('data').get('newNsfw'),
                    'bitrate': queue[c].get('data').get('oldBitrate') != queue[c].get('data').get('newBitrate'),
                    'userLimit': queue[c].get('data').get('oldLimit') != queue[c].get('data').get('newLimit'),
                    'category': queue[c].get('data').get('oldCategory') != queue[c].get('data').get('newCategory')})
                for c in range(len(t1)):
                    temp = [t2[c], t3[c], ': ']
                    if t4[c].get('name'): temp.append('Name changed to **{}**'.format(queue[c].get('data').get('newName')))
                    if t4[c].get('topic'): temp.append('Description updated')
                    if t4[c].get('slowmode'): temp.append('Slowmoded changed from {}s to {}s'.format(queue[c].get('data').get('oldSlowmode'), queue[c].get('data').get('newSlowmode')))
                    if t4[c].get('nsfw'): temp.append('NSFW turned **{}**'.format(v.get(queue[c].get('data').get('newNsfw'))))
                    if t4[c].get('bitrate'): temp.append('Bitrate adjusted from **{} to **{}**'.format(queue[c].get('data').get('oldBitrate'), queue[c].get('data').get('newBitrate')))
                    if t4[c].get('userLimit'): temp.append('User limit changed from **{}** to **{}**'.format(queue[c].get('data').get('oldLimit'), queue[c].get('data').get('newLimit')))
                    if t4[c].get('category'): temp.append('Moved from category **{}** to **{}**'.format(queue[c].get('data').get('oldCategory'), queue[c].get('data').get('newCategory')))
                    s.append(temp)
                temp2 = []
                for c in s[:5]: temp2.append('{}{}'.format(''.join(c[:3]), ', '.join(c[3:])))
                if sum([len(c) for c in temp2]) > 128:
                    temp2 = []
                    #Shortener formatting stuff here
                    combos = {}
                    sketch = [''.join('{}'.format(list(k.items()))) for k in t4]
                    greater = [d for d, e in collections.Counter(sketch).items() if e > 1] #Dict combinations that are greater than 1, if any
                    for d in greater: combos[d] = [e for e in range(len(t4)) if ''.join('{}'.format(str(list(t4[e].items())))) == d]
                    total = []
                    for d, e in combos.items():
                        total.extend(e)
                        if len(temp2) < 5:
                            temp2.append('{}: {} updated'.format(', '.join(['{}**{}**'.format(t2[f], t3[f]) for f in e]), ', '.join([k for k,v in list(t4[e[0]].items()) if v])))
                    for d in range(len(t1)):
                        if d not in total and len(temp2) < 5:
                            temp2.append('{}**{}**: {} updated'.format(t2[d], t3[d], ', '.join([k for k,v in list(t4[d[0]].items()) if v])))
                string = '▫'.join(temp2)
                if len(t1) > 5: string += ' ▫ and {} more channels'.format(len(t1) - 5)
                embed.add_field(name='Channel updates',value=string)
    embeds.append(embed.to_dict())
    return embeds

def MemberPosts(m: discord.Member):
    messageCount=0
    for channel in m.guild.text_channels:
        path = "Indexes/{}/{}".format(m.guild.id, channel.id)
        for f in os.listdir(path):
            if str(m.id) in f: messageCount+=1
    return messageCount
            
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