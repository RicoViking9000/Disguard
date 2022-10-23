'''This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files'''

import discord
from discord.ext import commands, tasks
import secure
import database
import lightningdb
import Antispam
import Cyberlog
import Birthdays
import utility
import os
import datetime
import collections
import asyncio
import traceback
import random
import logging
import inspect
import typing
import json
import copy
import codecs
import shutil
import asyncpraw
import sys
import py7zr
from pymongo import errors as mongoErrors
import tracemalloc
import linecache

tracemalloc.start()

booted = False
loading = None
presence = {'status': discord.Status.idle, 'activity': discord.Activity(name='My boss', type=discord.ActivityType.listening)}
cogs = ['Antispam', 'Moderation', 'Birthdays', 'Misc', 'Info', 'Reddit']

print("Connecting...")

prefixes = {}
variables = {}
emojis = {}
newline = '\n'
qlf = '  ' #Two special characters to represent quoteLineFormat
qlfc = ' '

yellow = (0xffff00, 0xffff66)
blue = (0x0000FF, 0x6666ff)

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

async def prefix(bot: commands.Bot, message: discord.Message):
    return (await utility.prefix(message.guild)) or '.'

intents = discord.Intents.all()

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, heartbeat_timeout=1500, intents=intents, allowed_mentions = discord.AllowedMentions.none())
bot.remove_command('help')

async def main():
    lightningdb.initialize()
    # database.initialize(secure.beta())
    # await bot.start(secure.beta())
    database.initialize(secure.token())
    await bot.start(secure.token())
        
indexes = 'Indexes'

async def UpdatePresence():
    await bot.change_presence(status=presence['status'], activity=presence['activity'])

@bot.listen()
async def on_connect():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name='the server connection', type=discord.ActivityType.listening))

@bot.listen()
async def on_ready(): #Method is called whenever bot is ready after connection/reconnection. Mostly deals with database verification and creation
    '''Method called when bot connects and all the internals are ready'''
    global booted
    global presence
    global loading
    global emojis
    if not booted:
        booted=True
        print('Booting...')
        loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')
        presence['activity'] = discord.Activity(name='my boss (Syncing data...)', type=discord.ActivityType.listening)
        await UpdatePresence()
        await bot.load_extension('Cyberlog')
        await asyncio.sleep(2)
        for cog in cogs:
            try:
                await bot.load_extension(cog)
            except Exception as e: 
                print(f'Cog load error: {e}')
                traceback.print_exc()
        cyber: Cyberlog.Cyberlog = bot.get_cog('Cyberlog')
        emojis = cyber.emojis
        def initializeCheck(m: discord.Message): return m.author.id == bot.user.id and m.channel.id == cyber.imageLogChannel.id and m.content == 'Completed'
        print('Waiting for database callback...')
        await bot.wait_for('message', check=initializeCheck) #Wait for bot to synchronize database
        presence['activity'] = discord.Activity(name='my boss (Indexing messages...)', type=discord.ActivityType.listening)
        await UpdatePresence()
        print('Starting indexing...')
        for server in bot.guilds:
            print(f'Indexing {server.name}')
            # await asyncio.gather(*[indexMessages(server, c) for c in server.text_channels])
            # Cyberlog.indexed[server.id] = True
        presence = {'status': discord.Status.online, 'activity': discord.Activity(name=f'{len(bot.guilds)} servers', type=discord.ActivityType.watching)}
        await cyber.grab_pins()
    print("Booted")
    await UpdatePresence()

async def indexMessages(server: discord.Guild, channel: discord.TextChannel, full=False):
    if channel.id in (534439214289256478, 910598159963652126): return
    start = datetime.datetime.now()
    try: saveImages = (await utility.get_server(server))['cyberlog'].get('image') and not channel.is_nsfw()
    except AttributeError: return
    if lightningdb.database.get_collection(str(channel.id)) is None: full = True
    existing_message_counter = 0
    async for message in channel.history(limit=None, oldest_first=full):
        try: await lightningdb.post_message(message)
        except mongoErrors.DuplicateKeyError:
            if not full:
                existing_message_counter += 1
                if existing_message_counter >= 15: break
        if not message.author.bot and (discord.utils.utcnow() - message.created_at).days < 7 and saveImages:
            attachments_path = f'Attachments/{message.guild.id}/{message.channel.id}/{message.id}'
            try: os.makedirs(attachments_path)
            except FileExistsError: pass
            for attachment in message.attachments:
                if attachment.size / 1000000 < 8:
                    try: await attachment.save(f'{attachments_path}/{attachment.filename}')
                    except discord.HTTPException: pass
        if full: await asyncio.sleep(0.0015)
    print(f'Indexed {server.name}: {channel.name} in {(datetime.datetime.now() - start).seconds} seconds')

@commands.is_owner()
@bot.command()
async def verify(ctx):
    status = await ctx.send("Verifying...")
    await database.Verification(bot)
    await status.delete()

@commands.is_owner()
@bot.command()
async def index(ctx, t: int = None):
    if not t: target = bot.guilds
    else:
        target = bot.get_channel(t)
        if target is None:
            target = bot.get_guild(t)
            if target is None: return await ctx.send('No target found for <{}>'.format(t))
    def rCheck(r, u): return str(r) in ('✅', '❌') and u.id == ctx.author.id and r.message.id == m.id
    m = await ctx.send('Index fully?')
    for r in ('✅', '❌'): await m.add_reaction(r)
    try: result = await bot.wait_for('reaction_add', check=rCheck, timeout=300)
    except asyncio.TimeoutError: return
    if str(result[0]) == '✅': full = True
    else: full = False
    status = await ctx.send(f'Indexing {"fully" if full else "partially"}...')
    if type(target) is discord.Guild: await asyncio.gather(*[indexMessages(target, c, full) for c in target.text_channels])
    elif type(target) is list:
        for t in target: await asyncio.gather(*[indexMessages(t, c, full) for c in t.text_channels])
    else: await asyncio.wait([indexMessages(ctx.guild, target, full)], return_when=asyncio.FIRST_COMPLETED)
    await status.delete()

@bot.command()
async def help(ctx: commands.Context):
    e=discord.Embed(title='Help', description=f"[Click to view help on my website](https://disguard.netlify.com/commands 'https://disguard.netlify.com/commands')\n\nNeed help with the bot?\n• [Join Disguard support server](https://discord.gg/xSGujjz)\n• Open a support ticket with the `{await utility.prefix(ctx.guild) if ctx.guild else '.'}ticket` command", color=yellow[await utility.color_theme(ctx.guild) if ctx.guild else 1])
    await ctx.send(embed=e)

@bot.command()
async def invite(ctx):
    e = discord.Embed(title='Invite Links', description='• Invite Disguard to your server: https://discord.com/oauth2/authorize?client_id=558025201753784323&permissions=8&scope=bot\n\n• Join the Disguard discord server: https://discord.gg/xSGujjz')
    await ctx.send(embed=e)

# @bot.command()
# async def privacy(ctx):
#     await ctx.send("https://disguard.netlify.app/privacybasic")

@bot.command()
async def delete(ctx: commands.Context, messageID: int):
    '''Deletes a message from DMs with the user'''
    try:
        message = await ctx.author.fetch_message(messageID)
        await message.delete()
        await ctx.message.add_reaction('✅')
    except: await ctx.message.add_reaction('❌')

@bot.command()
async def dashboard(ctx):
    await ctx.send(f"https://disguard.herokuapp.com/manage/{ctx.guild.id if ctx.guild else ''}\n\nUpon clicking the link, please allow a few seconds for the server to wake up")

@bot.command(aliases=['config', 'configuration', 'setup'])
async def server(ctx: commands.Context):
    '''Pulls up information about the current server, configuration-wise'''
    g = ctx.guild
    config = await utility.get_server(ctx.guild)
    cyberlog = config.get('cyberlog')
    antispam = config.get('antispam')
    baseURL = f'http://disguard.herokuapp.com/manage/{ctx.guild.id}'
    green = emojis['online']
    red = emojis['dnd']
    embed=discord.Embed(title=f'Server Configuration - {g}', color=yellow[await utility.color_theme(ctx.guild)])
    embed.description=f'''**Prefix:** `{config.get("prefix")}`\n\n⚙ General Server Settings [(Edit full settings on web dashboard)]({baseURL}/server)\n> Time zone: {config.get("tzname")} ({datetime.datetime.utcnow() + datetime.timedelta(hours=config.get("offset")):%I:%M %p})\n> {red if config.get("birthday") == 0 else green}Birthday announcements: {"<Disabled>" if config.get("birthday") == 0 else f"Announce daily to {bot.get_channel(config.get('birthday')).mention} at {config.get('birthdate'):%I:%M %p}"}\n> {red if not config.get("jumpContext") else green}Send embed for posted jump URLs: {"Enabled" if config.get("jumpContext") else "Disabled"}'''
    embed.description+=f'''\n🔨Antispam [(Edit full settings)]({baseURL}/antispam)\n> {f"{green}Antispam: Enabled" if antispam.get("enabled") else f"{red}Antispam: Disabled"}\n> ℹMember warnings: {antispam.get("warn")}; after losing warnings: {"Nothing" if antispam.get("action") == 0 else f"Automute for {antispam.get('muteTime') // 60} minute(s)" if antispam.get("action") == 1 else "Kick" if antispam.get("action") == 2 else "Ban" if antispam.get("action") == 3 else f"Give role {g.get_role(antispam.get('customRoleID'))} for {antispam.get('muteTime') // 60} minute(s)"}'''
    embed.description+=f'''\n📜 Logging [(Edit full settings)]({baseURL}/cyberlog)\n> {f"{green}Logging: Enabled" if cyberlog.get("enabled") else f"{red}Logging: Disabled"}\n> ℹDefault log channel: {bot.get_channel(cyberlog.get("defaultChannel")).mention if bot.get_channel(cyberlog.get("defaultChannel")) else "<Not configured>" if not cyberlog.get("defaultChannel") else "<Invalid channel>"}\n'''
    await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    await ctx.send(f'Pong! Websocket latency: {round(bot.latency * 1000)}ms')

@commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
@bot.command()
async def say(ctx: commands.Context, m: typing.Optional[discord.Member] = None, c: typing.Optional[discord.TextChannel] = None, *, t='Hello World'):
    '''Uses webhook to say something. T is text to say, m is member. Author if none provided. C is channel, ctx.channel if none provided'''
    bot.get_cog('Cyberlog').AvoidDeletionLogging(ctx.message)
    await ctx.message.delete()
    if c is None: c = ctx.channel
    if m is None: m = ctx.author
    w = await c.create_webhook(name='automationSayCommand', avatar=await m.avatar.with_static_format('png').read(), reason=f'Initiated by {ctx.author.name} to imitate {m.name} by saying "{t}"')
    await w.send(t, username=m.name)
    await w.delete()

@commands.is_owner()
@bot.command(name='eval')
async def evaluate(ctx, *args):
    global variables
    args = ' '.join(args)
    result = eval(args)
    if inspect.iscoroutine(result): await ctx.send(await eval(args))
    else: await ctx.send(result)

@commands.is_owner()
@bot.command()
async def broadcast(ctx: commands.Context):
    await ctx.send('Please type broadcast message')
    def patchCheck(m): return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
    try: message: discord.Message = await bot.wait_for('message', check=patchCheck, timeout=300)
    except asyncio.TimeoutError: return
    query = await ctx.send('Embed?')
    for r in ('❌', '☑'): await query.add_reaction(r)
    def rCheck(r, u): return str(r) in ('❌', '☑') and r.message.id == query.id and u.id == ctx.author.id
    try: reaction = await bot.wait_for('reaction_add', check=rCheck, timeout=300)
    except asyncio.TimeoutError: return
    if str(reaction[0]) == '☑': embedForm = True
    else: embedForm = False
    if embedForm: embed = discord.Embed(title=message.content[:message.content.find('\n')], description=message.content[message.content.find('\n'):], color=yellow[1])
    else: embed = message.content
    await ctx.send(content=f'Config - step 1: Servers\n\nType `all` to send to all servers, a comma-separated list of IDs to select specific servers, or an equation (eq: <statement>)\n\n{embed if not embedForm else ""}', embed=embed if embedForm else None)
    try: message = await bot.wait_for('message', check=patchCheck, timeout=300)
    except asyncio.TimeoutError: return
    servers = []
    if message.content.lower() == 'all': servers = bot.guilds
    elif message.content.startswith('eq:'):
        print(message.content[message.content.find('eq')+4:]) #I guess this is here to ensure my eval part works lol
        servers = [g for g in bot.guilds if eval(f'bot.lightningLogging.get(g.id).{message.content[message.content.find("eq")+4:]}')]
    else: servers = [bot.get_guild(int(g)) for g in message.content.split(', ')]
    await ctx.send(f'Broadcast will be sent to {", ".join([g.name for g in servers])} - {len(servers)} / {len(bot.guilds)} servers\n\nWhat specific destination to send the broadcast?\nA: default log channel\nB: moderator channel\nC: announcement channel\nD: general channel\nE: owner DMs')
    try: message = await bot.wait_for('message', check=patchCheck, timeout=300)
    except asyncio.TimeoutError: return
    destinations = []
    letters = message.content.lower().split(', ')
    if 'a' in letters: destinations += [bot.get_channel((await utility.get_server(g)).get('cyberlog').get('defaultChannel')) for g in servers]
    if 'b' in letters: destinations += [bot.get_channel((await utility.get_server(g)).get('moderatorChannel')[0]) for g in servers]
    if 'c' in letters: destinations += [bot.get_channel((await utility.get_server(g)).get('announcementsChannel')[0]) for g in servers]
    if 'd' in letters: destinations += [bot.get_channel((await utility.get_server(g)).get('generalChannel')[0]) for g in servers]
    if 'e' in letters: destinations += [g.owner for g in servers]
    destinations = list(dict.fromkeys(destinations))
    waiting = await ctx.send(content='These are the destinations. Ready to send it?', embed=discord.Embed(description='\n'.join(d.name for d in destinations if d)))
    await waiting.add_reaction('✔')
    def sendCheck(r, u): return str(r) == '✔' and r.message.id == waiting.id and u.id == ctx.author.id
    try: await bot.wait_for('reaction_add', check=sendCheck, timeout=300)
    except asyncio.TimeoutError: return
    status = await ctx.send(f'{loading}Sending broadcast to servers...')
    successfulList = []
    for d in destinations:
        if d:
            try:
                await d.send(content = embed if not embedForm else None, embed=embed if embedForm else None)
                successfulList.append(d.name)
            except: await ctx.send(f'Error with destination {d.name}')
    await status.edit(content=f'Successfully sent broadcast to {len(successfulList)} / {len(destinations)} destinations')

@bot.command()
async def data(ctx: commands.Context):
    def accept(r: discord.Reaction, u: discord.User): return str(r) in ['🇦', '🇧'] and u.id == ctx.author.id and r.message.id == requestMessage.id
    requestMessage = await ctx.send(f'Data retrieval command: I will gather all of the data I store about you and DM it to you as an archive file\nTo continue, please choose a file format\n{qlf}A - .zip\n{qlf}B - .7z')
    for reac in ['🇦', '🇧']: await requestMessage.add_reaction(reac)
    result = await bot.wait_for('reaction_add', check=accept)
    if str(result[0]) == '🇦': ext = 'zip'
    else: ext = '7z'
    if not ctx.author.dm_channel: await ctx.author.create_dm()
    ctx.channel = ctx.author.dm_channel
    statusMessage = await ctx.send(f'•You will be sent a .{ext} file containing all relevant data involving you for each server, with directories containing relevant data from that server stored as .json files\n•If you have Administrator permissions in a server, one of the .json files will be the entire database entry for your server\n•You will also receive a .json containing your global user data (independent of server-specific data)\n\n{loading}Processing data...')
    if not ctx.guild: await requestMessage.delete()
    else: await requestMessage.edit(content=None, embed=discord.Embed(description=f'[Click to jump to the DM I just sent you]({statusMessage.jump_url})'))
    def convertToFilename(string):
        export = ''
        illegalCharList = [c for c in '#%&\{\}\\<>*?/$!\'":@+`|=']
        for char in string:
            if char not in illegalCharList: 
                if char != ' ': export += char
                else: export += '-'
        return export
    basePath = f'Attachments/Temp/{ctx.message.id}'
    os.makedirs(basePath)
    userData = (await database.GetUser(ctx.author))
    userData.pop('_id')
    dataToWrite = json.dumps(userData, indent=4, default=serializeJson)
    attachmentCount = 0
    with open(f'{basePath}/{f"{convertToFilename(str(ctx.author))} - UserData"}.json', 'w+') as f:
        f.write(dataToWrite)
    for server in [g for g in bot.guilds if ctx.author in g.members]:
        member = [m for m in server.members if m.id == ctx.author.id][0]
        serverPath = f'{basePath}/{convertToFilename(server.name)}'
        os.makedirs(f'{serverPath}/MessageAttachments')
        if any(role.permissions.administrator for role in member.roles) or server.owner.id == member.id:
            try: os.makedirs(serverPath)
            except FileExistsError: pass
            serverData = (await database.GetServer(server))
            serverData.pop('_id')
            dataToWrite = json.dumps(serverData, indent=4, default=serializeJson)
            with open(f'{serverPath}/ServerDatabaseEntry.json', 'w+') as f:
                f.write(dataToWrite)
        dataToWrite = json.dumps(await database.GetMember(member), indent=4, default=serializeJson)
        with open(f'{serverPath}/Server-MemberInfo.json', 'w+') as f:
            f.write(dataToWrite)
        for channel in server.text_channels:
            indexData = await lightningdb.get_messages_by_author(member.id, [channel.id])
            memberIndexData = {}
            for k, v in indexData.items():
                try: os.makedirs(f'{serverPath}/MessageIndexes')
                except FileExistsError: pass
                memberIndexData.update({k: v})
                try:
                    aPath = f'Attachments/{server.id}/{channel.id}/{k}'
                    attachmentCount += len(os.listdir(aPath))
                except FileNotFoundError: pass
            if len(memberIndexData) > 0:
                with open(f'{serverPath}/MessageIndexes/{convertToFilename(channel.name)}.json', 'w+') as f:
                    f.write(json.dumps(memberIndexData, indent=4))
        with codecs.open(f'{serverPath}/MessageAttachments/README.TXT', 'w+', 'utf-8-sig') as f: 
            f.write(f"I also have {attachmentCount} file attachments on file that you've uploaded, but I can't attach them due to the 8MB file size limit. If you would like to receive these files, contact my developer (RicoViking9000#2395) in one of the following ways:\n{qlf}•Use the `invite` command to join my support server\n{qlf}•Use the `ticket` command to get in direct contact with my developer through the Ticket System\n{qlf}•If you share a server with my developer, you may DM him - but he won\'t accept random friend requests from users sharing no servers with him'")
    readMe = f'Directory Format\n\nDisguardUserDataRequest_[Timestamp]\n|-- 📄UserData.json --> Contains the database entry for your global data, not specific to a server\n|-- 📁[Server name] --> Contains the data for this server'
    readMe += f'\n|-- |-- 📄ServerDatabaseEntry.json --> If you are an administrator of this server, this will be a file containing the database entry for this server\n|-- |-- 📄Server-MemberInfo.json --> Contains your server-indepedent data entry for this server'
    readMe += f'\n|-- |-- 📁MessageIndexes --> Folder containing message indexes authored by you for this server\n|-- |-- |-- 📄[channel name].json --> File containing message indexes authored by you for this channel'
    readMe += f'\n|-- |-- 📁MessageAttachments --> Folder containing a ReadMe file explaining how to obtain message attachment data'
    readMe += '\n\nThis readME is also saved just inside of the zipped folder. If you do not have a code editor to open .json files and make them look nice, web browsers can open them (drag into new tab area or use ctrl + o in your web browser), along with Notepad or Notepad++ (or any text editor)\n\nA guide on how to interpret the data fields will be available soon on my website. In the meantime, if you have a question about any of the data, contact my developer through the `ticket` command or ask in my support server (`invite` command)'
    with codecs.open(f'{basePath}/README.txt', 'w+', 'utf-8-sig') as f: 
        f.write(readMe)
    fileName = f'Attachments/Temp/DisguardUserDataRequest_{(datetime.datetime.utcnow() + datetime.timedelta(hours=await utility.time_zone(ctx.guild) if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
    await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find(str(loading))] + f'{loading}Zipping data...')
    shutil.register_archive_format('7zip', py7zr.pack_7zarchive, description='7zip archive')
    shutil.make_archive(fileName, '7zip' if ext == '7z' else 'zip', basePath)
    fl = discord.File(f'{fileName}.{ext}')
    await statusMessage.delete()
    await ctx.send(content=f'```{readMe}```', file=fl)

@commands.is_owner()
@bot.command()
async def retrieveAttachments(ctx: commands.Context, user: discord.User):
    statusMessage = await ctx.send(f'{loading}Retrieving attachments for {user.name}')
    basePath = f'Attachments/Temp/{ctx.message.id}'
    def convertToFilename(string):
        export = ''
        illegalCharList = [c for c in '#%&\{\}\\<>*?/$!\'":@+`|=']
        for char in string:
            if char not in illegalCharList: 
                if char != ' ': export += char
                else: export += '-'
        return export
    for server in [g for g in bot.guilds if ctx.author in g.members]:
        serverPath = f'{basePath}/MessageAttachments/{convertToFilename(server.name)}'
        for channel in server.text_channels:
            with open(f'Indexes/{server.id}/{channel.id}.json') as f: indexData = json.load(f)
            channelPath = f'{serverPath}/{convertToFilename(channel.name)}'
            for k, v in indexData.items():
                if v['author0'] == user.id: 
                    try: 
                        aPath = f'Attachments/{server.id}/{channel.id}/{k}'
                        for attachment in os.listdir(aPath):
                            try: os.makedirs(channelPath)
                            except FileExistsError: pass
                            savedFile = shutil.copy2(f'{aPath}/{attachment}', channelPath)
                            os.replace(savedFile, f'{channelPath}/{k}_{attachment}')
                    except FileNotFoundError: pass
    with codecs.open(f'{basePath}/README.txt', 'w+', 'utf-8-sig') as f: 
        f.write(f"📁MessageAttachments --> Master Folder\n|-- 📁[Server Name] --> Folder of channel names in this server\n|-- |-- 📁[Channel Name] --> Folder of message attachments sent by you in this channel in the following format: MessageID_AttachmentName.xxx\n\nWhy are message attachments stored? Solely for the purposes of message deletion logging. Additionally, attachment storing is a per-server basis, and will only be done if the moderators of the server choose to tick 'Log images and attachments that are deleted' on the web dashboard. If a message containing an attachment is sent in a channel, I attempt to save the attachment, and if a message containing an attachment is deleted, I attempt to retrieve the attachment - which is then permanently deleted from my records.")
    fileName = f'Attachments/Temp/MessageAttachments_{convertToFilename(user.name)}_{(datetime.datetime.utcnow() + datetime.timedelta(hours=await utility.time_zone(ctx.guild) if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
    shutil.make_archive(fileName, 'zip', basePath)
    await statusMessage.edit(content=f'{os.path.abspath(fileName)}.zip')

@commands.is_owner()
@bot.command()
async def unduplicate(ctx):
    '''Removes duplicate entries from a user's status/username/avatar history'''
    #status = await ctx.send('Working on it')
    bot.useAttributeQueue = True
    await database.UnduplicateUsers(bot.users, ctx)
    bot.useAttributeQueue = False
    await database.BulkUpdateHistory(bot.attributeHistoryQueue)
    #await database.BulkUpdateHistory()
    # interval = datetime.datetime.now()
    # completed = 0
    # errors = 0
    # for u in bot.users: 
    #     if (datetime.datetime.now() - interval).seconds > 1: 
    #         await status.edit(content=f'Working on it\n{completed} / {len(bot.users)} users completed ({errors} errors)')
    #         interval = datetime.datetime.now()
    #     try: 
    #         await database.UnduplicateHistory(u)
    #         completed += 1
    #     except: errors += 1
    # await status.edit(content=f'Done - {completed} successful, {errors} errors')

@commands.is_owner()
@bot.command()
async def nameVerify(ctx):
    await database.NameVerify(ctx.guild)
    await ctx.send('Successful')

# @bot.event
# async def on_error(event, *args, **kwargs):
#     logging.error(exc_info=True)
#     traceback.print_exc()

@commands.is_owner()
@bot.command(aliases=['status'])
async def _status(ctx):
    '''Owner-only command to manually set Disguard's status'''
    global presence
    m = await ctx.send('React with what you would like my desired status to be')
    #emojis = [e for e in bot.get_cog('Cyberlog').emojis.values() if e.name in ['online', 'idle', 'dnd', 'offline', 'streaming', 'reload']]
    cog = bot.get_cog('Cyberlog')
    reactions = (emojis['online'], emojis['idle'], emojis['dnd'], emojis['offline'], emojis['streaming'], emojis['reload'])
    for r in reactions: await m.add_reaction(r)
    def reacCheck(r, m): return r.emoji in emojis and m.id == ctx.author.id
    r = await bot.wait_for('reaction_add', check=reacCheck)
    if r[0].emoji.name == 'online': status = discord.Status.online
    elif r[0].emoji.name == 'idle': status = discord.Status.idle
    elif r[0].emoji.name == 'dnd': status = discord.Status.dnd
    elif r[0].emoji.name == 'offline': status = discord.Status.invisible
    elif r[0].emoji.name == 'streaming': status = discord.Status.online
    else:
        presence = {'status': discord.Status.online, 'activity': discord.Activity(name=f'{len(bot.guilds)} servers', type=discord.ActivityType.watching)}
        await UpdatePresence()
        return await ctx.send('Successfully reset')
    m = await ctx.send('Type the word: Playing, Watching, Listening, Streaming')
    def msgCheck1(m): return m.author.id == ctx.author.id
    r = await bot.wait_for('message', check=msgCheck1)
    if r.content.lower() == 'playing': mode = discord.ActivityType.playing
    elif r.content.lower() == 'watching': mode = discord.ActivityType.watching
    elif r.content.lower() == 'listening': mode = discord.ActivityType.listening
    elif r.content.lower() == 'streaming': mode = discord.ActivityType.streaming
    else: return await ctx.send('Invalid type')
    m = await ctx.send('Type the name of the activity') 
    r = await bot.wait_for('message', check=msgCheck1)
    name = r.content
    presence = {'status': status, 'activity': discord.Activity(name=name, type=mode)}
    await UpdatePresence()
    await ctx.send('Successfully set')

@commands.is_owner()
@bot.command()
async def test(ctx):
    await ctx.send('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

@commands.is_owner()
@bot.command()
async def test2(ctx):
    print(await lightningdb.get_users())
    await ctx.send(await lightningdb.get_users())

@commands.is_owner()
@bot.command()
async def daylight(ctx):
    status = await ctx.send(loading)
    for s in bot.guilds:
        try:
            if await database.AdjustDST(s):
                defaultLogchannel = bot.get_channel((await utility.get_server(s))['cyberlog'].get('defaultChannel'))
                if defaultLogchannel:
                    e = discord.Embed(title='🕰 Server Time Zone update', color=yellow[1])
                    e.description = 'Your server\'s `time zone offset from UTC` setting via Disguard has automatically been incremented one hour, as it appears your time zone is in the USA & Daylight Savings Time has started (Spring Forward).\n\nTo revert this, you may enter your server\'s general settings page on my web dashboard (use the `config` command to retrieve a quick link).'
                    await defaultLogchannel.send(embed=e)
        except: pass
    await status.edit(content='Done')

def serializeJson(o):
    if type(o) is datetime.datetime: return o.isoformat()

asyncio.run(main())
