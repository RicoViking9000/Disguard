'''This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files'''

import discord
from discord.ext import commands, tasks
import secure
import database
import Antispam
import Cyberlog
import os
import datetime
import collections
import asyncio
import traceback
import random
import logging
import inspect
import typing


booted = False
loading = None
presence = {'status': discord.Status.idle, 'activity': discord.Activity(name='My boss', type=discord.ActivityType.listening)}
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays']
print("Booting...")
prefixes = {}
variables = {}
newline = '\n'
yellow = 0xffff00

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

def prefix(bot, message):
    try: p = prefixes.get(message.guild.id)
    except AttributeError: return '.'
    return p if p is not None else '.'

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, heartbeat_timeout=1500)
bot.remove_command('help')

indexes = 'Indexes'
oPath = 'G:/My Drive/Other'
urMom = 'G:/My Drive/Other/ur mom'
campMax = 'G:/My Drive/Other/M A X'

@tasks.loop(minutes=1)
async def updatePrefixes():
    for server in bot.guilds: prefixes[server.id] = await database.GetPrefix(server)

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
        updatePrefixes.start()
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
    path = "{}/{}/{}".format(indexes,server.id, channel.id)
    start = datetime.datetime.now()
    try: os.makedirs(path)
    except FileExistsError: pass
    p = os.listdir(path)
    saveImages = await database.GetImageLogPerms(server)
    try: 
        async for message in channel.history(limit=None, oldest_first=full):
            if not message.author.bot:
                if '{}_{}.txt'.format(message.id, message.author.id) in p: 
                    if not full: break
                    else: 
                        continue #Skip the code below as to not overwrite message edit history, plus to skip saving message indexes we already have (program will keep running, however, this is intentional)
                try: f = open('{}/{}_{}.txt'.format(path, message.id, message.author.id), "w+")
                except FileNotFoundError: pass
                try: f.write('{}\n{}\n{}'.format(message.created_at.strftime('%b %d, %Y - %I:%M:%S %p'), message.author.name, message.content if len(message.content) > 0 else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else "<No content>"))
                except UnicodeEncodeError: pass
                try: f.close()
                except: pass
                if (datetime.datetime.utcnow() - message.created_at).days < 7 and saveImages:
                    attach = 'Attachments/{}/{}/{}'.format(message.guild.id, message.channel.id, message.id)
                    try: os.makedirs(attach)
                    except FileExistsError: pass
                    for attachment in message.attachments:
                        if attachment.size / 1000000 < 8:
                            try: await attachment.save('{}/{}'.format(attach, attachment.filename))
                            except discord.HTTPException: pass
                if full: await asyncio.sleep(0.25)
    except discord.Forbidden: print('Index error for {}'.format(server.name))
    print('Indexed {}: {} in {} seconds'.format(server.name, channel.name, (datetime.datetime.now() - start).seconds))

@commands.is_owner()
@bot.command()
async def verify(ctx):
    status = await ctx.send("Verifying...")
    await database.Verification(bot)
    await status.delete()

@commands.is_owner()
@bot.command()
async def index(ctx, t: int):
    if t == 0: target = bot.guilds
    else:
        target = bot.get_channel(t)
        if target is None:
            target = bot.get_guild(t)
            if target is None: return await ctx.send('No target found for <{}>'.format(t))
    status = await ctx.send('Indexing...')
    if type(target) is discord.Guild: await asyncio.gather(*[indexMessages(target, c, True) for c in target.text_channels])
    elif type(target) is list:
        for t in target: await asyncio.gather(*[indexMessages(t, c, True) for c in t.text_channels])
    else: await asyncio.wait([indexMessages(ctx.guild, target, True)], return_when=asyncio.FIRST_COMPLETED)
    await status.delete()

@bot.command()
async def help(ctx):
    e=discord.Embed(title='Help', description=f"[Click to view help on my website](https://disguard.netlify.com/commands '✔ Verified URL to Disguard website - https://disguard.netlify.com/commands')\n\nNeed help with the bot?\n• [Join Disguard discord server](https://discord.gg/xSGujjz)\n• Open a support ticket with the `{prefixes.get(ctx.guild.id) if ctx.guild else '.'}ticket` command", color=yellow)
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
    embed.description+=f'''\n🔨Antispam [(Edit full settings)]({baseURL}/antispam)\n> {f"{green}Antispam: Enabled" if antispam.get("enabled") else "{red}Antispam: Disabled"}\n> ℹMember warnings: {antispam.get("warn")}; after losing warnings: {"Nothing" if antispam.get("action") == 0 else f"Automute for {antispam.get('muteTime') // 60} minute(s)" if antispam.get("action") == 1 else "Kick" if antispam.get("action") == 2 else "Ban" if antispam.get("action") == 3 else f"Give role {g.get_role(antispam.get('customRoleID'))} for {antispam.get('muteTime') // 60} minute(s)"}\n> React to expand details'''
    # embed.description+=f'''Flag members for: {f"{antispam.get('congruent')[0]} duplicate messages/{} min "}'''
    embed.description+=f'''\n📜 Logging [(Edit full settings)]({baseURL}/cyberlog)\n> {f"{green}Logging: Enabled" if cyberlog.get("enabled") else "{red}Logging: Disabled"}\n> ℹDefault log channel: {bot.get_channel(cyberlog.get("defaultChannel")).mention if bot.get_channel(cyberlog.get("defaultChannel")) else "<Not configured>" if not cyberlog.get("defaultChannel") else "<Invalid channel>"}\n> React to expand details'''
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
        try:
            await d.send(embed=embed)
            successfulList.append(d.name)
        except Exception as e: await ctx.send(f'Error with destination {d.name}: {e}')
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
            embed.add_field(name=f"{alphabet[i]}Ticket {ticket['number']}", value=f'''Members: {", ".join([bot.get_user(u['id']).name for i, u in enumerate(ticket['members']) if i not in (1, 2)])}\nStatus: {statusDict[ticket['status']]}\nLatest reply: {bot.get_user(ticket['conversation'][-1]['author']).name} • {(ticket['conversation'][-1]['timestamp'] + datetime.timedelta(hours=(bot.lightningLogging[tg.id]['offset'] if tg else -4))):%b %d, %Y • %I:%M %p} {bot.lightningLogging[tg.id]['tzname'] if tg else 'EDT'}\n> {ticket['conversation'][-1]['message']}''', inline=False)
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
        pages = list(paginate(filtered))
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
            messageContent = '\n'.join([f'**{d}**' if i == sortMode else d for i, d in enumerate(sortDescriptions)])
            await message.edit(content=messageContent)
            clearAt = datetime.datetime.now() + datetime.timedelta(seconds=5)
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
        await message.edit(content=None)

@commands.is_owner()
@bot.command()
async def unduplicate(ctx):
    '''Removes duplicate entries from a user's status/username/avatar history. The problem came from users with multiple servers with Disguard, and has been patched. This will repair the existing duplicates in the database.'''
    '''For the first stage, to avoid loss of data, I'm only going to test this on myself'''
    status = await ctx.send('Working on it')
    interval = datetime.datetime.now()
    completed = 0
    for u in bot.users: 
        if (datetime.datetime.now() - interval).seconds > 2: 
            await status.edit(content=f'Working on it\n{completed} / {len(bot.users)} users completed')
            interval = datetime.datetime.now()
        await database.UnduplicateHistory(u)
        completed += 1
    await status.edit(content='Done')

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
    await ctx.send(str(ctx.author.avatar_url_as(format='png')))


database.Initialize(secure.token())
bot.run(secure.token()) #Bot token stored in another file, otherwise anyone reading this could start the bot
#database.Initialize(secure.beta())
#bot.run(secure.beta())
