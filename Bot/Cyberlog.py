from inspect import trace
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
import math
import gc
import string
import codecs
import emojis
import asyncpraw

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

# yellow=0xffff00
# green=0x008000
# red=0xff0000
# blue=0x0000FF
# orange=0xD2691E

green = (0x008000, 0x66ff66)
blue = (0x0000FF, 0x6666ff)
red = (0xff0000, 0xff6666)
orange = (0xD2691E, 0xffc966)
yellow = (0xffff00, 0xffff66)

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
        self.emojis = {}
        #Emoji consortium: https://drive.google.com/drive/folders/14ttnIp6MkHdooCgMP167KNbgO-eeD3e8?usp=sharing
        for server in [560457796206985216, 403327720714665994, 495263898002522144]: #Disguard & RicoBot servers are currently being used for emoji hosting - with Pen Wars server being available for overflow reserves
            for e in bot.get_guild(server).emojis: self.emojis[e.name] = e
        self.bot = bot
        self.bot.lightningLogging = {}
        self.bot.lightningUsers = {}
        self.imageLogChannel = bot.get_channel(534439214289256478)
        self.globalLogChannel = bot.get_channel(566728691292438538)
        self.loading = self.emojis['loading']
        self.channelKeys = {'text': self.emojis['textChannel'], 'voice': self.emojis['voiceChannel'], 'category': self.emojis['folder'], 'private': self.emojis['hiddenVoiceChannel'], 'news': self.emojis['announcementsChannel'], 'store': self.emojis['storeChannel']}
        #self.permissionStrings = {} 0.2.25: Not used
        self.repeatedJoins = {}
        self.pins = {}
        self.categories = {}
        self.invites = {}
        self.roles = {}
        self.reactions = {}
        self.redditThreads = {}
        self.memberPermissions = {}
        self.memberVoiceLogs = {}
        #self.rawMessages = {} 0.2.25: Not used
        self.pauseDelete = []
        self.resumeToken = None
        self.channelCacheHelper = {}
        self.syncData.start()
        self.DeleteAttachments.start()
        self.trackChanges.start()

    def cog_unload(self):
        self.syncData.cancel()
        self.DeleteAttachments.cancel()
        self.trackChanges.cancel()

    @tasks.loop()
    async def trackChanges(self):
        #The global variables exist for the rare instances the cache data needs to be accessed outside of the Cyberlog class instance, in a read-only mode.
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
                        if change['operationType'] == 'update' and 'redditFeeds' in change['updateDescription']['updatedFields'].keys(): asyncio.create_task(self.redditFeedHandler(self.bot.get_guild(objectID)))
                        if change['operationType'] == 'update' and any([word in change['updateDescription']['updatedFields'].keys() for word in ('lastActive', 'lastOnline')]): continue
                        print(f'''{qlf}{change['clusterTime'].as_datetime() - datetime.timedelta(hours=5):%b %d, %Y • %I:%M:%S %p} - (database {change['operationType']} -- {change['ns']['db']} - {change['ns']['coll']}){f": {fullDocument[name]} - {', '.join([f' {k}' for k in change['updateDescription']['updatedFields'].keys()])}" if change['operationType'] == 'update' else ''}''')
            except Exception as e: print(f'Tracking error: {e}')
    
    @tasks.loop(hours = 6)
    async def syncData(self):
        #global lightningUsers
        #global lightningLogging
        global members
        print('Summarizing')
        started = datetime.datetime.now()
        rawStarted = datetime.datetime.now()
        try:
            if self.syncData.current_loop % 4 == 0: #This segment activates once per day
                if self.syncData.current_loop == 0: #This segment activates only once while the bot is up (on bootup)
                    await database.VerifyServers(self.bot, False, True)
                    asyncio.create_task(self.synchronizeDatabase(True))
                    def initializeCheck(m): return m.author.id == self.bot.user.id and m.channel == self.imageLogChannel and m.content == 'Synchronized'
                    await bot.wait_for('message', check=initializeCheck) #Wait for bot to synchronize database
                else: asyncio.create_task(self.synchronizeDatabase())
                await self.bot.get_cog('Birthdays').updateBirthdays()
            for g in self.bot.guilds:
                started = datetime.datetime.now()
                try:
                    generalChannel, announcementsChannel, moderatorChannel = await database.CalculateGeneralChannel(g, self.bot, True), await database.CalculateAnnouncementsChannel(g, self.bot, True), await database.CalculateModeratorChannel(g, self.bot, True)
                    print(f'{g.name}\n -general channel: {generalChannel}\n -announcements channel: {announcementsChannel}\n -moderator channel: {moderatorChannel}')
                except: pass
                await self.CheckDisguardServerRoles(g.members, mode=0, reason='Bot bootup check')
                self.memberPermissions[g.id] = {} #Ok, so then in the future, look into collections.defaultDict for this one, just like the ghost reaction logging
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
                                except (AttributeError, discord.HTTPException, aiohttp.client_exceptions.ClientPayloadError, aiohttp.client_exceptions.ClientOSError): pass
                                except (TypeError, IndexError):
                                    if not (await database.GetUser(m)).get('customStatusHistory'):
                                        asyncio.create_task(database.AppendCustomStatusHistory(m, None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), a.name)) #If the customStatusHistory is empty, we create the first entry
                                        updates.append('status')
                    except Exception as e: print(f'Custom status error for {m.name}: {e}')
                    try:
                        if m.name != self.bot.lightningUsers.get(m.id).get('usernameHistory')[-1].get('name'): 
                            asyncio.create_task(database.AppendUsernameHistory(m))
                            updates.append('username')
                    except (AttributeError, discord.HTTPException, aiohttp.client_exceptions.ClientPayloadError, aiohttp.client_exceptions.ClientOSError): pass
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
                    except (AttributeError, discord.HTTPException, aiohttp.client_exceptions.ClientPayloadError, aiohttp.client_exceptions.ClientOSError): pass
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
                    self.memberPermissions[g.id][m.id] = m.guild_permissions
                    if 'avatar' in updates: await asyncio.sleep((datetime.datetime.now() - memberStart).microseconds / 1000000)
                print(f'Member Management and attribute updates done in {(datetime.datetime.now() - started).seconds}s')
                started = datetime.datetime.now()
                for c in g.text_channels: 
                    try: self.pins[c.id] = [m.id for m in await c.pins()]
                    except (discord.Forbidden, aiohttp.client_exceptions.ClientOSError): pass
                for c in g.categories:
                    try: self.categories[c.id] = [c for c in c.channels]
                    except (discord.Forbidden, aiohttp.client_exceptions.ClientOSError): pass
                try: self.categories[g.id] = [c[1] for c in g.by_category() if c[0] is None]
                except (discord.Forbidden, aiohttp.client_exceptions.ClientOSError): pass
                print(f'Channel management done in {(datetime.datetime.now() - started).seconds}s')
                started = datetime.datetime.now()
                attachmentsPath = f'Attachments/{g.id}'
                indexesPath = f'{indexes}/{g.id}'
                for p in os.listdir(indexesPath):
                    if 'json' in p and not self.bot.get_channel(int(p[:p.find('.')])):
                        os.remove(f'{indexes}/{g.id}/{p}')
                for p in os.listdir(attachmentsPath):
                    if not self.bot.get_channel(int(p)):
                        shutil.rmtree(f'Attachments/{g.id}/{p}')
                print(f'Local file management done in {(datetime.datetime.now() - started).seconds}s')
                started = datetime.datetime.now()
                try:
                    self.invites[str(g.id)] = (await g.invites())
                    try: self.invites[str(g.id)+"_vanity"] = (await g.vanity_invite())
                    except (discord.HTTPException, aiohttp.client_exceptions.ClientOSError): pass
                except discord.Forbidden as e: print(f'Invite management error: Server {g.name}: {e.text}')
                except Exception as e: print(f'Invite management error: Server {g.name}\n{e}')
                print(f'Invite management done in {(datetime.datetime.now() - started).seconds}s')
                for r in g.roles: self.roles[r.id] = r.members #This allows the bot to properly display how many members had a role before it was deleted
            if self.syncData.current_loop % 4 == 0:
                if self.syncData.current_loop == 0:
                    started = datetime.datetime.now()
                    self.syncRedditFeeds.start()
                    asyncio.create_task(database.VerifyUsers(self.bot))
                    print(f'Full post-verification done in {(datetime.datetime.now() - started).seconds}s')
                for g in self.bot.guilds:
                    await verifyLogChannel(self.bot, g)
                print(f'Garbage collection: {gc.collect()} objects')
            started = datetime.datetime.now()                
            memberList = self.bot.get_all_members()
            await asyncio.gather(*[updateLastOnline(m, datetime.datetime.now()) for m in memberList if m.status != discord.Status.offline]) #This line was the source of members having no username. For some reason, their user data was not created, perhaps because they were added between then and now? Just make sure the methods that trigger when the bot encounters new members works properly.
            print(f'Status management done in {(datetime.datetime.now() - started).seconds}s')
            #self.bot.lightningLogging = lightningLogging
            ## Commented out as of patch 0.2.25 - remove next patch. Reason: I find this obsolete as synchronizeDatabase handles this the first time, and trackChanges keeps them updated thereafter
            #lightningLogging = self.bot.lightningLogging
            #lightningUsers = self.bot.lightningUsers
            await self.imageLogChannel.send('Completed')
        except Exception as e: 
            print('Summarize error: {}'.format(traceback.format_exc()))
            traceback.print_exc()
        print(f'Done summarizing: {(datetime.datetime.now() - rawStarted).seconds}s')

    async def synchronizeDatabase(self, notify=False):
        '''This method downloads data from the database and puts it in the lightningLogging/Users variables, then is kept updated in the motorMongo changeStream method (trackChanges)'''
        started = datetime.datetime.now()
        print('Synchronizing Database')
        global lightningLogging
        global lightningUsers
        async for s in await database.GetAllServers():
            if self.bot.get_guild(s['server_id']):
                self.bot.lightningLogging[s['server_id']] = s
                lightningLogging[s['server_id']] = s
            else: 
                attachmentsPath = f'Attachments/{s["server_id"]}'
                indexesPath = f'{indexes}/{s["server_id"]}'
                shutil.rmtree(attachmentsPath)
                shutil.rmtree(indexesPath)
                await database.DeleteServer(s['server_id'], self.bot)
        async for u in await database.GetAllUsers():
            if self.bot.get_user(u['user_id']):
                self.bot.lightningUsers[u['user_id']] = u
                lightningUsers[u['user_id']] = u
            else: await database.DeleteUser(u['user_id'], self.bot)
        print(f'Database Synchronization done in {(datetime.datetime.now() - started).seconds}s', notify)
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
                try: shutil.rmtree(path)
                except Exception as e: print(f'Attachment Deletion fail: {e}')
            for fl in outstandingTempFiles:
                try: shutil.rmtree((os.path.join(tempDir, fl)))
                except:
                    try: os.remove(os.path.join(tempDir, fl))
                    except Exception as e: print(f'Temp Attachment Deletion fail: {e}')
            print('Removed {} attachments in {} seconds'.format(len(removal) + len(outstandingTempFiles), (datetime.datetime.now() - time).seconds))
        except Exception as e: print('Fail: {}'.format(e))

    @tasks.loop(hours=1)
    async def syncRedditFeeds(self):
        '''Goes through all servers and ensures reddit feeds are working'''
        try:
            for server in self.bot.guilds: asyncio.create_task(self.redditFeedHandler(server))
        except: traceback.print_exc()
    
    async def redditFeedHandler(self, server):
        '''Handles starting/stopping of reddit feeds for servers, along with ensuring there are no duplicates, etc.'''
        runningFeeds = self.redditThreads.get(server.id) or []
        proposedFeeds = [entry['subreddit'] for entry in self.bot.lightningLogging[server.id].get('redditFeeds') or [] if self.bot.get_channel(entry['channel'])]
        feedsToCreate = [entry for entry in self.bot.lightningLogging[server.id].get('redditFeeds') or [] if entry['subreddit'] not in runningFeeds and self.bot.get_channel(entry['channel']) and not (await self.bot.reddit.subreddit(entry['subreddit'], fetch=True)).over18]
        feedsToDelete = [entry for entry in runningFeeds if entry['subreddit'] not in proposedFeeds]
        for feed in feedsToCreate: asyncio.create_task(self.createRedditStream(server, feed))
        for feed in feedsToDelete: self.redditThreads[server.id].remove(feed['subreddit'])
    
    async def createRedditStream(self, server, data):
        '''Data represents a singular subreddit customization data'''
        if self.redditThreads.get(server.id) and data["subreddit"] in self.redditThreads[server.id]: return #We already have a thread running for this server & subreddit
        reddit = self.bot.reddit
        channel = self.bot.get_channel(data['channel'])
        subreddit = await reddit.subreddit(data['subreddit'], fetch=True)
        try: self.redditThreads[server.id].append(data['subreddit']) #Marks that we have a running thread for this server & subreddit
        except KeyError: self.redditThreads[server.id] = [data['subreddit']]
        async for submission in subreddit.stream.submissions(skip_existing=True):
            try:
                if data['subreddit'] not in self.redditThreads[server.id]: return #This feed has been cancelled
                embed = await self.redditSubmissionEmbed(server, submission, True, data['truncateTitle'], data['truncateText'], data['media'], data['creditAuthor'], data['color'], data['timestamp'])
                await channel.send(embed=embed)
            except: pass
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        '''[DISCORD API METHOD] Called when message is sent
        Unlike RicoBot, I don't need to spend over 1000 lines of code doing things here in [ON MESSAGE] due to the web dashboard :D'''
        await self.bot.wait_until_ready()
        await updateLastActive(message.author, datetime.datetime.now(), 'sent a message')
        if type(message.channel) is discord.DMChannel: return
        if message.type is discord.MessageType.pins_add: await self.pinAddLogging(message)
        if message.content == f'<@!{self.bot.user.id}>': await self.sendGuideMessage(message)
        await asyncio.gather(*[self.saveMessage(message), self.jumpLinkQuoteContext(message), self.redditAutocomplete(message), self.redditEnhance(message)])

    async def saveMessage(self, message: discord.Message):
        path = f'{indexes}/{message.guild.id}'
        try: os.makedirs(path)
        except FileExistsError: pass
        try:
            with open(f'{path}/{message.channel.id}.json', 'r+') as f: 
                try: indexData = json.load(f)
                except json.JSONDecodeError: indexData = {}
                indexData[message.id] = {'author0': message.author.id, 'timestamp0': message.created_at.isoformat(), 'content0': '<Hidden due to channel being NSFW>' if message.channel.is_nsfw() else message.content if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<No content>"}
        except (FileNotFoundError, PermissionError): 
            indexData = {}
        indexData = json.dumps(indexData, indent=4)
        with open(f'{path}/{message.channel.id}.json', 'w+') as f:
            f.write(indexData)
        if message.author.bot: return
        if await database.GetImageLogPerms(message.guild) and len(message.attachments) > 0 and not message.channel.is_nsfw():
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
        if message.author.id == self.bot.user.id: return
        if enabled:
            words = message.content.split(' ')
            for w in words:
                if 'https://discord.com/channels/' in w or 'https://canary.discord.com/channels' in w: #This word is a hyperlink to a message
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
                        if result.embeds[0].footer.text is discord.Embed.Empty: result.embeds[0].set_footer(text=f'{(result.created_at + datetime.timedelta(hours=timeZone(message.guild))):%b %d, %Y - %I:%M %p} {nameZone(message.guild)}')
                        if result.embeds[0].author.name is discord.Embed.Empty: result.embeds[0].set_author(name=result.author.name, icon_url=result.author.avatar_url)
                        return await message.channel.send(content=result.content,embed=result.embeds[0])
    
    async def redditAutocomplete(self, message: discord.Message):
        if 'r/' not in message.content: return
        config = self.bot.lightningLogging[message.guild.id]['redditComplete']
        if config == 0: return #Feature is disabled
        if message.author.id == self.bot.user.id: return
        for w in message.content.split(' '):
            if 'r/' in w.lower() and 'https://' not in w:
                try:
                    subSearch = w[w.find('r/') + 2:]
                    result = await self.subredditEmbed(subSearch, config == 1)
                    if config == 1: await message.channel.send(result)
                    else: await message.channel.send(embed=result)
                except: pass

    async def redditEnhance(self, message: discord.Message):
        config = self.bot.lightningLogging[message.guild.id]['redditEnhance']
        if ('https://www.reddit.com/r/' not in message.content and 'https://old.reddit.com/r/' not in message.content) or config == (False, False): return
        if message.author.id == self.bot.user.id: return
        for w in message.content.split(' '):
            if ('https://www.reddit.com/r/' in w or 'https://old.reddit.com/r/' in w) and '/comments/' in w and config[0]:
                try:
                    embed = await self.redditSubmissionEmbed(message.guild, w, False)
                    await message.channel.send(embed=embed)
                except: pass
            elif ('https://www.reddit.com/r/' in w or 'https://old.reddit.com/r/' in w) and '/comments/' not in w and config[1]:
                try:
                    subSearch = w[w.find('r/') + 2:]
                    embed = await self.subredditEmbed(subSearch, False)
                    await message.channel.send(embed=embed)
                    message = await message.channel.fetch_message(message.id)
                except: pass
            else: continue
            message = await message.channel.fetch_message(message.id)
            if len(message.embeds) < 1:
                def check(b, a): return b.id == message.id and len(a.embeds) > len(b.embeds)
                result = (await self.bot.wait_for('message_edit', check=check))[1]
            else: result = message
            await result.edit(suppress=True)
            def reactionCheck(r, u): return r.emoji == self.emojis['expand'] and u.id == self.bot.user.id and r.message.id == message.id
            reaction, user = await self.bot.wait_for('reaction_add', check=reactionCheck)
            await message.remove_reaction(reaction, user)

    async def pinAddLogging(self, message: discord.Message):
        rawReceived = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(message.guild.id).get('offset')))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        destination = logChannel(message.guild, 'message')
        if destination is None: return
        f = None
        #These variables are explained in detail in the MessageEditHandler method
        settings = getCyberAttributes(message.guild, 'message')
        if settings['botLogging'] == 0 and message.author.bot: return #The server is set to not log actions performed by bots
        elif settings['botLogging'] == 1 and message.author.bot: settings['plainText'] = True #The server is set to only use plainText logging for actions performed by bots
        pinned = (await message.channel.pins())[0]
        embed=discord.Embed(
            title=f'''{(f'{self.emojis["thumbtack"]}' if settings['library'] > 0 else "📌") if settings['context'][0] > 0 else ""}{"Message was pinned" if settings['context'][0] < 2 else ''}''',
            description=f'''
                {"👮‍♂️" if settings['context'][1] > 0 else ""}{"Pinned by" if settings['context'][1] < 2 else ""}: {message.author.mention} ({message.author.name})
                {(self.emojis["member"] if settings['library'] > 0 else "👤") if settings['context'][1] > 0 else ""}{"Authored by" if settings['context'][1] < 2 else ""}: {pinned.author.mention} ({pinned.author.name})
                {self.channelEmoji(pinned.channel) if settings['context'][1] > 0 else ""}{"Channel" if settings['context'][1] > 2 else ""}: {pinned.channel.mention} {f"[{self.emojis['reply']}Jump]" if settings['context'][1] > 0 else "[Jump to message]"}({pinned.jump_url} 'Jump to message')
                {f"{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(message.guild)}" if settings['embedTimestamp'] > 1 else ''}''',
            color=settings['color'][1])
        if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
        if any(a > 1 for a in (settings['thumbnail'], settings['author'])): #Moderator image saving; target doesn't apply here since the target is the pinned message
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not message.author.is_avatar_animated() else 'gif'))
            try: await message.author.avatar_url_as(size=1024).save(savePath)
            except discord.HTTPException: pass
            f = discord.File(savePath)
            url = await self.uploadFiles(f)
            if settings['thumbnail'] > 1 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
            if settings['author'] > 1 and embed.author.name == discord.Embed.Empty: embed.set_author(name=message.author.name, icon_url=url)
        embed.add_field(name='Message', value=pinned.content)
        embed.set_footer(text=f'Pinned message ID: {pinned.id}')
        plainText = f'{message.author} pinned {"this" if settings["plainText"] else "a"} message to #{pinned.channel.name}'
        #m = await destination.send(content=plainText if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, file=f, tts=settings['tts'], reference=pinned if settings['plainText'] else None, allowed_mentions=discord.AllowedMentions(users=False))
        m = await destination.send(content=plainText if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
        if any((settings['tts'], settings['flashText'])) and not settings['plainText']: await m.edit(content=None)
        try: self.pins[pinned.channel.id].append(pinned.id)
        except KeyError: self.pins[pinned.channel.id] = [pinned.id]
        def reactionCheck(r, u): return r.message.id == m.id and not u.bot
        while True:
            result = await self.bot.wait_for('reaction_add', check=reactionCheck)
            if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(m.embeds) > 0:
                await m.edit(content=plainText, embed=None)
                await m.clear_reactions()
                if not settings['plainText']: await m.add_reaction(self.emojis['expand'])
            elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(m.embeds) < 1:
                await m.edit(content=None, embed=embed)
                await m.clear_reactions()
                if settings['plainText']: await m.add_reaction(self.emojis['collapse'])

    async def sendGuideMessage(self, message: discord.Message):
        await message.channel.send(embed=discord.Embed(title=f'Quick Guide - {message.guild}', description=f'Yes, I am online! Ping: {round(bot.latency * 1000)}ms\n\n**Prefix:** `{self.bot.lightningLogging.get(message.guild.id).get("prefix")}`\n\nHave a question or a problem? Use the `ticket` command to open a support ticket with my developer, or [click to join my support server](https://discord.com/invite/xSGujjz)', color=yellow[1]))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, p):
        '''Discord.py event listener: When a reaction is added to a message'''
        #Layer style: Message ID > User ID > Reaction (emoji)
        u = self.bot.get_user(p.user_id)
        await updateLastActive(u, datetime.datetime.now(), 'removed a reaction')
        if u.bot: return
        g = self.bot.get_guild(p.guild_id)
        if not g: return
        m = p.message_id
        if self.reactions: layerObject = self.reactions
        else: layerObject = collections.defaultdict(lambda: collections.defaultdict(dict))
        layerObject[m][u.id][p.emoji.name] = {'timestamp': datetime.datetime.utcnow(), 'guild': g.id}
        self.reactions = layerObject 
        sleepTime = self.bot.lightningLogging[g.id]['cyberlog']['ghostReactionTime']
        await asyncio.sleep(sleepTime)
        try: layerObject[m][u.id].remove(p.emoji.name)
        except: pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, p):
        '''Discord.py event listener: When a reaction is removed from a message'''
        u = self.bot.get_user(p.user_id)
        await updateLastActive(u, datetime.datetime.now(), 'removed a reaction')
        if u.bot: return
        g = self.bot.get_guild(p.guild_id)
        if not g: return
        m = p.message_id
        c = bot.get_channel(p.channel_id)
        layerObject = self.reactions[m][u.id][p.emoji.name]
        if not layerObject: return
        seconds = (datetime.datetime.utcnow() - layerObject['timestamp']).seconds
        if seconds < self.bot.lightningLogging[g.id]['cyberlog']['ghostReactionTime']:
            settings = getCyberAttributes(g, 'misc')
            rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=bot.lightningLogging[g.id]['offset'])
            received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
            color = blue[colorTheme(g)] if settings['color'][1] == 'auto' else settings['color'][1]
            result = await c.fetch_message(m)
            if result.author.id == self.bot.user.id and len(result.embeds) > 0: return
            rawEmoji = emojis.decode(p.emoji.name).replace(':', '') #Use the python Emojis module to get the name of an emoji - remove the colons so it doesn't get embedded into Discord. Only applies to unicode emojis.
            content = f'{u} removed the {rawEmoji} reaction from their message in #{c.name} {seconds} seconds after adding it' #There is a zero-width space in this line, after the first colon
            emojiLine = f'{self.emojis["emoji"] if settings["context"][1] > 0 else ""}{"Reaction" if settings["context"][1] < 2 else ""}: {p.emoji} ({rawEmoji})'
            userLine = f'{(self.emojis["member"] if settings["library"] > 0 else "👤") if settings["context"][1] > 0 else ""}{"Member" if settings["context"][1] < 2 else ""}: {u.mention} ({u.name})'
            channelLine = f'''{self.emojis["hashtag"] if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {c.mention} ({c.name}) {f'{self.emojis["reply"]}[Jump]({result.jump_url})' if result else ""}'''
            ghostTimeLine = f'{self.emojis["slowmode"] if settings["context"][1] > 0 else ""}{"Timespan" if settings["context"][1] < 2 else ""}: Removed {seconds}s after being added'
            timeLine = f'{(clockEmoji(rawReceived) if settings["library"] > 0 else "🕰") if settings["context"][1] > 0 else ""}{"Timestamp" if settings["context"][1] < 2 else ""}: {received} {nameZone(g)}'
            embed = discord.Embed(
                title=f'''{f'{self.emojis["emoji"]}👻' if settings["context"][0] > 0 else ""}{"Ghost message reaction" if settings["context"][0] < 2 else ""}''',
                description=f'{content}\n\n{emojiLine}\n{ghostTimeLine}\n{userLine}\n{channelLine}\n{timeLine if settings["embedTimestamp"] > 1 else ""}',
                color=color
            )
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            embed.set_footer(text=f'Message ID: {m}')
            f = None
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not u.is_avatar_animated() else 'gif'))
                try: await u.avatar_url_as(size=1024).save(savePath)
                except discord.HTTPException: pass
                f = discord.File(savePath)
                url = await self.uploadFiles(f)
                if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=u.name, icon_url=url)
            try: 
                message = await logChannel(g, 'misc').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
                if not settings['plainText']: await message.edit(embed=embed)
            except: pass
            try: layerObject[m][u.id].remove(p.emoji.name)
            except: pass    

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
        #Variables to hold essential data
        guild = after.guild
        author = after.author
        channel = after.channel
        b4 = None
        botIgnore = False
        c = logChannel(guild, 'message')
        settings = getCyberAttributes(guild, 'message')
        received = f'{timestamp:%b %d, %Y • %I:%M:%S %p}'
        utcTimestamp = timestamp - datetime.timedelta(hours=timeZone(guild))
        color = blue[colorTheme(guild)] if settings['color'][1] == 'auto' else settings['color'][1]
        if c is None: return #Invalid log channel or bot logging is disabled
        if settings['botLogging'] == 0 and after.author.bot: botIgnore = True
        elif settings['botLogging'] == 1 and after.author.bot: settings['plainText'] = True
        if type(before) is discord.Message:
            b4 = before
            before = before.content
        def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
        if after.id in self.pins.get(after.channel.id) and not after.pinned and not botIgnore: #Message was unpinned
            #These variables represent customization options that are used in multiple places
            #Notably: Embed data field descriptions will now need to be split up - the emoji part & the text part - since there are options to have either one or the other or both.
            try: eventMessage = [m for m in await after.channel.history(limit=5).flatten() if m.type is discord.MessageType.pins_add][0] #Attempt to find who pinned a new message, if applicable - they were likely to unpin the old one
            except IndexError: eventMessage = None
            #I will be multilining lots of code to account for the myriad of new customization settings - for organization purposes which I'll definitely need later
            embed=discord.Embed(
                title=f'''{(f'{self.emojis["thumbtack"]}❌' if settings['library'] > 0 else "📌❌") if settings['context'][0] > 0 else ""}{"Message was unpinned" if settings['context'][0] < 2 else ""}''',
                description=f'''
                {f'{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Unpinned by" if settings["context"][1] < 2 else ""}: {eventMessage.author.mention} ({eventMessage.author.name})' if eventMessage else ""}
                {(self.emojis["member"] if settings["library"] > 0 else "👤") if settings["context"][1] > 0 else ""}{"Authored by" if settings["context"][1] < 2 else ""}: {after.author.mention} ({after.author.name})
                {self.channelEmoji(after.channel) if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {after.channel.mention} {f"[{self.emojis['reply']}Jump]" if settings["context"][1] > 0 else "[Jump to message]"}({after.jump_url} 'Jump to message')
                {f"{(clockEmoji(timestamp) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(guild)}" if settings['embedTimestamp'] > 1 else ''}''',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            if any(a > 1 for a in (settings['thumbnail'], settings['author'])): #Moderator image saving; target doesn't apply here since the target is the pinned message
                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not author.is_avatar_animated() else 'gif'))
                try: await after.author.avatar_url_as(size=1024).save(savePath)
                except discord.HTTPException: pass
                f = discord.File(savePath)
                url = await self.uploadFiles(f)
                if settings['thumbnail'] > 1 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                if settings['author'] > 1 and embed.author.name == discord.Embed.Empty: embed.set_author(name=after.author.name, icon_url=url)
            embed.add_field(name=f'Message', value=after.content)
            embed.set_footer(text=f'Unpinned message ID: {after.id}')
            plainText = f'{eventMessage.author if eventMessage else "Someone"} unpinned a message from #{after.channel.name}'
            #m = await c.send(content=plainText if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, file=f, tts=settings['tts'], reference=after if settings['plainText'] else None, allowed_mentions=discord.AllowedMentions.none())
            m = await c.send(content=plainText if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            if any((settings['tts'], settings['flashText'])) and not settings['plainText']: await m.edit(content=None)
            self.pins[channel.id].remove(after.id)
            while True:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=plainText, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])
            return
        elif b4 and not b4.flags.suppress_embeds and after.flags.suppress_embeds and self.bot.lightningLogging[after.guild.id]['undoSuppression']:
            await after.add_reaction(self.emojis['expand'])
            def check(r, u): return r.emoji == self.emojis['expand'] and ManageServer(u) and r.message.id == after.id and not u.bot
            await self.bot.wait_for('reaction_add', check=check)
            await after.edit(suppress=False)
            after = await after.channel.fetch_message(after.id)
            for r in after.reactions:
                if r.emoji == self.emojis['expand']: 
                    return await r.clear()
        if botIgnore or after.author.id == self.bot.user.id: return
        if after.content.strip() == before.strip(): return #If the text before/after is the same, and after unpinned message log if applicable
        if any(w in before.strip() for w in ['attachments>', '<1 attachment:', 'embed>']): return
        beforeWordList = before.split(" ") #A list of words in the old message
        afterWordList = after.content.split(" ") #A list of words in the new message
        beforeParsed = [f'**{word}**' if word not in afterWordList else word for word in beforeWordList]
        afterParsed = [f'**{word}**' if word not in beforeWordList else word for word in afterWordList]
        beforeC, afterC = self.parseEdits(beforeWordList, afterWordList)
        if any([len(m) == 0 for m in [beforeC, afterC]]): beforeC, afterC = self.parseEdits(beforeWordList, afterWordList, True)
        if len(beforeC) >= 1024: beforeC = 'Message content too long to display in embed field'
        if len(afterC) >= 1024: afterC = 'Message content too long to display in embed field'
        embed = discord.Embed(
            title=f'''{(self.emojis['messageEdit'] if settings['library'] > 1 else f"📜✏") if settings['context'][0] > 0 else ''}{"Message was edited" if settings['context'][0] < 2 else ""}''',
            description=f'''{self.emojis['loading']} Finalyzing log''',
            color=color)
        if settings['embedTimestamp']: embed.timestamp = utcTimestamp
        embed.set_footer(text=f'Message ID: {after.id} {footerAppendum}')
        if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not author.is_avatar_animated() else 'gif'))
            try: await author.avatar_url_as(size=1024).save(savePath)
            except discord.HTTPException: pass
            f = discord.File(savePath)
            url = await self.uploadFiles(f)
            if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
            if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=after.author.name, icon_url=url)
        path = f'{indexes}/{after.guild.id}/{after.channel.id}.json'
        with open(path) as fl: #Open up index data to append the message edit history entry
            indexData = json.load(fl) #importing the index data from the filesystem
            number = len(indexData[str(after.id)].keys()) // 3 #This represents the suffix to the key names, because dicts need to have unique key names, and message edit history requires multiple entries
            indexData[str(after.id)].update({f'author{number}': after.author.id, f'timestamp{number}': datetime.datetime.utcnow().isoformat(), f'content{number}': after.content if len(after.content) > 0 else f"<{len(after.attachments)} attachment{'s' if len(after.attachments) > 1 else f':{after.attachments[0].filename}'}>" if len(after.attachments) > 0 else f"<{len(after.embeds)} embed>" if len(after.embeds) > 0 else "<No content>"})
            indexData = json.dumps(indexData, indent=4)
        plainText = f'{after.author} edited {"this" if settings["plainText"] else "a"} message\nBefore:`{beforeParsed if len(beforeParsed) < 1024 else beforeC}`\nAfter:`{afterParsed if len(afterParsed) < 1024 else afterC}\n`{after.jump_url}'
        try: 
            #msg = await c.send(content=plainText if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, file=f, tts=settings['tts'], reference=after if settings['plainText'] else None, allowed_mentions=discord.AllowedMentions(users=False))
            msg = await c.send(content=plainText if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            await msg.add_reaction(self.emojis['threeDots'])
        except discord.HTTPException as e: return await c.send(f'Message edit log error: {e}')
        with open(path, 'w+') as fl:
            fl.write(indexData) #push the changes to the json file
        embed.description=f'''
            {(self.emojis["member"] if settings["library"] > 0 else "👤") if settings["context"][1] > 0 else ""}{"Author" if settings["context"][1] < 2 else ""}: {author.mention} ({author.name})
            {self.channelEmoji(channel) if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {channel.mention} {f"[{self.emojis['reply']}Jump]" if settings["context"][1] > 0 else "[Jump to message]"}({after.jump_url} 'Jump to message')
            {f"{(clockEmoji(timestamp) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(guild)}" if settings['embedTimestamp'] > 1 else ''}'''
        rng = random.randint(1, 50) == 1 #2% chance to display the help guide
        embed.add_field(name=f'{self.emojis["before"] if settings["context"][1] > 0 and settings["library"] == 2 else ""}Before{" • Hover for full message" if rng and settings["context"][1] < 2 else ""}', value=f'''[{beforeC if len(beforeC) > 0 else f'<Quick parser found no new content; {self.emojis["threeDots"]} to see full changes>'}]({msg.jump_url} '{before.strip()}')''',inline=False)
        embed.add_field(name=f'{self.emojis["after"] if settings["context"][1] > 0 and settings["library"] == 2 else ""}After{" • Hover for full message" if rng and settings["context"][1] < 2 else ""}', value=f'''[{afterC if len(afterC) > 0 else f'<Quick parser found no new content; {self.emojis["threeDots"]} to see full changes>'}]({msg.jump_url} '{after.content.strip()}')''',inline=False)
        if len(embed.fields[0].value) > 1024: embed.set_field_at(0, name=embed.fields[0].name, value=beforeC if len(beforeC) in range(0, 1024) else '<Content is too long to be displayed>', inline=False)
        if len(embed.fields[1].value) > 1024: embed.set_field_at(1, name=embed.fields[1].name, value=afterC if len(afterC) in range(0, 1024) else '<Content is too long to be displayed>', inline=False)
        await msg.edit(content=None if any((settings['tts'], settings['flashText'])) and not settings['plainText'] else msg.content, embed=None if settings['plainText'] else embed)
        try: 
            if os.path.exists(savePath): os.remove(savePath)
        except: pass
        oldEmbed=copy.deepcopy(embed)
        oldContent=plainText
        await updateLastActive(author, datetime.datetime.now(), 'edited a message')
        while True:
            def iCheck(r, u): r.message.id == msg.id and not u.bot
            result = await self.bot.wait_for('reaction_add',check=iCheck)
            if result[0].emoji == self.emojis['threeDots'] or settings['plainText']:
                authorID = result[1].id
                embed.description += '\n\nNAVIGATION\n⬅: Go back to compressed view\nℹ: Full edited message\n📜: Message edit history\n🗒: Message in context'
                while True:
                    if len(embed.author.name) < 1: embed.set_author(icon_url=result[1].avatar_url, name=f'{result[1].name} - Navigating')
                    def optionsCheck(r, u): return str(r) in ['ℹ', '⬅', '📜', '🗒', self.emojis['collapse']] and r.message.id == msg.id and u.id == authorID
                    if not result:
                        try: result = await self.bot.wait_for('reaction_add',check=optionsCheck, timeout=180)
                        except asyncio.TimeoutError: result = ['⬅']
                    await msg.clear_reactions()
                    if str(result[0]) == 'ℹ' or str(result[0].emoji) == str(self.emojis['threeDots']):
                        embed.set_field_at(0, name='Before', value=' '.join(beforeParsed), inline=False)
                        embed.set_field_at(1, name='After', value=' '.join(afterParsed), inline=False)
                        embed.description=embed.description[:embed.description.find(nameZone(guild)) + len(nameZone(guild))] + f'\n\nNAVIGATION\n{qlf}⬅: Go back to compressed view\n> **ℹ: Full edited message**\n{qlf}📜: Message edit history\n{qlf}🗒: Message in context'
                        await msg.edit(content=None, embed=embed)
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
                    elif str(result[0]) == '⬅':
                        await msg.clear_reactions()
                        await msg.edit(content=oldContent, embed=oldEmbed if not settings['plainText'] else None)
                        embed = copy.deepcopy(oldEmbed)
                        if not settings['plainText']: await msg.add_reaction(self.emojis['threeDots'])
                        break
                    result = None
            elif result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎'):
                await msg.edit(content=plainText, embed=None)
                await msg.clear_reactions()

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        '''[DISCORD API METHOD] Called when message is edited'''
        if not after.guild: return #We don't deal with DMs
        received = datetime.datetime.utcnow() + datetime.timedelta(hours=timeZone(after.guild)) #Timestamp of receiving the message edit event
        asyncio.create_task(updateLastActive(after.author, datetime.datetime.now(), 'edited a message'))
        if self.pins.get(after.channel.id) is None: return
        g = after.guild
        if not logEnabled(g, 'message'): return #If the message edit log module is not enabled, return
        try:
            if not logExclusions(after.channel, after.author): return #Check the exclusion settings
        except: return
        await self.MessageEditHandler(before, after, received)

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
        except discord.NotFound: return
        except discord.Forbidden: 
            print('{} lacks permissions for message edit for some reason'.format(bot.get_guild(int(payload.data.get('guild_id'))).name))
            return
        author = g.get_member(after.author.id) #Get the member of the edited message, and if not found, return (this should always work, and if not, then it isn't a server and we can let it error and Tdon't need to proceed)
        asyncio.create_task(updateLastActive(author, datetime.datetime.now(), 'edited a message'))
        if not self.pins.get(channel.id): return
        if not logEnabled(g, 'message'): return #If the message edit log module is not enabled, return
        try:
            if not logExclusions(after.channel, author): return #Check the exclusion settings
        except: return
        c = logChannel(g, 'message')
        if c is None: return #Invalid log channel
        try:
            path = f'{indexes}/{after.guild.id}/{after.channel.id}.json'
            with open(path) as f:
                indexData = json.load(f)
                currentMessage = indexData[str(after.id)]
                before = currentMessage[f'content{len(currentMessage.keys()) // 3 - 1}']
        except FileNotFoundError as e: before = f'<Data retrieval error: {e}>' #If we can't find the file, then we say this
        except IndexError: before = after.content #Author is bot, and indexes aren't kept for bots; keep this for pins only
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
        def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
        c = logChannel(g, 'message')
        settings = getCyberAttributes(g, 'message')
        fileError = ''
        color = red[colorTheme(g)] if settings['color'][2] == 'auto' else settings['color'][2]
        if payload.message_id in self.pauseDelete: return self.pauseDelete.remove(payload.message_id)
        embed=discord.Embed(
            title=f'''{(f'{self.emojis["messageDelete"] if settings["library"] > 1 else "📜" + str(self.emojis["delete"])}') if settings["context"][0] > 0 else ""}{"Message was deleted" if settings["context"][0] < 2 else ""}''',
            description='',
            color=color)
        if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
        embed.set_footer(text=f'Message ID: {payload.message_id}')
        attachments = [] #List of files sent with this message
        path = 'Attachments/{}/{}/{}'.format(payload.guild_id,payload.channel_id, payload.message_id) #Where to retrieve message attachments from
        try:
            for directory in os.listdir(path):
                f = discord.File(f'{path}/{directory}')
                try: 
                    if any([ext in directory.lower() for ext in ['.png', '.jpeg', '.jpg', '.gif', '.webp']]):
                        URL = await self.uploadFiles(f)
                        embed.set_image(url=URL)
                    else: attachments.append(f)
                except discord.HTTPException:
                    fileError += f"\n{self.emojis['alert']} | This message's attachment ({f.filename}) is too large to be sent ({round(os.stat(f.fp).st_size / 1000000, 2)}mb). Please view [this page](https://disguard.netlify.app/privacy.html#appendixF) for more information including file retrieval."
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
            except (FileNotFoundError, IndexError, KeyError):
                try: channel = channel.mention
                except UnboundLocalError: channel = payload.channel_id
                embed.description=f'{self.emojis["textChannel"] if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {channel}\n\nUnable to provide information beyond what is here; this message was sent before my last restart, and I am unable to locate the indexed file locally to retrieve more information'
                plainText = f'''Somebody deleted their message in #{channel.name if type(channel) is discord.TextChannel else channel}\n\nUnable to provide more information about this event'''
                msg = await c.send(content=plainText if 'audit log' in plainText or 'too large' in plainText or any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
                if any((settings['tts'], settings['flashText'])) and not settings['plainText']: await msg.edit(content=None)
                while True:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                    if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                        await msg.edit(content=plainText, embed=None)
                        await msg.clear_reactions()
                        if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                    elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']) and len(msg.embeds) < 1:
                        await msg.edit(content=None, embed=embed)
                        await msg.clear_reactions()
                        if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])
        if settings['botLogging'] == 0 and author.bot: return
        elif settings['botLogging'] == 1 and author.bot: settings['plainText'] = True
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
        embed.description=f'''
            {(self.emojis["member"] if settings["library"] > 0 else "👤") if settings["context"][1] > 0 else ""}{"Authored by" if settings["context"][1] < 2 else ""}: {author.mention} ({author.name}){ '(No longer in this server)' if not memberObject else ''}
            {self.channelEmoji(channel) if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {channel.mention} • Jump to message [before]({messageBefore.jump_url if messageBefore else ''} \'{messageBefore.content if messageBefore else ''}\') or [after]({messageAfter.jump_url if messageAfter else ''} \'{messageAfter.content if messageAfter else ''}\') this one
            {self.emojis['sendMessage'] if settings["context"][1] > 0 else ""}: {created:%b %d, %Y • %I:%M:%S %p} {nameZone(g)}
            {self.emojis['delete']}: {received} {nameZone(g)} ({' '.join(reversed(display))} later)'''
        if message: embed.add_field(name="Content",value=message.content[:1024] if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f': {message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<Error retrieving content>")
        else: embed.add_field(name='Content',value='<No content>' if len(content) < 1 else content[:1024])
        for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            if ext in content.lower():
                if '://' in content:
                    url = content[message.content.find('http'):content.find(ext)+len(ext)+1]
                    embed.set_image(url=url)
        if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not author.is_avatar_animated() else 'gif'))
            try: await author.avatar_url_as(size=1024).save(savePath)
            except discord.HTTPException: pass
            f = discord.File(savePath)
            url = await self.uploadFiles(f)
            if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
            if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=author.name, icon_url=url)
        modDelete = False
        plainText = ''
        if readPerms(g, "message"):
            try:
                async for log in g.audit_logs(limit=1):
                    if log.action in (discord.AuditLogAction.message_delete, discord.AuditLogAction.message_bulk_delete) and absTime(datetime.datetime.utcnow(), log.created_at, datetime.timedelta(seconds=20)) and log.target.id in (author.id, channel.id) and log.user != author:
                        embed.description+=f'''\n{(f'{self.emojis["modDelete"]}👮‍♂️') if settings['context'][1] > 0 else ''}{"Deleted by" if settings['context'][1] < 2 else ""}: {log.user.mention} ({log.user.name})'''
                        embed.title = f'''{(f'{self.emojis["messageDelete"] if settings["library"] > 1 else "📜" + str(self.emojis["modDelete"])}') if settings["context"][0] > 0 else ""}{"Message was deleted" if settings["context"][1] < 2 else ''}'''
                        await updateLastActive(log.user, datetime.datetime.now(), 'deleted a message')
                        modDelete = True
                        if any(a in (3, 4) for a in (settings['thumbnail'], settings['author'])): #Moderator image saving; target doesn't apply here since the target is the pinned message
                            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not message.author.is_avatar_animated() else 'gif'))
                            try: await message.author.avatar_url_as(size=1024).save(savePath)
                            except discord.HTTPException: pass
                            f = discord.File(savePath)
                            url = await self.uploadFiles(f)
                            if settings['thumbnail'] in (3, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                            if settings['author'] in (3, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=author.name, icon_url=url)
                    else: await updateLastActive(author, datetime.datetime.now(), 'deleted a message')
            except Exception as e: plainText += f'You have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
        plainText=f'''{log.user if modDelete else author} deleted {f"{author}'s" if modDelete else "their"} message in #{channel.name if type(channel) is discord.TextChannel else channel}\n\n{'<No content>' if len(content) < 1 else content[:1900]}\n\n{plainText}'''
        a = 0
        while a < len(attachments):
            f = attachments[a]
            if os.stat(f.fp).st_size / 1000000 > 8:
                fileError += f"\n{self.emojis['alert']} | This message's attachment ({f.filename}) is too large to be sent ({round(os.stat(f.fp).st_size / 1000000, 2)}mb). Please view [this page](https://disguard.netlify.app/privacy.html#appendixF) for more information including file retrieval."
                savePath = f'{tempDir}/{payload.message_id}/{f.filename}'
                shutil.copy2(f.fp, savePath)
                attachments.pop(a)
            else: a += 1
        content += f'\n\n{fileError}'
        msg = await c.send(content=plainText if 'audit log' in plainText or 'too large' in plainText or any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, files=attachments, tts=settings['tts'])
        if any((settings['tts'], settings['flashText'])) and not settings['plainText']: await msg.edit(content=None)
        if os.path.exists(savePath): os.remove(savePath)
        #Now delete any attachments associated with this message
        path = f'Attachments/{g.id}/{channel.id}/{payload.message_id}'
        try: shutil.rmtree(path)
        except: pass
        while True:
            result = await self.bot.wait_for('reaction_add', check=reactionCheck)
            if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                await msg.edit(content=plainText, embed=None)
                await msg.clear_reactions()
                if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
            elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']) and len(msg.embeds) < 1:
                await msg.edit(content=None, embed=embed)
                await msg.clear_reactions()
                if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is created'''
        content=''
        savePath = None
        rawReceived = (channel.created_at + datetime.timedelta(hours=self.bot.lightningLogging.get(channel.guild.id).get('offset')))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        f=None
        msg = None
        if logEnabled(channel.guild, "channel"):
            settings = getCyberAttributes(channel.guild, 'channel')
            color = green[colorTheme(channel.guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            keytypes = {discord.Member: '👤', discord.Role: '🚩'}
            content = f'A moderator created a new {channel.type[0]} channel called {channel.name}'
            embed=discord.Embed(
                title=f'''{self.channelEmoji(channel) if settings["context"][0] > 0 else ""}{(self.emojis["channelCreate"] if settings["library"] > 1 else self.emojis["greenPlus"]) if settings["context"][0] > 0 else ""}{f"{channel.type[0][0].upper() + channel.type[0][1:]} Channel was created" if settings["context"][0] < 2 else ""}''',
                description=f'{self.channelKeys[channel.type[0] if settings["context"][1] > 0 else ""]}{"Channel" if settings["context"][1] < 2 else ""}: {f"{channel.mention} ({channel.name})" if channel.type[0] == "text" else channel.name}',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            if readPerms(channel.guild, "channel"):
                try:
                    log = (await channel.guild.audit_logs(limit=1).flatten())[0]
                    if log.action == discord.AuditLogAction.channel_create:
                        if settings['botLogging'] == 0 and log.user.bot: return
                        elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                        embed.description+=f'''\n{"👮‍♂️" if settings['context'][1] > 0 else ""}{"Created by" if settings['context'][1] < 2 else ""}: {log.user.mention} ({log.user.name}){f"{newline}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}'''
                        if any(a > 1 for a in (settings['thumbnail'], settings['author'])):
                            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                            try: await log.user.avatar_url_as(size=1024).save(savePath)
                            except discord.HTTPException: pass
                            f = discord.File(savePath)
                            url = await self.uploadFiles(f)
                            if settings['thumbnail'] > 1 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                            if settings['author'] > 1 and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                            content = f'{log.user} created a new {channel.type[0]} channel called {channel.name}'
                        await updateLastActive(log.user, datetime.datetime.now(), 'created a channel')
                except Exception as e: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            embed.set_footer(text=f'Channel ID: {channel.id}')
            msg = await logChannel(channel.guild, "channel").send(content=content if 'audit log' in content or any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            defaultRead = channel.overwrites_for(channel.guild.default_role).read_messages
            if defaultRead == False: 
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
            memberAccessibleNewline = ' ' if len(accessibleMembers) > 20 else newline
            memberUnaccessibleNewline = ' ' if len(unaccessibleMembers) > 20 else newline
            roleAccessibleNewline = ' ' if len(accessibleRoles) > 20 else newline
            roleUnaccessibleNewline = ' ' if len(unaccessibleRoles) > 20 else newline
            accessibleTail = f'ACCESSIBLE TO\n------------------\nROLES\n{roleAccessibleNewline.join([f"🚩 {r.name}" for r in accessibleRoles])}\n\nMEMBERS\n{memberAccessibleNewline.join([f"👤 {m.name}" for m in accessibleMembers])}'
            unaccessibleTail = f'NOT ACCESSIBLE TO\n-----------------------\nROLES\n{roleUnaccessibleNewline.join([f"🚩 {r.name}" for r in unaccessibleRoles])}\n\nMEMBERS\n{memberUnaccessibleNewline.join([f"👤 {m.name}" for m in unaccessibleMembers])}'
            if channel.overwrites_for(channel.guild.default_role).read_messages is not False: tempAccessibleString = f'''\n[{'🔓' if settings['context'][1] > 0 else ''}{'Accessible to' if settings['context'][1] < 2 else ''}: **Everyone by default**]({msg.jump_url} '{accessibleTail}')'''
            else:
                if sum(len(obj.name) for obj in accessible) > 32 or len(accessible) == 0: tempAccessibleString = f'''\n[{'🔓' if settings['context'][1] > 0 else ''}{'Accessible to' if settings['context'][1] < 2 else ''}: {len(accessibleRoles)} role{"s" if len(accessibleRoles) != 1 else ""} ({len(accessibleMembers)} member{"s" if len(accessibleMembers) != 1 else ""})]({msg.jump_url} '{accessibleTail}')'''
                else: tempAccessibleString = f'''\n[{'🔓' if settings['context'][1] > 0 else ''}{'Accessible to' if settings['context'][1] < 2 else ''}: {" • ".join([f'{keytypes.get(type(o))}{o.name}' for o in accessible])}]({msg.jump_url} '{accessibleTail}')'''
            if len(unaccessible) > 0: #At least one member or role can't access this channel by default
                if sum(len(obj.name) for obj in unaccessible) > 28: tempUnaccessibleString = f'''\n[{'🔒' if settings['context'][1] > 0 else ''}{'Not accessible to' if settings['context'][1] < 2 else ''}: {len(unaccessibleRoles)} role{"s" if len(unaccessibleRoles) != 1 else ""} ({len(unaccessibleMembers)} member{"s" if len(unaccessibleMembers) != 1 else ""})]({msg.jump_url} '{unaccessibleTail}')'''
                else: tempUnaccessibleString = f'''\n[{'Not accessible to' if settings['context'][1] < 2 else ''}: {" • ".join([f'{keytypes.get(type(o))}{o.name}' for o in unaccessible])}]({msg.jump_url} '{unaccessibleTail}')'''
            else: tempUnaccessibleString = ''
            if len(tempAccessibleString) + len(tempUnaccessibleString) > 1900:
                trimmedAccessibleString = f"\n{tempAccessibleString[tempAccessibleString.find('[')+1:tempAccessibleString.find(']')]}"
                trimmedUnaccessibleString = f"\n{tempUnaccessibleString[tempUnaccessibleString.find('[')+1:tempUnaccessibleString.find(']')]}"
                if len(tempAccessibleString) + len(trimmedUnaccessibleString) < 1900: embed.description+=f'{tempAccessibleString}{trimmedUnaccessibleString}'
                elif len(trimmedAccessibleString) + len(tempUnaccessibleString) < 1900: embed.description+=f'{trimmedAccessibleString}{tempUnaccessibleString}'
                elif len(trimmedAccessibleString) + len(trimmedUnaccessibleString) < 1900: embed.description+=f'{trimmedAccessibleString}{trimmedUnaccessibleString}'
            else: embed.description+=f'{tempAccessibleString}{tempUnaccessibleString}'
            singleQuoteMark = "'"
            plainTextAccessibleString = f"{tempAccessibleString[tempAccessibleString.find('[') + 1:tempAccessibleString.find(']')]}{newline}{tempAccessibleString[tempAccessibleString.find(singleQuoteMark) + 1:tempAccessibleString.find(')') - 1]}"
            plainTextUnaccessibleString = f"{tempUnaccessibleString[tempUnaccessibleString.find('[') + 1:tempUnaccessibleString.find(']')]}{newline}{tempUnaccessibleString[tempUnaccessibleString.find(singleQuoteMark) + 1:tempUnaccessibleString.find(')') - 1]}"
            if settings['embedTimestamp'] > 1: embed.description += f'''\n{(clockEmoji(rawReceived) if settings['library'] > 0 else "🕰") if settings['context'][1] > 0 else ""}{"Timestamp" if settings['context'][1] < 2 else ""}: {received} {nameZone(channel.guild)}'''
            if channel.type[0] != 'category':
                channelList = channel.category.channels if channel.category is not None else [c for c in channel.guild.channels if c.category is None]
                cIndexes = (channelList.index(channel) - 3 if channelList.index(channel) >= 3 else 0, channelList.index(channel) + 4 if channelList.index(channel) + 4 < len(channelList) else len(channelList))
                plainTextChannelList = f"{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList])}"
                embed.add_field(name=f'Category Tree',value=f'''{self.emojis['folder'] if settings['library'] > 1 else '📁'}{channel.category}\n{f"> [...Hover to view {len(channelList[:cIndexes[0]])} more channel{'s' if len(channelList[:cIndexes[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[:cIndexes[0]])}'){newline}" if cIndexes[0] > 0 else ""}{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList[cIndexes[0]:cIndexes[1]]])}{f"{newline}[Hover to view {len(channelList[cIndexes[1]:])} more channel{'s' if len(channelList[cIndexes:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[cIndexes[1]:])}')" if cIndexes[1] < len(channelList) else ""}''')
                if len(embed.fields[0].value) > 1024: embed.set_field_at(0, name=embed.fields[0].name, value=plainTextChannelList)
                if len(embed.fields[0].value) > 1024: embed.remove_field(0)
            await msg.edit(content=msg.content if not any((settings['tts'], settings['flashText'])) and not settings['plainText'] else None, embed=embed if not settings['plainText'] else None)
            try:
                if os.path.exists(savePath): os.remove(savePath)
            except: pass
        try:
            if channel.category is not None: self.categories[channel.category.id] = [c for c in channel.category.channels]
            else: self.categories[channel.guild.id] = [c[1] for c in channel.guild.by_category() if c[0] is None]
        except discord.Forbidden: pass
        if type(channel) is discord.TextChannel:
            self.pins[channel.id] = []
            asyncio.create_task(database.VerifyServer(channel.guild, bot))
        if msg:
            def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
            while True:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is updated'''
        rawReceived = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(after.guild.id).get('offset')))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        f = None
        msg = None
        channelPosFlag = False
        channelPosTimekey = f'{datetime.datetime.now():%m%d%Y%H%M%S%}'
        if logEnabled(before.guild, "channel"):
            content=f'A moderator updated the {after.type[0]} channel called {before.name}'
            savePath = None
            settings = getCyberAttributes(after.guild, 'channel')
            color = blue[colorTheme(after.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed=discord.Embed(
                title=f'''{self.channelEmoji(after) if settings["context"][0] > 0 else ""}{(self.emojis["channelEdit"] if settings["library"] > 1 else self.emojis["edit"] if settings["library"] > 0 else "✏") if settings["context"][0] > 0 else ""}{f"{after.type[0][0].upper() + after.type[0][1:]} Channel was updated (ℹ for channel info)" if settings["context"][0] < 2 else ""}''',
                description=f'{self.channelKeys[after.type[0]] if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {f"{after.mention} ({after.name})" if after.type[0] == "text" else after.name}',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            reactions = ['ℹ']
            if readPerms(before.guild, "channel"):
                try:
                    log = (await before.guild.audit_logs(limit=1).flatten())[0]
                    if log.action in (discord.AuditLogAction.channel_update, discord.AuditLogAction.overwrite_create, discord.AuditLogAction.overwrite_update, discord.AuditLogAction.overwrite_delete):
                        if log.user.id == self.bot.user.id and before.overwrites != after.overwrites: return
                        if settings['botLogging'] == 0 and log.user.bot: return
                        elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                        embed.description+=f'''\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Updated by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name}){f"{newline}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}'''
                        if any(a > 1 for a in (settings['thumbnail'], settings['author'])):
                            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                            try: await log.user.avatar_url_as(size=1024).save(savePath)
                            except discord.HTTPException: pass
                            f = discord.File(savePath)
                            url = await self.uploadFiles(f)
                            if settings['thumbnail'] > 1 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                            if settings['author'] > 1 and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                            content = f'{log.user} updated the {after.type[0]} channel called {before.name}'
                        await updateLastActive(log.user, datetime.datetime.now(), 'edited a channel')
                except Exception as e: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            embed.set_footer(text=f'Channel ID: {before.id}')
            if before.category == after.category != None:
                bc = self.categories.get(before.category.id)
                if bc and abs(bc.index(before) - after.category.channels.index(after)) > 1:
                    indexes = [] #Channel, before index, after index
                    channelPosFlag = True
                    self.channelCacheHelper[after.guild.id] = []
                    for i in range(len(before.category.channels)): indexes.append({'before': bc.index(before.category.channels[i]), 'after': after.category.channels.index(before.category.channels[i]), 'channel': after.category.channels[i]})
                    embed.add_field(name=f'Channel position changed',value=f'''{self.emojis['folder'] if settings['library'] > 1 else '📁'}{before.category.name}\n{newline.join([(f'~~{self.channelKeys.get(before.type[0])}{before.name}~~❌{newline}' if bc.index(before) == c and indexes[c].get('before') > indexes[c].get('after') else '') + f'{self.channelKeys.get(indexes[c].get("channel").type[0])}' + ('__**' if indexes[c].get('channel').id == before.id else '') + f'{indexes[c].get("channel").name} ' + ('**__' if indexes[c].get('channel').id == before.id else '') + ('↩' if abs(indexes[c].get('before') - indexes[c].get('after')) > 1 else '⬆' if indexes[c].get('before') > indexes[c].get('after') else '⬇' if indexes[c].get('before') < indexes[c].get('after') else '') + (f'{newline}~~{self.channelKeys.get(before.type[0])}{before.name}~~❌' if bc.index(before) == c and indexes[c].get('before') < indexes[c].get('after') else '') for c in range(len(indexes))])}''')
                    self.categories[after.category.id] = [c for c in after.category.channels]
            if before.overwrites != after.overwrites:
                embed.add_field(name='Permission overwrites updated',value='Manually react 🇵 to show/hide') #The rest of this code is later because we need a message link to the current message
            if before.name != after.name:
                embed.add_field(name='Name', value=f'{before.name} → **{after.name}**')
            if type(before) is discord.TextChannel:
                beforeTopic = before.topic if before.topic is not None and len(before.topic) > 0 else "<No topic>"
                afterTopic = after.topic if after.topic is not None and len(after.topic) > 0 else "<No topic>"
                if beforeTopic != afterTopic:
                    embed.add_field(name='Old Description', value=beforeTopic)
                    embed.add_field(name='New Description', value=afterTopic)
                if before.is_nsfw() != after.is_nsfw():
                    embed.add_field(name='NSFW', value=f'{before.is_nsfw()} → **{after.is_nsfw()}**')
                if before.slowmode_delay != after.slowmode_delay:
                    delays = [[before.slowmode_delay, 'second'], [after.slowmode_delay, 'second']]
                    for d in delays:
                        if d[0] is not None and d[0] >= 60:
                            d[0] //= 60
                            d[1] = 'minute'
                            if d[0] >= 60:
                                d[0] //= 60
                                d[1] = 'hour'
                    embed.add_field(name='Slowmode',value=f'{delays[0][0]} {delays[0][1]}{"s" if delays[0][0] != 1 else ""}' if before.slowmode_delay > 0 else '<Disabled>' + f' → **{delays[1][0]} {delays[1][1]}{"s" if delays[1][0] != 1 else ""}**' if after.slowmode_delay > 0 else '**<Disabled>**')
            elif type(before) is discord.VoiceChannel:
                if before.bitrate != after.bitrate:
                    embed.add_field(name='Bitrate',value=f'{before.bitrate // 1000} kbps' + f' → **{after.bitrate // 1000} kbps**')
                if before.user_limit != after.user_limit:
                    embed.add_field(name='User Limit', value=f'{before.user_limit} → **{after.user_limit}**')
            if type(before) is not discord.CategoryChannel and before.category != after.category:
                embed.add_field(name='Old Category', value='Old')
                embed.add_field(name='New Category', value='New')
            if len(embed.fields) > 0:
                msg = await logChannel(before.guild, "channel").send(content=content + embedToPlaintext(embed) if 'audit log' in content or any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
                if type(before) is not discord.CategoryChannel and before.category != after.category:
                    oldChannelList = self.categories.get(before.category.id) if before.category is not None else self.categories.get(before.guild.id)
                    newChannelList = after.category.channels if after.category is not None else [c[1] for c in after.guild.by_category() if c[0] is None]
                    oldIndexes = (oldChannelList.index(after) - 3 if oldChannelList.index(after) >= 3 else 0, oldChannelList.index(after) + 4 if oldChannelList.index(after) + 4 < len(oldChannelList) else len(oldChannelList))
                    newIndexes = (newChannelList.index(after) - 3 if newChannelList.index(after) >= 3 else 0, newChannelList.index(after) + 4 if newChannelList.index(after) + 4 < len(newChannelList) else len(newChannelList))
                    plainTextOldList = f"{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in oldChannelList])}"
                    plainTextNewList = f"{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in newChannelList])}"
                    for i, field in enumerate(embed.fields):
                        if field.name == 'Old Category':
                            embed.set_field_at(i, name="Old Category",value=f'''{self.emojis['folder'] if settings['library'] > 1 else '📁'}{before.category}\n{f"> [...Hover to view {len(oldChannelList[:oldIndexes[0]])} more channel{'s' if len(oldChannelList[:oldIndexes[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in oldChannelList[:oldIndexes[0]])}'){newline}" if oldIndexes[0] > 0 else ""}{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in oldChannelList[oldIndexes[0]:oldIndexes[1]]])}{f"{newline}> [Hover to view {len(oldChannelList[oldIndexes[1]:])} more channel{'s' if len(oldChannelList[oldIndexes[1]:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in oldChannelList[oldIndexes[1]:])}')" if oldIndexes[1] < len(oldChannelList) else ""}''')
                            embed.set_field_at(i + 1, name="New Category",value=f'''{self.emojis['folder'] if settings['library'] > 1 else '📁'}{after.category}\n{f"> [...Hover to view {len(newChannelList[:newIndexes[0]])} more channel{'s' if len(newChannelList[:newIndexes[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in newChannelList[:newIndexes[0]])}'){newline}" if newIndexes[0] > 0 else ""}{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in newChannelList[newIndexes[0]:newIndexes[1]]])}{f"{newline}> [Hover to view {len(newChannelList[newIndexes[1]:])} more channel{'s' if len(newChannelList[oldIndexes[1]:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in newChannelList[newIndexes[1]:])}')" if newIndexes[1] < len(newChannelList) else ""}''')
                            if len(embed.fields[i].value) > 1024: embed.set_field_at(i, name=embed.fields[i].name, value=plainTextOldList)
                            if len(embed.fields[i + 1].value) > 1024: embed.set_field_at(i + 1, name=embed.fields[i + 1].name, value=plainTextNewList)
                            break
                if before.overwrites != after.overwrites:
                    b4 = {key: dict(iter(value)) for (key, value) in before.overwrites.items()} #Channel permissions before it was updated
                    af = {key: dict(iter(value)) for (key, value) in after.overwrites.items()} #Channel permissions after it was updated
                    displayString = [] #Holds information about updated permission values - this will be displayed line by line in the future
                    english = {True: '✔', None: '➖', False: '✖'} #A mapping of overwrite values to emojis for easy visualization
                    classification = {discord.Role: '🚩', discord.Member: '👤'} #A mapping of overwrite targets to emojis for easy visualization. Unicode emojis due to codeblock & hover mechanics being utilized.
                    #Iterate through all members/roles in the after channel permissions. K represents the member/role, and V represents the dict of {key: Value} pairs for permissions
                    for k,v in af.items():
                        #If the overwrites are different or an overwrite was created, add the target's name to the string, with the target's name left-aligned and trailing dashes
                        if before.overwrites_for(k) != after.overwrites_for(k) or b4.get(k) != af.get(k): displayString.append(f'{classification[type(k)]}{k.name:-<71}')
                        #This will get triggered if there is an overwrite target (role/member) in the after permissions, but not before. This means that a new overwrite target was added to this channel.
                        if not b4.get(k):
                            displayString[-1] = f'{classification[type(k)]}{k.name}{" (⭐Created)":-<71}' #If the overwrite was just created, edit the last string entry to represent that. The :-<80 means add dashes to fill spaces, with the words (created) left-aligned.
                            b4[k] = {key: None for key in v.keys()} #If the overwrite was just created, set the before values to None to represent that for the parser later on
                        #Iterate through Permission name: Value. value can be False, None, or True - the format for PermissionOverwrites.
                        for kk,vv in v.items():
                            #If the current permission_name: Value key is different than the previous value, make note of it
                            if not set({kk: vv}.items()).issubset(b4.get(k).items()):
                                #String format: Permission Name, left aligned with spaces to fill 50 character gap, Pipestem, (emoji symbol, centered (3 characters)) right aligned, with spaces to fill the left, pipestem right aligned,
                                displayString.append(f'''   {permissionKeys[kk]:<42} | {f"{english[b4[k][kk]]:^3}":^9} -|- {f"{english[vv]:^3}":^9} |''')
                    for k,v in b4.items(): #Added in January update because apparently this code leaves out instances of overwrites being completely removed
                        if af.get(k) is None: #An overwrite for role/member was deleted
                            af[k] = {key: None for key in v.keys()}
                            displayString.append(f'{classification[type(k)]}{k.name}{" (❌Removed)":-<71}')
                            for kk,vv in v.items():
                                if not set({kk: vv}.items()).issubset(af.get(k).items()):
                                    displayString.append(f'''   {permissionKeys[kk]:<42} | {f"{english[vv]:^3}":^9} -|- {f"{english[af[k][kk]]:^3}":^9} |''')
                    permissionString = f'''```{"Permission overwrites updated":<45} | {"Before":^10} | {"After":^10} |\n{newline.join([line.replace('-|-', '|') for line in displayString])}```'''
                    #permissionString = '```{0:<56}|{1:^13}|{2:^20}\n{3}```'.format('Permission overwrites updated', 'Before', 'After', '\n'.join(displayString))
                    for i, f in enumerate(embed.fields):
                        if 'Permission overwrites' in f.name and len(displayString) > 0: 
                            embed.set_field_at(i, name='Permission overwrites updated', value=f'''[Use 🇵 to toggle details • Hover for preview]({msg.jump_url} '{permissionString.replace("```", "")}')''' if len(permissionString) < 950 else 'Use 🇵 to toggle details')
                            break
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
                #Figure out what to do about the hover links.
                gainDescription = (f'''{newline.join([f"[{len(v)} member{'s' if len(v) != 1 else ''} gained {len(k.split(' '))} permission{'s' if len(k.split(' ')) != 1 else ''} • Hover for details]({msg.jump_url} '--MEMBERS--{newline}{newline.join([m.name for m in v]) if len(v) < 20 else joinKeys[0].join([m.name for m in v])}{newline}{newline}--PERMISSIONS--{newline}{newline.join([permissionKeys.get(p) for p in k.split(' ')]) if len(k.split(' ')) < 20 else joinKeys[1].join([permissionKeys.get(p) for p in k.split(' ')])}')" for k, v in gainedKeys.items()])}{newline if len(removedKeys) > 0 and len(gainedKeys) > 0 else ''}''') if len(gainedKeys) > 0 else ''
                removeDescription = f'''{newline.join([f"[{len(v)} member{'s' if len(v) != 1 else ''} lost {len(k.split(' '))} permission{'s' if len(k.split(' ')) != 1 else ''} • Hover for details]({msg.jump_url} '--MEMBERS--{newline}{newline.join([m.name for m in v]) if len(v) < 20 else joinKeys[0].join([m.name for m in v])}{newline}{newline}--PERMISSIONS--{newline}{newline.join([permissionKeys.get(p) for p in k.split(' ')]) if len(k.split(' ')) < 20 else joinKeys[1].join([permissionKeys.get(p) for p in k.split(' ')])}')" for k,v in removedKeys.items()])}''' if len(removedKeys) > 0 else ''
                if len(gainDescription) > 0 or len(removeDescription) > 0: embed.description+=f'{newline if len(gainDescription) > 0 or len(removeDescription) > 0 else ""}{gainDescription}{removeDescription}'
                else: 
                    if before.overwrites != after.overwrites: embed.description+='\nPermissions were updated, but no members were affected'
                if settings['embedTimestamp'] > 1: embed.description+=f'''\n{(clockEmoji(rawReceived) if settings['library'] > 0 else "🕰") if settings['context'][1] > 0 else ""}{"Timestamp" if settings['context'][1] < 2 else ""}: {received} {nameZone(after.guild)}'''
                await msg.edit(content = content if settings['plainText'] else None, embed=None if settings['plainText'] else embed)
                for reaction in reactions: await msg.add_reaction(reaction)
                try: 
                    if os.path.exists(savePath): os.remove(savePath)
                except: pass
        if (before.position != after.position or before.category != after.category) and not channelPosFlag:
            try: self.channelCacheHelper[after.guild.id].append(channelPosTimekey)
            except: self.channelCacheHelper[after.guild.id] = [channelPosTimekey]
            asyncio.create_task(self.delayedUpdateChannelIndexes(after.guild, channelPosTimekey))
        if type(before) is discord.TextChannel and before.name != after.name: await asyncio.gather(database.VerifyServer(after.guild, bot))
        try:
            if msg:
                final = copy.deepcopy(embed)
                while True:
                    def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
                    r = await self.bot.wait_for('reaction_add', check=reactionCheck)
                    if str(r[0]) == '🇵' and '🇵' in reactions:
                        await msg.edit(content=(permissionString[:1995] + '…```') if len(permissionString) > 2000 else permissionString)
                        def undoCheck(rr, u): return str(rr) == '🇵' and rr.message.id == msg.id and u.id == r[1].id
                        try: await self.bot.wait_for('reaction_remove', check=undoCheck, timeout=120)
                        except asyncio.TimeoutError: await msg.remove_reaction(r[0], r[1])
                        await msg.edit(content=None)
                    elif str(r[0]) == 'ℹ':
                        await msg.clear_reactions()
                        if 'Loading channel information' not in embed.description: embed.description+='\n\n{} Loading channel information: {}'.format(self.loading, after.name)
                        await msg.edit(embed=embed)
                        result = await self.ChannelInfo(after, None if after.type[0] == 'category' else await after.invites(), None if after.type[0] != 'text' else await after.pins(), await after.guild.audit_logs(limit=None).flatten())
                        await msg.edit(content=result[0], embed=result[1])
                        await msg.add_reaction('⬅')
                        def backCheck(rr, u): return str(rr) == '⬅' and rr.message.id == msg.id and u.id == r[1].id
                        try: await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                        except asyncio.TimeoutError: pass
                        await msg.edit(content=content,embed=final)
                        await msg.clear_reactions()
                        for r in reactions: await msg.add_reaction(r)
                    elif r[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                        await msg.edit(content=content, embed=None)
                        await msg.clear_reactions()
                        if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                    elif (r[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']) and len(msg.embeds) < 1:
                        await msg.edit(content=None, embed=embed)
                        await msg.clear_reactions()
                        if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])
                        for reaction in ['🇵', 'ℹ']: await msg.add_reaction(reaction)
        except UnboundLocalError: return

    async def delayedUpdateChannelIndexes(self, g: discord.Guild, timekey):
        '''Updates channel cache data after 3 seconds, to account for logging
        Timekey: Unique key based on timestamp that allows the update process to go through only if it hasn't already, reducing inaccuracies in data
        '''
        await asyncio.sleep(1)
        if timekey not in self.channelCacheHelper[g.id]: return
        for c in g.categories:
            try: self.categories[c.id] = [c for c in c.channels]
            except discord.Forbidden: pass
        try: self.categories[g.id] = [c[1] for c in g.by_category() if c[0] is None]
        except discord.Forbidden: pass
        self.channelCacheHelper[g.id].remove(timekey)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when channel is deleted'''
        rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(channel.guild.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        msg = None
        if logEnabled(channel.guild, "channel"):
            content=f'A moderator deleted the {channel.type[0]} channel named {channel.name}'
            f = None
            savePath = None
            settings = getCyberAttributes(channel.guild, 'channel')
            color = red[colorTheme(channel.guild)] if settings['color'][2] == 'auto' else settings['color'][2]
            embed=discord.Embed(
                title=f'''{self.channelEmoji(channel) if settings["context"][0] > 0 else ""}{(self.emojis["channelDelete"] if settings["library"] > 1 else self.emojis["delete"]) if settings["context"][0] > 0 else ""}{f"{channel.type[0][0].upper() + channel.type[0][1:]} Channel was deleted" if settings['context'][0] < 2 else ''}''',
                description=f'{self.channelKeys.get(channel.type[0]) if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {channel.name}',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            if readPerms(channel.guild, "channel"):
                try:
                    log = (await channel.guild.audit_logs(limit=1).flatten())[0]
                    if log.action == discord.AuditLogAction.channel_delete:
                        if settings['botLogging'] == 0 and log.user.bot: return
                        elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                        embed.description+=f'''\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Deleted by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name}){f"{newline}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}'''
                        if any(a > 1 for a in (settings['thumbnail'], settings['author'])):
                            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.author.is_avatar_animated() else 'gif'))
                            try: await log.user.author.avatar_url_as(size=1024).save(savePath)
                            except discord.HTTPException: pass
                            f = discord.File(savePath)
                            url = await self.uploadFiles(f)
                            if settings['thumbnail'] > 1 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                            if settings['author'] > 1 and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                            content = f'{log.user} deleted the {channel.type[0]} channel named {channel.name}'
                        await updateLastActive(log.user, datetime.datetime.now(), 'deleted a channel')
                except Exception as e: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            if settings['embedTimestamp'] > 1: embed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(channel.guild)}"
            embed.set_footer(text=f'Channel ID: {channel.id}')
            content += embedToPlaintext(embed)
            msg = await logChannel(channel.guild, "channel").send(content=content if 'audit log' in content or any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            if channel.type[0] != 'category':
                channelList = self.categories.get(channel.category.id) if channel.category is not None else self.categories.get(channel.guild.id)                
                startEnd = (channelList.index(channel) - 3 if channelList.index(channel) >= 3 else 0, channelList.index(channel) + 4 if channelList.index(channel) + 4 < len(channelList) else len(channelList))
                plainTextChannelList = f"{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList])}"
                embed.add_field(name=f'Category Tree',value=f'''{self.emojis['folder'] if settings['library'] > 1 else '📁'}{channel.category}\n{f"> [...Hover to view {len(channelList[:startEnd[0]])} more channel{'s' if len(channelList[:startEnd[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[:startEnd[0]])}'){newline}" if startEnd[0] > 0 else ""}{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList[startEnd[0]:startEnd[1]]])}{f"{newline}> [Hover to view {len(channelList[startEnd[1]:])} more channel{'s' if len(channelList[startEnd[1]:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[startEnd[1]:])}')" if startEnd[1] < len(channelList) else ""}''')
                if channel.category is not None: self.categories[channel.category.id].remove(channel)
                else: self.categories[channel.guild.id].remove(channel)
            if channel.type[0] == 'text': 
                try:
                    path = f'{indexes}/{channel.guild.id}/{channel.id}.json'
                    with open(path) as f:
                        indexData = json.load(f)
                        embed.add_field(name='Message count', value=len(indexData.keys()))
                    #The code below was the code that would archive message data for deleted channels. This didn't work because there was no way to identify the server this channel belonged to other than combing through logs.
                    # try:
                    #     archivePath = f'{indexes}/Archive'
                    #     try: os.makedirs(archivePath)
                    #     except FileExistsError: pass
                    #     with open(f'{archivePath}/{channel.id}.json', 'w+') as f:
                    #         f.write(json.dumps(indexData, indent=4))
                    #         os.remove(path)
                    # except Exception as e: print(f'Channel deletion file saving error: {e}')
                    #This following code will purge all index data for this channel upon its deletion
                    try:
                        channelIndexPath = f'{indexes}/{channel.guild.id}/{channel.id}.json'
                        os.remove(channelIndexPath)
                        channelAttachmentsPath = f'Attachments/{channel.guild.id}/{channel.id}'
                        shutil.rmtree(channelAttachmentsPath)
                    except Exception as e: print(f'Failed to delete index data for channel {channel.name} ({channel.id}) of server {channel.guild.name} ({channel.guild.id}) because {e}')
                except Exception as e: embed.add_field(name='Message count',value=f'Error: {e}')
                self.pins.pop(channel.id, None)
            await msg.edit(content = None if not settings['plainText'] else content, embed=embed)
            if os.path.exists(savePath): os.remove(savePath)
        if type(channel) is discord.TextChannel: asyncio.create_task(database.VerifyServer(channel.guild, bot))
        if msg:
            def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
            while True:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member joins a server'''
        rawReceived = member.joined_at + datetime.timedelta(hours=self.bot.lightningLogging.get(member.guild.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        global members
        asyncio.create_task(self.doorguardHandler(member))
        msg = None
        if logEnabled(member.guild, "doorguard"):
            newInv = []
            content=f'{member} joined the server'
            savePath = None
            f = []
            targetInvite = None
            settings = getCyberAttributes(member.guild, 'doorguard')
            color = green[colorTheme(member.guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            count = len(member.guild.members)
            ageDisplay = elapsedDuration(datetime.datetime.utcnow() - member.created_at, False)
            embed=discord.Embed(
                title=f'''{(f"{self.emojis['member'] if not member.bot else '🤖'}{self.emojis['greenPlus']}" if settings['library'] < 2 else self.emojis['memberJoin']) if settings['context'][0] > 0 else ''}{f"New {'member' if not member.bot else 'bot'}"} {self.loading}''',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not member.is_avatar_animated() else 'gif'))
                try: await member.avatar_url_as(size=1024).save(savePath)
                except discord.HTTPException: pass
                f = discord.File(savePath)
                url = await self.uploadFiles(f)
                if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=member.name, icon_url=url)
            try:
                newInv = await member.guild.invites()
                oldInv = self.invites.get(str(member.guild.id))
            except discord.Forbidden:
                content+="Tip: I can determine who invited new members if I have the `Manage Server` permissions"
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
                if not targetInvite: #If the vanity invite either doesn't exist or isn't the invite used, then it was an invite created between the invites were stored & now
                    for i in newInv:
                        if i.id not in [oi.id for oi in oldInv] and i.uses != 0: 
                            targetInvite = i
                            break
            except Exception as e: embed.add_field(name='Invite Details',value=f'Error retrieving details: {e}'[:1023])
            try: self.invites[str(member.guild.id)] = newInv
            except: pass
            msg = await logChannel(member.guild, "doorguard").send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            if member.bot and settings['read']:
                try:
                    log = (await member.guild.audit_logs(limit=1).flatten())[0]
                    if log.action == discord.AuditLogAction.bot_add:
                        embed.description = f'''
                            {"🤖" if settings['context'][1] > 0 else ''}{"Bot" if settings['context'][1] < 2 else ''}: {member.mention} ({member.name})
                            {self.emojis["details"] if settings['context'][1] > 0 else ''}{"Placement" if settings['context'][1] < 2 else ''}: {count}{suffix(count)} member
                            Top.gg stats (when applicable) will be available in the future'''
                        if any(a > 2 for a in (settings['thumbnail'], settings['author'])):
                            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.author.is_avatar_animated() else 'gif'))
                            try: await log.user.author.avatar_url_as(size=1024).save(savePath)
                            except discord.HTTPException: pass
                            f = discord.File(savePath)
                            url = await self.uploadFiles(f)
                            if settings['thumbnail'] > 2 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                            if settings['author'] > 2 and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                            content = f'{log.user} added {member.name} to the server'
                        await updateLastActive(log.user, datetime.datetime.now(), 'deleted a channel')
                except: pass
            else:
                descriptionString = [ #First: plaintext version, second: hover-links hybrid version
                    f'''
                        {self.emojis['member'] if settings['context'][1] > 0 else ''}{"Member" if settings['context'][1] < 2 else ''}: {f"{member.mention} ({member.name})"}
                        {self.emojis["details"] if settings['context'][1] > 0 else ''}{"Placement" if settings['context'][1] < 2 else ''}: {count}{suffix(count)} member
                        {f"{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(member.guild)}" if settings['embedTimestamp'] > 1 else ''}
                        {"📅" if settings['context'][1] > 0 else ''}{"Account created" if settings['context'][1] < 2 else ''}: {(member.created_at + datetime.timedelta(hours=timeZone(member.guild))):%b %d, %Y • %I:%M %p} {nameZone(member.guild)}
                        {"🕯" if settings['context'][1] > 0 else ''}{"Account age" if settings['context'][1] < 2 else ''}: {f"{', '.join(ageDisplay[:-1])} and {ageDisplay[-1]}" if len(ageDisplay) > 1 else ageDisplay[0]} old
                        {self.emojis["share"] if settings['context'][1] > 0 else ""}{"Mutual Servers" if settings['context'][1] < 2 else ''}: {len([g for g in bot.guilds if member in g.members])}\n
                        QUICK ACTIONS\nYou will be asked to confirm any of these quick actions via reacting with a checkmark after initiation, so you can click one to learn more without harm.\n🤐: Mute {member.name}\n🔒: Quarantine {member.name}\n👢: Kick {member.name}\n🔨: Ban {member.name}''', 
                    f'''
                        {self.emojis['member'] if settings['context'][1] > 0 else ''}{"Member" if settings['context'][1] < 2 else ''}: {f"{member.mention} ({member.name})"}
                        {self.emojis["details"] if settings['context'][1] > 0 else ''}{"Placement" if settings['context'][1] < 2 else ''}: {count}{suffix(count)} member
                        {"🕯" if settings['context'][1] > 0 else ''}{"Account age" if settings['context'][1] < 2 else ''}: {ageDisplay[0]} old
                        [Hover or react 🔽 for more details]({msg.jump_url} '
                        {"🕰" if settings['context'][1] > 0 else ''}{"Timestamp" if settings['context'][1] < 2 else ''}: {received} {nameZone(member.guild)}
                        {"📅" if settings['context'][1] > 0 else ''}{"Account created" if settings['context'][1] < 2 else ''}: {(member.created_at + datetime.timedelta(hours=timeZone(member.guild))):%b %d, %Y • %I:%M %p} {nameZone(member.guild)}
                        {"🕯" if settings['context'][1] > 0 else ''}{"Account age" if settings['context'][1] < 2 else ''}: {f"{', '.join(ageDisplay[:-1])} and {ageDisplay[-1]}" if len(ageDisplay) > 1 else ageDisplay[0]} old
                        {"🌐" if settings['context'][1] > 0 else ""}{"Mutual Servers" if settings['context'][1] < 2 else ''}: {len([g for g in bot.guilds if member in g.members])}\n
                        QUICK ACTIONS\nYou will be asked to confirm any of these quick actions via reacting with a checkmark after initiation, so you can click one to learn more without harm.\n🤐: Mute {member.name}\n🔒: Quarantine {member.name}\n👢: Kick {member.name}\n🔨: Ban {member.name}')'''
                    ]
                embed.description = descriptionString[1]
                if targetInvite: 
                    content=f'{targetInvite.inviter} invited {member} to the server'
                    if any(a > 2 for a in (settings['thumbnail'], settings['author'])):
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not targetInvite.inviter.is_avatar_animated() else 'gif'))
                        try: await targetInvite.inviter.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        url = await self.uploadFiles(f)
                        if settings['thumbnail'] > 2 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                        if settings['author'] > 2 and embed.author.name == discord.Embed.Empty: embed.set_author(name=targetInvite.inviter.name, icon_url=url)
                        content = f'{log.user} added {member.name} to the server'
                    inviteString = [ #First: plaintext version, second: hover-links hybrid version
                        f'''
                            {"👮‍♂️" if settings['context'][1] > 0 else ""}{"Invited by" if settings['context'][1] < 2 else ""}: {f"{targetInvite.inviter.name} ({targetInvite.inviter.mention})" if targetInvite.inviter else "N/A"}
                            {"🔗" if settings['context'][1] > 0 else ""}{"Code" if settings['context'][1] < 2 else ""}: discord.gg/{targetInvite.code}
                            {self.emojis["textChannel"] if settings["context"] > 0 else ""}{"Channel" if settings['context'][1] < 2 else ""}: {targetInvite.channel.name if targetInvite.channel else "N/A"}
                            {"📅" if settings['context'][1] > 0 else ""}{"Created" if settings['context'][1] < 2 else ""}: {targetInvite.created_at:%b %d, %Y • %I:%M %p} {nameZone(member.guild)}
                            {f"{'♾' if settings['context'][1] > 0 else ''}Never expires" if targetInvite.max_age == 0 else f"{'⏰' if settings['context'][1] > 0 else ''}Expires: {(datetime.datetime.utcnow() + datetime.timedelta(seconds=targetInvite.max_age)):%b %d, %Y • %I:%M %p} {nameZone(member.guild)}"}
                            {"🔓" if settings['context'][1] > 0 else ''}{"Used" if settings['context'][1] < 2 else ""}: {targetInvite.uses} of {"∞" if targetInvite.max_uses == 0 else targetInvite.max_uses} times''',
                        f'''
                            {"👮‍♂️" if settings['context'][1] > 0 else ""}{"Invited by" if settings['context'][1] < 2 else ""}: {f"{targetInvite.inviter.name} ({targetInvite.inviter.mention})" if targetInvite.inviter else "N/A"}
                            [Hover or react 🔽 for more details]({msg.jump_url} '
                            {"🔗" if settings['context'][1] > 0 else ""}{"Code" if settings['context'][1] < 2 else ""}: discord.gg/{targetInvite.code}
                            {"🚪" if settings["context"][1] > 0 else ""}{"Channel" if settings['context'][1] < 2 else ""}: {targetInvite.channel.name if targetInvite.channel else "N/A"}
                            {"📅" if settings['context'][1] > 0 else ""}{"Created" if settings['context'][1] < 2 else ""}: {targetInvite.created_at:%b %d, %Y • %I:%M %p} {nameZone(member.guild)}
                            {f"{'♾' if settings['context'][1] > 0 else ''}Never expires" if targetInvite.max_age == 0 else f"{'⏰' if settings['context'][1] > 0 else ''}Expires: {(datetime.datetime.utcnow() + datetime.timedelta(seconds=targetInvite.max_age)):%b %d, %Y • %I:%M %p} {nameZone(member.guild)}"}
                            {"🔓" if settings['context'][1] > 0 else ''}{"Used" if settings['context'][1] < 2 else ""}: {targetInvite.uses} of {"∞" if targetInvite.max_uses == 0 else targetInvite.max_uses} times'''
                        ]
                    embed.add_field(name='Invite Details',value=inviteString[1] if len(inviteString[1]) < 1024 else inviteString[0])
            await msg.edit(content = content if settings['plainText'] else None, embed=embed if not settings['plainText'] else None)
        members[member.guild.id] = member.guild.members
        await asyncio.gather(*[database.VerifyServer(member.guild, bot), database.VerifyUser(member, bot), updateLastActive(member, datetime.datetime.now(), 'joined a server')])
        try:
            if os.path.exists(savePath): os.remove(savePath)
        except: pass
        if msg:
            if member.id in [m.id for m in member.guild.members]:
                embed.title=f'''{(f"{self.emojis['member'] if not member.bot else '🤖'}{self.emojis['greenPlus']}" if settings['library'] < 2 else self.emojis['memberJoin']) if settings['context'][0] > 0 else ''}{f"New {'member' if not member.bot else 'bot'} (React ℹ for member info viewer)" if settings['context'][0] < 2 else ''}'''
                await msg.edit(content=msg.content, embed=embed if not settings['plainText'] else None)
                final = copy.deepcopy(embed)
                memberInfoEmbed = None
                reactions = [self.emojis['expand'], 'ℹ', '🤐', '🔒', '👢', '🔨']
                while True:
                    if len(msg.embeds) > 0:
                        for r in reactions: await msg.add_reaction(r)
                    embed = copy.deepcopy(final)
                    def navigationCheck(r, u): return not u.bot and r.message.id == msg.id
                    r = await self.bot.wait_for('reaction_add', check=navigationCheck)
                    if r[0].emoji in reactions or settings['plainText']:
                        embed.clear_fields()
                        await msg.clear_reactions()
                        editEmbed = True
                        if str(r[0]) == 'ℹ':
                            if not memberInfoEmbed:
                                embed.description = f'{self.loading}Please wait for member information to load'
                                await msg.edit(embed=embed)
                                memberInfoEmbed = await self.MemberInfo(member, addThumbnail=False, calculatePosts=True)
                                memberInfoEmbed.set_thumbnail(url=url)
                            await msg.edit(embed=memberInfoEmbed)
                            await msg.add_reaction('⬅')
                            def backCheck(rr, u): return str(rr) == '⬅' and u == r[1] and rr.message.id == msg.id
                            try: await self.bot.wait_for('reaction_add', check=backCheck, timeout=300)
                            except asyncio.TimeoutError: pass
                        elif str(r[0]) == '🤐':
                            if await database.ManageRoles(r[1]) and await database.ManageChannels(r[1]):
                                embed.description = f'{r[1].name}, would you like me to mute **{member.name}**?\n\nThis member will remain muted until the role RicobotAutoMute is manually removed from them.\n\nTo confirm, react {self.emojis["whiteCheck"]} within 10 seconds'
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
                                embed.description = f'{r[1].name}, would you like me to quarantine **{member.name}**?\n\nThis will prevent {member.name} from being able to access any of the channels in this server until the `unlock` command is run.\n\nTo confirm, react {self.emojis["whiteCheck"]} within 10 seconds'
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
                                embed.description = f'{r[1].name}, would you like me to kick **{member.name}**? Please react {self.emojis["whiteCheck"]} within 10 seconds to confirm. To provide a reason for the kick, react 📝 instead of check, and you will be able to provide a reason at the next step.'
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
                                embed.description = f'{r[1].name}, would you like me to ban **{member.name}** indefinitely? Please react {self.emojis["whiteCheck"]} within 10 seconds to confirm. To provide a reason for the ban, react 📝 instead of check, and you will be able to provide a reason at the next step.'
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
                        elif (r[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']):
                            if len(msg.embeds) > 0 and 'https://' in msg.embeds[0].description:
                                final.description = descriptionString[0]
                                try: final.set_field_at(0, name='**Invite Details**', value=inviteString[0])
                                except: pass
                                reactions.remove(self.emojis['expand'])
                            elif settings['plainText']: #Prevents this doing something for a completely redundant reason
                                await msg.edit(content=None, embed=final)
                                editEmbed = False
                            reactions.insert(0, self.emojis['collapse'])
                        elif r[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎'):
                            if len(msg.embeds) > 0 and 'https://' not in msg.embeds[0].description:
                                final.description = descriptionString[1]
                                try: final.set_field_at(0, name='**Invite Details**', value=inviteString[1])
                                except: pass
                                reactions.remove(self.emojis['collapse'])
                            elif settings['plainText']: #Prevents this doing something for a completely redundant reason
                                await msg.edit(content=content, embed=None)
                                editEmbed = False
                            reactions.insert(0, self.emojis['expand'])
                        await msg.clear_reactions()
                        if editEmbed: await msg.edit(embed=final)
            else:
                embed.title=f'''{(f"{self.emojis['member'] if not member.bot else '🤖'}{self.emojis['greenPlus']}" if settings['library'] < 2 else self.emojis['memberJoin']) if settings['context'][0] > 0 else ''}{f"New {'member' if not member.bot else 'bot'}" if settings['context'][0] < 2 else ''} (Left the server)'''
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
                        sendTo = await database.CalculateGeneralChannel(member.guild, self.bot, True)
                        if sendTo.permissions_for(member).read_messages: await sendTo.send(sendString) #If the member can read messages in the server's general channel, then we'll send it there
            if len(joinLogs) >= rj[0]:
                joinSpanDisplay = elapsedDuration(joinLogs[-1] - joinLogs[0])
                joinSpan = (joinLogs[-1] - joinLogs[0])
                if len(joinSpanDisplay) == 0: joinSpanDisplay = ['0 seconds']
                if joinSpan.seconds < rj[1]:
                    unbanAt = datetime.datetime.utcnow() + datetime.timedelta(seconds=rj[2])
                    timezoneUnbanAt = unbanAt + datetime.timedelta(hours=timeZone(member.guild))
                    try: await member.send(f'You have been banned from `{member.guild.name}` until {timezoneUnbanAt:%b %d, %Y • %I:%M %p} {nameZone(member.guild)} for repeatedly joining and leaving the server.')
                    except: pass
                    try: await member.ban(reason=f'''[Antispam: repeatedJoins] {member.name} joined the server {len(joinLogs)} times in {joinSpanDisplay}, and will remain banned until {f"{timezoneUnbanAt:%b %d, %Y • %I:%M %p} {nameZone(member.guild)}" if rj[2] > 0 else "the ban is manually revoked"}.''')
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
        rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(member.guild.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        global members
        asyncio.create_task(updateLastActive(member, datetime.datetime.now(), 'left a server'))
        message = None
        if logEnabled(member.guild, "doorguard"):
            content=f'{member} left the server'
            f = []
            settings = getCyberAttributes(member.guild, 'doorguard')
            color = red[colorTheme(member.guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            embed=discord.Embed(
                title=f'''{(f"{self.emojis['member'] if not member.bot else '🤖'}❌" if settings['library'] < 2 else self.emojis['memberLeave']) if settings['context'][0] > 0 else ''}{"Member left" if not member.bot else "Bot removed"} ({self.loading} Finalyzing log)''',
                description=f"{(self.emojis['member'] if not member.bot else '🤖') if settings['context'][1] > 0 else ''}{'Member' if settings['context'][1] < 2 and not member.bot else 'Bot' if settings['context'][1] < 2 and member.bot else ''}: {member.mention} ({member.name})",
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            hereForDisplay = elapsedDuration(datetime.datetime.utcnow() - member.joined_at)
            embed.add_field(name='Post count',value=self.loading)
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not member.is_avatar_animated() else 'gif'))
                try: await member.avatar_url_as(size=1024).save(savePath)
                except discord.HTTPException: pass
                f = discord.File(savePath)
                url = await self.uploadFiles(f)
                if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=member.name, icon_url=url)
            if readPerms(member.guild, 'doorguard'):
                try:
                    log = (await member.guild.audit_logs(limit=1).flatten())[0]
                    if absTime(datetime.datetime.utcnow(), log.created_at, datetime.timedelta(seconds=3)) and log.target.id == member.id:
                        if log.action == discord.AuditLogAction.kick:
                            embed.title = f'{(self.emojis["memberLeave"] if settings["library"] > 1 else self.emojis["member"]) if settings["context"][1] > 0 else ""}{"👢" if settings["context"][1] > 0 else ""}{member.name} was kicked'
                            embed.description=f'{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Kicked by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name})'
                            content=f'{log.user} kicked {member} from the server'
                        elif log.action == discord.AuditLogAction.ban:
                            embed.title = f'{(self.emojis["memberLeave"] if settings["library"] > 1 else self.emojis["member"]) if settings["context"][1] > 0 else ""}{self.emojis["ban"] if settings["context"][1] > 0 else ""}{member.name} was banned'
                            embed.description=f'{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Banned by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name})'
                            content=f'{log.user} banned {member} from the server'
                        embed.insert_field_at(0, name='Reason', value=log.reason if log.reason is not None else "None provided",inline=True if log.reason is not None and len(log.reason) < 25 else False)
                        if any(a > 2 for a in (settings['thumbnail'], settings['author'])):
                            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not member.is_avatar_animated() else 'gif'))
                            try: await member.avatar_url_as(size=1024).save(savePath)
                            except discord.HTTPException: pass
                            f = discord.File(savePath)
                            url = await self.uploadFiles(f)
                            if settings['thumbnail'] > 2 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                            if settings['author'] > 2 and embed.author.name == discord.Embed.Empty: embed.set_author(name=member.name, icon_url=url)
                except Exception as e: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            message = await logChannel(member.guild, 'doorguard').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            try:
                sortedMembers = sorted(members.get(member.guild.id), key=lambda x: x.joined_at)
                memberJoinPlacement = sortedMembers.index(member) + 1
                hoverPlainText = f'''
                    Here since: {(member.joined_at + datetime.timedelta(hours=timeZone(member.guild))):%b %d, %Y • %I:%M:%S %p} {nameZone(member.guild)}
                    Left at: {received}
                    Here for: {hereForDisplay}
                    Was the {memberJoinPlacement}{suffix(memberJoinPlacement)} member, now we have {len(sortedMembers) - 1}
                    '''
                embed.description += f"[Hover for more details]({message.jump_url} '{hoverPlainText}'')"
                #embed.description+=f"\n[Hover for more details]({message.jump_url} 'Here since: {(member.joined_at + datetime.timedelta(hours=timeZone(member.guild))):%b %d, %Y • %I:%M:%S %p} {nameZone(member.guild)}"
                #embed.description+=f'''\nLeft at: {received}\nHere for: {hereForDisplay}'''
                #embed.description+=f'\nWas the {memberJoinPlacement}{suffix(memberJoinPlacement)} member, now we have {len(sortedMembers) - 1}'
            except Exception as e: print(f'Member leave placement fail: {e}')
            if 'Finalizing' in embed.title: embed.title = f'''{(f"{self.emojis['member'] if not member.bot else '🤖'}❌" if settings['library'] < 2 else self.emojis['memberLeave']) if settings['context'][0] > 0 else ''}{f'{"Member left" if not member.bot else "Bot removed"}' if settings['context'][0] < 2 else ''}'''
            await message.edit(content = None if any((settings['flashText'], settings['tts'])) and not settings['plainText'] else content, embed=embed if not settings['plainText'] else None)
            embed.set_field_at(-1, name='**Post count**', value=await asyncio.create_task(self.MemberPosts(member)))
            await message.edit(embed=embed if not settings['plainText'] else None)
            if any((settings['flashText'], settings['tts']) and not settings['plainText']): await message.edit(content=None)
        members[member.guild.id] = member.guild.members
        try: 
            if os.path.exists(savePath): os.remove(savePath)
        except: pass
        await asyncio.gather(*[database.VerifyServer(member.guild, bot), database.VerifyUser(member, bot)])
        if message:
            def reactionCheck(r, u): return r.message.id == message.id and not u.bot
            while True:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(message.embeds) > 0:
                    await message.edit(content=content, embed=None)
                    await message.clear_reactions()
                    if not settings['plainText']: await message.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(message.embeds) < 1:
                    await message.edit(content=None, embed=embed)
                    await message.clear_reactions()
                    if settings['plainText']: await message.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        received = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(guild.id).get('offset'))).strftime('%b %d, %Y • %I:%M:%S %p')
        msg = None
        if logEnabled(guild, 'doorguard'):
            settings = getCyberAttributes(guild, 'doorguard')
            color = green[colorTheme(guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            embed=discord.Embed(
                title=f'''{f"{self.emojis['member']}{self.emojis['unban']}" if settings["context"][0] > 0 else ""}{"User was unbanned" if settings['context'] < 2 else ""}''',
                description=f"{self.emojis['member'] if settings['context'][1] > 0 else ''}{'User' if settings['context'][1] < 2 else ''}: {user.name}",
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            content=f'{user} was unbanned'
            f = []
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not user.is_avatar_animated() else 'gif'))
                try: await user.avatar_url_as(size=1024).save(savePath)
                except discord.HTTPException: pass
                f = discord.File(savePath)
                url = await self.uploadFiles(f)
                if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=user.name, icon_url=url)
            if readPerms(guild, 'doorguard'):
                try:
                    log = (await guild.audit_logs(limit=1, action=discord.AuditLogAction.unban).flatten())[0]
                    embed.description = f'{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Unbanned by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name})'
                    if any(a > 2 for a in (settings['thumbnail'], settings['author'])):
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        url = await self.uploadFiles(f)
                        if settings['thumbnail'] > 2 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                        if settings['author'] > 2 and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                    await updateLastActive(log.user, datetime.datetime.now(), 'unbanned a user')
                    async for log in guild.audit_logs(limit=None): #Attempt to find the ban audit log to pull ban details
                        if log.action == discord.AuditLogAction.ban:
                            if log.target.id == user.id:
                                content=f'{log.user} unbanned {user}'
                                bannedForDisplay = elapsedDuration(datetime.datetime.utcnow() - log.created_at)
                                embed.add_field(name="Old ban details",value=f'React {self.emojis["expand"]} to expand', inline=False)
                                longString = f'''
                                    {'👮‍♂️' if settings['context'][1] > 0 else ''}{'Banned by' if settings['context'][1] < 2 else ''}: {log.user.name} ({log.user.mention})
                                    {'📜' if settings['context'][1] > 0 else ''}{'Banned because' if settings['context'][1] < 2 else ''}: {log.reason if log.reason is not None else '<No reason specified>'}
                                    {f"{self.emojis['ban']}📅" if settings['context'][1] > 0 else ''}{'Banned at' if settings['context'][1] < 2 else ''}: {(log.created_at + datetime.timedelta(hours=timeZone(guild))):%b %d, %Y • %I:%M:%S %p} {nameZone(guild)}
                                    {f"{self.emojis['unban']}📅" if settings['context'][1] > 0 else ''}{'Unbanned at' if settings['context'][1] < 2 else ''}: {received}
                                    {f"{self.emojis['ban']}📅" if settings['context'][1] > 0 else ''}{'Banned for' if settings['context'][1] < 2 else ''}: {bannedForDisplay}'''
                                break
                except Exception as e: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            embed.set_footer(text=f'User ID: {user.id}')
            #if await database.SummarizeEnabled(guild, 'doorguard'):
            #    summaries.get(str(guild.id)).add('doorguard', 7, datetime.datetime.now(), data, embed,content=content)
            #else:
            msg = await logChannel(guild, 'doorguard').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            if not settings['plainText'] and any((settings['flashText'], settings['tts'])): await msg.edit(content=None)
            if msg and len(embed.fields) > 0:
                if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                while True:
                    def toggleCheck(r, u): return not u.bot and r.message.id == msg.id
                    r = await self.bot.wait_for('reaction_add', check=toggleCheck)
                    if r[0].emoji == self.emojis['expand']:
                        await msg.clear_reactions()
                        if len(msg.embeds) > 0 and 'to expand' in embed.fields[-1].value: #Normal functionality
                            embed.set_field_at(-1, name='Ban details', value=longString)
                            await msg.edit(embed=embed)
                            await msg.add_reaction(self.emojis['collapse'])
                        else: #Expand from Plaintext
                            await msg.edit(content=None, embed=embed)
                            for reaction in [self.emojis['expand'], self.emojis['collapse']]: await msg.add_reaction(reaction)
                    elif r[0].emoji == self.emojis['collapse']:
                        await msg.clear_reactions() #This line appears everywhere rather than in one place because RicoBot, way back then, had a notrious bug where my code logic caused it to remove any reactions added to log messages
                        if len(msg.embeds) > 0 and 'Banned because' in embed.fields[-1].value:
                            embed.set_field_at(-1, name='Ban details', value=f'React {self.emojis["expand"]} to expand')
                            await msg.edit(embed=embed)
                            await msg.add_reaction(self.emojis['expand'])
                            if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])
                        else: #Embed to plaintext
                            await msg.edit(content=content, embed=None)
                    elif settings['plainText']:
                        await msg.clear_reactions()
                        await msg.edit(content=None, embed=embed)
                        for reaction in [self.emojis['expand'], self.emojis['collapse']]: await msg.add_reaction(r)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        '''[DISCORD API METHOD] Called when member changes status/game, roles, or nickname; only the two latter events used with this bot'''
        try: 
            rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(after.guild.id).get('offset'))
            received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        except (KeyError, AttributeError): return
        msg = None
        if logEnabled(after.guild, 'member'):
            f = []
            content=''
            auditLogFail = False
            settings = getCyberAttributes(after.guild, 'member')
            color = blue[colorTheme(after.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed = discord.Embed(color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not after.is_avatar_animated() else 'gif'))
                try: await after.avatar_url_as(size=1024).save(savePath)
                except discord.HTTPException: pass
                f = discord.File(savePath)
                url = await self.uploadFiles(f)
                if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=after.name, icon_url=url)
            if (before.nick != after.nick or before.roles != after.roles) and logEnabled(before.guild, "member") and memberGlobal(before.guild) != 1:
                content=f"{before}'s server attributes were updated"
                #data = {'member': before.id, 'name': before.name, 'server': before.guild.id}
                embed.description=f'{self.emojis["member"] if settings["context"][1] > 0 else ""}{"Recipient" if settings["context"][1] < 2 else ""}: {before.mention} ({before.name})'
                if before.roles != after.roles:
                    #print(f'{datetime.datetime.now()} Member update - role for {after.name} in server {after.guild.name}')
                    br = len(before.roles)
                    ar = len(after.roles)
                    embed.title = f'''{f"{self.emojis['member']}🚩{self.emojis['greenPlus']}" if settings['context'][0] > 0 else ''}{f'Member gained {"roles" if ar - br > 1 else "a role"}' if settings['context'][0] < 2 else ''}''' if ar > br else f'''{f"{self.emojis['member']}🚩❌" if settings['context'][0] > 0 else ''}{f'Member lost {"roles" if br - ar > 1 else "a role"}' if settings['context'][0] < 2 else ''}''' if ar < br else f'''{f"{self.emojis['member']}🚩✏" if settings['context'][0] > 0 else ''}{'Member roles moodified' if settings['context'][0] < 2 else ''}'''
                    try:
                        log = (await before.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update).flatten())[0]
                        if log.target.id == before.id: 
                            if settings['botLogging'] == 0 and log.user.bot: return
                            elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                            embed.description += f'\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Moderator" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name})'
                            if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and embed.thumbnail.url == discord.Embed.Empty)) or (settings['author'] > 2 or (settings['author'] == 2 and embed.author.name == discord.Embed.Empty)):
                                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                                try: await log.user.avatar_url_as(size=1024).save(savePath)
                                except discord.HTTPException: pass
                                f = discord.File(savePath)
                                url = await self.uploadFiles(f)
                                content = f"{log.user} updated {before}'s server attributes"
                                if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and embed.thumbnail.url == discord.Embed.Empty): embed.set_thumbnail(url=url)
                                if settings['author'] > 2 or (settings['author'] == 2 and embed.author.name == discord.Embed.Empty): embed.set_author(name=log.user.name, icon_url=url)
                            await updateLastActive(log.user, datetime.datetime.now(), 'updated someone\'s roles')
                    except Exception as e: auditLogFail = e
                    added = sorted([r for r in after.roles if r not in before.roles], key = lambda r: r.position)
                    removed = sorted([r for r in before.roles if r not in after.roles and r.id in [role.id for role in after.guild.roles]], key = lambda r: r.position)
                    for r in added:
                        if r.id in [role.id for role in after.guild.roles]: self.roles[r.id] = r.members
                    for r in removed:
                        if r.id in [role.id for role in after.guild.roles]: self.roles[r.id] = r.members
                    if len(added) > 0: 
                        embed.add_field(name=f'Role{"s" if len(added) > 1 else ""} added', value='\n'.join([r.name for r in added]))
                    if len(removed) > 0: 
                        embed.add_field(name=f'Role{"s" if len(removed) > 1 else ""} removed', value='\n'.join([r.name for r in removed]))
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
                            if rolePermissions:
                                lPK += rolePermissions
                                lostList.append(f'{r.name}\n> {", ".join(rolePermissions)}')
                        for r in added:
                            rolePermissions = [permissionKeys[p[0]] for p in r.permissions if permissionKeys[p[0]] in afterPerms and permissionKeys[p[0]] not in beforePerms and p in iter(r.permissions) and permissionKeys[p[0]] not in gPK]
                            if rolePermissions:
                                gPK += rolePermissions
                                gainedList.append(f'{r.name}\n> {", ".join(rolePermissions)}')
                        if len(lost) > 0: embed.add_field(name='Lost permissions', value='\n'.join(lostList), inline=False)
                        if len(gained) > 0: embed.add_field(name='Gained permissions', value='\n'.join(gainedList), inline=False)
                        self.memberPermissions[after.guild.id][after.id] = after.guild_permissions
                if before.nick != after.nick:
                    #print(f'{datetime.datetime.now()} Member update - nickname for {after.name} in server {after.guild.name}')
                    embed.title = f'''{f"{self.emojis['member'] if settings['library'] > 0 else '👤'}📄{self.emojis['edit'] if settings['library'] > 0 else '✏'}" if settings['context'][0] > 0 else ''}{"Member nickname updated" if settings['context'][0] < 2 else ''}'''
                    try:
                        log = (await before.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update).flatten())[0]
                        if log.target.id == before.id: 
                            embed.description += f'\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Moderator" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name})'
                            if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and embed.thumbnail.url == discord.Embed.Empty)) or (settings['author'] > 2 and (settings['author'] == 2 and embed.author.name == discord.Embed.Empty)):
                                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                                try: await log.user.avatar_url_as(size=1024).save(savePath)
                                except discord.HTTPException: pass
                                f = discord.File(savePath)
                                url = await self.uploadFiles(f)
                                content = f"{log.user} updated {before}'s server attributes"
                                if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and embed.thumbnail.url == discord.Embed.Empty): embed.set_thumbnail(url=url)
                                if settings['author'] > 2 or (settings['author'] == 2 and embed.author.name == discord.Embed.Empty): embed.set_author(name=log.user.name, icon_url=url)
                            await updateLastActive(log.user, datetime.datetime.now(), 'updated a nickname')
                    except Exception as e: auditLogFail = e
                    oldNick = before.nick if before.nick is not None else "<No nickname>"
                    newNick = after.nick if after.nick is not None else "<No nickname>"
                    embed.add_field(name="Old nickname",value=oldNick)
                    embed.add_field(name="New nickname",value=newNick)
                    #data['oldNick'] = oldNick
                    #data['newNick'] = newNick
                if settings['embedTimestamp'] > 1: embed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(after.guild)}"
                embed.set_footer(text=f'Member ID: {after.id}')
                try: content = f"{log.user} updated {before}'s server attributes"
                except: content = f"{before}'s server attributes were updated"
                content += embedToPlaintext(embed)
                if auditLogFail: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{auditLogFail}`'
                if len(embed.fields) > 0:
                    msg = await logChannel(after.guild, 'member').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
                    if not settings['plainText'] and any((settings['flashText'], settings['tts'])): await msg.edit(content=None)
                try:
                    if os.path.exists(savePath): os.remove(savePath)
                except: pass
        if before.guild_permissions != after.guild_permissions: await self.CheckDisguardServerRoles(after, mode=0, reason='Member permissions changed')
        #halfwayStart = datetime.datetime.now()
        for g in self.bot.guilds:
            if after.id in [m.id for m in g.members]:
                targetServer = g
                break
        #One server, selected to avoid duplication and unnecessary calls since this method is called simultaneously for every server a member is in
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
                            if {'e': None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), 'n': a.name} != {'e': user.get('customStatusHistory')[-1].get('emoji'), 'n': user.get('customStatusHistory')[-1].get('name')}: 
                                if not (await database.GetUser(after)).get('customStatusHistory'):
                                    asyncio.create_task(database.AppendCustomStatusHistory(after, None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), a.name))
                        except AttributeError as e: print(f'Attribute error: {e}')
                        except TypeError: asyncio.create_task(database.AppendCustomStatusHistory(after, None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), a.name)) #If the customStatusHistory is empty, we create the first entry
                        newMemb = before.guild.get_member(before.id)
                        if before.status == newMemb.status and before.name != newMemb.name: await updateLastActive(after, datetime.datetime.now(), 'changed custom status')
        if before.guild_permissions != after.guild_permissions: asyncio.create_task(database.VerifyUser(before, self.bot))
        if msg:
            def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
            while True:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        '''[DISCORD API METHOD] Called when a user changes their global username, avatar, or discriminator'''
        initialReceived = datetime.datetime.utcnow()
        servers = [s for s in bot.guilds if after.id in [m.id for m in s.members]] #Building a list of servers the updated member is in - then we'll calculate logging module permissions for each server
        membObj = [m for m in servers[0].members if m.id == after.id][0] #Fetching the discord.Member object for later use
        embed = discord.Embed(description='')
        content = f'{after.name} updated their global attrubutes'
        legacyTitleEmoji = []
        newTitleEmoji = []
        titles = []
        f = []
        try: thumbnailURL = self.bot.lightningUsers.get(after.id).get('avatarHistory')[-1].get('imageURL')
        except (TypeError, AttributeError): 
            thumbnailURL = before.avatar_url_as(static_format='png', size=1024)
        embed.set_thumbnail(url=thumbnailURL)
        if before.avatar_url != after.avatar_url:
            titles.append('Profile Picture')
            legacyTitleEmoji.append('🖼')
            newTitleEmoji.append(self.emojis['imageAdd'])
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not after.is_avatar_animated() else 'gif'))
            await after.avatar_url_as(size=1024).save(savePath)
            tempFile = discord.File(savePath)
            #Have to make use of the image log channel for the pupose of hover links. Optionally, edit the message once we have the image URL in the embed, but this will be expensive, especially when this may go to multiple servers
            message = await self.imageLogChannel.send(file=tempFile)
            embed.set_image(url=message.attachments[0].url) #New avatar
            embed.add_field(name="Profile picture updated", value=f"Old: [Thumbnail to the right]({thumbnailURL})\nNew: [Image below]({message.attachments[0].url})", inline=False)
            content += f'\n•Profile picture'
            await updateLastActive(after, datetime.datetime.now(), 'updated their profile picture')
            asyncio.create_task(database.AppendAvatarHistory(after, message.attachments[0].url))
            if os.path.exists(savePath): os.remove(savePath)
        if before.discriminator != after.discriminator:
            #data['discrim'] = True
            titles.append('Discriminator')
            legacyTitleEmoji.append('🔢')
            newTitleEmoji.append(self.emojis['discriminator'])
            embed.add_field(name="Old discriminator",value=before.discriminator)
            embed.add_field(name="New discriminator",value=after.discriminator)
            content += f'\n•Discriminator'
            await updateLastActive(after, datetime.datetime.now(), 'updated their discriminator')
        if before.name != after.name:
            titles.append('Username')
            legacyTitleEmoji.append('📄')
            newTitleEmoji.append(self.emojis['richPresence'])
            embed.add_field(name="Old username",value=before.name)
            embed.add_field(name="New username",value=after.name)
            content += f'\n•Discriminator'
            await updateLastActive(after, datetime.datetime.now(), 'updated their username')
            asyncio.create_task(database.AppendUsernameHistory(after))
            asyncio.create_task(database.VerifyUser(membObj, bot))
        embed.set_footer(text=f'User ID: {after.id}')
        for server in servers:
            try:
                if logEnabled(server, 'member') and memberGlobal(server) != 0:
                    rawReceived = initialReceived + datetime.timedelta(hours=self.bot.lightningLogging.get(server.id).get('offset'))
                    received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
                    settings = getCyberAttributes(server, 'member')
                    color = blue[colorTheme(server)] if settings['color'][1] == 'auto' else settings['color'][1]
                    newEmbed = copy.deepcopy(embed)
                    newContent = content + embedToPlaintext(embed)
                    #We have to customize embeds for each specific server. First, embed title and description
                    titleEmoji = legacyTitleEmoji if settings['library'] == 0 else [str(emoji) for emoji in newTitleEmoji]
                    titleBase = f'''{f"{self.emojis['member'] if settings['library'] > 0 else '👤'}{''.join(titleEmoji)}{self.emojis['edit'] if settings['library'] > 0 else '✏'}" if settings['context'][0] > 0 else ''}'''
                    if len(titles) == 3 and settings['context'][0] < 2: newEmbed.title = f"{titleBase}User's {', '.join(titles)} updated"
                    elif len(titles) != 3: newEmbed.title = f"{titleBase}User's {' & '.join(titles)} updated"
                    if before.name == after.name: newEmbed.description = f'''{f"{self.emojis['member'] if settings['library'] > 0 else '👤'}" if settings['context'][1] > 0 else ''}{'Member' if settings['context'][1] < 2 else ''}: {after.mention} ({after.name})'''
                    if settings['embedTimestamp'] > 1: newEmbed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(server)}"
                    #Next, color and timestamp
                    newEmbed.color = color
                    if settings['embedTimestamp']: newEmbed.timestamp = initialReceived
                    #Then, thumbnail/author
                    if any(a > 0 for a in (settings['thumbnail'], settings['author'])) and before.avatar_url == after.avatar_url:
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not message.author.is_avatar_animated() else 'gif'))
                        try: await after.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        url = await self.uploadFiles(f)
                        if settings['thumbnail'] > 0 and embed.thumbnail.url == discord.Embed.Empty: newEmbed.set_thumbnail(url=url)
                        if settings['author'] > 0 and embed.author.name == discord.Embed.Empty: newEmbed.set_author(name=after.name, icon_url=url)
                    msg = await logChannel(server, 'member').send(content = newContent if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=newEmbed if not settings['plainText'] else None, files=f if not settings['plainText'] else [], tts=settings['tts'])
                    if not settings['plainText'] and any((settings['flashText'], settings['tts'])): await msg.edit(content=None)
            except: pass
        for s in servers: asyncio.create_task(database.VerifyServer(s, bot))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot joins a server'''
        await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name=f'{len(self.bot.guilds)} servers', type=discord.ActivityType.watching))
        embed = discord.Embed(title=f'{self.emojis["greenPlus"]}Joined server', description=f'{guild.name}\n{guild.member_count} Members\nCreated {guild.created_at:%b %d, %Y • %I:%M %p} EDT', color=green[1])
        embed.set_footer(text=guild.id)
        await self.globalLogChannel.send(embed=embed)
        asyncio.create_task(database.VerifyServer(guild, bot))
        for member in guild.members:
            await database.VerifyUser(member, bot)
        content=f"Thank you for inviting me to {guild.name}!\n\n--Quick Start Guide--\n🔗Disguard Website: <https://disguard.netlify.com>\n{qlf}{qlf}Contains links to help page, server configuration, Disguard's official server, inviting the bot to your own server, and my GitHub repository\n🔗Configure your server's settings: <https://disguard.herokuapp.com/manage/{guild.id}>"
        content+=f'\nℹMy default prefix is `.` and can be changed on the online dashboard under "General Server Settings."\n\n❔Need help with anything, or just have a question? My developer would be more than happy to resolve your questions or concerns - you can quickly get in touch with my developer in the following ways:\n{qlf}Open a support ticket using the `.ticket` command\n{qlf}Join my support server: <https://discord.gg/xSGujjz>'
        try: target = await database.CalculateModeratorChannel(guild, self.bot, False)
        except:
            if guild.system_channel: target = guild.system_channel
            else:
                for channel in guild.text_channels:
                    if 'general' in channel.name: 
                        target = channel
                        break
        try: await target.send(content)
        except: pass
        await self.CheckDisguardServerRoles(guild.members, mode=1, reason='Bot joined a server')
        await asyncio.gather(*[self.indexServer(c) for c in guild.text_channels])

    async def indexServer(self, channel):
        '''This will fully index messages.'''
        path = f'{indexes}/{channel.guild.id}/{channel.id}'
        try: os.makedirs(path)
        except FileExistsError: pass
        indexData = {}
        try:
            async for message in channel.history(limit=None, oldest_first=True):
                if str(message.id) in indexData.keys(): 
                    break 
                indexData[str(message.id)] = {'author0': message.author.id, 'timestamp0': message.created_at.isoformat(), 'content0': '<Hidden due to channel being NSFW>' if channel.is_nsfw() else message.content if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<No content>"}
                await asyncio.sleep(0.0025)
            indexData = json.dumps(indexData, indent=4)
            with open(f'{path}.json', "w+") as f:
                f.write(indexData)
        except Exception as e: print(f'Index error for {channel.guild.name} - {channel.name}: {e}')

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(after.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        message = None
        if logEnabled(before, 'server'):
            content = 'Server settings were updated'
            f = []
            settings = getCyberAttributes(after, 'server')
            color = blue[colorTheme(after.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed=discord.Embed(title=f'{(self.emojis["serverUpdate"] if settings["library"] > 0 else "✏") if settings["context"][0] > 0 else ""}{"Server updated (React ℹ to view server details)" if settings["context"][0] < 2 else ""}', color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            if readPerms(before, 'server'):
                try:
                    log = (await after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update).flatten())[0]
                    if settings['botLogging'] == 0 and log.user.bot: return
                    elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                    embed.description = f'''{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Updated by' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.name}){f"{newline}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}'''
                    if any(a > 2 for a in (settings['thumbnail'], settings['author'])):
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        url = await self.uploadFiles(f)
                        if settings['thumbnail'] > 2 and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                        if settings['author'] > 2 and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                        content = f'{log.user} updated server settings'
                    await updateLastActive(log.user, datetime.datetime.now(), 'updated a server')
                except Exception as e: content+=f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            if before.afk_channel != after.afk_channel:
                embed.add_field(name='AFK Channel', value=f"{before.afk_channel.name if before.afk_channel else '<None>'} → **{after.afk_channel.name if after.afk_channel else '<None>'}**")
            if before.afk_timeout != after.afk_timeout:
                timeouts = [[before.afk_timeout, 'second'], [after.afk_timeout, 'second']]
                for t in timeouts:
                    if t[0] and t[0] >= 60:
                        t[0] //= 60
                        t[1] = 'minute'
                        if t[0] >= 60:
                            t[0] //= 60
                            t[1] = 'hour'
                embed.add_field(name='AFK Timeout', value=f'{timeouts[0][0]} {timeouts[0][1]}{"s" if timeouts[0][0] != 1 else ""} → **{timeouts[1][0]} {timeouts[1][1]}{"s" if timeouts[1][0] != 1 else ""}**')
            if before.mfa_level != after.mfa_level:
                values = {0: False, 1: True}
                embed.add_field(name='2FA Requirement for Mods', value=f'{values[before.mfa_level]} → **{after.mfa_level}**')
            if before.name != after.name:
                embed.add_field(name='Name', value=f'{before.name} → **{after.name}**')
            if before.owner != after.owner:
                embed.add_field(name='Owner', value=f'{before.owner.mention} ({before.owner.name}) → **{after.owner.mention} ({after.owner.name})**')
                o = f'{after.owner.mention} ({after.owner.name}), ownership of {after.name} has been transferred to you from {before.owner.mention} ({before.owner.name})'
                if not content: content = o
                else: content += f'\n{o}'
                await self.CheckDisguardServerRoles(after.guild.members, mode=0, reason='Server owner changed')
            if before.default_notifications != after.default_notifications:
                values = {'all_messages': 'All messages', 'only_mentions': 'Only mentions'}
                embed.add_field(name='Default Notifications', value=f'{values[before.default_notifications.name]} → **{values[after.default_notifications.name]}**')
            if before.explicit_content_filter != after.explicit_content_filter:
                values = {'disabled': 'Disabled', 'no_role': 'Filter for members without a role', 'all_members': 'Filter for everyone'}
                embed.add_field(name='Explicit Content Filter', value=f'{values[before.explicit_content_filter.name]} → **{values[after.explicit_content_filter.name]}**')
            if before.system_channel != after.system_channel:
                embed.add_field(name='System channel', value=f"{f'{before.system_channel.mention} ({before.system_channel.name})' if before.system_channel else '<None>'} → {f'{after.system_channel.mention} ({after.system_channel.name})' if after.system_channel else '<None>'}")
            if before.icon_url != after.icon_url:
                message = await self.imageLogChannel.send(before.icon_url_as(static_format='png'))
                thumbURL = message.attachments[0].url
                message = await self.imageLogChannel.send(after.icon_url_as(static_format='png'))
                imageURL = message.attachments[0].url
                embed.set_thumbnail(url=thumbURL)
                embed.set_image(url=imageURL)
                embed.add_field(name='Server icon updated',value=f'Old: [Thumbnail to the right]({thumbURL})\nNew: [Image below]({imageURL})')
            asyncio.create_task(database.VerifyServer(after, bot))
            if message and len(embed.fields) > 0:
                reactions = ['ℹ']
                if settings['embedTimestamp'] > 1: embed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(after)}"
                content += embedToPlaintext(embed)
                message = await logChannel(before, 'server').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'], allowed_mentions=discord.AllowedMentions(users=[after.owner]))
                if any((settings['tts'], settings['flashText'])) and not settings['plainText']: await message.edit(content=None)
                for r in reactions: await message.add_reaction(r)
                final = copy.deepcopy(embed)
                while True:
                    def reactionCheck(r, u): return r.message.id == message.id and not u.bot
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                    if str(result[0]) == 'ℹ':
                        if 'Loading server information' not in embed.description: embed.description+=f'\n\n{self.loading}Loading server information'
                        await message.edit(embed=embed)
                        logs, bans, hooks, invites = None, None, None, None
                        try:
                            logs = await after.audit_logs(limit=None).flatten()
                            bans = await after.bans()
                            hooks = await after.webhooks()
                            invites = await after.invites()
                        except: pass
                        new = await self.ServerInfo(after, logs, bans, hooks, invites)
                        if embed.author.name: new.set_author(icon_url=url, name=log.user.name)
                        await message.edit(embed=new)
                        await message.clear_reactions()
                        await message.add_reaction('⬅')
                        def backCheck(r, u): return str(r) == '⬅' and r.message.id == message.id and u.id == result[1].id
                        try: await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                        except asyncio.TimeoutError: pass
                        await message.edit(content=content, embed=final)
                        await message.clear_reactions()
                        for r in reactions: await message.add_reaction(r)
                    elif result[0].emoji == self.emojis['collapse'] and len(message.embeds) > 0:
                        await message.edit(content=content, embed=None)
                        await message.clear_reactions()
                    elif settings['plainText'] and len(message.embeds) < 1:
                        await message.edit(content=None, embed=embed)
                        await message.clear_reactions()
                        reactions.append(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot leaves a server'''
        embed = discord.Embed(title="❌Left server", description=f'{guild.name}', color=red[1])
        embed.set_footer(text=guild.id)
        await self.globalLogChannel.send(embed=embed)
        await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name=f'{len(self.bot.guilds)} servers', type=discord.ActivityType.watching))
        asyncio.create_task(database.VerifyServer(guild, bot))
        await self.CheckDisguardServerRoles(guild.members, mode=2, reason='Bot left a server')
        path = f'Attachments/{guild.id}'
        shutil.rmtree(path)
        for member in guild.members:
            await database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is created'''
        rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(role.guild.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        msg = None
        if logEnabled(role.guild, "role"):
            content = f'The role "{role.name}" was created'
            f = None
            settings = getCyberAttributes(role.guild, 'role')
            color = green[colorTheme(role.guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            embed=discord.Embed(
                title=f'''{(self.emojis['roleCreate'] if settings['library'] > 1 else f"🚩{self.emojis['greenPlus']}") if settings['context'][0] > 0 else ''}{'Role created' if settings['context'][0] < 2 else ''}''',
                description=f'''{(self.emojis["richPresence"] if settings['library'] > 0 else '📄') if settings['context'][1] > 0 else ''}{'Name' if settings['context'][1] < 2 else ''}: {role.name}''' if role.name != 'new role' else '',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            embed.set_footer(text=f'Role ID: {role.id}')
            if readPerms(role.guild, "role"):
                try:
                    log = (await role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create).flatten())[0]
                    if settings['botLogging'] == 0 and log.user.bot: return
                    elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                    embed.description += f'''\n👮‍♂️Created by: {log.user.mention} ({log.user.name}){f"{newline}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}'''
                    if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        url = await self.uploadFiles(f)
                        content = f'{log.user} created the role "{role.name}"'
                        if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                        if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                    await updateLastActive(log.user, datetime.datetime.now(), 'created a role')
                except Exception as e: content+=f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            if settings['embedTimestamp'] > 1: embed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(role.guild)}"
            content += embedToPlaintext(embed)
            msg = await logChannel(role.guild, 'role').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            if any((settings['tts'], settings['flashText'])) and not settings['plainText']: await msg.edit(content=None)
        self.roles[role.id] = role.members
        asyncio.create_task(database.VerifyServer(role.guild, bot))
        if msg:
            def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
            while True:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is deleted'''
        rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(role.guild.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        message = None
        roleMembers = []
        if logEnabled(role.guild, "role"):
            content=f'The role "{role.name}" was deleted'
            f = None
            settings = getCyberAttributes(role.guild, 'role')
            color = red[colorTheme(role.guild)] if settings['color'][2] == 'auto' else settings['color'][2]
            embed=discord.Embed(
                title=f'''{(self.emojis['roleDelete'] if settings['library'] > 1 else '🚩❌') if settings['context'][0] > 0 else ''}Role deleted {self.loading}''',
                description=f'{"🚩" if settings["context"][1] > 0 else ""}{"Role" if settings["context"][1] < 2 else ""}: {role.name}',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            embed.set_footer(text='Role ID: {}'.format(role.id))
            if readPerms(role.guild, "role"):
                try:
                    log = (await role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete).flatten())[0]
                    if settings['botLogging'] == 0 and log.user.bot: return
                    elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                    embed.description += f'''\n👮‍♂️Deleted by: {log.user.mention} ({log.user.name}){f"{newline}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}'''
                    if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        url = await self.uploadFiles(f)
                        content = f'{log.user} deleted the role "{role.name}"'
                        if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                        if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                    await updateLastActive(log.user, datetime.datetime.now(), 'deleted a role')
                except Exception as e: content+=f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            content += embedToPlaintext(embed)
            message = await logChannel(role.guild, 'role').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
            #Cache role members, and expel them upon role deletion. work for 2021.
            roleMembers = self.roles.get(role.id)
            if roleMembers:
                membersWhoLost = '\n'.join([f'👤{m.name}' for m in roleMembers]) if len(roleMembers) < 20 else '👤'.join([m.name for m in roleMembers]) if len(roleMembers) < 100 else '' #Last branch prevents unnecessary computations
                embed.description += f'\n{self.emojis["details"] if settings["context"][1] > 0 else ""}' + ('Nobody lost this role upon its deletion' if len(roleMembers) < 1 else f"[{len(roleMembers)} members lost this role upon its deletion]({message.jump_url} '{membersWhoLost}')" if len(roleMembers) < 100 else f'{len(roleMembers)} members lost this role upon its deletion')
                embed = self.PermissionChanges(roleMembers, message, embed)
            if settings['embedTimestamp'] > 1: embed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(role.guild)}"
            embed.title = f'''{(self.emojis['roleDelete'] if settings['library'] > 1 else f'🚩{self.emojis["delete"]}') if settings['context'][0] > 0 else ''}{'Role deleted (React ℹ for role information)' if settings['context'][0] < 2 else ''}'''
            if any((settings['tts'], settings['flashText'])) and not settings['plainText']: await message.edit(content=None)
            if not settings['plainText']: await message.edit(embed=embed)
            reactions = ['ℹ']
            for r in reactions: await message.add_reaction(r)
            final, roleInfo = copy.deepcopy(embed), None
        self.roles.pop(role.id, None)
        await self.CheckDisguardServerRoles(roleMembers if roleMembers else role.guild.members, mode=2, reason='Server role was deleted; member lost permissions')
        asyncio.create_task(database.VerifyServer(role.guild, bot))
        for member in role.members:
            await database.VerifyUser(member, bot)
        if message:
            while True:
                def reactionCheck(r, u): return r.message.id == message.id and not u.bot
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if str(result[0]) == 'ℹ':
                    if 'Loading role information' not in embed.description: embed.description+=f'\n\n{self.loading}Loading role information'
                    await message.edit(embed=embed)
                    try: logs = await role.guild.audit_logs(limit=None).flatten()
                    except: logs = None
                    if not roleInfo: 
                        roleInfo = await self.RoleInfo(role, logs)
                        if embed.author.name: roleInfo.set_author(icon_url=url, name=log.user.name)
                    await message.edit(embed=roleInfo)
                    await message.clear_reactions()
                    await message.add_reaction('⬅')
                    def backCheck(r, u): return str(r) == '⬅' and r.message.id == message.id and u.id == result[1].id
                    try: await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                    except asyncio.TimeoutError: pass
                    await message.edit(content=content, embed=final)
                    await message.clear_reactions()
                    for r in reactions: await message.add_reaction(r)
                elif result[0].emoji == self.emojis['collapse'] and len(message.embeds) > 0:
                    await message.edit(content=content, embed=None)
                    await message.clear_reactions()
                elif settings['plainText'] and len(message.embeds) < 1:
                    await message.edit(content=None, embed=embed)
                    await message.clear_reactions()
                    reactions.append(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is updated'''
        rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(after.guild.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        message = None
        if logEnabled(before.guild, 'role'):
            content = f'The role "{before.name}" was updated'
            f = None
            settings = getCyberAttributes(after.guild, 'role')
            color = blue[colorTheme(after.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed=discord.Embed(
                title=f'''{(self.emojis['roleEdit'] if settings['library'] > 1 else '🚩✏')}{'Role was updated (React ℹ to view role details)' if settings['context'][0] < 2 else ''}''',
                description=f'''{'🚩' if settings['context'] > 0 else ''}{'Role' if settings['context'][1] < 2 else ''}: {after.mention}{f" ({after.name})" if after.name == before.name else ""}''',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            if after.name != before.name: embed.description += f'''\n{self.emojis['richPresence'] if settings['context'][1] > 0 else ''}Name: {before.name} → **{after.name}**'''
            if readPerms(before.guild, "role"):
                try:
                    log = (await after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update).flatten())[0]
                    if settings['botLogging'] == 0 and log.user.bot: return
                    elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                    embed.description += f'''\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Updated by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name}){f"{newline}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}'''
                    if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        url = await self.uploadFiles(f)
                        content = f'{log.user} updated the role "{before.name}"'
                        if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
                        if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=log.user.name, icon_url=url)
                    await updateLastActive(log.user, datetime.datetime.now(), 'updated a role')
                except Exception as e: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            embed.set_footer(text=f'Role ID: {before.id}')
            reactions = ['ℹ']
            if before.color != after.color:
                embed.add_field(name='Old color', value=f'RGB{before.color.to_rgb()}\nHex: {before.color}\nReact {self.emojis["shuffle"]} to display')
                embed.add_field(name='New color', value=f'**RGB{after.color.to_rgb()}\nHex: {after.color}\nDisplayed on embed border**')
                embed.color = after.color
                reactions.append(self.emojis['shuffle'])
            if before.hoist != after.hoist: embed.add_field(name='Displayed separately', value=f'{before.hoist} → **{after.hoist}**')
            if before.mentionable != after.mentionable: embed.add_field(name='Mentionable', value=f'{before.mentionable} → **{after.mentionable}**')
            #Here marks the grave of the huge emoji dict. Deleted because it would be visually unappealing. Recover from Github commit history if desired.
            if before.permissions != after.permissions:
                afterPermissions = list(iter(after.permissions))
                changedPermissions = [] #I have no clue what this is for... flag for deletion
                for i, p in enumerate(iter(before.permissions)):
                    k, v = p[0], p[1]
                    if v != afterPermissions[i][1]:
                        changedPermissions.append((k, v))
                        embed.add_field(name=permissionKeys[k], value=f'{v} → **{afterPermissions[i][1]}**')
            if len(embed.fields) > 0 or before.name != after.name:
                content += embedToPlaintext(embed)
                message = await logChannel(after.guild, 'role').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
                for reac in reactions: await message.add_reaction(reac)
                embed = self.PermissionChanges(after.members, message, embed)
                if settings['embedTimestamp'] > 1: embed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(after.guild)}"
                if any((settings['tts'], settings['flashText'])) and not settings['plainText']: await message.edit(content=None)
                if not settings['plainText']: await message.edit(embed=embed)
                if before.permissions != after.permissions:
                    for m in after.members: self.memberPermissions[after.guild.id][m.id] = m.guild_permissions
        await self.CheckDisguardServerRoles(after.guild.members, mode=0, reason='Server role was updated; member\'s permissions changed')
        if before.name != after.name: asyncio.create_task(database.VerifyServer(after.guild, bot))
        for member in after.members:
            await database.VerifyUser(member, bot)
        if message and len(embed.fields) > 0 or before.name != after.name:
            final = copy.deepcopy(embed)
            while True:
                def reactionCheck(r, u): return r.message.id == message.id and not u.bot
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if str(result[0]) == 'ℹ':
                    await message.clear_reactions()
                    if 'Loading role information' not in embed.description: embed.description+=f'\n\n{self.loading}Loading role information'
                    await message.edit(embed=embed)
                    logs = None
                    try: logs = await after.audit_logs(limit=None).flatten()
                    except: pass
                    new = await self.RoleInfo(after, logs)
                    if embed.author.name: new.set_author(icon_url=url, name=log.user.name)
                    await message.edit(embed=new)
                    await message.add_reaction('⬅')
                    def backCheck(r, u): return str(r) == '⬅' and r.message.id == message.id and u.id == result[1].id
                    try: await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                    except asyncio.TimeoutError: pass
                    await message.edit(content=content, embed=final)
                    await message.clear_reactions()
                elif str(result[0]) == '🔀':
                    await message.remove_reaction(result[0], result[1])
                    setAt = 0 #field index
                    clearAt = 1
                    toSet = before
                    toClear = after
                    embed.color = before.color
                    if '🔀' in embed.fields[1].value: #new color value
                        setAt = 1
                        clearAt = 0
                        toSet = after
                        toClear = before
                        embed.color = after.color
                    embed.set_field_at(setAt, name=embed.fields[setAt].name, value=f'**RGB{toSet.color.to_rgb()}\nHex: {toSet.color}\nDisplayed on embed border**')
                    embed.set_field_at(clearAt, name=embed.fields[clearAt].name, value=f'RGB{toClear.color.to_rgb()}\nHex: {toClear.color}\nReact 🔀 to display')
                    await message.edit(embed=embed)
                elif result[0].emoji == self.emojis['collapse'] and len(message.embeds) > 0:
                    await message.edit(content=content, embed=None)
                    await message.clear_reactions()
                elif settings['plainText'] and len(message.embeds) < 1:
                    await message.edit(content=None, embed=embed)
                    await message.clear_reactions()
                    reactions.append(self.emojis['collapse'])
    
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        '''[DISCORD API METHOD] Called when emoji list is updated (creation, update, deletion)'''
        rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(guild.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        msg = None
        if logEnabled(guild, 'emoji'):
            content = 'Server emoji list updated'
            f = None
            settings = getCyberAttributes(guild, 'emoji')
            color = green[colorTheme(guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            embed = discord.Embed(
                title=f'''{(f'{self.emojis["emojiCreate"]}' if settings['library'] == 2 else f"{self.emojis['emoji']}{self.emojis['greenPlus']}" if settings['library'] == 1 else f"{self.emojis['minion']}{self.emojis['greenPlus']}") if settings['context'][0] > 0 else ""}{'Emoji created' if settings['context'][0] < 2 else ''}''',
                description = '',
                color=color)
            if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
            logType = discord.AuditLogAction.emoji_create
            if len(before) > len(after): #Emoji was deleted
                embed.title = f'''{(f'{self.emojis["emojiDelete"]}' if settings['library'] == 2 else f"{self.emojis['emoji']}{self.emojis['delete']}" if settings['library'] == 1 else f"{self.emojis['minion']}{self.emojis['delete']}") if settings['context'][0] > 0 else ""}{'Emoji deleted' if settings['context'][0] < 2 else ''}'''
                embed.color = red[colorTheme(guild)] if settings['color'][2] == 'auto' else settings['color'][2]
                logType = discord.AuditLogAction.emoji_delete
            elif len(after) == len(before):
                embed.title = f'''{(f'{self.emojis["emojiUpdate"]}' if settings['library'] == 2 else f"{self.emojis['emoji']}✏" if settings['library'] == 1 else f"{self.emojis['minion']}✏") if settings['context'][0] > 0 else ""}{'Emoji list updated' if settings['context'][0] < 2 else ''}'''
                embed.color = blue[colorTheme(guild)] if settings['color'][1] == 'auto' else settings['color'][1]
                logType = discord.AuditLogAction.emoji_update
            #utilize dictionaries for speed purposes, to prevent necessity of nested loops
            beforeDict = {}
            afterDict = {}
            footerIDList = []
            for emoji in before: beforeDict.update({emoji.id: {'name': emoji.name, 'url': emoji.url, 'raw': str(emoji)}})
            for emoji in after: afterDict.update({emoji.id: {'name': emoji.name, 'url': emoji.url, 'raw': str(emoji)}})
            for eID, emoji in beforeDict.items():
                if eID not in afterDict: #emoji deleted
                    embed.add_field(name=f'{self.emojis["delete"]}{emoji["name"]}', value=f'{emoji["raw"]} • [View image]({emoji["url"]})')
                    if embed.image.url is embed.Empty and settings['thumbnail'] in (1, 2, 4): embed.set_image(url=emoji['url'])
                    footerIDList.append(eID)
            for eID, emoji in afterDict.items():
                if eID not in beforeDict: #emoji created
                    embed.add_field(name=f'{self.emojis["greenPlus"]}{emoji["name"]}', value=f'{emoji["raw"]} • [View image]({emoji["url"]})')
                    if embed.image.url is embed.Empty and settings['thumbnail'] in (1, 2, 4): embed.set_image(url=emoji['url'])
                    footerIDList.append(eID)
                elif eID in beforeDict and beforeDict[eID]['name'] != emoji['name']: #name updated
                    embed.add_field(name=f'{beforeDict[eID]["name"]} → **{emoji["name"]}**', value=emoji['raw'])
                    if embed.image.url is embed.Empty and settings['thumbnail'] in (1, 2, 4): embed.set_image(url=emoji['url'])
                    footerIDList.append(eID)
            content += embedToPlaintext(embed)
            if readPerms(guild, "emoji"):
                try:
                    log = (await guild.audit_logs(limit=1, action=logType).flatten())[0]
                    if settings['botLogging'] == 0 and log.user.bot: return
                    elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                    embed.description += f'''\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Updated by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.name}){f"{newline}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}'''
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and embed.thumbnail.url == discord.Embed.Empty)) or (settings['author'] > 2 and (settings['author'] == 2 and embed.author.name == discord.Embed.Empty)):
                        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                        try: await log.user.avatar_url_as(size=1024).save(savePath)
                        except discord.HTTPException: pass
                        f = discord.File(savePath)
                        url = await self.uploadFiles(f)
                        content = f'{log.user} updated the server emoji list'
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and embed.thumbnail.url == discord.Embed.Empty): embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and embed.author.name == discord.Embed.Empty): embed.set_author(name=log.user.name, icon_url=url)
                    await updateLastActive(log.user, datetime.datetime.now(), 'updated emojis somewhere')
                except Exception as e: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            embed.set_footer(text=f'Relevant emoji IDs: {" • ".join(str(f) for f in footerIDList)}' if len(footerIDList) > 1 else f'Emoji ID: {footerIDList[0]}')
            if settings['embedTimestamp'] > 1: embed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(after.guild)}"
            if msg and len(embed.fields) > 0:
                msg = await logChannel(guild, 'emoji').send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
                if any((settings['plainText'], settings['flashText'])) and not settings['plainText']: await msg.edit(content=None)
                def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
                while True:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                    if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                        await msg.edit(content=content, embed=None)
                        await msg.clear_reactions()
                        if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                    elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                        await msg.edit(content=None, embed=embed)
                        await msg.clear_reactions()
                        if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        '''[DISCORD API METHOD] Called whenever a voice channel event is triggered - join/leave, mute/deafen, etc'''
        rawReceived = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(member.guild.id).get('offset'))
        received = rawReceived.strftime('%b %d, %Y • %I:%M:%S %p')
        msg = None
        if not logEnabled(member.guild, 'voice'):
            return
        settings = getCyberAttributes(member.guild, 'voice')
        theme = colorTheme(member.guild)
        color = blue[theme] if settings['color'][1] == 'auto' else settings['color'][1]
        embed=discord.Embed(
            title = f"{(self.emojis['voiceChannel'] if settings['library'] > 0 else '🎙') if settings['context'][0] > 0 else ''}{'Voice Channel Update' if settings['context'][0] < 2 else ''}",
            description=f"{(self.emojis['member'] if settings['library'] > 0 else '👤') if settings['context'][1] > 0 else ''}{'Member' if settings['context'][1] < 2 else ''}: {member.mention} ({member.name})\n",
            color=color)
        if settings['embedTimestamp'] in (1, 3): embed.timestamp = datetime.datetime.utcnow()
        content = None
        error = False
        f = []
        log = None
        if before.channel: beforePrivate = before.channel.overwrites_for(member.guild.default_role).read_messages == False
        if after.channel: afterPrivate = after.channel.overwrites_for(member.guild.default_role).read_messages == False
        onlyModActions = self.bot.lightningLogging[member.guild.id]['cyberlog']['onlyVCForceActions']
        onlyJoinLeave = self.bot.lightningLogging[member.guild.id]['cyberlog']['onlyVCJoinLeave'] #Make sure to do a full server verification every day to make sure this key exists
        logRecapsEnabled = self.bot.lightningLogging[member.guild.id]['cyberlog']['voiceChatLogRecaps']
        try: eventHistory = self.memberVoiceLogs[member.id]
        except KeyError:
            eventHistory = []
            self.memberVoiceLogs[member.id] = eventHistory
            eventHistory = self.memberVoiceLogs[member.id]
        if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
            savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not member.is_avatar_animated() else 'gif'))
            try: await member.avatar_url_as(size=1024).save(savePath)
            except discord.HTTPException: pass
            f = discord.File(savePath)
            url = await self.uploadFiles(f)
            if settings['thumbnail'] in (1, 2, 4) and embed.thumbnail.url == discord.Embed.Empty: embed.set_thumbnail(url=url)
            if settings['author'] in (1, 2, 4) and embed.author.name == discord.Embed.Empty: embed.set_author(name=member.name, icon_url=url)
        #Use an if/else structure for AFK/Not AFK because AFK involves switching channels - this prevents duplicates of AFK & Channel Switch logs
        if before.afk != after.afk:
            #Note these *extremly* long value lines due to the multitude of customization options between emoji choice, emoji/plaintext descriptions, and color schemes
            # lines = (
            #     f"{((self.emojis['neonGreenConnect'] if theme == 1 else self.emojis['darkGreenConnect']) if settings['library'] > 0 else '📤') if settings['context'] > 0 else ''}{'Left' if settings['context'] < 2 else ''}: {(self.channelEmoji(before.channel) if settings['library'] > 0 else '🎙') if settings['context'] > 0 else ''}{before.channel}",
            #     f"{((self.emojis['neonRedDisconnect'] if theme == 1 else self.emojis['darkRedDisconnect']) if settings['library'] > 0 else '📥') if settings['context'] > 0 else ''}{'Joined' if settings['context'] < 2 else ''}: {(self.channelEmoji(after.channel) if settings['library'] > 0 else '🎙') if settings['context'] > 0 else ''}{after.channel}"
            # )
            lines = (
                f"{(self.emojis['darkGreenConnect'] if settings['library'] > 0 else '📤') if settings['context'][1] > 0 else ''}{'Left' if settings['context'][1] < 2 else ''}: {(self.channelEmoji(before.channel) if settings['library'] > 0 else '🎙') if settings['context'][1] > 0 else ''}{before.channel}",
                f"{(self.emojis['darkRedDisconnect'] if settings['library'] > 0 else '📥') if settings['context'][1] > 0 else ''}{'Joined' if settings['context'][1] < 2 else ''}: {(self.channelEmoji(after.channel) if settings['library'] > 0 else '🎙') if settings['context'][1] > 0 else ''}{after.channel}"
            )
            if after.afk: 
                content = f'{member} went AFK from {before.channel}'
                eventHistory.append((rawReceived, f"{(self.emojis['idle'] if settings['library'] > 0 else '😴') if settings['context'][1] > 0 else ''}Went AFK"))
                embed.add_field(name=f"{(self.emojis['idle'] if settings['library'] > 0 else '😴') if settings['context'][1] > 0 else ''}Went AFK", value=f"{lines[0]}\n{lines[1]}")
            else: 
                content = f'{member} rejoined {after.channel} & is no longer AFK'
                eventHistory.append((rawReceived, f"{(self.emojis['online'] if settings['library'] > 0 else '🚫😴') if settings['context'][1] > 0 else ''}Returned from AFK"))
                embed.add_field(name=f"{(self.emojis['online'] if settings['library'] > 0 else '🚫😴') if settings['context'][1] > 0 else ''}Returned from AFK", value=f"{lines[0]}\n{lines[1]}")
        else:
            #method that calculates how long a member was muted or deafened for
            def sanctionedFor(mode):
                '''Returns a timespan string in standard Disguard format (x seconds or y minutes, etc) representing how long a member was muted or deafened, passed via the mode arg'''
                i = len(eventHistory) - 1
                e = eventHistory[-1]
                #while loop will iterate through eventHistory in reverse order until it either hits the beginning or finds the most recent mute/deafen
                while i > 0:
                    e = eventHistory[i]
                    if mode == 'mute' and 'Muted themselves' in e[1]: break
                    elif mode == 'modMute' and 'Muted by' in e[1]: break
                    elif mode == 'deafen' and 'Deafened themselves' in e[1]: break
                    elif mode == 'modDeafen' and 'Deafened by' in e[1]: break
                    else: i -= 1
                #If we hit the end without finding a match, then the member probably unmuted before joining the voice channel, which the API doesn't do anything with until they join
                if i > 0:
                    return elapsedDuration(rawReceived - e[0])
                else: return f'Special case: Member is on browser & had to accept microphone permissions or member toggled {mode} while outside of voice channel'
            #Member switched force-deafen or force-mute status - master if branch is for space-saving purposes when handing audit log retrieval
            if (before.deaf != after.deaf) or (before.mute != after.mute):
                #Audit log retrieval - check if audit log reading is enabled (remember that this is a change since I discovered the audit log supports voice moderations)
                if readPerms(member.guild, 'voice'):
                    try:
                        #Fetch the most recent audit log
                        log = (await member.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update).flatten())[0]
                        #Return or adjust settings if the server has special settings for actions performed by bots
                        if settings['botLogging'] == 0 and log.user.bot: return
                        elif settings['botLogging'] == 1 and log.user.bot: settings['plainText'] = True
                        #Retrieve the additional attributes necessary to verify this audit log entry applies to a mute/deafen
                        i = iter(log.before)
                        #Check to make sure that if the audit log represents a mute, our event is a mute, and same for deafen
                        if ('mute' in i and before.mute != after.mute) or ('deafen' in i and before.deaf != after.deaf):
                            #See message edit for documentation on this segment
                            if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and embed.thumbnail.url == discord.Embed.Empty)) or (settings['author'] > 2 and (settings['author'] == 2 and embed.author.name == discord.Embed.Empty)):
                                savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not log.user.is_avatar_animated() else 'gif'))
                                try: await log.user.avatar_url_as(size=1024).save(savePath)
                                except discord.HTTPException: pass
                                f = discord.File(savePath)
                                url = await self.uploadFiles(f)
                                if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and embed.thumbnail.url == discord.Embed.Empty): embed.set_thumbnail(url=url)
                                if settings['author'] > 2 or (settings['author'] == 2 and embed.author.name == discord.Embed.Empty): embed.set_author(name=log.user.name, icon_url=url)
                            await updateLastActive(log.user, datetime.datetime.now(), 'moderated a user in voice chat')
                    except Exception as e: error = f'You have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            #The 'onlyJoinLeave' and 'onlyModActions' moved inwards to allow the event history log to always be added to - this will be the new server default setting.
            if before.mute != after.mute:
                #Member is no longer force muted
                if before.mute:
                    content = f'{log.user if log else "[Moderator]"} unmuted {member}'
                    eventHistory.append((rawReceived, f'''{(f"👮‍♂️{self.emojis['unmuted']}" if settings['library'] > 0 else '🎙🔨🗣') if settings['context'][1] > 0 else ''}Unmuted by {log.user if log else '[a moderator]'}'''))
                    if not onlyJoinLeave:
                        embed.add_field(
                            name=f'''{(f"👮‍♂️{self.emojis['unmuted']}" if settings['library'] > 0 else '🎙🔨🗣') if settings['context'][1] > 0 else ''}Unmuted by moderator''',
                            value=f'''{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Moderator' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.name})\n(Was muted for {sanctionedFor("modMute")})''')
                #Member became force muted
                else:
                    content = f'{log.user if log else "[Moderator]"} muted {member}'
                    eventHistory.append((rawReceived, f'''{(self.emojis['modMuted'] if settings['library'] > 0 else '🎙🔨🤐') if settings['context'][1] > 0 else ''}Muted by {log.user if log else '[a moderator]'}'''))
                    if not onlyJoinLeave:
                        embed.add_field(
                            name=f'''{(self.emojis['modMuted'] if settings['library'] > 0 else '🎙🔨🤐') if settings['context'][1] > 0 else ''}Muted by moderator''',
                            value=f'''{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Moderator' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.name})''')
                    if before.deaf != after.deaf:
                    #If member was previously deafened, then they are no longer deafened
                        if before.deaf:
                            content = f'{log.user if log else "[Moderator]"} undeafened {member}'
                            eventHistory.append((rawReceived, f'''{(f"👮‍♂️{self.emojis['undeafened']}" if settings['library'] > 0 else '🔨🔊') if settings['context'][1] > 0 else ''}Undeafened by {log.user if log else '[a moderator]'}'''))
                            embed.add_field(
                                name=f'''{(f"👮‍♂️{self.emojis['undeafened']}" if settings['library'] > 0 else '🔨🔊') if settings['context'][1] > 0 else ''}Undeafened by moderator''',
                                value=f'''{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Moderator' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.name})\n(Was deafened for {sanctionedFor("modMute")})''')
                        #Otherwise, a moderator deafened them just now
                        else:
                            content = f'{log.user if log else "[Moderator]"} deafened {member}'
                            eventHistory.append((rawReceived, f'''{(self.emojis['modDeafened'] if settings['library'] > 0 else '🔨🔇') if settings['context'][1] > 0 else ''}Deafened by {log.user if log else '[a moderator]'}'''))
                            embed.add_field(
                                name=f'''{(self.emojis['modDeafened'] if settings['library'] > 0 else '🔨🔇') if settings['context'][1] > 0 else ''}Deafened by moderator''',
                                value=f'''{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Moderator' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.name})''')
            await updateLastActive(member, datetime.datetime.now(), 'voice channel activity')
            #Member changed self-deafen status
            if before.self_deaf != after.self_deaf:
                if before.self_deaf:
                    content = f'{member} undeafened themselves'
                    eventHistory.append((rawReceived, f"{(self.emojis['undeafened'] if settings['library'] > 0 else '🔊') if settings['context'][1] > 0 else ''}Undeafened themselves"))
                    if not onlyModActions and not onlyJoinLeave:
                        embed.add_field(name=f"{(self.emojis['undeafened'] if settings['library'] > 0 else '🔊') if settings['context'][1] > 0 else ''}Undeafened",value=f'(Was deafened for {sanctionedFor("deafen")})')
                else:
                    content = f'{member} deafened themselves'
                    eventHistory.append((rawReceived, f"{(self.emojis['deafened'] if settings['library'] > 0 else '🔇') if settings['context'][1] > 0 else ''}Deafened themselves"))
                    if not onlyModActions and not onlyJoinLeave:
                        embed.add_field(name=f"{(self.emojis['deafened'] if settings['library'] > 0 else '🔇') if settings['context'][1] > 0 else ''}Deafened",value='_ _')
            if before.self_mute != after.self_mute:
                if before.self_mute:
                    content = f'{member} unmuted themselves'
                    eventHistory.append((rawReceived, f"{(self.emojis['unmuted'] if settings['library'] > 0 else '🎙🗣') if settings['context'][1] > 0 else ''}Unmuted themselves"))
                    if not onlyModActions and not onlyJoinLeave:
                        embed.add_field(name=f"{(self.emojis['unmuted'] if settings['library'] > 0 else '🎙🗣') if settings['context'][1] > 0 else ''}Unmuted",value=f'(Was muted for {sanctionedFor("mute")})')
                else:
                    content = f'{member} muted themselves'
                    eventHistory.append((rawReceived, f"{(self.emojis['deafened'] if settings['library'] > 0 else '🔇') if settings['context'][1] > 0 else ''}Deafened themselves"))
                    if not onlyModActions and not onlyJoinLeave:
                        embed.add_field(name=f"{(self.emojis['deafened'] if settings['library'] > 0 else '🔇') if settings['context'][1] > 0 else ''}Deafened",value='_ _')
            if before.channel != after.channel:
                if not before.channel:
                    content = f'{member} connected to voice chat in {after.channel.name}'
                    #self.memberVoiceLogs.update({member.id: []}) #When the member joins a channel, we clear their history log from before, if it exists, to start a new one
                    eventHistory = []
                    self.memberVoiceLogs[member.id] = eventHistory
                    eventHistory = self.memberVoiceLogs[member.id]
                    #eventHistory.append((rawReceived, f"{((self.emojis['neonGreenConnect'] if theme == 1 else self.emojis['darkGreenConnect']) if settings['library'] > 0 else '📥') if settings['context'] > 0 else ''}Connected to {(self.emojis['privateVoiceChannel'] if afterPrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{after.channel}"))
                    eventHistory.append((rawReceived, f"{(self.emojis['darkGreenConnect'] if settings['library'] > 0 else '📥') if settings['context'][1] > 0 else ''}Connected to {(self.emojis['privateVoiceChannel'] if afterPrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{after.channel}"))
                    if not onlyModActions:
                        #embed.add_field(name=f"{((self.emojis['neonGreenConnect'] if theme == 1 else self.emojis['darkGreenConnect']) if settings['library'] > 0 else '📥') if settings['context'] > 0 else ''}Connected", value=f"To {(self.emojis['privateVoiceChannel'] if afterPrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{after.channel}")
                        embed.add_field(name=f"{((self.emojis['neonGreenConnect'] if theme == 1 else self.emojis['darkGreenConnect']) if settings['library'] > 0 else '📥') if settings['context'][1] > 0 else ''}Connected", value=f"To {(self.emojis['privateVoiceChannel'] if afterPrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{after.channel}")
                elif not after.channel:
                    content = f'{member} disconnected from {before.channel.name}'
                    #eventHistory.append((rawReceived, f"{((self.emojis['neonRedDisconnect'] if theme == 1 else self.emojis['darkRedDisconnect']) if settings['library'] > 0 else '📤') if settings['context'] > 0 else ''}Disconnected from {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel}"))
                    eventHistory.append((rawReceived, f"{(self.emojis['darkRedDisconnect'] if settings['library'] > 0 else '📤') if settings['context'][1] > 0 else ''}Disconnected from {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel}"))
                    if not onlyModActions:
                        #embed.add_field(name=f"{((self.emojis['neonRedDisconnect'] if theme == 1 else self.emojis['darkRedDisconnect']) if settings['library'] > 0 else '📤') if settings['context'] > 0 else ''}Disconnected", value=f"From {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel}")
                        embed.add_field(name=f"{(self.emojis['darkRedDisconnect'] if settings['library'] > 0 else '📤') if settings['context'][1] > 0 else ''}Disconnected", value=f"From {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel}")
                else:
                    content = f'{member} switched from {before.channel.name} to {after.channel.name}'
                    eventHistory.append((rawReceived, f"{(self.emojis['shuffle'] if settings['library'] > 0 else '🔀') if settings['context'][1] > 0 else ''}Switched from {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel} to {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{after.channel}"))
                    if not onlyModActions:
                        embed.add_field(name=f"{(self.emojis['shuffle'] if settings['library'] > 0 else '🔀') if settings['context'][1] > 0 else ''}Switched voice channels", value=f"{(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel} → {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}**{after.channel}**")
        if len(embed.fields) < 1: return
        #Method to build voice channel history embed
        def buildHistoryLog(eventHistory):
            logEmbed = discord.Embed(title='Member Voice Log Recap • ', description='', color=color)
            maxNumberOfEntries = 30 #Max number of log entries to display in the embed
            start, end = eventHistory[0 if len(eventHistory) < 30 else eventHistory[-1 * maxNumberOfEntries]], eventHistory[-1]
            #Set embed title based on the distance span between the start and end of voice log history
            if start[0].day == end[0].day: logEmbed.title += f'{start[0]:%I:%M %p} - {end[0]:%I:%M %p}' #Member began & ended voice session on the same day, so least amount of contextual date information
            elif (end[0] - start[0]).days < 1: logEmbed.title += f'{start[0]:%I:%M %p} yesterday - {end[0]:%I:%M %p} today' #Member began & ended voice session one day apart - so use yesterday & today
            else: logEmbed.title += f'{start[0]:%I:%M %p %b %d}  - {end[0]:%I:%M %p} today' #More than one day apart
            if len(eventHistory) > 30: logEmbed.title += f'(Last {maxNumberOfEntries} entries)'
            #Join the formatted log, last [maxNumberOfEntries] entries
            for e in eventHistory[-1 * maxNumberOfEntries:]:
                logEmbed.description += f'[{e[0]:%b %d %I:%M:%S %p}] {e[1]}\n'
            logEmbed.add_field(name='Voice Session Duration', value=elapsedDuration(eventHistory[-1][0] - eventHistory[0][0]))
            logFile = discord.File(savePath)
            logEmbed.set_author(name=member, icon_url=f'attachment://{logFile.filename}')
            eventHistory = []
            return logEmbed, logFile
        if settings['embedTimestamp'] > 1: embed.description += f"\n{(clockEmoji(rawReceived) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {received} {nameZone(member.guild.guild)}"
        lc = logChannel(member.guild, 'voice')
        if error: content += f'\n\n{error}'
        msg = await lc.send(content = content if any((settings['plainText'], settings['flashText'], settings['tts'])) or error else None, embed=embed if not settings['plainText'] else None, tts=settings['tts'])
        if any((settings['plainText'], settings['flashText'])) and not settings['plainText'] and not error: await msg.edit(content=None)
        if not after.channel and logRecapsEnabled:
            resultEmbed, fle = buildHistoryLog(eventHistory)
            await lc.send(embed=resultEmbed, file=fle)
        if msg:
            def reactionCheck(r, u): return r.message.id == msg.id and not u.bot
            while True:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck)
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']: await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']: await msg.add_reaction(self.emojis['collapse'])

    '''The following listener methods are used for lastActive tracking; not logging right now'''
    # As of update 0.2.25, on_raw_reaction_add and on_raw_reaction_remove are in use, at the top, for ghost reaction logging, the latter of which used to be here.

    @commands.Cog.listener()
    async def on_typing(self, c, u, w):
        await updateLastActive(u, datetime.datetime.now(), 'started typing somewhere')

    @commands.Cog.listener()
    async def on_webhooks_update(self, c):
        await asyncio.sleep(5)
        await updateLastActive((await c.guild.audit_logs(limit=1).flatten())[0].user, datetime.datetime.now(), 'updated webhooks')

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        encounter = datetime.datetime.now()
        if isinstance(error, commands.CommandNotFound): return
        embed = None
        alert = self.emojis['alert']
        #traceback.print_exception(type(error), error, error.__traceback__)
        m = await ctx.send(f'{alert} {error}')
        filename = datetime.datetime.now().strftime('%m%d%Y%H%M%S%f')
        p = f'{tempDir}/Tracebacks/{filename}.txt'
        try: os.makedirs(f'{tempDir}/Tracebacks')
        except FileExistsError: pass
        with codecs.open(p, 'w+', encoding='utf-8-sig') as f:
            f.write(''.join(traceback.format_exception(type(error), error, error.__traceback__)))
        while True:
            await m.add_reaction(self.emojis['information'])
            def optionsCheck(r, u): return r.emoji == self.emojis['information'] and u.id == ctx.author.id and r.message.id == m.id
            await self.bot.wait_for('reaction_add', check=optionsCheck)
            try: await m.clear_reactions()
            except: pass
            await m.edit(content=self.loading)
            if not embed:
                embed=discord.Embed(
                    title=f'{alert} An error has occured {alert}',
                    description=f"{error}\n\n{self.emojis['collapse']}: Collapse information\n{self.emojis['disguard']}: Forward this embed to my official server for my developer to view\n🎟: Open a support ticket with my developer\n\nSystem: Traceback is saved to {os.path.abspath(p)}",
                    timestamp=datetime.datetime.utcnow(),
                    color=red[colorTheme(ctx.guild)])
                embed.add_field(name='Command',value=f'{ctx.prefix}{ctx.command}')
                embed.add_field(name='Server',value=f'{ctx.guild.name}\n{ctx.guild.id}' if ctx.guild else 'N/A')
                embed.add_field(name='Channel',value=f'{self.channelEmoji(ctx.channel)}{ctx.channel.name}\n{ctx.channel.id}')
                embed.add_field(name='Author',value=f'{ctx.author.name}\n{ctx.author.id}')
                embed.add_field(name='Message',value=f'{ctx.message.content}\n{ctx.message.id}')
                embed.add_field(name='Occurence',value=encounter.strftime('%b %d, %Y • %I:%M %p EST'))
            await m.edit(content=None, embed=embed)
            reactions = [self.emojis['collapse'], self.emojis["disguard"], '🎟']
            for r in reactions: await m.add_reaction(r)
            def navigCheck(r,u): return r.emoji in reactions and u.id == ctx.author.id and r.message.id == m.id
            r = await self.bot.wait_for('reaction_add', check=navigCheck)
            if r[0].emoji == self.emojis['disguard']:
                errorChannel = bot.get_channel(620787092582170664)
                if os.path.exists(p): f = discord.File(p)
                else: f = None
                log = await errorChannel.send(embed=embed, file=f)
                await m.edit(content=f'A copy of this embed has been sent to my official server ({errorChannel.mention}). You may retract the error message from there at any time by reacting with {self.emojis["modDelete"]}. You may still quickly open a support ticket with 🎟, or you may use the command ({prefix(ctx.guild) if ctx.guild else "."}ticket)')
                reactions = [self.emojis['modDelete'], '🎟']
                while True:
                    for r in reactions: await m.add_reaction(r)
                    r = await bot.wait_for('reaction_add', check=navigCheck)
                    try: await m.remove_reaction(r[0], r[1])
                    except: pass
                    if r[0].emoji == self.emojis['modDelete']:
                        await m.edit(content=self.loading)
                        await log.delete()
                        break
                    else:
                        pass
            try: await m.clear_reactions()
            except: pass
            await m.edit(content=f'{alert} {error}', embed=None)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command()
    async def pause(self, ctx, *args):
        '''Pause logging or antispam for a duration'''
        status = await ctx.send(str(self.loading) + "Please wait...")
        status = await ctx.send(f'{self.emojis["loading"]}Pausing...')
        args = [a.lower() for a in args]
        defaultChannel = self.bot.get_channel(self.bot.lightningLogging[ctx.guild.id]['cyberlog']['defaultChannel'])
        if not defaultChannel:
            defaultChannel = self.bot.get_channel(self.bot.lightningLogging[ctx.guild.id]['antispam']['log'][1])
            if not defaultChannel:
                defaultChannel = ctx.channel
        if 'logging' in args:
            if 'logging' != args[0]:
                return
            key = 'cyberlog'
        if 'antispam' in args:
            if 'antispam' != args[0]:
                return
            key = 'antispam'
        duration = datetime.timedelta(seconds = self.ParsePauseDuration((' ').join(args[1:])))
        if duration > 0: 
            rawUntil = datetime.datetime.utcnow() + duration
            until = rawUntil + timeZone(ctx.guild)
        else: 
            rawUntil = datetime.datetime.max
            until = datetime.datetime.max
        embed = discord.Embed(
            title=f'The {args[0][0].upper()}{args[0][1:]} module was paused',
            description=f'''
                👮‍♂️Moderator: {ctx.author.mention} ({ctx.author.name})
                {clockEmoji(until)}Paused at: {until:%b %d, %Y • %I:%M %p}
                ⏰Paused until: {'Manually resumed' if duration == 0 else f"{until:%b %d, %Y • %I:%M %p} {nameZone(ctx.guild)}"}
                ''',
            color=yellow[colorTheme(ctx.guild)])
        embed.set_footer(text='Resuming at: ')
        embed.timestamp = rawUntil
        savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), 'png' if not ctx.author.is_avatar_animated() else 'gif'))
        try: await ctx.author.avatar_url_as(size=1024).save(savePath)
        except discord.HTTPException: pass
        f = discord.File(savePath)
        embed.set_thumbnail(url=f'attachment://{f.filename}')
        embed.set_author(name=ctx.author.name, icon_url=f'attachment://{f.filename}')
        await status.edit(content=None, embed=embed, file=f)
        await database.PauseMod(ctx.guild, key)
        self.bot.lightningLogging[ctx.guild.id][key]['enabled'] = False
        pauseTimedEvent = {'type': 'pause', 'target': key, 'server': ctx.guild.id}
        if len(args) == 1: return #If the duration is infinite, we don't wait
        await database.AppendTimedEvent(ctx.guild, pauseTimedEvent)
        await asyncio.sleep(duration)
        await database.ResumeMod(ctx.guild, key)
        self.bot.lightningLogging[ctx.guild.id][key]['enabled'] = True
        embed.title = f'The {args[0][0].upper()}{args[0][1:]} module has resumed'
        embed.description = ''
        await status.edit(embed=embed)
        
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
        embed=discord.Embed(color=yellow[colorTheme(ctx.guild)])
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
            embed=discord.Embed(color=yellow[colorTheme(ctx.guild)])
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
        main=discord.Embed(title='Info results viewer', color=yellow[colorTheme(ctx.guild)], timestamp=datetime.datetime.utcnow())
        embeds=[]
        PartialEmojiConverter = commands.PartialEmojiConverter()
        if len(arg) > 0:
            members, roles, channels, emojis = tuple(await asyncio.gather(*[self.FindMembers(ctx.guild, arg), self.FindRoles(ctx.guild, arg), self.FindChannels(ctx.guild, arg), self.FindEmojis(ctx.guild, arg)]))
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
            author = sorted((await ctx.channel.history(limit=100).filter(pred).flatten()), key = lambda m: m.created_at, reverse=True)[-1].author
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
            return await self.bot.get_cog('Birthdays').birthday(ctx, str(ctx.author.id))
        if len(embeds) > 1 or indiv is not None: 
            await message.edit(content='{}Still working'.format(self.loading),embed=indiv)
        members, roles, channels, inv, emojis = tuple(await asyncio.gather(*[self.FindMoreMembers(ctx.guild.members, arg), self.FindMoreRoles(ctx.guild, arg), self.FindMoreChannels(ctx.guild, arg), self.FindMoreInvites(ctx.guild, arg), self.FindMoreEmojis(ctx.guild, arg)]))
        counter = 0
        while counter < 2:
            #print(counter, logs)
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
                mainKeys.append('ℹInformation about you :)')
                indiv = await asyncio.create_task(self.MemberInfo(ctx.author, calculatePosts=False))
            if 'me' == arg:
                mainKeys.append('ℹInformation about you :)')
                indiv = await self.MemberInfo(ctx.author)
            if any(s == arg for s in ['him', 'her', 'them', 'it']):
                author = sorted((await ctx.channel.history(limit=100).filter(pred).flatten()), key = lambda m: m.created_at, reverse=True)[-1].author
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
            if 'server' in arg or 'guild' in arg or arg in ctx.guild.name.lower() or ctx.guild.name.lower() in arg: every.append(InfoResult((await self.ServerInfo(ctx.guild, logs, bans, webhooks, invites)), 'ℹServer information', compareMatch('server', arg)))
            if 'roles' in arg: every.append(InfoResult((await self.RoleListInfo(ctx.guild.roles, logs)), 'ℹRole list information', compareMatch('roles', arg)))
            if any(s in arg for s in ['members', 'people', 'users', 'bots', 'humans']): every.append(InfoResult((await self.MemberListInfo(ctx.guild.members)), 'ℹMember list information', compareMatch('members', arg)))
            if 'channels' in arg: every.append(InfoResult((await self.ChannelListInfo(ctx.guild.channels, logs)), 'ℹChannel list information', compareMatch('channels', arg)))
            if 'emoji' in arg or 'emotes' in arg: every.append(InfoResult((await self.EmojiListInfo(ctx.guild.emojis, logs)), 'ℹEmoji information', compareMatch('emoji', arg)))
            if 'invites' in arg: every.append(InfoResult((await self.InvitesListInfo(invites, logs, ctx.guild)), 'ℹInvites information', compareMatch('invites', arg)))
            if 'bans' in arg: every.append(InfoResult((await self.BansListInfo(bans, logs, ctx.guild)), 'ℹBans information', compareMatch('bans', arg)))
            if any(s in arg for s in ['dev', 'owner', 'master', 'creator', 'author', 'disguard', 'bot', 'you']): every.append(InfoResult((await self.BotInfo(await bot.application_info(), ctx.guild)), '{}Information about me'.format(bot.get_emoji(569191704523964437)), compareMatch('disguard', arg)))
            every.sort(key=lambda x: x.relevance, reverse=True)
            md = 'Viewing {} - {} of {} results for *{}*{}\n**Type the number of the option to view**\n'
            md2=[]
            used = md.format(1 if len(every) >= 1 else 0, 20 if len(every) >= 20 else len(every), len(every), arg, ' (Arrows to scroll)' if len(every) >= 20 else '')
            main.description=used
            for result in range(len(every)): md2.append('\n{}: {}'.format(result + 1, every[result].mainKey))
            main.description+=''.join(md2[:20])
            main.set_author(name='{}: {}'.format(ctx.author.name, ctx.author.id),icon_url=ctx.author.avatar_url)
            if len(main.description) > 2048: main.description = main.description[:2048]
            if len(every) == 0 and indiv is None: return await message.edit(embed=main)
            elif len(every) == 1: 
                if counter == 0 and type(every[0].obj) is not discord.Member:
                    temp = await self.evalInfo(every[0].obj, ctx.guild, logs)
                    temp.set_author(name='⭐{}% relevant ({})'.format(every[0].relevance, every[0].mainKey))
                    await message.edit(embed=temp)
            elif len(reactions) == 0: await message.edit(embed=main)
            if len(embeds) > 1 or indiv is not None: 
                #pass
                #await asyncio.sleep(5)
                await message.edit(embed=indiv)
            if type(priority) is discord.Member:
                for i, f in enumerate(message.embeds[0].fields):
                    if '📜Messages' == f.name: 
                        message.embeds[0].set_field_at(i, name=f.name, value=await self.MemberPosts(every[0].obj))
                        await message.edit(embed=message.embeds[0])
                        break
            if counter == 0:
                try: logs = await ctx.guild.audit_logs(limit=None).flatten()
                except: logs = False #signify failure to the end user
                try: invites = await ctx.guild.invites()
                except: invites = False
                try: bans = await ctx.guild.bans()
                except: bans = False
                try: webhooks = await ctx.guild.webhooks()
                except: webhooks = False
            counter += 1
        loadContent = discord.Embed(title='{}Loading {}', color=yellow[colorTheme(ctx.guild)])
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
                    try: await message.clear_reactions()
                    except: pass
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
                    await message.edit(content=None,embed=(await self.evalInfo(every[int(stuff.content)-1].obj, ctx.guild, logs)))
                    if type(every[int(stuff.content) - 1].obj) is discord.Member:
                        for i, f in enumerate(message.embeds[0].fields):
                            if '📜Messages' == f.name: 
                                message.embeds[0].set_field_at(i, name=f.name, value=await self.MemberPosts(every[0].obj))
                                await message.edit(embed=message.embeds[0])
                                break
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
        embed=discord.Embed(title=s.name, description='' if s.description is None else '**Server description:** {}\n\n'.format(s.description), timestamp=datetime.datetime.utcnow(), color=yellow[colorTheme(s)])
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
        embed.add_field(name='Audit logs',value=self.loading if logs is None else '🔒Unable to obtain audit logs' if logs is False else len(logs))
        if s.system_channel is not None: embed.add_field(name='System channel',value='{}: {}'.format(s.system_channel.mention, ', '.join([k[0] for k in (iter(s.system_channel_flags))])))
        embed.add_field(name='Role count',value=len(s.roles) - 1)
        embed.add_field(name='Owner',value=s.owner.mention)
        embed.add_field(name='Banned members',value=self.loading if bans is None else '🔒Unable to obtain server bans' if bans is False else len(bans))
        embed.add_field(name='Webhooks',value=self.loading if hooks is None else '🔒Unable to obtain webhooks' if hooks is False else len(hooks))
        embed.add_field(name='Invites',value=self.loading if invites is None else '🔒Unable to obtain invites' if invites is False else len(invites))
        embed.add_field(name='Emojis',value='{}/{}'.format(len(s.emojis), s.emoji_limit))
        embed.add_field(name='Messages', value=f'about {messages}')
        embed.set_footer(text='Server ID: {}'.format(s.id))
        return embed

    async def ChannelInfo(self, channel: discord.abc.GuildChannel, invites, pins, logs):
        permString = None
        global bot
        details = discord.Embed(title=f'{self.channelEmoji(channel)}{channel.name}', description='',color=yellow[colorTheme(channel.guild)], timestamp=datetime.datetime.utcnow())
        details.set_footer(text='Channel ID: {}'.format(channel.id))
        if type(channel) is discord.TextChannel: details.description+=channel.mention
        if type(channel) is not discord.CategoryChannel:
            #details.description+='\n\n**Channels {}**\n{}'.format('without a category' if channel.category is None else 'in category {}'.format(channel.category.name), '\n'.join(['{}'.format('{}{}{}{}'.format('**' if chan==channel else '', types.get(type(chan)), chan.name, '**' if chan==channel else '')) for chan in channel.category.channels]))
            details.description+='\n**Category:** {}'.format('None' if channel.category is None else channel.category.name)
        else: details.description+='\n\n**Channels in this category**\n{}'.format('\n'.join(['{}{}'.format(self.channelEmoji(chan), chan.name) for chan in channel.channels]))
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
        if logs:
            for log in logs:
                if log.action == discord.AuditLogAction.channel_update and (datetime.datetime.utcnow() - log.created_at).seconds > 600:
                    if log.target.id == channel.id:
                        updated = log.created_at + datetime.timedelta(hours=timeZone(channel.guild))
                        break
        if updated is None: updated = created
        details.add_field(name='Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nameZone(channel.guild), (datetime.datetime.utcnow()-created).days))
        details.add_field(name='Last updated',value=f'{updated:%b %d, %Y • %I:%M %p} {nameZone(channel.guild)} ({(datetime.datetime.utcnow() - updated).days} days ago)' if logs != [] else self.loading)
        inviteCount = []
        if invites:
            for inv in iter(invites): inviteCount.append(inv.inviter)
        details.add_field(name='Invites to here',value=self.loading if invites is None else '🔒Unable to retrieve invites' if invites is False else 'None' if len(inviteCount) == 0 else ', '.join(['{} by {}'.format(a[1], a[0].name) for a in iter(collections.Counter(inviteCount).most_common())]))
        if type(channel) is discord.TextChannel:
            details.add_field(name='Topic',value='{}{}'.format('<No topic>' if channel.topic is None or len(channel.topic) < 1 else channel.topic[:100], '' if channel.topic is None or len(channel.topic)<=100 else '...'),inline=False)
            details.add_field(name='Slowmode',value='{}s'.format(channel.slowmode_delay))
            with open(f'{indexes}/{channel.guild.id}/{channel.id}.json') as f: details.add_field(name='Message count',value=len(json.load(f).keys()))
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
        created = r.created_at + datetime.timedelta(hours=timeZone(r.guild))
        updated = None
        if logs:
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
        embed.add_field(name='Last updated',value=f'{updated:%b %d, %Y • %I:%M %p} {nameZone(r.guild)} ({(datetime.datetime.utcnow() - updated).days} days ago)' if logs != [] else self.loading if logs is None else '🔒Unable to obtain audit logs')
        embed.add_field(name='Belongs to',value='{} members'.format(len(r.members)))
        embed.set_footer(text='Role ID: {}'.format(r.id))
        return embed

    async def MemberInfo(self, m: discord.Member, *, addThumbnail=True, calculatePosts=True):
        if calculatePosts: postCount = await self.MemberPosts(m)
        else: postCount = self.loading
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
        activities = {discord.Status.online: self.emojis['online'], discord.Status.idle: self.emojis['idle'], discord.Status.dnd: self.emojis['dnd'], discord.Status.offline: self.emojis['offline']}
        #embed.description='{} ({}) {}\n\n{}Last active {} {} • {} ago ({}){}'.format(activities.get(m.status), m.mention, m.name,
        #    'Last online {} {} • {} ago\n'.format(onlineTimestamp.strftime('%b %d, %Y • %I:%M %p'), nameZone(m.guild), list(reversed(onlineDisplay))[0]) if m.status == discord.Status.offline else '', activeTimestamp.strftime('%b %d, %Y • %I:%M %p'), nameZone(m.guild), list(reversed(activeDisplay))[0], mA.get('reason'), '\n•This member is likely {} invisible'.format(self.emojis["offline"]) if mA.get('timestamp') > lastOnline(m) and m.status == discord.Status.offline else '')
        embed.description=f'{activities.get(m.status)} {m.name} ({m.mention})\nLast online: This feature is globally disabled until further notice\nLast Active: This feature is globally disabled until further notice'
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
        embed.add_field(name='📜Messages',value=postCount)
        embed.add_field(name='🎙Voice Chat',value=voice)
        if addThumbnail: embed.set_thumbnail(url=m.avatar_url)
        embed.set_footer(text='Member ID: {}'.format(m.id))
        return embed
        
    async def EmojiInfo(self, e: discord.Emoji, owner):
        created = e.created_at + datetime.timedelta(hours=timeZone(e.guild))
        embed = discord.Embed(title=e.name,description=str(e),timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(e.guild)])
        embed.set_image(url=e.url)
        embed.set_footer(text='Emoji ID: {}'.format(e.id))
        embed.add_field(name='Twitch emoji',value=e.managed)
        if owner is not None: embed.add_field(name='Uploaded by',value='{} ({})'.format(owner.mention, owner.name))
        embed.add_field(name='Server',value=e.guild.name)
        embed.add_field(name='📆Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nameZone(e.guild), (datetime.datetime.utcnow()-created).days))
        return embed

    async def PartialEmojiInfo(self, e: discord.PartialEmoji, s: discord.Guild):
        embed=discord.Embed(title=e.name,description=str(e),timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(s)])
        embed.set_image(url=e.url)
        embed.set_footer(text='Emoji ID: {}'.format(e.id))
        return embed

    async def InviteInfo(self, i: discord.Invite, s): #s: server
        embed=discord.Embed(title='Invite details',description=str(i),timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(s)])
        embed.set_thumbnail(url=i.guild.icon_url)
        expires=datetime.datetime.utcnow() + datetime.timedelta(seconds=i.max_age) + datetime.timedelta(hours=timeZone(s))
        created = i.created_at + datetime.timedelta(hours=timeZone(s))
        embed.add_field(name='📆Created',value='{} {} ({} days ago)'.format(created.strftime("%b %d, %Y • %I:%M %p"), nameZone(s), (datetime.datetime.utcnow() - created).days))
        embed.add_field(name='⏰Expires',value='{} {}'.format(expires.strftime("%b %d, %Y • %I:%M %p"), nameZone(s)) if i.max_age > 0 else 'Never')
        embed.add_field(name='Server',value=i.guild.name)
        embed.add_field(name='Channel',value=i.channel.mention)
        embed.add_field(name='Author',value='{} ({})'.format(i.inviter.mention, i.inviter.name))
        embed.add_field(name='Used',value='{}/{} times'.format(i.uses, '∞' if i.max_uses == 0 else i.max_uses))
        embed.set_footer(text='Invite server ID: {}'.format(i.guild.id))
        #In the future, once bot is more popular, integrate server stats from other servers
        return embed

    async def BotInfo(self, app: discord.AppInfo, s: discord.Guild):
        bpg = 1073741824 #Bytes per gig
        embed=discord.Embed(title='About Disguard',description='{0}{1}{0}'.format(bot.get_emoji(569191704523964437), app.description),timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(s)])
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
        embed=discord.Embed(title='{}\'s emojis'.format(emojis[0].guild.name),description='Total emojis: {}'.format(len(emojis)),timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(emojis[0].guild)])
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
        global bot
        embed=discord.Embed(title='{}\'s channels'.format(channels[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(channels[0].guild)])
        none=['(No category)'] if len([c for c in channels if type(c) is not discord.CategoryChannel and c.category is None]) else []
        none += ['|{}{}'.format(self.channelEmoji(c), c.name) for c in channels if type(c) is not discord.CategoryChannel and c.category is None]
        for chan in channels[0].guild.categories:
            none.append('{}{}'.format(self.channelEmoji(chan), chan.name))
            none+=['|{}{}'.format(self.channelEmoji(c), c.name) for c in chan.channels]
        embed.description='Total channels: {}\n\n{}'.format(len(channels), '\n'.join(none))
        if logs: embed.add_field(name='Total channels ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.channel_create])))
        elif logs is None: embed.add_field(name='Total channels ever created',value=self.loading)
        else: embed.add_field(name='Total channels ever created',value='🔒Unable to obtain audit logs')
        return embed

    async def RoleListInfo(self, roles, logs):
        '''Prereq: len(roles) > 0'''
        embed=discord.Embed(title='{}\'s roles'.format(roles[0].guild.name),timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(roles[0].guild)])
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
        embed=discord.Embed(title='{}\'s members'.format(members[0].guild.name),description='',timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(members[0].guild)])
        posts=[]
        for channel in members[0].guild.text_channels:
            with open(f'{indexes}/{members[0].guild.id}/{channel.id}.json') as f: 
                posts += [message['author0'] for message in json.load(f).values()]
        most = ['{} with {}'.format(bot.get_user(a[0]).name, a[1]) for a in iter(collections.Counter(posts).most_common(1))][0]
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
        embed=discord.Embed(title=f'{invites[0].guild.name if invites else "This server"}\'s invites', timestamp=datetime.datetime.utcnow(), color=yellow[colorTheme(s)])
        if invites: embed.description='Total invites: {}\n\n • {}'.format(len(invites), '\n • '.join(['discord.gg/**{}**: Goes to {}, created by {}'.format(i.code, i.channel.name, i.inviter.name) for i in invites]))[:2047]
        else: embed.description=f'Total invites: {self.loading if invites is None else "🔒Unable to obtain invites"}'
        if logs: embed.add_field(name='Total invites ever created',value='At least {}'.format(len([l for l in logs if l.action == discord.AuditLogAction.invite_create])))
        elif logs is None: embed.add_field(name='Total invites ever created',value=self.loading)
        else: embed.add_field(name='Total invites ever created',value='🔒Unable to obtain audit logs')
        return embed

    async def BansListInfo(self, bans, logs, s): #s=server
        embed=discord.Embed(title='{}\'s bans'.format(s.name),timestamp=datetime.datetime.utcnow(),color=yellow[colorTheme(s)])
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
                    created = l.created_at + datetime.timedelta(hours=timeZone(s))
                    array.append('{}: Banned by {} on {} because {}'.format(l.target.name, l.user.name, created.strftime('%m/%d/%Y@%H:%M'), '(No reason specified)' if b.reason is None else b.reason))
                    current.append(b.user)
        other=[]
        for l in logs:
            if l.action == discord.AuditLogAction.ban and l.target not in current:
                created = l.created_at + datetime.timedelta(hours=timeZone(s))
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
        try: return [{'invite': i, 'check': check(i)} for i in (await g.invites()) if check(i) is not None]
        except: return []

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

    def AvoidDeletionLogging(self, messages):
        '''Don't log the deletion of passed messages'''
        if type(messages) is list: self.pauseDelete += [m.id for m in messages]
        else: self.pauseDelete.append(messages.id)

    def channelEmoji(self, c,):
        '''Gives us the proper new emoji for the channel - good for varying channels in a single list'''
        if c.type == discord.ChannelType.category: return self.emojis['folder']
        elif c.type == discord.ChannelType.private: return self.emojis['member']
        elif c.type == discord.ChannelType.group: return self.emojis['members']
        elif c.type == discord.ChannelType.store: return self.emojis['storeChannel']
        elif c.type == discord.ChannelType.news: return self.emojis['announcementsChannel']
        else:
            private = c.overwrites_for(c.guild.default_role).read_messages == False
            if c.type == discord.ChannelType.text:
                if c.is_nsfw(): return self.emojis['nsfwChannel']
                elif c.guild.rules_channel and c.id == c.guild.rules_channel.id: return self.emojis['rulesChannel']
                elif private: return self.emojis['privateTextChannel']
                else: return self.emojis['textChannel']
            elif c.type == discord.ChannelType.voice:
                if private: return self.emojis['privateVoiceChannel']
                else: return self.emojis['voiceChannel']
        return '❔'

    def channelIsHidden(self, c, member):
        '''Returns a boolean representing whether a channel is visible to the given member'''
        return not c.permissions_for(member).read_messages

    async def CheckDisguardServerRoles(self, memb, *, mode=0, reason=None):
        '''Automatic scan for Alpha Tester/VIP Alpha Tester for Disguard's official server. Mode - 0=Add&Remove, 1=Add, 2=Remove'''
        #If we pass a solitary member, convert it to a list with a single entry, otherwise, leave it alone
        #COMMENT THE REST OF MY WORK. make the update good
        if self.bot.user.id != 558025201753784323: return
        if type(memb) is discord.User: members = [memb]
        else: members = memb
        disguardServer = bot.get_guild(560457796206985216) #Disguard official server
        disguardServerMemberList = [m.id for m in disguardServer.members] #List of member IDs in Disguard Official server
        disguardAlphaTester = disguardServer.get_role(571367278860304395) #Alpha Testers role in Disguard Official server
        disguardVIPTester = disguardServer.get_role(571367775163908096) #VIP Alpha Testers role in Disguard Official server
        alphaMembers = [member.id for member in disguardAlphaTester.members] #ID list of members who have the Alpha Testers role
        vipMembers = [member.id for member in disguardVIPTester.members] #ID list of members who have the VIP Alpha Testers role
        #Loop through all members passed in the argument
        for m in members:
            #If this member is in Disguard Official server
            if m.id in disguardServerMemberList:
                #Loop iteration member equivalent in Disguard server
                disguardMember = disguardServer.get_member(m.id)
                if mode != 2: #Handles adding of roles
                    if m.id == m.guild.owner.id: await disguardMember.add_roles(disguardVIPTester, reason=f'Automatic Scan: {reason}')
                    elif m.guild_permissions.manage_guild: await disguardMember.add_roles(disguardAlphaTester, reason=f'Automatic Scan: {reason}')
                if mode != 1: #Handles removing of roles
                    if m.id in alphaMembers or m.id in vipMembers:
                        memberServers = [server for server in bot.guilds if m.id in [member.id for member in server.members]]
                        if not any([m.id == s.owner.id for s in memberServers]) and m.id in vipMembers: await disguardMember.remove_roles(disguardVIPTester, reason=f'Automatic Scan: {reason}')
                        if not any([s.get_member(m.id).guild_permissions.manage_guild for s in memberServers]) and m.id in alphaMembers: await disguardMember.remove_roles(disguardAlphaTester, reason=f'Automatic Scan: {reason}')

    async def uploadFiles(self, f):
        if type(f) is not list: f = [f]
        message = await self.imageLogChannel.send(files=f)
        return [attachment.url for attachment in message.attachments] if len(f) > 1 else message.attachments[0].url

    def PermissionChanges(self, membersInput, message, embed, mod='role'):
        members = {}
        removedKeys = {}
        gainedKeys = {}
        g = membersInput[0].guild
        settings = getCyberAttributes(g, mod)
        for m in membersInput:
            oldPerms = self.memberPermissions[g.id][m.id]
            removed = ' '.join([p[0] for p in oldPerms if p[1] and p[0] not in [pp[0] for pp in m.guild_permissions if pp[1]]])
            gained = ' '.join([p[0] for p in m.guild_permissions if p[1] and p[0] not in [pp[0] for pp in oldPerms if pp[1]]])
            if len(removed) > 0: 
                try: members[m.id].update({'removed': removed})
                except KeyError: members[m.id] = {'removed': removed}
            if len(gained) > 0: 
                try: members[m.id].update({'gained': gained})
                except KeyError: members[m.id] = {'gained': gained}
        for k, v in members.items():
            try: removedKeys[v.get('removed')].append(g.get_member(k))
            except AttributeError: removedKeys[v.get('removed')] = [g.get_member(k)]
            except KeyError:
                if v.get('removed') is not None: removedKeys[v.get('removed')] = [g.get_member(k)]
            try: gainedKeys[v.get('gained')].append(g.get_member(k))
            except AttributeError: gainedKeys[v.get('gained')] = [g.get_member(k)]
            except KeyError:
                if v.get('gained') is not None: gainedKeys[v.get('gained')] = [g.get_member(k)]
        embedDescriptionLines = []
        for k, v in gainedKeys.items():
            embedDescriptionLines.append((f'''📥 {k}''', f'''{", ".join(m.name for m in v) if len(v) < 5 else f"[Hover to view the {len(v)} members]({message.jump_url} '{newline.join(m.name for m in v)}')" if len(v) < 30 else f"{len(v)} members"}'''))
        for k, v in removedKeys.items():
            embedDescriptionLines.append((f'''📤 {k}''', f'''{", ".join(m.name for m in v) if len(v) < 5 else f"[Hover to view the {len(v)} members]({message.jump_url} '{newline.join(m.name for m in v)}')" if len(v) < 30 else f"{len(v)} members"}'''))
        if len(embedDescriptionLines) == 0: embed.description += f'''\n{self.emojis['details'] if settings['context'][1] > 0 else ''}No members were affected by the permissions changes'''
        else:
            embed.description += f'''\n{self.emojis['edit'] if settings['context'][1] > 0 else ''}{len(members)} members had their permissions updated (see bottom)'''
            for tup in embedDescriptionLines[:25]:
                individualTup = tup[0].split(' ')
                overshoot = len(', '.join([permissionKeys[i] for i in tup[0].split(' ')[1:]])) + 1 - 256 #256 is embed field name character limit, +1 accounts for the emoji at the beginning
                #If we have 40 characters (or more) to spare, use the more concise custom emoji (yet it takes up many characters rather than 1 like the unicode emojis)
                if overshoot > 0:
                    truncatePerWord = math.ceil(overshoot / len(individualTup[1:])) #how many letters to cut per word, +1 at the end to include the triple periods character with length 1
                    if truncatePerWord > 1:
                        tup = [[], tup[1]]
                        for i in individualTup[1:]:
                            pki = permissionKeys[i]
                            offset = 0
                            if truncatePerWord % 2 == 0: offset -= 1
                            if len(pki) % 2 == 0: offset += 1
                            tup[0].append(f"{pki[:(len(pki) - truncatePerWord) // 2]}…{pki[(len(pki) + truncatePerWord) // 2 + offset:]}")
                    embed.add_field(name=individualTup[0] + ', '.join(tup[0]), value=tup[1], inline=False)
                else: 
                    if overshoot < -40 and settings['library'] > 0: individualTup[0] = individualTup[0].replace('📥', str(self.emojis['memberJoin'])).replace('📤', str(self.emojis['memberLeave']))
                    embed.add_field(name=individualTup[0] + ', '.join([permissionKeys[i] for i in tup[0][2:].split(' ')]), value=tup[1], inline=False)
        return embed

    async def subredditEmbed(self, search, plainText = False):
        reddit = self.bot.reddit
        subreddit = await reddit.subreddit(search, fetch=True)
        url = f'https://www.reddit.com{subreddit.url}'
        if plainText: return f'<{url}>'
        else:
            keyColor = subreddit.key_color or subreddit.primary_color or '#2E97E5' #The last one is the default blue
            embed = discord.Embed(
                title=f'r/{subreddit.display_name}',
                description=f'''{subreddit.public_description}\n\n{subreddit.subscribers} subscribers • {subreddit.active_user_count} online\n{f"{self.emojis['alert']}This subreddit is NSFW" if subreddit.over18 else ""}''',
                color=hexToColor(keyColor),
                url=url)
            embed.set_thumbnail(url=subreddit.icon_img)
            embed.set_image(url=subreddit.banner_background_image)
            return embed
    
    async def redditSubmissionEmbed(self, g, source, redditFeed=False, truncateTitle=100, truncateText=400, media=3, creditAuthor=True, color='colorCode', timestamp=True):
        '''Media - 0: All off, 1: Only thumbnail, 2: Only images, 3: All on'''
        if truncateTitle < 1: truncateTitle = 256
        if truncateText < 1: truncateText = 1900
        reddit = self.bot.reddit
        if type(source) is str:
            if 'https://' in source: submission = await reddit.submission(url=source)
            else: submission = await reddit.submission(id=source)
        else: submission = source
        author = submission.author
        await author.load()
        subreddit = submission.subreddit
        await subreddit.load()
        if submission.is_self: submissionType, linkFlavor = 'text', ''
        elif submission.is_video:
            submissionType, url = 'video', submission.media['reddit_video']['fallback_url'][:submission.media['reddit_video']['fallback_url'].find('?source=')]
            linkFlavor = f"\n[Direct video link]({url} '{url}')"
        elif 'i.redd.it' in submission.url: submissionType, linkFlavor = 'image', ''
        elif 'www.reddit.com/gallery' in submission.url: submissionType, linkFlavor = 'gallery', f"\n[Gallery view]({submission.url} '{submission.url}')"
        else: submissionType, linkFlavor = 'link', f"\n[{basicURL(submission.url)}]({submission.url} '{submission.url}')"
        typeKeys = {'text': '📜', 'video': self.emojis['camera'], 'image': self.emojis['images'], 'link': '🔗', 'gallery': self.emojis['details']}
        awards = submission.total_awards_received
        keyColor = subreddit.key_color or subreddit.primary_color or '#2E97E5' #The last one is the default blue
        if redditFeed: description=f'''{submissionType[0].upper()}{submissionType[1:]} post • r/{subreddit.display_name}{linkFlavor}{f"{newline}👀(Spoiler)" if submission.spoiler else ""}{f"{newline}{self.emojis['alert']}(NSFW)" if submission.over_18 else ""}'''
        else: description=f'''{submission.score} upvote{"s" if submission.score != 1 else ""} • {round(submission.upvote_ratio * 100)}% upvoted{f" • {awards} awards" if awards > 0 else ""}{f" • {submission.view_count} " if submission.view_count else ""} • {submission.num_comments} comment{"s" if submission.num_comments != 1 else ""} on r/{subreddit.display_name}{linkFlavor}{f"{newline}👀(Spoiler)" if submission.spoiler else ""}{f"{newline}{self.emojis['alert']}(NSFW)" if submission.over_18 else ""}'''
        embed = discord.Embed(
            title=f'{"🔒" if submission.locked and not redditFeed else ""}{"📌" if submission.stickied and not redditFeed else ""}{typeKeys[submissionType] if not redditFeed else ""}{(submission.title[:truncateTitle] + "…") if len(submission.title) > truncateTitle else submission.title}', 
            description=description,
            color=hexToColor(keyColor) if color == 'colorCode' else hexToColor(color), url=f'https://www.reddit.com{submission.permalink}')
        if submissionType == 'text': embed.description += f'\n\n{(submission.selftext[:truncateText] + "…") if len(submission.selftext) > truncateText else submission.selftext}'
        if creditAuthor > 0:
            embed.set_author(name=author.name if creditAuthor != 2 else discord.Embed.Empty, icon_url=author.icon_img if creditAuthor != 1 else discord.Embed.Empty)
        if media > 0:
            if media != 2: embed.set_thumbnail(url=subreddit.icon_img)
            if submissionType == 'image': 
                if redditFeed and media != 1: embed.set_image(url=submission.url)
                elif not redditFeed: embed.set_thumbnail(url=submission.url)
        if timestamp: embed.set_footer(text=f'{"Posted " if not redditFeed else ""}{(datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=submission.created_utc) + datetime.timedelta(hours=timeZone(g))):%b %d, %Y • %I:%M %p} {nameZone(g)}')
        return embed

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
    # return all([lightningLogging.get(s.id).get('cyberlog').get('modules')[modElement(s, mod)].get('enabled'),
    # lightningLogging.get(s.id).get('cyberlog').get('enabled'),
    # [any([lightningLogging.get(s.id).get('cyberlog').get('modules')[modElement(s, mod)].get('channel') is not None,
    # lightningLogging.get(s.id).get('cyberlog').get('modules')[modElement(s, mod)].get('defaultChannel') is not None])]])

    return all([lightningLogging.get(s.id).get('cyberlog').get(mod).get('enabled'),
    lightningLogging.get(s.id).get('cyberlog').get('enabled'),
    [any([lightningLogging.get(s.id).get('cyberlog').get(mod).get('channel') is not None,
    lightningLogging.get(s.id).get('cyberlog').get(mod).get('defaultChannel') is not None])]])

def logChannel(s: discord.Guild, mod):
    # modular = lightningLogging.get(s.id).get('cyberlog').get('modules')[modElement(s, mod)].get('channel')
    # default = lightningLogging.get(s.id).get('cyberlog').get('defaultChannel')
    # return s.get_channel(default) if modular is None else s.get_channel(modular)

    modular = lightningLogging.get(s.id).get('cyberlog').get(mod).get('channel')
    default = lightningLogging.get(s.id).get('cyberlog').get('defaultChannel')
    return s.get_channel(default) if modular is None else s.get_channel(modular)

async def verifyLogChannel(bot, s: discord.Guild):
    #modular = lightningLogging.get(s.id).get('cyberlog').get('modules')[modElement(s, mod)].get('channel')
    try: default = lightningLogging.get(s.id).get('cyberlog').get('defaultChannel')
    except: return
    if default == None: return
    final = s.get_channel(default)
    for mod in ['message', 'doorguard', 'server', 'channel', 'member', 'role', 'emoji', 'voice']:
        modular = lightningLogging.get(s.id).get('cyberlog').get(mod).get('channel')
        if not modular:
            channel = s.get_channel(modular)
            if not channel and type(modular) is int:
                if final:
                    try: await final.send(embed=discord.Embed(description=f'⚠Your configured log channel (ID `{modular}`) for the `{mod}` module is invalid and has been reset to no value.\n[Edit settings online](http://disguard.herokuapp.com/manage/{s.id}/cyberlog)'))
                    except: pass
                await database.SetSubLogChannel(s, mod, None)
    if not default:
        if not final and type(default) is int:
            try: await (await database.CalculateModeratorChannel(s, bot, False)).send(embed=discord.Embed(description=f'⚠Your configured default log channel (ID `{default}`) is invalid and has been reset to no value.\n[Edit settings online](http://disguard.herokuapp.com/manage/{s.id}/cyberlog)'))
            except: pass
            await database.SetLogChannel(s, None)

def logExclusions(channel: discord.TextChannel, member: discord.Member):
    return not any([channel.id in lightningLogging.get(channel.guild.id).get('cyberlog').get('channelExclusions'),
    member.id in lightningLogging.get(channel.guild.id).get('cyberlog').get('memberExclusions'),
    any([r.id in lightningLogging.get(channel.guild.id).get('cyberlog').get('roleExclusions') for r in member.roles])])

def memberGlobal(s: discord.Guild):
    return lightningLogging.get(s.id).get('cyberlog').get('memberGlobal')

def antispamObject(s: discord.Guild):
    return lightningLogging.get(s.id).get('antispam')

def readPerms(s: discord.Guild, mod):
    #return lightningLogging.get(s.id).get('cyberlog').get('modules')[modElement(s, mod)].get('read')
    return lightningLogging.get(s.id).get('cyberlog').get(mod).get('read') or lightningLogging[s.id]['cyberlog']['read']

def getLibrary(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'library')

def getThumbnail(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'thumbnail')

def getAuthor(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'author')

def getContext(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'context')

def getHoverLinks(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'hoverLinks')

def getColor(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'color')

def getPlainText(s: discord.Guild, mod):
     return cyberAttribute(s, mod, 'plainText')

def getEmbedTimestamp(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'embedTimestamp')

def getflashText(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'flashText')

def getTTS(s: discord.Guild, mod):
    return cyberAttribute(s, mod, 'tts')

def cyberAttribute(s: discord.Guild, mod, a):
    '''Returns common attribute: cyberlog <--> cyberlog module. Not coded for beta datasystem'''
    default = lightningLogging[s.id]['cyberlog'][a]
    specific = lightningLogging[s.id]['cyberlog'][mod][a]
    return specific or default

def getCyberAttributes(s: discord.Guild, mod):
    result = {}
    for word in ('library', 'thumbnail', 'author', 'context', 'hoverLinks', 'color', 'plainText', 'read', 'embedTimestamp', 'botLogging', 'flashText', 'tts'):
        result[word] = cyberAttribute(s, mod, word)
    return result

def clockEmoji(timestamp):
    '''Returns clock emoji in proper hand position, based on timestamp'''
    return f':clock{int(timestamp.strftime("%I"))}{"30" if int(f"{timestamp:%M}") in range(15, 46) else ""}:' #Converting to int in the first part removes padded zeros, and actually converts for range comparison in the second part

def absTime(x, y, distance):
    '''Checks to ensure x and y (date objects (date, datetime, or time)) are within `distance` (timedelta) of each other - essentially an absolute value mathod'''
    return x - y < distance or y - x < distance

def embedToPlaintext(e: discord.Embed):
    '''Returns a string composed of fields/values in the embed. Cleans up the content too.'''
    result = ''
    for f in e.fields:
        result += f'\n{f.name}: {multiLineQuote(f.value) if len(f.value) < 300 else "<Truncated>"}'
    #This somewhat intensive loop has to go character by character to clean up emojis and the like
    parsed = ''
    append = True #Whether to add characters into the parsed result (used for custom emojis, since those have angle brackets)
    for char in result:
        if char == '<': append = False #Pause appending for content inside of angle brackets
        if char == '>': append = True #Resume appending for content outside of angle brackets
        if char in string.printable and append: parsed += char
    return discord.utils.escape_mentions(parsed).replace('**', '').replace('*', '').replace('__', '')[:2000]

def multiLineQuote(s):
    '''Converts a string containing newlines in it to a block quote'''
    return '\n'.join([f'> {line}' for line in s.split('\n')])

def ManageServer(member: discord.Member): #Check if a member can manage server, used for checking if they can edit dashboard for server
    if member.id == member.guild.owner.id: return True
    if member.id == 247412852925661185: return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.manage_guild:
            return True
    return False

def nameZone(s: discord.Guild):
    return lightningLogging.get(s.id).get('tzname')

def timeZone(s: discord.Guild):
    return lightningLogging.get(s.id).get('offset')

def prefix(s: discord.Guild):
    return lightningLogging.get(s.id).get('prefix')

def getServer(s: discord.Guild):
    return lightningLogging.get(s.id)

def colorTheme(s):
    return getServer(s)['colorTheme']

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

def hexToColor(string):
    '''Convert a hex code (including if it's a string) to a discord color'''
    string = str(string).replace('#', '') #In case it isn't already
    if len(string) != 6: return discord.Color.default() #Invalid value
    try: 
        r, g, b = int(string[:2], 16), int(string[2:4], 16), int(string[4:], 16)
        return discord.Color.from_rgb(r, g, b)
    except: return discord.Color.default()

def basicURL(url):
    '''Return the URL only containing site domain'''
    return url[url.find('//') + 2:url.find('/', url.find('//') + 2)]
    

def elapsedDuration(timeSpan, joinString=True, fullUnits=True, *, onlyTimes=False):
    '''Returns a list of string representing elapsed time, given a dateTime. joinString determines return type'''
    hours, minutes, seconds = timeSpan.seconds // 3600, (timeSpan.seconds // 60) % 60, timeSpan.seconds - (timeSpan.seconds // 3600) * 3600 - ((timeSpan.seconds // 60) % 60)*60
    timeList = [seconds, minutes, hours, timeSpan.days]
    if onlyTimes: return list(reversed(timeList))
    display = []
    for i, v in reversed(tuple(enumerate(timeList))): #v stands for value
        if v != 0: display.append(f'{v} {units[i] if fullUnits else units[i][0]}{"s" if v != 1 and fullUnits else ""}')
    if len(display) == 0: display = ['0 seconds']
    if joinString: return f"{', '.join(display[:-1])} and {display[-1]}" if len(display) > 1 else display[0]
    else: return display #This is a list that will be joined as appropriate at my discretion in the parent method, if I don't want to use the default joiner above


def setup(Bot):
    global bot
    Bot.add_cog(Cyberlog(Bot))
    bot = Bot