'''This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files'''

import discord
from discord.ext import commands, tasks
import secure
import database
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


booted = False
loading = None
presence = {'status': discord.Status.idle, 'activity': discord.Activity(name='My boss', type=discord.ActivityType.listening)}
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays', 'Misc', 'Info', 'Reddit']

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

def prefix(bot, message):
    try: p = bot.lightningLogging[message.guild.id]['prefix']
    except (AttributeError, KeyError): return '.'
    return p if p is not None else '.'

def getData(bot):
    return bot.lightningLogging

def getUserData(bot):
    return bot.lightningUsers

intents = discord.Intents.all()

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, heartbeat_timeout=1500, intents=intents, allowed_mentions = discord.AllowedMentions.none())
bot.remove_command('help')

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
        presence['activity'] = discord.Activity(name="my boss (Verifying database...)", type=discord.ActivityType.listening)
        await UpdatePresence()
        for cog in cogs:
            try:
                bot.load_extension(cog)
            except Exception as e: 
                print(f'Cog load error: {e}')
                traceback.print_exc()
        emojis = bot.get_cog('Cyberlog').emojis
        def initializeCheck(m: discord.Message): return m.author.id == bot.user.id and m.channel.id == bot.get_cog('Cyberlog').imageLogChannel.id and m.content == 'Completed'
        print('Waiting for database callback...')
        await bot.wait_for('message', check=initializeCheck) #Wait for bot to synchronize database
        presence['activity'] = discord.Activity(name="my boss (Indexing messages...)", type=discord.ActivityType.listening)
        await UpdatePresence()
        print('Starting indexing...')
        for server in bot.guilds:
            print('Indexing {}'.format(server.name))
            await asyncio.gather(*[indexMessages(server, c) for c in server.text_channels])
            Cyberlog.indexed[server.id] = True
        presence = {'status': discord.Status.online, 'activity': discord.Activity(name=f'{len(bot.guilds)} servers', type=discord.ActivityType.watching)}
    print("Booted")
    await UpdatePresence()

async def indexMessages(server: discord.Guild, channel: discord.TextChannel, full=False):
    path = f'{indexes}/{server.id}'
    start = datetime.datetime.now()
    try: os.makedirs(path)
    except FileExistsError: pass
    path += f'/{channel.id}.json'
    try: saveImages = bot.lightningLogging[server.id]['cyberlog'].get('image') and not channel.is_nsfw()
    except AttributeError: return
    if not os.path.exists(path): 
        with open(path, 'w+') as f: f.write('{}')
        full = True
    with open(path) as f:
        try: indexData = json.load(f)
        except: indexData = {}
    try: 
        async for message in channel.history(limit=None, oldest_first=full):
            if str(message.id) in indexData.keys() and not full:
                break
            indexData[str(message.id)] = {'author0': message.author.id, 'timestamp0': message.created_at.isoformat(), 'content0': '<Hidden due to channel being NSFW>' if channel.is_nsfw() else message.content if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<No content>"}
            if not message.author.bot and (discord.utils.utcnow() - message.created_at).days < 7 and saveImages:
                attach = 'Attachments/{}/{}/{}'.format(message.guild.id, message.channel.id, message.id)
                try: os.makedirs(attach)
                except FileExistsError: pass
                for attachment in message.attachments:
                    if attachment.size / 1000000 < 8:
                        try: await attachment.save('{}/{}'.format(attach, attachment.filename))
                        except discord.HTTPException: pass
            if full: await asyncio.sleep(0.0025)
        indexData = json.dumps(indexData, indent=4)
        with open(path, "w+") as f:
            f.write(indexData)
    except Exception as e: print(f'Index error for {server.name} - {channel.name}: {e}')
    print('Indexed {}: {} in {} seconds'.format(server.name, channel.name, (datetime.datetime.now() - start).seconds))

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
async def help(ctx):
    e=discord.Embed(title='Help', description=f"[Click to view help on my website](https://disguard.netlify.com/commands 'https://disguard.netlify.com/commands')\n\nNeed help with the bot?\n• [Join Disguard support server](https://discord.gg/xSGujjz)\n• Open a support ticket with the `{getData(bot).get(ctx.guild.id).get('prefix') if ctx.guild else '.'}ticket` command", color=yellow[getData(bot)[ctx.guild.id]['colorTheme'] if ctx.guild else 1])
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
    config = getData(bot).get(g.id)
    cyberlog = config.get('cyberlog')
    antispam = config.get('antispam')
    baseURL = f'http://disguard.herokuapp.com/manage/{ctx.guild.id}'
    green = emojis['online']
    red = emojis['dnd']
    embed=discord.Embed(title=f'Server Configuration - {g}', color=yellow[bot.get_cog('Cyberlog').colorTheme(ctx.guild)])
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
async def broadcast(ctx):
    await ctx.send('Please type broadcast message')
    def patchCheck(m): return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
    try: message = await bot.wait_for('message', check=patchCheck, timeout=300)
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
    if 'a' in letters: destinations += [bot.get_channel(getData(bot).get(g.id).get('cyberlog').get('defaultChannel')) for g in servers]
    if 'b' in letters: destinations += [bot.get_channel(getData(bot).get(g.id).get('moderatorChannel')[0]) for g in servers]
    if 'c' in letters: destinations += [bot.get_channel(getData(bot).get(g.id).get('announcementsChannel')[0]) for g in servers]
    if 'd' in letters: destinations += [bot.get_channel(getData(bot).get(g.id).get('generalChannel')[0]) for g in servers]
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
async def data(ctx):
    def accept(r, u): return str(r) in ['🇦', '🇧'] and u.id == ctx.author.id and r.message.id == requestMessage.id
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
            try: 
                with open(f'Indexes/{server.id}/{channel.id}.json') as f: indexData = json.load(f)
            except FileNotFoundError: continue
            memberIndexData = {}
            for k, v in indexData.items():
                if v['author0'] == member.id: 
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
    fileName = f'Attachments/Temp/DisguardUserDataRequest_{(datetime.datetime.utcnow() + datetime.timedelta(hours=getData(bot)[ctx.guild.id]["offset"] if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
    await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find(str(loading))] + f'{loading}Zipping data...')
    shutil.register_archive_format('7zip', py7zr.pack_7zarchive, description='7zip archive')
    shutil.make_archive(fileName, '7zip' if ext == '7z' else 'zip', basePath)
    fl = discord.File(f'{fileName}.{ext}')
    await statusMessage.delete()
    await ctx.send(content=f'```{readMe}```', file=fl)

@commands.is_owner()
@bot.command()
async def retrieveAttachments(ctx, user: discord.User):
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
    fileName = f'Attachments/Temp/MessageAttachments_{convertToFilename(user.name)}_{(datetime.datetime.utcnow() + datetime.timedelta(hours=getData(bot)[ctx.guild.id]["offset"] if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
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
    reactions = (emojis['online'], emojis['idle'], emojis['dnd'], emojis['offline'], emojis['streaming'], emojis['loop'])
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
    #await ctx.send('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
    '''Generating random birthdays for each member on the test bot'''
    for user in bot.users:
        try:
            if not bot.lightningUsers[user.id].get('birthday'):
                birthday = datetime.datetime(datetime.date.today().year, 1, 1)
                month = random.randint(1, 12)
                daysPerMonth = {1:31, 2:28, 3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31}
                day = random.randint(1, daysPerMonth[month])
                birthday = birthday.replace(month=month, day=day)
                await database.SetBirthday(user, birthday)
                print(f'Set {birthday:%B %d} for {user.name}')
        except KeyError: pass


@commands.is_owner()
@bot.command()
async def test2(ctx):
    status = await ctx.send('Working')
    
    for u in bot.lightningUsers.values():
        user = bot.get_user(u['user_id'])
        if user.bot:
            if u.get('usernameHistory') and len(u['usernameHistory']) > 1000:
                u['usernameHistory'] = u['usernameHistory'][-1000:]
                asyncio.create_task(database.SetUsernameHistory(user, u['usernameHistory']))
            if u.get('avatarHistory') and len(u['avatarHistory']) > 1000:
                u['avatarHistory'] = u['avatarHistory'][-1000:]
                asyncio.create_task(database.SetAvatarHistory(user, u['avatarHistory']))
        

    await status.edit(content='Done')

@commands.is_owner()
@bot.command()
async def daylight(ctx):
    status = await ctx.send(loading)
    for s in bot.guilds:
        try:
            if await database.AdjustDST(s):
                defaultLogchannel = bot.get_channel(getData(bot)[s.id]['cyberlog'].get('defaultChannel'))
                if defaultLogchannel:
                    e = discord.Embed(title='🕰 Server Time Zone update', color=yellow[1])
                    e.description = 'Your server\'s `time zone offset from UTC` setting via Disguard has automatically been incremented one hour, as it appears your time zone is in the USA & Daylight Savings Time has started (Spring Forward).\n\nTo revert this, you may enter your server\'s general settings page on my web dashboard (use the `config` command to retrieve a quick link).'
                    await defaultLogchannel.send(embed=e)
        except: pass
    await status.edit(content='Done')

def serializeJson(o):
    if type(o) is datetime.datetime: return o.isoformat()


database.Initialize(secure.token())
bot.run(secure.token()) #Bot token stored in another file, otherwise anyone reading this could start the bot
#database.Initialize(secure.beta())
#bot.run(secure.beta())
