import discord
from discord.ext import commands, tasks
import database
import datetime
import asyncio
import os
import collections
import traceback
import copy
import sys
import random
import psutil
import cpuinfo
import typing
import json
import shutil
import aiohttp

bot = None
serverPurge = {}
summarizeOn=False
secondsInADay = 3600 * 24
units = ['second', 'minute', 'hour', 'day']
indexes = 'Indexes'
tempDir = 'Attachments/Temp' #Path to save images for profile picture changes and other images in logs
try: os.makedirs(tempDir)
except FileExistsError: pass

summaries = {}
grabbedSummaries = {}
indexed = {}
info = {}
lightningLogging = {}
lightningUsers = {}
members = {}

yellow=0xffff00
green=0x008000
red=0xff0000
blue=0x0000FF
newline='\n'
newlineQuote = '\n> '
qlf = '  ' #Two special characters to represent quoteLineFormat

permissionKeys = {'create_instant_invite': 'Create Invite', 'kick_members': 'Kick Members', 'ban_members': 'Ban Members', 'administrator': 'Administrator',
'manage_channels': 'Manage Channels', 'manage_guild': 'Manage Server', 'add_reactions': 'Add Reactions', 'view_audit_log': 'View Audit Log',
'priority_speaker': 'Priority Speaker', 'stream': 'Go Live', 'read_messages': 'Read Messages', 'send_messages': 'Send Messages', 
'send_tts_messages': 'Send TTS Messages', 'manage_messages': 'Manage Messages', 'embed_links': 'Embed Links', 'attach_files': 'Attach Files',
'read_message_history': 'Read Message History', 'mention_everyone': 'Mention @everyone, @here, and All Roles', 'external_emojis': 'Use External Emojis', 'view_guild_insights': 'View Server Insights',
'connect': 'Connect', 'speak': 'Speak', 'mute_members': 'Mute Members', 'deafen_members': 'Deafen Members', 'move_members': 'Move members',
'use_voice_activation': 'Use Voice Activity', 'change_nickname': 'Change Nickname', 'manage_nicknames': 'Manage Nicknames', 'manage_roles': 'Manage Roles', 'manage_webhooks': 'Manage Webhooks', 'manage_emojis': 'Manage Emojis'}

permissionDescriptions = {'create_instant_invite': '', 'kick_members': '', 'ban_members': '', 'administrator': 'Members with this permission have every permission and also bypass channel specific permissions',
'manage_channels': 'Members with this permission can create, edit, and delete channels', 'manage_guild': 'Members with this permission can change the server\'s name, region, icon, and other settings',
'add_reactions': 'Members with this permission can add **new** reactions to a message (this permission is not needed for members to add to an existing reaction)',
'view_audit_log': 'Members with this permission have access to view the server audit logs',
'priority_speaker': 'Members with this permission have the ability to be more easily heard when talking. When activated, the volume of others without this permission will be automatically lowered. This power is activated using the push to talk keybind.',
'stream': 'Members with this permission can stream applications or screenshare in voice channels', 'read_messages': '', 'send_messages': '', 'send_tts_messages': 'Members with this permission can send text-to-speech messages by starting a message with /tts. These messages can be heard by everyone focused on the channel',
'manage_messages': 'Members with this permission can delete messages authored by other members and can pin/unpin any message', 'embed_links': '', 'attach_files': '',
'read_message_history': '', 'mention_everyone': 'Members with this permission can use @everyone or @here to ping all members **in this channel**. They can also @mention all roles, even if that role is not normally mentionable',
'external_emojis': 'Use External Emojis', 'view_guild_insights': 'View Server Insights', 'connect': '', 'speak': '', 'mute_members': '', 'deafen_members': '', 'move_members': 'Members with this permission can drag members into and out of voice channels',
'use_voice_activation': 'Members must use Push-To-Talk if this permission is disabled', 'change_nickname': 'Members with this permission can change their own nickname', 'manage_nicknames': 'Manage Nicknames',
'manage_roles': 'Members with this permission can create new roles and edit/delete roles below their highest role granting this permission', 'manage_webhooks': 'Members with this permission can create, edit, and delete webhooks',
'manage_emojis': 'Members with this permission can use custom emojis from other servers in this server'}

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
    def __init__(self, obj, mainKey, relevance):
        self.obj = obj
        self.mainKey = mainKey
        self.relevance = relevance

class Cyberlog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.lightningLogging = {}
        self.bot.lightningUsers = {}
        self.disguard = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='disguard')
        self.loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')
        self.greenPlus = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='greenPlus')
        self.whitePlus = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='whitePlus')
        self.whiteMinus = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='whiteMinus')
        self.whiteCheck = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='whiteCheck')
        self.hashtag = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='hashtag')
        self.trashcan = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='trashcan')
        self.sendMessage = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='sendMessage')
        self.online= discord.utils.get(bot.get_guild(560457796206985216).emojis, name='online')
        self.idle = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='idle')
        self.dnd = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='dnd')
        self.offline = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='offline')
        self.imageLogChannel = bot.get_channel(534439214289256478)
        self.globalLogChannel = bot.get_channel(566728691292438538)
        self.channelKeys = {'text': self.hashtag, 'voice': '🎙', 'category': '📁', 'private': '🔒', 'news': '📰'}
        self.permissionStrings = {}
        self.repeatedJoins = {}
        self.pins = {}
        self.categories = {}
        self.invites = {}
        self.rawMessages = {}
        self.pauseDelete = []
        self.resumeToken = None
        self.summarize.start()
        self.DeleteAttachments.start()
        self.trackChanges.start()
    
    def cog_unload(self):
        self.summarize.cancel()
        self.DeleteAttachments.cancel()

    @tasks.loop()
    async def trackChanges(self):
        global lightningUsers
        global lightningLogging
        while True:
            try:
                async with database.getDatabase().watch(full_document='updateLookup', resume_after = self.resumeToken) as change_stream:
                    async for change in change_stream:
                        self.resumeToken = change_stream.resume_token
                        if change['operationType'] == 'delete': 
                            print(f"{qlf}{change['clusterTime'].as_datetime() - datetime.timedelta(hours=4):%b %d, %Y • %I:%M:%S %p} - database {change['operationType']}: {change['ns']['db']} - {change['ns']['coll']}")
                            continue
                        fullDocument = change['fullDocument']
                        objectID = list(fullDocument.values())[1]
                        collection = change['ns']['coll']
                        if collection == 'servers': 
                            name = 'name'
                            self.bot.lightningLogging[objectID] = fullDocument
                            lightningLogging[objectID] = fullDocument
                        elif collection == 'users': 
                            name = 'username'
                            self.bot.lightningUsers[objectID] = fullDocument
                            lightningUsers[objectID] = fullDocument
                        if change['operationType'] == 'update' and any([word in change['updateDescription']['updatedFields'].keys() for word in ('lastActive', 'lastOnline')]): continue
                        print(f'''{qlf}{change['clusterTime'].as_datetime() - datetime.timedelta(hours=4):%b %d, %Y • %I:%M:%S %p} - (database {change['operationType']} -- {change['ns']['db']} - {change['ns']['coll']}){f": {fullDocument[name]} - {', '.join([f' {k}' for k in change['updateDescription']['updatedFields'].keys()])}" if change['operationType'] == 'update' else ''}''')
            except Exception as e: 
                print(f'Tracking error: {e}')
                if str(e) == 'username': traceback.print_exc()

    @tasks.loop(hours = 6)
    async def summarize(self):
        global lightningUsers
        global lightningLogging
        global members
        try:
            print('Summarizing')
            started = datetime.datetime.now()
            rawStarted = datetime.datetime.now()
            if self.summarize.current_loop % 4 == 0:
                if self.summarize.current_loop == 0:
                    asyncio.create_task(self.synchronizeDatabase(True))
                    def initializeCheck(m): return m.author.id == self.bot.user.id and m.channel == self.imageLogChannel and m.content == 'Synchronized'
                    await bot.wait_for('message', check=initializeCheck) #Wait for bot to synchronize database
                else: asyncio.create_task(self.synchronizeDatabase())
                await self.bot.get_cog('Birthdays').updateBirthdays()
            for g in self.bot.guilds:
                started = datetime.datetime.now()
                try:
                    generalChannel, announcementsChannel, moderatorChannel = await database.CalculateGeneralChannel(g, True), await database.CalculateAnnouncementsChannel(g, True), await database.CalculateModeratorChannel(g, True)
                    print(f'{g.name}\n -general channel: {generalChannel}\n -announcements channel: {announcementsChannel}\n -moderator channel: {moderatorChannel}')
                except: pass
                for m in g.members:
                    memberStart = datetime.datetime.now()
                    updates = []
                    try:
                        for a in m.activities:
                            if a.type == discord.ActivityType.custom:
                                try:
                                    if {'e': None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), 'n': a.name} != {'e': self.bot.lightningUsers.get(m.id).get('customStatusHistory')[-1].get('emoji'), 'n': self.bot.lightningUsers.get(m.id).get('customStatusHistory')[-1].get('name')}:
                                        asyncio.create_task(database.AppendCustomStatusHistory(m, None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), a.name))
                                        updates.append('status')
                                except (AttributeError, discord.HTTPException, aiohttp.client_exceptions.ClientPayloadError): pass
                                except (TypeError, IndexError): 
                                    asyncio.create_task(database.AppendCustomStatusHistory(m, None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), a.name)) #If the customStatusHistory is empty, we create the first entry
                                    updates.append('status')
                    except Exception as e: print(f'Custom status error for {m.name}: {e}')
                    try:
                        if m.name != self.bot.lightningUsers.get(m.id).get('usernameHistory')[-1].get('name'): 
                            asyncio.create_task(database.AppendUsernameHistory(m))
                            updates.append('username')
                    except (AttributeError, discord.HTTPException, aiohttp.client_exceptions.ClientPayloadError): pass
                    except (TypeError, IndexError):
                        asyncio.create_task(database.AppendUsernameHistory(m))
                        updates.append('username')
                    except Exception as e: print(f'Username error for {m.name}: {e}')
                    try:
                        if str(m.avatar_url) != self.bot.lightningUsers.get(m.id).get('avatarHistory')[-1].get('discordURL'):
                            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not m.is_avatar_animated() else 'gif'))
                            await m.avatar_url_as(size=1024).save(savePath)
                            f = discord.File(savePath)
                            message = await self.imageLogChannel.send(file=f)
                            asyncio.create_task(database.AppendAvatarHistory(m, message.attachments[0].url))
                            if os.path.exists(savePath): os.remove(savePath)
                            updates.append('avatar')
                    except (AttributeError, discord.HTTPException, aiohttp.client_exceptions.ClientPayloadError): pass
                    except (TypeError, IndexError):
                        try:
                            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not m.is_avatar_animated() else 'gif'))
                            await m.avatar_url_as(size=1024).save(savePath)
                            f = discord.File(savePath)
                            message = await self.imageLogChannel.send(file=f)
                            asyncio.create_task(database.AppendAvatarHistory(m, message.attachments[0].url))
                            if os.path.exists(savePath): os.remove(savePath)
                            updates.append('avatar')
                        except discord.HTTPException: pass #Filesize is too large
                    except Exception as e: print(f'Avatar error for {m.name}: {e}')
                    #if len(updates) > 0: lightningUsers[m.id] = await database.GetUser(m) #Debating if we even need this line
                    if 'avatar' in updates: await asyncio.sleep((datetime.datetime.now() - memberStart).microseconds / 1000000)
                print(f'Member Management and attribute updates done in {(datetime.datetime.now() - started).seconds}s')
                started = datetime.datetime.now()
                for c in g.text_channels: 
                    try: self.pins[c.id] = [m.id for m in await c.pins()]
                    except discord.Forbidden: pass
                for c in g.categories:
                    try: self.categories[c.id] = c.channels
                    except discord.Forbidden: pass
                try: self.categories[g.id] = [c[1] for c in g.by_category() if c[0] is None]
                except discord.Forbidden: pass
                print(f'Channel management done in {(datetime.datetime.now() - started).seconds}s')
                started = datetime.datetime.now()
                try:
                    self.invites[str(g.id)] = (await g.invites())
                    try: self.invites[str(g.id)+"_vanity"] = (await g.vanity_invite())
                    except discord.HTTPException: pass
                except discord.Forbidden as e: print(f'Invite management error: Server {g.name}: {e.text}')
                except Exception as e: print(f'Invite management error: Server {g.name}\n{e}')
                print(f'Invite management done in {(datetime.datetime.now() - started).seconds}s')
            if self.summarize.current_loop % 4 == 0:
                if self.summarize.current_loop == 0:
                    started = datetime.datetime.now()   
                    asyncio.create_task(database.Verification(self.bot))
                    print(f'Full post-verification done in {(datetime.datetime.now() - started).seconds}s')
            started = datetime.datetime.now()                
            memberList = self.bot.get_all_members()
            await asyncio.gather(*[updateLastOnline(m, datetime.datetime.now()) for m in memberList if m.status != discord.Status.offline])               
            print(f'Status management done in {(datetime.datetime.now() - started).seconds}s')
            #self.bot.lightningLogging = lightningLogging
            lightningLogging = self.bot.lightningLogging
            lightningUsers = self.bot.lightningUsers
            await self.imageLogChannel.send('Completed')
        except Exception as e: 
            print('Summarize error: {}'.format(e))
            traceback.print_exc()
        print(f'Done summarizing: {(datetime.datetime.now() - rawStarted).seconds}s')

    async def synchronizeDatabase(self, notify=False):
        started = datetime.datetime.now()
        print('Synchronizing Database')
        global lightningLogging
        global lightningUsers
        async for s in await database.GetAllServers():
            self.bot.lightningLogging[s['server_id']] = s
            lightningLogging[s['server_id']] = s
        async for u in await database.GetAllUsers():
            self.bot.lightningUsers[u['user_id']] = u
            lightningUsers[u['user_id']] = u
        print(f'Database Synchronization done in {(datetime.datetime.now() - started).seconds}s')
        if notify: await self.imageLogChannel.send('Synchronized')

    @tasks.loop(hours=24)
    async def DeleteAttachments(self):
        print('Deleting attachments that are old')
        time = datetime.datetime.now()
        try:
            removal=[]
            outstandingTempFiles = os.listdir(tempDir)
            for server in self.bot.guilds:
                for channel in server.text_channels:
                    try:
                        path='Attachments/{}/{}'.format(server.id, channel.id)
                        for fl in os.listdir(path):
                            with open('{}/{}/{}/{}.txt'.format(indexes,server.id, channel.id, fl)) as f:
                                timestamp = datetime.datetime.strptime(list(enumerate(f))[0][1], '%b %d, %Y - %I:%M:%S %p')
                            if (datetime.datetime.utcnow() - timestamp).days > 365:
                                removal.append(path+fl)
                    except: pass
            for path in removal: 
                try: os.removedirs(path)
                except Exception as e: print(f'Attachment Deletion fail: {e}')
            for fl in outstandingTempFiles:
                try: shutil.rmtree((os.path.join(tempDir, fl)))
                except:
                    try: os.remove(os.path.join(tempDir, fl))
                    except Exception as e: print(f'Temp Attachment Deletion fail: {e}')
            print('Removed {} attachments in {} seconds'.format(len(removal) + len(outstandingTempFiles), (datetime.datetime.now() - time).seconds))
        except Exception as e: print('Fail: {}'.format(e))
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        '''[DISCORD API METHOD] Called when message is sent
        Unlike RicoBot, I don't need to spend over 1000 lines of code doing things here in [ON MESSAGE] due to the web dashboard :D'''
        await self.bot.wait_until_ready()
        await updateLastActive(message.author, datetime.datetime.now(), 'sent a message')
        if type(message.channel) is discord.DMChannel: return
        if message.type is discord.MessageType.pins_add: await self.pinAddLogging(message)
        if message.content == f'<@!{self.bot.user.id}>': await self.sendGuideMessage(message)
        await asyncio.gather(*[self.saveMessage(message), self.jumpLinkQuoteContext(message)])

    async def saveMessage(self, message: discord.Message):
        path = f'{indexes}/{message.guild.id}'
        try: os.makedirs(path)
        except FileExistsError: pass
        try:
            with open(f'{path}/{message.channel.id}.json', 'r+') as f: 
                indexData = json.load(f)
                indexData[message.id] = {'author0': message.author.id, 'timestamp0': message.created_at.isoformat(), 'content0': message.content if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<No content>"}
        except (FileNotFoundError, PermissionError): 
            indexData = {}
        indexData = json.dumps(indexData, indent=4)
        with open(f'{path}/{message.channel.id}.json', 'w+') as f:
            f.write(indexData)
        if message.author.bot: return
        if await database.GetImageLogPerms(message.guild) and len(message.attachments) > 0:
            path2 = 'Attachments/{}/{}/{}'.format(message.guild.id, message.channel.id, message.id)
            try: os.makedirs(path2)
            except FileExistsError: pass
            for a in message.attachments:
                if a.size / 1000000 < 8:
                    try: await a.save(path2+'/'+a.filename)
                    except discord.HTTPException: pass

    async def jumpLinkQuoteContext(self, message: discord.Message):
        try: enabled = self.bot.lightningLogging.get(message.guild.id).get('jumpContext')
        except AttributeError: return
        if enabled:
            words = message.content.split(' ')
            for w in words:
                if 'https://discordapp.com/channels/' in w: #This word is a hyperlink to a message
                    context = await self.bot.get_context(message)
                    messageConverter = commands.MessageConverter()
                    result = await messageConverter.convert(context, w)
                    if result is None: return
                    if len(result.embeds) == 0:
                        embed=discord.Embed(description=result.content)
                        embed.set_footer(text=f'{(result.created_at + datetime.timedelta(hours=timeZone(message.guild))):%b %d, %Y • %I:%M %p} {nameZone(message.guild)}')
                        embed.set_author(name=result.author.name,icon_url=result.author.avatar_url)
                        if len(result.attachments) > 0 and result.attachments[0].height is not None:
                            try: embed.set_image(url=result.attachments[0].url)
                            except: pass
                        return await message.channel.send(embed=embed)
                    else:
                        if result.embeds[0].footer.text is discord.Embed.Empty: result.embeds[0].set_footer(text=f'{(result.created_at + datetime.timedelta(hours=timeZone(message.guild))):%b %d, %Y - %I:%M: %p} {nameZone(message.guild)}')
                        if result.embeds[0].author.name is discord.Embed.Empty: result.embeds[0].set_author(name=result.author.name, icon_url=result.author.avatar_url)
                        return await message.channel.send(content=result.content,embed=result.embeds[0])

    async def pinAddLogging(self, message: discord.Message):
        received = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(message.guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        destination = logChannel(message.guild, 'message')
        if destination is None: return
        pinned = (await message.channel.pins())[0]
        embed=discord.Embed(title='📌Message was pinned',description='Pinned by: {} ({})\nAuthored by: {} ({})\nChannel: {} • [Jump to message]({})\nPrecise timestamp: {}'.format(message.author.mention, message.author.name, pinned.author.mention, pinned.author.name, pinned.channel.mention, pinned.jump_url, received),color=blue,timestamp=datetime.datetime.utcnow())
        embed.add_field(name='Message', value=pinned.content)
        embed.set_footer(text='Pinned message ID: {}'.format(pinned.id))
        await destination.send(embed=embed)
        try: self.pins[pinned.channel.id].append(pinned.id)
        except KeyError: self.pins[pinned.channel.id] = [pinned.id]

    async def sendGuideMessage(self, message: discord.Message):
        await message.channel.send(embed=discord.Embed(title=f'Quick Guide - {message.guild}', description=f'Yes, I am online! Ping: {round(bot.latency * 1000)}ms\n\n**Prefix:** `{self.bot.lightningLogging.get(message.guild.id).get("prefix")}`\n\nHave a question or a problem? Use the `ticket` command to open a support ticket with my developer', color=yellow))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        ej = payload.emoji
        global bot
        global grabbedSummaries
        u = self.bot.get_user(payload.user_id)
        if u.bot: return
        channel = self.bot.get_channel(payload.channel_id)
        if type(channel) is not discord.TextChannel: return
        try: message = await channel.fetch_message(payload.message_id)
        except: return
        user = self.bot.get_guild(channel.guild.id).get_member(payload.user_id)
        await updateLastActive(user, datetime.datetime.now(), 'added a reaction')
        if len(message.embeds) == 0: return
        if message.author.id != bot.get_guild(channel.guild.id).me.id: return
        e = message.embeds[0]
        f = e.footer.text
        try: fid = f[f.find(':')+2:]
        except: fid = str(message.id)
        oldReac = message.reactions
        if str(ej) == 'ℹ':
            if 'Server updated' in e.title:
                try: await message.clear_reactions()
                except discord.Forbidden: pass
                await message.edit(content='Embed will retract in 3 minutes',embed=await self.ServerInfo(message.guild, await message.guild.audit_logs(limit=None).flatten(), await message.guild.bans(), await message.guild.webhooks(), await message.guild.invites()))
            if 'Role was updated' in e.title:
                try: await message.clear_reactions()
                except discord.Forbidden: pass
                role = message.guild.get_role(int(fid))
                if role is None: return await message.edit(content='Unable to provide role information; it was probably deleted')
                await message.edit(content='Embed will retract in 3 minutes',embed=await self.RoleInfo(role, await role.guild.audit_logs(limit=None).flatten()))
            await asyncio.sleep(180)
            if message.embeds[0] != e:
                if 'React with' in e.title or 'event recaps' in e.title or 'Message was edited' in e.title or 'Channel was updated' in e.title:
                    await message.edit(content=None,embed=e)
                    await message.clear_reactions()
                    for r in oldReac: await message.add_reaction(r)
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
                    e.description='**{} total events**\nFrom {} {} to now\n\n'.format(len(summ.get('queue')), summ.get('lastUpdate').strftime("%b %d, %Y • %I:%M %p"), await database.GetNamezone(message.guild))
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
        if str(ej) == '📓':
            await message.clear_reactions()
            try: 
                queue = grabbedSummaries.get(str(message.id)).get('queue')
                sort = grabbedSummaries.get(str(message.id)).get('sorted')
            except AttributeError: 
                queue = await database.GetSummary(message.guild, message.id).get('queue')
                sort = 0
            embed = discord.Embed.from_dict(queue[0].get('embed'))
            template = discord.Embed(title='Server event recaps',description='Sort: Category' if sort == 0 else 'Sort: Timestamp',color=embed.color,timestamp=embed.timestamp)
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
            template = discord.Embed(title='Server event recaps',description='Sort: Category' if sort == 0 else 'Sort: Timestamp',color=embed.color,timestamp=embed.timestamp)
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

    def parseEdits(self, beforeWordList, afterWordList, findChanges=False):
        '''Returns truncated version of differences given before/after list of words
        -if findChanges is True, then one of the lists merely contains an additional word compared to the other one'''
        beforeC = "" #String that will be displayed in the embed - old content
        afterC = "" #String that will be displayed in the embed - new content
        beforeBooleans = [b in afterWordList for b in beforeWordList] #Used for determining placement when one list has more elements than the other; Falses will decrease the iterator
        afterBooleans = [a in beforeWordList for a in afterWordList]
        i = 0 #Iterator variable
        #The following code parses through both the old and new message in order to trim out what hasn't changed, which makes it much easier to see what's changed in long messages, and what makes Disguard edit logs so special
        while i < len(beforeWordList): #Loop through each word in the old message
            iteratorAtStart = i #This holds the value of the iterator at the start, and is used later
            if beforeWordList[i] not in afterWordList: #If the old word is not in the list of words in the new message...
                offset = len([b for b in beforeBooleans[:i] if not b]) #How many words aren't in the after list, up to the current iterator index i; used to determine offset
                if i > 2: 
                    beforeC += '...{} **{}**'.format(' '.join(beforeWordList[i - 2 : i]), beforeWordList[i]) #If it's the 3rd word or later, append three dots first
                    if findChanges: afterC += '...{}'.format(' '.join(afterWordList[i - 2 - offset : i - offset])) #If findChanges, add this context to the after String
                else: 
                    beforeC += '{} **{}**'.format(' '.join(beforeWordList[:i]), beforeWordList[i]) #Otherwise, add everything in the old message up to what's at the current iterator i
                    if findChanges: afterC += ' '.join(afterWordList[:i - offset]) #If applicable, add all words up to i to the after content string
                matchScanner = i + 1 #Set this value to one number above i; it will go through the rest of the old message to scan for more words that aren't in the new message
                altScanner = i - 1 #This is for the findChanges variable; for tracking through the new words list
                matchCount = 0 #How many words **are** in the new message
                matches=[] #Array of T/F depending on if word matches - if word matches, don't bold it
                #When this is done, there will be a list formed of booleans for each remaining word in the old words list, set based on if that word is in the new message
                while matchScanner < len(beforeWordList) and matchCount < 2: #Loop through the rest of the before words list as long as there are under two matches
                    matched = beforeWordList[matchScanner] in afterWordList #True if the current word in the old message is in the new message
                    if matched: matchCount += 1 #Append match count if a match is found
                    else: matchCount = 0 #Otherwise reset this because the parser checks for two identical words, then it breaks to trim the rest of the message until another difference is found
                    matches.append(matched)
                    matchScanner += 1
                confirmCount = 0 #Keeps track of how many matches have been found (this will always be <= the number of True in matches)
                for match in range(len(matches)): #Iterate through the generated list of booleans
                    if matches[match]: #If True (current word *is* in new message)...
                        confirmCount += 1
                        beforeC += ' {}'.format(beforeWordList[match + i + 1]) #Add this word (without bolding) to the result string
                    else: 
                        beforeC += ' **{}**'.format(beforeWordList[match + i + 1]) #Otherwise, add this word (with bolding) to the result string
                        altScanner += 1 #If a word has been removed then append this by 1
                    if findChanges:
                        try: afterC += ' {}'.format(afterWordList[match + altScanner + 1]) #Attempt to add the equivalent word (without bolding) to the result string
                        except IndexError:
                            if match + altScanner > i: afterC += ' {}'.format(' '.join(afterWordList[match + altScanner - 1:])) #If out of bounds occurs due to the end of the message, simply add the rest of the message
                    if confirmCount == len([m for m in matches if m]) and not findChanges: break #If all same word matches have been found, and findChanges is False, break out of this and move on to the next iteration of the **while** loop
                if matchScanner < len(beforeWordList): beforeC+= '... ' #If we aren't at the end of the word list, then add triple periods because the tail of the message will be truncated
                if altScanner < len(afterWordList) - 1 and findChanges: afterC += '... ' #Append triple periods if the remaining content is truncated
                i = matchScanner + 1 #Jump i ahead to the number after matchScanner because everything up to matchScanner has been parsed for differences already
            if i == iteratorAtStart: i += 1 #If no difference was found (i would equal iteratorAtStart), then simply iterate i by 1
        i=0 #Reset the iterator
        #The following code does the exact same thing as above, just to the new message content
        while i < len(afterWordList):
            iteratorAtStart = i
            if afterWordList[i] not in beforeWordList:
                offset = len([a for a in afterBooleans[:i] if not a])
                if i > 2: 
                    afterC += '...{} **{}**'.format(' '.join(afterWordList[i - 2 : i]), afterWordList[i])
                    if findChanges: beforeC += '...{}'.format(' '.join(beforeWordList[i - 2 - offset: i - offset]))
                else: 
                    afterC += '{} **{}**'.format(' '.join(afterWordList[:i]), afterWordList[i])
                    if findChanges: beforeC += ' '.join(beforeWordList[:i - offset])
                matchScanner = i + 1
                altScanner = i - 1
                matchCount = 0
                matches=[]
                while matchScanner < len(afterWordList) and matchCount < 2:
                    matched = afterWordList[matchScanner] in beforeWordList
                    if matched: matchCount += 1
                    else: matchCount = 0
                    matches.append(matched)
                    matchScanner += 1
                confirmCount = 0
                for match in range(len(matches)):
                    if matches[match]:
                        confirmCount += 1 
                        afterC += ' {}'.format(afterWordList[match + i + 1]) 
                    else: 
                        afterC += ' **{}**'.format(afterWordList[match + i + 1])
                        altScanner += 1
                    if findChanges: 
                        try: beforeC += ' {}'.format(beforeWordList[match + altScanner + 1])
                        except IndexError: 
                            if match + altScanner > i: beforeC += ' {}'.format(' '.join(beforeWordList[match + altScanner - 1:]))
                    if confirmCount == len([m for m in matches if m]) and not findChanges: break
                if matchScanner < len(afterWordList): afterC+='... '
                if altScanner < len(beforeWordList) - 1 and findChanges: beforeC += '... '
                i = matchScanner + 1
            if i == iteratorAtStart: i += 1
        return beforeC, afterC

    async def MessageEditHandler(self, before, after, timestamp, footerAppendum = ''):
        guild = after.guild
        author = after.author
        channel = after.channel
        c = logChannel(guild, 'message')
        utcTimestamp = timestamp - datetime.timedelta(hours=timeZone(guild))
        if c is None: return await updateLastActive(author, datetime.datetime.now(), 'edited a message') #Invalid log channel
        if after.id in self.pins.get(after.channel.id) and not after.pinned: #Message was unpinned
            eventMessage = [m for m in await after.channel.history(limit=5).flatten() if m.type is discord.MessageType.pins_add][0]
            embed=discord.Embed(title='🚫📌Message was unpinned',description=f'Unpinned by: {eventMessage.author.mention} ({eventMessage.author.name})\nAuthored by: {after.author.mention} ({after.author.name})\nChannel: {after.channel.mention} • [Jump to message]({after.jump_url})\nPrecise timestamp: {timestamp:%b %d, %Y • %I:%M:%S %p} {nameZone(guild)}', color=blue, timestamp=timestamp)
            embed.add_field(name='Message', value=after.content)
            embed.set_footer(text=f'Unpinned message ID: {after.id}')
            await c.send(embed=embed)
            return self.pins[channel.id].remove(after.id)
        if after.content.strip() == before.strip(): return await updateLastActive(author, datetime.datetime.now(), 'edited a message') #If the text before/after is the same, and after unpinned message log if applicable
        if any(w in before.strip() for w in ['attachments>', '<1 attachment:', 'embed>']): return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message')
        beforeWordList = before.split(" ") #A list of words in the old message
        afterWordList = after.content.split(" ") #A list of words in the new message
        beforeC, afterC = self.parseEdits(beforeWordList, afterWordList)
        if any([len(m) == 0 for m in [beforeC, afterC]]): beforeC, afterC = self.parseEdits(beforeWordList, afterWordList, True)
        if len(beforeC) >= 1024: beforeC = 'Message content too long to display in embed field'
        if len(afterC) >= 1024: afterC = 'Message content too long to display in embed field'
        embed = discord.Embed(title="📜✏ Message was edited (ℹ to expand details)", description=f'{self.loading} Finalyzing log', color=blue, timestamp=utcTimestamp)
        embed.set_footer(text=f'Message ID: {after.id} {footerAppendum}')
        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not author.is_avatar_animated() else 'gif'))
        try: await author.avatar_url_as(size=1024).save(savePath)
        except discord.HTTPException: pass
        f = discord.File(savePath)
        embed.set_thumbnail(url='attachment://{}'.format(f.filename))
        #embed.set_author(name=after.author.name, icon_url=f'attachment://{f.filename}')
        path = f'{indexes}/{after.guild.id}/{after.channel.id}.json'
        with open(path) as fl: #Open up index data to append the message edit history entry
            indexData = json.load(fl) #importing the index data from the filesystem
            number = len(indexData[str(after.id)].keys()) // 3 #This represents the suffix to the key names, because dicts need to have unique key names, and message edit history requires multiple entries
            indexData[str(after.id)].update({f'author{number}': after.author.id, f'timestamp{number}': datetime.datetime.utcnow().isoformat(), f'content{number}': after.content if len(after.content) > 0 else f"<{len(after.attachments)} attachment{'s' if len(after.attachments) > 1 else f':{after.attachments[0].filename}'}>" if len(after.attachments) > 0 else f"<{len(after.embeds)} embed>" if len(after.embeds) > 0 else "<No content>"})
            indexData = json.dumps(indexData, indent=4)
        try: 
            msg = await c.send(file=f,embed=embed)
            await msg.add_reaction('ℹ')
        except discord.HTTPException: return await c.send('Message edit log error')
        with open(path, 'w+') as fl:
            fl.write(indexData) #push the changes to the json file
        embed.description=f'👤: {author.mention}\n{self.hashtag}: {channel.mention} • [Jump to message]({after.jump_url})\n🕰: {timestamp:%b %d, %Y • %I:%M:%S %p} {nameZone(guild)}'
        embed.add_field(name='Before • Hover for full message', value=f"[{beforeC if len(beforeC) > 0 else '<Quick parser found no new content; ℹ to see full changes>'}]({msg.jump_url} '{before.strip()}')",inline=False)
        embed.add_field(name='After • Hover for full message', value=f"[{afterC if len(afterC) > 0 else '<Quick parser found no new content; ℹ to see full changes>'}]({msg.jump_url} '{after.content.strip()}')",inline=False)
        if len(embed.fields[0].value) > 1024: embed.set_field_at(0, name='Before',value=beforeC if len(beforeC) in range(0, 1024) else '<Content is too long to be displayed>', inline=False)
        if len(embed.fields[1].value) > 1024: embed.set_field_at(1, name='After',value=afterC if len(afterC) in range(0, 1024) else '<Content is too long to be displayed>', inline=False)
        await msg.edit(embed=embed)
        await VerifyLightningLogs(msg, 'message')
        if os.path.exists(savePath): os.remove(savePath)
        oldEmbed=copy.deepcopy(embed)
        await updateLastActive(author, datetime.datetime.now(), 'edited a message')
        while True:
            def iCheck(r, u): return str(r) == 'ℹ' and r.message.id == msg.id and not u.bot
            result = await self.bot.wait_for('reaction_add',check=iCheck)
            authorID = result[1].id
            embed.description += '\n\nNAVIGATION\n⬅: Go back to compressed view\nℹ: Full edited message\n📜: Message edit history\n🗒: Message in context'
            while True:
                if len(embed.author.name) < 1: embed.set_author(icon_url=result[1].avatar_url, name=f'{result[1].name} - Navigating')
                def optionsCheck(r, u): return str(r) in ['ℹ', '⬅', '📜', '🗒'] and r.message.id == msg.id and u.id == authorID
                if not result:
                    try: result = await self.bot.wait_for('reaction_add',check=optionsCheck, timeout=180)
                    except asyncio.TimeoutError: result = ['⬅']
                await msg.clear_reactions()
                if str(result[0]) == 'ℹ':
                    beforeParsed = [f'**{word}**' if word not in afterWordList else word for word in beforeWordList]
                    afterParsed = [f'**{word}**' if word not in beforeWordList else word for word in afterWordList]
                    embed.set_field_at(0, name='Before', value=' '.join(beforeParsed), inline=False)
                    embed.set_field_at(1, name='After', value=' '.join(afterParsed), inline=False)
                    embed.description=embed.description[:embed.description.find(nameZone(guild)) + len(nameZone(guild))] + f'\n\nNAVIGATION\n{qlf}⬅: Go back to compressed view\n> **ℹ: Full edited message**\n{qlf}📜: Message edit history\n{qlf}🗒: Message in context'
                    await msg.edit(embed=embed)
                    for r in ['⬅', '📜', '🗒']: await msg.add_reaction(r)
                elif str(result[0]) == '📜': 
                    try:
                        await msg.clear_reactions()
                        embed.clear_fields()
                        embed.description=embed.description[:embed.description.find(nameZone(guild)) + len(nameZone(guild))] + f'\n\nNAVIGATION\n{qlf}⬅: Go back to compressed view\n{qlf}ℹ: Full edited message\n> **📜: Message edit history**\n{qlf}🗒: Message in context'
                        with open(f'{indexes}/{guild.id}/{channel.id}.json', 'r+') as f:
                            indexData = json.load(f)
                            currentMessage = indexData[str(after.id)]
                            enum = list(enumerate(currentMessage.values()))
                            def makeHistory(): #This will create groups of 4 from enum; since 4 lines represent the file data for indexes
                                for i in range(0, len(enum), 3): yield enum[i:i+3]
                            entries = list(makeHistory()) #This will always have a length of 2 or more
                        for i, entry in enumerate(entries): 
                            embed.add_field(name=f'{(datetime.datetime.fromisoformat(entry[1][1]) + datetime.timedelta(hours=timeZone(guild))):%b %d, %Y • %I:%M:%S %p} {nameZone(guild)}{" (Created)" if i == 0 else " (Current)" if i == len(entries) - 1 else ""}',value=entry[-1][1], inline=False)
                        await msg.edit(embed=embed)
                        for r in ['⬅', 'ℹ', '🗒']: await msg.add_reaction(r)
                    except (discord.Forbidden, discord.HTTPException) as e:
                        embed.description+=f'\n\n⚠ Error parsing message edit history: {e}'
                        await msg.edit(embed=embed)
                        await asyncio.sleep(5)  
                elif str(result[0]) == '🗒':
                    try:
                        embed.clear_fields()
                        embed.description=embed.description[:embed.description.find(nameZone(guild)) + len(nameZone(guild))] + f'\n\nNAVIGATION\n{qlf}⬅: Go back to compressed view\n{qlf}ℹ: Full edited message\n{qlf}📜: Message edit history\n> **🗒: Message in context**'
                        messagesBefore = list(reversed(await after.channel.history(limit=6, before=after).flatten()))
                        messagesAfter = await after.channel.history(limit=6, after=after, oldest_first=True).flatten()
                        combinedMessages = messagesBefore + [after] + messagesAfter
                        combinedLength = sum(len(m.content) for m in combinedMessages)
                        if combinedLength > 1850: combinedMessageContent = [m.content[:1850 // len(combinedMessages)] for m in combinedMessages]
                        else: combinedMessageContent = [f"<{len(m.attachments)} attachment{'s' if len(m.attachments) > 1 else ''}>" if len(m.attachments) > 0 else f"<{len(m.embeds)} embed>" if len(m.embeds) > 0 else m.content if len(m.content) > 0 else "<Error retrieving content>" for m in combinedMessages]
                        for m in range(len(combinedMessages)): embed.add_field(name=f'**{combinedMessages[m].author.name}** • {(combinedMessages[m].created_at + datetime.timedelta(hours=timeZone(guild))):%b %d, %Y • %I:%M:%S %p} {nameZone(guild)}',value=combinedMessageContent[m] if combinedMessages[m].id != after.id else f'**[{combinedMessageContent[m]}]({combinedMessages[m].jump_url})**', inline=False)
                        await msg.edit(embed=embed)
                        for r in ['⬅', 'ℹ', '📜']: await msg.add_reaction(r)
                    except (discord.Forbidden, discord.HTTPException) as e:
                        embed.description+=f'\n\n⚠ Error retrieving messages: {e}'
                        await msg.edit(embed=embed)
                        await asyncio.sleep(5)
                if str(result[0]) not in ['🗒', 'ℹ', '📜']:
                    await msg.clear_reactions()
                    await msg.edit(embed=oldEmbed)
                    embed = copy.deepcopy(oldEmbed)
                    await msg.add_reaction('ℹ')
                    break
                result = None

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        '''[DISCORD API METHOD] Called when message is edited'''
        if not after.guild: return #We don't deal with DMs
        received = datetime.datetime.utcnow() + datetime.timedelta(hours=timeZone(after.guild)) #Timestamp of receiving the message edit event
        g = after.guild
        if not logEnabled(g, 'message'): return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message') #If the message edit log module is not enabled, return
        try:
            if not logExclusions(after.channel, after.author): return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message') #Check the exclusion settings
        except: return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message')
        if after.author.bot: return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message')
        await self.MessageEditHandler(before.content, after, received)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        '''[DISCORD API METHOD] Called when raw message is edited'''
        try: g = self.bot.get_guild(int(payload.data.get('guild_id'))) #Get the server of the edited message, return if not found (DMs; we don't track DM edits)
        except: return #We don't deal with DMs
        received = datetime.datetime.utcnow() + datetime.timedelta(hours=timeZone(g)) #Timestamp of receiving the message edit event
        footerAppendum = ''
        before = ''
        if payload.cached_message: return #If the message is stored internally (created after bot restart), it will get dealt with above, where searching the filesystem (which takes time, and stress on the SSD) isn't necessary
        #self.rawMessages[payload.message_id] = payload.data #Save message data to dict for later use
        channel = self.bot.get_channel(int(payload.data.get('channel_id'))) #Get the channel of the edited message
        try: after = await channel.fetch_message(payload.message_id) #Get the message object, and return if not found
        except discord.NotFound: return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message')
        except discord.Forbidden: 
            print('{} lacks permissions for message edit for some reason'.format(bot.get_guild(int(payload.data.get('guild_id'))).name))
            return
        author = g.get_member(after.author.id) #Get the member of the edited message, and if not found, return (this should always work, and if not, then it isn't a server and we don't need to proceed)
        if not logEnabled(g, 'message'): return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message') #If the message edit log module is not enabled, return
        try:
            if not logExclusions(after.channel, author): return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message') #Check the exclusion settings
        except: return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message')
        c = logChannel(g, 'message')
        if c is None: return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message') #Invalid log channel
        try:
            path = f'{indexes}/{after.guild.id}/{after.channel.id}.json'
            with open(path) as f:
                indexData = json.load(f)
                currentMessage = indexData[str(after.id)]
                before = currentMessage[f'content{len(currentMessage.keys()) // 3 - 1}']
        except FileNotFoundError as e: before = f'<Data retrieval error: {e}>' #If we can't find the file, then we say this
        except IndexError: before = after.content #Author is bot, and indexes aren't kept for bots; keep this for pins only
        if after.author.bot: return await updateLastActive(after.author, datetime.datetime.now(), 'edited a message') #If this were earlier, it would return before catching unpinned messages
        try: await self.MessageEditHandler(before, after, received, footerAppendum)
        except UnboundLocalError: await self.MessageEditHandler('<Data retrieval error>', after, received, footerAppendum) #If before doesn't exist

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        '''[DISCORD API METHOD] Called when message is deleted (RAW CONTENT)'''
        g = bot.get_guild(payload.guild_id)
        if not g: return #We don't deal with DM message deletions
        received = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(g.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        if serverPurge.get(payload.guild_id): return
        if not logEnabled(g, 'message'): return
        try: 
            message = payload.cached_message
            if message.type != discord.MessageType.default: return
        except AttributeError: message = None
        c = logChannel(g, 'message')
        if payload.message_id in self.pauseDelete: return self.pauseDelete.remove(payload.message_id)
        embed=discord.Embed(title="📜❌ Message was deleted",description='',timestamp=datetime.datetime.utcnow(),color=red)
        embed.set_footer(text=f'Message ID: {payload.message_id}')
        attachments = [] #List of files sent with this message
        path = 'Attachments/{}/{}/{}'.format(payload.guild_id,payload.channel_id, payload.message_id) #Where to retrieve message attachments from
        try:
            for directory in os.listdir(path):
                f = discord.File('{}/{}'.format(path, directory))
                attachments.append(f)
                if any([ext in directory.lower() for ext in ['.png', '.jpeg', '.jpg', '.gif', '.webp']]): embed.set_image(url='attachment://{}'.format(f.filename))
        except OSError: pass
        if message is not None:
            author = self.bot.get_user(message.author.id)
            channel, created, content = message.channel, message.created_at, message.content
        else:
            try:
                filePath = f'{indexes}/{payload.guild_id}/{payload.channel_id}.json'
                with open(filePath) as fl:
                    indexData = json.load(fl)
                    currentMessage = indexData[str(payload.message_id)]
                    authorID, created, content = tuple(currentMessage.values())[-3:]
                    author, channel, created = self.bot.get_user(authorID), self.bot.get_channel(payload.channel_id), datetime.datetime.fromisoformat(created)
                    indexData.pop(str(payload.message_id))
                with open(filePath, 'w+') as fl:
                    fl.write(json.dumps(indexData, indent=4))
            except (FileNotFoundError, IndexError):
                try: channel = channel.mention
                except: channel = payload.channel_id
                embed.description=f'Channel: {channel}\nUnable to provide information beyond what is here; this message was sent before my last restart, and I am unable to locate the indexed file locally to retrieve more information'
                return await c.send(embed=embed)      
        if datetime.datetime.utcnow() > created: #This makes negative time rather than posting some super weird timestamps. No, negative time doesn't exist but it makes more sense than what this would do otherwise
            mult = 1
            deletedAfter = datetime.datetime.utcnow() - created
        else:
            mult = -1
            deletedAfter = created - datetime.datetime.utcnow()
        hours, minutes, seconds = deletedAfter.seconds // 3600, (deletedAfter.seconds // 60) % 60, deletedAfter.seconds - (deletedAfter.seconds // 3600) * 3600 - ((deletedAfter.seconds // 60) % 60)*60
        times = [seconds*mult, minutes*mult, hours*mult, deletedAfter.days*mult] #This is the list of units for the deletedAfter
        units = ['second', 'minute', 'hour', 'day'] #Full words, but we'll only be using the first letter in the final result
        display = [] #This will be joined in the embed to combine the units and values
        for i in range(len(times)):
            if times[i] != 0: display.append('{}{}'.format(times[i], units[i][0])) #The if statement will not append units if everything to the right is 0 (such as 5 seconds later, where m/h/d would all be 0)
        if len(display) == 0: display.append(f'{deletedAfter.microseconds // 1000}ms')
        try: memberObject = g.get_member(author.id)
        except AttributeError: return
        try: 
            if author.bot or not logExclusions(channel, memberObject): return
        except: pass
        try: messageAfter = (await channel.history(limit=1, after=created, oldest_first=True).flatten())[0] #The message directly after the deleted one, if this is N/A the embed will have no hyperlink for this
        except IndexError: messageAfter = ''
        try: messageBefore = (await channel.history(limit=1, before=created).flatten())[0] #The message directly before the deleted one
        except IndexError: messageBefore = ''
        created += datetime.timedelta(hours=self.bot.lightningLogging.get(g.id).get('offset'))
        #embed.description='Author: {0} ({1})\nChannel: {2} • Jump to message [before]({3} \'{4}\') or [after]({5} \'{6}\') this one\nPosted: {7} {8}\nDeleted: {9} {8} ({10} later)'.format(author.mention if memberObject is not None else author.name, author.name if memberObject is not None else 'No longer in this server', channel.mention, messageBefore.jump_url if messageBefore != '' else '', messageBefore.content if messageBefore != '' else '', messageAfter.jump_url if messageAfter != '' else '', messageAfter.content if messageAfter != '' else '', created.strftime("%b %d, %Y • %I:%M:%S %p"), nameZone(bot.get_guild(payload.guild_id)), received, ' '.join(reversed(display)))
        embed.description=f"👤: {author.mention}{ '(No longer in this server)' if not memberObject else ''}\n{self.hashtag}: {channel.mention} • Jump to message [before]({messageBefore.jump_url if messageBefore else ''} \'{messageBefore.content if messageBefore else ''}\') or [after]({messageAfter.jump_url if messageAfter else ''} \'{messageAfter.content if messageAfter else ''}\') this one\n{self.sendMessage}: {created:%b %d, %Y • %I:%M:%S %p} {nameZone(g)}\n{self.trashcan}: {received} {nameZone(g)} ({' '.join(reversed(display))} later)"
        if message: embed.add_field(name="Content",value=message.content[:1024] if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f': {message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<Error retrieving content>")
        else: embed.add_field(name='Content',value='<No content>' if len(content) < 1 else content[:1024])
        for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            if ext in content.lower():
                if '://' in content:
                    url = content[message.content.find('http'):content.find(ext)+len(ext)+1]
                    embed.set_image(url=url)
        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not author.is_avatar_animated() else 'gif'))
        try: await author.avatar_url_as(size=1024).save(savePath)
        except discord.HTTPException: pass
        f = discord.File(savePath)
        attachments.append(f)
        embed.set_thumbnail(url='attachment://{}'.format(f.filename))
        embed.set_author(name=author.name, icon_url=f'attachment://{f.filename}')
        sendContent=None
        if readPerms(g, "message"):
            try:
                async for log in g.audit_logs(limit=1):
                    if log.action in (discord.AuditLogAction.message_delete, discord.AuditLogAction.message_bulk_delete) and (datetime.datetime.utcnow() - log.created_at).seconds < 20 and log.target.id in (author.id, channel.id) and log.user != author:
                        embed.description+=f'\n{self.trashcan}👮‍♂️: {log.user.mention} ({log.user.name})'
                        await updateLastActive(log.user, datetime.datetime.now(), 'deleted a message')
                    else: await updateLastActive(author, datetime.datetime.now(), 'deleted a message')
            except discord.Forbidden:
                sendContent="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
        if sendContent is None: 
            if random.randint(1, 100) == 1: sendContent='ℹProtip: Hover over the **before** or **after** message hyperlink to preview the content of the linked message' #1% chance of the protip popping up
        try: msg = await c.send(content=sendContent,embed=embed,files=attachments)
        except: msg = await c.send(content='An attachment to this message is too big to send',embed=embed)
        if os.path.exists(savePath): os.remove(savePath)
        await VerifyLightningLogs(msg, 'message')

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is created'''
        content=None
        savePath = None
        received = (channel.created_at + datetime.timedelta(hours=self.bot.lightningLogging.get(channel.guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        f=None
        if logEnabled(channel.guild, "channel"):
            keytypes = {discord.Member: '👤', discord.Role: '🚩'}
            embed=discord.Embed(title=f'{self.channelKeys.get(channel.type[0])}{self.greenPlus}{channel.type[0][0].upper() + channel.type[0][1:]} Channel was created', description=f'{self.channelKeys[channel.type[0]]}Channel: {f"{channel.mention} ({channel.name})" if channel.type[0] == "text" else channel.name}', color=green, timestamp=datetime.datetime.utcnow())
            if readPerms(channel.guild, "channel"):
                try:
                    log = (await channel.guild.audit_logs(limit=1).flatten())[0]
                    if log.action == discord.AuditLogAction.channel_create:
                        embed.description+=f'\n👮‍♂️Created by: {log.user.mention} ({log.user.name})' + (f' because "{log.reason}"' if log.reason is not None else '')
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        embed.set_thumbnail(url=f'attachment://{f.filename}')
                        await updateLastActive(log.user, datetime.datetime.now(), 'created a channel')
                except discord.Forbidden: content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
            defaultRead = channel.overwrites_for(channel.guild.default_role).read_messages
            if defaultRead is not None and not defaultRead: 
                accessible = [o[0] for o in list(iter(channel.overwrites.items())) if o[1].read_messages]
                unaccessible = [r for r in channel.guild.roles if r not in accessible]
                unaccessibleRoles = [o for o in unaccessible if type(o) is discord.Role]
            else:
                unaccessible = [o[0] for o in list(iter(channel.overwrites.items())) if not o[1].read_messages]
                unaccessibleRoles = [o for o in unaccessible if type(o) is discord.Role]
                accessible = [r for r in channel.guild.roles if r not in unaccessibleRoles]
            unaccessibleMembers = [m for m in channel.guild.members if not channel.permissions_for(m).read_messages]
            accessibleRoles = [o for o in accessible if type(o) is discord.Role]
            accessibleMembers = [m for m in channel.guild.members if channel.permissions_for(m).read_messages]
            embed.set_footer(text=f'Channel ID: {channel.id}')
            msg = await logChannel(channel.guild, "channel").send(content=content,embed=embed, file=f)
            memberAccessibleNewline = ' ' if len(accessibleMembers) > 20 else newline
            memberUnaccessibleNewline = ' ' if len(unaccessibleMembers) > 20 else newline
            roleAccessibleNewline = ' ' if len(accessibleRoles) > 20 else newline
            roleUnaccessibleNewline = ' ' if len(unaccessibleRoles) > 20 else newline
            accessibleTail = f'ROLES\n{roleAccessibleNewline.join([f"🚩 {r.name}" for r in accessibleRoles])}\n\nMEMBERS\n{memberAccessibleNewline.join([f"👤 {m.name}" for m in accessibleMembers])}'
            unaccessibleTail = f'ROLES\n{roleUnaccessibleNewline.join([f"🚩 {r.name}" for r in unaccessibleRoles])}\n\nMEMBERS\n{memberUnaccessibleNewline.join([f"👤 {m.name}" for m in unaccessibleMembers])}'
            if channel.overwrites_for(channel.guild.default_role).read_messages is not False: tempAccessibleString = f'''\n[🔓Accessible to: **Everyone by default**]({msg.jump_url} '{accessibleTail}')'''
            else:
                if sum(len(obj.name) for obj in accessible) > 32 or len(accessible) == 0: tempAccessibleString = f'''\n[🔓Accessible to: {len(accessibleRoles)} roles ({len(accessibleMembers)} members)]({msg.jump_url} '{accessibleTail}')'''
                else: tempAccessibleString = f'''\n[🔓Accessible to: {" • ".join([f'{keytypes.get(type(o))}{o.name}' for o in accessible])}]({msg.jump_url} '{accessibleTail}')'''
            if len(unaccessible) > 0: #At least one member or role can't access this channel by default
                if sum(len(obj.name) for obj in unaccessible) > 28: tempUnaccessibleString = f'''\n[🔒Not accessible to: {len(unaccessibleRoles)} roles ({len(unaccessibleMembers)} members)]({msg.jump_url} '{unaccessibleTail}')'''
                else: tempUnaccessibleString = f'''\n[🔒Not accessible to: {" • ".join([f'{keytypes.get(type(o))}{o.name}' for o in unaccessible])}]({msg.jump_url} '{unaccessibleTail}')'''
            else: tempUnaccessibleString = ''
            if len(tempAccessibleString) + len(tempUnaccessibleString) > 1900:
                trimmedAccessibleString = f"\n{tempAccessibleString[tempAccessibleString.find('[')+1:tempAccessibleString.find(']')]}"
                trimmedUnaccessibleString = f"\n{tempUnaccessibleString[tempUnaccessibleString.find('[')+1:tempUnaccessibleString.find(']')]}"
                if len(tempAccessibleString) + len(trimmedUnaccessibleString) < 1900: embed.description+=f'{tempAccessibleString}{trimmedUnaccessibleString}'
                elif len(trimmedAccessibleString) + len(tempUnaccessibleString) < 1900: embed.description+=f'{trimmedAccessibleString}{tempUnaccessibleString}'
                elif len(trimmedAccessibleString) + len(trimmedUnaccessibleString) < 1900: embed.description+=f'{trimmedAccessibleString}{trimmedUnaccessibleString}'
            else: embed.description+=f'{tempAccessibleString}{tempUnaccessibleString}'
            embed.description+=f'\n🕰Precise timestamp: {received} {nameZone(channel.guild)}'
            if channel.type[0] != 'category':
                channelList = channel.category.channels if channel.category is not None else [c for c in channel.guild.channels if c.category is None]
                cIndexes = (channelList.index(channel) - 3 if channelList.index(channel) >= 3 else 0, channelList.index(channel) + 4 if channelList.index(channel) + 4 < len(channelList) else len(channelList))
                embed.add_field(name="Category Tree",value=f'''📁{channel.category}\n{f"> [...Hover to view {len(channelList[:cIndexes[0]])} more channel{'s' if len(channelList[:cIndexes[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[:cIndexes[0]])}'){newline}" if cIndexes[0] > 0 else ""}{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList[cIndexes[0]:cIndexes[1]]])}{f"{newline}[Hover to view {len(channelList[cIndexes[1]:])} more channel{'s' if len(channelList[cIndexes:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[cIndexes[1]:])}')" if cIndexes[1] < len(channelList) else ""}''')
            await msg.edit(embed=embed)
            await VerifyLightningLogs(msg, 'channel')
            try:
                if os.path.exists(savePath): os.remove(savePath)
            except: pass
        try:
            if channel.category is not None: self.categories[channel.category.id] = channel.category.channels
            else: self.categories[channel.guild.id] = [c[1] for c in channel.guild.by_category() if c[0] is None]
        except discord.Forbidden: pass
        if type(channel) is discord.TextChannel:
            self.pins[channel.id] = []
            asyncio.create_task(database.VerifyServer(channel.guild, bot))

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is updated'''
        received = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(before.guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        f = None
        if logEnabled(before.guild, "channel"):
            content=None
            savePath = None
            embed=discord.Embed(title=f'{self.channelKeys.get(after.type[0])}✏{after.type[0][0].upper() + after.type[0][1:]} Channel was updated', description=f'{self.channelKeys[after.type[0]]}Channel: {f"{after.mention} ({after.name})" if after.type[0] == "text" else after.name}', color=blue, timestamp=datetime.datetime.utcnow())
            embed.description+=f' (Press ℹ to view channel details)'
            reactions = ['ℹ']
            if readPerms(before.guild, "channel"):
                try:
                    log = (await before.guild.audit_logs(limit=1).flatten())[0]
                    if log.action == discord.AuditLogAction.channel_update:
                        if log.user.id == self.bot.user.id: return
                        embed.description+=f'\n👮‍♂️Updated by: {log.user.mention} ({log.user.name})' + (f' because "{log.reason}"' if log.reason is not None else '')
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        embed.set_thumbnail(url=f'attachment://{f.filename}')
                        await updateLastActive(log.user, datetime.datetime.now(), 'edited a channel')
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`\n"
            embed.set_footer(text=f'Channel ID: {before.id}')
            #print(before.category.channels.index(before), after.category.channels.index(before), [c.name for c in before.category.channels], [c.name for c in after.category.channels])
            if before.category == after.category != None:
                bc = self.categories.get(before.category.id)
                if bc.index(before) != after.category.channels.index(before):
                    indexes = [] #Channel, before index, after index
                    for i in range(len(before.category.channels)): indexes.append({'before': bc.index(before.category.channels[i]), 'after': after.category.channels.index(before.category.channels[i]), 'channel': after.category.channels[i]})
                    embed.add_field(name='Channel position changed [BETA]',value=f'''📁{before.category.name}\n{newline.join([f'{self.channelKeys.get(indexes[c].get("channel").type[0])}' + ('__**' if indexes[c].get('channel').id == before.id else '') + f'{indexes[c].get("channel").name} ' + ('**__' if indexes[c].get('channel').id == before.id else '') + ('↩' if abs(indexes[c].get('before') - indexes[c].get('after')) > 1 else '⬆' if indexes[c].get('before') > indexes[c].get('after') else '⬇' if indexes[c].get('before') < indexes[c].get('after') else '') + (f'{newline}~~{self.channelKeys.get(before.type[0])}{before.name}~~❌' if bc.index(before) == c else '') for c in range(len(indexes))])}''')
                    self.categories[before.category.id] = after.category.channels
            if before.overwrites != after.overwrites:
                embed.add_field(name='Permission overwrites updated',value='Manually react 🇵 to show/hide') #The rest of this code is later because we need a message link to the current message
            if before.name != after.name: 
                embed.add_field(name="Old Name",value=before.name)
                embed.add_field(name="New Name",value=after.name)
            if type(before) is discord.TextChannel:
                beforeTopic = before.topic if before.topic is not None and len(before.topic) > 0 else "<No topic>"
                afterTopic = after.topic if after.topic is not None and len(after.topic) > 0 else "<No topic>"
                if beforeTopic != afterTopic:
                    embed.add_field(name="Old Description",value=beforeTopic)
                    embed.add_field(name="New Description",value=afterTopic)
                if before.is_nsfw() != after.is_nsfw():
                    embed.add_field(name="Old NSFW",value=before.is_nsfw())
                    embed.add_field(name="New NSFW",value=after.is_nsfw())
                if before.slowmode_delay != after.slowmode_delay:
                    delays = [[before.slowmode_delay, 'second'], [after.slowmode_delay, 'second']]
                    for d in delays:
                        if d[0] is not None and d[0] >= 60:
                            d[0] //= 60
                            d[1] = 'minute'
                            if d[0] >= 60:
                                d[0] //= 60
                                d[1] = 'hour'
                    embed.add_field(name='Old Slowmode',value=f'{delays[0][0]} {delays[0][1]}{"s" if delays[0][0] != 1 else ""}' if before.slowmode_delay > 0 else '<Disabled>')
                    embed.add_field(name='New Slowmode',value=f'{delays[1][0]} {delays[1][1]}{"s" if delays[1][0] != 1 else ""}' if after.slowmode_delay > 0 else '<Disabled>')
            elif type(before) is discord.VoiceChannel:
                if before.bitrate != after.bitrate:
                    embed.add_field(name="Old Bitrate",value=f'{before.bitrate // 1000} kbps')
                    embed.add_field(name="New Bitrate",value=f'{after.bitrate // 1000} kbps')
                if before.user_limit != after.user_limit:
                    embed.add_field(name="Old User Limit",value=before.user_limit)
                    embed.add_field(name="New User Limit",value=after.user_limit)
            if type(before) is not discord.CategoryChannel and before.category != after.category:
                embed.add_field(name='Old Category', value='Old')
                embed.add_field(name='New Category', value='New')
            if len(embed.fields) > 0:
                message = await logChannel(before.guild, "channel").send(content=content,embed=embed)
                if type(before) is not discord.CategoryChannel and before.category != after.category:
                    oldChannelList = self.categories.get(before.category.id) if before.category is not None else self.categories.get(before.guild.id)
                    newChannelList = after.category.channels if after.category is not None else [c[1] for c in after.guild.by_category() if c[0] is None]
                    oldIndexes = (oldChannelList.index(after) - 3 if oldChannelList.index(after) >= 3 else 0, oldChannelList.index(after) + 4 if oldChannelList.index(after) + 4 < len(oldChannelList) else len(oldChannelList))
                    newIndexes = (newChannelList.index(after) - 3 if newChannelList.index(after) >= 3 else 0, newChannelList.index(after) + 4 if newChannelList.index(after) + 4 < len(newChannelList) else len(newChannelList))
                    for i, field in enumerate(embed.fields):
                        if field.name == 'Old Category':
                            embed.set_field_at(i, name="Old Category",value=f'''📁{before.category}\n{f"> [...Hover to view {len(oldChannelList[:oldIndexes[0]])} more channel{'s' if len(oldChannelList[:oldIndexes[0]]) != 1 else ''}]({message.jump_url} '{newlineQuote.join(chan.name for chan in oldChannelList[:oldIndexes[0]])}'){newline}" if oldIndexes[0] > 0 else ""}{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in oldChannelList[oldIndexes[0]:oldIndexes[1]]])}{f"{newline}> [Hover to view {len(oldChannelList[oldIndexes[1]:])} more channel{'s' if len(oldChannelList[oldIndexes[1]:]) != 1 else ''}...]({message.jump_url} '{newlineQuote.join(chan.name for chan in oldChannelList[oldIndexes[1]:])}')" if oldIndexes[1] < len(oldChannelList) else ""}''')
                            embed.set_field_at(i + 1, name="New Category",value=f'''📁{after.category}\n{f"> [...Hover to view {len(newChannelList[:newIndexes[0]])} more channel{'s' if len(newChannelList[:newIndexes[0]]) != 1 else ''}]({message.jump_url} '{newlineQuote.join(chan.name for chan in newChannelList[:newIndexes[0]])}'){newline}" if newIndexes[0] > 0 else ""}{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in newChannelList[newIndexes[0]:newIndexes[1]]])}{f"{newline}> [Hover to view {len(newChannelList[newIndexes[1]:])} more channel{'s' if len(newChannelList[oldIndexes[1]:]) != 1 else ''}...]({message.jump_url} '{newlineQuote.join(chan.name for chan in newChannelList[newIndexes[1]:])}')" if newIndexes[1] < len(newChannelList) else ""}''')
                            break
                if before.overwrites != after.overwrites:
                    b4 = {} #Before permissions
                    af = {} #After permissions
                    temp=[]
                    english = {True: '✔', None: '➖', False: '✖'} #Symbols becuase True, False, None is confusing
                    classification = {discord.Role: '🚩', discord.Member: '👤'}
                    for k,v in before.overwrites.items(): b4.update({k: dict(iter(v))})
                    for k,v in after.overwrites.items(): af.update({k: dict(iter(v))})
                    for k,v in af.items():
                        if before.overwrites_for(k) != after.overwrites_for(k): temp.append('{}{:-<53s}'.format(classification.get(type(k)), k.name))
                        for kk,vv in v.items():
                            if b4.get(k) is None: #for example, a new overwrite for role/member was created
                                for kkk in list(v.keys()):
                                    b4[k] = {kkk: None}
                            if not set({kk: vv}.items()).issubset(b4.get(k).items()):
                                string2 = '{0:^3}'.format(english.get(vv)) #Set these to 15 if all else fails and increase now/prev spacing
                                temp.append('     {0:<50} |{1:>8}{2:>{diff}}{3:>10}'.format(f'{permissionKeys.get(kk)}:', string2, '|', english.get(b4.get(k).get(kk)), diff=4 if str(self.whiteMinus) in string2 else 5))
                    self.permissionStrings[message.id] = '```{0:<56}|{1:^13}|{2:^20}\n{3}```'.format('Permission overwrites updated', 'Now', 'Previously', '\n'.join(temp))
                    for f in range(len(embed.fields)):
                        if 'Permission overwrites' in embed.fields[f].name: embed.set_field_at(f, name='**Permission overwrites updated**', value=f'''[Use 🇵 to toggle details • Hover for preview]({message.jump_url} '{self.permissionStrings.get(message.id)}')''' if len(self.permissionStrings.get(message.id)) < 900 else 'Use 🇵 to toggle details')
                    reactions.append('🇵')
                members = {}
                removedKeys = {}
                gainedKeys = {}
                for m in after.guild.members:
                    removed = ' '.join([p[0] for p in iter(before.permissions_for(m)) if p[1] and p[0] not in [pp[0] for pp in after.permissions_for(m) if pp[1]]])
                    gained = ' '.join([p[0] for p in iter(after.permissions_for(m)) if p[1] and p[0] not in [pp[0] for pp in before.permissions_for(m) if pp[1]]])
                    if len(removed) > 0: 
                        try: members[m.id].update({'removed': removed})
                        except KeyError: members[m.id] = {'removed': removed}
                    if len(gained) > 0: 
                        try: members[m.id].update({'gained': gained})
                        except KeyError: members[m.id] = {'gained': gained}
                for k, v in members.items():
                    try: removedKeys[v.get('removed')].append(after.guild.get_member(k))
                    except AttributeError: removedKeys[v.get('removed')] = [after.guild.get_member(k)]
                    except KeyError:
                        if v.get('removed') is not None: removedKeys[v.get('removed')] = [after.guild.get_member(k)]
                    try: gainedKeys[v.get('gained')].append(after.guild.get_member(k))
                    except AttributeError: gainedKeys[v.get('gained')] = [after.guild.get_member(k)]
                    except KeyError:
                        if v.get('gained') is not None: gainedKeys[v.get('gained')] = [after.guild.get_member(k)]
                joinKeys = (' 👤 ', ' • ')
                gainDescription = (f'''{newline.join([f"[{len(v)} members gained {len(k.split(' '))} permissions • Hover for details]({message.jump_url} '--MEMBERS--{newline}{newline.join([m.name for m in v]) if len(v) < 20 else joinKeys[0].join([m.name for m in v])}{newline}{newline}--PERMISSIONS--{newline}{newline.join([permissionKeys.get(p) for p in k.split(' ')]) if len(k.split(' ')) < 20 else joinKeys[1].join([permissionKeys.get(p) for p in k.split(' ')])}')" for k, v in gainedKeys.items()])}{newline if len(removedKeys) > 0 and len(gainedKeys) > 0 else ''}''') if len(gainedKeys) > 0 else ''
                removeDescription = f'''{newline.join([f"[{len(v)} members lost {len(k.split(' '))} permissions • Hover for details]({message.jump_url} '--MEMBERS--{newline}{newline.join([m.name for m in v]) if len(v) < 20 else joinKeys[0].join([m.name for m in v])}{newline}{newline}--PERMISSIONS--{newline}{newline.join([permissionKeys.get(p) for p in k.split(' ')]) if len(k.split(' ')) < 20 else joinKeys[1].join([permissionKeys.get(p) for p in k.split(' ')])}')" for k,v in removedKeys.items()])}''' if len(removedKeys) > 0 else ''
                if len(gainDescription) > 0 or len(removeDescription) > 0: embed.description+=f'{newline if len(gainDescription) > 0 or len(removeDescription) > 0 else ""}{gainDescription}{removeDescription}\n🕰Precise timestamp: {received} {nameZone(after.guild)}'
                else: 
                    if before.overwrites != after.overwrites: embed.description+=f'\nPermissions were updated but nobody gained or lost permissions\n🕰Precise timestamp: {received} {nameZone(after.guild)}'
                    else: embed.description+=f'\n🕰Precise timestamp: {received} {nameZone(after.guild)}'
                await message.edit(embed=embed)
                for reaction in reactions: await message.add_reaction(reaction)
                try: 
                    if os.path.exists(savePath): os.remove(savePath)
                except: pass
                await VerifyLightningLogs(message, 'channel')
        if before.position != after.position or before.category != after.category:
            for c in after.guild.categories:
                try: self.categories[c.id] = c.channels
                except discord.Forbidden: pass
            try: self.categories[after.guild.id] = [c[1] for c in after.guild.by_category() if c[0] is None]
            except discord.Forbidden: pass
        if type(before) is discord.TextChannel and before.name != after.name: await asyncio.gather(database.VerifyServer(after.guild, bot))
        try:
            if logEnabled(before.guild, 'channel') and message:
                final = copy.deepcopy(embed)
                while True:
                    #try:
                    def reactionCheck(r, u): return str(r) in ('🇵', 'ℹ') and r.message.id == message.id and not u.bot
                    r = await self.bot.wait_for('reaction_add', check=reactionCheck)
                    if str(r[0]) == '🇵':
                        await message.edit(content=self.permissionStrings.get(message.id))
                        def undoCheck(rr, u): return str(rr) == '🇵' and rr.message.id == message.id and u.id == r[1].id
                        try: await self.bot.wait_for('reaction_remove', check=undoCheck, timeout=120)
                        except asyncio.TimeoutError: await message.remove_reaction(r[0], r[1])
                        await message.edit(content=content)
                    else:
                        await message.clear_reactions()
                        if 'Loading channel information' not in embed.description: embed.description+='\n\n{} Loading channel information: {}'.format(self.loading, after.name)
                        await message.edit(embed=embed)
                        result = await self.ChannelInfo(after, None if after.type[0] == 'category' else await after.invites(), None if after.type[0] != 'text' else await after.pins(), await after.guild.audit_logs(limit=None).flatten())
                        await message.edit(content=result[0], embed=result[1])
                        await message.add_reaction('⬅')
                        def backCheck(rr, u): return str(rr) == '⬅' and rr.message.id == message.id and u.id == r[1].id
                        try: await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                        except asyncio.TimeoutError: pass
                        await message.edit(content=content,embed=final)
                        await message.clear_reactions()
                        for r in reactions: await message.add_reaction(r)
                    #except Exception as e: print(f'Channel update reaction error {e}')
        except UnboundLocalError: return

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when channel is deleted'''
        received = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(channel.guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        if logEnabled(channel.guild, "channel"):
            content=None
            f = None
            savePath = None
            embed=discord.Embed(title=f'{self.channelKeys.get(channel.type[0])}❌{channel.type[0][0].upper() + channel.type[0][1:]} Channel was deleted', description=f'{self.hashtag if channel.type[0] == "text" else "🎙"}Channel: {channel.name}', color=red, timestamp=datetime.datetime.utcnow())
            if readPerms(channel.guild, "channel"):
                try:
                    log = (await channel.guild.audit_logs(limit=1).flatten())[0]
                    if log.action == discord.AuditLogAction.channel_delete:
                        embed.description+=f'\n👮‍♂️Deleted by: {log.user.mention} ({log.user.name})' + (f' because "{log.reason}"' if log.reason is not None else '')
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        embed.set_thumbnail(url=f'attachment://{f.filename}')
                        await updateLastActive(log.user, datetime.datetime.now(), 'deleted a channel')
                except discord.Forbidden: content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
            embed.description+=f'\n🕰Precise timestamp: {received} {nameZone(channel.guild)}'
            embed.set_footer(text=f'Channel ID: {channel.id}')
            msg = await logChannel(channel.guild, "channel").send(content=content,embed=embed,file=f)
            if channel.type[0] != 'category':
                channelList = self.categories.get(channel.category.id) if channel.category is not None else self.categories.get(channel.guild.id)                
                startEnd = (channelList.index(channel) - 3 if channelList.index(channel) >= 3 else 0, channelList.index(channel) + 4 if channelList.index(channel) + 4 < len(channelList) else len(channelList))
                embed.add_field(name="Category Tree",value=f'''📁{channel.category}\n{f"> [...Hover to view {len(channelList[:startEnd[0]])} more channel{'s' if len(channelList[:startEnd[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[:startEnd[0]])}'){newline}" if startEnd[0] > 0 else ""}{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList[startEnd[0]:startEnd[1]]])}{f"{newline}> [Hover to view {len(channelList[startEnd[1]:])} more channel{'s' if len(channelList[startEnd[1]:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[startEnd[1]:])}')" if startEnd[1] < len(channelList) else ""}''')
                if channel.category is not None: self.categories[channel.category.id].remove(channel)
                else: self.categories[channel.guild.id].remove(channel)
            if channel.type[0] == 'text': 
                try:
                    path = f'{indexes}/{channel.guild.id}/{channel.id}.json'
                    with open(path) as f:
                        indexData = json.load(f)
                        embed.add_field(name='Message count', value=len(indexData.keys()))
                    try:
                        archivePath = f'{indexes}/Archive'
                        try: os.makedirs(archivePath)
                        except FileExistsError: pass
                        with open(f'{archivePath}/{channel.id}.json', 'w+') as f:
                            f.write(json.dumps(indexData, indent=4))
                            os.remove(path)
                    except Exception as e: print(f'Channel deletion file saving error: {e}')
                    #embed.add_field(name='Message count',value=len(os.listdir(f'{indexes}/{channel.guild.id}/{channel.id}')))
                except Exception as e: embed.add_field(name='Message count',value=f'Error: {e}')
                self.pins.pop(channel.id, None)
            await msg.edit(embed=embed)
            if os.path.exists(savePath): os.remove(savePath)
            await VerifyLightningLogs(msg, 'channel')
        if type(channel) is discord.TextChannel: asyncio.create_task(database.VerifyServer(channel.guild, bot))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member joins a server'''
        received = (member.joined_at + datetime.timedelta(hours=self.bot.lightningLogging.get(member.guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        global members
        asyncio.create_task(self.doorguardHandler(member))
        if logEnabled(member.guild, "doorguard"):
            newInv = []
            content=None
            savePath = None
            f = None
            targetInvite = None
            reactions = ['🔽', 'ℹ', '🤐', '🔒', '👢', '🔨']
            count = len(member.guild.members)
            ageDelta = datetime.datetime.utcnow() - member.created_at
            units = ['second', 'minute', 'hour', 'day']
            hours, minutes, seconds = ageDelta.seconds // 3600, (ageDelta.seconds // 60) % 60, ageDelta.seconds - (ageDelta.seconds // 3600) * 3600 - ((ageDelta.seconds // 60) % 60)*60
            ageTimes = [seconds, minutes, hours, ageDelta.days]
            ageDisplay = []
            for i in range(len(ageTimes) - 1, -1, -1):
                if ageTimes[i] != 0: ageDisplay.append(f'{ageTimes[i]} {units[i]}{"s" if ageTimes[i] != 1 else ""}')
            if len(ageDisplay) == 0: ageDisplay = ['0 seconds']
            embed=discord.Embed(title=f"👤{self.greenPlus}New member {self.loading}",timestamp=datetime.datetime.utcnow(),color=0x008000)
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not member.is_avatar_animated() else 'gif'))
            try: await member.avatar_url_as(size=1024).save(savePath)
            except discord.HTTPException: pass
            f = discord.File(savePath)
            embed.set_thumbnail(url=f'attachment://{f.filename}')
            embed.set_footer(text='Member ID: {}'.format(member.id))
            try:
                newInv = await member.guild.invites()
                oldInv = self.invites.get(str(member.guild.id))
            except discord.Forbidden:
                content="Tip: I can determine who invited new members if I have the `Manage Server` permissions"
            try:
                for invite in oldInv:
                    try:
                        if newInv[newInv.index(invite)].uses > invite.uses:
                            targetInvite = newInv[newInv.index(invite)]
                            break
                    except ValueError: #An invite that reached max uses will be missing from the new list
                        targetInvite = newInv[newInv.index(invite)]
                        break 
                if not targetInvite: #Check the vanity invite (if applicable) if we don't have an invite
                    try:
                        invite = await member.guild.vanity_invite()
                        if invite.uses > self.invites.get(str(member.guild.id)+"_vanity").uses: targetInvite = invite
                    except discord.HTTPException: pass
            except Exception as e: embed.add_field(name='Invite Details',value=f'Error retrieving details: {e}'[:1023])
            try: self.invites[str(member.guild.id)] = newInv
            except: pass
            msg = await logChannel(member.guild, "doorguard").send(content=content,embed=embed,file=f)
            descriptionString = [f'''{member.mention} ({member.name})\n{count}{suffix(count)} member\nPrecise timestamp of join: {received}\nAccount created: {(member.created_at + datetime.timedelta(hours=timeZone(member.guild))):%b %d, %Y • %I:%M %p} {nameZone(member.guild)}\nAccount age: {f"{', '.join(ageDisplay[:-1])} and {ageDisplay[-1]}" if len(ageDisplay) > 1 else ageDisplay[0]} old\nMutual Servers: {len([g for g in bot.guilds if member in g.members])}\n\nQUICK ACTIONS\nYou will be asked to confirm any of these quick actions via reacting with a checkmark after initiation, so you can click one to learn more without harm.\n🤐: Mute {member.name}\n🔒: Quarantine {member.name}\n👢: Kick {member.name}\n🔨: Ban {member.name}''', 
                f'''{member.mention} ({member.name})\n{count}{suffix(count)} member\nAccount age: {ageDisplay[0]} old\n[Hover or react 🔽 for more details]({msg.jump_url} 'Precise timestamp of join: {received}\nAccount created: {(member.created_at + datetime.timedelta(hours=timeZone(member.guild))):%b %d, %Y • %I:%M %p} {nameZone(member.guild)}\nAccount age: {f"{', '.join(ageDisplay[:-1])} and {ageDisplay[-1]}" if len(ageDisplay) > 1 else ageDisplay[0]} old\nMutual Servers: {len([g for g in bot.guilds if member in g.members])}\n\nQUICK ACTIONS\nYou will be asked to confirm any of these quick actions via reacting with a checkmark after initiation, so you can click one to learn more without harm.\n🤐: Mute {member.name}\n🔒: Quarantine {member.name}\n👢: Kick {member.name}\n🔨: Ban {member.name}')''']
            embed.description = descriptionString[1]
            if targetInvite: 
                inviteString = [f'''Invited by {targetInvite.inviter.name} ({targetInvite.inviter.mention})\nCode: discord.gg/{targetInvite.code}\nChannel: {targetInvite.channel.name}\nCreated: {targetInvite.created_at:%b %d, %Y • %I:%M %p} {nameZone(member.guild)}\n{"Never expires" if targetInvite.max_age == 0 else f"Expires: {(datetime.datetime.utcnow() + datetime.timedelta(seconds=targetInvite.max_age)):%b %d, %Y • %I:%M %p} {nameZone(member.guild)}"}\nUsed: {targetInvite.uses} of {"∞" if targetInvite.max_uses == 0 else targetInvite.max_uses} times''',
                    f'''Invited by {targetInvite.inviter.name} ({targetInvite.inviter.mention})\n[Hover or react 🔽 for more details]({msg.jump_url} '\nCode: discord.gg/{targetInvite.code}\nChannel: {targetInvite.channel.name}\nCreated: {targetInvite.created_at:%b %d, %Y • %I:%M %p} {nameZone(member.guild)}\n{"Never expires" if targetInvite.max_age == 0 else f"Expires: {(datetime.datetime.utcnow() + datetime.timedelta(seconds=targetInvite.max_age)):%b %d, %Y • %I:%M %p} {nameZone(member.guild)}"}\nUsed: {targetInvite.uses} of {"∞" if targetInvite.max_uses == 0 else targetInvite.max_uses} times')''']
                embed.add_field(name='Invite Details',value=inviteString[1] if len(inviteString[1]) < 1024 else inviteString[0])
            await msg.edit(embed=embed)
            await VerifyLightningLogs(msg, 'doorguard')
        members[member.guild.id] = member.guild.members
        await asyncio.gather(*[database.VerifyServer(member.guild, bot), database.VerifyUser(member, bot), updateLastActive(member, datetime.datetime.now(), 'joined a server')])
        try:
            if os.path.exists(savePath): os.remove(savePath)
        except: pass
        if logEnabled(member.guild, "doorguard"):
            if member in member.guild.members:
                embed.title=f'👤{self.greenPlus}New member (React ℹ for member info viewer)'
                await msg.edit(embed=embed)
                final = copy.deepcopy(embed)
                memberInfoEmbed = None
                while True:
                    for r in reactions: await msg.add_reaction(r)
                    embed = copy.deepcopy(final)
                    def navigationCheck(r, u): return str(r) in reactions and not u.bot and r.message.id == msg.id
                    r = await self.bot.wait_for('reaction_add', check=navigationCheck)
                    embed.clear_fields()
                    await msg.clear_reactions()
                    if str(r[0]) == '🔽':
                        final.description = descriptionString[0]
                        try: final.set_field_at(0, name='**Invite Details**', value=inviteString[0])
                        except: pass
                        reactions.remove('🔽')
                        reactions.insert(0, '🔼')
                    elif str(r[0]) == '🔼':
                        final.description = descriptionString[1]
                        try: final.set_field_at(0, name='**Invite Details**', value=inviteString[1])
                        except: pass
                        reactions.remove('🔼')
                        reactions.insert(0, '🔽')
                    elif str(r[0]) == 'ℹ':
                        if not memberInfoEmbed:
                            embed.description = f'{self.loading}Please wait for member information to load'
                            await msg.edit(embed=embed)
                            memberInfoEmbed = await self.MemberInfo(member, False)
                            memberInfoEmbed.set_thumbnail(url=f'attachment://{f.filename}')
                        await msg.edit(embed=memberInfoEmbed)
                        await msg.add_reaction('⬅')
                        def backCheck(rr, u): return str(rr) == '⬅' and u == r[1] and rr.message.id == msg.id
                        try: await self.bot.wait_for('reaction_add', check=backCheck, timeout=300)
                        except asyncio.TimeoutError: pass
                    elif str(r[0]) == '🤐':
                        if await database.ManageRoles(r[1]) and await database.ManageChannels(r[1]):
                            embed.description = f'{r[1].name}, would you like me to mute **{member.name}**?\n\nThis member will remain muted until the role RicobotAutoMute is manually removed from them.\n\nTo confirm, react {self.whiteCheck} within 10 seconds'
                            embed.set_image(url='https://i.postimg.cc/s2pZs1Cv/ten.gif')
                            await msg.edit(embed=embed)
                            for reaction in ['❌', '✔']: await msg.add_reaction(reaction)
                            def confirmCheck(rr, u): return str(rr) in ['❌', '✔'] and u == r[1] and rr.message.id == msg.id
                            try: rr = await self.bot.wait_for('reaction_add', check=confirmCheck, timeout=10)
                            except asyncio.TimeoutError: rr = [0]
                            if str(rr[0]) == '✔':
                                muteRole = discord.utils.get(member.guild.roles, name='RicobotAutoMute')
                                if muteRole is None: muteRole = await member.guild.create_role(name='RicobotAutoMute', reason='Quickmute')
                                try: await muteRole.edit(position=member.guild.me.top_role.position - 1)
                                except discord.Forbidden: embed.description+='\nUnable to move mute role below mine. Members with role above RicobotAutoMute will not be muted unless its position is moved further up.'
                                for c in member.guild.text_channels: 
                                    try: await c.set_permissions(muteRole, send_messages=False)
                                    except discord.Forbidden as error: embed.description+=f'\nUnable to create permission overwrites for the channel {c.name} because `{error.text}`. Please set the permissions for this channel to [RicobotAutoMute: Send Messages = ❌] for the mute to work there.'
                                try: 
                                    await member.add_roles(muteRole)
                                    embed.description=final.description+f'\n\n**Successfully muted {member.name}**'
                                except discord.Forbidden as error: embed.description+=f'\n\n**Unable to mute {member.name} because `{error.text}`.**'
                                await msg.edit(embed=embed)
                                final.description = embed.description
                        else:
                            embed.description+=f'\n\n**{r[1].name}, you need `Manage Roles` and `Manage Channels` permissions to mute {member.name}.**'
                            await msg.edit(embed=embed)
                            await asyncio.sleep(10)
                    elif str(r[0]) == '🔒':
                        if await database.ManageChannels(r[1]):
                            embed.description = f'{r[1].name}, would you like me to quarantine **{member.name}**?\n\nThis will prevent {member.name} from being able to access any of the channels in this server until the `unlock` command is run.\n\nTo confirm, react {self.whiteCheck} within 10 seconds'
                            embed.set_image(url='https://i.postimg.cc/s2pZs1Cv/ten.gif')
                            await msg.edit(embed=embed)
                            for reaction in ['❌', '✔']: await msg.add_reaction(reaction)
                            def confirmCheck(rr, u): return str(rr) in ['❌', '✔'] and u == r[1] and rr.message.id == msg.id
                            try: rr = await self.bot.wait_for('reaction_add', check=confirmCheck, timeout=10)
                            except asyncio.TimeoutError: rr = [0]
                            if str(rr[0]) == '✔':
                                for c in member.guild.text_channels: 
                                    try: await c.set_permissions(member, read_messages=False)
                                    except discord.Forbidden as error: embed.description+=f'\nUnable to create permission overwrites for the channel {c.name} because `{error.text}`. Please set the permissions for this channel to [{member.name}: Read Messages = ❌] for the quarantine to work there.'
                                embed.description=final.description+f'\n\n**Successfully quarantined {member.name}.**\nUse `{prefix(member.guild)}unlock {member.id}` to unlock this user when desired.'
                                await msg.edit(embed=embed)
                                final.description = embed.description
                        else:
                            embed.description+=f'\n\n**{r[1].name}, you need `Manage Channels` permissions to quarantine {member.name}.**'
                            await msg.edit(embed=embed)
                            await asyncio.sleep(10)
                    elif str(r[0]) == '👢':
                        if await database.KickMembers(r[1]):
                            embed.description = f'{r[1].name}, would you like me to kick **{member.name}**? Please react {self.whiteCheck} within 10 seconds to confirm. To provide a reason for the kick, react 📝 instead of check, and you will be able to provide a reason at the next step.'
                            embed.set_image(url='https://i.postimg.cc/s2pZs1Cv/ten.gif')
                            await msg.edit(embed=embed)
                            for reaction in ['❌', '📝', '✔']: await msg.add_reaction(reaction)
                            def confirmCheck(rr, u): return str(rr) in ['❌', '📝', '✔'] and u == r[1] and rr.message.id == msg.id
                            try: rr = await self.bot.wait_for('reaction_add', check=confirmCheck, timeout=10)
                            except asyncio.TimeoutError: rr = [0]
                            if str(rr[0]) == '✔':
                                try: 
                                    await member.kick()
                                    embed.description=final.description+f'\n\n**Successfully kicked {member.name}**'
                                except discord.Forbidden as error: embed.description+=f'\n\n**Unable to kick {member.name} because `{error.text}`.**'
                                await msg.edit(embed=embed)
                                final.description = embed.description
                            elif str(rr[0]) == '📝':
                                def reasonCheck(m): return msg.channel == m.channel and m.author.id == r[1].id
                                embed.description=f'Please type the reason you would like to kick {member.name}.\n\nType your reason within 60 seconds. The first message you type will be used, and {member.name} will be kicked.\n\nTo cancel, wait 60 seconds without sending anything.'
                                embed.set_image(url='https://i.postimg.cc/kg2rttTh/sixty.gif')
                                await msg.edit(embed=embed)
                                try: reason = await self.bot.wait_for('message', check=reasonCheck, timeout=60)
                                except: pass
                                try:
                                    await member.kick(reason=f'Kicked by {r[1].name} because {reason.content}')
                                    embed.description=final.description+f'\n\nSuccessfully kicked {member.name}.'
                                    final.description = embed.description
                                except discord.Forbidden as error: embed.description+=f'\n\n**Unable to kick {member.name} because `{error.text}`.**'
                                except UnboundLocalError: pass #Timeout
                                await msg.edit(embed=embed)
                        else:
                            embed.description+=f'\n\n**{r[1].name}, you need `Kick Members` permissions to kick {member.name}.**'
                            await msg.edit(embed=embed)
                            await asyncio.sleep(10)
                    elif str(r[0]) == '🔨':
                        if await database.BanMembers(r[1]):
                            embed.description = f'{r[1].name}, would you like me to ban **{member.name}** indefinitely? Please react {self.whiteCheck} within 10 seconds to confirm. To provide a reason for the ban, react 📝 instead of check, and you will be able to provide a reason at the next step.'
                            embed.set_image(url='https://i.postimg.cc/s2pZs1Cv/ten.gif')
                            await msg.edit(embed=embed)
                            for reaction in ['❌', '📝', '✔']: await msg.add_reaction(reaction)
                            def confirmCheck(rr, u): return str(rr) in ['❌', '📝', '✔'] and u == r[1] and rr.message.id == msg.id
                            try: rr = await self.bot.wait_for('reaction_add', check=confirmCheck, timeout=10)
                            except asyncio.TimeoutError: rr = [0]
                            if str(rr[0]) == '✔':
                                try: 
                                    await member.ban()
                                    embed.description=final.description+f'\n\n**Successfully banned {member.name}**'
                                except discord.Forbidden as error: embed.description+=f'\n\n**Unable to ban {member.name} because `{error.text}`.**'
                                await msg.edit(embed=embed)
                                final.description = embed.description
                            elif str(rr[0]) == '📝':
                                def reasonCheck(m): return msg.channel == m.channel and m.author.id == r[1].id
                                embed.description=f'Please type the reason you would like to ban {member.name}.\n\nType your reason within 60 seconds. The first message you type will be used, and {member.name} will be banned.\n\nTo cancel, wait 60 seconds without sending anything.'
                                embed.set_image(url='https://i.postimg.cc/kg2rttTh/sixty.gif')
                                await msg.edit(embed=embed)
                                try: reason = await self.bot.wait_for('message', check=reasonCheck, timeout=60)
                                except: pass
                                try:
                                    await member.ban(reason=f'Banned by {r[1].name} because {reason.content}')
                                    embed.description=final.description+f'\n\nSuccessfully banned {member.name}.'
                                    final.description = embed.description
                                except discord.Forbidden as error: embed.description+=f'\n\n**Unable to ban {member.name} because `{error.text}`.**'
                                except UnboundLocalError: pass #Timeout
                                await msg.edit(embed=embed)
                        else:
                            embed.description+=f'\n\n**{r[1].name}, you need `Ban Members` permissions to ban {member.name}.**'
                            await msg.edit(embed=embed)
                            await asyncio.sleep(10)
                    await msg.clear_reactions()
                    await msg.edit(embed=final) 
            else:
                embed.title=f'👤{self.greenPlus}New member (Left the server)'
                await msg.edit(embed=embed)

    async def doorguardHandler(self, member: discord.Member):
        '''REPEATED JOINS'''
        rj = antispamObject(member.guild).get('repeatedJoins')
        if 0 not in rj[:2]: #Make sure this module is enabled (remember, modules are set to 0 to mark them as disabled)
            try: self.repeatedJoins[f'{member.guild.id}_{member.id}'].append(member.joined_at)
            except (AttributeError, KeyError): self.repeatedJoins[f'{member.guild.id}_{member.id}'] = [member.joined_at]
            joinLogs = self.repeatedJoins.get(f'{member.guild.id}_{member.id}')
            remainingDelta = ((joinLogs[0] + datetime.timedelta(seconds=rj[1])) - datetime.datetime.utcnow()) #Time remaining before oldest join log expires. If a member joins the server [threshold] times in this timespan, they're punished
            durationDelta = datetime.timedelta(seconds=rj[2])
            rH, rM, rS = remainingDelta.seconds // 3600, (remainingDelta.seconds // 60) % 60, remainingDelta.seconds - (remainingDelta.seconds // 3600) * 3600 - ((remainingDelta.seconds // 60) % 60) * 60 #remainingHours, remainingMinutes, remainingSeconds
            dH, dM, dS = durationDelta.seconds // 3600, (durationDelta.seconds // 60) % 60, durationDelta.seconds - (durationDelta.seconds // 3600) * 3600 - ((durationDelta.seconds // 60) % 60) * 60 #ban duration Hours, Minutes, Seconds            
            remainingTimes = [rS, rM, rH, remainingDelta.days]
            durationTimes = [dH, dM, dS, durationDelta.days]
            remainingDisplay = []
            durationDisplay = []
            for i in range(len(remainingTimes) - 1, -1, -1):
                if remainingTimes[i] != 0: remainingDisplay.append(f'{remainingTimes[i]} {units[i]}{"s" if remainingTimes[i] != 1 else ""}')
                if durationTimes[i] != 0: durationDisplay.append(f'{durationTimes[i]} {units[i]}{"s" if durationTimes[i] != 1 else ""}')
            if len(remainingDisplay) == 0: remainingDisplay = ['0 seconds']
            if len(durationDisplay) == 0: durationDisplay = ['0 seconds']
            if len(joinLogs) > 1:
                #This is the warning segment: If this is at least the second time the member has joined the server recently, then we will warn them of the threshold and consequences if they continue to join.
                sendString = f'''{member.mention}, `{member.guild.name}` has my Antispam [repeated joins] module enabled. If you join this server {rj[0] - len(joinLogs)} more time{'s' if rj[0] - len(joinLogs) != 1 else ''} in {f"{', '.join(remainingDisplay[:-1])} and {remainingDisplay[-1]}" if len(remainingDisplay) > 1 else remainingDisplay[0]}, you will be banned{'.' if rj[2] == 0 else f" for {', '.join(durationDisplay[:-1])} and {durationDisplay[-1]}" if len(durationDisplay) > 1 else f" for {durationDisplay[0]}"}.'''
                try: await member.send(sendString)
                except discord.Forbidden: #Can't DM member, try to let them know in the server (if ageKick is disabled)
                    if await database.GetAgeKick(member.guild) is None:
                        sendTo = await database.CalculateGeneralChannel(member.guild, True)
                        if sendTo.permissions_for(member).read_messages: await sendTo.send(sendString) #If the member can read messages in the server's general channel, then we'll send it there
            if len(joinLogs) >= rj[0]:
                joinSpan = (joinLogs[-1] - joinLogs[0])
                jH, jM, jS = joinSpan.seconds // 3600, (joinSpan.seconds // 60) % 60, joinSpan.seconds - (joinSpan.seconds // 3600) * 3600 - ((joinSpan.seconds // 60) % 60) * 60
                joinSpanTimes = [jS, jM, jH, joinSpan.days]
                joinSpanDisplay = []
                for i in range(len(joinSpanTimes) - 1, -1, -1):
                    if joinSpanTimes[i] != 0: joinSpanDisplay.append(f'{joinSpanTimes[i]} {units[i]}{"s" if joinSpanTimes[i] != 1 else ""}')
                if len(joinSpanDisplay) == 0: joinSpanDisplay = ['0 seconds']
                if joinSpan.seconds < rj[1]:
                    unbanAt = datetime.datetime.utcnow() + datetime.timedelta(seconds=rj[2])
                    timezoneUnbanAt = unbanAt + datetime.timedelta(hours=timeZone(member.guild))
                    try: await member.send(f'You have been banned from `{member.guild.name}` until {timezoneUnbanAt:%b %d, %Y • %I:%M %p} {nameZone(member.guild)} for repeatedly joining and leaving the server.')
                    except: pass
                    try: await member.ban(reason=f'''[Antispam: repeatedJoins] {member.name} joined the server {len(joinLogs)} times in {f"{', '.join(joinSpanDisplay[:-1])} and {joinSpanDisplay[-1]}" if len(joinSpanDisplay) > 1 else joinSpanDisplay[0]}, and will remain banned until {f"{timezoneUnbanAt:%b %d, %Y • %I:%M %p} {nameZone(member.guild)}" if rj[2] > 0 else "the ban is manually revoked"}.''')
                    except discord.Forbidden: 
                        try: await logChannel(member.guild, "doorguard").send(f'Unable to ban {member.name} for [ageKick: repeatedJoins] module')
                        except: pass
                    self.repeatedJoins[f'{member.guild.id}_{member.id}'].clear()
                    banTimedEvent = {'type': 'ban', 'flavor': '[Antispam: repeatedJoins]', 'target': member.id, 'expires': datetime.datetime.utcnow() + datetime.timedelta(seconds=rj[2])}
                    await database.AppendTimedEvent(member.guild, banTimedEvent)
        '''AGEKICK ⬇'''
        acctAge = (datetime.datetime.utcnow() - member.created_at).days
        antispam = antispamObject(member.guild)
        ageKick = antispam.get('ageKick')
        if ageKick is not None: #Check account age; requested feature
            if acctAge < ageKick and member.id not in antispam.get('ageKickWhitelist'): #If the account age is under the threshold and they're not whitelisted:
                memberCreated = member.created_at + datetime.timedelta(hours=timeZone(member.guild))
                canRejoin = memberCreated + datetime.timedelta(days=ageKick)
                formatter = '%b %d, %Y • %I:%M %p'
                timezone = nameZone(member.guild)
                dm = antispam.get('ageKickDM')
                try: await member.send(eval(dm))
                except discord.Forbidden as e: 
                    try: await logChannel(member.guild, "doorguard").send(content=f'I will kick {member.name}, but I can\'t DM them explaining why they were kicked because {e.text}.')
                    except: pass
                await member.kick(reason=f'[Antispam: ageKick] Account must be {ageKick} days old')
            elif member.id in antispam.get('ageKickWhitelist'): await database.RemoveWhitelistEntry(member.guild, member.id)
        '''Repeated Joins: Sleeping'''
        if 0 not in rj[:2]:
            try:
                if len(joinLogs) >= rj[0] and rj[2] > 0:
                    await asyncio.sleep(rj[2])
                    try: await member.unban(reason='[Antispam: repeatedJoins] Ban time is up!')
                    except discord.Forbidden: await logChannel(member.guild, "doorguard").send(f'Unable to unban {member.name} for [ageKick: repeatedJoins]; their ban time is up')
                    await database.RemoveTimedEvent(member.guild, banTimedEvent)
                else: 
                    await asyncio.sleep(rj[1])
                    if len(joinLogs) > 0: self.repeatedJoins[f'{member.guild.id}_{member.id}'].pop(0) #Removes the oldest entry
            except UnboundLocalError: pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member leaves a server'''
        received = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(member.guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        global members
        asyncio.create_task(updateLastActive(member, datetime.datetime.now(), 'left a server'))
        if logEnabled(member.guild, "doorguard"):
            content=None
            f = None
            embed=discord.Embed(title=f'👤❌Member left ({self.loading}Finalizing log)', description=f'{member.mention} ({member.name})', timestamp=datetime.datetime.utcnow(), color=red)
            span = datetime.datetime.utcnow() - member.joined_at
            hours, minutes, seconds = span.seconds // 3600, (span.seconds // 60) % 60, span.seconds - (span.seconds // 3600) * 3600 - ((span.seconds // 60) % 60) * 60
            times = [seconds, minutes, hours, span.days]
            hereForDisplay = []
            for i in range(len(times) - 1, -1, -1):
                if times[i] != 0: hereForDisplay.append(f'{times[i]} {units[i]}{"s" if times[i] != 1 else ""}')            
            if len(hereForDisplay) == 0: hereForDisplay = ['0 seconds']
            embed.add_field(name='Post count',value=self.loading)
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not member.is_avatar_animated() else 'gif'))
            try: await member.avatar_url_as(size=1024).save(savePath)
            except discord.HTTPException: pass
            f = discord.File(savePath)
            embed.set_thumbnail(url=f'attachment://{f.filename}')
            embed.set_footer(text=f'Member ID: {member.id}')
            message = await logChannel(member.guild, 'doorguard').send(content=content,embed=embed,file=f)
            if readPerms(member.guild, 'doorguard'):
                try:
                    log = (await member.guild.audit_logs(limit=1).flatten())[0]
                    if (datetime.datetime.utcnow() - log.created_at).seconds < 3 and log.target.id == member.id:
                        if log.action == discord.AuditLogAction.kick:
                            embed.title = f'👤👢{member.name} was kicked'
                            embed.description=f'👮‍♂️Kicked by: {log.user.mention} ({log.user.name})'
                            embed.insert_field_at(0, name='**Reason**',value=log.reason if log.reason is not None else "None provided", inline=True if log.reason is not None and len(log.reason) < 25 else False)
                        elif log.action == discord.AuditLogAction.ban:
                            embed.title = f'👤🔨{member.name} was banned'
                            embed.description=f'👮‍♂️Banned by: {log.user.mention} ({log.user.name})'
                            embed.insert_field_at(0, name="**Reason**",value=log.reason if log.reason is not None else "None provided",inline=True if log.reason is not None and len(log.reason) < 25 else False)
                except discord.Forbidden: content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
                except AttributeError: pass
            try:
                embed.description+=f"\n[Hover for more details]({message.jump_url} 'Here since: {(member.joined_at + datetime.timedelta(hours=timeZone(member.guild))):%b %d, %Y • %I:%M:%S %p} {nameZone(member.guild)}"
                embed.description+=f'''\nLeft at: {received}\nHere for: {f"{', '.join(hereForDisplay[:-1])} and {hereForDisplay[-1]}" if len(hereForDisplay) > 1 else hereForDisplay[0]}'''
                sortedMembers = sorted(members.get(member.guild.id), key=lambda x: x.joined_at)
                memberJoinPlacement = sortedMembers.index(member) + 1
                embed.description+=f'\nWas the {memberJoinPlacement}{suffix(memberJoinPlacement)} member, now we have {len(sortedMembers) - 1}'
            except Exception as e: print(f'Member leave placement fail: {e}')
            embed.description+="')"
            if 'Finalizing' in embed.title: embed.title = '👤❌Member left'
            await message.edit(embed=embed)
            embed.set_field_at(-1, name='**Post count**', value=await asyncio.create_task(self.MemberPosts(member)))
            await message.edit(embed=embed)
            await VerifyLightningLogs(message, 'doorguard')
        members[member.guild.id] = member.guild.members
        try: 
            if os.path.exists(savePath): os.remove(savePath)
        except: pass
        await asyncio.gather(*[database.VerifyServer(member.guild, bot), database.VerifyUser(member, bot)])

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        received = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        if logEnabled(guild, 'doorguard'):
            embed=discord.Embed(title=f'👤🚫🔨User was unbanned',description=f"👤User: {user.name}",timestamp=datetime.datetime.utcnow(),color=green)
            content=None
            f = None
            #data = {'member': user.id, 'name': user.name, 'server': guild.id}
            if readPerms(guild, 'doorguard'):
                try:
                    log = (await guild.audit_logs(limit=1, action=discord.AuditLogAction.unban).flatten())[0]
                    embed.description = f'👤Unbanned by: {log.user.mention} ({log.user.name})'
                    await updateLastActive(log.user, datetime.datetime.now(), 'unbanned a user')
                    async for log in guild.audit_logs(limit=None): #Attempt to find the ban audit log to pull ban details
                        if log.action == discord.AuditLogAction.ban:
                            if log.target.id == user.id:
                                span = datetime.datetime.utcnow() - log.created_at
                                hours, minutes, seconds = span.seconds // 3600, (span.seconds // 60) % 60, span.seconds - (span.seconds // 3600) * 3600 - ((span.seconds // 60) % 60) * 60
                                times = [seconds, minutes, hours, span.days]
                                bannedForDisplay = []
                                for i in range(len(times) - 1, -1, -1):
                                    if times[i] != 0: bannedForDisplay.append(f'{times[i]} {units[i]}{"s" if times[i] != 1 else ""}')
                                if len(bannedForDisplay) == 0: bannedForDisplay = ['0 seconds']                                
                                embed.add_field(name="Ban details",value='React ℹ to expand', inline=False)
                                longString = f'''Banned by: {log.user.name} ({log.user.mention})\nBanned because: {log.reason if log.reason is not None else '<No reason specified>'}\nBanned at: {(log.created_at + datetime.timedelta(hours=timeZone(guild))):%b %d, %Y • %I:%M:%S %p} {nameZone(guild)}\nUnbanned at: {received}\nBanned for: {f"{', '.join(bannedForDisplay[:-1])} and {bannedForDisplay[-1]}" if len(bannedForDisplay) > 1 else bannedForDisplay[0]}'''
                                break
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`\nI also need that permission to determine if a member was kicked/banned"
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not user.is_avatar_animated() else 'gif'))
            try: await user.avatar_url_as(size=1024).save(savePath)
            except discord.HTTPException: pass
            f = discord.File(savePath)
            embed.set_thumbnail(url=f'attachment://{f.filename}')
            embed.set_footer(text=f'User ID: {user.id}')
            #if await database.SummarizeEnabled(guild, 'doorguard'):
            #    summaries.get(str(guild.id)).add('doorguard', 7, datetime.datetime.now(), data, embed,content=content)
            #else:
            msg = await logChannel(guild, 'doorguard').send(content=content,embed=embed,file=f)
            await VerifyLightningLogs(msg, 'doorguard')
            if len(embed.fields) > 0:
                await msg.add_reaction('ℹ')
                while True:
                    def toggleCheck(r, u): return str(r) == 'ℹ' and not u.bot and r.message.id == msg.id
                    await self.bot.wait_for('reaction_add', check=toggleCheck)
                    embed.set_field_at(-1, name='**Ban details**', value=longString)
                    await msg.edit(embed=embed)
                    await self.bot.wait_for('reaction_remove', check=toggleCheck)
                    embed.set_field_at(-1, name='**Ban details**', value='React ℹ to expand')
                    await msg.edit(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        '''[DISCORD API METHOD] Called when member changes status/game, roles, or nickname; only the two latter events used with this bot'''
        try: received = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(after.guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        except (KeyError, AttributeError): return
        embed = discord.Embed(timestamp = datetime.datetime.utcnow(), color=blue)
        if (before.nick != after.nick or before.roles != after.roles) and logEnabled(before.guild, "member") and memberGlobal(before.guild) != 1:
            content=None
            #data = {'member': before.id, 'name': before.name, 'server': before.guild.id}
            embed.description=f'👤Recipient: {before.mention} ({before.name})'
            if before.roles != after.roles:
                #print(f'{datetime.datetime.now()} Member update - role for {after.name} in server {after.guild.name}')
                br = len(before.roles)
                ar = len(after.roles)
                embed.title = f'👤🚩{self.greenPlus}Member gained {"roles" if ar - br > 1 else "a role"}' if len(after.roles) > len(before.roles) else f'👤🚩❌Member lost {"roles" if br - ar > 1 else "a role"}' if len(after.roles) < len(before.roles) else f'👤🚩✏Member roles moodified'
                try:
                    log = (await before.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update).flatten())[0]
                    if log.target.id == before.id: 
                        embed.description += f'\n👮‍♂️Moderator: {log.user.mention} ({log.user.name})'
                        embed.set_author(name=log.user.name, icon_url=log.user.avatar_url)
                        await updateLastActive(log.user, datetime.datetime.now(), 'updated someone\'s roles')
                except Exception as e: content=f"You have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`"
                added = sorted([r for r in after.roles if r not in before.roles], key = lambda r: r.position)
                removed = sorted([r for r in before.roles if r not in after.roles], key = lambda r: r.position)
                if len(added) > 0: 
                    embed.add_field(name=f'Role{"(s)" if len(added) > 1 else ""} added', value='\n'.join([f'_ _{qlf}{r.name}' for r in added]))
                    #data['newRoles'] = len(added)
                if len(removed) > 0: 
                    embed.add_field(name=f'Role{"(s)" if len(removed) > 1 else ""} removed', value='\n'.join([f'_ _{qlf}{r.name}' for r in removed]))
                    #data['oldRoles'] = len(removed)
                beforePerms = [permissionKeys[p[0]] for p in iter(before.guild_permissions) if p[1]]
                afterPerms = [permissionKeys[p[0]] for p in iter(after.guild_permissions) if p[1]]
                if beforePerms != afterPerms:
                    lost = [p for p in beforePerms if p not in afterPerms]
                    gained = [p for p in afterPerms if p not in beforePerms]
                    lPK = []
                    gPK = []
                    lostList = []
                    gainedList = [] 
                    for r in removed:
                        rolePermissions = [permissionKeys[p[0]] for p in r.permissions if permissionKeys[p[0]] in beforePerms and permissionKeys[p[0]] not in afterPerms and p in iter(r.permissions) and permissionKeys[p[0]] not in lPK]
                        lPK += rolePermissions
                        lostList.append(f'{r.name}\n> {", ".join(rolePermissions)}')
                    for r in added:
                        rolePermissions = [permissionKeys[p[0]] for p in r.permissions if permissionKeys[p[0]] in afterPerms and permissionKeys[p[0]] not in beforePerms and p in iter(r.permissions) and permissionKeys[p[0]] not in gPK]
                        gPK += rolePermissions
                        gainedList.append(f'{r.name}\n> {", ".join(rolePermissions)}')
                    if len(lost) > 0: embed.add_field(name='Lost permissions', value='\n'.join(lostList), inline=False)
                    if len(gained) > 0: embed.add_field(name='Gained permissions', value='\n'.join(gainedList), inline=False)
            if before.nick != after.nick:
                #print(f'{datetime.datetime.now()} Member update - nickname for {after.name} in server {after.guild.name}')
                embed.title = '👤📄✏Member nickname updated'
                try:
                    log = (await before.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update).flatten())[0]
                    if log.target.id == before.id: 
                        embed.description += f'\n👮‍♂️Moderator: {log.user.mention} ({log.user.name})'
                        embed.set_author(name=log.user.name, icon_url=log.user.avatar_url)
                        await updateLastActive(log.user, datetime.datetime.now(), 'updated a nickname')
                except Exception as e: content=f"You have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`"
                oldNick = before.nick if before.nick is not None else "<No nickname>"
                newNick = after.nick if after.nick is not None else "<No nickname>"
                embed.add_field(name="Old nickname",value=oldNick)
                embed.add_field(name="New nickname",value=newNick)
                #data['oldNick'] = oldNick
                #data['newNick'] = newNick
            embed.description += f'\n🕰Timestamp: {received} {nameZone(after.guild)}'
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not after.is_avatar_animated() else 'gif'))
            try: await after.avatar_url_as(size=1024).save(savePath)
            except discord.HTTPException: pass
            f = discord.File(savePath)
            embed.set_thumbnail(url=f'attachment://{f.filename}')
            embed.set_footer(text=f'Member ID: {after.id}')
            if len(embed.fields) > 0:
                #if await database.SummarizeEnabled(before.guild, 'member'):
                #    summaries.get(str(before.guild.id)).add('member', 8, datetime.datetime.now(), data, embed,content=content)
                #else:
                msg = await (logChannel(before.guild, "member")).send(content=content, embed=embed)
                await VerifyLightningLogs(msg, 'member')
            try:
                if os.path.exists(savePath): os.remove(savePath)
            except: pass
        #halfwayStart = datetime.datetime.now()
        targetServer = [g for g in self.bot.guilds if after in g.members][0] #One server, selected to avoid duplication and unnecessary calls since this method is called simultaneously for every server a member is in
        if before.status != after.status:
            if after.guild.id == targetServer.id:
                #print(f'{datetime.datetime.now()} Member update - inside of status update for {after.name} in server {after.guild.name}')
                if after.status == discord.Status.offline: await updateLastOnline(after, datetime.datetime.now())
                if not any(a == discord.Status.offline for a in [before.status, after.status]) and any(a in [discord.Status.online, discord.Status.idle] for a in [before.status, after.status]) and any(a == discord.Status.dnd for a in [before.status, after.status]): await updateLastActive(after, datetime.datetime.now(), 'left DND' if before.status == discord.Status.dnd else 'enabled DND')
        if before.activities != after.activities:
            '''This is for LastActive information and custom status history'''
            #print(f'{datetime.datetime.now()} Member update - outside of activity update for {after.name} in server {after.guild.name}')
            if after.guild.id == targetServer.id:
                for a in after.activities:
                    if a.type == discord.ActivityType.custom:
                        #print(f'{datetime.datetime.now()} Member update - inside of activity update for {after.name} in server {after.guild.name}')
                        try:
                            #timeStarted = datetime.datetime.now()
                            try: user = self.bot.lightningUsers[after.id]
                            except KeyError: return
                            #print(f'{datetime.datetime.now()} Time taken to fetch user from database: {(datetime.datetime.now() - timeStarted).seconds} seconds')
                            if {'e': None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), 'n': a.name} != {'e': user.get('customStatusHistory')[-1].get('emoji'), 'n': user.get('customStatusHistory')[-1].get('name')}: asyncio.create_task(database.AppendCustomStatusHistory(after, None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), a.name))
                        except AttributeError as e: print(f'Attribute error: {e}')
                        except TypeError: asyncio.create_task(database.AppendCustomStatusHistory(after, None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), a.name)) #If the customStatusHistory is empty, we create the first entry
                        newMemb = before.guild.get_member(before.id)
                        if before.status == newMemb.status and before.name != newMemb.name: await updateLastActive(after, datetime.datetime.now(), 'changed custom status')
        #print(f'Excluding verifying the user, finished the latter half of member update in {(datetime.datetime.now() - halfwayStart).seconds} seconds')
        if before.guild_permissions != after.guild_permissions: asyncio.create_task(database.VerifyUser(before, self.bot))

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        '''[DISCORD API METHOD] Called when a user changes their global username, avatar, or discriminator'''
        received = datetime.datetime.utcnow()
        servers = [s for s in bot.guilds if after.id in [m.id for m in s.members]] #Building a list of servers the updated member is in - then we'll calculate logging module permissions for each server
        membObj = [m for m in servers[0].members if m.id == after.id][0] #Fetching the discord.Member object for later use
        # for server in bot.guilds: #Since this method doesn't supply a server, we need to get every server this member is a part of, to
        #     for member in server.members: #log to when they change their username, discriminator, or avatar
        #         if member.id == before.id:
        #             servers.append(server)
        #             membObj = member
        #             break
        embed = discord.Embed(description=f'👤User: {after.mention} ({after.name})', timestamp=received, color=blue)
        titleEmoji = []
        titles = []
        #data = {'member': before.id, 'oldName': before.name, 'newName': after.name}
        try: thumbnailURL = self.bot.lightningUsers.get(after.id).get('avatarHistory')[-1].get('imageURL')
        except (TypeError, AttributeError): 
            if before.avatar_url is not None: thumbnailURL = before.avatar_url_as(static_format='png', size=1024)
        embed.set_thumbnail(url=thumbnailURL)
        if before.avatar_url != after.avatar_url:
            titles.append('Avatar')
            titleEmoji.append('🖼')
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not after.is_avatar_animated() else 'gif'))
            await after.avatar_url_as(size=1024).save(savePath)
            f = discord.File(savePath)
            message = await self.imageLogChannel.send(file=f)
            #data['pfp'] = True
             #Old avatar
            embed.set_image(url=message.attachments[0].url) #New avatar
            embed.add_field(name="Avatar updated", value=f"Old: [Thumbnail to the right]({thumbnailURL})\nNew: [Image below]({message.attachments[0].url})", inline=False)
            await updateLastActive(after, datetime.datetime.now(), 'updated their profile picture')
            asyncio.create_task(database.AppendAvatarHistory(after, message.attachments[0].url))
            if os.path.exists(savePath): os.remove(savePath)
        if before.discriminator != after.discriminator:
            #data['discrim'] = True
            titles.append('Discriminator')
            titleEmoji.append('🔢')
            embed.add_field(name="Old discriminator",value=before.discriminator)
            embed.add_field(name="New discriminator",value=after.discriminator)
            await updateLastActive(after, datetime.datetime.now(), 'updated their discriminator')
        if before.name != after.name:
            titles.append('Username')
            titleEmoji.append('📄')
            embed.add_field(name="Old username",value=before.name)
            embed.add_field(name="New username",value=after.name)
            await updateLastActive(after, datetime.datetime.now(), 'updated their username')
            asyncio.create_task(database.AppendUsernameHistory(after))
            asyncio.create_task(database.VerifyUser(membObj, bot))
        if len(titles) == 3: embed.title = f"👤{''.join(titleEmoji)}✏User's {', '.join(titles)} updated"
        else: embed.title = f"👤{''.join(titleEmoji)}✏User's {' & '.join(titles)} updated"
        embed.set_footer(text=f'User ID: {after.id}')
        for server in servers:
            try:
                #data['server'] = server.id
                if logEnabled(server, "member") and memberGlobal(server) != 0:
                    #if await database.SummarizeEnabled(server, 'member'):
                    #    summaries.get(str(server.id)).add('member', 9, datetime.datetime.now(), data, embed)
                    #else:
                    timestampedEmbed = copy.deepcopy(embed)
                    timestampedEmbed.description += f'🕰Precise Timestamp: {received + datetime.timedelta(hours=self.bot.lightningLogging.get(server.id).get("offset")):%b %d, %Y • %I:%M:%S %p}'
                    msg = await (await database.GetLogChannel(server, "member")).send(embed=embed)
                    await VerifyLightningLogs(msg, 'member')
            except: pass
        for s in servers: asyncio.create_task(database.VerifyServer(s, bot))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot joins a server'''
        await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name="{} servers".format(len(self.bot.guilds)), type=discord.ActivityType.watching))
        await self.globalLogChannel.send(embed=discord.Embed(title="{}Joined server".format(self.whitePlus),description='{} {}'.format(guild.name, guild.id),timestamp=datetime.datetime.utcnow(),color=0x008000))
        asyncio.create_task(database.VerifyServer(guild, bot))
        for member in guild.members:
            await database.VerifyUser(member, bot)
        post=None
        content="Thank you for inviting me to your server!\nTo configure me, you can connect your Discord account and enter your server's settings here: <https://disguard.herokuapp.com>\n{}Please wait while I index your server's messages...".format(self.loading)
        if guild.system_channel is not None:
            try: post = await guild.system_channel.send(content) #Update later to provide more helpful information
            except discord.Forbidden: pass
        if post is None:
            for channel in guild.text_channels:
                if 'general' in channel.name:
                    try: 
                        post = await channel.send(content) #Update later to provide more helpful information
                        break
                    except discord.Forbidden: pass
        await asyncio.gather(*[self.indexServer(c) for c in guild.text_channels])
        indexed[guild.id] = True
        try: await post.edit(content="Thank you for inviting me to your server!\nTo configure me, you can connect your Discord account and enter your server's settings here: <https://disguard.herokuapp.com>")
        except: pass

    async def indexServer(self, channel):
        path = f'{indexes}/{channel.guild.id}/{channel.id}'
        try: os.makedirs(path)
        except FileExistsError: pass
        indexData = {}
        try: 
            async for message in channel.history(limit=None):
                if str(message.id) in indexData.keys(): 
                    break 
                indexData[message.id] = {'author0': message.author.id, 'timestamp0': message.created_at.isoformat(), 'content0': message.content if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<No content>"}
            indexData = json.dumps(indexData, indent=4)
            with open(f'{path}.json', "w+") as f:
                f.write(indexData)
        except Exception as e: print(f'Index error for {channel.guild.name} - {channel.name}: {e}')

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        global bot
        if logEnabled(before, 'server'):
            embed=discord.Embed(title="✏Server updated (React with ℹ to view server details)",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
            content=None
            if readPerms(before, 'server'):
                try:
                    async for log in before.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.guild_update:
                            embed.description= "By: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                            await updateLastActive(log.user, datetime.datetime.now(), 'updated a server')
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
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
                reactions = ['ℹ']
                #if await database.SummarizeEnabled(before, 'server'):
                #    summaries.get(str(before.id)).add('server', 10, datetime.datetime.now(), data, embed,content=content, reactions=reactions)
                #else:
                message = await logChannel(before, 'server').send(content=content,embed=embed)
                for r in reactions: await message.add_reaction(r)
                await VerifyLightningLogs(message, 'server')
        asyncio.create_task(database.VerifyServer(after, bot))

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot leaves a server'''
        await self.globalLogChannel.send(embed=discord.Embed(title="❌Left server",description='{} {}'.format(guild.name, guild.id),timestamp=datetime.datetime.utcnow(),color=0xff0000))
        await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name="{} servers".format(len(self.bot.guilds)), type=discord.ActivityType.watching))
        asyncio.create_task(database.VerifyServer(guild, bot))
        for member in guild.members:
            await database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is created'''
        global bot
        if logEnabled(role.guild, "role"):
            content=None
            #data = {'role': role.id, 'name': role.name, 'server': role.guild.id}
            embed=discord.Embed(title="🚩{}Role created".format(self.whitePlus),timestamp=datetime.datetime.utcnow(),description=" ",color=0x008000)
            embed.description="Name: "+role.name if role.name != "new role" else ""
            embed.set_footer(text='Role ID: {}'.format(role.id))
            if readPerms(role.guild, "role"):
                try:
                    async for log in role.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.role_create: 
                            embed.description+="\nCreated by: "+log.user.mention+" ("+log.user.name+")"
                            await updateLastActive(log.user, datetime.datetime.now(), 'created a role')
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
            #if await database.SummarizeEnabled(role.guild, 'role'):
            #    summaries.get(str(role.guild.id)).add('role', 11, datetime.datetime.now(), data, embed,content=content)
            #else:
            msg = await (logChannel(role.guild, "role")).send(content=content,embed=embed)
            await VerifyLightningLogs(msg, 'role')
        asyncio.create_task(database.VerifyServer(role.guild, bot))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is deleted'''
        global bot
        if logEnabled(role.guild, "role"):
            #data = {'role': role.id, 'name': role.name, 'server': role.guild.id}
            content=None
            embed=discord.Embed(title="🚩❌Role deleted",description="Role: "+role.name,timestamp=datetime.datetime.utcnow(),color=0xff0000)
            embed.set_footer(text='Role ID: {}'.format(role.id))
            if readPerms(role.guild, "role"):
                try:
                    async for log in role.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.role_delete: 
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
                            await updateLastActive(log.user, datetime.datetime.now(), 'deleted a role')
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
            embed.description+="\n:warning: "+str(len(role.members))+" members lost this role :warning:"
            #if await database.SummarizeEnabled(role.guild, 'role'):
            #    summaries.get(str(role.guild.id)).add('role', 12, datetime.datetime.now(), data, embed,content=content)
            #else:
            msg = await (logChannel(role.guild, "role")).send(content=content,embed=embed)
            await VerifyLightningLogs(msg, 'role')
        asyncio.create_task(database.VerifyServer(role.guild, bot))
        for member in role.members:
            await database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is updated'''
        global bot
        if logEnabled(before.guild, "role"):
            content=None
            data = {'server': before.guild.id, 'role': before.id, 'oldName': before.name, 'newName': after.name}
            color=0x0000FF if before.color == after.color else after.color
            embed=discord.Embed(title="🚩✏Role was updated (React with ℹ to view role details)",description="Name: "+ after.name if before.name == after.name else "Name: "+before.name+" → "+after.name,color=color,timestamp=datetime.datetime.utcnow())
            if readPerms(before.guild, "role"):
                try:
                    async for log in before.guild.audit_logs(limit=1): #Color too
                            if log.action == discord.AuditLogAction.role_update:
                                embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                                await updateLastActive(log.user, datetime.datetime.now(), 'updated a role')
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
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
                #if await database.SummarizeEnabled(before.guild, 'role'):
                #    summaries.get(str(before.guild.id)).add('role', 13, datetime.datetime.now(), data, embed,content=content, reactions=reactions)
                #else:
                message = await logChannel(before.guild, "role").send(content=content,embed=embed)
                for reac in reactions: await message.add_reaction(reac)
                await VerifyLightningLogs(message, 'role')
        if before.name != after.name: asyncio.create_task(database.VerifyServer(after.guild, bot))
        for member in after.members:
            await database.VerifyUser(member, bot)
    
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        '''[DISCORD API METHOD] Called when emoji list is updated (creation, update, deletion)'''
        if not logEnabled(guild, "emoji"):
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
        if readPerms(guild, "emoji"):
            try:
                async for log in guild.audit_logs(limit=1):
                    if log.action == discord.AuditLogAction.emoji_delete or log.action==discord.AuditLogAction.emoji_create or log.action==discord.AuditLogAction.emoji_update:
                        embed.description = "By: "+log.user.mention+" ("+log.user.name+")"
                        embed.set_thumbnail(url=log.user.avatar_url)
                        await updateLastActive(log.user, datetime.datetime.now(), 'updated emojis somewhere')
            except discord.Forbidden:
                content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: `View Audit Log`"
        if len(before) > len(after): #Emoji was removed
            embed.title="❌Emoji removed"
            data['removed'] = [{'emoji': a.id, 'name': a.name} for a in before if a not in after]
            for emoji in before:
                if emoji not in after:
                    embed.add_field(name=emoji.name,value=str(emoji))
                    embed.set_footer(text="Emoji ID: "+str(emoji.id))
                    embed.set_image(url=emoji.url)
        elif len(after) > len(before): #Emoji was added
            embed.title="{}Emoji created".format(self.whitePlus)
            data['added'] = [{'emoji': a.id, 'name': a.name} for a in after if a not in before]
            for emoji in after:
                if emoji not in before:
                    embed.add_field(name=emoji.name,value=str(emoji))
                    embed.set_footer(text="Emoji ID: "+str(emoji.id))
                    embed.set_image(url=emoji.url)
        else: #Emoji was updated
            embed.title="✏Emoji list updated"
            data['updated'] = [{'emoji': before[a].id, 'oldName': before[a].name, 'newName': after[a].name} for a in range(len(before))]
            embed.set_footer(text="")
            for a in range(len(before)):
                if before[a].name != after[a].name:
                    embed.add_field(name=before[a].name+" → "+after[a].name,value=str(before[a]))
                    embed.set_footer(text=embed.footer.text+"Emoji ID: "+str(before[a].id))
                    embed.set_image(url=before[a].url)
        if len(embed.fields)>0:
            #if await database.SummarizeEnabled(guild, 'emoji'):
            #    summaries.get(str(guild.id)).add('emoji', 14, datetime.datetime.now(), data, embed,content=content)
            #else:
            msg = await (logChannel(guild, "emoji")).send(content=content,embed=embed)
            await VerifyLightningLogs(msg, 'emoji')
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not logEnabled(member.guild, 'voice'):
            return
        embed=discord.Embed(title="Voice Channel update",description=member.mention,timestamp=datetime.datetime.utcnow(),color=0x0000FF)
        data = {'server': member.guild.id, 'member': member.id, 'name': member.name}
        data['oldChannel'] = before.channel.id if before.channel is not None else None
        data['newChannel'] = after.channel.id if after.channel is not None else None
        if before.afk != after.afk:
            if after.afk: embed.add_field(name="😴",value="Went AFK (was in "+before.channel.name+")")
            else: embed.add_field(name='🚫😴',value='No longer AFK; currently in {}'.format(after.channel.name))
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
            if not readPerms(member.guild, 'voice'): #the readPerms variable is used here to determine mod-only actions for variable convenience since audit logs aren't available
                await updateLastActive(member, datetime.datetime.now(), 'voice channel activity')
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
        #if await database.SummarizeEnabled(member.guild, 'voice'):
        #    summaries.get(str(member.guild.id)).add('voice', 15, datetime.datetime.now(), data, embed)
        #else:
        msg = await (logChannel(member.guild, 'voice')).send(embed=embed)
        await VerifyLightningLogs(msg, 'voice')

    '''The following listener methods are used for lastActive tracking; not logging right now'''

    @commands.Cog.listener()
    async def on_typing(self, c, u, w):
        await updateLastActive(u, datetime.datetime.now(), 'started typing somewhere')

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, p):
        await updateLastActive(self.bot.get_user(p.user_id), datetime.datetime.now(), 'removed a reaction')

    @commands.Cog.listener()
    async def on_webhooks_update(self, c):
        await asyncio.sleep(5)
        await updateLastActive((await c.guild.audit_logs(limit=1).flatten())[0].user, datetime.datetime.now(), 'updated webhooks')

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        encounter = datetime.datetime.now()
        if isinstance(error, commands.CommandNotFound): return
        m = await ctx.send(f'⚠ {error}')
        #traceback.print_exception(type(error), error, error.__traceback__)
        while True:
            await m.add_reaction('ℹ')
            def infoCheck(r,u): return str(r) == 'ℹ' and u.id == ctx.author.id and r.message.id == m.id
            await self.bot.wait_for('reaction_add', check=infoCheck)
            try: await m.clear_reactions()
            except: pass
            await m.edit(content=self.loading)
            embed=discord.Embed(title='⚠An error has occured⚠',description=f"""{error}\n\n⬆: Collapse information\n{self.disguard}: Send this to my developer via my official server\n\n[Hover for traceback]({m.jump_url} '{''.join(traceback.format_exception(type(error), error, error.__traceback__, 3)[:5])}')""",timestamp=datetime.datetime.utcnow(),color=red)
            embed.add_field(name='Command',value='{}{}'.format(ctx.prefix, ctx.command))
            embed.add_field(name='Server',value='{} ({})'.format(ctx.guild.name, ctx.guild.id) if ctx.guild is not None else 'N/A')
            embed.add_field(name='Channel',value='{} ({}){}'.format(ctx.channel.name, ctx.channel.id, '(NSFW)' if ctx.channel.is_nsfw() else '') if type(ctx.channel) is discord.TextChannel else 'DMs')
            embed.add_field(name='Author',value='{} ({})'.format(ctx.author.name, ctx.author.id))
            embed.add_field(name='Message',value='{} ({})'.format(ctx.message.content, ctx.message.id))
            embed.add_field(name='Occurence',value=encounter.strftime('%b %d, %Y • %I:%M %p EST'))
            await m.edit(content=None,embed=embed)
            for r in ['⬆️', self.disguard]: await m.add_reaction(r)
            def navigCheck(r,u): return str(r) == '⬆️' or r.emoji == self.disguard and u.id == ctx.author.id and r.message.id == m.id
            r = await self.bot.wait_for('reaction_add', check=navigCheck)
            if type(r[0].emoji) is discord.Emoji: 
                log = await bot.get_channel(620787092582170664).send(embed=embed)
                await m.edit(content='A copy of this embed has been sent to my official server ({}). If you would like to delete this from there for whatever reason, react with the ❌.'.format(bot.get_channel(620787092582170664).mention))
                await m.add_reaction('❌')
                def check2(r, u): return str(r) == '❌' and u.id == ctx.author.id and r.message.id == m.id
                await bot.wait_for('reaction_add', check=check2)
                await m.edit(content=self.loading)
                try: await m.clear_reactions()
                except: pass
                await log.delete()
                await m.edit(content='⚠An error occured: **{}**, and I was unable to execute your command'.format(str(error)),embed=None)
            try: await m.clear_reactions()
            except: pass
            await m.edit(content=f'⚠ {error}', embed=None)

    @commands.command()
    async def pause(self, ctx, *args):
        '''Pause logging or antispam for a duration'''
        status = await ctx.send(str(self.loading) + "Please wait...")
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
            if ctx.channel !=logChannel(ctx.guild, 'message'):
                await logChannel(ctx.guild, 'message').send(classify+" was paused by "+ctx.author.name)
            await database.PauseMod(ctx.guild, classify.lower())
            self.bot.lightningLogging[ctx.guild.id]['antispam'][args[0]]['enabled'] = False
            return
        duration = self.ParsePauseDuration((" ").join(args[1:]))
        embed=discord.Embed(title=classify+" was paused",description="by "+ctx.author.mention+" ("+ctx.author.name+")\n\n"+(" ").join(args[1:]),color=0x008000,timestamp=datetime.datetime.utcnow()+datetime.timedelta(seconds=duration))
        embed.set_footer(text="Logging will resume")
        embed.set_thumbnail(url=ctx.author.avatar_url)
        logged = await logChannel(ctx.guild, 'message').send(embed=embed)
        try:
            await logged.pin()
        except discord.Forbidden:
            pass
        await status.edit(content="✅",embed=embed)
        await database.PauseMod(ctx.guild, classify.lower())
        self.bot.lightningLogging[ctx.guild.id][args[0]]['enabled'] = False
        await asyncio.sleep(duration)
        await database.ResumeMod(ctx.guild, classify.lower())
        self.bot.lightningLogging[ctx.guild.id][args[0]]['enabled'] = True
        try:
            await logged.delete()
        except discord.Forbidden:
            pass
        await logChannel(ctx.guild, 'message').send(classify+" was unpaused",delete_after=60*60*24)
        
    @commands.command()
    async def unpause(self, ctx, *args):
        if len(args) < 1: return await ctx.send("Please provide module `antispam` or `logging` to unpause")
        args = [a.lower() for a in args]
        if 'antispam' in args:
            await database.ResumeMod(ctx.guild, 'antispam')
            self.bot.lightningLogging[ctx.guild.id]['antispam']['enabled'] = True
            await ctx.send("✅Successfully resumed antispam moderation")
        if 'logging' in args:
            await database.ResumeMod(ctx.guild, 'cyberlog')
            self.bot.lightningLogging[ctx.guild.id]['cyberlog']['enabled'] = True
            await ctx.send("✅Successfully resumed logging")

    @commands.command()
    async def history(self, ctx, target: typing.Optional[discord.Member] = None, *, mod = ''):
        '''Viewer for custom status, username, and avatar history
        •If no member is provided, it will default to the command author
        •If no module is provided, it will default to the homepage'''
        await ctx.trigger_typing()
        if target is None: target = ctx.author
        p = prefix(ctx.guild)
        embed=discord.Embed(color=yellow)
        letters = [letter for letter in ('🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿')]
        def navigationCheck(r, u): return str(r) in navigationList and u.id == ctx.author.id and r.message.id == message.id
        async def viewerAbstraction():
            e = copy.deepcopy(embed)
            e.description = ''
            tailMappings = {'avatar': 'imageURL', 'username': 'name', 'customStatus': 'name'}
            backslash = '\\'
            data = self.bot.lightningUsers[target.id].get(f'{mod}History')
            e.description = f'{len(data) if len(data) < 19 else 19} / {len(data)} entries shown; oldest on top\nWebsite portal coming soon'
            if mod == 'avatar': e.description += '\nTo set an entry as the embed thumbnail, react with that letter'
            if mod == 'customStatus': e.description += '\nTo set a custom emoji as the embed thumbnail, react with that letter'
            for i, entry in enumerate(data[-19:]): #first twenty entries because that is the max number of reactions
                if i > 0:
                    span = entry.get('timestamp') - prior.get('timestamp')
                    hours, minutes, seconds = span.seconds // 3600, (span.seconds // 60) % 60, span.seconds - (span.seconds // 3600) * 3600 - ((span.seconds // 60) % 60) * 60
                    times = [seconds, minutes, hours, span.days]
                    distanceDisplay = []
                    for j in range(len(times) - 1, -1, -1):
                        if times[j] != 0: distanceDisplay.append(f'{times[j]} {units[j]}{"s" if times[j] != 1 else ""}')
                    if len(distanceDisplay) == 0: distanceDisplay = ['0 seconds']
                prior = entry
                timestampString = f'{entry.get("timestamp") + datetime.timedelta(hours=timeZone(ctx.guild) if ctx.guild is not None else -4):%b %d, %Y • %I:%M %p} {nameZone(ctx.guild) if ctx.guild is not None else "EST"}'
                if mod in ('avatar', 'customStatus'): timestampString += f' {"• " + (backslash + letters[i]) if mod == "avatar" or (mod == "customStatus" and entry.get("emoji") and len(entry.get("emoji")) > 1) else ""}'
                e.add_field(name=timestampString if i == 0 else f'**{distanceDisplay[0]} later** • {timestampString}', value=f'''> {entry.get("emoji") if entry.get("emoji") and len(entry.get("emoji")) == 1 else f"[Custom Emoji]({entry.get('emoji')})" if entry.get("emoji") else ""} {entry.get(tailMappings.get(mod)) if entry.get(tailMappings.get(mod)) else ""}''', inline=False)
            headerTail = f'{"🏠 Home" if mod == "" else "🖼 Avatar History" if mod == "avatar" else "📝 Username History" if mod == "username" else "💭 Custom Status History"}'
            header = f'📜 Attribute History / 👮 / {headerTail}'
            header = f'📜 Attribute History / 👮 {target.name:.{63 - len(header)}} / {headerTail}'
            footerText = 'Data from June 10, 2020 and on • Data before June 14 may be missing'
            if mod == 'customStatus': footerText = 'Data from June 10, 2020 and on • Data before June 17 may be missing'
            e.set_footer(text=footerText)
            e.title = header
            return e, data[-19:]
        while True:
            embed=discord.Embed(color=yellow)
            if any(attempt in mod.lower() for attempt in ['avatar', 'picture', 'pfp']): mod = 'avatar'
            elif any(attempt in mod.lower() for attempt in ['name']): mod = 'username'
            elif any(attempt in mod.lower() for attempt in ['status', 'emoji', 'presence', 'quote']): mod = 'customStatus'
            elif mod != '': 
                members = await self.FindMoreMembers(ctx.guild.members, mod)
                members.sort(key = lambda x: x.get('check')[1], reverse=True)
                if len(members) == 0: return await ctx.send(embed=discord.Embed(description=f'Unknown history module type or invalid user \"{mod}\"\n\nUsage: `{"." if ctx.guild is None else p}history |<member>| |<module>|`\n\nSee the [help page](https://disguard.netlify.app/history.html) for more information'))
                target = members[0].get('member')
                mod = ''
            headerTail = f'{"🏠 Home" if mod == "" else "🖼 Avatar History" if mod == "avatar" else "📝 Username History" if mod == "username" else "💭 Custom Status History"}'
            header = f'📜 Attribute History / 👮 / {headerTail}'
            header = f'📜 Attribute History / 👮 {target.name:.{63 - len(header)}} / {headerTail}'
            embed.title = header
            navigationList = ['🖼', '📝', '💭']
            if mod == '':
                try: await message.clear_reactions()
                except UnboundLocalError: pass
                embed.description=f'Welcome to the attribute history viewer! Currently, the following options are available:\n🖼: Avatar History (`{p}history avatar`)\n📝: Username History(`{p}history username`)\n💭: Custom Status History(`{p}history status`)\n\nReact with your choice to enter the respective module'
                try: await message.edit(embed=embed)
                except UnboundLocalError: message = await ctx.send(embed=embed)
                for emoji in navigationList: await message.add_reaction(emoji)
                result = await self.bot.wait_for('reaction_add', check=navigationCheck)
                if str(result[0]) == '🖼': mod = 'avatar'
                elif str(result[0]) == '📝': mod = 'username'
                elif str(result[0]) == '💭': mod = 'customStatus'
            newEmbed, data = await viewerAbstraction()
            try: await message.edit(embed=newEmbed)
            except UnboundLocalError: message = await ctx.send(embed=newEmbed)
            await message.clear_reactions()
            navigationList = ['🏠']
            if mod == 'avatar': navigationList += letters[:len(data)]
            if mod == 'customStatus':
                for letter in letters[:len(data)]:
                    if newEmbed.fields[letters.index(letter)].name.endswith(letter): navigationList.append(letter)
            for emoji in navigationList: await message.add_reaction(emoji)
            cache = '' #Stores last letter reaction, if applicable, to remove reaction later on
            while mod != '':
                result = await self.bot.wait_for('reaction_add', check=navigationCheck)
                if str(result[0]) == '🏠': mod = ''
                else: 
                    value = newEmbed.fields[letters.index(str(result[0]))].value
                    newEmbed.set_thumbnail(url=value[value.find('>')+1:].strip() if mod == 'avatar' else value[value.find('(')+1:value.find(')')])
                    headerTail = '🏠 Home' if mod == '' else '🖼 Avatar History' if mod == 'avatar' else '📝 Username History' if mod == 'username' else '💭 Custom Status History'
                    header = f'📜 Attribute History / 👮 / {headerTail}'
                    header = f'📜 Attribute History / 👮 {target.name:.{50 - len(header)}} / {headerTail}'
                    newEmbed.title = header
                    if cache: await message.remove_reaction(cache, result[1])
                    cache = str(result[0])
                    await message.edit(embed=newEmbed)
    
    @commands.guild_only()
    @commands.command()
    async def info(self, ctx, *args): #queue system: message, embed, every 3 secs, check if embed is different, edit message to new embed
        import emoji
        arg = ' '.join([a.lower() for a in args])
        message = await ctx.send('{}Searching'.format(self.loading))
        mainKeys=[]
        main=discord.Embed(title='Info results viewer',color=yellow,timestamp=datetime.datetime.utcnow())
        embeds=[]
        PartialEmojiConverter = commands.PartialEmojiConverter()
        if len(arg) > 0:
            members, roles, channels, emojis = tuple(await asyncio.gather(*[self.FindMembers(ctx.guild, arg), self.FindRoles(ctx.guild, arg), self.FindChannels(ctx.guild, arg), self.FindEmojis(ctx.guild, arg)]))
            try: logs = await ctx.guild.audit_logs(limit=None).flatten()
            except: logs = None
            try: invites = await ctx.guild.invites()
            except: invites = None
            try: bans = await ctx.guild.bans()
            except: bans = None
        else:
            await message.edit(content=f'{self.loading}Loading content')
            members = []
            roles = []
            channels = []
            emojis = []
        relevance = []
        indiv=None
        for m in members:
            mainKeys.append('👤{}'.format(m[0].name))
            embeds.append(m[0])
            relevance.append(m[1])
        for r in roles:
            mainKeys.append('🚩{}'.format(r[0].name))
            embeds.append(r[0])
            relevance.append(r[1])
        for c in channels:
            types = {discord.TextChannel: str(self.hashtag), discord.VoiceChannel: '🎙', discord.CategoryChannel: '📂'}
            mainKeys.append('{}{}'.format(types.get(type(c)), c[0].name))
            embeds.append(c[0])
            relevance.append(c[1])
        for e in emojis:
            mainKeys.append('{}{}'.format(e[0],e[0].name))
            embeds.append(e[0])
            relevance.append(e[1])
        if 'server' == arg or 'guild' == arg:
            mainKeys.append('ℹServer information')
            try: hooks = await ctx.guild.webhooks()
            except: hooks = None
            indiv = await self.ServerInfo(ctx.guild, logs, bans, hooks, invites)
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
            indiv = await self.InvitesListInfo(invites, logs)
        if 'bans' == arg:
            mainKeys.append('ℹBans information')
            indiv = await self.BansListInfo(bans, logs, ctx.guild)
        if len(arg) == 0:
            await message.edit(content='{}Loading content'.format(self.loading)) 
            mainKeys.append('ℹInformation about you :)')
            indiv = await asyncio.create_task(self.MemberInfo(ctx.author))
        if 'me' == arg:
            await message.edit(content='{}Loading content'.format(self.loading))
            mainKeys.append('ℹInformation about you :)')
            indiv = await self.MemberInfo(ctx.author)
        if any(s == arg for s in ['him', 'her', 'them', 'it']):
            await message.edit(content='{}Loading content'.format(self.loading))
            def pred(m): return m.author != ctx.guild.me and m.author != ctx.author
            author = sorted((await ctx.channel.history(limit=100).filter(pred).flatten()), key = lambda m: m.created_at, reverse=True)[-1].author
            mainKeys.append('ℹInformation about the person above you ({})'.format(author.name))
            indiv = await self.MemberInfo(author)
        if 'hardware' == arg:
            mainKeys.append('Information about me')
            indiv = await self.BotInfo(await self.bot.application_info())
        #Calculate relevance
        await message.edit(content='{}Loading content'.format(self.loading))
        reactions = ['⬅']
        if len(embeds) > 0 and indiv is None: 
            priority = embeds[relevance.index(max(relevance))]
            indiv=await self.evalInfo(priority, ctx.guild)
            indiv.set_author(name='⭐Best match ({}% relevant)\n(React ⬅ to see all results)'.format(relevance[embeds.index(priority)]))
        else:
            if indiv is not None: indiv.set_author(name='⭐Best match: {}'.format(mainKeys[0]))
            if len(embeds) == 0 and indiv is None: 
                main.description='{}0 results for *{}*, but I\'m still searching advanced results'.format(self.loading, arg)
                reactions = []
                indiv = main.copy()
        if len(arg) == 0: 
            await message.edit(content=None,embed=indiv)
            await message.add_reaction('🍰')
            def birthdayCheck(r,u): return u == ctx.author and r.message.id == message.id and str(r) == '🍰'
            await self.bot.wait_for('reaction_add',check=birthdayCheck)
            try: await message.delete()
            except: pass
            return await self.bot.get_cog('Birthdays').birthday(ctx, str(ctx.author.id))
        if len(embeds) > 1 or indiv is not None: await message.edit(content='{}Still searching in the background'.format(self.loading),embed=indiv)
        members, roles, channels, inv, emojis = tuple(await asyncio.gather(*[self.FindMoreMembers(ctx.guild.members, arg), self.FindMoreRoles(ctx.guild, arg), self.FindMoreChannels(ctx.guild, arg), self.FindMoreInvites(ctx.guild, arg), self.FindMoreEmojis(ctx.guild, arg)]))
        every=[]
        types = {discord.TextChannel: str(self.hashtag), discord.VoiceChannel: '🎙', discord.CategoryChannel: '📂'}
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
        if 'server' in arg or 'guild' in arg or arg in ctx.guild.name.lower() or ctx.guild.name.lower() in arg:
            try: hooks = await ctx.guild.webhooks()
            except: hooks = None
            every.append(InfoResult((await self.ServerInfo(ctx.guild, logs, bans, hooks, invites)), 'ℹServer information', compareMatch('server', arg)))
        if 'roles' in arg: every.append(InfoResult((await self.RoleListInfo(ctx.guild.roles, logs)), 'ℹRole list information', compareMatch('roles', arg)))
        if any(s in arg for s in ['members', 'people', 'users', 'bots', 'humans']): every.append(InfoResult((await self.MemberListInfo(ctx.guild.members)), 'ℹMember list information', compareMatch('members', arg)))
        if 'channels' in arg: every.append(InfoResult((await self.ChannelListInfo(ctx.guild.channels, logs)), 'ℹChannel list information', compareMatch('channels', arg)))
        if 'emoji' in arg or 'emotes' in arg: every.append(InfoResult((await self.EmojiListInfo(ctx.guild.emojis, logs)), 'ℹEmoji information', compareMatch('emoji', arg)))
        if 'invites' in arg: every.append(InfoResult((await self.InvitesListInfo(invites, logs)), 'ℹInvites information', compareMatch('invites', arg)))
        if 'bans' in arg: every.append(InfoResult((await self.BansListInfo(bans, logs, ctx.guild)), 'ℹBans information', compareMatch('bans', arg)))
        if any(s in arg for s in ['dev', 'owner', 'master', 'creator', 'author', 'disguard', 'bot', 'you']): every.append(InfoResult((await self.BotInfo(await bot.application_info())), '{}Information about me'.format(bot.get_emoji(569191704523964437)), compareMatch('disguard', arg)))
        every.sort(key=lambda x: x.relevance, reverse=True)
        md = 'Viewing {} - {} of {} results for *{}*{}\n**Type the number of the option to view**\n'
        md2=[]
        used = md.format(1 if len(every) >= 1 else 0, 20 if len(every) >= 20 else len(every), len(every), arg, ' (Arrows to scroll)' if len(every) >= 20 else '')
        main.description=used
        for result in range(len(every)): md2.append('\n{}: {}'.format(result + 1, every[result].mainKey))
        main.description+=''.join(md2[:20])
        main.set_author(name='{}: {}'.format(ctx.author.name, ctx.author.id),icon_url=ctx.author.avatar_url)
        if len(main.description) > 2048: main.description = main.description[:2048]
        if len(every) == 0 and indiv is None: return await message.edit(content=None,embed=main)
        elif len(every) == 1: 
            temp = await self.evalInfo(every[0].obj, ctx.guild)
            temp.set_author(name='⭐{}% relevant ({})'.format(every[0].relevance, every[0].mainKey))
            await message.edit(content=None,embed=temp)
        elif len(reactions) == 0: await message.edit(content=None,embed=main)
        loadContent = discord.Embed(title='{}Loading {}',color=yellow)
        if message.content is not None: await message.edit(content=None)
        past = False
        while True:
            if past or message.embeds[0].author.name is not discord.Embed.Empty and '⭐' in message.embeds[0].author.name: 
                if len(every) > 0: 
                    for r in ['⬅']: await message.add_reaction(r)
                try: desired = ctx.guild.get_member(int(message.embeds[0].footer.text[message.embeds[0].footer.text.find(':') + 1:]))
                except: desired = None
                def checkBday(r, u): return u == desired and not u.bot and r.message.id == message.id and str(r) == '🍰'
                def checkBack(r, u): return u == ctx.author and r.message.id == message.id and str(r) == '⬅'
                if 'member details' in message.embeds[0].title.lower() and desired: await message.add_reaction('🍰')
                d, p = await asyncio.wait([self.bot.wait_for('reaction_add', check=checkBack), self.bot.wait_for('reaction_add', check=checkBday)], return_when=asyncio.FIRST_COMPLETED)
                try: r = d.pop().result()
                except: pass
                for f in p: f.cancel()
                if str(r[0]) == '⬅':
                    await message.clear_reactions()
                    await message.edit(embed=main)
                else: 
                    await message.delete()
                    return await self.bot.get_cog('Birthdays').birthday(ctx, str(ctx.author.id))
            if len(every) >= 20:
                for r in ['◀', '▶']: await message.add_reaction(r)
            def check(m):
                try: return m.author==ctx.author and int(m.content) <= len(every)
                except: return False
            past = False
            def reacCheck(r, u): return str(r) in ['◀', '▶'] and u==ctx.author
            while not past:
                done, pending = await asyncio.wait([bot.wait_for('message', check=check, timeout=300), bot.wait_for('reaction_add', check=reacCheck, timeout=300)], return_when=asyncio.FIRST_COMPLETED)
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
                    self.AvoidDeletionLogging(stuff)
                    try: await stuff.delete()
                    except: pass
                    await message.edit(content=None,embed=(await self.evalInfo(every[int(stuff.content)-1].obj, ctx.guild)))
                    await message.add_reaction('⬅')
                    if 'member details' in message.embeds[0].title.lower(): await message.add_reaction('🍰')

    def ParsePauseDuration(self, s: str):
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

    async def ServerInfo(self, s: discord.Guild, logs, bans, hooks, invites):
        '''Formats an embed, displaying stats about a server. Used for ℹ navigation or `info` command'''
        embed=discord.Embed(title=s.name,description='' if s.description is None else '**Server description:** {}\n\n'.format(s.description),timestamp=datetime.datetime.utcnow(),color=yellow)
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
        for c in s.text_channels: 
            with open(f'{indexes}/{c.guild.id}/{c.id}.json') as f: 
                messages += len(json.load(f).keys())
        created = s.created_at
        txt='{}Text Channels: {}'.format(self.hashtag, len(s.text_channels))
        vc='{}Voice Channels: {}'.format('🎙', len(s.voice_channels))
        cat='{}Category Channels: {}'.format('📂', len(s.categories))
        embed.description+=('**Channel count:** {}\n{}\n{}\n{}'.format(len(s.channels),cat, txt, vc))
        onlineGeneral = 'Online: {} / {} ({}%)'.format(len([m for m in s.members if m.status != discord.Status.offline]), len(s.members), round(len([m for m in s.members if m.status != discord.Status.offline]) / len(s.members) * 100))
        offlineGeneral = 'Offline: {} / {} ({}%)'.format(len([m for m in s.members if m.status == discord.Status.offline]), len(s.members), round(len([m for m in s.members if m.status == discord.Status.offline]) / len(s.members) * 100))
        online='{}Online: {}'.format(self.online, len([m for m in s.members if m.status == discord.Status.online]))
        idle='{}Idle: {}'.format(self.idle, len([m for m in s.members if m.status == discord.Status.idle]))
        dnd='{}Do not disturb: {}'.format(self.dnd, len([m for m in s.members if m.status == discord.Status.dnd]))
        offline='{}Offline/invisible: {}'.format(self.offline, len([m for m in s.members if m.status == discord.Status.offline]))
        embed.description+='\n\n**Member count:** {}{}\n{}'.format(len(s.members),'' if s.max_members is None else '/{}'.format(s.max_members),'\n'.join([onlineGeneral, offlineGeneral, online, idle, dnd, offline]))
        embed.description+='\n\n**Features:** {}'.format(', '.join(s.features) if len(s.features) > 0 else 'None')
        embed.description+='\n\n**Nitro boosters:** {}/{}, **perks:** {}'.format(s.premium_subscription_count,perkDict.get(s.premium_tier),', '.join(perks))
        #embed.set_thumbnail(url=s.icon_url)
        embed.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nameZone(s), (datetime.datetime.utcnow()-created).days),inline=False)
        embed.add_field(name='Region',value=str(s.region))
        embed.add_field(name='AFK Timeout',value='{}s --> {}'.format(s.afk_timeout, s.afk_channel))
        if s.max_presences is not None: embed.add_field(name='Max Presences',value='{} (BETA)'.format(s.max_presences))
        embed.add_field(name='Mods need 2FA',value=mfa.get(s.mfa_level))
        embed.add_field(name='Verification',value=veri.get(str(s.verification_level)))
        embed.add_field(name='Explicit filter',value=s.explicit_content_filter)
        embed.add_field(name='Default notifications',value=str(s.default_notifications)[str(s.default_notifications).find('.')+1:])
        try: embed.add_field(name='Locale',value=s.preferred_locale)
        except: pass
        embed.add_field(name='Audit logs',value='N/A' if logs is None else len(logs))
        if s.system_channel is not None: embed.add_field(name='System channel',value='{}: {}'.format(s.system_channel.mention, ', '.join([k[0] for k in (iter(s.system_channel_flags))])))
        embed.add_field(name='Role count',value=len(s.roles) - 1)
        embed.add_field(name='Owner',value=s.owner.mention)
        embed.add_field(name='Banned members',value=0 if bans is None else len(bans))
        embed.add_field(name='Webhooks',value=0 if hooks is None else len(hooks))
        embed.add_field(name='Invites',value=0 if invites is None else len(invites))
        embed.add_field(name='Emojis',value='{}/{}'.format(len(s.emojis), s.emoji_limit))
        embed.add_field(name='Messages', value='about {}'.format(messages))
        embed.set_footer(text='Server ID: {}'.format(s.id))
        return embed

    async def ChannelInfo(self, channel: discord.abc.GuildChannel, invites, pins, logs):
        permString = None
        global bot
        types = {discord.TextChannel: str(self.hashtag), discord.VoiceChannel: '🎙', discord.CategoryChannel: '📂'}
        details = discord.Embed(title='{}{}'.format(types.get(type(channel)),channel.name), description='',color=yellow, timestamp=datetime.datetime.utcnow())
        details.set_footer(text='Channel ID: {}'.format(channel.id))
        if type(channel) is discord.TextChannel: details.description+=channel.mention
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
            temp.append('{:<60s}'.format(permissionKeys.get(k)))
            string='\n'.join(['     {}: {:>{diff}}'.format(kk.name, english.get(vv), diff=25 - len(kk.name)) for kk,vv in iter(v.items())])
            temp.append(string)
            permString = '```Channel permission overwrites\n{}```'.format('\n'.join(temp))
        created=channel.created_at + datetime.timedelta(hours=timeZone(channel.guild))
        updated = None
        if logs is not None:
            for log in logs:
                if log.action == discord.AuditLogAction.channel_update and (datetime.datetime.utcnow() - log.created_at).seconds > 600:
                    if log.target.id == channel.id:
                        updated = log.created_at + datetime.timedelta(hours=await database.GetTimezone(channel.guild))
                        break
        if updated is None: updated = created
        details.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nameZone(channel.guild), (datetime.datetime.utcnow()-created).days))
        details.add_field(name='Last updated',value='{}'.format('{} {} ({} days ago)'.format(updated.strftime("%b %d, %Y • %I:%M %p"),nameZone(channel.guild), (datetime.datetime.utcnow()-updated).days)))
        inviteCount = []
        for inv in iter(invites): inviteCount.append(inv.inviter)
        details.add_field(name='Invites to here',value='None' if len(inviteCount) == 0 else ', '.join(['{} by {}'.format(a[1], a[0].name) for a in iter(collections.Counter(inviteCount).most_common())]))
        if type(channel) is discord.TextChannel:
            details.add_field(name='Topic',value='{}{}'.format('<No topic>' if channel.topic is None or len(channel.topic) < 1 else channel.topic[:100], '' if channel.topic is None or len(channel.topic)<=100 else '...'),inline=False)
            details.add_field(name='Slowmode',value='{}s'.format(channel.slowmode_delay))
            with open(f'{indexes}/{channel.guild.id}/{channel.id}.json') as f: details.add_field(name='Message count',value=len(json.load(f).keys()))
            details.add_field(name='NSFW',value=channel.is_nsfw())
            details.add_field(name='News channel?',value=channel.is_news())
            details.add_field(name='Pins count',value=len(pins))
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
        created = r.created_at + datetime.timedelta(hours=timeZone(r.guild))
        updated = None
        for log in logs:
            if log.action == discord.AuditLogAction.role_update and (datetime.datetime.utcnow() - log.created_at).seconds > 600:
                if log.target.id == r.id:
                    updated = log.created_at + datetime.timedelta(hours=timeZone(r.guild))
                    break
        if updated is None: updated = created
        embed=discord.Embed(title='🚩Role: {}'.format(r.name),description='**Permissions:** {}'.format('Administrator' if r.permissions.administrator else ' • '.join([permissionKeys.get(p[0]) for p in iter(r.permissions) if p[1]])),timestamp=datetime.datetime.utcnow(),color=r.color)
        #embed.description+='\n**Position**:\n{}'.format('\n'.join(['{0}{1}{0}'.format('**' if sortedRoles[role] == r else '', sortedRoles[role].name) for role in range(start, start+6)]))
        embed.add_field(name='Displayed separately',value=r.hoist)
        embed.add_field(name='Externally managed',value=r.managed)
        embed.add_field(name='Mentionable',value=r.mentionable)
        embed.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nameZone(r.guild), (datetime.datetime.utcnow()-created).days))
        embed.add_field(name='Last updated',value='{}'.format('{} {} ({} days ago)'.format(updated.strftime("%b %d, %Y • %I:%M %p"), nameZone(r.guild), (datetime.datetime.utcnow()-updated).days)))
        embed.add_field(name='Belongs to',value='{} members'.format(len(r.members)))
        embed.set_footer(text='Role ID: {}'.format(r.id))
        return embed

    async def MemberInfo(self, m: discord.Member, addThumbnail=True):
        postCount = await self.MemberPosts(m)
        tz = timeZone(m.guild)
        nz = nameZone(m.guild)
        embed=discord.Embed(title='Member details',timestamp=datetime.datetime.utcnow(),color=m.color)
        mA = lastActive(m) #The dict (timestamp and reason) when a member was last active
        activeTimestamp = mA.get('timestamp') + datetime.timedelta(hours=timeZone(m.guild) + 4) #The timestamp value when a member was last active, with adjustments for timezones
        onlineTimestamp = lastOnline(m) + datetime.timedelta(hours=timeZone(m.guild) + 4) #The timestamp value when a member was last online, with adjustments for timezones
        onlineDelta = (datetime.datetime.now() - lastOnline(m)) #the timedelta between now and member's last online appearance
        activeDelta = (datetime.datetime.now() - mA.get('timestamp')) #The timedelta between now and when a member was last active
        units = ['second', 'minute', 'hour', 'day'] #Used in the embed description
        hours, minutes, seconds = activeDelta.seconds // 3600, (activeDelta.seconds // 60) % 60, activeDelta.seconds - (activeDelta.seconds // 3600) * 3600 - ((activeDelta.seconds // 60) % 60)*60
        activeTimes = [seconds, minutes, hours, activeDelta.days] #List of self explanatory values
        hours, minutes, seconds = onlineDelta.seconds // 3600, (onlineDelta.seconds // 60) % 60, onlineDelta.seconds - (onlineDelta.seconds // 3600) * 3600 - ((onlineDelta.seconds // 60) % 60)*60
        onlineTimes = [seconds, minutes, hours, onlineDelta.days]
        activeDisplay = []
        onlineDisplay = []
        for i in range(len(activeTimes)):
            if activeTimes[i] != 0: activeDisplay.append('{}{}'.format(activeTimes[i], units[i][0]))
            if onlineTimes[i] != 0: onlineDisplay.append('{}{}'.format(onlineTimes[i], units[i][0]))
        if len(activeDisplay) == 0: activeDisplay = ['0s']
        activities = {discord.Status.online: self.online, discord.Status.idle: self.idle, discord.Status.dnd: self.dnd, discord.Status.offline: self.offline}
        embed.description='{}{} {}\n\n{}Last active {} {} • {} ago ({}){}'.format(activities.get(m.status), m.mention, '' if m.nick is None else 'aka {}'.format(m.nick),
            'Last online {} {} • {} ago\n'.format(onlineTimestamp.strftime('%b %d, %Y • %I:%M %p'), nameZone(m.guild), list(reversed(onlineDisplay))[0]) if m.status == discord.Status.offline else '', activeTimestamp.strftime('%b %d, %Y • %I:%M %p'), nameZone(m.guild), list(reversed(activeDisplay))[0], mA.get('reason'), '\n•This member is likely {}invisible'.format(self.offline) if mA.get('timestamp') > lastOnline(m) and m.status == discord.Status.offline else '')
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
        embed.description+='\n\n**Roles:** {}\n\n**Permissions:** {}\n\nReact 🍰 to switch to Birthday Information view'.format(' • '.join([r.name for r in reversed(m.roles)]), 'Administrator' if m.guild_permissions.administrator else ' • '.join([permissionKeys.get(p[0]) for p in iter(m.guild_permissions) if p[1]]))
        boosting = m.premium_since
        joined = m.joined_at + datetime.timedelta(hours=tz)
        created = m.created_at + datetime.timedelta(hours=tz)
        if m.voice is None: voice = 'None'
        else:
            voice = '{}{} in {}{}'.format('🔇' if m.voice.mute or m.voice.self_mute else '', '🤐' if m.voice.deaf or m.voice.self_deaf else '','N/A' if m.voice.channel is None else m.voice.channel.name, ', AFK' if m.voice.afk else '')
        if boosting is None: embed.add_field(name='Boosting server',value='Nope')
        else:
            boosting += datetime.timedelta(hours=tz)
            embed.add_field(name='Boosting server',value='{}'.format('Since {} {} ({} days ago)'.format(boosting.strftime("%b %d, %Y • %I:%M %p"), nz, (datetime.datetime.utcnow()-boosting).days)))
        embed.add_field(name='📆Account created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nz, (datetime.datetime.utcnow()-created).days))
        embed.add_field(name='📆Joined server',value='{} {} ({} days ago)'.format(joined.strftime("%b %d, %Y • %I:%M %p"), nz, (datetime.datetime.utcnow()-joined).days))
        embed.add_field(name='📜Posts',value=postCount)
        embed.add_field(name='🎙Voice Chat',value=voice)
        if addThumbnail: embed.set_thumbnail(url=m.avatar_url)
        embed.set_footer(text='Member ID: {}'.format(m.id))
        return embed
        
    async def EmojiInfo(self, e: discord.Emoji, owner):
        created = e.created_at + datetime.timedelta(hours=timeZone(e.guild))
        embed = discord.Embed(title=e.name,description=str(e),timestamp=datetime.datetime.utcnow(),color=yellow)
        embed.set_image(url=e.url)
        embed.set_footer(text='Emoji ID: {}'.format(e.id))
        embed.add_field(name='Twitch emoji',value=e.managed)
        if owner is not None: embed.add_field(name='Uploaded by',value='{} ({})'.format(owner.mention, owner.name))
        embed.add_field(name='Server',value=e.guild.name)
        embed.add_field(name='📆Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nameZone(e.guild), (datetime.datetime.utcnow()-created).days))
        return embed

    async def PartialEmojiInfo(self, e: discord.PartialEmoji):
        embed=discord.Embed(title=e.name,description=str(e),timestamp=datetime.datetime.utcnow(),color=yellow)
        embed.set_image(url=e.url)
        embed.set_footer(text='Emoji ID: {}'.format(e.id))
        return embed

    async def InviteInfo(self, i: discord.Invite, s): #s: server
        embed=discord.Embed(title='Invite details',description=str(i),timestamp=datetime.datetime.utcnow(),color=yellow)
        embed.set_thumbnail(url=i.guild.icon_url)
        expires=datetime.datetime.utcnow() + datetime.timedelta(seconds=i.max_age) + datetime.timedelta(hours=timeZone(s))
        created = i.created_at + datetime.timedelta(hours=timeZone(s))
        embed.add_field(name='📆Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nameZone(s), (datetime.datetime.utcnow()-created).days))
        embed.add_field(name='⏰Expires',value='{} {}'.format(expires.strftime("%b %d, %Y • %I:%M %p"), nameZone(s)) if i.max_age > 0 else 'Never')
        embed.add_field(name='Server',value=i.guild.name)
        embed.add_field(name='Channel',value=i.channel.mention)
        embed.add_field(name='Author',value='{} ({})'.format(i.inviter.mention, i.inviter.name))
        embed.add_field(name='Used',value='{}/{} times'.format(i.uses, '∞' if i.max_uses == 0 else i.max_uses))
        embed.set_footer(text='Invite server ID: {}'.format(i.guild.id))
        #In the future, once bot is more popular, integrate server stats from other servers
        return embed

    async def BotInfo(self, app: discord.AppInfo):
        bpg = 1073741824 #Bytes per gig
        embed=discord.Embed(title='About Disguard',description='{0}{1}{0}'.format(bot.get_emoji(569191704523964437), app.description),timestamp=datetime.datetime.utcnow(),color=yellow)
        embed.description+=f'\n\nDISGUARD HOST SYSTEM INFORMATION\nCPU: {cpuinfo.get_cpu_info().get("brand")}\n•   Usage: {psutil.cpu_percent()}%\n​•   Core count: {psutil.cpu_count(logical=False)} cores, {psutil.cpu_count()} threads\n​​​​​​‍‍‍​​​•   {(psutil.cpu_freq().current / 1000):.2f} GHz current clock speed; {(psutil.cpu_freq().max / 1000):.2f} GHz max clock speed'
        embed.description+=f'\n​RAM: {(psutil.virtual_memory().total / bpg):.1f}GB total ({(psutil.virtual_memory().used / bpg):.1f}GB used, {(psutil.virtual_memory().free / bpg):.1f}GB free)'
        embed.description+=f'\nSTORAGE: {psutil.disk_usage("/").total // bpg}GB total ({psutil.disk_usage("/").used // bpg}GB used, {psutil.disk_usage("/").free // bpg}GB free)'
        embed.set_footer(text='My ID: {}'.format(app.id))
        embed.set_thumbnail(url=app.icon_url)
        embed.add_field(name='Developer',value=app.owner)
        embed.add_field(name='Public Bot',value=app.bot_public)
        embed.add_field(name='In development since',value='March 20, 2019')
        embed.add_field(name='Website with information',value=f'[Disguard Website](https://disguard.netlify.com/ \'https://disguard.netlify.com/\')')
        embed.add_field(name='Servers',value=len(bot.guilds))
        embed.add_field(name='Emojis',value=len(bot.emojis))
        embed.add_field(name='Users',value=len(bot.users))
        return embed

    async def EmojiListInfo(self, emojis, logs):
        '''Prereq: len(emojis) > 0'''
        embed=discord.Embed(title='{}\'s emojis'.format(emojis[0].guild.name),description='Total emojis: {}'.format(len(emojis)),timestamp=datetime.datetime.utcnow(),color=yellow)
        static = [str(e) for e in emojis if not e.animated]
        animated = [str(e) for e in emojis if e.animated]
        if len(static) > 0: embed.add_field(name='Static emojis: {}/{}'.format(len(static), emojis[0].guild.emoji_limit),value=''.join(static)[:1023],inline=False)
        if len(animated) > 0: embed.add_field(name='Animated emojis: {}/{}'.format(len(animated), emojis[0].guild.emoji_limit),value=''.join(animated)[:1023],inline=False)
        if logs is not None: embed.add_field(name='Total emojis ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.emoji_create])))
        return embed

    async def ChannelListInfo(self, channels, logs):
        '''Prereq: len(channels) > 0'''
        global bot
        codes = {discord.TextChannel: str(self.hashtag), discord.VoiceChannel: '🎙', discord.CategoryChannel: '📂'}
        embed=discord.Embed(title='{}\'s channels'.format(channels[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow)
        none=['(No category)'] if len([c for c in channels if type(c) is not discord.CategoryChannel and c.category is None]) else []
        none += ['|{}{}'.format(codes.get(type(c)), c.name) for c in channels if type(c) is not discord.CategoryChannel and c.category is None]
        for chan in channels[0].guild.categories:
            none.append('{}{}'.format(codes.get(type(chan)), chan.name))
            none+=['|{}{}'.format(codes.get(type(c)), c.name) for c in chan.channels]
        embed.description='Total channels: {}\n\n{}'.format(len(channels), '\n'.join(none))
        if logs is not None: embed.add_field(name='Total channels ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.channel_create])))
        return embed

    async def RoleListInfo(self, roles, logs):
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

    async def MemberListInfo(self, members):
        embed=discord.Embed(title='{}\'s members'.format(members[0].guild.name),description='',timestamp=datetime.datetime.utcnow(),color=yellow)
        posts=[]
        for channel in members[0].guild.text_channels:
            with open(f'{indexes}/{members[0].guild.id}/{channel.id}.json') as f: 
                posts += [message['author0'] for message in json.load(f).values()]
        most = ['{} with {}'.format(bot.get_user(a[0]).name, a[1]) for a in iter(collections.Counter(posts).most_common(1))][0]
        online=bot.get_emoji(606534231631462421)
        idle=bot.get_emoji(606534231610490907)
        dnd=bot.get_emoji(606534231576805386)
        offline=bot.get_emoji(606534231492919312)
        humans='👤Humans: {}'.format(len([m for m in members if not m.bot]))
        bots='🤖Bots: {}\n'.format(len([m for m in members if m.bot]))
        onlineGeneral = 'Online: {} / {} ({}%)'.format(len([m for m in members if m.status != discord.Status.offline]), len(members), round(len([m for m in members if m.status != discord.Status.offline]) / len(members) * 100))
        offlineGeneral = 'Offline: {} / {} ({}%)'.format(len([m for m in members if m.status == discord.Status.offline]), len(members), round(len([m for m in members if m.status == discord.Status.offline]) / len(members) * 100))
        online='{}Online: {}'.format(online, len([m for m in members if m.status == discord.Status.online]))
        idle='{}Idle: {}'.format(idle, len([m for m in members if m.status == discord.Status.idle]))
        dnd='{}Do not disturb: {}'.format(dnd, len([m for m in members if m.status == discord.Status.dnd]))
        offline='{}Offline/invisible: {}'.format(offline, len([m for m in members if m.status == discord.Status.offline]))
        embed.description+='\n\n**Member count:** {}{}\n{}'.format(len(members),'' if members[0].guild.max_members is None else '/{}'.format(members[0].guild.max_members),'\n'.join([humans, bots, onlineGeneral, offlineGeneral, online, idle, dnd, offline]))
        embed.add_field(name='Playing/Listening/Streaming',value=len([m for m in members if len(m.activities) > 0]))
        embed.add_field(name='Members with nickname',value=len([m for m in members if m.nick is not None]))
        embed.add_field(name='On mobile',value=len([m for m in members if m.is_on_mobile()]))
        embed.add_field(name='In voice channel',value=len([m for m in members if m.voice is not None]))
        embed.add_field(name='Most posts',value=most)
        embed.add_field(name='Moderators',value=len([m for m in members if m.guild_permissions.manage_guild]))
        embed.add_field(name='Administrators',value=len([m for m in members if m.guild_permissions.administrator]))
        return embed

    async def InvitesListInfo(self, invites, logs):
        embed=discord.Embed(title='{}\'s invites'.format(invites[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow)
        embed.description='Total invites: {}\n\n • {}'.format(len(invites), '\n • '.join(['discord.gg/**{}**: Goes to {}, created by {}'.format(i.code, i.channel.name, i.inviter.name) for i in invites]))[:2047]
        if logs is not None: embed.add_field(name='Total invites ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.invite_create])))
        return embed

    async def BansListInfo(self, bans, logs, s): #s=server
        embed=discord.Embed(title='{}\'s bans'.format(s.name),timestamp=datetime.datetime.utcnow(),color=yellow)
        embed.description='Users currently banned: {}'.format(len(bans))
        if len(bans) == 0: return embed
        null = embed.copy()
        array = []
        current = []
        if logs is not None:
            for b in bans:
                for l in logs:
                    if l.action == discord.AuditLogAction.ban and l.target == b.user:
                        created = l.created_at + datetime.timedelta(hours=await database.GetTimezone(s))
                        array.append('{}: Banned by {} on {} because {}'.format(l.target.name, l.user.name, created.strftime('%m/%d/%Y@%H:%M'), '(No reason specified)' if b.reason is None else b.reason))
                        current.append(b.user)
            other=[]
            for l in logs:
                if l.action == discord.AuditLogAction.ban and l.target not in current:
                    created = l.created_at + datetime.timedelta(hours=await database.GetTimezone(s))
                    other.append('{}: Banned by {} on {} because {}'.format(l.target.name, l.user.name, created.strftime('%m/%d/%Y@%H:%M'), '(No reason specified)' if l.reason is None else l.reason))
                    current.append(b.user)
        for b in bans:
            if b.user not in current: array.append('{}: Banned because {}'.format(b.user.name, '(No reason specified)' if b.reason is None else b.reason))
        embed.add_field(name='Banned now',value='\n'.join(array)[:1023],inline=False)
        if len(array) == 0: 
            null.description='Unable to provide ban info'
            return null
        if logs is not None: embed.add_field(name='Banned previously',value='\n\n'.join([' • {}'.format(o) for o in other])[:1023])
        return embed

    async def MemberPosts(self, m: discord.Member):
        messageCount=0
        for channel in m.guild.text_channels: 
            with open(f'{indexes}/{m.guild.id}/{channel.id}.json') as f:
                loaded = json.load(f)
                messageCount += len([k for k, v in loaded.items() if m.id == v['author0']])
        return messageCount

    # async def calculateMemberPosts(self, m: discord.Member, p):
    #     try: return len([f for f in os.listdir(p) if str(m.id) in f])
    #     except FileNotFoundError: return 0

    # async def MostMemberPosts(self, g: discord.Guild):
    #     posts=[]
    #     for channel in g.text_channels: posts += await self.bot.loop.create_task(self.calculateMostMemberPosts(f'{indexes}/{g.id}/{channel.id}'))
    #     return ['{} with {}'.format(bot.get_user(a[0]).name, a[1]) for a in iter(collections.Counter(posts).most_common(1))][0]

    # async def calculateMostMemberPosts(self, p):
    #     with open(p) as f:
    #         return [int(v['author0']) for v in json.load(f).values()]
    #     #return [int(f[f.find('_')+1:f.find('.')]) for f in os.listdir(p)]

    # async def calculateChannelPosts(self, c):
    #     return len(os.listdir(f'{indexes}/{c.guild.id}/{c.id}'))

    def FindMember(self, g: discord.Guild, arg):
        def check(m): return any([arg.lower() == m.nick,
            arg.lower() in m.name.lower(),
            arg in m.discriminator,
            arg in str(m.id)]) 
        return discord.utils.find(check, g.members)

    async def FindMembers(self, g: discord.Guild, arg):
        '''Used for smart info command. Finds anything matching the filter'''
        arg = arg.lower()
        def check(m):
            if m.nick is not None and m.nick.lower() == arg: return compareMatch(arg, m.nick)
            if arg in m.name.lower(): return compareMatch(arg, m.name)
            if arg in m.discriminator: return compareMatch(arg, m.discriminator)
            if arg in str(m.id): return compareMatch(arg, str(m.id))
            return None
        return [(mem, check(mem)) for mem in g.members if check(mem) is not None]

    async def FindRoles(self, g: discord.Guild, arg):
        arg = arg.lower()
        def check(r):
            if arg in r.name.lower(): return compareMatch(arg, r.name)
            if arg in str(r.id): return compareMatch(arg, str(r.id))
            return None
        return [(rol, check(rol)) for rol in g.roles if check(rol) is not None]

    async def FindChannels(self, g: discord.Guild, arg):
        arg=arg.lower()
        def check(c): 
            if arg in c.name.lower(): return compareMatch(arg, c.name)
            if arg in str(c.id): return compareMatch(arg, str(c.id))
            return None
        return [(cha, check(cha)) for cha in g.channels if check(cha) is not None]

    async def FindEmojis(self, g: discord.Guild, arg):
        arg=arg.lower()
        def check(e): 
            if arg in e.name.lower(): return compareMatch(arg, e.name)
            if arg in str(e.id): return compareMatch(arg, str(e.id))
            return None
        return [(emo, check(emo)) for emo in g.emojis if check(emo) is not None]

    '''Split between initial findings and later findings - optimizations'''

    async def FindMoreMembers(self, members, arg):
        arg=arg.lower()
        def check(m):
            if type(m) is discord.Member and m.nick is not None and m.nick.lower() == arg.lower(): return 'Nickname is \'{}\''.format(m.nick.replace(arg, '**{}**'.format(arg))), compareMatch(arg, m.nick)
            if arg in m.name.lower(): return 'Username is \'{}\''.format(m.name).replace(arg, '**{}**'.format(arg)), compareMatch(arg, m.name)
            if arg in m.discriminator: return 'Discriminator is \'{}\''.format(m.discriminator).replace(arg, '**{}**'.format(arg)), compareMatch(arg, m.discriminator)
            if arg in str(m.id): return 'ID matches: \'{}\''.format(m.id).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(m.id))
            if arg in '<@!{}>'.format(m.id): return 'Mentioned', 100
            if type(m) is discord.Member and len(m.activities) > 0:
                if any(arg in a.name.lower() for a in m.activities if a.name is not None): return 'Playing \'{}\''.format([a.name for a in m.activities if a.name is not None and arg in a.name.lower()][0]).replace(arg, '**{}**'.format(arg)), compareMatch(arg, [a.name for a in m.activities if arg in a.name.lower()][0])
                if any(a.type is discord.ActivityType.listening for a in m.activities):
                    for a in m.activities:
                        try:
                            if a.type is discord.ActivityType.listening:
                                if arg in a.title.lower(): return 'Listening to {} by {}'.format(a.title.replace(arg, '**{}**'.format(arg)), ', '.join(a.artists)), compareMatch(arg, a.title)
                                elif any([arg in s.lower() for s in a.artists]): return 'Listening to {} by {}'.format(a.title, ', '.join(a.artists).replace(arg, '**{}**'.format(arg))), compareMatch(arg, [s for s in a.artists if arg in s.lower()][0])
                        except: pass
            if type(m) is discord.Member and arg in m.joined_at.strftime('%A %B %d %Y %B %Y').lower(): return 'Server join date appears to match your search', compareMatch(arg, m.created_at.strftime('%A%B%d%Y%B%Y'))
            if arg in m.created_at.strftime('%A %B %d %Y %B %Y').lower(): return 'Account creation date appears to match your search', compareMatch(arg, m.created_at.strftime('%A%B%d%Y%B%Y'))
            if type(m) is discord.Member and arg in str(m.status): return 'Member is \'{}\''.format(str(m.status).replace(arg, '**{}**'.format(arg))), compareMatch(arg, str(m.status))
            if type(m) is discord.Member and any(s in arg for s in ['mobile', 'phone']) and m.is_on_mobile(): return 'Is on mobile app'.replace(arg, '**{}**'.format(arg)), compareMatch(arg, 'mobile')
            if type(m) is discord.Member and (any(arg in r.name.lower() for r in m.roles) or any(arg in str(r.id) for r in m.roles)): return 'Has role matching **{}**'.format(arg), compareMatch(arg, [r.name for r in m.roles if arg in r.name.lower() or arg in str(r.id)][0])
            if type(m) is discord.Member and any([arg in [p[0] for p in iter(m.guild_permissions) if p[1]]]): return 'Has permissions: \'{}\''.format([p[0] for p in iter(m.guild_permissions) if p[1] and arg in p[0]][0].replace(arg, '**{}**'.format(arg))), compareMatch(arg, [p[0] for p in iter(m.guild_permissions) if p[1] and arg in p[0]][0])
            if 'bot' in arg and m.bot: return 'Bot account', compareMatch(arg, 'bot')
            if type(m) is not discord.Member: return None
            if m.voice is None: return None #Saves multiple checks later on since it's all voice attribute matching
            if any(s in arg for s in ['voice', 'audio', 'talk']): return 'In voice chat', compareMatch(arg, 'voice')
            if 'mute' in arg and (m.voice.mute or m.voice.self_mute): return 'Muted', compareMatch(arg, 'mute')
            if 'deaf' in arg and (m.voice.deaf or m.voice.self_deaf): return 'Deafened', compareMatch(arg, 'deaf')
            if arg in m.voice.channel.name.lower(): return 'Current voice channel matches **{}**'.format(arg), compareMatch(arg, m.voice.channel.name)
            return None
        return [{'member': m, 'check': check(m)} for m in members if check(m) is not None] #list of dicts
        
    async def FindMoreRoles(self, g: discord.Guild, arg):
        arg=arg.lower()
        def check(r):
            if arg in r.name.lower(): return 'Role name is \'{}\''.format(r.name.replace(arg, '**{}**'.format(arg))), compareMatch(arg, r.name)
            if arg in str(r.id): return 'Role ID is \'{}\''.format(r.id).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(r.id))
            if any([arg in [p[0] for p in iter(r.permissions) if p[1]]]): return 'Role has permissions: \'{}\''.format([p[0] for p in iter(r.permissions) if p[1] and arg in p[0]][0].replace(arg, '**{}**'.format(arg))), compareMatch(arg, [p[0] for p in iter(r.permissions) if p[1] and arg in p[0]][0])
            if any(['hoist' in arg, all(s in arg for s in ['display', 'separate'])]) and r.hoist: return 'Role is displayed separately', compareMatch(arg, 'separate')
            if 'managed' in arg and r.managed: return 'Role is externally managed', compareMatch(arg, 'managed')
            if 'mentionable' in arg and r.mentionable: return 'Role is mentionable', compareMatch(arg, 'mentionable')
            if arg in r.created_at.strftime('%A %B %d %Y %B %Y').lower(): return 'Role creation date appears to match your search', compareMatch(arg, r.created_at.strftime('%A%B%d%Y%B%Y'))
            return None
        return [{'role': r, 'check': check(r)} for r in g.roles if check(r) is not None] #List of dicts

    async def FindMoreChannels(self, g: discord.Guild, arg):
        arg=arg.lower()
        def check(c):
            if arg in c.name.lower(): return 'Name is \'{}\''.format(c.name.replace(arg, '**{}**'.format(arg))), compareMatch(arg, c.name)
            if arg in str(c.id): return 'ID is \'{}\''.format(c.id).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(c.id))
            if arg in c.created_at.strftime('%A %B %d %Y %B %Y').lower(): return 'Creation date appears to match your search', compareMatch(arg, c.created_at.strftime('%A%B%d%Y%B%Y'))
            if type(c) is discord.TextChannel and c.topic is not None and arg in c.topic: return 'Topic contains **{}**'.format(arg), compareMatch(arg, c.topic)
            if type(c) is discord.TextChannel and c.slowmode_delay > 0 and arg in str(c.slowmode_delay): return 'Slowmode is {}s'.format(c.slowmode_delay), compareMatch(arg, c.slowmode_delay)
            if type(c) is discord.TextChannel and c.is_news() and 'news' in arg: return 'News channel', compareMatch(arg, 'news')
            if type(c) is discord.VoiceChannel and arg in str(c.bitrate / 1000): return 'Bitrate: {}'.format(round(c.bitrate/1000)).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(round(c.bitrate/1000)))
            if type(c) is discord.VoiceChannel and c.user_limit > 0 and arg in str(c.user_limit): return 'User limit is {}'.format(c.user_limit).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(c.user_limit))
            if type(c) is not discord.VoiceChannel and c.is_nsfw() and 'nsfw' in arg: return 'NSFW', compareMatch(arg, 'nsfw')
            return None
        return [{'channel': c, 'check': check(c)} for c in g.channels if check(c) is not None]

    async def FindMoreInvites(self, g: discord.Guild, arg):
        arg=arg.lower()
        def check(i):
            if arg in i.code.lower(): return i.code.replace(arg, '**{}**'.format(arg)), compareMatch(arg, i.code)
            if arg in i.created_at.strftime('%A %B %d %Y %B %Y').lower(): return 'Creation date appears to match your search', compareMatch(arg, i.created_at.strftime('%A%B%d%Y%B%Y'))
            if i.temporary and 'temp' in arg: return 'Invite is temporary'
            if arg in str(i.uses): return 'Used {} times'.format(i.uses), compareMatch(arg, str(i.uses))
            if arg in str(i.max_uses): return 'Can be used {} times'.format(i.max_uses), compareMatch(arg, str(i.uses))
            if arg in i.inviter.name or arg in str(i.inviter.id): return 'Created by {}'.format(i.inviter.name).replace(arg, '**{}**'.format(arg)), compareMatch(arg, i.inviter.name)
            if arg in i.channel.name or arg in str(i.channel.id): return 'Goes to {}'.format(i.channel.name).replace(arg, '**{}**'.format(arg)), compareMatch(arg, i.channel.name)
            return None
        return [{'invite': i, 'check': check(i)} for i in (await g.invites()) if check(i) is not None]

    async def FindMoreEmojis(self, g: discord.Guild, arg):
        arg=arg.lower()
        def check(e):
            if arg in e.name.lower(): return 'Emoji name is {}'.format(e.name.replace(arg, '**{}**'.format(arg))), compareMatch(arg, e.name)
            if arg == str(e): return 'Emoji typed in search query', 100
            if arg in str(e.id): return 'ID is \'{}\''.format(e.id).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(e.id))
            if 'animated' in arg and e.animated: return 'Emoji is animated', compareMatch(arg, 'animated')
            if 'managed' in arg and e.managed: return 'Emoji is externally managed', compareMatch(arg, 'managed')
            if arg in e.created_at.strftime('%A %B %d %Y %B %Y').lower(): return 'Role creation date appears to match your search', compareMatch(arg, e.created_at.strftime('%A%B%d%Y%B%Y'))
            return None
        return [{'emoji': e, 'check': check(e)} for e in g.emojis if check(e) is not None]

    async def evalInfo(self, obj, g: discord.Guild):
        if type(obj) is discord.Embed: return obj
        logs = await obj.guild.audit_logs(limit=None).flatten()
        if type(obj) is discord.Member: return await self.MemberInfo(obj)
        if type(obj) is discord.Role: return await self.RoleInfo(obj, logs)
        if type(obj) in [discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]: return (await self.ChannelInfo(obj, await obj.invites(), await obj.pins(), logs))[1]
        if type(obj) is discord.Emoji: return await self.EmojiInfo(obj, (await obj.guild.fetch_emoji(obj.id)).user)
        if type(obj) is discord.Invite: return await self.InviteInfo(obj, g)
        if type(obj) is discord.PartialEmoji: return await self.PartialEmojiInfo(obj)

    def AvoidDeletionLogging(self, messages):
        '''Don't log the deletion of passed messages'''
        if type(messages) is list: self.pauseDelete += [m.id for m in messages]
        else: self.pauseDelete.append(messages.id)

def compareMatch(arg, search):
    return round(len(arg) / len(search) * 100)

async def VerifyLightningLogs(m: discord.Message, mod):
    '''Used to update things for the new lightning logging feature'''
    if not logEnabled(m.guild, mod): return await m.delete()
    if m.channel != logChannel(m.guild, mod):
        new = await logChannel(m.guild, mod).send(content=m.content,embed=m.embeds[0],attachments=m.attachments)
        for reac in m.reactions: await new.add_reaction(str(reac))
        return await m.delete()

async def updateServer(s: discord.Guild):
    lightningLogging[s.id] = await database.GetServer(s)

def ConfigureSummaries(b):
    global summaries
    for server in b.guilds:
        summaries[str(server.id)] = ServerSummary()
        members[server.id] = server.members

def modElement(s: discord.Guild, mod):
    '''Return the placement of the desired log module'''
    return lightningLogging.get(s.id).get('cyberlog').get('modules').index([x for x in lightningLogging.get(s.id).get('cyberlog').get('modules') if x.get('name').lower() == mod][0])

def logEnabled(s: discord.Guild, mod):
    return all([lightningLogging.get(s.id).get('cyberlog').get(mod).get('enabled'),
    lightningLogging.get(s.id).get('cyberlog').get('enabled'),
    [any([lightningLogging.get(s.id).get('cyberlog').get(mod).get('channel') is not None,
    lightningLogging.get(s.id).get('cyberlog').get(mod).get('defaultChannel') is not None])]])

def logChannel(s: discord.Guild, mod):
    modular = lightningLogging.get(s.id).get('cyberlog').get(mod).get('channel')
    default = lightningLogging.get(s.id).get('cyberlog').get('defaultChannel')
    return s.get_channel(default) if modular is None else s.get_channel(modular)

def logExclusions(channel: discord.TextChannel, member: discord.Member):
    return not any([channel.id in lightningLogging.get(channel.guild.id).get('cyberlog').get('channelExclusions'),
    member.id in lightningLogging.get(channel.guild.id).get('cyberlog').get('memberExclusions'),
    any([r.id in lightningLogging.get(channel.guild.id).get('cyberlog').get('roleExclusions') for r in member.roles])])

def memberGlobal(s: discord.Guild):
    return lightningLogging.get(s.id).get('cyberlog').get('memberGlobal')

def antispamObject(s: discord.Guild):
    return lightningLogging.get(s.id).get('antispam')

def readPerms(s: discord.Guild, mod):
    return lightningLogging.get(s.id).get('cyberlog').get(mod).get('read')

def nameZone(s: discord.Guild):
    return lightningLogging.get(s.id).get('tzname')

def timeZone(s: discord.Guild):
    return lightningLogging.get(s.id).get('offset')

def prefix(s: discord.Guild):
    return lightningLogging.get(s.id).get('prefix')

def getServer(s: discord.Guild):
    return lightningLogging.get(s.id)

def lastActive(u: discord.User):
    try: return lightningUsers.get(u.id).get('lastActive')
    except AttributeError: return {'timestamp': datetime.datetime.min, 'reason': 'not tracked yet'}

async def updateLastActive(u: discord.User, timestamp, reason):
    try: lightningUsers[u.id]['lastActive'] = {'timestamp': timestamp, 'reason': reason}
    except: pass
    asyncio.create_task(database.SetLastActive(u, timestamp, reason))

def lastOnline(u: discord.User):
    try: return lightningUsers.get(u.id).get('lastOnline')
    except AttributeError: return datetime.datetime.min

async def updateLastOnline(u: discord.User, timestamp):
    try: lightningUsers[u.id]['lastOnline'] = timestamp
    except: pass
    asyncio.create_task(database.SetLastOnline(u, timestamp))

def beginPurge(s: discord.Guild):
    '''Prevent logging of purge'''
    serverPurge[s.id] = True

def endPurge(s: discord.Guild):
    serverPurge[s.id] = False

def suffix(count: int):
    sfx='th'
    if count % 100 in [11, 12, 13]:
        sfx='th'
    elif count%10==1:
        sfx='st'
    elif count%10==2:
        sfx='nd'
    elif count%10==3:
        sfx='rd'
    return sfx


def setup(Bot):
    global bot
    Bot.add_cog(Cyberlog(Bot))
    bot = Bot