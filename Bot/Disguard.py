'''This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files'''

import discord
from discord.ext import commands, tasks
import secure
import database
import Antispam
import Cyberlog
import Birthdays
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


booted = False
loading = None
presence = {'status': discord.Status.idle, 'activity': discord.Activity(name='My boss', type=discord.ActivityType.listening)}
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays']
print("Booting...")
prefixes = {}
variables = {}
newline = '\n'
qlf = '  ' #Two special characters to represent quoteLineFormat
qlfc = ' '
yellow = 0xffff00

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

def prefix(bot, message):
    try: p = bot.lightningLogging[message.guild.id]['prefix']
    except (AttributeError, KeyError): return '.'
    return p if p is not None else '.'

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, heartbeat_timeout=1500, allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)) #Make sure bot doesn't tag everyone/mass roles people unless I specify
bot.remove_command('help')

indexes = 'Indexes'
oPath = 'G:/My Drive/Other'
urMom = 'G:/My Drive/Other/ur mom'
campMax = 'G:/My Drive/Other/M A X'

# @tasks.loop(minutes=1)
# async def updatePrefixes():
#     for server in bot.guilds: prefixes[server.id] = await database.GetPrefix(server)

# @tasks.loop(minutes=1)
# async def anniversaryDayKickoff():
#     if datetime.datetime.now().strftime('%m %d %y %H:%M') == '03 18 20 10:55':
#         embed=discord.Embed(title=datetime.datetime.now().strftime('%B %d, %Y %H:%M %p'),description=secure.anniversary(),color=0xffff00, timestamp=datetime.datetime.utcnow())
#         embed.set_image(url=secure.embedImage())
#         await bot.get_user(596381991151337482).send(content=secure.anniversaryMessage(), embed=embed)
#         anniversaryDayKickoff.cancel()

# @tasks.loop(minutes=1)
# async def easterAnnouncement():
#     if datetime.datetime.now().strftime('%m %d %y %H:%M') == '04 12 20 06:00':
#         for server in bot.guilds:
#             try: await (await database.CalculateAnnouncementsChannel(server, True)).send('🐰🥚✝ Happy Easter! ✝🥚🐰\n\nWishing every one of you a happy and blessed day filled with new life no matter what the state of the world may be right now,\nRicoViking9000, the developer of Disguard')
#             except: pass

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
    if not booted:
        booted=True
        #updatePrefixes.start()
        loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')
        presence['activity'] = discord.Activity(name="my boss (Verifying database...)", type=discord.ActivityType.listening)
        await UpdatePresence()
        for cog in cogs:
            try:
                bot.load_extension(cog)
            except:
                pass
        #await database.Verification(bot)
        #await Antispam.PrepareMembers(bot)
        #await bot.get_cog('Birthdays').updateBirthdays()
        # easterAnnouncement.start()
        #Cyberlog.ConfigureSummaries(bot)
        def initializeCheck(m): return m.author.id == bot.user.id and m.channel.id == 534439214289256478 and m.content == 'Completed'
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

async def indexMessages(server, channel, full=False):
    path = f'{indexes}/{server.id}/{channel.id}'
    start = datetime.datetime.now()
    try: os.makedirs(path)
    except FileExistsError: pass
    path += '.json'
    try: saveImages = await database.GetImageLogPerms(server)
    except AttributeError: return
    if not os.path.exists(path): 
        with open(path, 'w+') as f: f.write('{}')
    with open(path) as f:
        try: indexData = json.load(f)
        except: indexData = {}
    try: 
        async for message in channel.history(limit=None, oldest_first=full):
            if str(message.id) in indexData.keys() and not full:
                break
            indexData[message.id] = {'author0': message.author.id, 'timestamp0': message.created_at.isoformat(), 'content0': message.content if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<No content>"}
            if not message.author.bot and (datetime.datetime.utcnow() - message.created_at).days < 7 and saveImages:
                attach = 'Attachments/{}/{}/{}'.format(message.guild.id, message.channel.id, message.id)
                try: os.makedirs(attach)
                except FileExistsError: pass
                for attachment in message.attachments:
                    if attachment.size / 1000000 < 8:
                        try: await attachment.save('{}/{}'.format(attach, attachment.filename))
                        except discord.HTTPException: pass
            if full: await asyncio.sleep(0.05)
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
    e=discord.Embed(title='Help', description=f"[Click to view help on my website](https://disguard.netlify.com/commands '✔ Verified URL to Disguard website - https://disguard.netlify.com/commands')\n\nNeed help with the bot?\n• [Join Disguard support server](https://discord.gg/xSGujjz)\n• Open a support ticket with the `{bot.lightningLogging.get(ctx.guild.id).get('prefix') if ctx.guild else '.'}ticket` command", color=yellow)
    await ctx.send(embed=e)

@bot.command()
async def invite(ctx):
    e = discord.Embed(title='Invite Links', description='• Invite Disguard to your server: https://discord.com/oauth2/authorize?client_id=558025201753784323&permissions=8&scope=bot\n\n• Join the Disguard discord server: https://discord.gg/xSGujjz')
    await ctx.send(embed=e)

@bot.command(aliases=['config', 'configuration', 'setup'])
async def server(ctx):
    '''Pulls up information about the current server, configuration-wise'''
    g = ctx.guild
    config = bot.lightningLogging.get(g.id)
    cyberlog = config.get('cyberlog')
    antispam = config.get('antispam')
    baseURL = f'http://disguard.herokuapp.com/manage/{ctx.guild.id}'
    green = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='online')
    red = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='dnd')
    embed=discord.Embed(title=f'Server Configuration - {g}', color=yellow)
    embed.description=f'''**Prefix:** `{config.get("prefix")}`\n\n⚙ General Server Settings [(Edit full settings on web dashboard)]({baseURL}/server)\n> Time zone: {config.get("tzname")} ({datetime.datetime.utcnow() + datetime.timedelta(hours=config.get("offset")):%I:%M %p})\n> {red if config.get("birthday") == 0 else green}Birthday announcements: {"<Disabled>" if config.get("birthday") == 0 else f"Announce daily to {bot.get_channel(config.get('birthday')).mention} at {config.get('birthdate'):%I:%M %p}"}\n> {red if not config.get("jumpContext") else green}Send embed for posted jump URLs: {"Enabled" if config.get("jumpContext") else "Disabled"}'''
    embed.description+=f'''\n🔨Antispam [(Edit full settings)]({baseURL}/antispam)\n> {f"{green}Antispam: Enabled" if antispam.get("enabled") else "{red}Antispam: Disabled"}\n> ℹMember warnings: {antispam.get("warn")}; after losing warnings: {"Nothing" if antispam.get("action") == 0 else f"Automute for {antispam.get('muteTime') // 60} minute(s)" if antispam.get("action") == 1 else "Kick" if antispam.get("action") == 2 else "Ban" if antispam.get("action") == 3 else f"Give role {g.get_role(antispam.get('customRoleID'))} for {antispam.get('muteTime') // 60} minute(s)"}'''
    # embed.description+=f'''Flag members for: {f"{antispam.get('congruent')[0]} duplicate messages/{} min "}'''
    embed.description+=f'''\n📜 Logging [(Edit full settings)]({baseURL}/cyberlog)\n> {f"{green}Logging: Enabled" if cyberlog.get("enabled") else "{red}Logging: Disabled"}\n> ℹDefault log channel: {bot.get_channel(cyberlog.get("defaultChannel")).mention if bot.get_channel(cyberlog.get("defaultChannel")) else "<Not configured>" if not cyberlog.get("defaultChannel") else "<Invalid channel>"}\n'''
    # embed.description+=f'''\nMessage Edit & Delete\n{f" {green}Enabled" if cyberlog.get("message").get("enabled") else f" {red}Disabled"}\n{f" ℹOverrides default log channel to {bot.get_channel(cyberlog.get('message').get('channel')).mention}" if cyberlog.get('message').get('channel') and cyberlog.get('message').get('channel') != cyberlog.get('defaultChannel') else ''}\n{f"{green}Read audit log: Enabled" if cyberlog.get('message').get('read') else f"{red}Read audit log: Disabled"}\n{f"{green}Log deleted images and attachments: Enabled" if cyberlog.get('image') else f"{red}Log deleted images and attachments: Disabled"}'''
    # embed.description+=f'''\nMember Join & Leave\n{f" {green}Enabled" if cyberlog.get("doorguard").get("enabled") else f" {red}Disabled"}\n{f" ℹOverrides default log channel to {bot.get_channel(cyberlog.get('doorguard').get('channel')).mention}" if cyberlog.get('doorguard').get('channel') and cyberlog.get('doorguard').get('channel') != cyberlog.get('defaultChannel') else ''}\n{f"{green}Read audit log: Enabled" if cyberlog.get('doorguard').get('read') else f"{red}Read audit log: Disabled"}'''
    # embed.description+=f'''\nChannel Create, Edit & Delete\n{f" {green}Enabled" if cyberlog.get("channel").get("enabled") else f" {red}Disabled"}\n{f" ℹOverrides default log channel to {bot.get_channel(cyberlog.get('channel').get('channel')).mention}" if cyberlog.get('channel').get('channel') and cyberlog.get('channel').get('channel') != cyberlog.get('defaultChannel') else ''}\n{f"{green}Read audit log: Enabled" if cyberlog.get('channel').get('read') else f"{red}Read audit log: Disabled"}'''
    # embed.description+=f'''\nMember Attribute Update\n{f" {green}Enabled" if cyberlog.get("member").get("enabled") else f" {red}Disabled"}\n{f" ℹOverrides default log channel to {bot.get_channel(cyberlog.get('member').get('channel')).mention}" if cyberlog.get('member').get('channel') and cyberlog.get('member').get('channel') != cyberlog.get('defaultChannel') else ''}\n{f"{green}Read audit log: Enabled" if cyberlog.get('member').get('read') else f"{red}Read audit log: Disabled"}\nℹLogging selection: {'Only local (role give/role remove & nickname) logs' if cyberlog.get('memberGlobal') == 0 else 'Only global (avatar & username) logs' if cyberlog.get('memberGlobal') == 1 else 'Both local (role give/remove & nickname) and global (avatar & username) logs'}'''
    # embed.description+=f'''\nRole Create, Edit & Delete\n{f" {green}Enabled" if cyberlog.get("role").get("enabled") else f" {red}Disabled"}\n{f" ℹOverrides default log channel to {bot.get_channel(cyberlog.get('role').get('channel')).mention}" if cyberlog.get('role').get('channel') and cyberlog.get('role').get('channel') != cyberlog.get('defaultChannel') else ''}\n{f"{green}Read audit log: Enabled" if cyberlog.get('role').get('read') else f"{red}Read audit log: Disabled"}'''
    # embed.description+=f'''\nEmoji Create, Edit & Delete\n{f" {green}Enabled" if cyberlog.get("emoji").get("enabled") else f" {red}Disabled"}\n{f" ℹOverrides default log channel to {bot.get_channel(cyberlog.get('emoji').get('channel')).mention}" if cyberlog.get('emoji').get('channel') and cyberlog.get('emoji').get('channel') != cyberlog.get('defaultChannel') else ''}\n{f"{green}Read audit log: Enabled" if cyberlog.get('emoji').get('read') else f"{red}Read audit log: Disabled"}'''
    # embed.description+=f'''\nServer Update\n{f" {green}Enabled" if cyberlog.get("server").get("enabled") else f" {red}Disabled"}\n{f" ℹOverrides default log channel to {bot.get_channel(cyberlog.get('server').get('channel')).mention}" if cyberlog.get('server').get('channel') and cyberlog.get('server').get('channel') != cyberlog.get('defaultChannel') else ''}\n{f"{green}Read audit log: Enabled" if cyberlog.get('server').get('read') else f"{red}Read audit log: Disabled"}'''
    # embed.description+=f'''\nVoice Chat\n{f" {green}Enabled" if cyberlog.get("voice").get("enabled") else f" {red}Disabled"}\n{f" ℹOverrides default log channel to {bot.get_channel(cyberlog.get('voice').get('channel')).mention}" if cyberlog.get('voice').get('channel') and cyberlog.get('voice').get('channel') != cyberlog.get('defaultChannel') else ''}\n{f"{red}Log joins, leaves, mutes, and deafens: Disabled; only mod-enforced mutes & deafens" if cyberlog.get('voice').get('read') else f"{green}Log joins, leaves, mutes, and deafens: Enabled"}'''
    embed.set_footer(text='More detailed config view and editing from here will be available in the future')
    await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    await ctx.send(f'Pong! Websocket latency: {round(bot.latency * 1000)}ms')

@commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
@bot.command()
async def say(ctx, m: typing.Optional[discord.Member] = None, c: typing.Optional[discord.TextChannel] = None, *, t='Hello World'):
    '''Uses webhook to say something. T is text to say, m is member. Author if none provided. C is channel, ctx.channel if none provided'''
    bot.get_cog('Cyberlog').AvoidDeletionLogging(ctx.message)
    await ctx.message.delete()
    if c is None: c = ctx.channel
    if m is None: m = ctx.author
    w = await c.create_webhook(name='automationSayCommand', avatar=await m.avatar_url_as().read(), reason=f'Initiated by {ctx.author.name} to imitate {m.name} by saying "{t}"')
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
    embed = discord.Embed(title=message.content[:message.content.find('\n')], description=message.content[message.content.find('\n'):], color=yellow)
    await ctx.send(content='Config - step 1: Servers\n\nType `all` to send to all servers, a comma-separated list of IDs to select specific servers, or an equation (eq: <statement>)', embed=embed)
    try: message = await bot.wait_for('message', check=patchCheck, timeout=300)
    except asyncio.TimeoutError: return
    servers = []
    if message.content.lower() == 'all': servers = bot.guilds
    elif message.content.startswith('eq:'):
        print(message.content[message.content.find('eq')+4:])
        servers = [g for g in bot.guilds if eval(f'bot.lightningLogging.get(g.id).{message.content[message.content.find("eq")+4:]}')]
    else: servers = [bot.get_guild(int(g)) for g in message.content.split(', ')]
    await ctx.send(f'Broadcast will be sent to {", ".join([g.name for g in servers])} - {len(servers)} / {len(bot.guilds)} servers\n\nWhat specific destination to send the broadcast?\nA: default log channel\nB: moderator channel\nC: announcement channel\nD: general channel\nE: owner DMs')
    try: message = await bot.wait_for('message', check=patchCheck, timeout=300)
    except asyncio.TimeoutError: return
    destinations = []
    letters = message.content.lower().split(', ')
    if 'a' in letters: destinations += [bot.get_channel(bot.lightningLogging.get(g.id).get('cyberlog').get('defaultChannel')) for g in servers]
    if 'b' in letters: destinations += [bot.get_channel(bot.lightningLogging.get(g.id).get('moderatorChannel')) for g in servers]
    if 'c' in letters: destinations += [bot.get_channel(bot.lightningLogging.get(g.id).get('announcementChannel')) for g in servers]
    if 'd' in letters: destinations += [bot.get_channel(bot.lightningLogging.get(g.id).get('generalChannel')) for g in servers]
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
                await d.send(embed=embed)
                successfulList.append(d.name)
            except: await ctx.send(f'Error with destination {d.name}')
    await status.edit(content=f'Successfully sent broadcast to {len(successfulList)} / {len(destinations)} destinations')

@bot.command(aliases=['feedback', 'ticket'])
async def support(ctx, *, opener=''):
    '''Command to initiate a feedback ticket. Anything typed after the command name will be used to start the support ticket
    Ticket status
    0: unopened by dev
    1: opened (dev has viewed)
    2: in progress (dev has replied)
    3: closed'''
    await ctx.trigger_typing()
    def navigationCheck(r, u): return str(r) in reactions and r.message.id == status.id and u.id == ctx.author.id
    if not opener:
        embed=discord.Embed(title='Disguard Support Menu', description=f'Welcome to Disguard support!\n\nIf you would easily like to get support, you may join my official server: https://discord.gg/xSGujjz\n\nIf you would like to get in touch with my developer without joining servers, react 🎟 to open a support ticket\n\nIf you would like to view your support tickets, type `{prefixes.get(ctx.guild.id) if ctx.guild else "."}tickets` or react 📜', color=yellow)
        status = await ctx.send(embed=embed)
        reactions = ['🎟', '📜']
        for r in reactions: await status.add_reaction(r)
        result = await bot.wait_for('reaction_add', check=navigationCheck)
        if str(result[0]) == '📜': 
            await status.delete()
            return await ticketsCommand(ctx)
        await ctx.send('Please type the message you would like to use to start the support thread, such as a description of your problem or a question you have')
        def ticketCreateCheck(m): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
        try: result = await bot.wait_for('message', check=ticketCreateCheck, timeout=300)
        except asyncio.TimeoutError: return await ctx.send('Timed out')
        opener = result.content
    if not ctx.guild:
        await ctx.trigger_typing()
        serverList = [g for g in bot.guilds if ctx.author in g.members] + ['<Prefer not to answer>']
        if len(serverList) > 2: #If the member is in more than one server with the bot, prompt for which server they're in
            alphabet = '🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿'
            newline = '\n'
            awaitingServerSelection = await ctx.send(f'Because we\'re in DMs, please provide the server you\'re representing by reacting with the corresponding letter\n\n{newline.join([f"{alphabet[i]}: {g}" for i, g in enumerate(serverList)])}')
            for letter in [l for l in alphabet if l in awaitingServerSelection.content]: await awaitingServerSelection.add_reaction(letter)
            def selectionCheck(r, u): return str(r) in alphabet and r.message.id == awaitingServerSelection.id and u.id == ctx.author.id
            try: selection = await bot.wait_for('reaction_add', check=selectionCheck, timeout=300)
            except asyncio.TimeoutError: return await ctx.send('Timed out')
            server = serverList[alphabet.index(str(selection[0]))]
            if type(server) is str: server = None
    else: server = ctx.guild
    embed=discord.Embed(title=f'🎟 Disguard Ticket System / {loading} Creating Ticket...', color=yellow)
    status = await ctx.send(embed=embed)
    if server: p = server.get_member(ctx.author.id).guild_permissions
    ticket = {'number': ctx.message.id, 'id': ctx.message.id, 'author': ctx.author.id, 'channel': str(ctx.channel), 'server': server.id if server else None, 'notifications': True, 'prestige': 'N/A' if not server else 'Owner' if ctx.author.id == server.owner.id else 'Administrator' if p.administrator else 'Moderator' if p.manage_server else 'Junior Moderator' if p.kick_members or p.ban_members or p.manage_channels or p.manage_roles or p.manage_members else 'Member', 'status': 0, 'conversation': []}
    firstEntry = {'author': ctx.author.id, 'timestamp': datetime.datetime.utcnow(), 'message': opener}
    ticket['conversation'].append(firstEntry)
    authorMember, devMember, botMember = {'id': ctx.author.id, 'bio': 'Created this ticket', 'permissions': 2, 'notifications': True}, {'id': 247412852925661185, 'bio': 'Bot developer', 'permissions': 1, 'notifications': True}, {'id': bot.user.id, 'bio': 'System messages', 'permissions': 1, 'notifications': False} #2: Owner, 1: r/w, 0: r 
    ticket['members'] = [authorMember, devMember, botMember]
    try: ticketList = await database.GetSupportTickets()
    except AttributeError: ticketList = []
    ticket['number'] = len(ticketList)
    await database.CreateSupportTicket(ticket)
    whiteCheck = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='whiteCheck')
    embed.title = f'🎟 Disguard Ticket System / {whiteCheck} Support Ticket Created!'
    embed.description = f'''Your support ticket has been created\n\nTicket {ticket['number']}\nAuthor: {ctx.author.name}\nMessage: {opener}\n\nTo view this ticket, react 🎟 or type `{prefixes.get(ctx.guild.id) if ctx.guild else "."}tickets {ticket['number']}`\nThat will allow you to add members to the support thread if desired, disable notifications, reply, and more.'''
    await status.edit(embed=embed)
    reactions = ['🎟']
    await status.add_reaction('🎟')
    devManagement = bot.get_channel(681949259192336406)
    await devManagement.send(embed=embed)
    result = await bot.wait_for('reaction_add', check=navigationCheck)
    await ticketsCommand(ctx, number=ticket['number'])

@bot.command(name='tickets')
async def ticketsCommand(ctx, number:int = None):
    '''Command to view feedback tickets'''
    g = ctx.guild
    alphabet = [l for l in ('🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿')]
    trashcan = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='trashcan')
    statusDict = {0: 'Unopened', 1: 'Viewed', 2: 'In progress', 3: 'Closed', 4: 'Locked'}
    message = await ctx.send(embed=discord.Embed(description=f'{loading}Downloading ticket data'))
    tickets = await database.GetSupportTickets()
    embed=discord.Embed(title='🎟 Disguard Ticket System / 🗃 Browse Your Tickets', color=yellow)
    embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url_as(static_format='png'))
    if len(tickets) == 0: 
        embed.description = 'There are currently no tickets in the system'
        return await message.edit(embed=embed)
    def organize(sortMode):
        if sortMode == 0: filtered.sort(key = lambda x: x['conversation'][-1]['timestamp'], reverse=True)
        elif sortMode == 1: filtered.sort(key = lambda x: x['conversation'][-1]['timestamp'])
        elif sortMode == 2: filtered.sort(key = lambda x: x['number'], reverse=True)
        else: filtered.sort(key = lambda x: x['number'])
    def paginate(iterable, resultsPerPage=10):
        for i in range(0, len(iterable), resultsPerPage): yield iterable[i : i + resultsPerPage]
    def populateEmbed(pages, index, sortDescription):
        embed.clear_fields()
        embed.description = f'''{f'NAVIGATION':-^70}\n{trashcan}: Delete this embed\n🗃: Adjust sort\n◀: Previous page\n🇦 - {alphabet[len(pages[index]) - 1]}: View ticket\n▶: Next page\n{f'Tickets for {ctx.author.name}':-^70}\nPage {index + 1} of {len(pages)}\nViewing {len(pages[index])} of {len(filtered)} results\nSort: {sortDescription}'''
        for i, ticket in enumerate(pages[index]):
            tg = g
            if not tg and ticket['server']: tg = bot.get_guild(ticket['server'])
            embed.add_field(name=f"{alphabet[i]}Ticket {ticket['number']}", value=f'''> Members: {", ".join([bot.get_user(u['id']).name for i, u in enumerate(ticket['members']) if i not in (1, 2)])}\n> Status: {statusDict[ticket['status']]}\n> Latest reply: {bot.get_user(ticket['conversation'][-1]['author']).name} • {(ticket['conversation'][-1]['timestamp'] + datetime.timedelta(hours=(bot.lightningLogging[tg.id]['offset'] if tg else -4))):%b %d, %Y • %I:%M %p} {bot.lightningLogging[tg.id]['tzname'] if tg else 'EDT'}\n> {qlf}{ticket['conversation'][-1]['message']}''', inline=False)
    async def notifyMembers(ticket):
        e = discord.Embed(title=f"New activity in ticket {ticket['number']}", description=f"To view the ticket, use the tickets command (`.tickets {ticket['number']}`)\n\n{'Highlighted message':-^70}", color=yellow)
        entry = ticket['conversation'][-1]
        messageAuthor = bot.get_user(entry['author'])
        e.set_author(name=messageAuthor, icon_url=messageAuthor.avatar_url_as(static_format='png'))
        e.add_field(name=f"{messageAuthor.name} • {(entry['timestamp'] + datetime.timedelta(hours=(bot.lightningLogging[tg.id]['offset'] if tg else -4))):%b %d, %Y • %I:%M %p} {bot.lightningLogging[tg.id]['tzname'] if tg else 'EDT'}", value=f'> {entry["message"]}', inline=False)
        for m in ticket['members']:
            if m['notifications'] and m['id'] != entry['author']:
                try: await bot.get_user(m['id']).send(embed=e)
                except: pass
    clearReactions = True
    currentPage = 0
    sortMode = 0
    sortDescriptions = ['Recently Active (Newest first)', 'Recently Active (Oldest first)', 'Ticket Number (Descending)', 'Ticket Number (Ascending)']
    filtered = [t for t in tickets if ctx.author.id in [m['id'] for m in t['members']]]
    if len(filtered) == 0:
        embed.description = f'There are currently no tickets in the system created by or involving you. To create a feedback ticket, type `{prefixes.get(ctx.guild.id) if ctx.guild else "."}ticket`'
        return await message.edit(embed=embed)
    def optionNavigation(r, u): return r.emoji in reactions and r.message.id == message.id and u.id == ctx.author.id and not u.bot
    def messageCheck(m): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
    while True:
        filtered = [t for t in tickets if ctx.author.id in [m['id'] for m in t['members']]]
        organize(sortMode)
        pages = list(paginate(filtered, 5))
        sortDescription = sortDescriptions[sortMode]
        populateEmbed(pages, currentPage, sortDescription)
        if number and number > len(tickets): 
            await message.edit(content=f'The ticket number you provided ({number}) is invalid. Switching to browse view')
            number = None
        if not number:
            if ctx.guild: 
                if clearReactions: await message.clear_reactions()
                else: clearReactions = True
                await message.edit(embed=embed)
            else:
                await message.delete()
                message = await ctx.send(content=message.content, embed=embed)
            reactions = [trashcan, '🗃', '◀'] + alphabet[:len(pages[currentPage])] + ['▶']
            for r in reactions: await message.add_reaction(str(r))
            destination = await bot.wait_for('reaction_add', check=optionNavigation)
            try: await message.remove_reaction(*destination)
            except: pass
        else: destination = [alphabet[0]]
        async def clearMessageContent():
            await asyncio.sleep(5)
            if datetime.datetime.now() > clearAt: await message.edit(content=None)
        if str(destination[0]) == str(trashcan): return await message.delete()
        elif str(destination[0]) == '🗃':
            clearReactions = False
            sortMode += 1 if sortMode != 3 else -3
            messageContent = '--SORT MODE--\n' + '\n'.join([f'> **{d}**' if i == sortMode else f'{qlfc}{d}' for i, d in enumerate(sortDescriptions)])
            await message.edit(content=messageContent)
            clearAt = datetime.datetime.now() + datetime.timedelta(seconds=4)
            asyncio.create_task(clearMessageContent())
        elif str(destination[0]) in ['◀', '▶']:
            if str(destination[0]) == '◀': currentPage -= 1
            else: currentPage += 1
            if currentPage < 0: currentPage = 0
            if currentPage == len(pages): currentPage = len(pages) - 1
        elif str(destination[0]) in alphabet[:len(pages[currentPage])]: 
            if not number: number = pages[currentPage][alphabet.index(str(destination[0]))]['number']
            ticket = [t for t in tickets if t['number'] == number][0]
            if ctx.author.id not in [m['id'] for m in ticket['members']]: 
                await message.edit(content=f'The ticket number you provided ({number}) does not include you, and you do not have a pending invite to it.\n\nIf you were invited to this ticket, then either the ticket author revoked the invite, or you declined the invite.\n\nSwitching to browse view')
                number = None
                continue
            if ctx.author.id == 247412852925661185 and ticket['status'] < 1: ticket['status'] = 1
            member = [m for m in ticket['members'] if m['id'] == ctx.author.id][0]
            if member['permissions'] == 3:
                embed.clear_fields()
                whiteCheck = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='whiteCheck')
                embed.description=f"You've been invited to this support ticket (Ticket {number})\n\nWhat would you like to do?\n⬅: Go back\n❌: Reject invite\n{whiteCheck}: Accept invite"
                reactions = ['⬅', '❌', whiteCheck]
                if ctx.guild: 
                    if clearReactions: await message.clear_reactions()
                    else: clearReactions = True
                    await message.edit(embed=embed)
                else:
                    await message.delete()
                    message = await ctx.send(embed=embed)
                for r in reactions: await message.add_reaction(str(r))
                result = await bot.wait_for('reaction_add', check=optionNavigation)
                if str(result[0]) == str(whiteCheck):
                    ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} accepted their invite*'})
                    member.update({'permissions': 1, 'notifications': True})
                    asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                else:
                    if str(result[0]) == '❌':
                        ticket['members'].remove(member)
                        ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} declined their invite*'})
                    number = None
                    asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                    continue
            conversationPages = list(paginate(ticket['conversation'], 7))
            currentConversationPage = len(conversationPages) - 1
            while True:
                embed.clear_fields()
                server = bot.get_guild(ticket['server'])
                member = [m for m in ticket['members'] if m['id'] == ctx.author.id][0]
                memberIndex = ticket['members'].index(member)
                tg = g
                if not tg and ticket['server']: tg = bot.get_guild(ticket['server'])
                hashtag = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='hashtag')
                def returnPresence(status): return '🔒' if status == 4 else discord.utils.get(bot.get_guild(560457796206985216).emojis, name='online') if status == 3 else discord.utils.get(bot.get_guild(560457796206985216).emojis, name='idle') if status in (1, 2) else discord.utils.get(bot.get_guild(560457796206985216).emojis, name='dnd')
                reactions = ['⬅', '👥', '↩']
                reactions.insert(2, '🔔' if not ctx.guild or not member['notifications'] else '🔕')
                conversationPages = list(paginate(ticket['conversation'], 7))
                if len(conversationPages) > 0 and currentConversationPage != 0: reactions.insert(reactions.index('👥') + 2, '◀')
                if len(conversationPages) > 0 and currentConversationPage != len(conversationPages) - 1: reactions.insert(reactions.index('↩') + 1, '▶')
                if member['permissions'] == 0: reactions.remove('↩')
                if ctx.author.id == 247412852925661185: reactions.append('🔒')
                embed.title = f'🎟 Disguard Ticket System / Ticket {number}'
                embed.description = f'''{'TICKET DATA':-^70}\n👮‍♂️Author: {bot.get_user(ticket['author'])}\n⭐Prestige: {ticket['prestige']}\n👥Other members involved: {', '.join([bot.get_user(u["id"]).name for u in ticket['members'] if u["id"] not in (247412852925661185, bot.user.id, ctx.author.id)]) if len(ticket['members']) > 3 else 'None - react 👥 to add'}\n⛓Server: {bot.get_guild(ticket['server'])}\n{hashtag}Channel: {bot.get_channel(ticket['channel']) if type(ticket['channel']) is int else ticket['channel']}\n{returnPresence(ticket['status'])}Dev visibility status: {statusDict.get(ticket['status'])}\n{'🔔' if member['notifications'] else '🔕'}Notifications: {member['notifications']}\n\n{'CONVERSATION - ↩ to reply' if member['permissions'] > 0 else 'CONVERSATION':-^70}\nPage {currentConversationPage + 1} of {len(conversationPages)}{f'{newline}◀ and ▶ to navigate' if len(conversationPages) > 1 else ''}\n\n'''
                for entry in conversationPages[currentConversationPage]: embed.add_field(name=f"{bot.get_user(entry['author']).name} • {(entry['timestamp'] + datetime.timedelta(hours=(bot.lightningLogging[tg.id]['offset'] if tg else -4))):%b %d, %Y • %I:%M %p} {bot.lightningLogging[tg.id]['tzname'] if tg else 'EDT'}", value=f'> {entry["message"]}', inline=False)
                if ctx.guild: 
                    if clearReactions: await message.clear_reactions()
                    else: clearReactions = True
                    await message.edit(content=None, embed=embed)
                else:
                    await message.delete()
                    message = await ctx.send(embed=embed)
                for r in reactions: await message.add_reaction(r)
                result = await bot.wait_for('reaction_add', check=optionNavigation)
                if str(result[0]) == '⬅': break
                elif str(result[0]) == '🔒':
                    ticket['status'] = 3
                    ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*My developer has closed this support ticket. If you still need assistance on this matter, you may reopen it by responding to it. Otherwise, it will silently lock in 7 days.*'})
                    await notifyMembers(ticket)
                elif str(result[0]) in ['◀', '▶']:
                    if str(result[0]) == '◀': currentConversationPage -= 1
                    else: currentConversationPage += 1
                    if currentConversationPage < 0: currentConversationPage = 0
                    if currentConversationPage == len(conversationPages): currentConversationPage = len(conversationPages) - 1
                elif str(result[0]) == '👥':
                    embed.clear_fields()
                    permissionsDict = {0: 'View ticket', 1: 'View and respond to ticket', 2: 'Ticket Owner (View, Respond, Manage Sharing)', 3: 'Invite sent'}
                    memberResults = []
                    while True:
                        def calculateBio(m): 
                            return '(No description)' if type(m) is not discord.Member else "Server Owner" if server.owner.id == m.id else "Server Administrator" if m.guild_permissions.administrator else "Server Moderator" if m.guild_permissions.manage_guild else "Junior Server Moderator" if m.guild_permissions.manage_roles or m.guild_permissions.manage_channels else '(No description)'
                        if len(memberResults) == 0: staffMemberResults = [m for m in server.members if any([m.guild_permissions.administrator, m.guild_permissions.manage_guild, m.guild_permissions.manage_channels, m.guild_permissions.manage_roles, m.id == server.owner.id]) and not m.bot and m.id not in [mb['id'] for mb in ticket['members']]][:15]
                        memberFillerText = [f'{bot.get_user(u["id"])}{newline}> {u["bio"]}{newline}> Permissions: {permissionsDict[u["permissions"]]}' for u in ticket['members']]
                        embed.description = f'''**__{'TICKET SHARING SETTINGS':-^85}__\n\n{'Permanently included':-^40}**\n{newline.join([f'👤{f}' for f in memberFillerText[:3]])}'''
                        embed.description += f'''\n\n**{'Additional members':-^40}**\n{newline.join([f'👤{f}{f"{newline}> {alphabet[i]} to manage" if ctx.author.id == ticket["author"] else ""}' for i, f in enumerate(memberFillerText[3:])]) if len(memberFillerText) > 2 else 'None yet'}'''
                        if ctx.author.id == ticket['author']: embed.description += f'''\n\n**{'Add a member':-^40}**\nSend a message to search for a member to add, then react with the corresponding letter to add them{f'{newline}{newline}Moderators of {bot.get_guild(ticket["server"])} are listed below as suggestions. You may also react with the letter next to their name to add them quickly, otherwise send a message to search for someone else' if ticket['server'] and len(staffMemberResults) > 0 else ''}'''
                        reactions = ['⬅']
                        if memberIndex > 2: 
                            embed.description += '\n\nIf you would like to leave the ticket, react 🚪'
                            reactions.append('🚪')
                        offset = len([a for a in alphabet if a in embed.description])
                        if server and len(memberResults) == 0: memberResults = staffMemberResults
                        embed.description += f'''\n\n{newline.join([f'{alphabet[i + offset]}{m.name} - {calculateBio(m)}' for i, m in enumerate(memberResults)])}'''
                        reactions += [l for l in alphabet if l in embed.description]
                        if ctx.guild: 
                            if clearReactions: await message.clear_reactions()
                            else: clearReactions = True
                            await message.edit(content=None, embed=embed)
                        else:
                            await message.delete()
                            message = await ctx.send(embed=embed)
                        for r in reactions: await message.add_reaction(r)
                        d, p = await asyncio.wait([bot.wait_for('reaction_add', check=optionNavigation), bot.wait_for('message', check=messageCheck)], return_when=asyncio.FIRST_COMPLETED)
                        try: result = d.pop().result()
                        except: pass
                        for f in p: f.cancel()
                        if type(result) is tuple:
                            if str(result[0]) in alphabet:
                                if not embed.description[embed.description.find(str(result[0])) + 2:].startswith('to manage'):
                                    addMember = memberResults[alphabet.index(str(result[0]))]
                                    invite = discord.Embed(title='🎟 Invited to ticket', description=f"Hey {addMember.name},\n{ctx.author.name} has invited you to **support ticket {ticket['number']}** with {', '.join([bot.get_user(m['id']).name for i, m in enumerate(ticket['members']) if i not in (1, 2)])}.\n\nThe Disguard support ticket system is a tool for server members to easily get in touch with my developer for issues, help, and questions regarding the bot\n\nTo join the support ticket, type `.tickets {ticket['number']}`", color=yellow)
                                    invite.set_footer(text=f'You are receiving this DM because {ctx.author} invited you to a support ticket')
                                    try: 
                                        await addMember.send(embed=invite)
                                        ticket['members'].append({'id': addMember.id, 'bio': calculateBio(addMember), 'permissions': 3, 'notifications': False})
                                        ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} invited {addMember} to the ticket*'})
                                        memberResults.remove(addMember)
                                    except Exception as e: await ctx.send(f'Error inviting {addMember} to ticket: {e}.\n\nBTW, error code 50007 means that the recipient disabled DMs from server members - they will need to temporarily allow this in the Server Options > Privacy Settings in order to be invited')
                                else:
                                    user = bot.get_user([mb['id'] for mb in ticket['members']][2 + len([l for l in alphabet if l in embed.description])]) #Offset - the first three members in the ticket are permanent
                                    while True:
                                        if ctx.author.id != ticket['author']: break #If someone other than the ticket owner gets here, deny them
                                        ticketUser = [mb for mb in ticket['members'] if mb['id'] == user.id][0]
                                        embed.description=f'''**{f'Manage {user.name}':-^70}**\n{'🔒' if not ctx.guild or ticketUser['permissions'] == 0 else '🔓'}Permissions: {permissionsDict[ticketUser['permissions']]}\n\n📜Responses: {len([r for r in ticket['conversation'] if r['author'] == user.id])}\n\n{f'🔔Notifications: True' if ticketUser['notifications'] else '🔕Notifications: False'}\n\n❌: Remove this member'''
                                        reactions = ['⬅', '🔓' if ctx.guild and ticketUser['permissions'] == 0 else '🔒', '❌']
                                        if ctx.guild: 
                                            if clearReactions: await message.clear_reactions()
                                            else: clearReactions = True
                                            await message.edit(content=None, embed=embed)
                                        else:
                                            await message.delete()
                                            message = await ctx.send(embed=embed)
                                        for r in reactions: await message.add_reaction(r)
                                        result = await bot.wait_for('reaction_add', check=optionNavigation)
                                        if str(result[0]) == '⬅': break
                                        elif str(result[0]) == '❌':
                                            ticket['members'] = [mbr for mbr in ticket['members'] if mbr['id'] != user.id]
                                            ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} removed {addMember} from the ticket*'})
                                            break
                                        else:
                                            if str(result[0]) == '🔒':
                                                if ctx.guild: reactions = ['⬅', '🔓', '❌']
                                                else: clearReactions = False
                                                ticketUser['permissions'] = 0
                                            else:
                                                if ctx.guild: reactions = ['⬅', '🔒', '❌']
                                                else: clearReactions = False
                                                ticketUser['permissions'] = 1
                                            ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} updated {ticketUser}\'s permissions to `{permissionsDict[ticketUser["permissions"]]}`*'})
                                            ticket['members'] = [m if m['id'] != user.id else ticketUser for m in ticket['members']]
                                        asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                            elif str(result[0]) == '🚪':
                                ticket['members'] = [mbr for mbr in ticket['members'] if mbr['id'] != ctx.author.id]
                                ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} left the ticket*'})
                                await message.delete()
                                asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                                return await ticketsCommand(ctx)
                            else: break
                        else:
                            try: 
                                bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                                await result.delete()
                            except: pass
                            memberResults = (await bot.get_cog('Cyberlog').FindMoreMembers([u for u in bot.users if any([u.id in [m.id for m in s.members] for s in bot.guilds])], result.content))[:15]
                            memberResults.sort(key = lambda x: x.get('check')[1], reverse=True)
                            memberResults = [r['member'] for r in memberResults if r['member'].id not in [m['id'] for m in ticket['members']]]
                            staffMemberResults = []
                        asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                elif str(result[0]) == '↩':
                    embed.description = '**__Please type your response (under 1024 characters) to the conversation, or react ⬅ to cancel__**'
                    reactions = ['⬅']
                    if ctx.guild: 
                        if clearReactions: await message.clear_reactions()
                        else: clearReactions = True
                        await message.edit(content=None, embed=embed)
                    else:
                        await message.delete()
                        message = await ctx.send(embed=embed)
                    for r in reactions: await message.add_reaction(r)
                    d, p = await asyncio.wait([bot.wait_for('reaction_add', check=optionNavigation), bot.wait_for('message', check=messageCheck)], return_when=asyncio.FIRST_COMPLETED)
                    try: result = d.pop().result()
                    except: pass
                    for f in p: f.cancel()
                    if type(result) is discord.Message:
                        try: 
                            bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                            await result.delete()
                        except: pass
                        ticket['conversation'].append({'author': ctx.author.id, 'timestamp': datetime.datetime.utcnow(), 'message': result.content})
                        if ticket['status'] != 2: ticket['status'] = 2
                        conversationPages = list(paginate(ticket['conversation'], 7))
                        if len(ticket['conversation']) % 7 == 1 and len(ticket['conversation']) > 7 and currentConversationPage + 1 < len(conversationPages): currentConversationPage += 1 #Jump to the next page if the new response is on a new page
                        await notifyMembers(ticket)
                else: member['notifications'] = not member['notifications']
                ticket['members'] = [member if i == memberIndex else m for i, m in enumerate(ticket['members'])]
                asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
        number = None #Triggers browse mode
        try:
            if datetime.datetime.now() > clearAt: await message.edit(content=None)
        except UnboundLocalError: await message.edit(content=None)

@bot.command(aliases = ['schedule'])
async def _schedule(ctx, *, desiredDate=None):
    pRoles = [619514236736897024, 739597955178430525, 615002577007804416, 668263236214456320, 623685383489585163, 565694432494485514]
    try:
        if 'set' == desiredDate: raise KeyError
        schedule = bot.lightningUsers[ctx.author.id]['schedule']
    except KeyError:
        #memberRoles = [[r.id for r in m.roles for m in [g.members for g in bot.guilds] if m.id == ctx.author.id]]
        # unlock = False
        # for g in [server for server in bot.guilds if ctx.author in server.members]:
        #     for r in [member for member in g.members if member.id == ctx.author.id][0].roles:
        #         if r.id in pRoles: 
        #             unlock = True
        #             break
        memberRoleList = [m.roles for m in bot.get_all_members() if ctx.author.id == m.id]
        totalRoleList = []
        for roleList in memberRoleList: totalRoleList.extend(roleList)
        if not any([r.id in pRoles for r in totalRoleList]):
            locked = await ctx.send('🔒This is a private command, and you don\'t have a permitted role. If you believe this is a mistake, please wait patiently - Google verification will be available soon')
            def unlock(r, u): return str(r) == '🔓' and r.message.id == locked.id and u.id == 247412852925661185
            await bot.wait_for('reaction_add', check=unlock)
            await ctx.send('🔓My developer has unlocked this command for you')
        string = f"Welcome to schedule setup! Since you're setting up a new schedule, let's go over the basics:\n{qlf}• Your schedule is private and only accessible to you, unless you use this command in a server"
        string += f'\n{qlf}• This command will be expanded with new features as time goes on, such as Google Account verification, sending you your schedule every morning, lunch schedules, website viewer, and more\n{qlf}• If you make a mistake during setup, type `cancel`\n{qlf}• If you are resetting an existing schedule, the old one will not be overwritten until this setup is complete\n\nLet\'s get started with your last name, due to the alphabet split. What\'s your last name? (Only the first letter will be stored)'
        await ctx.send(string)
        def rChecker(m): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
        response = await bot.wait_for('message', check=rChecker)
        if response.content.lower() == 'cancel': return await ctx.send('Cancelled setup')
        lastName = response.content
        await ctx.send(f'Now to enter your classes: Enter all 8 of your classes (excluding advisory), each on its own line (no indents), P1 first, P9 last. On desktop, use shift+enter to create a newline. Example:\n{qlf}Math\n{qlf}English\n{qlf}History\n{qlf}Theology\n{qlf}Band\n{qlf}PE\n{qlf}Spanish\n{qlf}Biology')
        response = await bot.wait_for('message', check=rChecker)
        if response.content.lower() == 'cancel': return await ctx.send('Cancelled setup')
        classes = response.content.split('\n') + [lastName[0]]
        statusMessage = await ctx.send(f'{loading}')
        await database.SetSchedule(ctx.author, classes)
        await statusMessage.edit(content=f'Schedule setup complete!\n{qlf}To reset your schedule, type `{bot.lightningLogging[ctx.guild.id]["prefix"]}schedule set`\n{qlf}You may type a day after the command (such as "tomorrow," "Friday," or "September 21") to view the schedule for that day\n\nReact 📅 or use the schedule command to view your schedule')
        await statusMessage.add_reaction('📅')
        def calendarChecker(r, u): return str(r) == '📅' and r.message.id == statusMessage.id and u.id == ctx.author.id
        await bot.wait_for('reaction_add', check=calendarChecker, timeout=None)
        desiredDate = None
        schedule = bot.lightningUsers[ctx.author.id]['schedule']
    if ctx.guild:
        statusMessage = await ctx.send("🔒You're using this command publicly in a server. By 🔓unlocking your schedule, you're aware that others may view your schedule. Alternatively, react 🔒 and I'll DM you your schedule")
        def lockedOut(r, u): return str(r) in ('🔓', '🔒') and r.message.id == statusMessage.id and u.id == ctx.author.id
        for r in ('🔓', '🔒'): await statusMessage.add_reaction(r)
        result = await bot.wait_for('reaction_add', check=lockedOut)
        if str(result[0]) == '🔒':
            if not ctx.author.dm_channel: await ctx.author.create_dm()
            ctx.channel = ctx.author.dm_channel
            statusMessage = None #to trigger the error
        else: await statusMessage.clear_reactions()
    try: await statusMessage.edit(content=f'{loading}Building schedule...')
    except: statusMessage = await ctx.send(f'{loading}Building schedule...')
    contentLog = []
    firstDay = datetime.date(2020, 8, 31) #First day of classes
    noClasses = ['09-04', '09-07', '09-23', '10-12', '10-14', '10-30', '11-25', '11-26', '11-27'] #list of days when there aren't classes - MM-DD
    today = datetime.date.today()
    if not desiredDate:
        desiredDate = today
        if datetime.datetime.now() > datetime.datetime(today.year, today.month, today.day, 14, 50) and int(f'{today:%w}') not in (0, 6):  #If it's later than 2:50PM and it's not a weekend, pull up tomorrow's schedule
            contentLog.append("ℹIt's after 2:50PM, so tomorrow's schedule will be displayed")
            date = today + datetime.timedelta(days=1)
        else:
            date = today
    elif type(desiredDate) is str: 
        dt = Birthdays.calculateDate(ctx.message, datetime.datetime.now())
        if not dt:
            contentLog.append(f"⚠Unable to calculate a date from `{desiredDate}`; switching to today's schedule")
            date = today
            desiredDate = today
        else: 
            date = datetime.date(dt.year, dt.month, dt.day)
            desiredDate = date
    while int(f'{date:%w}') in (0, 6) or f'{date:%m-%d}' in noClasses or date < firstDay: #If it's not a weekend, there are classes today, or it's not the first day of classes yet
        date += datetime.timedelta(days=1) #If the provided date is a weekend day, or a day without classes, we jump ahead to the next available day
        if int(f'{today:%w}') != 5: contentLog.append(f'ℹClasses are not in session during the date you provided ({desiredDate:%A, %B %d}), so the next date with classes ({date:%A, %B %d}) will be displayed') #If it's not Friday
        else: contentLog.append(f"ℹThis school week is over, so the next date with classes ({date:%A, %B %d}) will be displayed") #If it's friday - this may get passed from 'if not desiredDate'
    lastInitial = schedule[-1] #Last initial of user
    schedule = copy.deepcopy(schedule)
    schedule.pop(-1) #Remove the last initial since it's not part of the schedule and was simply placed there for convenience
    letters = 'PANTHERS'
    onlineLetters = 'PAHE' if lastInitial.lower() > 'k' else 'NTRS'
    daySpan = []
    daysSince = (date - firstDay).days
    while daysSince > 0:
        if len(daySpan) == 0: daySpan.append(date - datetime.timedelta(days=1))
        else: daySpan.append(daySpan[-1] - datetime.timedelta(days=1))
        daysSince -= 1
    daySpan = [d for d in daySpan if int(f'{d:%w}') not in (0, 6) and f'{d:%m-%d}' not in noClasses] #get the days that are not weekend days or days without classes
    currentDayLetter = letters[len(daySpan) % len(letters)]
    online = currentDayLetter in onlineLetters
    dailyClasses = schedule[:4] if letters.index(currentDayLetter) % 2 == 0 else schedule[4:] #take either the first or last half of classes depending on letter day
    try: rotationFactor = letters.index(currentDayLetter) // 2
    except ZeroDivisionError: rotationFactor = 0
    rotatedClasses = collections.deque(copy.deepcopy(dailyClasses))
    rotatedClasses.rotate(rotationFactor)
    rotatedClasses = list(rotatedClasses) #the four daily classes, rotated depending on the schedule
    rotatedClasses.insert(3, 'Advisory')
    schedule.insert(1, 'Advisory')
    def time(s): return datetime.time(int(s[:s.find(':')]), int(s[s.find(':') + 1:]))
    def fTime(t): return f'{t:%I:%M %p}'
    nowTime = datetime.datetime.now()
    times = [(time('7:45'), time('9:20')), (time('9:25'), time('10:55')), (time('11:00'), time('12:55')), (time('13:00'), time('13:15')), (time('13:20'), time('14:50'))]
    dateTimes = [(datetime.datetime(nowTime.year, nowTime.month, nowTime.day, t[0].hour, t[0].minute), datetime.datetime(nowTime.year, nowTime.month, nowTime.day, t[1].hour, t[1].minute)) for t in times]
    dayDescription = f'{"Today" if date == datetime.date.today() else "Tomorrow" if date == datetime.date.today() + datetime.timedelta(days=1) else f"{date:%A, %B %d}"}'
    embed = discord.Embed(title=f'{date:%B %d} - {currentDayLetter} day', color=yellow)
    embed.description=f'''{"💻" if online else "👥"}{"Today" if date == datetime.date.today() else "Tomorrow" if date == datetime.date.today() + datetime.timedelta(days=1) else f"On {date:%A, %B %d}, "} your classes are {"online" if online else "in person"}\n\n{f"{f'{dayDescription.upper()}'}'S SCHEDULE":-^70}'''
    for i, period in enumerate(rotatedClasses):
        compareTime = (datetime.datetime(date.year, date.month, date.day, times[i][0].hour, times[i][0].minute), datetime.datetime(date.year, date.month, date.day, times[i][1].hour, times[i][1].minute))
        def classStatus():
            return '✅' if nowTime > compareTime[1] else discord.utils.get(bot.get_guild(560457796206985216).emojis, name='online') if nowTime > compareTime[0] else ''
        def timeUntil():
            string = ''
            if dateTimes[i][0] > nowTime:
                hours = (dateTimes[i][0] - nowTime) // datetime.timedelta(hours=1)
                result = (hours, (dateTimes[i][0] - nowTime) // datetime.timedelta(minutes=1) - 60*hours)
                string = 'Begins'
            else: 
                hours = (dateTimes[i][1] - nowTime) // datetime.timedelta(hours=1)
                result = (hours, (dateTimes[i][1] - nowTime) // datetime.timedelta(minutes=1) - 60*hours)
                string = 'Ends'
            if result[0] > 0: return f'> {string} in {result[0]}h {result[1]}m'
            else: return f'> {string} in {result[1]} minutes'
        embed.add_field(name=f'{classStatus()}{"P" if i != 3 else ""}{schedule.index(period) + 1 if period != "Advisory" else period}{" & lunch" if i == 2 else ""} • {fTime(times[i][0])} - {fTime(times[i][1])}',
            value=f'> {period}\n{timeUntil() if (nowTime < dateTimes[i][0] and i == 0) or (dateTimes[i][0] < nowTime < dateTimes[i][1]) else ""}{f"{newline}A lunch: 11:00-11:25{newline}B lunch: 11:30-11:55{newline}C lunch: 12:00-12:25{newline}D lunch: 12:30-12:55" if i == 2 else ""}', inline=False)
    return await statusMessage.edit(content=contentLog[-1] if len(contentLog) > 0 else None, embed=embed)

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
    def serializeJson(o):
        if type(o) is datetime.datetime: return o.isoformat()
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
            with open(f'Indexes/{server.id}/{channel.id}.json') as f: indexData = json.load(f)
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
    fileName = f'Attachments/Temp/DisguardUserDataRequest_{(datetime.datetime.utcnow() + datetime.timedelta(hours=bot.lightningLogging[ctx.guild.id]["offset"] if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
    await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find(str(loading))] + f'{loading}Zipping data...')
    import py7zr
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
    fileName = f'Attachments/Temp/MessageAttachments_{convertToFilename(user.name)}_{(datetime.datetime.utcnow() + datetime.timedelta(hours=bot.lightningLogging[ctx.guild.id]["offset"] if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
    shutil.make_archive(fileName, 'zip', basePath)
    await statusMessage.edit(content=f'{os.path.abspath(fileName)}.zip')

@commands.is_owner()
@bot.command()
async def unduplicate(ctx):
    '''Removes duplicate entries from a user's status/username/avatar history. The problem came from users with multiple servers with Disguard, and has been patched. This will repair the existing duplicates in the database.'''
    '''For the first stage, to avoid loss of data, I'm only going to test this on myself'''
    status = await ctx.send('Working on it')
    interval = datetime.datetime.now()
    completed = 0
    errors = 0
    for u in bot.users: 
        if (datetime.datetime.now() - interval).seconds > 2: 
            await status.edit(content=f'Working on it\n{completed} / {len(bot.users)} users completed ({errors} errors)')
            interval = datetime.datetime.now()
        try: 
            await database.UnduplicateHistory(u)
            completed += 1
        except: errors += 1
    await status.edit(content=f'Done - {completed} successful, {errors} errors')

@commands.is_owner()
@bot.command()
async def nameVerify(ctx):
    await database.NameVerify(ctx.guild)
    await ctx.send('Successful')

def fileAbstraction(e, p, n):
    '''
    e: Emoji to use surrounding the embed title
    p: Path relative to the directory Other in my Google Drive
    n: Name between the emojis in the embed title'''
    image = False
    newDir = f'{oPath}/{p}'
    directory = os.listdir(newDir)
    while not image:
        result = random.randint(0, len(directory) - 1)
        if '.ini' not in directory[result]: image = True
    path = f'{newDir}/{directory[result]}'
    f = discord.File(path)
    embed = discord.Embed(title=f'{e} {n} {e}',description=f'{f.filename} • Image {result + 1} of {len(directory) - 1}',color=0xffff00)
    if any([ext in directory[result].lower() for ext in ['.png', '.jpeg', '.jpg', '.gif', '.webp']]): embed.set_image(url=f'attachment://{f.filename}')
    else: embed.description=f'<Attachment: {f.filename}> • File {result + 1} of {len(directory) - 1}'
    if ' ' in directory[result]: embed.set_footer(text='Discord does not allow direct image attachments with spaces in the filename to embeds')
    return (embed, f)

@commands.cooldown(2, 15, commands.BucketType.member)
@bot.command(aliases=['lex'])
async def lexy(ctx):
    if ctx.author.id not in [247412852925661185, 596381991151337482, 524391119564570664]: return
    r = fileAbstraction(bot.get_emoji(674389988363993116), 'ur mom', 'Lex')
    await ctx.send(embed=r[0],file=r[1])  

@bot.command(aliases=['max'])
async def _max(ctx):
    if not any([ctx.author in bot.get_guild(g).members for g in [611301150129651763, 709588078779695115]]): return
    r = fileAbstraction(bot.get_emoji(696789467901591683), 'M A X', 'Max')
    await ctx.send(embed=r[0],file=r[1])

@bot.command(aliases=['davey'])
async def david(ctx):
    if not any([ctx.author in bot.get_guild(g).members for g in [611301150129651763, 709588078779695115]]): return
    r = fileAbstraction(bot.get_emoji(708847959642603580), 'D A V I D', 'David')
    await ctx.send(embed=r[0],file=r[1])

@bot.command()
async def marvel(ctx):
    if not any([ctx.author in bot.get_guild(g).members for g in [611301150129651763]]): return
    r = fileAbstraction(bot.get_emoji(726991924086702121), 'M A R V E L', 'Marvel Characters')
    await ctx.send(embed=r[0],file=r[1])

@commands.is_owner()
@bot.command()
async def test(ctx):
    status = await ctx.send('Working')
    

    for g in bot.guilds:
        if bot.lightningLogging[g.id]['cyberlog']['voice']['read']: #12/10 daytime: carry old settings into new settings, based on audit log reading setting
            await database.getDatabase().disguard.servers.update_one({'server_id': g.id}, {'$set': {'cyberlog.onlyVCForceActions': True}})
        else: 
            await database.getDatabase().disguard.servers.update_one({'server_id': g.id}, {'$set': {'cyberlog.voice.read': True}})


    await status.edit(content='Done')

@commands.is_owner()
@bot.command()
async def daylight(ctx):
    status = await ctx.send(loading)
    for s in bot.guilds:
        if await database.AdjustDST(s):
            defaultLogchannel = bot.get_channel(bot.lightningLogging[s.id]['cyberlog'].get('defaultChannel'))
            if defaultLogchannel:
                e = discord.Embed(title='🕰 Server Time Zone update', color=yellow)
                e.description = 'Your server\'s time zone offset from UTC setting via Disguard has automatically been decremented, as it appears your time zone is in the USA & Daylight Savings Time has ended.\n\nTo revert this, you may enter your server\'s general settings page on my web dashboard (use the `config` command to retrieve a quick link).'
                await defaultLogchannel.send(embed=e)
    await status.edit(content='Done')


database.Initialize(secure.token())
bot.run(secure.token()) #Bot token stored in another file, otherwise anyone reading this could start the bot
#database.Initialize(secure.beta())
#bot.run(secure.beta())
