import asyncio
import codecs
import collections
import copy
import datetime
import difflib
import gc
import json
import logging
import math
import os
import re
import shutil
import textwrap
import traceback
import typing

import aiofiles
import aiofiles.os as aios
import aioshutil
import discord
import emojis
from discord.ext import commands, tasks

import database
import Indexing
import Info
import lightningdb
import Reddit
import utility

bot = None
serverPurge = {}
summarizeOn = False
secondsInADay = 3600 * 24
DST = 4 if datetime.datetime.now() < datetime.datetime(2023, 11, 5, 2) else 5
units = ['second', 'minute', 'hour', 'day']
logUnits = ['message', 'doorguard', 'channel', 'member', 'role', 'emoji', 'server', 'voice', 'misc']
TEMP_DIR = 'storage/temp'  # Path to save images for profile picture changes and other images in logs
gimpedServers = [403698615446536203, 460611346837405696, 366019576661671937]
try:
    os.makedirs(TEMP_DIR)
except FileExistsError:
    pass
stockImage = 'https://www.femalefirst.co.uk/image-library/land/500/r/rick-astley-whenever-you-need-somebody-album-cover.jpg'

logger = logging.getLogger('discord')

summaries = {}
grabbedSummaries = {}
indexed = {}

# yellow=0xffff00
# green=0x008000
# red=0xff0000
# blue=0x0000FF
# orange=0xD2691E

green = (0x008000, 0x66FF66)
blue = (0x0000FF, 0x6666FF)
red = (0xFF0000, 0xFF6666)
orange = (0xD2691E, 0xFFC966)
yellow = (0xFFFF00, 0xFFFF66)

NEWLINE = '\n'
newlineQuote = '\n> '
qlf = '  '  # Two special characters to represent quoteLineFormat


class Cyberlog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.emojis: typing.Dict[int, discord.Emoji] = {}
        # Emoji consortium: https://drive.google.com/drive/folders/14ttnIp6MkHdooCgMP167KNbgO-eeD3e8?usp=sharing
        for server in [560457796206985216, 403327720714665994, 495263898002522144, 1176517654287224894]:
            for e in bot.get_guild(server).emojis:
                self.emojis[e.name] = e
        self.bot = bot
        self.bot.attributeHistoryQueue = collections.defaultdict(dict)
        self.bot.useAttributeQueue = False
        self.imageLogChannel: discord.TextChannel = bot.get_channel(534439214289256478)
        self.globalLogChannel: discord.TextChannel = bot.get_channel(566728691292438538)
        self.loading: discord.Emoji = self.emojis['loading']
        self.channelKeys = {
            'text': self.emojis['textChannel'],
            'voice': self.emojis['voiceChannel'],
            'category': self.emojis['folder'],
            'private': self.emojis['hiddenVoiceChannel'],
            'news': self.emojis['announcementsChannel'],
            'store': self.emojis['storeChannel'],
        }
        self.repeatedJoins: typing.Dict[str, typing.List[datetime.datetime]] = {}
        self.pins: typing.Dict[int, typing.List[int]] = {}  # enablement of this feature is tied to attachment logging being enabled
        self.categories: typing.Dict[int, typing.List[discord.abc.GuildChannel]] = {}
        self.members: typing.Dict[int, typing.List[discord.Member]] = {}
        self.invites = {}
        self.roles: typing.Dict[int, discord.Member] = {}
        self.reactions = {}
        self.memberPermissions = collections.defaultdict(lambda: collections.defaultdict(dict))
        self.memberVoiceLogs = {}
        self.pauseDelete = []
        self.resumeToken = None
        self.channelCacheHelper = {}
        self.syncData.start()
        self.delete_message_attachments.start()
        self.trackChanges.start()

    def cog_unload(self):
        self.syncData.cancel()
        self.delete_message_attachments.cancel()
        self.trackChanges.cancel()

    @tasks.loop()
    async def trackChanges(self):
        await asyncio.sleep(3)
        reddit: Reddit.Reddit = self.bot.get_cog('Reddit')
        try:
            async with database.getDatabase().watch(full_document='updateLookup', resume_after=self.resumeToken) as change_stream:
                async for change in change_stream:
                    self.resumeToken = change_stream.resume_token
                    if change['operationType'] == 'delete':
                        print(
                            f"{qlf}{change['clusterTime'].as_datetime() - datetime.timedelta(hours=DST):%b %d, %Y • %I:%M:%S %p} - database {change['operationType']}: {change['ns']['db']} - {change['ns']['coll']}"
                        )
                        continue
                    fullDocument = change['fullDocument']
                    collection = change['ns']['coll']
                    if collection == 'disguard':
                        continue
                    elif collection == 'servers':
                        name = 'name'
                        objectID = fullDocument['server_id']
                        await lightningdb.patch_server(objectID, fullDocument)
                    elif collection == 'users':
                        name = 'user_id'
                        objectID = fullDocument['user_id']
                        await lightningdb.patch_user(objectID, fullDocument)
                    if change['operationType'] == 'update' and 'redditFeeds' in change['updateDescription']['updatedFields'].keys():
                        asyncio.create_task(reddit.redditFeedHandler(self.bot.get_guild(objectID)), name='Reddit Feed Handler - DB change')
                    if change['operationType'] == 'update' and any(
                        [word in change['updateDescription']['updatedFields'].keys() for word in ('lastActive', 'lastOnline')]
                    ):
                        continue  # Add attribute history probably
                    print(
                        f"""{qlf}{change['clusterTime'].as_datetime() - datetime.timedelta(hours=DST):%b %d, %Y • %I:%M:%S %p} - (database {change['operationType']} -- {change['ns']['db']} - {change['ns']['coll']}){f": {fullDocument[name]} - {', '.join([f' {k}' for k in change['updateDescription']['updatedFields'].keys()])}" if change['operationType'] == 'update' else ''}"""
                    )
        except Exception as e:
            print(f'Tracking error: {e}')
            traceback.print_exc()

    @tasks.loop(hours=24)  # V1.0: This now only runs once per day
    async def syncData(self):
        print('Syncing data')
        started = datetime.datetime.now()
        rawStarted = datetime.datetime.now()
        try:
            if self.syncData.current_loop % 2 == 0:  # This segment activates once every two days
                if self.syncData.current_loop == 0:  # This segment activates only once while the bot is up (on bootup)
                    task = database.Verification(self.bot)
                    await asyncio.wait_for(task, timeout=None)
                    # await database.Verification(self.bot)
                    # asyncio.create_task(self.synchronizeDatabase(True))
                    # def initializeCheck(m): return m.author.id == self.bot.user.id and m.channel == self.imageLogChannel and m.content == 'Synchronized'
                    # await self.bot.wait_for('message', check=initializeCheck) #Wait for bot to synchronize database
                # else: asyncio.create_task(self.synchronizeDatabase())
                await asyncio.sleep(0.5)
                await self.bot.get_cog('birthdays').verifyBirthdaysDict()
            for g in self.bot.guilds:
                timeString = f'Processing attributes for {g.name}'
                print(timeString)
                started = datetime.datetime.now()
                serverStarted = datetime.datetime.now()
                try:
                    asyncio.gather(
                        database.CalculateGeneralChannel(g, self.bot, True),
                        database.CalculateAnnouncementsChannel(g, self.bot, True),
                        database.CalculateModeratorChannel(g, self.bot, True),
                    )
                except:
                    pass
                await self.CheckDisguardServerRoles(g.members, mode=0, reason='Full verification check')  # Remove this for v1.0
                timeString += f'\n •Default channel calculations: {(datetime.datetime.now() - started).seconds}s'
                started = datetime.datetime.now()
                for r in g.roles:
                    self.roles[r.id] = r.members  # This allows the bot to properly display how many members had a role before it was deleted
                self.members[g.id] = g.members
                for m in g.members:
                    self.memberPermissions[g.id][m.id] = m.guild_permissions
                timeString += f'\n •Member cache management: {(datetime.datetime.now() - started).seconds}s'
                started = datetime.datetime.now()
                for c in g.categories:
                    try:
                        self.categories[c.id] = c.channels
                    except discord.Forbidden:
                        pass
                try:
                    self.categories[g.id] = [c[1] for c in g.by_category() if c[0] is None]  # This can be made faster without a generator
                except discord.Forbidden:
                    pass
                timeString += f'\n •Channel cache management: {(datetime.datetime.now() - started).seconds}s'
                started = datetime.datetime.now()
                attachmentsPath = f'Attachments/{g.id}'
                try:
                    for p in os.listdir(attachmentsPath):
                        if p != 'LogArchive' and not self.bot.get_channel(int(p)):
                            shutil.rmtree(f'Attachments/{g.id}/{p}', ignore_errors=True)
                except FileNotFoundError:
                    pass
                timeString += f'\n •Local attachment management: {(datetime.datetime.now() - started).seconds}s'
                started = datetime.datetime.now()
                try:
                    self.invites[str(g.id)] = await g.invites()
                    try:
                        self.invites[str(g.id) + '_vanity'] = await g.vanity_invite()
                    except discord.HTTPException:
                        pass
                except:
                    pass
                timeString += f'\n •Invites management: {(datetime.datetime.now() - started).seconds}s\nFinished attribute processing in {(datetime.datetime.now() - serverStarted).seconds}s total'
                print(timeString)
            started = datetime.datetime.now()
            # drop message indexes for channels the bot can't find
            for collection in await lightningdb.database.list_collection_names():
                if collection not in ('servers', 'users') and not self.bot.get_channel(int(collection)):
                    await lightningdb.delete_channel(int(collection))
            print(f'Verified local message indexes in {(datetime.datetime.now() - started).seconds}s')
            print("About to process users' attribute history")
            started = datetime.datetime.now()
            started2 = datetime.datetime.now()
            self.bot.useAttributeQueue = True
            updateOperations = collections.defaultdict(dict)
            for i, m in enumerate(self.bot.get_all_members()):
                m: discord.Member = m
                updatedAvatar = False
                if await self.privacyEnabledChecker(m, 'default', 'attributeHistory'):
                    # for g in self.bot.guilds:
                    #     m = g.get_member(u.id)
                    #     if m: break
                    cache = await utility.get_user(m)
                    if await self.privacyEnabledChecker(m, 'attributeHistory', 'statusHistory'):
                        try:
                            if m.status != discord.Status.offline:
                                if m.activity == discord.ActivityType.custom or not m.activity:
                                    prev = cache.get('statusHistory', [{}])[-1]
                                    proposed = {
                                        'e': None
                                        if not m.activity
                                        else m.activity.emoji.url
                                        if m.activity.emoji.is_custom_emoji()
                                        else str(m.activity.emoji)
                                        if m.activity.emoji
                                        else None,
                                        'n': m.activity.name if m.activity else None,
                                    }
                                    if proposed != {'e': prev.get('emoji'), 'n': prev.get('name')}:
                                        updateOperations[m.id].update(
                                            {'statusHistory': {'emoji': proposed['e'], 'name': proposed['n'], 'timestamp': discord.utils.utcnow()}}
                                        )
                        except Exception as e:
                            print(f'Custom status error for {m.name}: {e}')
                    if await self.privacyEnabledChecker(m, 'attributeHistory', 'usernameHistory'):
                        try:
                            if m.name != cache.get('usernameHistory', [{}])[-1].get('name'):
                                updateOperations[m.id].update({'usernameHistory': {'name': m.name, 'timestamp': discord.utils.utcnow()}})
                        except Exception as e:
                            print(f'Username error for {m.name}: {e}')
                    if await self.privacyEnabledChecker(m, 'attributeHistory', 'displaynameHistory'):
                        try:
                            if m.display_name != cache.get('displaynameHistory', [{}])[-1].get('name'):
                                updateOperations[m.id].update({'displaynameHistory': {'name': m.display_name, 'timestamp': discord.utils.utcnow()}})
                        except Exception as e:
                            print(f'Displayname error for {m.name}: {e}')
                    if await self.privacyEnabledChecker(m, 'attributeHistory', 'avatarHistory'):
                        try:
                            if m.display_avatar.url != cache.get('avatarHistory', [{}])[-1].get('discordURL'):
                                updateOperations[m.id].update(
                                    {
                                        'avatarHistory': {
                                            'discordURL': m.display_avatar.url,
                                            'imageURL': await self.imageToURL(m.display_avatar),
                                            'timestamp': discord.utils.utcnow(),
                                        }
                                    }
                                )
                                updatedAvatar = True
                        except Exception as e:
                            print(f'Avatar error for {m.name}: {e}')
                        if m.bot and len(cache.get('avatarHistory')) > 150:
                            stripped_avatar_history = cache.get('avatarHistory')[-150:]
                            asyncio.create_task(database.SetAvatarHistory(m, stripped_avatar_history), name='SyncData - Avatar History')
                    if updatedAvatar:
                        await discord.utils.sleep_until(
                            datetime.datetime.now() + datetime.timedelta(seconds=1)
                        )  # To prevent ratelimiting if Disguard sends a message to retrieve the image URL
                    if i % 1000 == 0 and i > 0:
                        print(f'Processed attribute history for 1000 users in {(datetime.datetime.now() - started).seconds}s')
                        started = datetime.datetime.now()
            print(f'Processed attribute history for {len(self.bot.users)} users in {(datetime.datetime.now() - started2).seconds}s')
            started = datetime.datetime.now()
            asyncio.create_task(database.BulkUpdateHistory(updateOperations), name='SyncData - Bulk Update History')
            print(f'Saved attribute history for everyone in {(datetime.datetime.now() - started).seconds}s')
            self.bot.useAttributeQueue = False
            await database.BulkUpdateHistory(self.bot.attributeHistoryQueue)
            self.bot.attributeHistoryQueue = []
            started = datetime.datetime.now()
            if self.syncData.current_loop % 2 == 0:
                if self.syncData.current_loop == 0:
                    self.bot.get_cog('Reddit').syncRedditFeeds.start()
                for g in self.bot.guilds:
                    try:
                        await verifyLogChannel(self.bot, g)
                    except:
                        pass
            # elif self.syncData.current_loop % 3 == 0 and self.syncData.current_loop != 0:
            #     for g in self.bot.guilds:
            #         for c in g.text_channels:
            #             asyncio.create_task(self.indexChannel(c, 0.0040))
            await updateLastOnline([m for m in self.bot.get_all_members() if m.status != discord.Status.offline], discord.utils.utcnow())
            print(f'Finished everything else in {(datetime.datetime.now() - started).seconds}s')
            print(f'Garbage collection: {gc.collect()} objects')
        except Exception:
            print('Data sync error: {}'.format(traceback.format_exc()))
            traceback.print_exc()
        finally:
            await self.imageLogChannel.send(
                'Completed'
            )  # Moved this into finally so that message indexing and other bootup tasks can commence even if this fails
        print(f'Done syncing data: {(datetime.datetime.now() - rawStarted).seconds}s')

    # async def synchronizeDatabase(self, notify=False):
    #     '''This method downloads data from the database and puts it in the local mongoDB variables, then is kept updated in the motorMongo changeStream method (trackChanges)'''
    #     started = datetime.datetime.now()
    #     print('Synchronizing Database')
    #     await lightningdb.wipe()
    #     for s in self.bot.guilds:
    #         try: await lightningdb.post_server(s)
    #         except errors.DuplicateKeyError: pass
    #     for m in self.bot.get_all_members():
    #         try: await lightningdb.post_user(m)
    #         except errors.DuplicateKeyError: pass
    #     if notify: await self.imageLogChannel.send('Synchronized')
    #     print(f'Database Synchronization done in {(datetime.datetime.now() - started).seconds}s')

    @tasks.loop(hours=24)
    async def delete_message_attachments(self):
        # This becomes less relevant with attachments stored in the image log channels
        print('Deleting temp attachments')
        logger.info('Deleting temp attachments')
        time = discord.utils.utcnow()
        try:
            temp_items = await aios.listdir(TEMP_DIR)
            for item in temp_items:
                # if the item is a folder, delete the folder
                if await aios.path.isdir(os.path.join(TEMP_DIR, item)):
                    await aioshutil.rmtree(TEMP_DIR)
                # if the item is a file, delete the file
                elif await aios.path.isfile(os.path.join(TEMP_DIR, item)):
                    await aios.remove(os.path.join(TEMP_DIR, item))
            print(f'Removed temp items in {(discord.utils.utcnow() - time).seconds} seconds')
            logger.info(f'Removed temp items in {(discord.utils.utcnow() - time).seconds} seconds')
        except Exception as e:
            print(f'Temp files deletion fail: {e}')
            traceback.print_exc()
            logger.error(f'Temp files deletion fail: {e}', exc_info=True)

    async def grab_pins(self):
        """Fetches pinned messages to be stored locally"""
        for g in self.bot.guilds:
            saving_enabled = (await utility.get_server(g)).get('cyberlog', {}).get('image')
            if not saving_enabled:
                continue
            for c in g.text_channels:
                try:
                    self.pins[c.id] = [m.id for m in await c.pins()]
                except (discord.Forbidden, discord.HTTPException):
                    pass

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        pass  # But eventually add command statistics

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """[DISCORD API METHOD] Called when message is sent"""
        await self.bot.wait_until_ready()
        if not serverIsGimped(message.guild):
            await updateLastActive(message.author, discord.utils.utcnow(), 'sent a message')
        if type(message.channel) is discord.DMChannel:
            return
        if message.type is discord.MessageType.pins_add:
            await self.pinAddLogging(message)

    async def pinAddLogging(self, message: discord.Message):
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(message.guild))
        destination = await logChannel(message.guild, 'message')
        if not destination:
            return
        # These variables are explained in detail in the MessageEditHandler method
        settings = await getCyberAttributes(message.guild, 'message')
        if settings['botLogging'] == 0 and message.author.bot:
            return  # The server is set to not log actions performed by bots
        elif settings['botLogging'] == 1 and message.author.bot:
            settings['plainText'] = True  # The server is set to only use plainText logging for actions performed by bots
        pinned = (await message.channel.pins())[0]
        color = blue[await utility.color_theme(message.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
        embed = discord.Embed(
            title=f"""{(f'{self.emojis["thumbtack"]}' if settings['library'] > 0 else "📌") if settings['context'][0] > 0 else ""}{"Message was pinned" if settings['context'][0] < 2 else ''}""",
            description=textwrap.dedent(f"""
                {"👮‍♂️" if settings['context'][1] > 0 else ""}{"Pinned by" if settings['context'][1] < 2 else ""}: {message.author.mention} ({message.author.display_name})
                {(self.emojis["member"] if settings['library'] > 0 else "👤") if settings['context'][1] > 0 else ""}{"Authored by" if settings['context'][1] < 2 else ""}: {pinned.author.mention} ({pinned.author.display_name})
                {utility.channelEmoji(self, pinned.channel) if settings['context'][1] > 0 else ""}{"Channel" if settings['context'][1] < 2 else ""}: {pinned.channel.mention} {f"[{self.emojis['reply']}Jump]" if settings["context"][1] > 0 else "[Jump to message]"}({message.jump_url} 'Jump to message')
                {f"{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}" if settings['embedTimestamp'] > 1 else ''}"""),
            color=color,
        )
        if settings['embedTimestamp'] in (1, 3):
            embed.timestamp = discord.utils.utcnow()
        if any(
            a > 1 for a in (settings['thumbnail'], settings['author'])
        ):  # Moderator image saving; target doesn't apply here since the target is the pinned message
            url = await self.imageToURL(message.author.display_avatar)
            if settings['thumbnail'] > 1:
                embed.set_thumbnail(url=url)
            if settings['author'] > 1:
                embed.set_author(name=message.author.display_name, icon_url=url)
        embed.add_field(name='Message', value=utility.contentParser(pinned))
        embed.set_footer(text=f'Pinned message ID: {pinned.id}')
        for a in pinned.attachments:
            if any(w in a.filename.lower() for w in ['.png', '.jpg', '.gif', '.jpeg', '.webp']):
                savePath = f'Attachments/Temp/{a.filename}'
                await a.save(savePath)
                url = await self.uploadFiles(savePath)
                embed.set_image(url=url)
                break
        for extension in ('.png', '.jpg', '.gif', '.jpeg', '.webp'):
            if extension in pinned.content.lower() and '://' in pinned.content:
                url = pinned.content[pinned.content.find('http') : pinned.content.find(extension) + len(extension) + 1]
                embed.set_image(url=url)
                break
        plainText = f'{message.author} pinned {"this" if settings["plainText"] else "a"} message to #{pinned.channel.name}'
        m: discord.Message = await destination.send(
            content=plainText if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
            embed=embed if not settings['plainText'] else None,
            tts=settings['tts'],
        )
        await self.archiveLogEmbed(message.guild, m.id, embed, 'Message Pin')
        if any((settings['tts'], settings['flashText'])) and not settings['plainText']:
            await m.edit(content=None)
        if self.pins.get(pinned.channel.id):
            self.pins[pinned.channel.id].append(pinned.id)

        def reactionCheck(r: discord.Reaction, u: discord.User):
            return r.message.id == m.id and not u.bot

        while not self.bot.is_closed():  # This stuff has never been reliable...
            try:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
            except asyncio.TimeoutError:
                break
            if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(m.embeds) > 0:
                await m.edit(content=plainText, embed=None)
                await m.clear_reactions()
                if not settings['plainText']:
                    await m.add_reaction(self.emojis['expand'])
            elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(m.embeds) < 1:
                await m.edit(content=None, embed=embed)
                await m.clear_reactions()
                if settings['plainText']:
                    await m.add_reaction(self.emojis['collapse'])

    async def pinRemoveLogging(
        self, message: discord.Message, received: datetime.datetime, adjusted: datetime.datetime, logChannel: discord.TextChannel
    ):
        # These variables represent customization options that are used in multiple places
        # Notably: Embed data field descriptions will now need to be split up - the emoji part & the text part - since there are options to have either one or the other or both.
        # I will be multilining lots of code to account for the myriad of new customization settings - for organization purposes which I'll definitely need later
        # V1.0: Consider splitting the unpin stuff into its own method; the message edit handler here is a bit long
        settings = await getCyberAttributes(message.guild, 'message')
        color = blue[await utility.color_theme(message.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
        content = f'Someone unpinned a message from #{message.channel.name}'
        embed = discord.Embed(
            title=f"""{(f'{self.emojis["thumbtack"]}❌' if settings['library'] > 0 else "📌❌") if settings['context'][0] > 0 else ""}{"Message was unpinned" if settings['context'][0] < 2 else ""}""",
            description='',
            color=color,
        )
        if await readPerms(message.guild, 'message'):
            try:
                log = await message.guild.audit_logs().get(action=discord.AuditLogAction.message_pin)
                if settings['botLogging'] == 0 and log.user.bot:
                    return
                elif settings['botLogging'] == 1 and log.user.bot:
                    settings['plainText'] = True
                embed.description += f'{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Unpinned by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name})'
                if settings['thumbnail'] > 1 or settings['author'] > 1:
                    url = await self.imageToURL(log.user.display_avatar)
                    if settings['thumbnail'] > 1:
                        embed.set_thumbnail(url=url)
                    if settings['author'] > 1:
                        embed.set_author(name=log.user.display_name, icon_url=url)
                content = f'{log.user} unpinned a message from #{message.channel.name}'
                if message.guild.id not in gimpedServers:
                    await updateLastActive(log.user, discord.utils.utcnow(), 'unpinned a message')
            except:
                pass  # the message on audit log fails will be phased out by permissions showing on the dashboard. this also allows us to swallow conditions when we may fail to retrieve the audit log
        embed.description += (
            textwrap.dedent(f"""
            {(self.emojis["member"] if settings["library"] > 0 else "👤") if settings["context"][1] > 0 else ""}{"Authored by" if settings["context"][1] < 2 else ""}: {message.author.mention} ({message.author.display_name})
            {utility.channelEmoji(self, message.channel) if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {message.channel.mention} {f"[{self.emojis['reply']}Jump]" if settings["context"][1] > 0 else "[Jump to message]"}({message.jump_url} 'Jump to message')
            {f"{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}" if settings['embedTimestamp'] > 1 else ''}"""),
        )
        if settings['embedTimestamp'] in (1, 3):
            embed.timestamp = discord.utils.utcnow()
        embed.add_field(name='Message', value=utility.contentParser(message))
        embed.set_footer(text=f'Unpinned message ID: {message.id}')
        for a in message.attachments:
            if any(w in a.filename.lower() for w in ['.png', '.jpg', '.gif', '.jpeg', '.webp']):
                savePath = f'Attachments/Temp/{a.filename}'
                await a.save(savePath)
                url = await self.uploadFiles(savePath)
                embed.set_image(url=url)
                break
        # Sometime, learn regex to possibly improve the efficiency of this stuff, especially when the antispam module is redone
        for extension in ('.png', '.jpg', '.gif', '.jpeg', '.webp'):
            if extension in message.content.lower() and '://' in message.content:
                url = message.content[message.content.find('http') : message.content.find(extension) + len(extension) + 1]
                embed.set_image(url=url)
                break
        msg: discord.Message = await logChannel.send(
            content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
            embed=embed if not settings['plainText'] else None,
            tts=settings['tts'],
        )
        if any((settings['tts'], settings['flashText'])) and not settings['plainText']:
            await msg.edit(content=None)
        if self.pins.get(message.channel.id):
            self.pins[message.channel.id].remove(message.id)

        def reactionCheck(r: discord.Reaction, u: discord.User):
            return r.message.id == msg.id and not u.bot

        while not self.bot.is_closed():
            try:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
            except asyncio.TimeoutError:
                break
            if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                await msg.edit(content=content, embed=None)
                await msg.clear_reactions()
                if not settings['plainText']:
                    await msg.add_reaction(self.emojis['expand'])
            elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']) and len(msg.embeds) < 1:
                await msg.edit(content=None, embed=embed)
                await msg.clear_reactions()
                if settings['plainText']:
                    await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, p: discord.RawReactionActionEvent):
        """Discord.py event listener: When a reaction is added to a message"""
        # Layer style: Message ID > User ID > Reaction (emoji)
        u = self.bot.get_user(p.user_id)
        if not u:
            return
        if not serverIsGimped(self.bot.get_guild(p.guild_id)):
            await updateLastActive(u, discord.utils.utcnow(), 'added a reaction')
        if u.bot:
            return
        g = self.bot.get_guild(p.guild_id)
        if not g:
            return
        m = p.message_id

        # embed suppression handling
        server_settings = await utility.get_server(g)
        if server_settings['undoSuppression']:
            if p.emoji == self.emojis['expand'] and utility.ManageServer(u):
                message = await g.get_channel(p.channel_id).fetch_message(m)
                await message.edit(suppress=False)
                for r in message.reactions:
                    if r.emoji == self.emojis['expand']:
                        return await r.clear()

        # ghost reaction handling
        if self.reactions:
            layerObject = self.reactions
        else:
            layerObject = collections.defaultdict(lambda: collections.defaultdict(dict))
        layerObject[m][u.id][p.emoji.name] = {'timestamp': discord.utils.utcnow(), 'guild': g.id}
        self.reactions = layerObject
        sleepTime = (await utility.get_server(g))['cyberlog']['ghostReactionTime']
        await asyncio.sleep(sleepTime)
        try:
            layerObject[m][u.id].remove(p.emoji.name)
        except:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, p: discord.RawReactionActionEvent):
        """Discord.py event listener: When a reaction is removed from a message"""
        u = self.bot.get_user(p.user_id)
        if not u:
            return
        if not serverIsGimped(self.bot.get_guild(p.guild_id)):
            await updateLastActive(u, discord.utils.utcnow(), 'removed a reaction')
        if u.bot:
            return
        g = self.bot.get_guild(p.guild_id)
        if not g:
            return
        m = p.message_id
        c: discord.TextChannel = self.bot.get_channel(p.channel_id)
        try:
            layerObject = self.reactions[m][u.id][p.emoji.name]
            if not layerObject:
                return
        except KeyError:
            return
        seconds = (discord.utils.utcnow() - layerObject['timestamp']).seconds
        if seconds < (await utility.get_server(g))['cyberlog']['ghostReactionTime']:
            settings = await getCyberAttributes(g, 'misc')
            received = discord.utils.utcnow()
            adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(g))
            color = blue[await utility.color_theme(g)] if settings['color'][1] == 'auto' else settings['color'][1]
            result = await c.fetch_message(m)
            if result.author.id == self.bot.user.id:
                return
            rawEmoji = emojis.decode(
                p.emoji.name
            ).replace(
                ':', ''
            )  # Use the python Emojis module to get the name of an emoji - remove the colons so it doesn't get embedded into Discord. Only applies to unicode emojis.
            content = f'{u} removed the {rawEmoji} reaction from their message in #{c.name} {seconds} seconds after adding it'  # There is a zero-width space in this line, after the first colon
            emojiLine = f'{self.emojis["emoji"] if settings["context"][1] > 0 else ""}{"Reaction" if settings["context"][1] < 2 else ""}: {p.emoji} ({rawEmoji})'
            userLine = f'{(self.emojis["member"] if settings["library"] > 0 else "👤") if settings["context"][1] > 0 else ""}{"Member" if settings["context"][1] < 2 else ""}: {u.mention} ({u.display_name})'
            channelLine = f"""{self.emojis["textChannel"] if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {c.mention} ({c.name}) {f'{self.emojis["reply"]}[Jump]({result.jump_url})' if result else ""}"""
            ghostTimeLine = f'{self.emojis["slowmode"] if settings["context"][1] > 0 else ""}{"Timespan" if settings["context"][1] < 2 else ""}: Removed {seconds}s after being added'
            timeLine = f'{(utility.clockEmoji(adjusted) if settings["library"] > 0 else "🕰") if settings["context"][1] > 0 else ""}{"Timestamp" if settings["context"][1] < 2 else ""}: {utility.DisguardLongTimestamp(received)}'
            embed = discord.Embed(
                title=f"""{f'{self.emojis["emoji"]}👻' if settings["context"][0] > 0 else ""}{"Ghost message reaction" if settings["context"][0] < 2 else ""}""",
                description=f'{content}\n\n{emojiLine}\n{ghostTimeLine}\n{userLine}\n{channelLine}\n{timeLine if settings["embedTimestamp"] > 1 else ""}',
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text=f'Message ID: {m}')
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                url = await self.imageToURL(u.display_avatar)
                if settings['thumbnail'] in (1, 2, 4):
                    embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4):
                    embed.set_author(name=u.display_name, icon_url=url)
            try:
                message = await (await logChannel(g, 'misc')).send(
                    content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                    embed=embed if not settings['plainText'] else None,
                    tts=settings['tts'],
                )
                if not settings['plainText']:
                    await message.edit(embed=embed)
                await self.archiveLogEmbed(g, message.id, embed, 'Ghost Reaction Remove')
            except:
                pass
            try:
                layerObject[m][u.id].remove(p.emoji.name)
            except:
                pass

    def parse_edits(self, before_words: list[str], after_words: list[str], context: int = 2):
        """
        Returns truncated differences between two strings, showing only content around the changes.

        Args:
            before (str): The original string.
            after (str): The modified string.
            context (int): Number of words to include around the differences for context.

        Returns:
            tuple: A tuple containing the truncated 'before' and 'after' strings with differences highlighted.
        """
        matcher = difflib.SequenceMatcher(None, before_words, after_words)

        before_result = []
        after_result = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Include context words around changes
                if len(before_result) > 0:
                    before_result.extend(before_words[i1 : i1 + context])
                    after_result.extend(after_words[j1 : j1 + context])
            elif tag in ('replace', 'delete', 'insert'):
                # Highlight differences
                before_result.extend(before_words[max(0, i1 - context) : i1])
                after_result.extend(after_words[max(0, j1 - context) : j1])

                before_result.extend(f'**{word}**' for word in before_words[i1:i2])
                after_result.extend(f'**{word}**' for word in after_words[j1:j2])

                before_result.extend(before_words[i2 : i2 + context])
                after_result.extend(after_words[j2 : j2 + context])

        return ' '.join(before_result), ' '.join(after_result)

    async def message_edit_handler(self, before: str | discord.Message, after: discord.Message, timestamp: datetime.datetime):
        # Variables to hold essential data
        guild = after.guild
        # author = after.author
        # channel = after.channel
        # b4 = None
        bot_ignore = False
        log_channel = await logChannel(guild, 'message')
        settings = await getCyberAttributes(guild, 'message')
        server_settings = await utility.get_server(guild)
        bot_author_settings = server_settings.get('cyberlog', {}).get('messageLogsBotAuthor', 0)
        received = discord.utils.utcnow()
        tz_adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(guild))
        color = blue[await utility.color_theme(guild)] if settings['color'][1] == 'auto' else settings['color'][1]
        before_is_message = False
        if not log_channel:
            return  # Invalid log channel or bot logging is disabled
        if bot_author_settings == 0 and after.author.bot:
            bot_ignore = True
        elif bot_author_settings == 1 and after.author.bot:
            settings['plainText'] = True
        if type(before) is discord.Message:
            before_is_message = True
            before_content = before.content
        else:
            before_content = before
        if after.id in self.pins.get(after.channel.id, []) and not after.pinned and not bot_ignore:  # Message was unpinned
            await self.pinRemoveLogging(after, received, tz_adjusted, log_channel)
        elif before_is_message and not before.flags.suppress_embeds and after.flags.suppress_embeds and server_settings['undoSuppression']:
            await after.add_reaction(self.emojis['expand'])
            return
            # code to re-expand message has been moved to on_raw_reaction_add
        if bot_ignore or after.author.id == self.bot.user.id:
            # return if bot edited its own message
            return
        attachments = []
        embed = discord.Embed(
            title=f"""{(self.emojis['messageEdit'] if settings['library'] > 1 else "📜✏") if settings['context'][0] > 0 else ''}{"Message edited" if settings['context'][0] < 2 else ""}""",
            description='',
            color=color,
        )
        embed.description = f"""
            {(self.emojis["member"] if settings["library"] > 0 else "👤") if settings["context"][1] > 0 else ""}{"Author" if settings["context"][1] < 2 else ""}: {after.author.mention} ({after.author.display_name})
            {utility.channelEmoji(self, after.channel) if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {after.channel.mention} {f"[{self.emojis['reply']}Jump]" if settings["context"][1] > 0 else "[Jump to message]"}({after.jump_url} 'Jump to message')
            {f"{(utility.clockEmoji(timestamp) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}" if settings['embedTimestamp'] > 1 else ''}
            """

        if after.content.strip() != before_content.strip():
            before_words = before_content.split(' ')  # A list of words in the old message
            after_words = after.content.split(' ')  # A list of words in the new message
            before_parsed, after_parsed = self.parse_edits(before_words, after_words, 2)
            # will be passed to the next view/button for simple view swapping

            outputs = {'compressed': {'before': before_parsed, 'after': after_parsed}, 'full': {'before': before_content, 'after': after.content}}

            # set embed display based on the length of before/after

            room_to_grow = 4096 - len(embed.description)
            if 1024 <= len(before_parsed) < room_to_grow:
                embed.description += (
                    f'{self.emojis["before"] if settings["context"][1] > 0 and settings["library"] == 2 else ""} **Before**:\n{before_parsed}\n'
                )
                room_to_grow = 4096 - len(embed.description)
            else:
                if 0 <= len(before_parsed) < 1024:
                    before_display = before_parsed
                else:
                    # I'd be amazed if this ever happens, but just in case
                    before_display = '<Content too long to display. Use the buttons below to view the full content>'
                embed.add_field(
                    name=f'{self.emojis["before"] if settings["context"][1] > 0 and settings["library"] == 2 else ""}Before',
                    value=before_display,
                    inline=False,
                )
            if 1024 <= len(after_parsed) < room_to_grow:
                embed.description += (
                    f'{self.emojis["after"] if settings["context"][1] > 0 and settings["library"] == 2 else ""} **After**:\n{after_parsed}\n'
                )
            else:
                if 0 <= len(after_parsed) < 1024:
                    after_display = after_parsed
                else:
                    # I'd be amazed if this ever happens, but just in case
                    after_display = '<Content too long to display. Use the buttons below to view the full content>'
                embed.add_field(
                    name=f'{self.emojis["after"] if settings["context"][1] > 0 and settings["library"] == 2 else ""}After',
                    value=after_display,
                    inline=False,
                )
        if before_is_message and before.attachments != after.attachments:
            # get attachments that aren't in both before & after
            removed_attachments = list(set(after.attachments) - set(before.attachments))
            added_attachments = list(set(before.attachments) - set(after.attachments))
            unique_attachments = removed_attachments + added_attachments
            embed.add_field(
                name=f'{self.emojis["details"] if settings["context"][1] > 0 else ""}Attachments changed',
                value='\n'.join(f'{"-" if a in removed_attachments else "+"} {a.filename}' for a in unique_attachments),
                inline=False,
            )
            # update indexes
        if before_is_message and before.flags != after.flags:
            if before.flags.crossposted != after.flags.crossposted:
                embed.add_field(
                    name=f'{self.emojis["details"] if settings["context"][1] > 0 else ""}Crosspost status changed',
                    value='This message was crossposted somewhere' if after.flags.crossposted else "This message's crosspost was removed",
                    inline=False,
                )
            if before.flags.source_message_deleted != after.flags.source_message_deleted:
                embed.add_field(
                    name=f'{self.emojis["details"] if settings["context"][1] > 0 else ""}Dangling message reference',
                    value='The original message that this message refers to was deleted'
                    if after.flags.source_message_deleted
                    else "This message's original source message was undeleted... is that even logically possible?",
                    inline=False,
                )
            if before.flags.has_thread != after.flags.has_thread:
                embed.add_field(
                    name=f'{self.emojis["details"] if settings["context"][1] > 0 else ""}Thread status changed',
                    value='This message is now in a thread' if after.flags.has_thread else 'This message is no longer in a thread',
                    inline=False,
                )
        if settings['embedTimestamp'] in (1, 3):
            embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f'Message ID: {after.id}')
        if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
            image_path = await self.image_to_local_attachment(after.author.display_avatar)
            attachments.append(image_path)
            if settings['thumbnail'] in (1, 2, 4):
                embed.set_thumbnail(url=f'attachment://{os.path.basename(image_path)}')
            if settings['author'] in (1, 2, 4):
                embed.set_author(name=after.author.display_name, icon_url=f'attachment://{os.path.basename(image_path)}')
        indexing_cog: Indexing.Indexing = self.bot.get_cog('Indexing')
        new_edition = await indexing_cog.edition_from_message(after)
        await lightningdb.patch_message_2024(after.channel.id, after.id, new_edition)
        plainText = f"""{after.author} edited {"this" if settings["plainText"] else "a"} message\nBefore:`{before_content if len(before_content) < 1000 else '<content too long>'}`\nAfter:`{after.content if len(after.content) < 1024 else '<content too long>'}\n`{after.jump_url}"""

        view = self.MessageEditMenu(self, self.bot, settings, before_content, after, outputs, embed)
        try:
            msg: discord.Message = await log_channel.send(
                content=plainText if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
                files=[discord.File(attachment) for attachment in attachments],
                view=view,
            )
            if not settings['plainText']:
                ...
                # modal
        except discord.HTTPException as e:
            logger.error(f'Failed to send message edit log: {e}', exc_info=True)
        await msg.edit(
            content=None if any((settings['tts'], settings['flashText'])) and not settings['plainText'] else msg.content,
            embed=None if settings['plainText'] else embed,
        )
        await self.archiveLogEmbed(after.guild, msg.id, embed, 'Message Edit')
        if not serverIsGimped(guild):
            await updateLastActive(after.author, discord.utils.utcnow(), 'edited a message')
        return
        #         elif str(result[0]) == '📜':
        #             try:
        #                 await msg.clear_reactions()
        #                 embed.clear_fields()
        #                 embed.description = (
        #                     embed.description[
        #                         : embed.description.find(utility.DisguardLongTimestamp(received)) + len(utility.DisguardLongTimestamp(received))
        #                     ]
        #                     + f'\n\nNAVIGATION\n{qlf}⬅: Go back to compressed view\n{qlf}ℹ: Full edited message\n> **📜: Message edit history**\n{qlf}🗒: Message in context'
        #                 )
        #                 message_data = await lightningdb.get_message(after.channel.id, after.id)
        #                 editions = message_data['editions']

        #                 for i, entry in enumerate(editions):
        #                     embed.add_field(
        #                         name=f'{utility.DisguardLongTimestamp(datetime.datetime.fromisoformat(entry["timestamp"]))}{" (Created)" if i == 0 else " (Current)" if i == len(editions) - 1 else ""}',
        #                         value=entry['content'],
        #                         inline=False,
        #                     )
        #                 await msg.edit(embed=embed)
        #                 for r in ['⬅', 'ℹ', '🗒']:
        #                     await msg.add_reaction(r)
        #             except (discord.Forbidden, discord.HTTPException) as e:
        #                 embed.description += f'\n\n⚠ Error parsing message edit history: {e}'
        #                 await msg.edit(embed=embed)
        #                 await asyncio.sleep(5)
        #         elif str(result[0]) == '🗒':
        #             try:
        #                 embed.clear_fields()
        #                 embed.description = (
        #                     embed.description[
        #                         : embed.description.find(utility.DisguardLongTimestamp(received)) + len({utility.DisguardLongTimestamp(received)})
        #                     ]
        #                     + f'\n\nNAVIGATION\n{qlf}⬅: Go back to compressed view\n{qlf}ℹ: Full edited message\n{qlf}📜: Message edit history\n> **🗒: Message in context**'
        #                 )
        #                 messagesBefore = list(reversed([message async for message in after.channel.history(limit=6, before=after)]))
        #                 messagesAfter = [message async for message in after.channel.history(limit=6, after=after, oldest_first=True)]
        #                 combinedMessages = messagesBefore + [after] + messagesAfter
        #                 combinedLength = sum(len(m.content) for m in combinedMessages)
        #                 if combinedLength > 1850:
        #                     combinedMessageContent = [utility.contentParser(m)[: 1850 // len(combinedMessages)] for m in combinedMessages]
        #                 else:
        #                     combinedMessageContent = [utility.contentParser(m) for m in combinedMessages]
        #                 for m in range(len(combinedMessages)):
        #                     embed.add_field(
        #                         name=f'**{combinedMessages[m].author.name}** • {utility.DisguardLongTimestamp(combinedMessages[m].created_at + datetime.timedelta(hours=await utility.time_zone(guild)))}',
        #                         value=combinedMessageContent[m]
        #                         if combinedMessages[m].id != after.id
        #                         else f'**[{combinedMessageContent[m]}]({combinedMessages[m].jump_url})**',
        #                         inline=False,
        #                     )
        #                 await msg.edit(embed=embed)
        #                 for r in ['⬅', 'ℹ', '📜']:
        #                     await msg.add_reaction(r)
        #             except (discord.Forbidden, discord.HTTPException) as e:
        #                 embed.description += f'\n\n⚠ Error retrieving messages: {e}'
        #                 await msg.edit(embed=embed)
        #                 await asyncio.sleep(5)
        #         elif str(result[0]) == '⬅':
        #             await msg.clear_reactions()
        #             await msg.edit(content=oldContent if settings['plainText'] else None, embed=oldEmbed if not settings['plainText'] else None)
        #             embed = copy.deepcopy(oldEmbed)
        #             if not settings['plainText']:
        #                 await msg.add_reaction(self.emojis['threeDots'])
        #             break
        #         result = None
        # elif result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎'):
        #     await msg.edit(content=plainText, embed=None)
        #     await msg.clear_reactions()

    class MessageEditMenu(discord.ui.View):
        def __init__(
            self,
            cyberlog,
            bot: commands.Bot,
            settings: dict,
            before_content: str,
            after: discord.Message,
            outputs: dict[str, dict[str, str]],
            og_embed: discord.Embed,
        ):
            super().__init__(timeout=180)
            self.cyberlog: Cyberlog = cyberlog
            self.bot = bot
            self.settings = settings
            self.before_content = before_content
            self.after = after
            self.outputs = outputs
            self.og_embed = og_embed
            self.back_button = self.cyberlog.BackToMessageEditMenuButton(self, og_embed)

        @discord.ui.button(label='Expand before & after', style=discord.ButtonStyle.secondary)
        async def expand_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
            if 'Collapse' in button.label:
                button.label = 'Expand before & after'
                return await interaction.response.edit_message(content=None, embed=self.og_embed, view=self)
            await interaction.response.defer()
            after_content = self.after.content
            self.new_embed = copy.deepcopy(self.og_embed)
            self.new_embed.clear_fields()
            self.new_embed.description = ''
            using_paginated_view = False
            description_length = 0
            if 0 <= len(self.before_content) < 1024:
                self.new_embed.add_field(
                    name=f'{self.bot.emojis["before"] if self.settings["context"][1] > 0 and self.settings["library"] == 2 else ""}Before',
                    value=self.before_content,
                    inline=False,
                )
            else:
                self.new_embed.description += f'{self.cyberlog.emojis["before"] if self.settings["context"][1] > 0 and self.settings["library"] == 2 else ""} **Before**:\n{self.before_content}\n'
                description_length += len(self.new_embed.description)
            if 0 <= len(after_content) < 1024:
                self.new_embed.add_field(
                    name=f'{self.bot.emojis["after"] if self.settings["context"][1] > 0 and self.settings["library"] == 2 else ""}After',
                    value=self.after.content,
                    inline=False,
                )
            else:
                if len(after_content) > (4096 - description_length):
                    using_paginated_view = True
                    self.new_embed.clear_fields()
                    # ignore next branch
                else:
                    self.new_embed.description += f'{self.bot.emojis["after"] if self.settings["context"][1] > 0 and self.settings["library"] == 2 else ""} **After**:\n{after_content}\n'
            if not using_paginated_view:
                button.label = 'Collapse before & after'
                await interaction.followup.edit_message(message_id=interaction.message.id, view=self, embed=self.new_embed)
            else:
                await interaction.response.edit_message(
                    message_id=interaction.message.id,
                    embed=self.new_embed,
                    view=Cyberlog.ExpandedMessageEditMenu(self.back_button, self.before_content, after_content, self),
                )

        @discord.ui.button(label='View edit history', style=discord.ButtonStyle.secondary)
        async def view_edit_history(self, interaction: discord.Interaction, button: discord.ui.Button): ...

        @discord.ui.button(label='View index file & attachments', style=discord.ButtonStyle.secondary)
        async def view_index_file(self, interaction: discord.Interaction, button: discord.ui.Button):
            ...
            # combine with message info

    class BackToMessageEditMenuButton(discord.ui.Button):
        def __init__(self, prev_view, embed: discord.Embed):
            super().__init__(label='Back', style=discord.ButtonStyle.primary)
            self.prev_view: Cyberlog.MessageEditMenu = prev_view
            self.embed = embed

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.edit_message(content=None, embed=self.embed, view=self.prev_view)

    class ExpandedMessageEditMenu(discord.ui.View):
        def __init__(self, back_button, before_content: str, after_content: str, previous_view: discord.ui.View):
            super().__init__(timeout=180)
            self.add_item(back_button)
            self.before_content = before_content
            self.after_content = after_content
            self.previous_view: Cyberlog.MessageEditMenu = previous_view
            self.showing_before = True

        @discord.ui.button(label='Show after', style=discord.ButtonStyle.secondary)
        async def show_after(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.showing_before:
                self.showing_before = False
                button.label = 'Show before'
                self.previous_view.new_embed.description = f'{self.previous_view.cyberlog.emojis["before"] if self.previous_view.settings["context"][1] > 0 and self.previous_view.settings["library"] == 2 else ""} **Before**:\n{self.before_content}\n'
                await interaction.response.edit_message(embed=self.previous_view.new_embed, view=self)
            else:
                self.showing_before = True
                button.label = 'Show after'
                self.previous_view.new_embed.description = f'{self.previous_view.cyberlog.emojis["after"] if self.previous_view.settings["context"][1] > 0 and self.previous_view.settings["library"] == 2 else ""} **After**:\n{self.after_content}\n'
                await interaction.response.edit_message(embed=self.previous_view.new_embed, view=self)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """[DISCORD API METHOD] Called when message is edited"""
        if not after.guild:
            return  # We don't deal with DMs
        received = discord.utils.utcnow() + datetime.timedelta(
            hours=await utility.time_zone(after.guild)
        )  # Timestamp of receiving the message edit event
        if after.guild.id not in gimpedServers:
            update_last_active_task = asyncio.create_task(
                updateLastActive(after.author, discord.utils.utcnow(), 'edited a message'), name='message_edit - Update Last Active'
            )
        g = after.guild
        if not (await logEnabled(g, 'message')):
            await utility.await_task(update_last_active_task)  # Wait for the task to finish if it was created
            return  # If the message edit log module is not enabled, return
        try:
            if not await logExclusions(after.channel, after.author):
                await utility.await_task(update_last_active_task)
                return  # Check the exclusion settings
        except:
            print('log exclusion error')
            traceback.print_exc()
            await utility.await_task(update_last_active_task)
            return
        await self.message_edit_handler(before, after, received)
        try:
            await utility.await_task(update_last_active_task)  # Wait for the task to finish if it was created
        except (asyncio.CancelledError, UnboundLocalError):
            pass

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        """[DISCORD API METHOD] Called when raw message is edited"""
        try:
            g = self.bot.get_guild(int(payload.data.get('guild_id')))  # Get the server of the edited message
        except:
            return  # We don't deal with DMs
        received = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(g))  # Timestamp of receiving the message edit event
        before = ''
        if payload.cached_message:
            return  # If the message is stored internally (created after bot restart), it will get dealt with above, where searching the local indexes isn't necessary
        channel = self.bot.get_channel(int(payload.data.get('channel_id')))  # Get the channel of the edited message
        try:
            after = await channel.fetch_message(payload.message_id)  # Get the message object, and return if not found
        except discord.NotFound:
            return
        except discord.Forbidden:
            print('{} lacks permissions for message edit for some reason'.format(g.name))
            return
        author = g.get_member(after.author.id)  # Get the member of the edited message
        if g.id not in gimpedServers:
            update_last_active_task = asyncio.create_task(
                updateLastActive(author, discord.utils.utcnow(), 'edited a message'), name='raw_message_edit - Update Last Active'
            )
        if not (await logEnabled(g, 'message')):
            await utility.await_task(update_last_active_task)
            return  # If the message edit log module is not enabled, return
        try:
            if not await logExclusions(after.channel, author):
                await utility.await_task(update_last_active_task)
                return  # Check the exclusion settings
        except:
            print('log exclusion error')
            traceback.print_exc()
            await utility.await_task(update_last_active_task)
            return
        c = await logChannel(g, 'message')
        if c is None:
            await utility.await_task(update_last_active_task)
            return  # Invalid log channel
        message_data = await lightningdb.get_message(channel.id, after.id)
        if message_data:
            try:
                before = message_data['editions'][-2]['content']
            except IndexError:
                before = after.content
        else:
            before = after.content
        try:
            await self.message_edit_handler(before, after, received)
        except UnboundLocalError:
            await self.message_edit_handler('<Data retrieval error>', after, received)  # If before doesn't exist
        await utility.await_task(update_last_active_task)  # Wait for the task to finish if it was created

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """[DISCORD API METHOD] Called when message is deleted (RAW CONTENT)"""
        g = self.bot.get_guild(payload.guild_id)
        if not g:
            return  # We don't deal with DM message deletions
        received = discord.utils.utcnow()
        if serverPurge.get(payload.guild_id):
            return
        if not await logEnabled(g, 'message'):
            return
        try:
            message = payload.cached_message
            # if message.type in [discord.MessageType.pins_add]:
            #     return  # don't log
        except AttributeError:
            message = None

        def reactionCheck(r: discord.Reaction, u: discord.User):
            return r.message.id == msg.id and not u.bot

        c = await logChannel(g, 'message')
        settings = await getCyberAttributes(g, 'message')
        fileError = ''
        color = red[await utility.color_theme(g)] if settings['color'][2] == 'auto' else settings['color'][2]
        if payload.message_id in self.pauseDelete:
            return self.pauseDelete.remove(payload.message_id)
        embed = discord.Embed(
            title=f"""{(f'{self.emojis["messageDelete"] if settings["library"] > 1 else "📜" + str(self.emojis["delete"])}') if settings["context"][0] > 0 else ""}{" Message was deleted" if settings["context"][0] < 2 else ""}""",
            description='',
            color=color,
        )
        if settings['embedTimestamp'] in (1, 3):
            embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f'Message ID: {payload.message_id}')
        cyber = (await utility.get_server(g)).get('cyberlog')
        attachments = []  # List of files to be sent with this message
        # Retrieve this message index & export it to a JSON
        message_data = await lightningdb.get_message(payload.channel_id, payload.message_id)
        index_path = f'storage/temp/index_{payload.message_id}.json'
        if message_data:
            try:
                with open(index_path, 'w') as json_file:
                    json.dump(message_data, json_file, indent=4)
                    if cyber.get('sendIndexFile'):
                        attachments.append(index_path)
            except Exception:
                logger.error(f'Error writing message index to {index_path}', exc_info=True)

        attachments_path = f'storage/{g.id}/attachments/{payload.channel_id}/{payload.message_id}'  # Where to retrieve message attachments from

        try:
            for file in await aios.listdir(attachments_path):
                savePath = f'{attachments_path}/{file}'
                attachments.append(savePath)

                if any([ext in file.lower() for ext in ['.png', '.jpeg', '.jpg', '.gif', '.webp']]) and utility.empty(embed.image.url):
                    embed.set_image(url=f'attachment://{file}')

                # except discord.HTTPException:
                #     fileError += f"\n{self.emojis['alert']} | This message's attachment ({directory}) is too large to be sent ({round(os.stat(savePath).st_size / 1000000, 2)}mb). Please view [this page](https://disguard.netlify.app/privacy.html#appendixF) for more information including file retrieval."
        except FileNotFoundError:
            # this message has no attachments; path does not exist
            pass
        if message:
            author = message.author
            if not author:
                author = await self.bot.fetch_user(message.author.id)
            channel, created, content = message.channel, message.created_at, message.content
        else:
            try:
                author, channel, created = (
                    await self.bot.fetch_user(message_data['author_id']),
                    self.bot.get_channel(payload.channel_id),
                    datetime.datetime.fromtimestamp(message_data['created_at'], tz=discord.utils.utcnow().tzinfo),
                )
                await lightningdb.delete_message(payload.channel_id, payload.message_id)
            except (KeyError, IndexError):
                try:
                    channel = channel.mention
                except UnboundLocalError:
                    channel = self.bot.get_channel(payload.channel_id)
                    if not channel:
                        channel = payload.channel_id
                embed.description = f'{self.emojis["textChannel"] if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {channel}\n\nError retrieving further information'
                plainText = f"""Somebody deleted their message in #{channel}\n\nUnable to provide more information about this event"""
                msg: discord.Message = await c.send(
                    content=plainText if 'too large' in plainText or any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                    embed=embed if not settings['plainText'] else None,
                    tts=settings['tts'],
                    files=[discord.File(attachment) for attachment in attachments] if attachments else None,
                )
                if any((settings['tts'], settings['flashText'])) and not settings['plainText']:
                    await msg.edit(content=None)
                return
        log_bot_author = cyber.get('messageLogsBotAuthor')
        if log_bot_author == 1 and author.bot:
            settings['plainText'] = True
        if discord.utils.utcnow() > created:
            mult = 1
        else:
            mult = -1  # This makes negative time rather than posting some super weird timestamps. No, negative time doesn't exist but it makes more sense than what this would do otherwise
        deletedAfter: datetime.datetime = abs(created - discord.utils.utcnow())
        hours, minutes, seconds = (
            deletedAfter.seconds // 3600,
            (deletedAfter.seconds // 60) % 60,
            deletedAfter.seconds - (deletedAfter.seconds // 3600) * 3600 - ((deletedAfter.seconds // 60) % 60) * 60,
        )
        times = [
            seconds * mult,
            minutes * mult,
            hours * mult,
            deletedAfter.days * mult,
        ]  # This is the list of units for the deletedAfter. Because of potential negative values, use this code instead of the utility function
        units = ['second', 'minute', 'hour', 'day']  # Full words, but we'll only be using the first letter in the final result
        display = []  # This will be joined in the embed to combine the units and values
        for i in range(len(times)):
            if times[i] != 0:
                display.append(
                    '{}{}'.format(times[i], units[i][0])
                )  # The if statement will not append units if everything to the right is 0 (such as 5 seconds later, where m/h/d would all be 0)
        if len(display) == 0:
            display.append(f'{deletedAfter.microseconds // 1000}ms')
        try:
            memberObject = g.get_member(author.id)
        except AttributeError:
            return
        try:
            if author.bot and author.id == self.bot.user.id:
                p = f'storage/{g.id}/misc/modLogs.json'
                async with aiofiles.open(p) as f:
                    try:
                        content = await f.read()
                        logArchives = json.loads(content)
                    except:
                        logArchives = {}
                if payload.message_id in [int(k) for k in logArchives.keys()]:
                    await self.updateLogEmbed(g, payload.message_id, {'customKeyMessageIsDeleted': True})
            if (author.bot and not (await utility.get_server(g))['cyberlog'].get('disguardLogRecursion')) or not await logExclusions(
                channel, memberObject
            ):
                return
        except:
            pass
        try:
            messageAfter = [message async for message in channel.history(limit=1, after=created, oldest_first=True)][
                0
            ]  # The message directly after the deleted one, if this is N/A the embed will have no hyperlink for this
        except IndexError:
            messageAfter = ''
        try:
            messageBefore = [message async for message in channel.history(limit=1, before=created)][0]  # The message directly before the deleted one
        except IndexError:
            messageBefore = ''
        created -= datetime.timedelta(hours=DST)
        embed.description = textwrap.dedent(f"""
            {(self.emojis["member"] if settings["library"] > 0 else "👤") if settings["context"][1] > 0 else ""}{" Authored by" if settings["context"][1] < 2 else ""}: {author.mention} ({author.display_name}){' (No longer here)' if not memberObject else ''}
            {utility.channelEmoji(self, channel) if settings["context"][1] > 0 else ""}{" Channel" if settings["context"][1] < 2 else ""}: {channel.mention} • Jump to [previous]({messageBefore.jump_url if messageBefore else ''}) or [next]({messageAfter.jump_url if messageAfter else ''}) message
            {self.emojis['sendMessage'] if settings["context"][1] > 0 else ""}{" Sent" if settings["context"][1] < 2 else ""}: {utility.DisguardLongTimestamp(created)}
            {self.emojis['delete'] if settings["context"][1] > 0 else ""}{" Deleted" if settings["context"][1] < 2 else ""}: {utility.DisguardLongTimestamp(received)} ({' '.join(reversed(display))} later)""")
        if message:
            embed.add_field(name='Content', value=message.content[:1024] if len(message.content) > 0 else utility.contentParser(message))
        else:
            content = message_data['editions'][-1]['content']
            embed.add_field(name='Content', value='<No content. Review attached message index for more details>' if not content else content[:1024])
        # Regex pattern to match image URLs
        image_url_pattern = r'(https?://[^\s]+?\.(?:png|jpg|jpeg|gif|webp))'
        matches = re.findall(image_url_pattern, content)
        if matches:
            embed.set_image(url=matches[0])
        if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
            image_path = await self.image_to_local_attachment(author.display_avatar)
            attachments.append(image_path)
            if settings['thumbnail'] in (1, 2, 4):
                embed.set_thumbnail(url=f'attachment://{os.path.basename(image_path)}')
            if settings['author'] in (1, 2, 4):
                embed.set_author(name=author.display_name, icon_url=f'attachment://{os.path.basename(image_path)}')
        modDelete = False
        plainText = ''
        log = None
        if await readPerms(g, 'message'):
            try:
                log = [a_log async for a_log in g.audit_logs(limit=1)][0]
                if (
                    log.action in (discord.AuditLogAction.message_delete, discord.AuditLogAction.message_bulk_delete)
                    and utility.absTime(discord.utils.utcnow(), log.created_at, datetime.timedelta(seconds=5))
                    and log.target.id in (author.id, channel.id)
                    and log.user != author
                ):
                    embed.description += f"""\n{(f'{self.emojis["modDelete"]}👮‍♂️') if settings['context'][1] > 0 else ''}{" Deleted by" if settings['context'][1] < 2 else ""}: {log.user.mention} ({log.user.display_name})"""
                    embed.title = f"""{(f'{self.emojis["messageDelete"] if settings["library"] > 1 else "📜" + str(self.emojis["modDelete"])}') if settings["context"][0] > 0 else ""}{" Message was deleted" if settings["context"][1] < 2 else ''}"""
                    if not serverIsGimped(g):
                        await updateLastActive(log.user, discord.utils.utcnow(), 'deleted a message')
                    modDelete = True
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        image_path = await self.image_to_local_attachment(log.user.display_avatar)
                        attachments.append(image_path)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=f'attachment://{os.path.basename(image_path)}')
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=f'attachment://{os.path.basename(image_path)}')
                else:
                    if g.id not in gimpedServers:
                        await updateLastActive(author, discord.utils.utcnow(), 'deleted a message')
            except Exception:
                logger.error(f'Encountered error when trying to get audit log for {g.name} message delete', exc_info=True)
        if log and log.user.bot:
            if settings['botLogging'] == 0:
                return
            if settings['botLogging'] == 1:
                settings['plainText'] = True
        if log_bot_author in [0, 2] and author.bot:
            # Check to see if the recursion deletion mode is enabled for Disguard log messages
            if author.id == self.bot.user.id and (await utility.get_server(g))['cyberlog'].get('disguardLogRecursion'):
                channels = [(await utility.get_server(g))['cyberlog']['defaultChannel']]
                for w in logUnits:
                    channels.append((await utility.get_server(g))['cyberlog'][w]['channel'])
                if channel.id in channels:  # We have a log channel
                    # if log and log.user.id == 247412852925661185: return
                    modUser = log.user if log else 'A moderator'
                    content = f"{self.emojis['fileClone']} | {modUser.mention} ({modUser.display_name}) deleted my log embed, so I cloned it here"
                    p = f'storage/{g.id}/misc/modLogs.json'
                    try:
                        async with aiofiles.open(p) as f:
                            try:
                                content = await f.read()
                                logArchives = json.loads(content)
                            except Exception:
                                logger.error(f'Encountered error when trying to load log archives for {g.name} message delete', exc_info=True)
                                logArchives = {}
                    except FileNotFoundError:
                        logArchives = {}
                    try:
                        embed = discord.Embed.from_dict(logArchives[str(payload.message_id)])
                    except KeyError:
                        return
                    msg = await c.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(users=False))
                    await self.archiveLogEmbed(g, msg.id, embed, 'Message Delete (Recursion Clone)')
                    return
            if settings['botLogging'] == 0:
                return
        plainText = f"""{log.user if modDelete else author} deleted {f"{author}'s" if modDelete else "their"} message in #{channel.name if type(channel) is discord.TextChannel else channel}\n\n{'<No content>' if not content else content[:1900]}\n\n{plainText}"""
        a = 0
        while a < len(attachments):
            f = attachments[a]
            if (await aios.stat(f)).st_size / 1_000_000 > 10:
                fileError += f"\n{self.emojis['alert']} | This message's attachment ({os.path.basename(f)}) is too large to be sent ({round(os.stat(f).st_size / 1_000_000, 2)}mb). Please view [this page](https://disguard.netlify.app/privacy.html#appendixF) for more information including file retrieval."
                savePath = f'{TEMP_DIR}/{payload.message_id}/{os.path.basename(f)}'
                await aioshutil.copy2(f, savePath)
                attachments.pop(a)
            else:
                a += 1
        content += f'\n\n{fileError}'
        msg = await c.send(
            content=plainText
            if 'audit log' in plainText or 'too large' in plainText or any((settings['plainText'], settings['flashText'], settings['tts']))
            else None,
            embed=embed if not settings['plainText'] else None,
            files=[discord.File(f) for f in attachments[:10]],
            tts=settings['tts'],
        )
        if any((settings['tts'], settings['flashText'])) and not settings['plainText']:
            await msg.edit(content=None)
        await self.archiveLogEmbed(g, msg.id, embed, 'Message Delete')
        # Now delete any attachments associated with this message
        try:
            await aioshutil.rmtree(attachments_path)
        except FileNotFoundError:
            # This message had no attachments
            pass
        while not self.bot.is_closed():
            try:
                result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
            except asyncio.TimeoutError:
                break
            if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                await msg.edit(content=plainText, embed=None)
                await msg.clear_reactions()
                if not settings['plainText']:
                    await msg.add_reaction(self.emojis['expand'])
            elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']) and len(msg.embeds) < 1:
                await msg.edit(content=None, embed=embed)
                await msg.clear_reactions()
                if settings['plainText']:
                    await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """[DISCORD API METHOD] Called when server channel is created"""
        content = ''
        savePath = None
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(channel.guild))
        msg = None
        if await logEnabled(channel.guild, 'channel'):
            settings = await getCyberAttributes(channel.guild, 'channel')
            color = green[await utility.color_theme(channel.guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            keytypes = {discord.Member: '👤', discord.Role: '🚩'}
            content = f'A moderator created a new {channel.type[0]} channel called {channel.name}'
            embed = discord.Embed(
                title=f"""{utility.channelEmoji(self, channel) if settings["context"][0] > 0 else ""}{(self.emojis["channelCreate"] if settings["library"] > 1 else self.emojis["darkGreenPlus"]) if settings["context"][0] > 0 else ""}{f"{utility.CHANNEL_KEYS.get(channel.type, 'Unknown type')} Channel was created" if settings["context"][0] < 2 else ""}""",
                description=f'{self.channelKeys[channel.type[0] if settings["context"][1] > 0 else ""]}{"Channel" if settings["context"][1] < 2 else ""}: {f"{channel.mention} ({channel.name})" if channel.type[0] == "text" else channel.name}',
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if await readPerms(channel.guild, 'channel'):
                try:
                    log = await channel.guild.audit_logs().get(action=discord.AuditLogAction.channel_create)
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description += f"""\n{"👮‍♂️" if settings['context'][1] > 0 else ""}{"Created by" if settings['context'][1] < 2 else ""}: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} created a new {channel.type[0]} channel called {channel.name}'
                    if channel.guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'created a channel')
                except:
                    pass
            embed.set_footer(text=f'Channel ID: {channel.id}')
            msg: discord.Message = await (await logChannel(channel.guild, 'channel')).send(
                content=content if 'audit log' in content or any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            defaultRead = channel.overwrites_for(channel.guild.default_role).read_messages
            if defaultRead is False:
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
            memberAccessibleNewline = ' ' if len(accessibleMembers) > 20 else NEWLINE
            memberUnaccessibleNewline = ' ' if len(unaccessibleMembers) > 20 else NEWLINE
            roleAccessibleNewline = ' ' if len(accessibleRoles) > 20 else NEWLINE
            roleUnaccessibleNewline = ' ' if len(unaccessibleRoles) > 20 else NEWLINE
            accessibleTail = f'ACCESSIBLE TO\n------------------\nROLES\n{roleAccessibleNewline.join([f"🚩 {r.name}" for r in accessibleRoles])}\n\nMEMBERS\n{memberAccessibleNewline.join([f"👤 {m.name}" for m in accessibleMembers])}'
            unaccessibleTail = f'NOT ACCESSIBLE TO\n-----------------------\nROLES\n{roleUnaccessibleNewline.join([f"🚩 {r.name}" for r in unaccessibleRoles])}\n\nMEMBERS\n{memberUnaccessibleNewline.join([f"👤 {m.name}" for m in unaccessibleMembers])}'
            if channel.overwrites_for(channel.guild.default_role).read_messages is not False:
                tempAccessibleString = f"""\n[{'🔓' if settings['context'][1] > 0 else ''}{'Accessible to' if settings['context'][1] < 2 else ''}: **Everyone by default**]({msg.jump_url} '{accessibleTail}')"""
            else:
                if sum(len(obj.name) for obj in accessible) > 32 or len(accessible) == 0:
                    tempAccessibleString = f"""\n[{'🔓' if settings['context'][1] > 0 else ''}{'Accessible to' if settings['context'][1] < 2 else ''}: {len(accessibleRoles)} role{"s" if len(accessibleRoles) != 1 else ""} ({len(accessibleMembers)} member{"s" if len(accessibleMembers) != 1 else ""})]({msg.jump_url} '{accessibleTail}')"""
                else:
                    tempAccessibleString = f"""\n[{'🔓' if settings['context'][1] > 0 else ''}{'Accessible to' if settings['context'][1] < 2 else ''}: {" • ".join([f'{keytypes.get(type(o))}{o.name}' for o in accessible])}]({msg.jump_url} '{accessibleTail}')"""
            if len(unaccessible) > 0:  # At least one member or role can't access this channel by default
                if sum(len(obj.name) for obj in unaccessible) > 28:
                    tempUnaccessibleString = f"""\n[{'🔒' if settings['context'][1] > 0 else ''}{'Not accessible to' if settings['context'][1] < 2 else ''}: {len(unaccessibleRoles)} role{"s" if len(unaccessibleRoles) != 1 else ""} ({len(unaccessibleMembers)} member{"s" if len(unaccessibleMembers) != 1 else ""})]({msg.jump_url} '{unaccessibleTail}')"""
                else:
                    tempUnaccessibleString = f"""\n[{'Not accessible to' if settings['context'][1] < 2 else ''}: {" • ".join([f'{keytypes.get(type(o))}{o.name}' for o in unaccessible])}]({msg.jump_url} '{unaccessibleTail}')"""
            else:
                tempUnaccessibleString = ''
            if len(tempAccessibleString) + len(tempUnaccessibleString) > 1900:
                trimmedAccessibleString = f"\n{tempAccessibleString[tempAccessibleString.find('[')+1:tempAccessibleString.find(']')]}"
                trimmedUnaccessibleString = f"\n{tempUnaccessibleString[tempUnaccessibleString.find('[')+1:tempUnaccessibleString.find(']')]}"
                if len(tempAccessibleString) + len(trimmedUnaccessibleString) < 1900:
                    embed.description += f'{tempAccessibleString}{trimmedUnaccessibleString}'
                elif len(trimmedAccessibleString) + len(tempUnaccessibleString) < 1900:
                    embed.description += f'{trimmedAccessibleString}{tempUnaccessibleString}'
                elif len(trimmedAccessibleString) + len(trimmedUnaccessibleString) < 1900:
                    embed.description += f'{trimmedAccessibleString}{trimmedUnaccessibleString}'
            else:
                embed.description += f'{tempAccessibleString}{tempUnaccessibleString}'
            # singleQuoteMark = "'"
            # plainTextAccessibleString = f"{tempAccessibleString[tempAccessibleString.find('[') + 1:tempAccessibleString.find(']')]}{newline}{tempAccessibleString[tempAccessibleString.find(singleQuoteMark) + 1:tempAccessibleString.find(')') - 1]}"
            # plainTextUnaccessibleString = f"{tempUnaccessibleString[tempUnaccessibleString.find('[') + 1:tempUnaccessibleString.find(']')]}{newline}{tempUnaccessibleString[tempUnaccessibleString.find(singleQuoteMark) + 1:tempUnaccessibleString.find(')') - 1]}"
            if settings['embedTimestamp'] > 1:
                embed.description += f"""\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else "🕰") if settings['context'][1] > 0 else ""}{"Timestamp" if settings['context'][1] < 2 else ""}: {utility.DisguardLongTimestamp(received)}"""
            if channel.type[0] != 'category':
                channelList = channel.category.channels if channel.category is not None else [c for c in channel.guild.channels if c.category is None]
                cIndexes = (
                    channelList.index(channel) - 3 if channelList.index(channel) >= 3 else 0,
                    channelList.index(channel) + 4 if channelList.index(channel) + 4 < len(channelList) else len(channelList),
                )
                plainTextChannelList = f"{NEWLINE.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList])}"
                embed.add_field(
                    name='Category Tree',
                    value=f"""{self.emojis['folder'] if settings['library'] > 1 else '📁'}{channel.category}\n{f"> [...Hover to view {len(channelList[:cIndexes[0]])} more channel{'s' if len(channelList[:cIndexes[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[:cIndexes[0]])}'){NEWLINE}" if cIndexes[0] > 0 else ""}{NEWLINE.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList[cIndexes[0]:cIndexes[1]]])}{f"{NEWLINE}[Hover to view {len(channelList[cIndexes[1]:])} more channel{'s' if len(channelList[cIndexes:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[cIndexes[1]:])}')" if cIndexes[1] < len(channelList) else ""}""",
                )
                if len(embed.fields[0].value) > 1024:
                    embed.set_field_at(0, name=embed.fields[0].name, value=plainTextChannelList)
                if len(embed.fields[0].value) > 1024:
                    embed.remove_field(0)
            await msg.edit(
                content=msg.content if not any((settings['tts'], settings['flashText'])) and not settings['plainText'] else None,
                embed=embed if not settings['plainText'] else None,
            )
            await self.archiveLogEmbed(channel.guild, msg.id, embed, 'Channel Create')
            try:
                if os.path.exists(savePath):
                    os.remove(savePath)
            except:
                pass
        try:
            if channel.category is not None:
                self.categories[channel.category.id] = [c for c in channel.category.channels]
            else:
                self.categories[channel.guild.id] = [c[1] for c in channel.guild.by_category() if c[0] is None]
        except discord.Forbidden:
            pass
        if type(channel) is discord.TextChannel:
            if (await utility.get_server(channel.guild)).get('cyberlog', {}).get('image'):
                self.pins[channel.id] = []
            asyncio.create_task(database.VerifyChannel(channel, True), name=f'channel_create - VerifyChannel-{channel.id}')
        if msg:

            def reactionCheck(r: discord.Reaction, u: discord.User):
                return r.message.id == msg.id and not u.bot

            while not self.bot.is_closed():
                try:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                except asyncio.TimeoutError:
                    break
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']:
                        await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']:
                        await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        """[DISCORD API METHOD] Called when server channel is updated"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(after.guild))
        f = None
        msg = None
        channelPosFlag = False
        channelPosTimekey = f'{discord.utils.utcnow():%m%d%Y%H%M%S}'
        if await logEnabled(before.guild, 'channel'):
            content = f'A moderator updated the {after.type[0]} channel called {before.name}'
            savePath = None
            settings = await getCyberAttributes(after.guild, 'channel')
            color = blue[await utility.color_theme(after.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed = discord.Embed(
                title=f"""{utility.channelEmoji(self, after) if settings["context"][0] > 0 else ""}{(self.emojis["channelEdit"] if settings["library"] > 1 else self.emojis["edit"] if settings["library"] > 0 else "✏") if settings["context"][0] > 0 else ""}
                {f"{utility.CHANNEL_KEYS.get(after.type, after.type)} Channel was updated" if settings["context"][0] < 2 else ""}""",
                description=f'{self.channelKeys[after.type[0]] if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {f"{after.mention} ({after.name})" if after.type[0] == "text" else after.name}',
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            reactions = ['ℹ']
            if await readPerms(before.guild, 'channel'):
                try:
                    log = await before.guild.audit_logs().find(
                        lambda x: x.action
                        in (
                            discord.AuditLogAction.channel_update,
                            discord.AuditLogAction.overwrite_create,
                            discord.AuditLogAction.overwrite_update,
                            discord.AuditLogAction.overwrite_delete,
                        )
                    )
                    if log.user.id == self.bot.user.id and before.overwrites != after.overwrites:
                        return  # Avoid logging Disguard updates to channel overwrites
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description += f"""\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Updated by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} updated the {after.type[0]} channel called {before.name}'
                    if after.guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'edited a channel')
                except:
                    pass  # Exception as e: content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            embed.set_footer(text=f'Channel ID: {before.id}')
            if before.category == after.category is not None:
                bc = self.categories.get(before.category.id)
                if bc and abs(bc.index(before) - after.category.channels.index(after)) > 1:
                    indexes = []  # Channel, before index, after index
                    channelPosFlag = True
                    self.channelCacheHelper[after.guild.id] = []
                    for i in range(len(before.category.channels)):
                        indexes.append(
                            {
                                'before': bc.index(before.category.channels[i]),
                                'after': after.category.channels.index(before.category.channels[i]),
                                'channel': after.category.channels[i],
                            }
                        )
                    embed.add_field(
                        name='Channel position changed',
                        value=f"""{self.emojis['folder'] if settings['library'] > 1 else '📁'}{before.category.name}\n{NEWLINE.join([(f'~~{self.channelKeys.get(before.type[0])}{before.name}~~❌{NEWLINE}' if bc.index(before) == c and indexes[c].get('before') > indexes[c].get('after') else '') + f'{self.channelKeys.get(indexes[c].get("channel").type[0])}' + ('__**' if indexes[c].get('channel').id == before.id else '') + f'{indexes[c].get("channel").name} ' + ('**__' if indexes[c].get('channel').id == before.id else '') + ('↩' if abs(indexes[c].get('before') - indexes[c].get('after')) > 1 else '⬆' if indexes[c].get('before') > indexes[c].get('after') else '⬇' if indexes[c].get('before') < indexes[c].get('after') else '') + (f'{NEWLINE}~~{self.channelKeys.get(before.type[0])}{before.name}~~❌' if bc.index(before) == c and indexes[c].get('before') < indexes[c].get('after') else '') for c in range(len(indexes))])}""",
                    )
                    self.categories[after.category.id] = [c for c in after.category.channels]
            if before.overwrites != after.overwrites:
                embed.add_field(
                    name='Permission overwrites updated', value='Manually react 🇵 to show/hide'
                )  # The rest of this code is later because we need a message link to the current message
                if log and log.user == self.bot.user:
                    return
            if before.name != after.name:
                embed.add_field(name='Name', value=f'{before.name} → **{after.name}**')
            if type(before) is discord.TextChannel:
                beforeTopic = before.topic if before.topic is not None and len(before.topic) > 0 else '<No topic>'
                afterTopic = after.topic if after.topic is not None and len(after.topic) > 0 else '<No topic>'
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
                    embed.add_field(
                        name='Slowmode',
                        value=f'{delays[0][0]} {delays[0][1]}{"s" if delays[0][0] != 1 else ""}'
                        if before.slowmode_delay > 0
                        else '<Disabled>' + f' → **{delays[1][0]} {delays[1][1]}{"s" if delays[1][0] != 1 else ""}**'
                        if after.slowmode_delay > 0
                        else '**<Disabled>**',
                    )
            elif type(before) is discord.VoiceChannel:
                if before.bitrate != after.bitrate:
                    embed.add_field(name='Bitrate', value=f'{before.bitrate // 1000} kbps' + f' → **{after.bitrate // 1000} kbps**')
                if before.user_limit != after.user_limit:
                    embed.add_field(name='User Limit', value=f'{before.user_limit} → **{after.user_limit}**')
            if type(before) is not discord.CategoryChannel and before.category != after.category:
                embed.add_field(name='Old Category', value='Old')
                embed.add_field(name='New Category', value='New')
            if len(embed.fields) > 0:
                content += utility.embedToPlaintext(embed)
                msg: discord.Message = await (await logChannel(before.guild, 'channel')).send(
                    content=content if 'audit log' in content or any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                    embed=embed if not settings['plainText'] else None,
                    tts=settings['tts'],
                )
                if type(before) is not discord.CategoryChannel and before.category != after.category:
                    oldChannelList = self.categories.get(before.category.id) if before.category is not None else self.categories.get(before.guild.id)
                    newChannelList = (
                        after.category.channels if after.category is not None else [c[1] for c in after.guild.by_category() if c[0] is None]
                    )
                    oldIndexes = (
                        oldChannelList.index(after) - 3 if oldChannelList.index(after) >= 3 else 0,
                        oldChannelList.index(after) + 4 if oldChannelList.index(after) + 4 < len(oldChannelList) else len(oldChannelList),
                    )
                    newIndexes = (
                        newChannelList.index(after) - 3 if newChannelList.index(after) >= 3 else 0,
                        newChannelList.index(after) + 4 if newChannelList.index(after) + 4 < len(newChannelList) else len(newChannelList),
                    )
                    plainTextOldList = f"{NEWLINE.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in oldChannelList])}"
                    plainTextNewList = f"{NEWLINE.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in newChannelList])}"
                    for i, field in enumerate(embed.fields):
                        if field.name == 'Old Category':
                            embed.set_field_at(
                                i,
                                name='Old Category',
                                value=f"""{self.emojis['folder'] if settings['library'] > 1 else '📁'}{before.category}\n{f"> [...Hover to view {len(oldChannelList[:oldIndexes[0]])} more channel{'s' if len(oldChannelList[:oldIndexes[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in oldChannelList[:oldIndexes[0]])}'){NEWLINE}" if oldIndexes[0] > 0 else ""}{NEWLINE.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in oldChannelList[oldIndexes[0]:oldIndexes[1]]])}{f"{NEWLINE}> [Hover to view {len(oldChannelList[oldIndexes[1]:])} more channel{'s' if len(oldChannelList[oldIndexes[1]:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in oldChannelList[oldIndexes[1]:])}')" if oldIndexes[1] < len(oldChannelList) else ""}""",
                            )
                            embed.set_field_at(
                                i + 1,
                                name='New Category',
                                value=f"""{self.emojis['folder'] if settings['library'] > 1 else '📁'}{after.category}\n{f"> [...Hover to view {len(newChannelList[:newIndexes[0]])} more channel{'s' if len(newChannelList[:newIndexes[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in newChannelList[:newIndexes[0]])}'){NEWLINE}" if newIndexes[0] > 0 else ""}{NEWLINE.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == after.id else c.name) for c in newChannelList[newIndexes[0]:newIndexes[1]]])}{f"{NEWLINE}> [Hover to view {len(newChannelList[newIndexes[1]:])} more channel{'s' if len(newChannelList[oldIndexes[1]:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in newChannelList[newIndexes[1]:])}')" if newIndexes[1] < len(newChannelList) else ""}""",
                            )
                            if len(embed.fields[i].value) > 1024:
                                embed.set_field_at(i, name=embed.fields[i].name, value=plainTextOldList)
                            if len(embed.fields[i + 1].value) > 1024:
                                embed.set_field_at(i + 1, name=embed.fields[i + 1].name, value=plainTextNewList)
                            break
                if before.overwrites != after.overwrites:
                    b4 = {key: dict(iter(value)) for (key, value) in before.overwrites.items()}  # Channel permissions before it was updated
                    af = {key: dict(iter(value)) for (key, value) in after.overwrites.items()}  # Channel permissions after it was updated
                    displayString = []  # Holds information about updated permission values - this will be displayed line by line in the future
                    english = {True: '✔', None: '➖', False: '✖'}  # A mapping of overwrite values to emojis for easy visualization
                    classification = {
                        discord.Role: '🚩',
                        discord.Member: '👤',
                    }  # A mapping of overwrite targets to emojis for easy visualization. Unicode emojis due to codeblock & hover mechanics being utilized.
                    # Iterate through all members/roles in the after channel permissions. K represents the member/role, and V represents the dict of {key: Value} pairs for permissions
                    for k, v in af.items():
                        # If the overwrites are different or an overwrite was created, add the target's name to the string, with the target's name left-aligned and trailing dashes
                        if before.overwrites_for(k) != after.overwrites_for(k) or b4.get(k) != af.get(k):
                            displayString.append(f'{classification[type(k)]}{k.name:-<71}')
                        # This will get triggered if there is an overwrite target (role/member) in the after permissions, but not before. This means that a new overwrite target was added to this channel.
                        if not b4.get(k):
                            displayString[-1] = (
                                f'{classification[type(k)]}{k.name}{" (⭐Created)":-<71}'  # If the overwrite was just created, edit the last string entry to represent that. The :-<80 means add dashes to fill spaces, with the words (created) left-aligned.
                            )
                            b4[k] = {
                                key: None for key in v.keys()
                            }  # If the overwrite was just created, set the before values to None to represent that for the parser later on
                        # Iterate through Permission name: Value. value can be False, None, or True - the format for PermissionOverwrites.
                        for kk, vv in v.items():
                            # If the current permission_name: Value key is different than the previous value, make note of it
                            if not set({kk: vv}.items()).issubset(b4.get(k).items()):
                                # String format: Permission Name, left aligned with spaces to fill 50 character gap, Pipestem, (emoji symbol, centered (3 characters)) right aligned, with spaces to fill the left, pipestem right aligned,
                                displayString.append(
                                    f"""   {utility.pretty_permission(kk):<42} | {f"{english[b4[k][kk]]:^3}":^9} -|- {f"{english[vv]:^3}":^9} |"""
                                )
                    for (
                        k,
                        v,
                    ) in (
                        b4.items()
                    ):  # Added in January update because apparently this code leaves out instances of overwrites being completely removed
                        if af.get(k) is None:  # An overwrite for role/member was deleted
                            af[k] = {key: None for key in v.keys()}
                            displayString.append(f'{classification[type(k)]}{k.name}{" (❌Removed)":-<71}')
                            for kk, vv in v.items():
                                if not set({kk: vv}.items()).issubset(af.get(k).items()):
                                    displayString.append(
                                        f"""   {utility.pretty_permission(kk):<42} | {f"{english[vv]:^3}":^9} -|- {f"{english[af[k][kk]]:^3}":^9} |"""
                                    )
                    permissionString = f"""```{"Permission overwrites updated":<45} | {"Before":^10} | {"After":^10} |\n{NEWLINE.join([line.replace('-|-', '|') for line in displayString])}```"""
                    # permissionString = '```{0:<56}|{1:^13}|{2:^20}\n{3}```'.format('Permission overwrites updated', 'Before', 'After', '\n'.join(displayString))
                    for i, f in enumerate(embed.fields):
                        if 'Permission overwrites' in f.name and len(displayString) > 0:
                            embed.set_field_at(
                                i,
                                name='Permission overwrites updated',
                                value=f"""[Use 🇵 to toggle details • Hover for preview]({msg.jump_url} '{permissionString.replace("```", "")}')"""
                                if len(permissionString) < 950
                                else 'Use 🇵 to toggle details',
                            )
                            break
                    reactions.append('🇵')
                members = {}
                removedKeys = {}
                gainedKeys = {}
                for m in after.guild.members:
                    removed = ' '.join(
                        [p[0] for p in iter(before.permissions_for(m)) if p[1] and p[0] not in [pp[0] for pp in after.permissions_for(m) if pp[1]]]
                    )
                    gained = ' '.join(
                        [p[0] for p in iter(after.permissions_for(m)) if p[1] and p[0] not in [pp[0] for pp in before.permissions_for(m) if pp[1]]]
                    )
                    if len(removed) > 0:
                        try:
                            members[m.id].update({'removed': removed})
                        except KeyError:
                            members[m.id] = {'removed': removed}
                    if len(gained) > 0:
                        try:
                            members[m.id].update({'gained': gained})
                        except KeyError:
                            members[m.id] = {'gained': gained}
                for k, v in members.items():
                    try:
                        removedKeys[v.get('removed')].append(after.guild.get_member(k))
                    except AttributeError:
                        removedKeys[v.get('removed')] = [after.guild.get_member(k)]
                    except KeyError:
                        if v.get('removed') is not None:
                            removedKeys[v.get('removed')] = [after.guild.get_member(k)]
                    try:
                        gainedKeys[v.get('gained')].append(after.guild.get_member(k))
                    except AttributeError:
                        gainedKeys[v.get('gained')] = [after.guild.get_member(k)]
                    except KeyError:
                        if v.get('gained') is not None:
                            gainedKeys[v.get('gained')] = [after.guild.get_member(k)]
                joinKeys = (' 👤 ', ' • ')
                # Figure out what to do about the hover links.
                gainDescription = (
                    (
                        f"""{NEWLINE.join([f"[{len(v)} member{'s' if len(v) != 1 else ''} gained {len(k.split(' '))} permission{'s' if len(k.split(' ')) != 1 else ''} • Hover for details]({msg.jump_url} '--MEMBERS--{NEWLINE}{NEWLINE.join([m.name for m in v]) if len(v) < 20 else joinKeys[0].join([m.name for m in v])}{NEWLINE}{NEWLINE}--PERMISSIONS--{NEWLINE}{NEWLINE.join([utility.pretty_permission(p) for p in k.split(' ')]) if len(k.split(' ')) < 20 else joinKeys[1].join([utility.pretty_permission(p) for p in k.split(' ')])}')" for k, v in gainedKeys.items()])}{NEWLINE if len(removedKeys) > 0 and len(gainedKeys) > 0 else ''}"""
                    )
                    if len(gainedKeys) > 0
                    else ''
                )
                removeDescription = (
                    f"""{NEWLINE.join([f"[{len(v)} member{'s' if len(v) != 1 else ''} lost {len(k.split(' '))} permission{'s' if len(k.split(' ')) != 1 else ''} • Hover for details]({msg.jump_url} '--MEMBERS--{NEWLINE}{NEWLINE.join([m.name for m in v]) if len(v) < 20 else joinKeys[0].join([m.name for m in v])}{NEWLINE}{NEWLINE}--PERMISSIONS--{NEWLINE}{NEWLINE.join([utility.pretty_permission(p) for p in k.split(' ')]) if len(k.split(' ')) < 20 else joinKeys[1].join([utility.pretty_permission(p) for p in k.split(' ')])}')" for k,v in removedKeys.items()])}"""
                    if len(removedKeys) > 0
                    else ''
                )
                if len(gainDescription) > 0 or len(removeDescription) > 0:
                    embed.description += (
                        f'{NEWLINE if len(gainDescription) > 0 or len(removeDescription) > 0 else ""}{gainDescription}{removeDescription}'
                    )
                else:
                    if before.overwrites != after.overwrites:
                        embed.description += '\nPermissions were updated, but no members were affected'
                if settings['embedTimestamp'] > 1:
                    embed.description += f"""\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else "🕰") if settings['context'][1] > 0 else ""}{"Timestamp" if settings['context'][1] < 2 else ""}: {utility.DisguardLongTimestamp(received)}"""
                try:
                    await msg.edit(content=content if settings['plainText'] else None, embed=None if settings['plainText'] else embed)
                except discord.HTTPException:
                    await msg.edit(content=content if settings['plainText'] else None)
                await self.archiveLogEmbed(after.guild, msg.id, embed, 'Channel Update')
                if not settings['plainText']:
                    for reaction in reactions:
                        await msg.add_reaction(reaction)
                try:
                    if os.path.exists(savePath):
                        os.remove(savePath)
                except:
                    pass
        if (before.position != after.position or before.category != after.category) and not channelPosFlag:
            try:
                self.channelCacheHelper[after.guild.id].append(channelPosTimekey)
            except:
                self.channelCacheHelper[after.guild.id] = [channelPosTimekey]
            asyncio.create_task(
                self.delayedUpdateChannelIndexes(after.guild, channelPosTimekey),
                name=f'channel_update - delayedUpdateChannelIndexes-{after.guild.id}-{channelPosTimekey}',
            )
        if type(before) is discord.TextChannel and before.name != after.name:
            asyncio.create_task(database.VerifyChannel(after), name=f'channel_update - VerifyChannel-{after.id}')
        try:
            if msg:
                final = copy.deepcopy(embed)
                while not self.bot.is_closed():

                    def reactionCheck(r, u):
                        return r.message.id == msg.id and not u.bot

                    try:
                        r = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                    except asyncio.TimeoutError:
                        break
                    if str(r[0]) == '🇵' and '🇵' in reactions:
                        await msg.edit(content=(permissionString[:1995] + '…```') if len(permissionString) > 2000 else permissionString)

                        def undoCheck(rr, u):
                            return str(rr) == '🇵' and rr.message.id == msg.id and u.id == r[1].id

                        try:
                            await self.bot.wait_for('reaction_remove', check=undoCheck, timeout=120)
                        except asyncio.TimeoutError:
                            await msg.remove_reaction(r[0], r[1])
                        await msg.edit(content=None)
                    elif str(r[0]) == 'ℹ':
                        await msg.clear_reactions()
                        if 'Loading channel information' not in embed.description:
                            embed.description += f'\n\n{self.loading} Loading channel information: {after.name}'
                        await msg.edit(embed=embed)
                        info: Info.Info = self.bot.get_cog('Info')
                        result = await info.ChannelInfo(
                            after,
                            None if after.type[0] == 'category' else await after.invites(),
                            None if after.type[0] != 'text' else await after.pins(),
                            [log async for log in after.guild.audit_logs(limit=None)],
                        )
                        await msg.edit(content=result[0], embed=result[1])
                        await msg.add_reaction('⬅')

                        def backCheck(rr, u):
                            return str(rr) == '⬅' and rr.message.id == msg.id and u.id == r[1].id

                        try:
                            await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                        except asyncio.TimeoutError:
                            pass
                        await msg.edit(content=content, embed=final)
                        await msg.clear_reactions()
                        for r in reactions:
                            await msg.add_reaction(r)
                    elif r[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                        await msg.edit(content=content, embed=None)
                        await msg.clear_reactions()
                        if not settings['plainText']:
                            await msg.add_reaction(self.emojis['expand'])
                    elif (r[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']) and len(msg.embeds) < 1:
                        await msg.edit(content=None, embed=embed)
                        await msg.clear_reactions()
                        if settings['plainText']:
                            await msg.add_reaction(self.emojis['collapse'])
                        for reaction in ['🇵', 'ℹ']:
                            await msg.add_reaction(reaction)
        except UnboundLocalError:
            return

    async def delayedUpdateChannelIndexes(self, g: discord.Guild, timekey):
        """Updates channel cache data after 1 second, to account for logging
        Timekey: Unique key based on timestamp that allows the update process to go through only if it hasn't already, reducing inaccuracies in data
        """
        await asyncio.sleep(1)
        if timekey not in self.channelCacheHelper[g.id]:
            return
        for c in g.categories:
            try:
                self.categories[c.id] = [c for c in c.channels]
            except discord.Forbidden:
                pass
        try:
            self.categories[g.id] = [c[1] for c in g.by_category() if c[0] is None]
        except discord.Forbidden:
            pass
        self.channelCacheHelper[g.id].remove(timekey)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """[DISCORD API METHOD] Called when channel is deleted"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(channel.guild))
        msg = None
        if await logEnabled(channel.guild, 'channel'):
            content = f'A moderator deleted the {channel.type[0]} channel named {channel.name}'
            settings = await getCyberAttributes(channel.guild, 'channel')
            color = red[await utility.color_theme(channel.guild)] if settings['color'][2] == 'auto' else settings['color'][2]
            embed = discord.Embed(
                title=f"""{utility.channelEmoji(self, channel) if settings["context"][0] > 0 else ""}{(self.emojis["channelDelete"] if settings["library"] > 1 else self.emojis["delete"]) if settings["context"][0] > 0 else ""}{f"{utility.CHANNEL_KEYS.get(channel.type, 'Unknown type')} Channel was deleted" if settings['context'][0] < 2 else ''}""",
                description=f'{self.channelKeys.get(channel.type[0]) if settings["context"][1] > 0 else ""}{"Channel" if settings["context"][1] < 2 else ""}: {channel.name}',
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if await readPerms(channel.guild, 'channel'):
                try:
                    log = await channel.guild.audit_logs().get(action=discord.AuditLogAction.channel_delete)
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description += f"""\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Deleted by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} deleted the {channel.type[0]} channel named {channel.name}'
                    if channel.guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'deleted a channel')
                except:
                    pass
            if settings['embedTimestamp'] > 1:
                embed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}"
            embed.set_footer(text=f'Channel ID: {channel.id}')
            content += utility.embedToPlaintext(embed)
            msg: discord.Message = await (await logChannel(channel.guild, 'channel')).send(
                content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            if channel.type[0] != 'category':
                channelList = self.categories.get(channel.category.id) if channel.category is not None else self.categories.get(channel.guild.id)
                startEnd = (
                    channelList.index(channel) - 3 if channelList.index(channel) >= 3 else 0,
                    channelList.index(channel) + 4 if channelList.index(channel) + 4 < len(channelList) else len(channelList),
                )
                # plainTextChannelList = f"{newline.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList])}"
                embed.add_field(
                    name='Category Tree',
                    value=f"""{self.emojis['folder'] if settings['library'] > 1 else '📁'}{channel.category}\n{f"> [...Hover to view {len(channelList[:startEnd[0]])} more channel{'s' if len(channelList[:startEnd[0]]) != 1 else ''}]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[:startEnd[0]])}'){NEWLINE}" if startEnd[0] > 0 else ""}{NEWLINE.join([f'> {self.channelKeys.get(c.type[0])}' + (f'**{c.name}**' if c.id == channel.id else c.name) for c in channelList[startEnd[0]:startEnd[1]]])}{f"{NEWLINE}> [Hover to view {len(channelList[startEnd[1]:])} more channel{'s' if len(channelList[startEnd[1]:]) != 1 else ''}...]({msg.jump_url} '{newlineQuote.join(chan.name for chan in channelList[startEnd[1]:])}')" if startEnd[1] < len(channelList) else ""}""",
                )
                if channel.category is not None:
                    self.categories[channel.category.id].remove(channel)
                else:
                    self.categories[channel.guild.id].remove(channel)
            if channel.type[0] == 'text':
                messages = await lightningdb.get_channel_messages(channel.id)
                embed.add_field(name='Message count', value=len(messages) if messages else 0)
                await lightningdb.delete_channel(channel.id)
                channel_attachments_path = f'storage/{channel.guild.id}/attachments/{channel.id}'
                try:
                    await aioshutil.rmtree(channel_attachments_path)
                except FileNotFoundError:
                    # this channel didn't have an attachments directory
                    pass
                self.pins.pop(channel.id, None)
            await msg.edit(content=None if not settings['plainText'] else content, embed=embed)
            await self.archiveLogEmbed(channel.guild, msg.id, embed, 'Channel Delete')
        if type(channel) is discord.TextChannel:
            asyncio.create_task(
                database.VerifyServer(channel.guild, self.bot), name=f'channel_delete - VerifyServer-{channel.guild.id}'
            )  # Look into database methods to remove channels without needing to call the VerifyServer method
        if msg:

            def reactionCheck(r, u):
                return r.message.id == msg.id and not u.bot

            while not self.bot.is_closed():
                try:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                except asyncio.TimeoutError:
                    break
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']:
                        await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']:
                        await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """[DISCORD API METHOD] Called when member joins a server"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(member.guild))
        self.members[member.guild.id].append(member)
        asyncio.create_task(self.doorguardHandler(member), name=f'doorguardHandler-{member.guild.id}-{member.id}')
        msg = None
        if await logEnabled(member.guild, 'doorguard'):
            newInv = []
            content = f'{member} joined the server'
            targetInvite = None
            settings = await getCyberAttributes(member.guild, 'doorguard')
            color = green[await utility.color_theme(member.guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            count = len(member.guild.members)
            ageDisplay = utility.elapsedDuration(discord.utils.utcnow() - member.created_at, False)
            embed = discord.Embed(
                title=f"""{(f"{self.emojis['member'] if not member.bot else '🤖'}{self.emojis['darkGreenPlus']}" if settings['library'] < 2 else self.emojis['memberJoin']) if settings['context'][0] > 0 else ''}{f"New {'member' if not member.bot else 'bot'}"} {self.loading}""",
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                url = await self.imageToURL(member.display_avatar)
                if settings['thumbnail'] in (1, 2, 4):
                    embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4):
                    embed.set_author(name=member.display_name, icon_url=url)
            try:
                newInv = await member.guild.invites()
                oldInv = self.invites.get(str(member.guild.id))
            except discord.Forbidden:
                pass
                # content+="Tip: I can determine who invited new members if I have the `Manage Server` permissions"
            try:
                for invite in oldInv:
                    try:
                        if newInv[newInv.index(invite)].uses > invite.uses:
                            targetInvite = newInv[newInv.index(invite)]
                            break
                    except ValueError:  # An invite that reached max uses will be missing from the new list
                        targetInvite = newInv[newInv.index(invite)]
                        break
                if not targetInvite:  # Check the vanity invite (if applicable) if we don't have an invite
                    try:
                        invite = await member.guild.vanity_invite()
                        if invite.uses > self.invites.get(str(member.guild.id) + '_vanity').uses:
                            targetInvite = invite
                    except discord.HTTPException:
                        pass
                if not targetInvite:  # If the vanity invite either doesn't exist or isn't the invite used, then it was an invite created between the invites were stored & now
                    for i in newInv:
                        if i.id not in [oi.id for oi in oldInv] and i.uses != 0:
                            targetInvite = i
                            break
            except discord.Forbidden:
                embed.add_field(name='Invite Details', value='Enable `manage server` permissions to use this feature')
            except Exception as e:
                embed.add_field(name='Invite Details', value=f'Error retrieving details: {e}'[:1023])
            try:
                self.invites[str(member.guild.id)] = newInv
            except:
                pass
            msg = await (await logChannel(member.guild, 'doorguard')).send(
                content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            if member.bot and settings['read']:
                try:
                    log = [a_log async for a_log in member.guild.audit_logs(limit=1)][0]
                    if log.action == discord.AuditLogAction.bot_add:
                        embed.description = f"""
                            {"🤖" if settings['context'][1] > 0 else ''}{"Bot" if settings['context'][1] < 2 else ''}: {member.mention} ({member.display_name})
                            {self.emojis["details"] if settings['context'][1] > 0 else ''}{"Placement" if settings['context'][1] < 2 else ''}: {count}{utility.suffix(count)} member
                            Top.gg stats (when applicable) will be available in the future"""
                        if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                            settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                        ):
                            url = await self.imageToURL(log.user.display_avatar)
                            if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                                embed.set_thumbnail(url=url)
                            if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                                embed.set_author(name=log.user.display_name, icon_url=url)
                        content = f'{log.user} added the {member.display_name} bot to the server'
                        await updateLastActive(log.user, discord.utils.utcnow(), 'added a bot to a server')
                except:
                    pass
            else:
                descriptionString = [  # First: plaintext version, second: hover-links hybrid version
                    textwrap.dedent(f"""
                        {self.emojis['member'] if settings['context'][1] > 0 else ''}{"Member" if settings['context'][1] < 2 else ''}: {f"{member.mention} ({member.display_name})"}
                        {self.emojis["details"] if settings['context'][1] > 0 else ''}{"Placement" if settings['context'][1] < 2 else ''}: {count}{utility.suffix(count)} member
                        {f"{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}" if settings['embedTimestamp'] > 1 else ''}
                        {"📅" if settings['context'][1] > 0 else ''}{"Account created" if settings['context'][1] < 2 else ''}: {utility.DisguardIntermediateTimestamp(member.created_at)}
                        {"🕯" if settings['context'][1] > 0 else ''}{"Account age" if settings['context'][1] < 2 else ''}: {f"{', '.join(ageDisplay[:-1])} and {ageDisplay[-1]}" if len(ageDisplay) > 1 else ageDisplay[0]} old
                        {self.emojis["share"] if settings['context'][1] > 0 else ""}{"Mutual Servers" if settings['context'][1] < 2 else ''}: {len([g for g in self.bot.guilds if member in g.members])}\n
                        QUICK ACTIONS\nYou will be asked to confirm any of these quick actions via reacting with a checkmark after initiation, so you can click one to learn more without harm.\n🤐: Mute {member.display_name}\n🔒: Quarantine {member.display_name}\n👢: Kick {member.display_name}\n🔨: Ban {member.display_name}"""),
                    textwrap.dedent(f"""
                        {self.emojis['member'] if settings['context'][1] > 0 else ''}{"Member" if settings['context'][1] < 2 else ''}: {f"{member.mention} ({member.display_name})"}
                        {self.emojis["details"] if settings['context'][1] > 0 else ''}{"Placement" if settings['context'][1] < 2 else ''}: {count}{utility.suffix(count)} member
                        {"🕯" if settings['context'][1] > 0 else ''}{"Account age" if settings['context'][1] < 2 else ''}: {ageDisplay[0]} old
                        [Hover or react {self.emojis["expand"]} for more details]({msg.jump_url} '
                        {"🕰" if settings['context'][1] > 0 else ''}{"Timestamp" if settings['context'][1] < 2 else ''}: {utility.DisguardStandardTimestamp(adjusted)} {await utility.name_zone(member.guild)}
                        {"📅" if settings['context'][1] > 0 else ''}{"Account created" if settings['context'][1] < 2 else ''}: {(utility.DisguardStandardTimestamp(member.created_at + datetime.timedelta(hours=await utility.time_zone(member.guild))))} {await utility.name_zone(member.guild)}
                        {"🕯" if settings['context'][1] > 0 else ''}{"Account age" if settings['context'][1] < 2 else ''}: {f"{', '.join(ageDisplay[:-1])} and {ageDisplay[-1]}" if len(ageDisplay) > 1 else ageDisplay[0]} old
                        {"🌐" if settings['context'][1] > 0 else ""}{"Mutual Servers" if settings['context'][1] < 2 else ''}: {len([g for g in self.bot.guilds if member in g.members])}\n
                        QUICK ACTIONS\nYou will be asked to confirm any of these quick actions via reacting with a checkmark after initiation, so you can click one to learn more without harm.\n🤐: Mute {member.display_name}\n🔒: Quarantine {member.display_name}\n👢: Kick {member.display_name}\n🔨: Ban {member.display_name}')"""),
                ]
                embed.description = descriptionString[1]
                if targetInvite:
                    content = f'{targetInvite.inviter} invited {member} to the server' if targetInvite.inviter else content
                    if (
                        (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)))
                        or (settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)))
                        and targetInvite.inviter
                    ):
                        url = await self.imageToURL(targetInvite.inviter.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=targetInvite.inviter.name, icon_url=url)
                    inviteString = [  # First: plaintext version, second: hover-links hybrid version
                        textwrap.dedent(f"""
                            {self.emojis["member"] if settings['context'][1] > 0 else ""}{"Invited by" if settings['context'][1] < 2 else ""}: {f"{targetInvite.inviter.display_name} ({targetInvite.inviter.mention})" if targetInvite.inviter else "N/A"}
                            {"🔗" if settings['context'][1] > 0 else ""}{"Code" if settings['context'][1] < 2 else ""}: discord.gg/{targetInvite.code}
                            {self.emojis["textChannel"] if settings["context"][1] > 0 else ""}{"Channel" if settings['context'][1] < 2 else ""}: {targetInvite.channel.name if targetInvite.channel else "N/A"}
                            {"📅" if settings['context'][1] > 0 else ""}{"Created" if settings['context'][1] < 2 else ""}: {utility.DisguardIntermediateTimestamp(targetInvite.created_at)}
                            {f"{'♾' if settings['context'][1] > 0 else ''}Never expires" if targetInvite.max_age == 0 else f"{'⏰' if settings['context'][1] > 0 else ''}Expires: {utility.DisguardRelativeTimestamp(discord.utils.utcnow() + datetime.timedelta(seconds=targetInvite.max_age))}"}
                            {"🔓" if settings['context'][1] > 0 else ''}{"Used" if settings['context'][1] < 2 else ""}: {targetInvite.uses} of {"∞" if targetInvite.max_uses == 0 else targetInvite.max_uses} times"""),
                        textwrap.dedent(f"""
                            {self.emojis["member"] if settings['context'][1] > 0 else ""}{"Invited by" if settings['context'][1] < 2 else ""}: {f"{targetInvite.inviter.display_name} ({targetInvite.inviter.mention})" if targetInvite.inviter else "N/A"}
                            [Hover or react {self.emojis["expand"]} for more details]({msg.jump_url} '
                            {"🔗" if settings['context'][1] > 0 else ""}{"Code" if settings['context'][1] < 2 else ""}: discord.gg/{targetInvite.code}
                            {"🚪" if settings["context"][1] > 0 else ""}{"Channel" if settings['context'][1] < 2 else ""}: {targetInvite.channel.name if targetInvite.channel else "N/A"}
                            {"📅" if settings['context'][1] > 0 else ""}{"Created" if settings['context'][1] < 2 else ""}: {targetInvite.created_at:%b %d, %Y • %I:%M %p} {await utility.name_zone(member.guild)}
                            {f"{'♾' if settings['context'][1] > 0 else ''}Never expires" if targetInvite.max_age == 0 else f"{'⏰' if settings['context'][1] > 0 else ''}Expires: {(discord.utils.utcnow() + datetime.timedelta(seconds=targetInvite.max_age)):%b %d, %Y • %I:%M %p} {await utility.name_zone(member.guild)}"}
                            {"🔓" if settings['context'][1] > 0 else ''}{"Used" if settings['context'][1] < 2 else ""}: {targetInvite.uses} of {"∞" if targetInvite.max_uses == 0 else targetInvite.max_uses} times')"""),
                    ]  # Note to self: in v2.0, invites have an "expired_at" attribute, thus making "max age" calculations redundant
                    embed.add_field(name='Invite Details', value=inviteString[1] if len(inviteString[1]) < 1024 else inviteString[0])
            if member.flags.did_rejoin:
                embed.set_footer(text='This member rejoined the server')
            await msg.edit(content=content if settings['plainText'] else None, embed=embed if not settings['plainText'] else None)
            await self.archiveLogEmbed(member.guild, msg.id, embed, 'Member Join')
        await asyncio.gather(
            *[
                database.VerifyMember(member, new=True, warnings=(await utility.get_server(member.guild)).get('antispam', {}).get('warn', 3)),
                database.VerifyUser(member, self.bot, new=True),
                updateLastActive(member, discord.utils.utcnow(), 'joined a server'),
            ]
        )

        # Check if member is trying to circumvent a mute
        async def muteDelay(event):
            # Sleeps for 20 seconds to ensure no other bots want to add roles upon join
            await asyncio.sleep(20)
            duration = (discord.utils.utcnow() - event['expires']).total_seconds
            await self.bot.get_cog('Moderation').muteMembers(
                [member], member.guild.me, duration=duration, reason="Member rejoined server but their mute isn't over yet"
            )

        hadToRemute = False
        events = (await utility.get_server(member.guild)).get('antispam', {}).get('timedEvents')
        for event in events:
            try:
                if event['type'] == 'mute' and event['target'] == member.id and (discord.utils.utcnow() - event['timestamp']).total_seconds > 60:
                    hadToRemute = True
                    asyncio.create_task(muteDelay, event, name=f'muteDelay-{member.guild.id}-{member.id}')
            except:
                pass
        if msg:
            if member.id in [m.id for m in member.guild.members]:  # TODO: change to dict for performance if possible?
                embed.title = f"""{(f"{self.emojis['member'] if not member.bot else '🤖'}{self.emojis['darkGreenPlus']}" if settings['library'] < 2 else self.emojis['memberJoin']) if settings['context'][0] > 0 else ''}{f"New {'member' if not member.bot else 'bot'}" if settings['context'][0] < 2 else ''}"""
                if hadToRemute:
                    embed.description += f"\n{self.emojis['greenCheck']}Succesfully remuted {member.display_name}"
                await msg.edit(content=msg.content, embed=embed if not settings['plainText'] else None)
                return
                final = copy.deepcopy(embed)
                memberInfoEmbed = None
                reactions = [self.emojis['expand'], 'ℹ', '🤐', '🔒', '👢', '🔨']
                while not self.bot.is_closed():
                    if not settings['plainText']:
                        for r in reactions:
                            await msg.add_reaction(r)
                    embed = copy.deepcopy(final)

                    def navigationCheck(r, u):
                        return not u.bot and r.message.id == msg.id

                    r: typing.Tuple[discord.Reaction, discord.User] = await self.bot.wait_for('reaction_add', check=navigationCheck)
                    if r[0].emoji in reactions or settings['plainText']:
                        # TODO for V1.0: Redo all this stuff
                        # EVERYTHING BELOW THIS WILL BE REDONE, thus it's obsolete and not necessarily syntactically correct anymore
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

                            def backCheck(rr, u):
                                return str(rr) == '⬅' and u == r[1] and rr.message.id == msg.id

                            try:
                                await self.bot.wait_for('reaction_add', check=backCheck, timeout=300)
                            except asyncio.TimeoutError:
                                pass
                        elif str(r[0]) == '🤐':
                            if await database.ManageRoles(r[1]) and await database.ManageChannels(r[1]):
                                embed.description = f'{r[1].display_name}, would you like me to mute **{member.display_name}**?\n\nThis member will remain muted until the unmute command is used on them.\n\nTo confirm, react {self.emojis["whiteCheck"]} within 10 seconds'
                                embed.set_image(url='https://i.postimg.cc/s2pZs1Cv/ten.gif')
                                await msg.edit(embed=embed)
                                for reaction in ['❌', '✔']:
                                    await msg.add_reaction(reaction)

                                def confirmCheck(rr, u):
                                    return str(rr) in ['❌', '✔'] and u == r[1] and rr.message.id == msg.id

                                try:
                                    rr = await self.bot.wait_for('reaction_add', check=confirmCheck, timeout=10)
                                except asyncio.TimeoutError:
                                    rr = [0]
                                if str(rr[0]) == '✔':
                                    results = await self.bot.get_cog('Moderation').muteMembers(
                                        member, rr[1], reason=f'Moderator: {rr[1]}\nSource: Member join log quick actions'
                                    )

                                    def nestMore(array):
                                        return (
                                            '\n'.join([f'{NEWLINE}{qlf}{qlf}{i}' for i in array])
                                            if len(array) > 1
                                            else f'{array[0]}'
                                            if len(array) == 1
                                            else ''
                                        )

                                    embed.description = '\n\n'.join(
                                        [
                                            f"""{m}:\n{NEWLINE.join([f"{qlf}{k}: {NEWLINE.join([f'{qlf}{nestMore(v)}'])}" for k, v in n.items()])}"""
                                            if len(n) > 0
                                            else ''
                                            for m, n in results.items()
                                        ]
                                    )
                                    await msg.edit(embed=embed)
                                    final.description = embed.description
                            else:
                                embed.description += f'\n\n**{r[1].display_name}, you need `Manage Roles` and `Manage Channels` permissions to mute {member.display_name}.**'
                                await msg.edit(embed=embed)
                                await asyncio.sleep(10)
                        elif str(r[0]) == '🔒':
                            if await database.ManageChannels(r[1]):
                                embed.description = f'{r[1].display_name}, would you like me to quarantine **{member.display_name}**?\n\nThis will prevent {member.display_name} from being able to access any of the channels in this server until the `unlock` command is run.\n\nTo confirm, react {self.emojis["whiteCheck"]} within 10 seconds'
                                embed.set_image(url='https://i.postimg.cc/s2pZs1Cv/ten.gif')
                                await msg.edit(embed=embed)
                                for reaction in ['❌', '✔']:
                                    await msg.add_reaction(reaction)

                                def confirmCheck(rr, u):
                                    return str(rr) in ['❌', '✔'] and u == r[1] and rr.message.id == msg.id

                                try:
                                    rr = await self.bot.wait_for('reaction_add', check=confirmCheck, timeout=10)
                                except asyncio.TimeoutError:
                                    rr = [0]
                                if str(rr[0]) == '✔':
                                    for c in member.guild.text_channels:
                                        try:
                                            await c.set_permissions(member, read_messages=False)
                                        except discord.Forbidden as error:
                                            embed.description += f'\nUnable to create permission overwrites for the channel {c.name} because `{error.text}`. Please set the permissions for this channel to [{member.display_name}: Read Messages = ❌] for the quarantine to work there.'
                                    embed.description = (
                                        final.description
                                        + f'\n\n**Successfully quarantined {member.display_name}.**\nUse `{await utility.prefix(member.guild)}unlock {member.id}` to unlock this user when desired.'
                                    )
                                    await msg.edit(embed=embed)
                                    final.description = embed.description
                            else:
                                embed.description += (
                                    f'\n\n**{r[1].display_name}, you need `Manage Channels` permissions to quarantine {member.name}.**'
                                )
                                await msg.edit(embed=embed)
                                await asyncio.sleep(10)
                        elif str(r[0]) == '👢':
                            if await database.KickMembers(r[1]):
                                embed.description = f'{r[1].display_name}, would you like me to kick **{member.display_name}**? Please react {self.emojis["whiteCheck"]} within 10 seconds to confirm. To provide a reason for the kick, react 📝 instead of check, and you will be able to provide a reason at the next step.'
                                embed.set_image(url='https://i.postimg.cc/s2pZs1Cv/ten.gif')
                                await msg.edit(embed=embed)
                                for reaction in ['❌', '📝', '✔']:
                                    await msg.add_reaction(reaction)

                                def confirmCheck(rr, u):
                                    return str(rr) in ['❌', '📝', '✔'] and u == r[1] and rr.message.id == msg.id

                                try:
                                    rr = await self.bot.wait_for('reaction_add', check=confirmCheck, timeout=10)
                                except asyncio.TimeoutError:
                                    rr = [0]
                                if str(rr[0]) == '✔':
                                    try:
                                        await member.kick()
                                        embed.description = final.description + f'\n\n**Successfully kicked {member.display_name}**'
                                    except discord.Forbidden as error:
                                        embed.description += f'\n\n**Unable to kick {member.display_name} because `{error.text}`.**'
                                    await msg.edit(embed=embed)
                                    final.description = embed.description
                                elif str(rr[0]) == '📝':

                                    def reasonCheck(m):
                                        return msg.channel == m.channel and m.author.id == r[1].id

                                    embed.description = f'Please type the reason you would like to kick {member.display_name}.\n\nType your reason within 60 seconds. The first message you type will be used, and {member.display_name} will be kicked.\n\nTo cancel, wait 60 seconds without sending anything.'
                                    embed.set_image(url='https://i.postimg.cc/kg2rttTh/sixty.gif')
                                    await msg.edit(embed=embed)
                                    try:
                                        reason = await self.bot.wait_for('message', check=reasonCheck, timeout=60)
                                    except:
                                        pass
                                    try:
                                        await member.kick(reason=f'Kicked by {r[1].display_name} because {reason.content}')
                                        embed.description = final.description + f'\n\nSuccessfully kicked {member.display_name}.'
                                        final.description = embed.description
                                    except discord.Forbidden as error:
                                        embed.description += f'\n\n**Unable to kick {member.display_name} because `{error.text}`.**'
                                    except UnboundLocalError:
                                        pass  # Timeout
                                    await msg.edit(embed=embed)
                            else:
                                embed.description += (
                                    f'\n\n**{r[1].display_name}, you need `Kick Members` permissions to kick {member.display_name}.**'
                                )
                                await msg.edit(embed=embed)
                                await asyncio.sleep(10)
                        elif str(r[0]) == '🔨':
                            if await database.BanMembers(r[1]):
                                embed.description = f'{r[1].display_name}, would you like me to ban **{member.display_name}** indefinitely? Please react {self.emojis["whiteCheck"]} within 10 seconds to confirm. To provide a reason for the ban, react 📝 instead of check, and you will be able to provide a reason at the next step.'
                                embed.set_image(url='https://i.postimg.cc/s2pZs1Cv/ten.gif')
                                await msg.edit(embed=embed)
                                for reaction in ['❌', '📝', '✔']:
                                    await msg.add_reaction(reaction)

                                def confirmCheck(rr, u):
                                    return str(rr) in ['❌', '📝', '✔'] and u == r[1] and rr.message.id == msg.id

                                try:
                                    rr = await self.bot.wait_for('reaction_add', check=confirmCheck, timeout=10)
                                except asyncio.TimeoutError:
                                    rr = [0]
                                if str(rr[0]) == '✔':
                                    try:
                                        await member.ban()
                                        embed.description = final.description + f'\n\n**Successfully banned {member.display_name}**'
                                    except discord.Forbidden as error:
                                        embed.description += f'\n\n**Unable to ban {member.display_name} because `{error.text}`.**'
                                    await msg.edit(embed=embed)
                                    final.description = embed.description
                                elif str(rr[0]) == '📝':

                                    def reasonCheck(m):
                                        return msg.channel == m.channel and m.author.id == r[1].id

                                    embed.description = f'Please type the reason you would like to ban {member.display_name}.\n\nType your reason within 60 seconds. The first message you type will be used, and {member.display_name} will be banned.\n\nTo cancel, wait 60 seconds without sending anything.'
                                    embed.set_image(url='https://i.postimg.cc/kg2rttTh/sixty.gif')
                                    await msg.edit(embed=embed)
                                    try:
                                        reason = await self.bot.wait_for('message', check=reasonCheck, timeout=60)
                                    except:
                                        pass
                                    try:
                                        await member.ban(reason=f'Banned by {r[1].display_name} because {reason.content}')
                                        embed.description = final.description + f'\n\nSuccessfully banned {member.display_name}.'
                                        final.description = embed.description
                                    except discord.Forbidden as error:
                                        embed.description += f'\n\n**Unable to ban {member.display_name} because `{error.text}`.**'
                                    except UnboundLocalError:
                                        pass  # Timeout
                                    await msg.edit(embed=embed)
                            else:
                                embed.description += f'\n\n**{r[1].display_name}, you need `Ban Members` permissions to ban {member.display_name}.**'
                                await msg.edit(embed=embed)
                                await asyncio.sleep(10)
                        elif r[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or settings['plainText']:
                            if len(msg.embeds) > 0 and 'https://' in msg.embeds[0].description:
                                final.description = descriptionString[0]
                                try:
                                    final.set_field_at(0, name='**Invite Details**', value=inviteString[0])
                                except:
                                    pass
                                reactions.remove(self.emojis['expand'])
                            elif settings['plainText']:  # Prevents this doing something for a completely redundant reason
                                await msg.edit(content=None, embed=final)
                                editEmbed = False
                            reactions.insert(0, self.emojis['collapse'])
                        elif r[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎'):
                            if len(msg.embeds) > 0 and 'https://' not in msg.embeds[0].description:
                                final.description = descriptionString[1]
                                try:
                                    final.set_field_at(0, name='**Invite Details**', value=inviteString[1])
                                except:
                                    pass
                                reactions.remove(self.emojis['collapse'])
                            elif settings['plainText']:  # Prevents this doing something for a completely redundant reason
                                await msg.edit(content=content, embed=None)
                                editEmbed = False
                            reactions.insert(0, self.emojis['expand'])
                        await msg.clear_reactions()
                        if editEmbed:
                            await msg.edit(embed=final)
            else:
                embed.title = f"""{(f"{self.emojis['member'] if not member.bot else '🤖'}{self.emojis['darkGreenPlus']}" if settings['library'] < 2 else self.emojis['memberJoin']) if settings['context'][0] > 0 else ''}{f"New {'member' if not member.bot else 'bot'}" if settings['context'][0] < 2 else ''} (Left the server)"""
                await msg.edit(embed=embed)

    async def doorguardHandler(self, member: discord.Member):
        """REPEATED JOINS"""  # Consider splitting this up into three methods or adding exception catchers
        rj = await antispamObject(member.guild).get('repeatedJoins')
        if 0 not in rj[:2]:  # Make sure this module is enabled (remember, modules are set to 0 to mark them as disabled)
            try:
                self.repeatedJoins[f'{member.guild.id}_{member.id}'].append(member.joined_at)
            except (AttributeError, KeyError):
                self.repeatedJoins[f'{member.guild.id}_{member.id}'] = [member.joined_at]
            joinLogs = self.repeatedJoins.get(f'{member.guild.id}_{member.id}')
            remainingDelta: datetime.timedelta = (
                (joinLogs[0] + datetime.timedelta(seconds=rj[1])) - discord.utils.utcnow()
            )  # Time remaining before oldest join log expires. If a member joins the server [threshold] times in this timespan, they're punished
            durationDelta = datetime.timedelta(seconds=rj[2])
            rH, rM, rS = (
                remainingDelta.seconds // 3600,
                (remainingDelta.seconds // 60) % 60,
                remainingDelta.seconds - (remainingDelta.seconds // 3600) * 3600 - ((remainingDelta.seconds // 60) % 60) * 60,
            )  # remainingHours, remainingMinutes, remainingSeconds
            dH, dM, dS = (
                durationDelta.seconds // 3600,
                (durationDelta.seconds // 60) % 60,
                durationDelta.seconds - (durationDelta.seconds // 3600) * 3600 - ((durationDelta.seconds // 60) % 60) * 60,
            )  # ban duration Hours, Minutes, Seconds
            remainingTimes = [rS, rM, rH, remainingDelta.days]
            durationTimes = [dH, dM, dS, durationDelta.days]
            remainingDisplay = []
            durationDisplay = []
            units = ['second', 'minute', 'hour', 'day']
            for i in range(len(remainingTimes) - 1, -1, -1):
                if remainingTimes[i] != 0:
                    remainingDisplay.append(f'{remainingTimes[i]} {units[i]}{"s" if remainingTimes[i] != 1 else ""}')
                if durationTimes[i] != 0:
                    durationDisplay.append(f'{durationTimes[i]} {units[i]}{"s" if durationTimes[i] != 1 else ""}')
            if len(remainingDisplay) == 0:
                remainingDisplay = ['0 seconds']
            if len(durationDisplay) == 0:
                durationDisplay = ['0 seconds']
            if len(joinLogs) > 1:
                # This is the warning segment: If this is at least the second time the member has joined the server recently, then we will warn them of the threshold and consequences if they continue to join.
                sendString = f"""{member.mention}, `{member.guild.name}` has my Antispam [repeated joins] module enabled. If you join this server {rj[0] - len(joinLogs)} more time{'s' if rj[0] - len(joinLogs) != 1 else ''} in {f"{', '.join(remainingDisplay[:-1])} and {remainingDisplay[-1]}" if len(remainingDisplay) > 1 else remainingDisplay[0]}, you will be banned{'.' if rj[2] == 0 else f" for {', '.join(durationDisplay[:-1])} and {durationDisplay[-1]}" if len(durationDisplay) > 1 else f" for {durationDisplay[0]}"}."""
                try:
                    await member.send(sendString)
                except discord.Forbidden:  # Can't DM member, try to let them know in the server (if ageKick is disabled)
                    if await database.GetAgeKick(member.guild) is None:
                        sendTo: discord.TextChannel = await database.CalculateGeneralChannel(member.guild, self.bot, True)
                        if sendTo.permissions_for(member).read_messages:
                            await sendTo.send(sendString)  # If the member can read messages in the server's general channel, then we'll send it there
            if len(joinLogs) >= rj[0]:
                joinSpanDisplay = utility.elapsedDuration(joinLogs[-1] - joinLogs[0])
                joinSpan = joinLogs[-1] - joinLogs[0]
                if len(joinSpanDisplay) == 0:
                    joinSpanDisplay = ['0 seconds']
                if joinSpan.seconds < rj[1]:
                    unbanAt = discord.utils.utcnow() + datetime.timedelta(seconds=rj[2])
                    timezoneUnbanAt = unbanAt + datetime.timedelta(hours=await utility.time_zone(member.guild))
                    try:
                        await member.send(
                            f'You have been banned from `{member.guild.name}` for {utility.DisguardRelativeTimestamp(unbanAt)} for repeatedly joining and leaving the server.'
                        )
                    except:
                        pass
                    try:
                        await member.ban(
                            reason=f"""[Antispam: repeatedJoins] {member.display_name} joined the server {len(joinLogs)} times in {joinSpanDisplay}, and will remain banned until {f"{timezoneUnbanAt:%b %d, %Y • %I:%M %p} {await utility.name_zone(member.guild)}" if rj[2] > 0 else "the ban is manually revoked"}."""
                        )  # If I find out that the unix timestamps work in audit logs, I will update this line too
                    except discord.Forbidden:
                        try:
                            await (await logChannel(member.guild, 'doorguard')).send(
                                f'Unable to ban {member.name} for [ageKick: repeatedJoins] module'
                            )
                        except:
                            pass
                    self.repeatedJoins[f'{member.guild.id}_{member.id}'].clear()
                    banTimedEvent = {
                        'type': 'ban',
                        'flavor': '[Antispam: repeatedJoins]',
                        'target': member.id,
                        'expires': discord.utils.utcnow() + datetime.timedelta(seconds=rj[2]),
                    }
                    await database.AppendTimedEvent(member.guild, banTimedEvent)
        """AGEKICK ⬇"""
        acctAge = (discord.utils.utcnow() - member.created_at).days
        antispam = await antispamObject(member.guild)
        ageKick = antispam.get('ageKick')
        if ageKick is not None:  # Check account age; requested feature
            if member.created_at > (discord.utils.utcnow() - datetime.timedelta(seconds=ageKick)) and member.id not in antispam.get(
                'ageKickWhitelist'
            ):  # If the account age is under the threshold and they're not whitelisted:
                memberCreated = member.created_at + datetime.timedelta(hours=await utility.time_zone(member.guild))
                canRejoin = memberCreated + datetime.timedelta(days=ageKick)
                formatter = '%b %d, %Y • %I:%M %p'
                timezone = await utility.name_zone(member.guild)
                dm = antispam.get('ageKickDM')
                try:
                    await member.send(eval(dm))
                except discord.Forbidden as e:
                    try:
                        await (await logChannel(member.guild, 'doorguard')).send(
                            content=f"I will kick {member.display_name}, but I can't DM them explaining why they were kicked because {e.text}."
                        )
                    except:
                        pass
                await member.kick(reason=f'[Antispam: ageKick] Account must be {ageKick} days old; is only {acctAge} days old')
            elif member.id in antispam.get('ageKickWhitelist'):
                await database.RemoveWhitelistEntry(member.guild, member.id)
        """WARMUP"""  # mute members on join until configured time passes
        if antispam.get('warmup', 0) > 0:
            warmup, loops = antispam['warmup'], 0
            units = {0: 'second', 1: 'minute', 2: 'hour', 3: 'day', 4: 'week'}
            values = {0: 60, 1: 60, 2: 60, 3: 24, 4: 7}
            while warmup >= values[loops] and loops < 4:
                warmup /= values[loops]
                loops += 1
            await self.bot.get_cog('Moderation').muteMembers(
                [member],
                member.guild.me,
                duration=antispam['warmup'],
                reason=f'[Antispam: Warmup] This new member will be able to begin chatting in {round(warmup)} {units[loops]}{"s" if warmup != 1 else ""} (at {utility.DisguardStandardTimestamp(discord.utils.utcnow() + datetime.timedelta(seconds=antispam.get("warmup", 0)) + datetime.timedelta(hours=await utility.time_zone(member.guild)))}).',
                waitToUnmute=True,
            )
        """Repeated Joins: Sleeping"""
        if 0 not in rj[:2]:
            try:
                if len(joinLogs) >= rj[0] and rj[2] > 0:
                    await asyncio.sleep(rj[2])
                    try:
                        await member.unban(reason='[Antispam: repeatedJoins] Ban time is up!')
                    except discord.Forbidden:
                        await (await logChannel(member.guild, 'doorguard')).send(
                            f'Unable to unban {member.display_name} for [ageKick: repeatedJoins]; their ban time is up'
                        )
                    await database.RemoveTimedEvent(member.guild, banTimedEvent)
                else:
                    await asyncio.sleep(rj[1])
                    if len(joinLogs) > 0:
                        self.repeatedJoins[f'{member.guild.id}_{member.id}'].pop(0)  # Removes the oldest entry
            except UnboundLocalError:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """[DISCORD API METHOD] Called when member leaves a server"""
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(member.guild))
        if member.guild.id not in gimpedServers:
            asyncio.create_task(
                updateLastActive(member, discord.utils.utcnow(), 'left a server'),
                name=f'member_leave - updateLastActive-{member.guild.id}-{member.id}',
            )
        message = None
        if await logEnabled(member.guild, 'doorguard'):
            content = f'{member} left the server'
            settings = await getCyberAttributes(member.guild, 'doorguard')
            color = red[await utility.color_theme(member.guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            embed = discord.Embed(
                title=f"""{(f"{self.emojis['member'] if not member.bot else '🤖'}❌" if settings['library'] < 2 else self.emojis['memberLeave']) if settings['context'][0] > 0 else ''}{"Member left" if not member.bot else "Bot removed"} ({self.loading} Finalizing log)""",
                description=f"{(self.emojis['member'] if not member.bot else '🤖') if settings['context'][1] > 0 else ''}{'Member' if settings['context'][1] < 2 and not member.bot else 'Bot' if settings['context'][1] < 2 and member.bot else ''}: {member.mention} ({member.display_name})",
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            hereForDisplay = utility.elapsedDuration(discord.utils.utcnow() - member.joined_at)
            embed.add_field(name='Post count', value=self.loading)
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                url = await self.imageToURL(member.display_avatar)
                if settings['thumbnail'] in (1, 2, 4):
                    embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4):
                    embed.set_author(name=member.display_name, icon_url=url)
            if await readPerms(member.guild, 'doorguard'):
                try:
                    log = await member.guild.audit_logs().find(
                        lambda x: utility.absTime(discord.utils.utcnow(), x.created_at, datetime.timedelta(seconds=3) and x.target.id == member.id)
                    )
                    # if utility.absTime(discord.utils.utcnow(), log.created_at, datetime.timedelta(seconds=3)) and log.target.id == member.id:
                    if log.action in (discord.AuditLogAction.kick, discord.AuditLogAction.ban):
                        if log.action == discord.AuditLogAction.kick:
                            embed.title = f'{(self.emojis["memberLeave"] if settings["library"] > 1 else self.emojis["member"]) if settings["context"][1] > 0 else ""}{"👢" if settings["context"][1] > 0 else ""}{member.display_name} was kicked'
                            embed.description += f'\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Kicked by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name})'
                            content = f'{log.user} kicked {member} from the server'
                        else:
                            embed.title = f'{(self.emojis["memberLeave"] if settings["library"] > 1 else self.emojis["member"]) if settings["context"][1] > 0 else ""}{self.emojis["ban"] if settings["context"][1] > 0 else ""}{member.display_name} was banned'
                            embed.description += f'\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Banned by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name})'
                            content = f'{log.user} banned {member} from the server'
                        embed.insert_field_at(
                            0, name='Reason', value=log.reason or 'None provided', inline=True if log.reason and len(log.reason) < 25 else False
                        )
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                except:
                    pass
            message = await (await logChannel(member.guild, 'doorguard')).send(
                content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            try:
                sortedMembers = sorted(self.members[member.guild.id], key=lambda x: x.joined_at or discord.utils.utcnow())
                memberJoinPlacement = sortedMembers.index(member) + 1
                hoverPlainText = textwrap.dedent(f"""
                    Here since: {(member.joined_at + datetime.timedelta(hours=await utility.time_zone(member.guild))):%b %d, %Y • %I:%M:%S %p} {await utility.name_zone(member.guild)}
                    Left at: {adjusted:%b %d, %Y • %I:%M:%S %p}
                    Here for: {hereForDisplay}
                    Was the {memberJoinPlacement}{utility.suffix(memberJoinPlacement)} member, now we have {len(sortedMembers) - 1}
                    """)
                embed.description += f"\n[Hover for more details]({message.jump_url} '{hoverPlainText}')"
                # embed.description+=f"\n[Hover for more details]({message.jump_url} 'Here since: {(member.joined_at + datetime.timedelta(hours=self.timeZone(member.guild))):%b %d, %Y • %I:%M:%S %p} {self.nameZone(member.guild)}"
                # embed.description+=f'''\nLeft at: {received}\nHere for: {hereForDisplay}'''
                # embed.description+=f'\nWas the {memberJoinPlacement}{suffix(memberJoinPlacement)} member, now we have {len(sortedMembers) - 1}'
            except Exception as e:
                print(f'Member leave placement fail: {e}')
            if 'Finalizing' in embed.title:
                embed.title = f"""{(f"{self.emojis['member'] if not member.bot else '🤖'}❌" if settings['library'] < 2 else self.emojis['memberLeave']) if settings['context'][0] > 0 else ''}{f'{"Member left" if not member.bot else "Bot removed"}' if settings['context'][0] < 2 else ''}"""
            await message.edit(content=content if settings['plainText'] else None, embed=embed if not settings['plainText'] else None)
            info: Info.Info = self.bot.get_cog('Info')
            embed.set_field_at(-1, name='**Post count**', value=await info.MemberPosts(member))
            await message.edit(embed=embed if not settings['plainText'] else None)
            await self.archiveLogEmbed(member.guild, message.id, embed, 'Member Leave')
            # if any((settings['flashText'], settings['tts'])) and not settings['plainText']: await message.edit(content=None)
        self.members[member.guild.id].remove(member)
        await asyncio.gather(*[database.VerifyMembers(member.guild, [member]), database.DeleteUser(member, self.bot)])
        if message:

            def reactionCheck(r, u):
                return r.message.id == message.id and not u.bot

            while not self.bot.is_closed():
                try:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                except asyncio.TimeoutError:
                    break
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(message.embeds) > 0:
                    await message.edit(content=content, embed=None)
                    await message.clear_reactions()
                    if not settings['plainText']:
                        await message.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(message.embeds) < 1:
                    await message.edit(content=None, embed=embed)
                    await message.clear_reactions()
                    if settings['plainText']:
                        await message.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        received = discord.utils.utcnow()
        msg = None
        if await logEnabled(guild, 'doorguard'):
            settings = await getCyberAttributes(guild, 'doorguard')
            color = green[await utility.color_theme(guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            embed = discord.Embed(
                title=f"""{f"{self.emojis['member']}{self.emojis['unban']}" if settings["context"][0] > 0 else ""}{"User was unbanned" if settings['context'][0] < 2 else ""}""",
                description=f"{self.emojis['member'] if settings['context'][1] > 0 else ''}{'User' if settings['context'][1] < 2 else ''}: {user.display_name}",
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            content = f'{user} was unbanned'
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                url = await self.imageToURL(user.display_avatar)
                if settings['thumbnail'] in (1, 2, 4):
                    embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4):
                    embed.set_author(name=user.display_name, icon_url=url)
            if await readPerms(guild, 'doorguard'):
                try:
                    log = await guild.audit_logs().get(action=discord.AuditLogAction.unban)
                    embed.description += f'\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Unbanned by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name})'
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    if guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'unbanned a user')
                    log = await guild.audit_logs(limit=None).get(action=discord.AuditLogAction.ban, target__id=user.id)
                    content = f'{log.user} unbanned {user}'
                    bannedForDisplay = utility.elapsedDuration(discord.utils.utcnow() - log.created_at)
                    embed.add_field(name='Retrieved ban details', value=f'React {self.emojis["expand"]} to expand', inline=False)
                    longString = textwrap.dedent(f"""
                        {'👮‍♂️' if settings['context'][1] > 0 else ''}{'Banned by' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.display_name})
                        {'📜' if settings['context'][1] > 0 else ''}{'Banned because' if settings['context'][1] < 2 else ''}: {log.reason if log.reason is not None else '<No reason specified>'}
                        {f"{self.emojis['ban']}🕰" if settings['context'][1] > 0 else ''}{'Banned at' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(log.created_at - datetime.timedelta(hours=DST))}
                        {f"{self.emojis['unban']}🕰" if settings['context'][1] > 0 else ''}{'Unbanned at' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}
                        {f"{self.emojis['ban']}⏳" if settings['context'][1] > 0 else ''}{'Banned for' if settings['context'][1] < 2 else ''}: {bannedForDisplay}""")
                except:
                    pass
            embed.set_footer(text=f'User ID: {user.id}')
            msg: discord.Message = await (await logChannel(guild, 'doorguard')).send(
                content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            if not settings['plainText'] and any((settings['flashText'], settings['tts'])):
                await msg.edit(content=None)
            await self.archiveLogEmbed(guild, msg.id, embed, 'Member Unban')
            if msg and len(embed.fields) > 0:
                if not settings['plainText']:
                    await msg.add_reaction(self.emojis['expand'])
                while not self.bot.is_closed():

                    def toggleCheck(r, u):
                        return not u.bot and r.message.id == msg.id

                    try:
                        r = await self.bot.wait_for('reaction_add', check=toggleCheck, timeout=1800)
                    except asyncio.TimeoutError:
                        break
                    if r[0].emoji == self.emojis['expand']:
                        await msg.clear_reactions()
                        if len(msg.embeds) > 0 and 'to expand' in embed.fields[-1].value:  # Normal functionality
                            embed.set_field_at(-1, name='Retrieved ban details', value=longString)
                            await msg.edit(embed=embed)
                            await msg.add_reaction(self.emojis['collapse'])
                        else:  # Expand from Plaintext
                            await msg.edit(content=None, embed=embed)
                            for reaction in [self.emojis['expand'], self.emojis['collapse']]:
                                await msg.add_reaction(reaction)
                    elif r[0].emoji == self.emojis['collapse']:
                        await msg.clear_reactions()
                        if len(msg.embeds) > 0 and 'Banned because' in embed.fields[-1].value or '📜' in embed.fields[-1].value:
                            embed.set_field_at(-1, name='Retrieved ban details', value=f'React {self.emojis["expand"]} to expand')
                            await msg.edit(embed=embed)
                            await msg.add_reaction(self.emojis['expand'])
                            if settings['plainText']:
                                await msg.add_reaction(self.emojis['collapse'])
                        else:  # Embed to plaintext
                            await msg.edit(content=content, embed=None)
                    elif settings['plainText']:
                        await msg.clear_reactions()
                        await msg.edit(content=None, embed=embed)
                        for reaction in [self.emojis['expand'], self.emojis['collapse']]:
                            await msg.add_reaction(r)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """[DISCORD API METHOD] Called when member changes roles or nickname"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(after.guild))
        msg = None
        if await logEnabled(after.guild, 'member') and any([before.nick != after.nick, before.roles != after.roles]):
            content = ''
            auditLogFail = False
            settings = await getCyberAttributes(after.guild, 'member')
            color = blue[await utility.color_theme(after.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed = discord.Embed(color=color)
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                url = await self.imageToURL(after.display_avatar)
                if settings['thumbnail'] in (1, 2, 4):
                    embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4):
                    embed.set_author(name=after.display_name, icon_url=url)
            if await memberGlobal(before.guild) != 1:
                content = f"{before}'s server attributes were updated"
                embed.description = f'{self.emojis["member"] if settings["context"][1] > 0 else ""}{"Recipient" if settings["context"][1] < 2 else ""}: {before.mention} ({before.display_name})'
                if before.roles != after.roles:
                    br = len(before.roles)
                    ar = len(after.roles)
                    embed.title = (
                        f"""{f"{self.emojis['member']}🚩{self.emojis['darkGreenPlus']}" if settings['context'][0] > 0 else ''}{f'Member gained {"roles" if ar - br > 1 else "a role"}' if settings['context'][0] < 2 else ''}"""
                        if ar > br
                        else f"""{f"{self.emojis['member']}🚩❌" if settings['context'][0] > 0 else ''}{f'Member lost {"roles" if br - ar > 1 else "a role"}' if settings['context'][0] < 2 else ''}"""
                        if ar < br
                        else f"""{f"{self.emojis['member']}🚩✏" if settings['context'][0] > 0 else ''}{'Member roles moodified' if settings['context'][0] < 2 else ''}"""
                    )
                    try:
                        log = await after.guild.audit_logs().get(action=discord.AuditLogAction.member_role_update, target__id=after.id)
                        if settings['botLogging'] == 0 and log.user.bot:
                            return
                        elif settings['botLogging'] == 1 and log.user.bot:
                            settings['plainText'] = True
                        embed.description += f'\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Moderator" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name})'
                        if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                            settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                        ):
                            url = await self.imageToURL(log.user)
                            content = f"{log.user} updated {before}'s server attributes"
                            if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                                embed.set_thumbnail(url=url)
                            if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                                embed.set_author(name=log.user.display_name, icon_url=url)
                        if after.guild.id not in gimpedServers:
                            await updateLastActive(log.user, discord.utils.utcnow(), "updated someone's roles")
                    except:
                        pass
                    added = sorted([r for r in after.roles if r not in before.roles], key=lambda r: r.position)
                    removed = sorted(
                        [r for r in before.roles if r not in after.roles and r.id in [role.id for role in after.guild.roles]],
                        key=lambda r: r.position,
                    )
                    for r in added:
                        if after.guild.get_role(r):
                            self.roles[r.id] = r.members
                    for r in removed:
                        if after.guild.get_role(r):
                            self.roles[r.id] = r.members
                    if len(added) > 0:
                        embed.add_field(name=f'Role{"s" if len(added) > 1 else ""} added', value='\n'.join([r.name for r in added]))
                    if len(removed) > 0:
                        embed.add_field(name=f'Role{"s" if len(removed) > 1 else ""} removed', value='\n'.join([r.name for r in removed]))
                    beforePerms = utility.stringifyPermissions(before.guild_permissions)
                    afterPerms = utility.stringifyPermissions(after.guild_permissions)
                    if beforePerms != afterPerms:
                        lost = [p for p in beforePerms if p not in afterPerms]
                        gained = [p for p in afterPerms if p not in beforePerms]
                        lPK = []
                        gPK = []
                        lostList = []
                        gainedList = []
                        for r in removed:
                            rolePermissions = [
                                utility.pretty_permission(p[0])
                                for p in r.permissions
                                if utility.pretty_permission(p[0]) in beforePerms
                                and utility.pretty_permission(p[0]) not in afterPerms
                                and p in iter(r.permissions)
                                and utility.pretty_permission(p[0]) not in lPK
                            ]
                            if rolePermissions:
                                lPK += rolePermissions
                                lostList.append(f'{r.name}\n> {", ".join(rolePermissions)}')
                        for r in added:
                            rolePermissions = [
                                utility.pretty_permission(p[0])
                                for p in r.permissions
                                if utility.pretty_permission(p[0]) in afterPerms
                                and utility.pretty_permission(p[0]) not in beforePerms
                                and p in iter(r.permissions)
                                and utility.pretty_permission(p[0]) not in gPK
                            ]
                            if rolePermissions:
                                gPK += rolePermissions
                                gainedList.append(f'{r.name}\n> {", ".join(rolePermissions)}')
                        if len(lost) > 0:
                            embed.add_field(name='Lost permissions', value='\n'.join(lostList), inline=False)
                        if len(gained) > 0:
                            embed.add_field(name='Gained permissions', value='\n'.join(gainedList), inline=False)
                        self.memberPermissions[after.guild.id][after.id] = after.guild_permissions
                if before.nick != after.nick:
                    embed.title = f"""{f"{self.emojis['member'] if settings['library'] > 0 else '👤'}📄{self.emojis['edit'] if settings['library'] > 0 else '✏'}" if settings['context'][0] > 0 else ''}{"Member nickname updated" if settings['context'][0] < 2 else ''}"""
                    try:
                        log = await after.guild.audit_logs().get(action=discord.AuditLogAction.member_update, target__id=after.id)
                        embed.description += f'\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Moderator" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name})'
                        if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                            settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                        ):
                            url = await self.imageToURL(log.user.display_avatar)
                            content = f"{log.user} updated {before}'s server attributes"
                            if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                                embed.set_thumbnail(url=url)
                            if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                                embed.set_author(name=log.user.display_name, icon_url=url)
                        if after.guild.id not in gimpedServers:
                            await updateLastActive(log.user, discord.utils.utcnow(), 'updated a nickname')
                    except:
                        pass
                    oldNick = before.nick if before.nick is not None else '<No nickname>'
                    newNick = after.nick if after.nick is not None else '<No nickname>'
                    embed.add_field(name='Old nickname', value=oldNick)
                    embed.add_field(name='New nickname', value=newNick)
                if settings['embedTimestamp'] > 1:
                    embed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}"
                embed.set_footer(text=f'Member ID: {after.id}')
                try:
                    content = f"{log.user} updated {before}'s server attributes"
                except:
                    content = f"{before}'s server attributes were updated"
                content += utility.embedToPlaintext(embed)
                if auditLogFail:
                    content += (
                        f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{auditLogFail}`'
                    )
                if len(embed.fields) > 0:
                    msg = await (await logChannel(after.guild, 'member')).send(
                        content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                        embed=embed if not settings['plainText'] else None,
                        tts=settings['tts'],
                    )
                    if not settings['plainText'] and any((settings['flashText'], settings['tts'])):
                        await msg.edit(content=None)
                await self.archiveLogEmbed(after.guild, msg.id, embed, 'Member Update')
        if before.guild_permissions != after.guild_permissions:
            await self.CheckDisguardServerRoles(after, mode=0, reason='Member permissions changed')
        if before.guild_permissions != after.guild_permissions:
            asyncio.create_task(database.VerifyUser(before, self.bot), name=f'member_update - VerifyUser-{before.guild.id}-{before.id}')
        if msg:

            def reactionCheck(r, u):
                return r.message.id == msg.id and not u.bot

            while not self.bot.is_closed():
                try:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                except asyncio.TimeoutError:
                    break
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']:
                        await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']:
                        await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """[DISCORD API METHOD] Called when a member's status/activity changes"""
        # try:
        #     received = datetime.datetime.now()
        #     adjusted = discord.utils.utcnow() + datetime.timedelta(self.timeZone(after.guild))
        # except (KeyError, AttributeError): return
        # for g in self.bot.guilds:
        #     if after.id in [m.id for m in g.members]:
        #         targetServer = g
        #         break
        # Because this method is called for every server a member is in, we select an arbitrary server to avoid running this code multiple times for members in multiple servers with Disguard in it
        targetServer = after.mutual_guilds[0]
        if after.guild.id == targetServer.id and before.status != after.status:
            # if after.guild.id == targetServer.id:
            if after.status == discord.Status.offline and after.guild.id not in gimpedServers:
                await updateLastOnline(
                    after, discord.utils.utcnow()
                )  # If we "catch" a member going offline, mark them as last being online right now
            # if not any(a == discord.Status.offline for a in [before.status, after.status]) and any(a in [discord.Status.online, discord.Status.idle] for a in [before.status, after.status]) and any(a == discord.Status.dnd for a in [before.status, after.status]): await updateLastActive(after, discord.utils.utcnow(), 'left DND' if before.status == discord.Status.dnd else 'enabled DND')
            if (
                any(a == discord.Status.dnd for a in (before.status, after.status))
                and not any(a == discord.Status.offline for a in (before.status, after.status))
                and after.guild.id not in gimpedServers
            ):
                await updateLastActive(after, discord.utils.utcnow(), 'left DND' if before.status == discord.Status.dnd else 'enabled DND')
        if (
            after.guild.id == targetServer.id
            and before.activity != after.activity
            and any(a.type == discord.ActivityType.custom for a in (before.activity, after.activity) if a)
            and not any([before.status == discord.Status.offline, after.status == discord.Status.offline])
        ):
            # This is for LastActive information and custom status history
            # if after.guild.id == targetServer.id:
            #     for a in after.activities:
            #         if a.type == discord.ActivityType.custom:
            if (
                await self.privacyEnabledChecker(after, 'attributeHistory', 'statusHistory')
                and after.activity
                and after.activity.type == discord.ActivityType.custom
            ):
                try:
                    try:
                        user = await utility.get_user(after)
                    except KeyError:
                        return
                    a = after.activity
                    if not a:
                        return
                    prev = user.get('statusHistory', [{}])[-1]
                    proposed = {'e': None if not a.emoji else a.emoji.url if a.emoji.is_custom_emoji() else str(a.emoji), 'n': a.name if a else None}
                    if proposed != {'e': prev.get('emoji'), 'n': prev.get('name')}:
                        # if not (await database.GetUser(after)).get('customStatusHistory'):
                        asyncio.create_task(
                            database.AppendCustomStatusHistory(
                                after, None if not a.emoji else a.emoji.url if a.emoji.is_custom_emoji() else str(a.emoji), a.name if a.name else None
                            ),
                            name=f'presence_update - AppendCustomStatusHistory-{after.guild.id}-{after.id}',
                        )
                except Exception as e:
                    print(f'CSH error: {e}')
                    traceback.print_exc()
                # except TypeError: asyncio.create_task(database.AppendCustomStatusHistory(after, None if a.emoji is None else str(a.emoji.url) if a.emoji.is_custom_emoji() else str(a.emoji), a.name)) #If the customStatusHistory is empty, we create the first entry
            # newMemb = before.guild.get_member(before.id)
            # if before.status == newMemb.status and before.name != newMemb.name: await updateLastActive(after, discord.utils.utcnow(), 'changed custom status')
            if after.guild.id not in gimpedServers:
                await updateLastActive(after, discord.utils.utcnow(), 'changed custom status')

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """[DISCORD API METHOD] Called when a user changes their global username, avatar, or discriminator"""
        rawReceived = discord.utils.utcnow()
        servers: typing.List[discord.Guild] = after.mutual_guilds
        membObj = servers[0].get_member(after.id)  # Getting the discord.Member object for later use
        embed = discord.Embed(description='')
        content = f'{after.display_name} updated their global attrubutes'
        legacyTitleEmoji = []
        newTitleEmoji = []  # We need two separate lists because each server might have different emoji display settings
        titles = []
        f = []
        try:
            thumbnailURL = (await utility.get_user(after))['avatarHistory'][-1]['imageURL']
        except (TypeError, AttributeError, KeyError):
            try:
                thumbnailURL = await self.imageToURL(before.display_avatar)
            except discord.NotFound:
                thumbnailURL = ''
        embed.set_thumbnail(url=thumbnailURL)
        if before.display_avatar != after.display_avatar:
            titles.append('Profile Picture')
            legacyTitleEmoji.append('🖼')
            newTitleEmoji.append(self.emojis['imageAdd'])
            url = await self.imageToURL(after.display_avatar)
            embed.set_image(url=url)  # New avatar
            embed.add_field(
                name='Profile picture updated', value=f'Old: [Thumbnail to the right]({thumbnailURL})\nNew: [Image below]({url})', inline=False
            )
            content += '\n•Profile picture'
            await updateLastActive(after, discord.utils.utcnow(), 'updated their profile picture')
            if await self.privacyEnabledChecker(after, 'attributeHistory', 'avatarHistory'):
                asyncio.create_task(database.AppendAvatarHistory(after, url), name=f'user_update - AppendAvatarHistory-{after.id}')
        if before.discriminator != after.discriminator:
            titles.append('Discriminator')
            legacyTitleEmoji.append('🔢')
            newTitleEmoji.append(self.emojis['discriminator'])
            embed.add_field(name='Old discriminator', value=before.discriminator)
            embed.add_field(name='New discriminator', value=after.discriminator)
            content += '\n•Discriminator'
            await updateLastActive(after, discord.utils.utcnow(), 'updated their discriminator')
        if before.name != after.name:
            titles.append('Username')
            legacyTitleEmoji.append('📄')
            newTitleEmoji.append(self.emojis['richPresence'])
            embed.add_field(name='Old username', value=before.name)
            embed.add_field(name='New username', value=after.name)
            content += '\n•Discriminator'
            await updateLastActive(after, discord.utils.utcnow(), 'updated their username')
            if await self.privacyEnabledChecker(after, 'attributeHistory', 'usernameHistory'):
                asyncio.create_task(database.AppendUsernameHistory(after), name=f'user_update - AppendUsernameHistory-{after.id}')
            asyncio.create_task(database.VerifyUser(membObj, self.bot), name=f'user_update - VerifyUser-{after.id}')
        if before.display_name != after.display_name:
            titles.append('Display name')
            legacyTitleEmoji.append('📄')
            newTitleEmoji.append(self.emojis['richPresence'])
            embed.add_field(name='Old display name', value=before.display_name)
            embed.add_field(name='New display name', value=after.display_name)
            content += '\n•Display name'
            await updateLastActive(after, discord.utils.utcnow(), 'updated their display name')
            if await self.privacyEnabledChecker(after, 'attributeHistory', 'displayNameHistory'):
                asyncio.create_task(database.AppendDisplaynameHistory(after), name=f'user_update - AppendDisplaynameHistory-{after.id}')
        embed.set_footer(text=f'User ID: {after.id}')
        for server in servers:
            try:
                if await logEnabled(server, 'member') and await memberGlobal(server) != 0:
                    adjusted = rawReceived + datetime.timedelta(hours=await utility.time_zone(server))
                    settings = await getCyberAttributes(server, 'member')
                    color = blue[await utility.color_theme(server)] if settings['color'][1] == 'auto' else settings['color'][1]
                    newEmbed = copy.deepcopy(embed)
                    newContent = content + utility.embedToPlaintext(embed)
                    # We have to customize embeds for each specific server. First, embed title and description
                    titleEmoji = legacyTitleEmoji if settings['library'] == 0 else [str(emoji) for emoji in newTitleEmoji]
                    titleBase = f"""{f"{self.emojis['member'] if settings['library'] > 0 else '👤'}{''.join(titleEmoji)}{self.emojis['edit'] if settings['library'] > 0 else '✏'}" if settings['context'][0] > 0 else ''}"""
                    if len(titles) == 3 and settings['context'][0] < 2:
                        newEmbed.title = f"{titleBase}User's {', '.join(titles)} updated"
                    elif len(titles) != 3:
                        newEmbed.title = f"{titleBase}User's {' & '.join(titles)} updated"
                    if before.name == after.name:
                        newEmbed.description = f"""{f"{self.emojis['member'] if settings['library'] > 0 else '👤'}" if settings['context'][1] > 0 else ''}{'Member' if settings['context'][1] < 2 else ''}: {after.mention} ({after.display_name})"""
                    if settings['embedTimestamp'] > 1:
                        newEmbed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(rawReceived)}"
                    # Next, color and timestamp
                    newEmbed.color = color
                    if settings['embedTimestamp']:
                        newEmbed.timestamp = rawReceived
                    # Then, thumbnail/author
                    if any(a > 0 for a in (settings['thumbnail'], settings['author'])) and before.display_avatar == after.display_avatar:
                        url = await self.imageToURL(after.display_avatar)
                        if settings['thumbnail'] > 0 and utility.empty(embed.thumbnail.url):
                            newEmbed.set_thumbnail(url=url)
                        if settings['author'] > 0 and utility.empty(embed.author.name):
                            newEmbed.set_author(name=after.display_name, icon_url=url)
                    msg = await (await logChannel(server, 'member')).send(
                        content=newContent if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                        embed=newEmbed if not settings['plainText'] else None,
                        files=f if not settings['plainText'] else [],
                        tts=settings['tts'],
                    )
                    if msg.content and not settings['plainText'] and any((settings['flashText'], settings['tts'])):
                        await msg.edit(content=None)  # TODO: reduce unnecessary edits
                    await self.archiveLogEmbed(server, msg.id, embed, 'User Update')
            except:
                pass
        for s in servers:
            asyncio.create_task(
                database.VerifyMember(s.get_member(after.id), warnings=(await utility.get_server(s))['antispam'].get('warn', 3)),
                name=f'user_update - VerifyMember-{s.id}-{after.id}',
            )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """[DISCORD API METHOD] Called when the bot joins a server"""
        await self.bot.change_presence(
            status=discord.Status.online, activity=discord.Activity(name=f'{len(self.bot.guilds)} servers', type=discord.ActivityType.watching)
        )
        embed = discord.Embed(
            title=f'{self.emojis["darkGreenPlus"]}Joined server',
            description=f'{guild.name}\n{guild.member_count} Members\nCreated {utility.DisguardRelativeTimestamp(guild.created_at)}',
            color=green[1],
        )
        embed.set_footer(text=guild.id)
        await self.globalLogChannel.send(embed=embed)
        asyncio.create_task(
            database.VerifyServer(guild, self.bot, new=True, includeMembers=guild.members), name=f'guild_join - VerifyServer-{guild.id}'
        )
        asyncio.create_task(database.VerifyUsers(self.bot, guild.members), name=f'guild_join - VerifyUsers-{guild.id}')
        # TODO: Improve teh server join experience
        content = f"Thank you for inviting me to {guild.name}!\n\n--Quick Start Guide--\n🔗Disguard Website: <https://disguard.netlify.app>\n{qlf}{qlf}Contains links to help page, server configuration, Disguard's official server, inviting the bot to your own server, and my GitHub repository\n🔗Configure your server's settings: <https://disguard.herokuapp.com/manage/{guild.id}>"
        content += f'\nℹDisguard uses slash commands for interacting with commands. A help guide is available with `/help` or on the website.\n\n❔Need help with anything, or just have a question? My team is more than happy to resolve your questions or concerns - you can quickly get in touch with my developer in the following ways:\n{qlf}Open a support ticket using the `/ticket` command\n{qlf}Join my support server: <https://discord.gg/xSGujjz>'
        try:
            target = await database.CalculateModeratorChannel(guild, self.bot, False)
        except:
            if guild.system_channel:
                target = guild.system_channel
            else:
                for channel in guild.text_channels:
                    if 'general' in channel.name:
                        target = channel
                        break
        try:
            await target.send(content)
        except:
            pass
        await self.CheckDisguardServerRoles(guild.members, mode=1, reason='Bot joined a server')
        indexing_cog: Indexing.Indexing = self.bot.get_cog('Indexing')
        if indexing_cog:
            await indexing_cog.index_channels(guild.text_channels)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """[DISCORD API METHOD] Called when a server's attributes are updated"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(after))
        if await logEnabled(before, 'server'):
            content = 'Server settings were updated'
            settings = await getCyberAttributes(after, 'server')
            color = blue[await utility.color_theme(after)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed = discord.Embed(
                title=f'{(self.emojis["serverUpdate"] if settings["library"] > 0 else "✏") if settings["context"][0] > 0 else ""}{"Server updated" if settings["context"][0] < 2 else ""}',
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
                url = await self.imageToURL(after.icon)
                if settings['thumbnail'] in (1, 2, 4):
                    embed.set_thumbnail(url=url)
                if settings['author'] in (1, 2, 4):
                    embed.set_author(name=after.display_name, icon_url=url)
            if await readPerms(before, 'server'):
                try:
                    log = await after.audit_logs().get(action=discord.AuditLogAction.guild_update)
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description = f"""{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Updated by' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} updated server settings'
                    if after.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'updated a server')
                except Exception as e:
                    content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            if before.afk_channel != after.afk_channel:
                embed.add_field(
                    name='AFK Channel',
                    value=f"{before.afk_channel.name if before.afk_channel else '<None>'} → **{after.afk_channel.name if after.afk_channel else '<None>'}**",
                )
            if before.afk_timeout != after.afk_timeout:
                timeouts = [[before.afk_timeout, 'second'], [after.afk_timeout, 'second']]
                for t in timeouts:
                    if t[0] and t[0] >= 60:
                        t[0] //= 60
                        t[1] = 'minute'
                        if t[0] >= 60:
                            t[0] //= 60
                            t[1] = 'hour'
                embed.add_field(
                    name='AFK Timeout',
                    value=f'{timeouts[0][0]} {timeouts[0][1]}{"s" if timeouts[0][0] != 1 else ""} → **{timeouts[1][0]} {timeouts[1][1]}{"s" if timeouts[1][0] != 1 else ""}**',
                )
            if before.mfa_level != after.mfa_level:
                values = {0: False, 1: True}
                embed.add_field(name='2FA Requirement for Mods', value=f'{values[before.mfa_level]} → **{after.mfa_level}**')
            if before.name != after.name:
                embed.add_field(name='Name', value=f'{before.name} → **{after.name}**')
            if before.owner != after.owner:
                embed.add_field(
                    name='Owner',
                    value=f'{before.owner.mention} ({before.owner.display_name}) → **{after.owner.mention} ({after.owner.display_name})**',
                )
                o = f'{after.owner.mention} ({after.owner.display_name}), ownership of {after.name} has been transferred to you from {before.owner.mention} ({before.owner.display_name})'
                if not content:
                    content = o
                else:
                    content += f'\n{o}'
                await self.CheckDisguardServerRoles(after.members, mode=0, reason='Server owner changed')
            if before.default_notifications != after.default_notifications:
                values = {'all_messages': 'All messages', 'only_mentions': 'Only mentions'}
                embed.add_field(
                    name='Default Notifications',
                    value=f'{values[before.default_notifications.name]} → **{values[after.default_notifications.name]}**',
                )
            if before.explicit_content_filter != after.explicit_content_filter:
                values = {'disabled': 'Disabled', 'no_role': 'Filter for members without a role', 'all_members': 'Filter for everyone'}
                embed.add_field(
                    name='Explicit Content Filter',
                    value=f'{values[before.explicit_content_filter.name]} → **{values[after.explicit_content_filter.name]}**',
                )
            if before.system_channel != after.system_channel:
                embed.add_field(
                    name='System channel',
                    value=f"{f'{before.system_channel.mention} ({before.system_channel.name})' if before.system_channel else '<None>'} → {f'{after.system_channel.mention} ({after.system_channel.name})' if after.system_channel else '<None>'}",
                )
            if before.icon != after.icon:
                thumbURL = await self.imageToURL(before.icon.with_static_format('png'))
                imageURL = await self.imageToURL(after.icon.with_static_format('png'))
                embed.set_thumbnail(url=thumbURL)
                embed.set_image(url=imageURL)
                embed.add_field(name='Server icon updated', value=f'Old: [Thumbnail to the right]({thumbURL})\nNew: [Image below]({imageURL})')
            asyncio.create_task(database.VerifyServer(after, self.bot), name=f'guild_update - VerifyServer-{after.id}')
            if len(embed.fields) > 0:
                reactions = ['ℹ']
                if settings['embedTimestamp'] > 1:
                    embed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}"
                content += utility.embedToPlaintext(embed)
                message: discord.Message = await (await logChannel(before, 'server')).send(
                    content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                    embed=embed if not settings['plainText'] else None,
                    tts=settings['tts'],
                    allowed_mentions=discord.AllowedMentions(users=[after.owner]),
                )
                if any((settings['tts'], settings['flashText'])) and not settings['plainText']:
                    await message.edit(content=None)
                await self.archiveLogEmbed(after, message.id, embed, 'Server Update')
                if not settings['plainText']:
                    for r in reactions:
                        await message.add_reaction(r)
                final = copy.deepcopy(embed)
                while not self.bot.is_closed():

                    def reactionCheck(r, u):
                        return r.message.id == message.id and not u.bot

                    try:
                        result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                    except asyncio.TimeoutError:
                        break
                    if str(result[0]) == 'ℹ':
                        if 'Loading server information' not in embed.description:
                            embed.description += f'\n\n{self.loading}Loading server information'
                        await message.edit(embed=embed)
                        logs, bans, hooks, invites = None, None, None, None
                        try:
                            logs = [log async for log in after.audit_logs(limit=None)]
                            bans = [ban async for ban in after.bans(limit=None)]
                            hooks = await after.webhooks()
                            invites = await after.invites()
                        except:
                            pass
                        info: Info.Info = self.bot.get_cog('Info')
                        new = await info.ServerInfo(after, logs, bans, hooks, invites)
                        if embed.author.display_name:
                            new.set_author(icon_url=url, name=log.user.name)
                        await message.edit(embed=new)
                        await message.clear_reactions()
                        await message.add_reaction('⬅')

                        def backCheck(r, u):
                            return str(r) == '⬅' and r.message.id == message.id and u.id == result[1].id

                        try:
                            await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                        except asyncio.TimeoutError:
                            pass
                        await message.edit(content=content, embed=final)
                        await message.clear_reactions()
                        for r in reactions:
                            await message.add_reaction(r)
                    elif result[0].emoji == self.emojis['collapse'] and len(message.embeds) > 0:
                        await message.edit(content=content, embed=None)
                        await message.clear_reactions()
                    elif settings['plainText'] and len(message.embeds) < 1:
                        await message.edit(content=None, embed=embed)
                        await message.clear_reactions()
                        reactions.append(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """[DISCORD API METHOD] Called when the bot leaves a server"""
        embed = discord.Embed(title='❌Left server', description=guild.name, color=red[1])
        embed.set_footer(text=guild.id)
        await self.globalLogChannel.send(embed=embed)
        await self.bot.change_presence(
            status=discord.Status.online, activity=discord.Activity(name=f'{len(self.bot.guilds)} servers', type=discord.ActivityType.watching)
        )
        asyncio.create_task(database.VerifyServer(guild, self.bot), name=f'guild_remove - VerifyServer-{guild.id}')
        await self.CheckDisguardServerRoles(guild.members, mode=2, reason='Bot left a server')
        path = f'Attachments/{guild.id}'
        shutil.rmtree(path)
        await database.VerifyUsers(self.bot, guild.members)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        """[DISCORD API METHOD] Called when a server role is created"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(role.guild))
        msg = None
        if await logEnabled(role.guild, 'role'):
            content = f'The role "{role.name}" was created'
            settings = await getCyberAttributes(role.guild, 'role')
            color = green[await utility.color_theme(role.guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            embed = discord.Embed(
                title=f"""{(self.emojis['roleCreate'] if settings['library'] > 1 else f"🚩{self.emojis['darkGreenPlus']}") if settings['context'][0] > 0 else ''}{'Role created' if settings['context'][0] < 2 else ''}""",
                description=f"""{(self.emojis["richPresence"] if settings['library'] > 0 else '📄') if settings['context'][1] > 0 else ''}{'Name' if settings['context'][1] < 2 else ''}: {role.name}"""
                if role.name != 'new role'
                else '',
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if role.display_icon:
                embed.set_thumbnail(url=role.display_icon.url)
            embed.set_footer(text=f'Role ID: {role.id}')
            if await readPerms(role.guild, 'role'):
                try:
                    log = await role.guild.audit_logs().get(action=discord.AuditLogAction.role_create)
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description += f"""\n👮‍♂️Created by: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} created the role "{role.name}"'
                    if role.guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'created a role')
                except Exception as e:
                    content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            if settings['embedTimestamp'] > 1:
                embed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}"
            content += utility.embedToPlaintext(embed)
            msg: discord.Message = await (await logChannel(role.guild, 'role')).send(
                content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            if any((settings['tts'], settings['flashText'])) and not settings['plainText']:
                await msg.edit(content=None)
            await self.archiveLogEmbed(role.guild, msg.id, embed, 'Role Create')
        self.roles[role.id] = role.members
        asyncio.create_task(database.VerifyServer(role.guild, self.bot), name=f'guild_role_create - VerifyServer-{role.guild.id}')
        if msg:

            def reactionCheck(r, u):
                return r.message.id == msg.id and not u.bot

            while not self.bot.is_closed():
                try:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                except asyncio.TimeoutError:
                    break
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']:
                        await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']:
                        await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """[DISCORD API METHOD] Called when a server role is deleted"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(role.guild))
        message = None
        roleMembers = []
        if await logEnabled(role.guild, 'role'):
            content = f'The role "{role.name}" was deleted'
            settings = await getCyberAttributes(role.guild, 'role')
            color = red[await utility.color_theme(role.guild)] if settings['color'][2] == 'auto' else settings['color'][2]
            embed = discord.Embed(
                title=f"""{(self.emojis['roleDelete'] if settings['library'] > 1 else '🚩❌') if settings['context'][0] > 0 else ''}Role deleted {self.loading}""",
                description=f'{"🚩" if settings["context"][1] > 0 else ""}{"Role" if settings["context"][1] < 2 else ""}: {role.name}',
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if role.display_icon:
                embed.set_thumbnail(url=role.display_icon.url)
            embed.set_footer(text='Role ID: {}'.format(role.id))
            if await readPerms(role.guild, 'role'):
                try:
                    log = await role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete).next()
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description += f"""\n👮‍♂️Deleted by: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} deleted the role "{role.name}"'
                    if role.guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'deleted a role')
                except:
                    pass  # Exception as e: content+=f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            content += utility.embedToPlaintext(embed)
            message: discord.Message = await (await logChannel(role.guild, 'role')).send(
                content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            # Cache role members, and expel them upon role deletion. work for 2021.
            roleMembers = self.roles.get(role.id)
            if roleMembers:
                membersWhoLost = (
                    '\n'.join([f'👤{m.display_name}' for m in roleMembers])
                    if len(roleMembers) < 20
                    else '👤'.join([m.name for m in roleMembers])
                    if len(roleMembers) < 100
                    else ''
                )  # Last branch prevents unnecessary computations
                embed.description += f'\n{self.emojis["details"] if settings["context"][1] > 0 else ""}' + (
                    'Nobody lost this role upon its deletion'
                    if len(roleMembers) < 1
                    else f"[{len(roleMembers)} members lost this role upon its deletion]({message.jump_url} '{membersWhoLost}')"
                    if len(roleMembers) < 100
                    else f'{len(roleMembers)} members lost this role upon its deletion'
                )
                embed = await self.PermissionChanges(roleMembers, message, embed)
            if settings['embedTimestamp'] > 1:
                embed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}"
            embed.title = f"""{(self.emojis['roleDelete'] if settings['library'] > 1 else f'🚩{self.emojis["delete"]}') if settings['context'][0] > 0 else ''}{'Role deleted' if settings['context'][0] < 2 else ''}"""
            if any((settings['tts'], settings['flashText'])) and not settings['plainText']:
                await message.edit(content=None)
            await self.archiveLogEmbed(role.guild, message.id, embed, 'Role Update')
            if not settings['plainText']:
                await message.edit(embed=embed)
            reactions = ['ℹ']
            if not settings['plainText']:
                for r in reactions:
                    await message.add_reaction(r)
            final, roleInfo = copy.deepcopy(embed), None
        await self.CheckDisguardServerRoles(
            roleMembers if roleMembers else role.guild.members, mode=2, reason='Server role was deleted; member lost permissions'
        )
        asyncio.create_task(
            database.VerifyServer(role.guild, self.bot, includeMembers=self.roles.get(role.id, role.guild.members)),
            name=f'guild_role_delete - VerifyServer-{role.guild.id}',
        )
        asyncio.create_task(
            database.VerifyUsers(self.bot, self.roles.get(role.id, role.guild.members)), name=f'guild_role_delete - VerifyUsers-{role.guild.id}'
        )
        self.roles.pop(role.id, None)
        if message:
            # again, everything below this is not necessarily syntactically correct with the new changes
            while not self.bot.is_closed():

                def reactionCheck(r, u):
                    return r.message.id == message.id and not u.bot

                try:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                except asyncio.TimeoutError:
                    break
                if str(result[0]) == 'ℹ':
                    if 'Loading role information' not in embed.description:
                        embed.description += f'\n\n{self.loading}Loading role information'
                    await message.edit(embed=embed)
                    try:
                        logs = [log async for log in role.guild.audit_logs(limit=None)]
                    except:
                        logs = None
                    if not roleInfo:
                        roleInfo = await self.RoleInfo(role, logs)
                        if embed.author.name:
                            roleInfo.set_author(icon_url=url, name=log.user.display_name)
                    await message.edit(embed=roleInfo)
                    await message.clear_reactions()
                    await message.add_reaction('⬅')

                    def backCheck(r, u):
                        return str(r) == '⬅' and r.message.id == message.id and u.id == result[1].id

                    try:
                        await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                    except asyncio.TimeoutError:
                        pass
                    await message.edit(content=content, embed=final)
                    await message.clear_reactions()
                    for r in reactions:
                        await message.add_reaction(r)
                elif result[0].emoji == self.emojis['collapse'] and len(message.embeds) > 0:
                    await message.edit(content=content, embed=None)
                    await message.clear_reactions()
                elif settings['plainText'] and len(message.embeds) < 1:
                    await message.edit(content=None, embed=embed)
                    await message.clear_reactions()
                    reactions.append(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """[DISCORD API METHOD] Called when a server role is updated"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(after.guild))
        message = None
        if await logEnabled(before.guild, 'role'):
            content = f'The role "{before.name}" was updated'
            settings = await getCyberAttributes(after.guild, 'role')
            color = blue[await utility.color_theme(after.guild)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed = discord.Embed(
                title=f"""{(self.emojis['roleEdit'] if settings['library'] > 1 else '🚩✏')}{'Role was updated' if settings['context'][0] < 2 else ''}""",
                description=f"""{'🚩' if settings['context'][1] > 0 else ''}{'Role' if settings['context'][1] < 2 else ''}: {after.mention}{f" ({after.name})" if after.name == before.name else ""}""",
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if after.name != before.name:
                embed.description += (
                    f"""\n{self.emojis['richPresence'] if settings['context'][1] > 0 else ''}Name: {before.name} → **{after.name}**"""
                )
            if await readPerms(before.guild, 'role'):
                try:
                    log = await after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update).next()
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description += f"""\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Updated by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} updated the role {before.name}'
                    if after.guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'updated a role')
                except:
                    pass
            embed.set_footer(text=f'Role ID: {before.id}')
            reactions = ['ℹ']
            if before.color != after.color:
                embed.add_field(name='Old color', value=f'RGB{before.color.to_rgb()}\nHex: {before.color}\nReact {self.emojis["shuffle"]} to display')
                embed.add_field(name='New color', value=f'**RGB{after.color.to_rgb()}\nHex: {after.color}\nDisplayed on embed border**')
                embed.color = after.color
                reactions.append(self.emojis['shuffle'])
            if before.hoist != after.hoist:
                embed.add_field(name='Displayed separately', value=f'{before.hoist} → **{after.hoist}**')
            if before.mentionable != after.mentionable:
                embed.add_field(name='Mentionable', value=f'{before.mentionable} → **{after.mentionable}**')
            if before.display_icon != after.display_icon:
                thumbURL = await self.imageToURL(before.display_icon)
                imageURL = await self.imageToURL(after.display_icon)
                embed.set_thumbnail(url=thumbURL)
                embed.set_image(url=imageURL)
                embed.add_field(name='Role icon updated', value=f'Old: [Thumbnail to the right]({thumbURL})\nNew: [Image below]({imageURL})')
            if before.permissions != after.permissions:
                afterPermissions = list(iter(after.permissions))
                for i, p in enumerate(iter(before.permissions)):
                    k, v = p[0], p[1]
                    if v != afterPermissions[i][1]:
                        embed.add_field(name=utility.pretty_permission(k), value=f'{v} → **{afterPermissions[i][1]}**')
            if len(embed.fields) > 0 or before.name != after.name:
                content += utility.embedToPlaintext(embed)
                message: discord.Message = await (await logChannel(after.guild, 'role')).send(
                    content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                    embed=embed if not settings['plainText'] else None,
                    tts=settings['tts'],
                )
                if not settings['plainText']:
                    for reac in reactions:
                        await message.add_reaction(reac)
                embed = await self.PermissionChanges(after.members, message, embed, permissionsChanged=before.permissions != after.permissions)
                if settings['embedTimestamp'] > 1:
                    embed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}"
                if any((settings['tts'], settings['flashText'])) and not settings['plainText']:
                    await message.edit(content=None)
                if not settings['plainText']:
                    await message.edit(embed=embed)
                await self.archiveLogEmbed(after.guild, message.id, embed, 'Role Update')
                if before.permissions != after.permissions:
                    for m in after.members:
                        self.memberPermissions[after.guild.id][m.id] = m.guild_permissions
        await self.CheckDisguardServerRoles(after.guild.members, mode=0, reason="Server role was updated; member's permissions changed")
        if before.name != after.name:
            asyncio.create_task(
                database.VerifyServer(after.guild, self.bot, includeMembers=after.members if before.permissions != after.permissions else []),
                name=f'guild_role_update - VerifyServer-{after.guild.id}',
            )
        for member in after.members:
            await database.VerifyUser(member, self.bot)
        if message and len(embed.fields) > 0 or before.name != after.name:
            # cutoff
            final = copy.deepcopy(embed)
            while not self.bot.is_closed():

                def reactionCheck(r, u):
                    return r.message.id == message.id and not u.bot

                try:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                except asyncio.TimeoutError:
                    break
                if str(result[0]) == 'ℹ':
                    await message.clear_reactions()
                    if 'Loading role information' not in embed.description:
                        embed.description += f'\n\n{self.loading}Loading role information'
                    await message.edit(embed=embed)
                    logs = None
                    try:
                        logs = [log async for log in after.audit_logs(limit=None)]
                    except:
                        pass
                    new = await self.RoleInfo(after, logs)
                    if embed.author.name:
                        new.set_author(icon_url=url, name=log.user.display_name)
                    await message.edit(embed=new)
                    await message.add_reaction('⬅')

                    def backCheck(r, u):
                        return str(r) == '⬅' and r.message.id == message.id and u.id == result[1].id

                    try:
                        await self.bot.wait_for('reaction_add', check=backCheck, timeout=120)
                    except asyncio.TimeoutError:
                        pass
                    await message.edit(content=content, embed=final)
                    await message.clear_reactions()
                elif str(result[0]) == '🔀':
                    await message.remove_reaction(result[0], result[1])
                    setAt = 0  # field index
                    clearAt = 1
                    toSet = before
                    toClear = after
                    embed.color = before.color
                    if '🔀' in embed.fields[1].value:  # new color value
                        setAt = 1
                        clearAt = 0
                        toSet = after
                        toClear = before
                        embed.color = after.color
                    embed.set_field_at(
                        setAt, name=embed.fields[setAt].name, value=f'**RGB{toSet.color.to_rgb()}\nHex: {toSet.color}\nDisplayed on embed border**'
                    )
                    embed.set_field_at(
                        clearAt, name=embed.fields[clearAt].name, value=f'RGB{toClear.color.to_rgb()}\nHex: {toClear.color}\nReact 🔀 to display'
                    )
                    await message.edit(embed=embed)
                elif result[0].emoji == self.emojis['collapse'] and len(message.embeds) > 0:
                    await message.edit(content=content, embed=None)
                    await message.clear_reactions()
                elif settings['plainText'] and len(message.embeds) < 1:
                    await message.edit(content=None, embed=embed)
                    await message.clear_reactions()
                    reactions.append(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: typing.List[discord.Emoji], after: typing.List[discord.Emoji]):
        """[DISCORD API METHOD] Called when emoji list is updated (creation, update, deletion)"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(guild))
        msg = None
        if await logEnabled(guild, 'emoji'):
            content = 'Server emoji list updated'
            settings = await getCyberAttributes(guild, 'emoji')
            color = green[await utility.color_theme(guild)] if settings['color'][0] == 'auto' else settings['color'][0]
            embed = discord.Embed(
                title=f"""{(f'{self.emojis["emojiCreate"]}' if settings['library'] == 2 else f"{self.emojis['emoji']}{self.emojis['darkGreenPlus']}" if settings['library'] == 1 else f"{self.emojis['minion']}{self.emojis['darkGreenPlus']}") if settings['context'][0] > 0 else ""}{'Emoji created' if settings['context'][0] < 2 else ''}""",
                description='',
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            logType = discord.AuditLogAction.emoji_create
            if len(before) > len(after):  # Emoji was deleted
                embed.title = f"""{(f'{self.emojis["emojiDelete"]}' if settings['library'] == 2 else f"{self.emojis['emoji']}{self.emojis['delete']}" if settings['library'] == 1 else f"{self.emojis['minion']}{self.emojis['delete']}") if settings['context'][0] > 0 else ""}{'Emoji deleted' if settings['context'][0] < 2 else ''}"""
                embed.color = red[await utility.color_theme(guild)] if settings['color'][2] == 'auto' else settings['color'][2]
                logType = discord.AuditLogAction.emoji_delete
            elif len(after) == len(before):
                embed.title = f"""{(f'{self.emojis["emojiUpdate"]}' if settings['library'] == 2 else f"{self.emojis['emoji']}✏" if settings['library'] == 1 else f"{self.emojis['minion']}✏") if settings['context'][0] > 0 else ""}{'Emoji list updated' if settings['context'][0] < 2 else ''}"""
                embed.color = blue[await utility.color_theme(guild)] if settings['color'][1] == 'auto' else settings['color'][1]
                logType = discord.AuditLogAction.emoji_update
            # utilize dictionaries for speed purposes, to prevent necessity of nested loops
            beforeDict = {}
            afterDict = {}
            footerIDList = []
            for emoji in before:
                beforeDict.update({emoji.id: {'name': emoji.name, 'url': emoji.url, 'raw': str(emoji)}})
            for emoji in after:
                afterDict.update({emoji.id: {'name': emoji.name, 'url': emoji.url, 'raw': str(emoji)}})
            for eID, emoji in beforeDict.items():
                if eID not in afterDict:  # emoji deleted
                    embed.add_field(name=f'{self.emojis["delete"]}{emoji["name"]}', value=f'{emoji["raw"]} • [View image]({emoji["url"]})')
                    if not embed.image.url and settings['thumbnail'] in (1, 2, 4):
                        embed.set_image(url=emoji['url'])
                    footerIDList.append(eID)
            for eID, emoji in afterDict.items():
                if eID not in beforeDict:  # emoji created
                    embed.add_field(name=f'{self.emojis["darkGreenPlus"]}{emoji["name"]}', value=f'{emoji["raw"]} • [View image]({emoji["url"]})')
                    if not embed.image.url and settings['thumbnail'] in (1, 2, 4):
                        embed.set_image(url=emoji['url'])
                    footerIDList.append(eID)
                elif eID in beforeDict and beforeDict[eID]['name'] != emoji['name']:  # name updated
                    embed.add_field(name=f'{beforeDict[eID]["name"]} → **{emoji["name"]}**', value=emoji['raw'])
                    if not embed.image.url and settings['thumbnail'] in (1, 2, 4):
                        embed.set_image(url=emoji['url'])
                    footerIDList.append(eID)
            content += utility.embedToPlaintext(embed)
            if await readPerms(guild, 'emoji'):
                try:
                    log = await guild.audit_logs(limit=1, action=logType).next()
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description += f"""\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Updated by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} updated the server emoji list'
                    if guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'updated server emojis somewhere')
                except Exception as e:
                    content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            if footerIDList:
                embed.set_footer(
                    text=f'Relevant emoji IDs: {" • ".join(str(f) for f in footerIDList)}'
                    if len(footerIDList) > 1
                    else f'Emoji ID: {footerIDList[0]}'
                )
            if settings['embedTimestamp'] > 1:
                embed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}"
            if len(embed.fields) > 0:
                msg: discord.Message = await (await logChannel(guild, 'emoji')).send(
                    content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                    embed=embed if not settings['plainText'] else None,
                    tts=settings['tts'],
                )
                if any((settings['plainText'], settings['flashText'])) and not settings['plainText']:
                    await msg.edit(content=None)
                await self.archiveLogEmbed(guild, msg.id, embed, 'Emoji Update')

                # cutoff
                def reactionCheck(r, u):
                    return r.message.id == msg.id and not u.bot

                while not self.bot.is_closed():
                    try:
                        result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                    except asyncio.TimeoutError:
                        break
                    if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                        await msg.edit(content=content, embed=None)
                        await msg.clear_reactions()
                        if not settings['plainText']:
                            await msg.add_reaction(self.emojis['expand'])
                    elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                        await msg.edit(content=None, embed=embed)
                        await msg.clear_reactions()
                        if settings['plainText']:
                            await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_raw_app_command_permissions_update(self, payload: discord.RawAppCommandPermissionsUpdateEvent):
        """[DISCORD API METHOD] Called when application command permissions are updated"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(payload.guild_id))
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if await logEnabled(guild, 'command'):
            content = 'Application command permissions updated'
            settings = await getCyberAttributes(guild, 'command')
            color = blue[await utility.color_theme(guild)] if settings['color'][1] == 'auto' else settings['color'][1]
            embed = discord.Embed(
                title=f"""{(f'{self.emojis["command"]}{self.emojis["darkGreenPlus"]}' if settings['library'] == 1 else f"{self.emojis['minion']}{self.emojis['darkGreenPlus']}") if settings['context'][0] > 0 else ""}{'Application command permissions updated' if settings['context'][0] < 2 else ''}""",
                description=f"""{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Command' if settings['context'][1] < 2 else ''}: {payload.command_name}""",
                color=color,
            )
            if settings['embedTimestamp'] in (1, 3):
                embed.timestamp = discord.utils.utcnow()
            if await readPerms(guild, 'command'):
                try:
                    log = await guild.audit_logs(limit=1, action=discord.AuditLogAction.application_command_permission_update).next()
                    if settings['botLogging'] == 0 and log.user.bot:
                        return
                    elif settings['botLogging'] == 1 and log.user.bot:
                        settings['plainText'] = True
                    embed.description += f"""\n{"👮‍♂️" if settings["context"][1] > 0 else ""}{"Updated by" if settings["context"][1] < 2 else ""}: {log.user.mention} ({log.user.display_name}){f"{NEWLINE}{self.emojis['details'] if settings['context'][1] > 0 else ''}{'Reason' if settings['context'][1] < 2 else ''}: {log.reason}" if log.reason else ""}"""
                    if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                        settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                    ):
                        url = await self.imageToURL(log.user.display_avatar)
                        if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                            embed.set_thumbnail(url=url)
                        if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                            embed.set_author(name=log.user.display_name, icon_url=url)
                    content = f'{log.user} updated the application command permissions'
                    if guild.id not in gimpedServers:
                        await updateLastActive(log.user, discord.utils.utcnow(), 'updated application command permissions somewhere')
                except Exception as e:
                    content += f'\nYou have enabled audit log reading for your server, but I encountered an error utilizing that feature: `{e}`'
            content += utility.embedToPlaintext(embed)
            msg: discord.Message = await (await logChannel(guild, 'command')).send(
                content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            if any((settings['plainText'], settings['flashText'])) and not settings['plainText']:
                await msg.edit(content=None)
            await self.archiveLogEmbed(guild, msg.id, embed, 'Application Command Update')
            # cutoff

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild, before, after):
        pass

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction, command):
        pass

    @commands.Cog.listener()
    async def on_automod_rule_create(self, rule):
        pass

    @commands.Cog.listener()
    async def on_automod_rule_update(self, rule):
        pass

    @commands.Cog.listener()
    async def on_automod_rule_delete(self, rule):
        pass

    @commands.Cog.listener()
    async def on_automod_action(self, execution):
        pass

    # @commands.Cog.listener()
    # async def on_entitlement_create(self, entitlement):
    #     pass

    # @commands.Cog.listener()
    # async def on_entitlement_update(self, entitlement):
    #     pass

    # @commands.Cog.listener()
    # async def on_entitlement_delete(self, entitlement):
    #     pass

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        try:
            self.invites[str(invite.guild.id)] = await invite.guild.invites()
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        try:
            self.invites[str(invite.guild.id)] = await invite.guild.invites()
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.TextChannel):
        logs = [log async for log in channel.guild.audit_logs(limit=3)]
        await updateLastActive(
            await discord.utils.find(
                lambda x: x.action
                in (discord.AuditLogAction.webhook_create, discord.AuditLogAction.webhook_update, discord.AuditLogAction.webhook_delete),
                logs,
            ).user,
            'updated webhooks',
        )

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        pass

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        pass

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        pass

    @commands.Cog.listener()
    async def on_scheduled_event_user_add(self, event: discord.ScheduledEvent, user: discord.User):
        pass

    @commands.Cog.listener()
    async def on_scheduled_event_user_remove(self, event: discord.ScheduledEvent, user: discord.User):
        pass

    @commands.Cog.listener()
    async def on_stage_instance_create(self, stage: discord.StageInstance):
        pass

    @commands.Cog.listener()
    async def on_stage_instance_update(self, before: discord.StageInstance, after: discord.StageInstance):
        pass

    @commands.Cog.listener()
    async def on_stage_instance_delete(self, stage: discord.StageInstance):
        pass

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        pass

    @commands.Cog.listener()
    async def on_raw_thread_update(self, before: discord.Thread, after: discord.Thread):
        pass

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, thread: discord.Thread):
        pass

    @commands.Cog.listener()
    async def on_thread_join(self, thread: discord.Thread):
        pass

    @commands.Cog.listener()
    async def on_thread_remove(self, thread: discord.Thread):
        pass

    @commands.Cog.listener()
    async def on_thread_member_join(self, member: discord.Member):
        pass

    @commands.Cog.listener()
    async def on_raw_thread_member_remove(self, member: discord.Member):
        pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """[DISCORD API METHOD] Called whenever a voice channel event is triggered - join/leave, mute/deafen, etc"""
        received = discord.utils.utcnow()
        adjusted = discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(member.guild))
        msg = None
        serverData = await utility.get_server(member.guild)
        logRecapsEnabled = serverData['cyberlog']['voiceChatLogRecaps']
        if not await logEnabled(member.guild, 'voice') and not logRecapsEnabled:
            return
        settings = await getCyberAttributes(member.guild, 'voice')
        theme = await utility.color_theme(member.guild)
        color = blue[theme] if settings['color'][1] == 'auto' else settings['color'][1]
        embed = discord.Embed(
            title=f"{(self.emojis['voiceChannel'] if settings['library'] > 0 else '🎙') if settings['context'][0] > 0 else ''}{'Voice Channel Update' if settings['context'][0] < 2 else ''}",
            description=f"{(self.emojis['member'] if settings['library'] > 0 else '👤') if settings['context'][1] > 0 else ''}{'Member' if settings['context'][1] < 2 else ''}: {member.mention} ({member.display_name})",
            color=color,
        )
        if settings['embedTimestamp'] in (1, 3):
            embed.timestamp = discord.utils.utcnow()
        content = None
        error = False
        log = None
        if before.channel:
            beforePrivate = before.channel.overwrites_for(member.guild.default_role).read_messages is False
        if after.channel:
            afterPrivate = after.channel.overwrites_for(member.guild.default_role).read_messages is False
        onlyModActions = serverData['cyberlog']['onlyVCForceActions']
        onlyJoinLeave = serverData['cyberlog']['onlyVCJoinLeave']  # Make sure to do a full server verification every day to make sure this key exists
        try:
            eventHistory = self.memberVoiceLogs[member.id]
        except KeyError:
            eventHistory = []
            self.memberVoiceLogs[member.id] = eventHistory
            eventHistory: typing.List[typing.Tuple] = self.memberVoiceLogs[member.id]
        if any(a in (1, 2, 4) for a in (settings['thumbnail'], settings['author'])):
            url = await self.imageToURL(member.display_avatar)
            if settings['thumbnail'] in (1, 2, 4):
                embed.set_thumbnail(url=url)
            if settings['author'] in (1, 2, 4):
                embed.set_author(name=member.display_name, icon_url=url)
        # Use an if/else structure for AFK/Not AFK because AFK involves switching channels - this prevents duplicates of AFK & Channel Switch logs
        if before.afk != after.afk:
            # Note these *extremly* long value lines due to the multitude of customization options between emoji choice, emoji/plaintext descriptions, and color schemes
            lines = (
                f"{(self.emojis['darkRedDisconnect'] if settings['library'] > 0 else '📤') if settings['context'][1] > 0 else ''}{'Left' if settings['context'][1] < 2 else ''}: {(utility.channelEmoji(self, before.channel) if settings['library'] > 0 else '🎙') if settings['context'][1] > 0 else ''}{before.channel}",
                f"{(self.emojis['darkGreenConnect'] if settings['library'] > 0 else '📥') if settings['context'][1] > 0 else ''}{'Joined' if settings['context'][1] < 2 else ''}: {(utility.channelEmoji(self, after.channel) if settings['library'] > 0 else '🎙') if settings['context'][1] > 0 else ''}{after.channel}",
            )
            if after.afk:
                content = f'{member} went AFK from {before.channel}'
                eventHistory.append(
                    (adjusted, f"{(self.emojis['idle'] if settings['library'] > 0 else '😴') if settings['context'][1] > 0 else ''}Went AFK")
                )
                embed.add_field(
                    name=f"{(self.emojis['idle'] if settings['library'] > 0 else '😴') if settings['context'][1] > 0 else ''}Went AFK",
                    value=f'{lines[0]}\n{lines[1]}',
                )
            else:
                content = f'{member} rejoined {after.channel} & is no longer AFK'
                eventHistory.append(
                    (
                        adjusted,
                        f"{(self.emojis['online'] if settings['library'] > 0 else '🚫😴') if settings['context'][1] > 0 else ''}Returned from AFK",
                    )
                )
                embed.add_field(
                    name=f"{(self.emojis['online'] if settings['library'] > 0 else '🚫😴') if settings['context'][1] > 0 else ''}Returned from AFK",
                    value=f'{lines[0]}\n{lines[1]}',
                )
        else:
            # method that calculates how long a member was muted or deafened for
            def sanctionedFor(mode):
                """Returns a timespan string in standard Disguard format (x seconds or y minutes, etc) representing how long a member was muted or deafened, passed via the mode arg"""
                i = len(eventHistory) - 1
                e = eventHistory[-1]
                # while loop will iterate through eventHistory in reverse order until it either hits the beginning or finds the most recent mute/deafen
                while i > 0:
                    e = eventHistory[i]
                    if mode == 'mute' and 'Muted themselves' in e[1]:
                        break
                    elif mode == 'modMute' and 'Muted by' in e[1]:
                        break
                    elif mode == 'deafen' and 'Deafened themselves' in e[1]:
                        break
                    elif mode == 'modDeafen' and 'Deafened by' in e[1]:
                        break
                    else:
                        i -= 1
                # If we hit the end without finding a match, then the member probably unmuted before joining the voice channel, which the API doesn't do anything with until they join
                if i > 0:
                    return utility.elapsedDuration(adjusted - e[0])
                else:
                    return f'Special case: Member is on browser & had to accept microphone permissions or member toggled {mode} while outside of voice channel'

            # Member switched force-deafen or force-mute status - master if branch is for space-saving purposes when handing audit log retrieval
            if (before.deaf != after.deaf) or (before.mute != after.mute):
                # Audit log retrieval - check if audit log reading is enabled (remember that this is a change since I discovered the audit log supports voice moderations)
                if await readPerms(member.guild, 'voice'):
                    try:
                        # Fetch the most recent audit log
                        log = await member.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update).next()
                        # Return or adjust settings if the server has special settings for actions performed by bots
                        if settings['botLogging'] == 0 and log.user.bot:
                            return
                        elif settings['botLogging'] == 1 and log.user.bot:
                            settings['plainText'] = True
                        # Retrieve the additional attributes necessary to verify this audit log entry applies to a mute/deafen
                        i = iter(log.before)
                        # Check to make sure that if the audit log represents a mute, our event is a mute, and same for deafen
                        if ('mute' in i and before.mute != after.mute) or ('deafen' in i and before.deaf != after.deaf):
                            # See message edit for documentation on this segment
                            if (settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url))) or (
                                settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name))
                            ):
                                url = await self.imageToURL(log.user.display_avatar)
                                if settings['thumbnail'] > 2 or (settings['thumbnail'] == 2 and utility.empty(embed.thumbnail.url)):
                                    embed.set_thumbnail(url=url)
                                if settings['author'] > 2 or (settings['author'] == 2 and utility.empty(embed.author.name)):
                                    embed.set_author(name=log.user.display_name, icon_url=url)
                            if member.guild.id not in gimpedServers:
                                await updateLastActive(log.user, discord.utils.utcnow(), 'moderated a user in voice chat')
                    except:
                        pass
            # The 'onlyJoinLeave' and 'onlyModActions' moved inwards to allow the event history log to always be added to - this will be the new server default setting.
            if before.mute != after.mute:
                # Member is no longer force muted
                if before.mute:
                    content = f'{log.user if log else "[Moderator]"} unmuted {member}'
                    eventHistory.append(
                        (
                            adjusted,
                            f"""{(f"👮‍♂️{self.emojis['unmuted']}" if settings['library'] > 0 else '🎙🔨🗣') if settings['context'][1] > 0 else ''}Unmuted by {log.user if log else '[a moderator]'}""",
                        )
                    )
                    if not onlyJoinLeave:
                        embed.add_field(
                            name=f"""{(f"👮‍♂️{self.emojis['unmuted']}" if settings['library'] > 0 else '🎙🔨🗣') if settings['context'][1] > 0 else ''}Unmuted by moderator""",
                            value=f"""{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Moderator' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.display_name})\n(Was muted for {sanctionedFor("modMute")})""",
                        )
                # Member became force muted
                else:
                    content = f'{log.user if log else "[Moderator]"} muted {member}'
                    eventHistory.append(
                        (
                            adjusted,
                            f"""{(self.emojis['modMuted'] if settings['library'] > 0 else '🎙🔨🤐') if settings['context'][1] > 0 else ''}Muted by {log.user if log else '[a moderator]'}""",
                        )
                    )
                    if not onlyJoinLeave:
                        embed.add_field(
                            name=f"""{(self.emojis['modMuted'] if settings['library'] > 0 else '🎙🔨🤐') if settings['context'][1] > 0 else ''}Muted by moderator""",
                            value=f"""{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Moderator' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.display_name})""",
                        )
                    if before.deaf != after.deaf:
                        # If member was previously deafened, then they are no longer deafened
                        if before.deaf:
                            content = f'{log.user if log else "[Moderator]"} undeafened {member}'
                            eventHistory.append(
                                (
                                    adjusted,
                                    f"""{(f"👮‍♂️{self.emojis['undeafened']}" if settings['library'] > 0 else '🔨🔊') if settings['context'][1] > 0 else ''}Undeafened by {log.user if log else '[a moderator]'}""",
                                )
                            )
                            embed.add_field(
                                name=f"""{(f"👮‍♂️{self.emojis['undeafened']}" if settings['library'] > 0 else '🔨🔊') if settings['context'][1] > 0 else ''}Undeafened by moderator""",
                                value=f"""{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Moderator' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.display_name})\n(Was deafened for {sanctionedFor("modMute")})""",
                            )
                        # Otherwise, a moderator deafened them just now
                        else:
                            content = f'{log.user if log else "[Moderator]"} deafened {member}'
                            eventHistory.append(
                                (
                                    adjusted,
                                    f"""{(self.emojis['modDeafened'] if settings['library'] > 0 else '🔨🔇') if settings['context'][1] > 0 else ''}Deafened by {log.user if log else '[a moderator]'}""",
                                )
                            )
                            embed.add_field(
                                name=f"""{(self.emojis['modDeafened'] if settings['library'] > 0 else '🔨🔇') if settings['context'][1] > 0 else ''}Deafened by moderator""",
                                value=f"""{'👮‍♂️' if settings['context'][1] > 0 else ''}{'Moderator' if settings['context'][1] < 2 else ''}: {log.user.mention} ({log.user.display_name})""",
                            )
            if member.guild.id not in gimpedServers:
                await updateLastActive(
                    member, discord.utils.utcnow(), 'voice channel activity'
                )  # Not 100% accurate, especially for moderator actions
            # Member changed self-deafen status
            if before.self_deaf != after.self_deaf:
                if before.self_deaf:
                    content = f'{member} undeafened themselves'
                    eventHistory.append(
                        (
                            adjusted,
                            f"{(self.emojis['undeafened'] if settings['library'] > 0 else '🔊') if settings['context'][1] > 0 else ''}Undeafened themselves",
                        )
                    )
                    if not onlyModActions and not onlyJoinLeave:
                        embed.add_field(
                            name=f"{(self.emojis['undeafened'] if settings['library'] > 0 else '🔊') if settings['context'][1] > 0 else ''}Undeafened",
                            value=f'(Was deafened for {sanctionedFor("deafen")})',
                        )
                else:
                    content = f'{member} deafened themselves'
                    eventHistory.append(
                        (
                            adjusted,
                            f"{(self.emojis['deafened'] if settings['library'] > 0 else '🔇') if settings['context'][1] > 0 else ''}Deafened themselves",
                        )
                    )
                    if not onlyModActions and not onlyJoinLeave:
                        embed.add_field(
                            name=f"{(self.emojis['deafened'] if settings['library'] > 0 else '🔇') if settings['context'][1] > 0 else ''}Deafened",
                            value='_ _',
                        )
            if before.self_mute != after.self_mute:
                if before.self_mute:
                    content = f'{member} unmuted themselves'
                    eventHistory.append(
                        (
                            adjusted,
                            f"{(self.emojis['unmuted'] if settings['library'] > 0 else '🎙🗣') if settings['context'][1] > 0 else ''}Unmuted themselves",
                        )
                    )
                    if not onlyModActions and not onlyJoinLeave:
                        embed.add_field(
                            name=f"{(self.emojis['unmuted'] if settings['library'] > 0 else '🎙🗣') if settings['context'][1] > 0 else ''}Unmuted",
                            value=f'(Was muted for {sanctionedFor("mute")})',
                        )
                else:
                    content = f'{member} muted themselves'
                    eventHistory.append(
                        (
                            adjusted,
                            f"{(self.emojis['deafened'] if settings['library'] > 0 else '🔇') if settings['context'][1] > 0 else ''}Deafened themselves",
                        )
                    )
                    if not onlyModActions and not onlyJoinLeave:
                        embed.add_field(
                            name=f"{(self.emojis['deafened'] if settings['library'] > 0 else '🔇') if settings['context'][1] > 0 else ''}Deafened",
                            value='_ _',
                        )
            if before.channel != after.channel:
                # read audit log for member_move to get the moderator
                if not before.channel:
                    content = f'{member} connected to voice chat in {after.channel.name}'
                    eventHistory = []
                    self.memberVoiceLogs[member.id] = eventHistory
                    eventHistory = self.memberVoiceLogs[member.id]
                    eventHistory.append(
                        (
                            adjusted,
                            f"{(self.emojis['darkGreenConnect'] if settings['library'] > 0 else '📥') if settings['context'][1] > 0 else ''}Connected to {(self.emojis['privateVoiceChannel'] if afterPrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{after.channel}",
                        )
                    )
                    if not onlyModActions:
                        embed.add_field(
                            name=f"{((self.emojis['neonGreenConnect'] if theme == 1 else self.emojis['darkGreenConnect']) if settings['library'] > 0 else '📥') if settings['context'][1] > 0 else ''}Connected",
                            value=f"To {(self.emojis['privateVoiceChannel'] if afterPrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{after.channel}",
                        )
                elif not after.channel:
                    content = f'{member} disconnected from {before.channel.name}'
                    eventHistory.append(
                        (
                            adjusted,
                            f"{(self.emojis['darkRedDisconnect'] if settings['library'] > 0 else '📤') if settings['context'][1] > 0 else ''}Disconnected from {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel}",
                        )
                    )
                    if not onlyModActions:
                        embed.add_field(
                            name=f"{(self.emojis['darkRedDisconnect'] if settings['library'] > 0 else '📤') if settings['context'][1] > 0 else ''}Disconnected",
                            value=f"From {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel}",
                        )
                else:
                    content = f'{member} switched from {before.channel.name} to {after.channel.name}'
                    eventHistory.append(
                        (
                            adjusted,
                            f"{(self.emojis['shuffle'] if settings['library'] > 0 else '🔀') if settings['context'][1] > 0 else ''}Switched from {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel} to {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{after.channel}",
                        )
                    )
                    if not onlyModActions:
                        embed.add_field(
                            name=f"{(self.emojis['shuffle'] if settings['library'] > 0 else '🔀') if settings['context'][1] > 0 else ''}Switched voice channels",
                            value=f"{(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}{before.channel} → {(self.emojis['privateVoiceChannel'] if beforePrivate else self.emojis['voiceChannel']) if settings['library'] > 0 else '🎙'}**{after.channel}**",
                        )
        if len(embed.fields) < 1:
            return

        # Method to build voice channel history embed
        async def buildHistoryLog(eventHistory):
            logEmbed = discord.Embed(title='Member Voice Log Recap • ', description='', color=color)
            maxNumberOfEntries = 30  # Max number of log entries to display in the embed
            start, end = eventHistory[0 if len(eventHistory) < 30 else eventHistory[-1 * maxNumberOfEntries]], eventHistory[-1]
            # Set embed title based on the distance span between the start and end of voice log history
            if start[0].day == end[0].day:
                logEmbed.title += f'{utility.DisguardShortTimestamp(start[0])} - {utility.DisguardShortTimestamp(end[0])}'  # Member began & ended voice session on the same day, so least amount of contextual date information
            elif (end[0] - start[0]).days < 1:
                logEmbed.title += f'{utility.DisguardShortTimestamp(start[0])} yesterday - {utility.DisguardShortTimestamp(end[0])} today'  # Member began & ended voice session one day apart - so use yesterday & today
            else:
                logEmbed.title += f'{utility.DisguardShortTimestamp(start[0])}{start[0]:%b %d}  - {utility.DisguardShortTimestamp(end[0])} today'  # More than one day apart... somehow
            if len(eventHistory) > 30:
                logEmbed.title += f'(Last {maxNumberOfEntries} entries)'
            # Join the formatted log, last [maxNumberOfEntries] entries
            for e in eventHistory[-1 * maxNumberOfEntries :]:
                logEmbed.description += f'[{utility.DisguardShortmonthTimestamp(e[0])}] {e[1]}\n'
            logEmbed.add_field(name='Voice Session Duration', value=utility.elapsedDuration(eventHistory[-1][0] - eventHistory[0][0]))
            logEmbed.set_author(name=member, icon_url=await self.imageToURL(member.display_avatar))
            eventHistory = []
            return logEmbed

        lc = await logChannel(member.guild, 'voice')
        if await logEnabled(member.guild, 'voice'):
            if settings['embedTimestamp'] > 1:
                embed.description += f"\n{(utility.clockEmoji(adjusted) if settings['library'] > 0 else '🕰') if settings['context'][1] > 0 else ''}{'Timestamp' if settings['context'][1] < 2 else ''}: {utility.DisguardLongTimestamp(received)}"
            if error:
                content += f'\n\n{error}'
            msg: discord.Message = await lc.send(
                content=content if any((settings['plainText'], settings['flashText'], settings['tts'])) or error else None,
                embed=embed if not settings['plainText'] else None,
                tts=settings['tts'],
            )
            if any((settings['plainText'], settings['flashText'])) and not settings['plainText'] and not error:
                await msg.edit(content=None)
            await self.archiveLogEmbed(member.guild, msg.id, embed, 'Voice Session Update')
        else:
            msg = None
        if not after.channel and logRecapsEnabled:
            resultEmbed = await buildHistoryLog(eventHistory)
            await lc.send(embed=resultEmbed)
        # cutoff
        if msg:

            def reactionCheck(r, u):
                return r.message.id == msg.id and not u.bot

            while not self.bot.is_closed():
                try:
                    result = await self.bot.wait_for('reaction_add', check=reactionCheck, timeout=1800)
                except asyncio.TimeoutError:
                    break
                if result[0].emoji in (self.emojis['collapse'], '⏫', '⬆', '🔼', '❌', '✖', '❎') and len(msg.embeds) > 0:
                    await msg.edit(content=content, embed=None)
                    await msg.clear_reactions()
                    if not settings['plainText']:
                        await msg.add_reaction(self.emojis['expand'])
                elif (result[0].emoji in (self.emojis['expand'], '⏬', '⬇', '🔽') or not settings['plainText']) and len(msg.embeds) < 1:
                    await msg.edit(content=None, embed=embed)
                    await msg.clear_reactions()
                    if settings['plainText']:
                        await msg.add_reaction(self.emojis['collapse'])

    @commands.Cog.listener()
    async def on_typing(self, c: discord.abc.Messageable, u: discord.User, w: datetime.datetime):
        if c.guild and not serverIsGimped(c.guild):
            await updateLastActive(u, discord.utils.utcnow(), 'started typing somewhere')  # 9/29/21: Changed behavior to not work in DMs

    # TODO: Implement views
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        occurrence = discord.utils.utcnow()
        if isinstance(error, commands.CommandNotFound):
            return
        view = ErrorView(self, ctx, error, occurrence)
        await ctx.send(f'{self.emojis["alert"]} | {error}', view=view)

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def archives(self, ctx: commands.Context):
        """
        Retrieve the log archive file for this server
        """
        embed = discord.Embed(title='Log Archives', description=f'{self.emojis["loading"]}', color=yellow[await utility.color_theme(ctx.guild)])
        p = f'storage/{ctx.guild.id}/misc/modLogs.json'
        f = discord.File(p)
        try:
            await ctx.send(file=f)
        except Exception:
            logger.error(f'Unable to upload Log Archive file for {ctx.guild.name} | {ctx.guild.id}', exc_info=True)
            embed.description = 'Unable to upload Log Archive file'
            await ctx.send(embed=embed)

    def AvoidDeletionLogging(self, messages: typing.Union[typing.List[discord.Message], discord.Message]):
        """Don't log the deletion of passed messages"""
        if type(messages) is list:
            self.pauseDelete += [m.id for m in messages]
        else:
            self.pauseDelete.append(messages.id)

    async def privacyEnabledChecker(self, u: discord.User, parent, child):
        try:
            p = (await utility.get_user(u))['privacy']
        except (KeyError, TypeError):
            return False
        if p.get(child, [0, 0])[0] == 2:
            return await self.privacyEnabledChecker(u, 'default', parent)
        return p.get(child, [0, 0])[0] == 1

    async def privacyVisibilityChecker(self, u: discord.User, parent, child):
        try:
            p = (await utility.get_user(u))['privacy']
        except (KeyError, TypeError):
            return False
        if p.get(child, [0, 0])[1] == 2:
            return await self.privacyEnabledChecker(u, 'default', parent)
        return p.get(child, [0, 0])[1] == 1

    async def uploadFiles(self, f):
        # if type(f) is not list: f = [f]
        try:
            message: discord.Message = await self.imageLogChannel.send(
                file=discord.File(f) if type(f) is not list else None, files=[discord.File(fi) for fi in f] if type(f) is list else None
            )
            return [attachment.url for attachment in message.attachments] if type(f) is list else message.attachments[0].url
        except discord.HTTPException:
            return ''

    # Compare with uploadFiles
    async def imageToURL(self, asset: discord.Asset):
        """Given an image asset, retrieve a new Discord CDN URL from it for permanent use"""
        savePath = f'{TEMP_DIR}/{discord.utils.utcnow():%m%d%Y%H%M%S%f}.{"gif" if asset.is_animated() else "png"}'
        await asset.replace(size=1024, static_format='png').save(savePath)
        f = discord.File(savePath)
        message = await self.imageLogChannel.send(file=f)
        try:
            os.remove(savePath)
        except:
            pass
        return message.attachments[0].url

    async def image_to_local_attachment(self, asset: discord.Asset) -> str:
        """Given an image asset, save it locally and return that filepath"""
        save_path = f'{TEMP_DIR}/{discord.utils.utcnow():%m%d%Y%H%M%S%f}.{"gif" if asset.is_animated() else "png"}'
        await asset.replace(size=1024, static_format='png').save(save_path)
        return save_path

    async def archiveLogEmbed(self, server, id, embed, flavorText):
        p = f'storage/{server.id}/misc/modLogs.json'
        try:
            await aios.makedirs(f'storage/{server.id}/misc')
        except FileExistsError:
            pass
        try:
            async with aiofiles.open(p) as f:
                try:
                    content = await f.read()
                    logArchives = json.loads(content)
                except Exception:
                    logArchives = {}
                    logger.info(f'Log archive file for {server.id} is empty or invalid', exec_info=True)
        except FileNotFoundError:
            logArchives = {}
        e = embed.to_dict()
        e['customKeyFlavorText'] = flavorText
        if not e.get('timestamp'):
            e['timestamp'] = discord.utils.utcnow().isoformat()
        logArchives[id] = e
        logArchives = json.dumps(logArchives, indent=4)
        async with aiofiles.open(p, 'w+') as f:
            await f.write(logArchives)

    async def updateLogEmbed(self, server, id, data):
        p = f'storage/{server.id}/misc/modLogs.json'
        async with aiofiles.open(p) as f:
            try:
                content = await f.read()
                logArchives = json.loads(content)
            except:
                logArchives = {}
        logArchives[id].update(data)
        logArchives = json.dumps(logArchives, indent=4)
        async with open(p, 'w+') as f:
            await f.write(logArchives)

    # Review this monstrosity
    async def PermissionChanges(
        self, membersInput: typing.List[discord.Member], message: discord.Message, embed: discord.Embed, mod: str = 'role', permissionsChanged=True
    ):
        """Given an embed, modify and return it to describe how members' permissions changed by comparing current permissions against the internal cache. Does not update the members permission cache."""
        members: typing.Dict[int, typing.Dict[str, str]] = {}
        removedKeys: typing.Dict[str, typing.List[discord.Member]] = {}
        gainedKeys: typing.Dict[str, typing.List[discord.Member]] = {}
        g = message.guild
        settings = await getCyberAttributes(g, mod)
        for m in membersInput:
            oldPerms = self.memberPermissions[g.id][m.id]
            # Technically can be made faster by calling each of the loops once separately rather than twice in a gen
            removed = ' '.join(
                [p[0] for p in oldPerms if p[1] and p[0] not in [pp[0] for pp in m.guild_permissions if pp[1]]]
            )  # Permissions that were set to true previously and aren't currently set to True
            gained = ' '.join(
                [p[0] for p in m.guild_permissions if p[1] and p[0] not in [pp[0] for pp in oldPerms if pp[1]]]
            )  # Same but permissions that are set to True not but weren't before
            if removed:
                try:
                    members[m.id].update({'removed': removed})
                except KeyError:
                    members[m.id] = {'removed': removed}
            if gained > 0:
                try:
                    members[m.id].update({'gained': gained})
                except KeyError:
                    members[m.id] = {'gained': gained}
        for k, v in members.items():
            try:
                removedKeys[v['removed']].append(g.get_member(k))
            except AttributeError:
                removedKeys[v.get('removed')] = [g.get_member(k)]
            except KeyError:
                if v.get('removed'):
                    removedKeys[v['removed']] = [g.get_member(k)]
            try:
                gainedKeys[v.get('gained')].append(g.get_member(k))
            except AttributeError:
                gainedKeys[v['gained']] = [g.get_member(k)]
            except KeyError:
                if v.get('gained'):
                    gainedKeys[v['gained']] = [g.get_member(k)]
        embedDescriptionLines: typing.List[str] = []
        for k, v in gainedKeys.items():
            embedDescriptionLines.append(
                (
                    f"""📥 {k}""",
                    f"""{", ".join(m.display_name for m in v) if len(v) < 5 else f"[Hover to view the {len(v)} members]({message.jump_url} '{NEWLINE.join(m.display_name for m in v)}')" if len(v) < 30 else f"{len(v)} members"}""",
                )
            )
        for k, v in removedKeys.items():
            embedDescriptionLines.append(
                (
                    f"""📤 {k}""",
                    f"""{", ".join(m.display_name for m in v) if len(v) < 5 else f"[Hover to view the {len(v)} members]({message.jump_url} '{NEWLINE.join(m.display_name for m in v)}')" if len(v) < 30 else f"{len(v)} members"}""",
                )
            )
        if len(embedDescriptionLines) == 0 and permissionsChanged:
            embed.description += (
                f"""\n{self.emojis['details'] if settings['context'][1] > 0 else ''}No members were affected by the permissions changes"""
            )
        else:
            embed.description += (
                f"""\n{self.emojis['edit'] if settings['context'][1] > 0 else ''}{len(members)} members had their permissions updated (see bottom)"""
            )
            for tup in embedDescriptionLines[:25]:
                individualTup = tup[0].split(' ')
                overshoot = (
                    len(', '.join([utility.pretty_permission(i) for i in tup[0].split(' ')[1:]])) + 1 - 256
                )  # 256 is embed field name character limit, +1 accounts for the emoji at the beginning
                if overshoot > 0:
                    truncatePerWord = math.ceil(
                        overshoot / len(individualTup[1:])
                    )  # how many letters to cut per word, +1 at the end to include the triple periods character with length 1
                    if truncatePerWord > 1:
                        tup = [[], tup[1]]
                        for i in individualTup[1:]:
                            pki = utility.pretty_permission(i)
                            offset = 0
                            if truncatePerWord % 2 == 0:
                                offset -= 1
                            if len(pki) % 2 == 0:
                                offset += 1
                            tup[0].append(f'{pki[:(len(pki) - truncatePerWord) // 2]}…{pki[(len(pki) + truncatePerWord) // 2 + offset:]}')
                    embed.add_field(name=individualTup[0] + ', '.join(tup[0]), value=tup[1], inline=False)
                else:  # If we have 40 characters (or more) to spare, use the more concise custom emoji (yet it takes up many characters rather than 1 like the unicode emojis)
                    if overshoot < -40 and settings['library'] > 0:
                        individualTup[0] = (
                            individualTup[0].replace('📥', str(self.emojis['memberJoin'])).replace('📤', str(self.emojis['memberLeave']))
                        )
                    embed.add_field(
                        name=individualTup[0] + ', '.join([utility.pretty_permission(i) for i in tup[0][2:].split(' ')]), value=tup[1], inline=False
                    )
        return embed

    async def CheckDisguardServerRoles(self, memb: typing.List[discord.Member], *, mode=0, reason=None):
        """Automatic scan for Alpha Tester/VIP Alpha Tester for Disguard's official server. Mode - 0=Add&Remove, 1=Add, 2=Remove"""
        # If we pass a solitary member, convert it to a list with a single entry, otherwise, leave it alone
        if self.bot.user.id != 558025201753784323:
            return
        if type(memb) in (discord.User, discord.Member):
            members = [memb]
        else:
            members = memb
        disguardServer = bot.get_guild(560457796206985216)  # Disguard official server
        disguardServerMemberList = [m.id for m in disguardServer.members]  # List of member IDs in Disguard Official server
        disguardAlphaTester = disguardServer.get_role(571367278860304395)  # Alpha Testers role in Disguard Official server
        disguardVIPTester = disguardServer.get_role(571367775163908096)  # VIP Alpha Testers role in Disguard Official server
        alphaMembers = [member.id for member in disguardAlphaTester.members]  # ID list of members who have the Alpha Testers role
        vipMembers = [member.id for member in disguardVIPTester.members]  # ID list of members who have the VIP Alpha Testers role
        # Loop through all members passed in the argument
        for m in members:
            # If this member is in Disguard Official server
            if m.id in disguardServerMemberList:
                # Loop iteration member equivalent in Disguard server
                disguardMember = disguardServer.get_member(m.id)
                if mode != 2:  # Handles adding of roles
                    if m.id == m.guild.owner.id:
                        await disguardMember.add_roles(disguardVIPTester, reason=f'Automatic Scan: {reason}')
                    elif m.guild_permissions.manage_guild:
                        await disguardMember.add_roles(disguardAlphaTester, reason=f'Automatic Scan: {reason}')
                if mode != 1:  # Handles removing of roles
                    if m.id in alphaMembers or m.id in vipMembers:
                        memberServers = [server for server in bot.guilds if m.id in [member.id for member in server.members]]
                        if not any([m.id == s.owner.id for s in memberServers]) and m.id in vipMembers:
                            await disguardMember.remove_roles(disguardVIPTester, reason=f'Automatic Scan: {reason}')
                        if not any([s.get_member(m.id).guild_permissions.manage_guild for s in memberServers]) and m.id in alphaMembers:
                            await disguardMember.remove_roles(disguardAlphaTester, reason=f'Automatic Scan: {reason}')

    async def dispatch_notice(self, server: discord.Guild, embed: discord.Embed):
        try:
            channel = server.get_channel((await utility.get_server(server)).get('cyberlog').get('defaultChannel'))
            if channel:
                await channel.send(embed=embed)
        except Exception as e:
            logger.error(f'Error dispatching notice: {e}', exc_info=True)


async def logEnabled(s: discord.Guild, mod: str):
    server_data = await utility.get_server(s)
    return all(
        [
            server_data.get('cyberlog').get(mod).get('enabled'),
            server_data.get('cyberlog').get('enabled'),
            [
                any(
                    [
                        server_data.get('cyberlog').get(mod).get('channel') is not None,
                        server_data.get('cyberlog').get(mod).get('defaultChannel') is not None,
                    ]
                )
            ],
        ]
    )


async def logChannel(s: discord.Guild, mod: str):
    server_data = await utility.get_server(s)
    modular = server_data.get('cyberlog').get(mod).get('channel')
    default = server_data.get('cyberlog').get('defaultChannel')
    return s.get_channel(default) if modular is None else s.get_channel(modular)


async def verifyLogChannel(bot, s: discord.Guild):
    server_data = await utility.get_server(s)
    try:
        default = server_data.get('cyberlog').get('defaultChannel')
    except:
        return
    if default is None:
        return
    final = s.get_channel(default)
    for mod in ['message', 'doorguard', 'server', 'channel', 'member', 'role', 'emoji', 'voice']:
        modular = server_data.get('cyberlog').get(mod).get('channel')
        if not modular:
            channel = s.get_channel(modular)
            if not channel and type(modular) is int and modular != 0:
                if final:
                    try:
                        await final.send(
                            embed=discord.Embed(
                                description=f'⚠ | Your configured log channel (ID `{modular}`) for the `{mod}` module is invalid and has been reset to no value.\n[Edit settings online](http://disguard.herokuapp.com/manage/{s.id}/cyberlog)'
                            )
                        )
                    except:
                        pass
                await database.SetSubLogChannel(s, mod, None)
    if not default:
        if not final and type(default) is int and default != 0:
            try:
                await (await database.CalculateModeratorChannel(s, bot, False)).send(
                    embed=discord.Embed(
                        description=f'⚠ | Your configured default log channel (ID `{default}`) is invalid and has been reset to no value.\n[Edit settings online](http://disguard.herokuapp.com/manage/{s.id}/cyberlog)'
                    )
                )
            except:
                pass
            await database.SetLogChannel(s, None)


async def logExclusions(channel: discord.TextChannel, member: discord.Member):
    server_data = await utility.get_server(channel.guild)
    if type(member) is not discord.Member:
        member = channel.guild.get_member(member.id)
    if not member:
        return False
    return not any(
        [
            channel.id in server_data.get('cyberlog').get('channelExclusions'),
            member.id in server_data.get('cyberlog').get('memberExclusions'),
            any([r.id in server_data.get('cyberlog').get('roleExclusions') for r in member.roles]),
        ]
    )


async def memberGlobal(s: discord.Guild):
    return (await utility.get_server(s)).get('cyberlog').get('memberGlobal')


async def antispamObject(s: discord.Guild):
    return (await utility.get_server(s)).get('antispam')


async def readPerms(s: discord.Guild, mod):
    server_data = await utility.get_server(s)
    return server_data.get('cyberlog').get(mod).get('read') or server_data['cyberlog']['read']


async def getLibrary(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'library')


async def getThumbnail(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'thumbnail')


async def getAuthor(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'author')


async def getContext(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'context')


async def getHoverLinks(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'hoverLinks')


async def getColor(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'color')


async def getPlainText(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'plainText')


async def getEmbedTimestamp(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'embedTimestamp')


async def getflashText(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'flashText')


async def getTTS(s: discord.Guild, mod):
    return await cyberAttribute(s, mod, 'tts')


async def cyberAttribute(s: discord.Guild, mod, a):
    """Returns common attribute: cyberlog <--> cyberlog module. Not coded for beta datasystem"""
    server_data = await utility.get_server(s)
    default = server_data['cyberlog'][a]
    specific = server_data['cyberlog'][mod][a]

    def processor(i):
        if type(i) is list:
            return i if any(a is not None for a in i) else []
        else:
            return i

    specific = processor(specific)
    return specific if specific not in (None, []) else default


async def getCyberAttributes(s: discord.Guild, mod):
    result = {}
    for word in (
        'library',
        'thumbnail',
        'author',
        'context',
        'hoverLinks',
        'color',
        'plainText',
        'read',
        'embedTimestamp',
        'botLogging',
        'flashText',
        'tts',
    ):
        result[word] = await cyberAttribute(s, mod, word)
    return result


async def lastActive(u: discord.User):
    return (await utility.get_user(u)).get('lastActive', {'timestamp': datetime.datetime.min, 'reason': 'not tracked yet'})


async def updateLastActive(users: typing.Union[discord.User, typing.List[discord.User]], timestamp: datetime.datetime, reason: str):
    toUpdate = []
    if type(users) is not list:
        users = [users]
    cyber: Cyberlog = bot.get_cog('Cyberlog')
    for u in users:
        if not u:
            logger.info(f'updateLastActive: User is None, skipping update. {reason}')
        if await cyber.privacyEnabledChecker(u, 'profile', 'lastActive'):
            try:
                (await utility.get_user(u))['lastActive'] = {'timestamp': timestamp, 'reason': reason}
            except:
                pass
            if u not in toUpdate:
                toUpdate.append(u)
    asyncio.create_task(database.SetLastActive(toUpdate, timestamp, reason), name='SetLastActive')


async def lastOnline(u: discord.User):
    return (await utility.get_user(u)).get('lastOnline', datetime.datetime.min)


async def updateLastOnline(users: typing.Union[discord.User, typing.List[discord.User]], timestamp: datetime.datetime):
    toUpdate = []
    if type(users) is not list:
        users = [users]
    cyber: Cyberlog = bot.get_cog('Cyberlog')
    for u in users:
        if await cyber.privacyEnabledChecker(u, 'profile', 'lastOnline'):
            try:
                (await utility.get_user(u))['lastOnline'] = timestamp
            except:
                pass
            if u not in toUpdate:
                toUpdate.append(u)
    await database.SetLastOnline(toUpdate, timestamp)


def serverIsGimped(s: discord.Guild):
    return False


def beginPurge(s: discord.Guild):
    """Prevent logging of purge"""
    serverPurge[s.id] = True


def endPurge(s: discord.Guild):
    serverPurge[s.id] = False


async def setup(Bot: commands.Bot):
    global bot
    await Bot.add_cog(Cyberlog(Bot))
    bot = Bot


class ErrorView(discord.ui.View):
    def __init__(self, cyberlog: Cyberlog, ctx: commands.Context, error: Exception, occurrence: datetime.datetime):
        super().__init__(timeout=600)
        self.cyberlog = cyberlog
        self.ctx = ctx
        self.error = error
        self.occurrence = occurrence
        self.errorDetailsView = None
        self.embed = None
        self.button = self.viewDetailsButton(cyberlog, ctx)
        self.add_item(self.button)
        asyncio.create_task(self.writeError(), name='WriteError')

    async def writeError(self):
        consoleLogChannel: discord.TextChannel = self.cyberlog.bot.get_channel(873069122458615849)
        self.filename = self.occurrence.strftime('%m%d%Y%H%M%S%f')
        self.path = f'{TEMP_DIR}/tracebacks/{self.filename}.txt'
        try:
            os.makedirs(f'{TEMP_DIR}/tracebacks')
        except FileExistsError:
            pass
        with codecs.open(self.path, 'w+', encoding='utf-8-sig') as f:
            f.write(''.join(traceback.format_exception(type(self.error), self.error, self.error.__traceback__)))
        if os.path.exists(self.path):
            f = discord.File(self.path)
        else:
            f = None
        await consoleLogChannel.send(file=f)

    class viewDetailsButton(discord.ui.Button):
        def __init__(self, cyberlog: Cyberlog, ctx: commands.Context):
            super().__init__(emoji=cyberlog.emojis['details'], label='View error information', custom_id=f'{ctx.message.id}-viewinfo')

        async def callback(self, interaction: discord.Interaction):
            view: ErrorView = self.view
            embed = discord.Embed(
                title=f'{view.cyberlog.emojis["alert"]} An error has occured',
                description=str(view.error),
                color=red[await utility.color_theme(view.ctx.guild)],
            )
            embed.add_field(name='Command', value=f'{view.ctx.prefix}{view.ctx.command}')
            embed.add_field(name='Server', value=f'{view.ctx.guild.name}\n{view.ctx.guild.id}' if view.ctx.guild else 'N/A')
            embed.add_field(
                name='Channel', value=f'{utility.channelEmoji(view.cyberlog, view.ctx.channel)}{view.ctx.channel.name}\n{view.ctx.channel.id}'
            )
            embed.add_field(name='Author', value=f'{view.ctx.author.display_name}\n{view.ctx.author.id}')
            embed.add_field(
                name='Author/Bot Permissions', value=f'{view.ctx.author.guild_permissions.value}\n{view.ctx.guild.me.guild_permissions.value}'
            )
            embed.add_field(name='Occurrence', value=utility.DisguardLongTimestamp(view.occurrence))
            view.embed = embed
            if not view.errorDetailsView:
                view.errorDetailsView = ErrorDetailsView(view)
            await interaction.response.edit_message(
                content=interaction.message.content if view.errorDetailsView.buttonSend.disabled else None, embed=embed, view=view.errorDetailsView
            )


class ErrorDetailsView(discord.ui.View):
    def __init__(self, errorView: ErrorView):
        super().__init__()
        self.cyberlog = errorView.cyberlog
        self.error = errorView.error
        self.ctx = errorView.ctx
        self.errorView = errorView
        self.report = None
        self.buttonCollapse = self.collapseButton(self.cyberlog, self.ctx)
        self.buttonSend = self.sendButton(self.cyberlog, self.ctx)
        self.buttonTicket = self.openTicketButton(self.cyberlog, self.ctx)
        self.add_item(self.buttonCollapse)
        self.add_item(self.buttonSend)
        self.add_item(self.buttonTicket)

    class collapseButton(discord.ui.Button):
        def __init__(self, cyberlog: Cyberlog, ctx: commands.Context):
            super().__init__(emoji=cyberlog.emojis['collapse'], label='Collapse embed', custom_id=f'{ctx.message.id}-collapse')

        async def callback(self, interaction: discord.Interaction):
            view: ErrorDetailsView = self.view
            await interaction.response.edit_message(
                content=f'{view.cyberlog.emojis["alert"]} | {view.error}' if not view.buttonSend.disabled else '', embed=None, view=view.errorView
            )

    class sendButton(discord.ui.Button):
        def __init__(self, cyberlog: Cyberlog, ctx: commands.Context):
            super().__init__(emoji=cyberlog.emojis['sendMessage'], label='Send diagnostic data', custom_id=f'{ctx.message.id}-forward')

        async def callback(self, interaction: discord.Interaction):
            view: ErrorDetailsView = self.view
            embed = discord.Embed(
                title='Send diagnostic data',
                description="Want to help squash these bugs? Sending diagnostic data will forward this embed to a channel visible only to my developer in Disguard's Official Server, along with contextually relevant information as appropriate. For more information, check out [Disguard's privacy policy](https://disguard.netlify.app/privacy#appendixG). If this sounds alright, then click the green button.",
            )
            await interaction.response.edit_message(embed=embed, view=ErrorDiagnosticConfirmationView(view))

    class openTicketButton(discord.ui.Button):
        def __init__(self, cyberlog: Cyberlog, ctx: commands.Context):
            super().__init__(emoji='🎟', label='Open support ticket', custom_id=f'{ctx.message.id}-ticket')

        async def callback(self, interaction: discord.Interaction):
            view: ErrorDetailsView = self.view
            command = view.cyberlog.bot.get_command('support')
            await command.invoke(view.ctx)


class ErrorDiagnosticConfirmationView(discord.ui.View):
    def __init__(self, errorDetailsView: ErrorDetailsView):
        super().__init__()
        self.errorDetailsView = errorDetailsView
        self.add_item(self.noButton(errorDetailsView))
        self.add_item(self.yesButton(errorDetailsView))

    class noButton(discord.ui.Button):
        def __init__(self, errorDetailsView: ErrorDetailsView):
            super().__init__(style=discord.ButtonStyle.red, label='Cancel', custom_id=f'{errorDetailsView.ctx.message.id}-no')

        async def callback(self, interaction: discord.Interaction):
            view: ErrorDiagnosticConfirmationView = self.view
            await interaction.response.edit_message(embed=view.errorDetailsView.errorView.embed, view=view.errorDetailsView)

    class yesButton(discord.ui.Button):
        def __init__(self, errorDetailsView: ErrorDetailsView):
            super().__init__(style=discord.ButtonStyle.green, label='Confirm', custom_id=f'{errorDetailsView.ctx.message.id}-yes')

        async def callback(self, interaction: discord.Interaction):
            view: ErrorDiagnosticConfirmationView = self.view
            # TODO: advanced traceback
            view.errorDetailsView.buttonSend.disabled = True
            filename = view.errorDetailsView.errorView.occurrence.strftime('%m%d%Y%H%M%S%f')
            path = f'{TEMP_DIR}/tracebacks/{filename}-detailed.txt'
            if not os.path.exists(f'{TEMP_DIR}/tracebacks'):
                os.makedirs(f'{TEMP_DIR}/tracebacks')
            header = f'Occurrence: {utility.DisguardStandardTimestamp(view.errorDetailsView.errorView.occurrence)} UTC\nServer: {view.errorDetailsView.ctx.guild.name} ({view.errorDetailsView.ctx.guild.id}) • {view.errorDetailsView.ctx.guild.member_count} members\n'
            header += f'Channel: {view.errorDetailsView.ctx.channel.name} ({view.errorDetailsView.ctx.channel.id})\nMember: {view.errorDetailsView.ctx.author.display_name} ({view.errorDetailsView.ctx.author.id})\nMember permissions: {utility.outputPermissions(view.errorDetailsView.ctx.author.guild_permissions)}\n'
            header += f'Bot permissions: {utility.outputPermissions(view.errorDetailsView.ctx.guild.me.guild_permissions)}\nMessage: {view.errorDetailsView.ctx.message.content}'
            with codecs.open(path, 'w+', encoding='utf-8-sig') as f:
                f.write(
                    f'{header}\n\n{"".join(traceback.format_exception(type(view.errorDetailsView.error), view.errorDetailsView.error, view.errorDetailsView.error.__traceback__))}'
                )
            if os.path.exists(path):
                f = discord.File(path)
            else:
                f = None
            errorChannel: discord.TextChannel = view.errorDetailsView.cyberlog.bot.get_channel(620787092582170664)
            await errorChannel.send(file=f)
            await interaction.response.edit_message(
                content="Diagnostic data was successfully submitted to my developer via Disguard's Official Server: <https://discord.gg/xSGujjz>. Thanks for making it easier to fix bugs!",
                view=view.errorDetailsView,
            )
            # TODO: bug bounty
