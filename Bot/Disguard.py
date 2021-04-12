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
import asyncpraw


booted = False
loading = None
presence = {'status': discord.Status.idle, 'activity': discord.Activity(name='My boss', type=discord.ActivityType.listening)}
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays']

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
logger.setLevel(logging.DEBUG)
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

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, heartbeat_timeout=1500, allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)) #Make sure bot doesn't tag everyone/mass roles people unless I specify
bot.remove_command('help')

bot.reddit = asyncpraw.Reddit(user_agent = 'Portal for Disguard - Auto link functionality. --RV9k--')

indexes = 'Indexes'
oPath = 'G:/My Drive/Other'
urMom = 'G:/My Drive/Other/ur mom'
campMax = 'G:/My Drive/Other/M A X'

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

@tasks.loop(minutes=5)
async def scheduleDeliveryLoop():
    n = datetime.datetime.now()
    desiredDate = n
    if int(f'{n:%H%M}') > 1450: desiredDate += datetime.timedelta(days=1)
    if int(f'{desiredDate:%W}') in (0, 6): return
    timeOfDay = 'morning' if int(f'{n:%H}') in range(3, 12) else 'afternoon' if int(f'{n:%H}') in range(12, 17) else 'evening'
    users = [u for u in getUserData(bot).values() if u.get('schedule') and type(u.get('schedule')) is dict and u.get('schedule').get('daily')]
    try: noClasses = getUserData(bot)[247412852925661185]['highSchoolDaysOffSpring2021'] #dict of days when there aren't classes - MM-DD-YYYY
    except: noClasses = {}
    for u in users:
        daily = u['schedule']['daily']
        try: user = bot.get_user(u['user_id'])
        except Exception as e: 
            print(f'Error for {u["username"]}: {e}')
            continue
        if (n - datetime.datetime(n.year, n.month, n.day, daily.hour, daily.minute)).seconds // 60 < 5: #Announce in increments of 5 mins
            if f'{n:%m-%d-%Y}' in noClasses.keys():
                day = noClasses[f'{n:%m-%d-%Y}']
                embed=discord.Embed(title=f'{n:%A, %B %d}: No school', description=f"{'❄️' if day['snowDay'] else ''}Reason: {day['reason']}", color=0x66ccff if day['snowDay'] else 0xffff66)
                content = f'Good {timeOfDay}, today there is no school. See the embed for an explanation.'
            else:
                schedule = u['schedule']
                embed = (await buildSchedule(None, '', user, None, schedule))[0]
                content = f'Good {timeOfDay}, here is your schedule for the day.'
            #try: await user.send(content=content, embed=embed)
            #except: pass
            await user.send(content=content, embed=embed)

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
            except Exception as e: print(f'Cog load error: {e}')
        #await database.Verification(bot)
        #await Antispam.PrepareMembers(bot)
        #await bot.get_cog('Birthdays').updateBirthdays()
        # easterAnnouncement.start()
        #Cyberlog.ConfigureSummaries(bot)
        scheduleDeliveryLoop.start()
        emojis = bot.get_cog('Cyberlog').emojis
        def initializeCheck(m): return m.author.id == bot.user.id and m.channel.id == bot.get_cog('Cyberlog').imageLogChannel.id and m.content == 'Completed'
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

async def indexMessages(server, channel, full=False):
    path = f'{indexes}/{server.id}'
    start = datetime.datetime.now()
    try: os.makedirs(path)
    except FileExistsError: pass
    path += f'/{channel.id}.json'
    try: saveImages = await database.GetImageLogPerms(server) and not channel.is_nsfw()
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
            if not message.author.bot and (datetime.datetime.utcnow() - message.created_at).days < 7 and saveImages:
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

@bot.command()
async def privacy(ctx):
    await ctx.send("https://disguard.netlify.app/privacybasic")

@bot.command()
async def dashboard(ctx):
    await ctx.send(f"https://disguard.herokuapp.com/manage/{ctx.guild.id if ctx.guild else ''}\n\nUpon clicking the link, please allow a few seconds for the server to wake up")

@bot.command(aliases=['config', 'configuration', 'setup'])
async def server(ctx):
    '''Pulls up information about the current server, configuration-wise'''
    g = ctx.guild
    config = getData(bot).get(g.id)
    cyberlog = config.get('cyberlog')
    antispam = config.get('antispam')
    baseURL = f'http://disguard.herokuapp.com/manage/{ctx.guild.id}'
    green = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='online')
    red = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='dnd')
    embed=discord.Embed(title=f'Server Configuration - {g}', color=yellow[Cyberlog.colorTheme(ctx.guild)])
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

@bot.command(aliases=['feedback', 'ticket'])
async def support(ctx, *, opener=''):
    '''Command to initiate a feedback ticket. Anything typed after the command name will be used to start the support ticket
    Ticket status
    0: unopened by dev
    1: opened (dev has viewed)
    2: in progress (dev has replied)
    3: closed'''
    await ctx.trigger_typing()
    colorTheme = Cyberlog.colorTheme(ctx.guild) if ctx.guild else 1
    details = bot.get_cog('Cyberlog').emojis['details']
    def navigationCheck(r, u): return str(r) in reactions and r.message.id == status.id and u.id == ctx.author.id
    #If the user didn't provide a message with the command, prompt them with one here
    if opener.startsWith('System:'):
        specialCase = opener[opener.find(':') + 1:].strip()
        opener = ''
    else:
        specialCase = False
    if not opener:
        embed=discord.Embed(title='Disguard Support Menu', description=f"Welcome to Disguard support!\n\nIf you would easily like to get support, you may join my official server: https://discord.gg/xSGujjz\n\nIf you would like to get in touch with my developer without joining servers, react 🎟 to open a support ticket\n\nIf you would like to view your active support tickets, type `{getData(bot)[ctx.guild.id]['prefix'] if ctx.guild else '.'}tickets` or react {details}", color=yellow[colorTheme])
        status = await ctx.send(embed=embed)
        reactions = ['🎟', details]
        for r in reactions: await status.add_reaction(r)
        result = await bot.wait_for('reaction_add', check=navigationCheck)
        if result[0].emoji == details:
            await status.delete()
            return await ticketsCommand(ctx)
        await ctx.send('Please type the message you would like to use to start the support thread, such as a description of your problem or a question you have')
        def ticketCreateCheck(m): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
        try: result = await bot.wait_for('message', check=ticketCreateCheck, timeout=300)
        except asyncio.TimeoutError: return await ctx.send('Timed out')
        opener = result.content
    #If the command was used in DMs, ask the user if they wish to represent one of their servers
    if not ctx.guild:
        await ctx.trigger_typing()
        serverList = [g for g in bot.guilds if ctx.author in g.members] + ['<Prefer not to answer>']
        if len(serverList) > 2: #If the member is in more than one server with the bot, prompt for which server they're in
            alphabet = '🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿'
            newline = '\n'
            awaitingServerSelection = await ctx.send(f'Because we\'re in DMs, please provide the server you\'re representing by reacting with the corresponding letter\n\n{newline.join([f"{alphabet[i]}: {g}" for i, g in enumerate(serverList)])}')
            possibleLetters = [l for l in alphabet if l in awaitingServerSelection.content]
            for letter in possibleLetters: await awaitingServerSelection.add_reaction(letter)
            def selectionCheck(r, u): return str(r) in possibleLetters and r.message.id == awaitingServerSelection.id and u.id == ctx.author.id
            try: selection = await bot.wait_for('reaction_add', check=selectionCheck, timeout=300)
            except asyncio.TimeoutError: return await ctx.send('Timed out')
            server = serverList[alphabet.index(str(selection[0]))]
            if type(server) is str: server = None
        else: server = serverList[0]
    else: server = ctx.guild
    embed=discord.Embed(title=f'🎟 Disguard Ticket System / {loading} Creating Ticket...', color=yellow[colorTheme])
    status = await ctx.send(embed=embed)
    #Obtain server permissions for the member to calculate their prestige (rank of power in the server)
    if server: p = server.get_member(ctx.author.id).guild_permissions
    else: p = discord.Permissions.none()
    #Create ticket dictionary (number here is a placeholder)
    ticket = {'number': ctx.message.id, 'id': ctx.message.id, 'author': ctx.author.id, 'channel': str(ctx.channel), 'server': server.id if server else None, 'notifications': True, 'prestige': 'N/A' if not server else 'Server Owner' if ctx.author.id == server.owner.id else 'Server Administrator' if p.administrator else 'Server Moderator' if p.manage_server else 'Junior Server Moderator' if p.kick_members or p.ban_members or p.manage_channels or p.manage_roles or p.manage_members else 'Server Member', 'status': 0, 'conversation': []}
    #If a ticket was created in a special manner, this system message will be the first message
    if specialCase: ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{specialCase}*'})
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
    embed.description = f'''Your support ticket has successfully been created\n\nTicket number: {ticket['number']}\nAuthor: {ctx.author.name}\nMessage: {opener}\n\nTo view this ticket, react 🎟 or type `{getData(bot)[ctx.guild.id]['prefix'] if ctx.guild else "."}tickets {ticket['number']}`, which will allow you to add members to the support thread if desired, disable DM notifications, reply, and more.'''
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
    colorTheme = Cyberlog.colorTheme(ctx.guild) if ctx.guild else 1
    #emojis = bot.get_cog('Cyberlog').emojis
    global emojis
    trashcan = emojis['delete']
    statusDict = {0: 'Unopened', 1: 'Viewed', 2: 'In progress', 3: 'Closed', 4: 'Locked'}
    message = await ctx.send(embed=discord.Embed(description=f'{loading}Downloading ticket data'))
    tickets = await database.GetSupportTickets()
    embed=discord.Embed(title=f"🎟 Disguard Ticket System / {emojis['details']} Browse Your Tickets", color=yellow[colorTheme])
    embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url_as(static_format='png'))
    if len(tickets) == 0: 
        embed.description = 'There are currently no tickets in the system'
        return await message.edit(embed=embed)
    def organize(sortMode):
        if sortMode == 0: filtered.sort(key = lambda x: x['conversation'][-1]['timestamp'], reverse=True) #Recently active tickets first
        elif sortMode == 1: filtered.sort(key = lambda x: x['conversation'][-1]['timestamp']) #Recently active tickets last
        elif sortMode == 2: filtered.sort(key = lambda x: x['number'], reverse=True) #Highest ticket numbers first
        elif sortMode == 3: filtered.sort(key = lambda x: x['number']) #Lowest ticket numbers first
    def paginate(iterable, resultsPerPage=10):
        for i in range(0, len(iterable), resultsPerPage): yield iterable[i : i + resultsPerPage]
    def populateEmbed(pages, index, sortDescription):
        embed.clear_fields()
        embed.description = f'''{f'NAVIGATION':-^70}\n{trashcan}: Delete this embed\n{emojis['details']}: Adjust sort\n◀: Previous page\n🇦 - {alphabet[len(pages[index]) - 1]}: View ticket\n▶: Next page\n{f'Tickets for {ctx.author.name}':-^70}\nPage {index + 1} of {len(pages)}\nViewing {len(pages[index])} of {len(filtered)} results\nSort: {sortDescription}'''
        for i, ticket in enumerate(pages[index]):
            tg = g #probably stands for 'ticketGuild'
            if not tg and ticket['server']: tg = bot.get_guild(ticket['server'])
            embed.add_field(
                name=f"{alphabet[i]}Ticket {ticket['number']}",
                value=f'''> Members: {", ".join([bot.get_user(u['id']).name for i, u in enumerate(ticket['members']) if i not in (1, 2)])}\n> Status: {statusDict[ticket['status']]}\n> Latest reply: {bot.get_user(ticket['conversation'][-1]['author']).name} • {(ticket['conversation'][-1]['timestamp'] + datetime.timedelta(hours=(getData(bot)[tg.id]['offset'] if tg else -5))):%b %d, %Y • %I:%M %p} {getData(bot)[tg.id]['tzname'] if tg else 'EST'}\n> {qlf}{ticket['conversation'][-1]['message']}''',
                inline=False)
    async def notifyMembers(ticket):
        e = discord.Embed(title=f"New activity in ticket {ticket['number']}", description=f"To view the ticket, use the tickets command (`.tickets {ticket['number']}`)\n\n{'Highlighted message':-^70}", color=yellow[ticketColorTheme])
        entry = ticket['conversation'][-1]
        messageAuthor = bot.get_user(entry['author'])
        e.set_author(name=messageAuthor, icon_url=messageAuthor.avatar_url_as(static_format='png'))
        e.add_field(
            name=f"{messageAuthor.name} • {(entry['timestamp'] + datetime.timedelta(hours=(getData(bot)[tg.id]['offset'] if tg else -5))):%b %d, %Y • %I:%M %p} {getData(bot)[tg.id]['tzname'] if tg else 'EST'}",
            value=f'> {entry["message"]}',
            inline=False)
        e.set_footer(text=f"You are receiving this DM because you have notifications enabled for ticket {ticket['number']}. View the ticket to disable notifications.")
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
        embed.description = f"There are currently no tickets in the system created by or involving you. To create a feedback ticket, type `{getData(bot)[ctx.guild.id]['prefix'] if ctx.guild else '.'}ticket`"
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
            await message.edit(content=f'The ticket number you provided ({number}) is invalid. Switching to browse view.')
            number = None
        if not number:
            if ctx.guild: 
                if clearReactions: await message.clear_reactions()
                else: clearReactions = True
                await message.edit(embed=embed)
            else:
                await message.delete()
                message = await ctx.send(content=message.content, embed=embed)
            reactions = [trashcan, emojis['details'], emojis['arrowBackwards']] + alphabet[:len(pages[currentPage])] + [emojis['arrowForwards']]
            for r in reactions: await message.add_reaction(r)
            destination = await bot.wait_for('reaction_add', check=optionNavigation)
            try: await message.remove_reaction(*destination)
            except: pass
        else: destination = [alphabet[0]]
        async def clearMessageContent():
            await asyncio.sleep(5)
            if datetime.datetime.now() > clearAt: await message.edit(content=None)
        clearAt = None
        if destination[0].emoji == trashcan: return await message.delete()
        elif destination[0].emoji == emojis['details']:
            clearReactions = False
            sortMode += 1 if sortMode != 3 else -3
            messageContent = '--SORT MODE--\n' + '\n'.join([f'> **{d}**' if i == sortMode else f'{qlfc}{d}' for i, d in enumerate(sortDescriptions)])
            await message.edit(content=messageContent)
            clearAt = datetime.datetime.now() + datetime.timedelta(seconds=4)
            asyncio.create_task(clearMessageContent())
        elif destination[0].emoji in (emojis['arrowBackward'], emojis['arrowForward']):
            if destination[0].emoji == emojis['arrowBackward']: currentPage -= 1
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
            #If I view the ticket and it's marked as not viewed yet, mark it as viewed
            if ctx.author.id == 247412852925661185 and ticket['status'] < 1: ticket['status'] = 1
            member = [m for m in ticket['members'] if m['id'] == ctx.author.id][0]
            if member['permissions'] == 3: #If member has a pending invite to the current ticket
                embed.clear_fields()
                back = emojis['arrowLeft']
                greenCheck = emojis['greenCheck']
                embed.description=f"You've been invited to this support ticket (Ticket {number})\n\nWhat would you like to do?\n{back}: Go back\n❌: Decline invite\n{greenCheck}: Accept invite"
                reactions = [back, '❌', greenCheck]
                if ctx.guild: 
                    if clearReactions: await message.clear_reactions()
                    else: clearReactions = True
                    await message.edit(embed=embed)
                else:
                    await message.delete()
                    message = await ctx.send(embed=embed)
                for r in reactions: await message.add_reaction(str(r))
                result = await bot.wait_for('reaction_add', check=optionNavigation)
                if result[0].emoji == greenCheck:
                    ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} accepted their invite*'})
                    member.update({'permissions': 1, 'notifications': True})
                    asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                else:
                    if str(result[0]) == '❌':
                        ticket['members'].remove(member)
                        ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} declined their invite*'})
                        asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                    number = None
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
                ticketColorTheme = Cyberlog.colorTheme(tg) if tg else 1
                def returnPresence(status): return emojis['hiddenVoiceChannel'] if status == 4 else emojis['online'] if status == 3 else emojis['idle'] if status in (1, 2) else emojis['dnd']
                reactions = [emojis['arrowLeft'], emojis['members'], emojis['reply']]
                reactions.insert(2, emojis['bell'] if not ctx.guild or not member['notifications'] else emojis['bellMute'])
                conversationPages = list(paginate(ticket['conversation'], 7))
                if len(conversationPages) > 0 and currentConversationPage != 0: reactions.insert(reactions.index(emojis['members']) + 2, emojis['arrowBackward'])
                if len(conversationPages) > 0 and currentConversationPage != len(conversationPages) - 1: reactions.insert(reactions.index(emojis['reply']) + 1, emojis['arrowForward'])
                if member['permissions'] == 0: reactions.remove(emojis['reply'])
                if ctx.author.id == 247412852925661185: reactions.append(emojis['hiddenVoiceChannel'])
                embed.title = f'🎟 Disguard Ticket System / Ticket {number}'
                embed.description = f'''{'TICKET DATA':-^70}\n{emojis['member']}Author: {bot.get_user(ticket['author'])}\n⭐Prestige: {ticket['prestige']}\n{emojis['members']}Other members involved: {', '.join([bot.get_user(u["id"]).name for u in ticket['members'] if u["id"] not in (247412852925661185, bot.user.id, ctx.author.id)]) if len(ticket['members']) > 3 else f'None - react {emojis["members"]} to add'}\n⛓Server: {bot.get_guild(ticket['server'])}\n{returnPresence(ticket['status'])}Dev visibility status: {statusDict.get(ticket['status'])}\n{emojis['bell'] if member['notifications'] else emojis['bellMute']}Notifications: {member['notifications']}\n\n{f'CONVERSATION - {emojis["reply"]} to reply' if member['permissions'] > 0 else 'CONVERSATION':-^70}\nPage {currentConversationPage + 1} of {len(conversationPages)}{f'{newline}{emojis["arrowBackward"]} and {emojis["arrowForward"]} to navigate' if len(conversationPages) > 1 else ''}\n\n'''
                for entry in conversationPages[currentConversationPage]: embed.add_field(name=f"{bot.get_user(entry['author']).name} • {(entry['timestamp'] + datetime.timedelta(hours=(getData(bot)[tg.id]['offset'] if tg else -4))):%b %d, %Y • %I:%M %p} {getData(bot)[tg.id]['tzname'] if tg else 'EST'}", value=f'> {entry["message"]}', inline=False)
                if ctx.guild: 
                    if clearReactions: await message.clear_reactions()
                    else: clearReactions = True
                    await message.edit(content=None, embed=embed)
                else:
                    await message.delete()
                    message = await ctx.send(embed=embed)
                for r in reactions: await message.add_reaction(r)
                result = await bot.wait_for('reaction_add', check=optionNavigation)
                if result[0].emoji == emojis['arrowBackward']: break
                elif result[0].emoji == emojis['hiddenVoiceChannel']:
                    ticket['status'] = 3
                    ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*My developer has closed this support ticket. If you still need assistance on this matter, you may reopen it by responding to it. Otherwise, it will silently lock in 7 days.*'})
                    await notifyMembers(ticket)
                elif result[0].emoji in (emojis['arrowBackward'], emojis['arrowForward']):
                    if result[0].emoji == emojis['arrowBackward']: currentConversationPage -= 1
                    else: currentConversationPage += 1
                    if currentConversationPage < 0: currentConversationPage = 0
                    if currentConversationPage == len(conversationPages): currentConversationPage = len(conversationPages) - 1
                elif result[0].emoji == emojis['members']:
                    embed.clear_fields()
                    permissionsDict = {0: 'View ticket', 1: 'View and respond to ticket', 2: 'Ticket Owner (View, Respond, Manage Sharing)', 3: 'Invite sent'}
                    memberResults = []
                    while True:
                        def calculateBio(m): 
                            return '(No description)' if type(m) is not discord.Member else "Server Owner" if server.owner.id == m.id else "Server Administrator" if m.guild_permissions.administrator else "Server Moderator" if m.guild_permissions.manage_guild else "Junior Server Moderator" if m.guild_permissions.manage_roles or m.guild_permissions.manage_channels else '(No description)'
                        if len(memberResults) == 0: staffMemberResults = [m for m in server.members if any([m.guild_permissions.administrator, m.guild_permissions.manage_guild, m.guild_permissions.manage_channels, m.guild_permissions.manage_roles, m.id == server.owner.id]) and not m.bot and m.id not in [mb['id'] for mb in ticket['members']]][:15]
                        memberFillerText = [f'{bot.get_user(u["id"])}{newline}> {u["bio"]}{newline}> Permissions: {permissionsDict[u["permissions"]]}' for u in ticket['members']]
                        embed.description = f'''**__{'TICKET SHARING SETTINGS':-^85}__\n\n{'Permanently included':-^40}**\n{newline.join([f'👤{f}' for f in memberFillerText[:3]])}'''
                        embed.description += f'''\n\n**{'Additional members':-^40}**\n{newline.join([f'{emojis["member"]}{f}{f"{newline}> {alphabet[i]} to manage" if ctx.author.id == ticket["author"] else ""}' for i, f in enumerate(memberFillerText[3:])]) if len(memberFillerText) > 2 else 'None yet'}'''
                        if ctx.author.id == ticket['author']: embed.description += f'''\n\n**{'Add a member':-^40}**\nSend a message to search for a member to add, then react with the corresponding letter to add them{f'{newline}{newline}Moderators of {bot.get_guild(ticket["server"])} are listed below as suggestions. You may react with the letter next to their name to quickly add them, otherwise send a message to search for someone else' if ticket['server'] and len(staffMemberResults) > 0 else ''}'''
                        reactions = [emojis['arrowLeft']]
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
                        if type(result) is tuple: #Meaning a reaction, rather than a message search
                            if str(result[0]) in alphabet:
                                if not embed.description[embed.description.find(str(result[0])) + 2:].startswith('to manage'):
                                    addMember = memberResults[alphabet.index(str(result[0]))]
                                    invite = discord.Embed(title='🎟 Invited to ticket', description=f"Hey {addMember.name},\n{ctx.author.name} has invited you to **support ticket {ticket['number']}** with [{', '.join([bot.get_user(m['id']).name for i, m in enumerate(ticket['members']) if i not in (1, 2)])}].\n\nThe Disguard support ticket system is a tool for server members to easily get in touch with my developer for issues, help, and questions regarding the bot\n\nTo join the support ticket, type `.tickets {ticket['number']}`", color=yellow[ticketColorTheme])
                                    invite.set_footer(text=f'You are receiving this DM because {ctx.author} invited you to a Disguard support ticket')
                                    try: 
                                        await addMember.send(embed=invite)
                                        ticket['members'].append({'id': addMember.id, 'bio': calculateBio(addMember), 'permissions': 3, 'notifications': False})
                                        ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} invited {addMember} to the ticket*'})
                                        memberResults.remove(addMember)
                                    except Exception as e: await ctx.send(f'Error inviting {addMember} to ticket: {e}.\n\nBTW, error code 50007 means that the recipient disabled DMs from server members - they will need to temporarily allow this in the `Server Options > Privacy Settings` or `User Settings > Privacy & Safety` in order to be invited')
                                else:
                                    user = bot.get_user([mb['id'] for mb in ticket['members']][2 + len([l for l in alphabet if l in embed.description])]) #Offset - the first three members in the ticket are permanent
                                    while True:
                                        if ctx.author.id != ticket['author']: break #If someone other than the ticket owner gets here, deny them
                                        ticketUser = [mb for mb in ticket['members'] if mb['id'] == user.id][0]
                                        embed.description=f'''**{f'Manage {user.name}':-^70}**\n{'🔒' if not ctx.guild or ticketUser['permissions'] == 0 else '🔓'}Permissions: {permissionsDict[ticketUser['permissions']]}\n\n{emojis['details']}Responses: {len([r for r in ticket['conversation'] if r['author'] == user.id])}\n\n{f'{emojis["bell"]}Notifications: True' if ticketUser['notifications'] else f'{emojis["bellMute"]}Notifications: False'}\n\n❌: Remove this member'''
                                        reactions = [emojis['arrowLeft'], '🔓' if ctx.guild and ticketUser['permissions'] == 0 else '🔒', '❌'] #The reason we don't use the unlock if the command is used in DMs is because we can't remove user reactions ther
                                        if ctx.guild: 
                                            if clearReactions: await message.clear_reactions()
                                            else: clearReactions = True
                                            await message.edit(content=None, embed=embed)
                                        else:
                                            await message.delete()
                                            message = await ctx.send(embed=embed)
                                        for r in reactions: await message.add_reaction(r)
                                        result = await bot.wait_for('reaction_add', check=optionNavigation)
                                        if result[0].emoji == emojis['arrowLeft']: break
                                        elif str(result[0]) == '❌':
                                            ticket['members'] = [mbr for mbr in ticket['members'] if mbr['id'] != user.id]
                                            ticket['conversation'].append({'author': bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} removed {user} from the ticket*'})
                                            break
                                        else:
                                            if str(result[0]) == '🔒':
                                                if ctx.guild: reactions = [emojis['arrowLeft'], '🔓', '❌']
                                                else: clearReactions = False
                                                ticketUser['permissions'] = 0
                                            else:
                                                if ctx.guild: reactions = [emojis['arrowLeft'], '🔒', '❌']
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
                elif result[0].emoji == emojis['reply']:
                    embed.description = f'**__Please type your response (under 1024 characters) to the conversation, or react {emojis["arrowLeft"]} to cancel__**'
                    reactions = [emojis['arrowLeft']]
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
                elif result[0].emoji in (emojis['bell'], emojis['bellMute']): member['notifications'] = not member['notifications']
                ticket['members'] = [member if i == memberIndex else m for i, m in enumerate(ticket['members'])]
                asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
        number = None #Triggers browse mode
        try:
            if datetime.datetime.now() > clearAt: await message.edit(content=None)
        except UnboundLocalError: await message.edit(content=None)

@bot.command(aliases = ['schedule'])
async def _schedule(ctx, *, desiredDate=None):
    await ctx.trigger_typing()
    yellow = (0xffff00, 0xffff66)
    pRoles = [619514236736897024, 739597955178430525, 615002577007804416, 668263236214456320, 623685383489585163, 565694432494485514] #List of roles able to use this command
    wantsToEdit = False
    statusMessage = None
    reactions = []
    #emojis = bot.get_cog('Cyberlog').emojis
    schedule = {}
    initialSchedule = {}
    initialPassedDate = ''
    global emojis
    def reactionCheck(r, u): 
        nonlocal statusMessage
        return r.emoji in reactions and r.message.id == statusMessage.id and u.id == ctx.author.id and not u.bot
    def messageCheck(m): 
        return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
    def bold(x, comparison): return f'**{x}**' if x != comparison else x
    async def lastNameInput(breakAfter = False):
        nonlocal reactions
        nonlocal statusMessage
        reactions = [emojis['next']]
        if schedule['lastInitial']: lastInitial = schedule['lastInitial']
        else: lastInitial = 'Waiting for input'
        string = f"Welcome to schedule setup! Since you're setting up a new schedule, let's go over the basics:\n{qlf}• Your schedule is private and only accessible to you, unless you use this command in a server and allow me to post your schedule after a confirmation prompt"
        string += f'\n{qlf}• This command may be expanded with new features as time goes on. By default, you\'ll be DMd about important changes, but this can be turned off.\n{qlf}• If you make a mistake during setup, you can always type a new value or reset the current step\n{qlf}• If you are resetting an existing schedule, the old one will not be overwritten until you save your changes at the end of setup\n{qlf}• To edit settings at a later date, use `{getData(bot)[ctx.guild.id]["prefix"] if ctx.guild else "."}schedule edit` or the reaction attached to schedules to edit parts as needed, or `{getData(bot)[ctx.guild.id]["prefix"] if ctx.guild else "."}schedule set` to go through the full setup process\n\n{qlf}If you wish to exit setup at any time, type `cancel`.\n{qlf}During the entirety of setup, use {emojis["previous"]} and {emojis["next"]} to navigate through the steps.\n{qlf}Please note that the general flow of the data editing features of the schedule module work best in servers due to DM limitations (removing reactions from messages)\n\n(Required) Step 1/5: Let\'s get started with you entering your last name, due to the current alphabet split. (Only the first letter will be stored)\n\nLast initial: `{lastInitial}`'
        oldPrompt = None
        if ctx.guild and statusMessage: 
            statusMessage = await ctx.channel.fetch_message(statusMessage.id)
            if [r.emoji for r in statusMessage.reactions] != reactions: await statusMessage.clear_reactions()
            await statusMessage.edit(content=string, embed=None)
        else: 
            if breakAfter and statusMessage: oldPrompt = statusMessage
            statusMessage = await ctx.send(string)
        for r in reactions: await statusMessage.add_reaction(r)
        while True:
            d, p = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=reactionCheck)], return_when=asyncio.FIRST_COMPLETED)
            try: result = d.pop().result()
            except: result = None
            for f in p: f.cancel()
            if type(result) is discord.Message:
                if result.content.lower() == 'cancel': return await ctx.send('Cancelled setup')
                lastInitial = result.content[0].upper()
                await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('Last initial') + 14] + f'`{lastInitial}`')
                if ctx.guild:
                    bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                    await result.delete()
            else:
                if ctx.guild: await statusMessage.remove_reaction(*result)
                break
        schedule['lastInitial'] = lastInitial
        if breakAfter: 
            try: await oldPrompt.delete()
            except: pass
            return lastInitial, statusMessage
        else: await classesInput()

    async def classesInput(breakAfter = False):
        nonlocal reactions
        nonlocal statusMessage
        reactions = [emojis['previous'], emojis['reload'], emojis['next']]
        if breakAfter: reactions.pop(0)
        if schedule['classes']: classes = schedule['classes']
        else: 
            classes = [None, 'Advisory', None, None, None, None, None, None, None]
            initialSchedule['classes'] = copy.deepcopy(classes)
        def buildClassString():
            s = ''
            for i, c in enumerate(classes):
                s += f'''{str(emojis['arrowForward']) if str(emojis['arrowForward']) not in s and None in classes and c == None else qlf}{f"P{1 if i == 0 else i + 1}" if i != 1 else f"Advisory"}{f": {bold(c, initialSchedule['classes'][i]) if c else '<Waiting for input>'}"}\n'''
            if None not in classes: s += f"\n\n{emojis['greenCheck']} All classes are set. {'Next step: teachers' if not breakAfter else ''}"
            return s
        string = f'(Required) Step 2/5: Class Periods\nYou may enter your class periods in the following ways:\n•Type a single message, and the class represented by the arrow will be set with your input\n•Type multiple classes, each on their own lines, or separated by a comma and a space - classes starting from the arrow will be filled by your input\n•Type `p1: <classname>` to set or overwrite a certain class\n•Do not enter advisory on this page\nUse {emojis["reload"]} to reset the class list.\n\n{buildClassString()}'
        oldPrompt = None
        if ctx.guild and statusMessage: 
            statusMessage = await ctx.channel.fetch_message(statusMessage.id)
            if [r.emoji for r in statusMessage.reactions] != reactions: await statusMessage.clear_reactions()
            await statusMessage.edit(content=string, embed=None)
        else: 
            if breakAfter and statusMessage: oldPrompt = statusMessage
            statusMessage = await ctx.send(string)
        for r in reactions: await statusMessage.add_reaction(r)
        while True:
            d, p = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=reactionCheck)], return_when=asyncio.FIRST_COMPLETED)
            try: result = d.pop().result()
            except: result = None
            for f in p: f.cancel()
            if type(result) is discord.Message:
                if result.content.lower() == 'cancel': return await ctx.send('Cancelled setup')
                if ':' in result.content:
                    classIndex = int(result.content[result.content.find(':') - 1])
                    if classIndex == 1: classIndex = 0
                    else: classIndex -= 1
                    toWrite = result.content[result.content.find(':') + 1:].strip()
                    classes[classIndex] = toWrite if 'skip' not in toWrite.lower() else 0
                else:
                    if ',' in result.content or '\n' in result.content:
                        if ',' in result.content: classesToWrite = result.content.split(', ')
                        else: classesToWrite = result.content.split('\n')
                    else: classesToWrite = [result.content]
                    try: classIndex = classes.index(None)
                    except ValueError: classIndex = 0
                    while len(classesToWrite) > 0:
                        if classIndex != 1:
                            classes[classIndex] = classesToWrite[0] if 'skip' not in classesToWrite[0].lower() else 0
                            classesToWrite.pop(0)
                        classIndex += 1
                        if classIndex == 9: classIndex = 0
                await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n') + 2] + buildClassString())
                if ctx.guild:
                    bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                    await result.delete()
            else:
                if ctx.guild: await statusMessage.remove_reaction(*result)
                if result[0].emoji == emojis['reload']:
                    classes = [None, 'Advisory', None, None, None, None, None, None, None]
                    await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n') + 2] + buildClassString())
                elif result[0].emoji == emojis['previous']:
                    schedule['classes'] = classes
                    return await lastNameInput()
                else: break
        schedule['classes'] = classes
        if breakAfter: 
            try: await oldPrompt.delete()
            except: pass
            return classes, statusMessage
        else: await teachersInput()

    async def teachersInput(breakAfter = False):
        nonlocal reactions
        nonlocal statusMessage
        reactions = [emojis['previous'], emojis['reload'], emojis['next']]
        if breakAfter: reactions.pop(0)
        if schedule['teachers']: teachers = schedule['teachers']
        else: 
            teachers = [None, None, None, None, None, None, None, None, None]
            initialSchedule['teachers'] = copy.deepcopy(teachers)
        def buildTeacherString():
            s = ''
            for i, c in enumerate(teachers):
                s += f'''{str(emojis['arrowForward']) if str(emojis['arrowForward']) not in s and None in teachers and c == None else qlf}{f"P{1 if i == 0 else i + 1}" if i != 1 else f"Advisory"}{f": {bold(c, initialSchedule['teachers'][i]) if type(c) is str else '<Skipped>' if c == 0 else '<Not specified>'}"}\n'''
            if None not in teachers: s += f"\n\n{emojis['greenCheck']} All teachers are set. {'Next step: room numbers' if not breakAfter else ''}"
            return s
        string = f'(Optional) Step 3/5: Teachers\nIf you would like to add the teacher for your classes, you may do so now. Enter data in the same manner as the classes page (go back to see the guide again - your data will save). To skip a teacher for a class, type `skip` for their name leave their field blank.\n\n{buildTeacherString()}'
        oldPrompt = None
        if ctx.guild and statusMessage: 
            statusMessage = await ctx.channel.fetch_message(statusMessage.id)
            if [r.emoji for r in statusMessage.reactions] != reactions: await statusMessage.clear_reactions()
            await statusMessage.edit(content=string, embed=None)
        else: 
            if breakAfter and statusMessage: oldPrompt = statusMessage
            statusMessage = await ctx.send(string)
        for r in reactions: await statusMessage.add_reaction(r)
        while True:
            d, p = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=reactionCheck)], return_when=asyncio.FIRST_COMPLETED)
            try: result = d.pop().result()
            except: result = None
            for f in p: f.cancel()
            if type(result) is discord.Message:
                if result.content.lower() == 'cancel': return await ctx.send('Cancelled setup')
                if ':' in result.content:
                    try: 
                        classIndex = int(result.content[result.content.find(':') - 1])
                        if classIndex == 1: classIndex = 0
                        else: classIndex -= 1
                    except ValueError: classIndex = 1
                    toWrite = result.content[result.content.find(':') + 1:].strip()
                    teachers[classIndex] = toWrite if 'skip' not in toWrite.lower() else 0
                else:
                    if ',' in result.content or '\n' in result.content:
                        if ',' in result.content: classesToWrite = result.content.split(', ')
                        else: classesToWrite = result.content.split('\n')
                    else: classesToWrite = [result.content]
                    try: classIndex = teachers.index(None)
                    except ValueError: classIndex = 0
                    while len(classesToWrite) > 0:
                        teachers[classIndex] = classesToWrite[0] if 'skip' not in classesToWrite[0].lower() else 0
                        classesToWrite.pop(0)
                        classIndex += 1
                        if classIndex == 9: classIndex = 0 
                await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n') + 2] + buildTeacherString())
                if ctx.guild:
                    bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                    await result.delete()
            else:
                if ctx.guild: await statusMessage.remove_reaction(*result)
                if result[0].emoji == emojis['reload']:
                    teachers = [None, None, None, None, None, None, None, None, None]
                    await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n') + 2] + buildTeacherString())
                elif result[0].emoji == emojis['previous']:
                    for i, t in enumerate(teachers):
                        if t == 0: teachers[i] = None
                    schedule['teachers'] = teachers
                    return await classesInput()
                else: break
        for i, t in enumerate(teachers):
            if t == 0: teachers[i] = None
        schedule['teachers'] = teachers
        if breakAfter: 
            try: await oldPrompt.delete()
            except: pass
            return teachers, statusMessage
        else: await roomsInput()

    async def roomsInput(breakAfter = False):
        nonlocal reactions
        nonlocal statusMessage
        reactions = [emojis['previous'], emojis['reload'], emojis['next']]
        if breakAfter: reactions.pop(0)
        if schedule['rooms']: rooms = schedule['rooms']
        else: 
            rooms = [None, None, None, None, None, None, None, None, None]
            initialSchedule['rooms'] = copy.deepcopy(rooms)
        def buildRoomsString():
            s = ''
            for i, c in enumerate(rooms):
                s += f'''{str(emojis['arrowForward']) if str(emojis['arrowForward']) not in s and None in rooms and c == None else qlf}{f"P{1 if i == 0 else i + 1}" if i != 1 else "Advisory"}{f": {bold(c, initialSchedule['rooms'][i]) if type(c) is str else '<Skipped>' if c == 0 else '<Not specified>'}"}\n'''
            if None not in rooms: s += f"\n\n{emojis['greenCheck']} All rooms are set. {'Next step: lunches' if not breakAfter else ''}"
            return s
        string = f'(Optional) Step 4/5: Room numbers\nIf you would like to add the room number for your classes, you may do so now. Perform this in a similar manner to adding teachers. To skip a room number for a class, type `skip` for its class period or leave its field blank.\n\n{buildRoomsString()}'
        oldPrompt = None
        if ctx.guild and statusMessage: 
            statusMessage = await ctx.channel.fetch_message(statusMessage.id)
            if [r.emoji for r in statusMessage.reactions] != reactions: await statusMessage.clear_reactions()
            await statusMessage.edit(content=string, embed=None)
        else: 
            if breakAfter and statusMessage: oldPrompt = statusMessage
            statusMessage = await ctx.send(string)
        for r in reactions: await statusMessage.add_reaction(r)
        while True:
            d, p = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=reactionCheck)], return_when=asyncio.FIRST_COMPLETED)
            try: result = d.pop().result()
            except: result = None
            for f in p: f.cancel()
            if type(result) is discord.Message:
                if result.content.lower() == 'cancel': return await ctx.send('Cancelled setup')
                if ':' in result.content:
                    try: 
                        classIndex = int(result.content[result.content.find(':') - 1])
                        if classIndex == 1: classIndex = 0
                        else: classIndex -= 1
                    except ValueError: classIndex = 1
                    toWrite = result.content[result.content.find(':') + 1:].strip()
                    rooms[classIndex] = toWrite if 'skip' not in toWrite.lower() else 0
                else:
                    if ',' in result.content or '\n' in result.content:
                        if ',' in result.content: classesToWrite = result.content.split(', ')
                        else: classesToWrite = result.content.split('\n')
                    else: classesToWrite = [result.content]
                    try: classIndex = rooms.index(None)
                    except ValueError: classIndex = 0
                    while len(classesToWrite) > 0:
                        rooms[classIndex] = classesToWrite[0] if 'skip' not in classesToWrite[0].lower() else 0
                        classesToWrite.pop(0)
                        classIndex += 1
                        if classIndex == 9: classIndex = 0
                await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n') + 2] + buildRoomsString())
                if ctx.guild:
                    bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                    await result.delete()
            else:
                if ctx.guild: await statusMessage.remove_reaction(*result)
                if result[0].emoji == emojis['reload']:
                    rooms = [None, None, None, None, None, None, None, None, None]
                    await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n') + 2] + buildRoomsString())
                elif result[0].emoji == emojis['previous']:
                    for i, t in enumerate(rooms):
                        if t == 0: rooms[i] = None
                    schedule['rooms'] = rooms
                    return await teachersInput()
                else: break
        for i, t in enumerate(rooms):
            if t == 0: rooms[i] = None #variable T b/c copy and paste
        schedule['rooms'] = rooms
        if breakAfter: 
            try: await oldPrompt.delete()
            except: pass
            return rooms, statusMessage
        else: await lunchInput()

    async def lunchInput(breakAfter = False):
        nonlocal reactions
        nonlocal statusMessage
        reactions = [emojis['previous'], emojis['reload'], emojis['next']]
        if breakAfter: reactions.pop(0)
        if schedule['lunches']: lunches = schedule['lunches']
        else: 
            lunches = [None, 'N/A', None, None, None, None, None, None, None]
            initialSchedule['lunches'] = copy.deepcopy(lunches)
        def buildLunchesString():
            s = ''
            for i, c in enumerate(lunches):
                s += f'''{str(emojis['arrowForward']) if str(emojis['arrowForward']) not in s and None in lunches and c == None else qlf}{f"P{1 if i == 0 else i + 1}" if i != 1 else "Advisory"}{f": {bold(c, initialSchedule['lunches'][i]) if type(c) is str else '<Skipped>' if c == 0 else '<Not specified>'}"}\n'''
            if None not in lunches: s += f"\n\n{emojis['greenCheck']} All lunch periods are set. {'Next step: Save & view your completed schedule' if not breakAfter else ''}"
            return s
        string = f'(Optional) Step 5/5: Lunch periods\nIf you would like to add the lunch period for your classes, you may do so now. Type a single letter for each period (it will automatically be capitalized). To skip a lunch for a class, type `skip` for its class period or leave its field blank.\n\n{buildLunchesString()}'
        oldPrompt = None
        if ctx.guild and statusMessage: 
            statusMessage = await ctx.channel.fetch_message(statusMessage.id)
            if [r.emoji for r in statusMessage.reactions] != reactions: await statusMessage.clear_reactions()
            await statusMessage.edit(content=string, embed=None)
        else: 
            if breakAfter and statusMessage: oldPrompt = statusMessage
            statusMessage = await ctx.send(string)
        for r in reactions: await statusMessage.add_reaction(r)
        while True:
            d, p = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=reactionCheck)], return_when=asyncio.FIRST_COMPLETED)
            try: result = d.pop().result()
            except: result = None
            for f in p: f.cancel()
            if type(result) is discord.Message:
                if result.content.lower() == 'cancel': return await ctx.send('Cancelled setup')
                if ':' in result.content:
                    try: 
                        classIndex = int(result.content[result.content.find(':') - 1])
                        if classIndex == 1: classIndex = 0
                        else: classIndex -= 1
                    except ValueError: classIndex = 1
                    toWrite = result.content[result.content.find(':') + 1:].strip()
                    lunches[classIndex] = toWrite if 'skip' not in toWrite.lower() else 0
                else:
                    if ',' in result.content or '\n' in result.content:
                        if ',' in result.content: classesToWrite = result.content.split(', ')
                        else: classesToWrite = result.content.split('\n')
                    else: classesToWrite = [result.content]
                    try: classIndex = lunches.index(None)
                    except ValueError: classIndex = 0
                    while len(classesToWrite) > 0:
                        if classIndex != 1:
                            lunches[classIndex] = classesToWrite[0] if 'skip' not in classesToWrite[0].lower() else 0
                            classesToWrite.pop(0)
                        classIndex += 1
                        if classIndex == 9: classIndex = 0
                await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n') + 2] + buildLunchesString())
                if ctx.guild:
                    bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                    await result.delete()
            else:
                if ctx.guild: await statusMessage.remove_reaction(*result)
                if result[0].emoji == emojis['reload']:
                    lunches = [None, None, None, None, None, None, None, None, None]
                    await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n') + 2] + buildLunchesString())
                elif result[0].emoji == emojis['previous']:
                    for i, t in enumerate(lunches):
                        if t == 0: lunches[i] = None
                    schedule['lunches'] = lunches
                    return await roomsInput()
                else: break
        for i, t in enumerate(lunches):
            if t == 0: lunches[i] = None
        schedule['lunches'] = lunches
        if breakAfter: 
            try: await oldPrompt.delete()
            except: pass
            return lunches, statusMessage
        else: await saveSchedule()
    
    async def saveSchedule():
        nonlocal reactions
        nonlocal statusMessage
        await statusMessage.edit(content=f'{loading} Saving schedule...')
        await database.SetSchedule(ctx.author, schedule)
        await statusMessage.edit(content=f'Schedule setup complete!\n{qlf}To reset your schedule, type `{getData(bot)[ctx.guild.id]["prefix"] if ctx.guild else "."}schedule set`\n{qlf}To edit your schedule or other settings, type `{getData(bot)[ctx.guild.id]["prefix"] if ctx.guild else "."}schedule edit` or use the reaction attached to the schedule\n{qlf}You may type a day after the command (such as "tomorrow," "Friday," or "September 21") to view the schedule for that day\n\nReact {emojis["details"]} or use the schedule command again to view your schedule')
        reactions = [emojis['details']]
        if ctx.guild: await statusMessage.clear_reactions()
        for r in reactions: await statusMessage.add_reaction(r)
        await bot.wait_for('reaction_add', check=reactionCheck, timeout=None)
        if ctx.guild: await statusMessage.clear_reactions()

    async def bulkEdit():
        nonlocal reactions
        nonlocal statusMessage
        nonlocal schedule
        reactions = ['❌', emojis['greenCheck']]
        def buildClassesString():
            s = ''
            for i in range(9):
                c = (schedule['classes'][i], initialSchedule['classes'][i])
                t = (schedule['teachers'][i], initialSchedule['teachers'][i])
                r = (schedule['rooms'][i], initialSchedule['rooms'][i])
                l = (schedule['lunches'][i], initialSchedule['lunches'][i])
                s += f'''{f"P{i + 1}" if i != 1 else "Advisory"}: {f"{bold(*c)}"}{f" • {bold(*t)}" if t[0] else ' • <No teacher specified>'}{f" • Rm {bold(*r)}" if r[0] else ' • <No room number specified>'}{f" • {bold(*l)} lunch" if l[0] else ' • <No lunch specified>'}\n'''
            return s
        string = f"Here you can quickly edit multiple attributes for a single class at once. Type messages following this pattern (editing multiple classes, with each edit on its own line is allowed) until the data is how you want it, then react ❌ to cancel without saving, or {emojis['greenCheck']} to save your changes:\n\n`P<periodNumber>: <class name> <teacher name> <room number> <lunch>`\n\n•To edit advisory, type 'Advisory' instead of P<number>, and any class name will be ignored\n•Follow this order exactly. To skip updating one of the attributes of a class, type a dash `-` in its place. To clear optional data for an attribute of a class, type `clear` in its place\n\nExample of me updating my government class, where I leave the class name alone but clear the teacher: `P9: - clear 104A C`\nYour schedule is below:\n\n\n{buildClassesString()}"
        oldPrompt = None
        if ctx.guild and statusMessage: 
            statusMessage = await ctx.channel.fetch_message(statusMessage.id)
            if [r.emoji for r in statusMessage.reactions] != reactions: await statusMessage.clear_reactions()
            await statusMessage.edit(content=string, embed=None)
        else: 
            oldPrompt = statusMessage
            statusMessage = await ctx.send(string)
        for r in reactions: await statusMessage.add_reaction(r)
        while True:
            d, p = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=reactionCheck)], return_when=asyncio.FIRST_COMPLETED)
            try: result = d.pop().result()
            except: result = None
            for f in p: f.cancel()
            if type(result) is discord.Message:
                if '\n' in result.content: rawData = result.content.replace('`', '').split('\n')
                else: rawData = [result.content.replace('`', '')]
                for line in rawData:
                    rawPeriod, className, teacherName, roomNumber, lunch = line.split(' ')
                    period = int(rawPeriod[1]) if 'advisory' not in rawPeriod.lower() else 2 #Index 1 of something like `P1:`
                    if '-' != className: schedule['classes'][period - 1] = className if period != 2 else 'Advisory' #This is required, so we don't check for clearing this value
                    if '-' != teacherName: schedule['teachers'][period - 1] = None if teacherName.lower() == 'clear' else teacherName
                    if '-' != roomNumber: schedule['rooms'][period - 1] = None if roomNumber.lower() == 'clear' else roomNumber
                    if '-' != lunch: schedule['lunches'][period - 1] = None if roomNumber.lower() == 'clear' else lunch if period != 2 else 'N/A'
                await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find('\n\n\n') + 3] + buildClassesString())
                if ctx.guild:
                    bot.get_cog('Cyberlog').AvoidDeletionLogging(r)
                    await result.delete()
            else:
                if result[0].emoji == emojis['greenCheck']:
                    await database.SetSchedule(ctx.author, schedule)
                elif result[0].emoji == '❌':
                    schedule = initialSchedule
                if ctx.guild: await statusMessage.clear_reactions()
                break
        try: await oldPrompt.delete()
        except: pass
        return statusMessage

    async def editMode():
        nonlocal statusMessage
        nonlocal schedule
        nonlocal initialSchedule
        nonlocal reactions
        nonlocal yellow
        try: await statusMessage.edit(content=f'{loading}Preparing settings...')
        except: statusMessage = await ctx.send(f'{loading}Preparing settings...')
        slide = {False: emojis['slideToggleOff'], True: emojis['slideToggleOn']}
        while True:
            def truncate(l, cutoff=4):
                return ', '.join([f'{entry[:cutoff]}…' if entry and len(entry) > cutoff else str(entry) for entry in l])
            reactions = [emojis['member'], emojis['details'], emojis['members'], emojis['greyCompass'], emojis['apple'], emojis['edit'], emojis['hiddenVoiceChannel'], emojis['bell'], emojis['newsChannel'], '❌', emojis['greenCheck']]
            embed = discord.Embed(title=f'Schedule Management: {ctx.author.name}', description=f"React with the emoji corresponding to a data field to edit that data, and react with {emojis['greenCheck']} when you're done to save your data or ❌ to cancel without saving.\n\n", color=yellow[1])
            embed.description += f"{'SCHEDULE SETTINGS':-^70}\n{emojis['member']}Last initial: {schedule['lastInitial']}\n{emojis['details']}Classes: [{truncate(schedule['classes'])}]\n{emojis['members']}Teachers: [{truncate(schedule['teachers'])}]\n{emojis['greyCompass']}Rooms: {truncate(schedule['rooms'], 5)}\n{emojis['apple']}Lunches: {truncate(schedule['lunches'])}\n\n{emojis['edit']}: Bulk edit multiple attributes for any class period at once\n\n"
            embed.description += f'''{'OTHER SETTINGS':-^70}\n{slide[schedule['guard']]}{emojis['hiddenVoiceChannel']}Enable confirmation prompt when viewing schedule outside of DMs\n{slide[schedule['announce']]}{emojis['bell']}DM announcements for special school closures like snow\n{emojis['slideToggleOn'] if schedule['daily'] else emojis['slideToggleOff']}{emojis['newsChannel']}Daily schedule delivery{f": {schedule['daily']:%I:%M %p}" if schedule['daily'] else ''}'''
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url_as(format='png', size=1024))
            await statusMessage.edit(content=f'{loading} Please wait for all reactions to be added...', embed=embed)
            for r in reactions: await statusMessage.add_reaction(r)
            await statusMessage.edit(content=None)
            oldMessage = None
            result = await bot.wait_for('reaction_add', check=reactionCheck)
            if result[0].emoji == emojis['member']: schedule['lastInitial'], oldMessage = await lastNameInput(True)
            elif result[0].emoji == emojis['details']: schedule['classes'], oldMessage = await classesInput(True)
            elif result[0].emoji == emojis['members']: schedule['teachers'], oldMessage = await teachersInput(True)
            elif result[0].emoji == emojis['greyCompass']: schedule['rooms'], oldMessage = await roomsInput(True)
            elif result[0].emoji == emojis['apple']: schedule['lunches'], oldMessage = await lunchInput(True)
            elif result[0].emoji == emojis['hiddenVoiceChannel']: schedule['guard'] = not schedule['guard']
            elif result[0].emoji == emojis['bell']: schedule['announce'] = not schedule['announce']
            elif result[0].emoji == emojis['newsChannel']:
                dailySetupEmbed = discord.Embed(title='Configure daily announcements', description=f'Type the time you would like to receive your daily schedule (`HH:MM AM/PM`)\n\nTyping a time after 2:50PM will have me send you the schedule for the next day at the time you specify\n\nFor optimization purposes, the delivery loop code only checks the time every 5 minutes\n\nYou can save or cancel changes on the previous page. Type `disable` to turn off this setting.', color=yellow[1])
                dailySetupEmbed.description += f'''\n\nCurrent value: {f"{schedule['daily']:%I:%M %p}" if schedule['daily'] else '<Disabled>'}'''
                reactions = [emojis['arrowLeft']]
                if ctx.guild:
                    await statusMessage.edit(embed=dailySetupEmbed)
                    await statusMessage.clear_reactions()
                else:
                    await statusMessage.delete()
                    statusMessage = await ctx.send(embed=dailySetupEmbed)
                for reaction in reactions: await statusMessage.add_reaction(reaction)
                while True:
                    d, p = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=reactionCheck)], return_when=asyncio.FIRST_COMPLETED)
                    try: result = d.pop().result()
                    except: pass
                    for f in p: f.cancel()
                    if type(result) is discord.Message:
                        try: 
                            if 'disable' in result.content: schedule['daily'] = False
                            else:
                                schedule['daily'] = datetime.datetime.strptime(result.content.upper(), '%I:%M %p')
                            d = dailySetupEmbed.description
                            d = d[:d.find('Current value:') + 15] + (f"{schedule['daily']:%I:%M %p}" if schedule['daily'] else '<Disabled>')
                            dailySetupEmbed.description = d
                            if ctx.guild:
                                bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                                await result.delete()
                            await statusMessage.edit(embed=dailySetupEmbed)
                        except ValueError:
                            await ctx.send(f'{emojis["alert"]}Invalid format, please use `HH:MM AM/PM`')
                            continue
                    else:
                        if not ctx.guild: await statusMessage.delete()
                        else: await statusMessage.clear_reactions()
                        break #Out of this double-waiting while loop
            elif result[0].emoji == emojis['edit']: #By far... the longest module
                oldMessage = await bulkEdit()
            elif result[0].emoji in ['❌', emojis['greenCheck']]:
                if result[0].emoji == '❌':
                    schedule = initialSchedule
                elif result[0].emoji == emojis['greenCheck']:
                    await statusMessage.edit(content=f'{loading}Saving...')
                    await database.SetSchedule(ctx.author, schedule)
                if not ctx.guild: await statusMessage.delete()
                else: await statusMessage.clear_reactions()
                break
            if not ctx.guild and result[0].emoji in reactions[:6] + [emojis['edit']]:
                try: await oldMessage.delete()
                except: pass
                await statusMessage.delete()
            elif ctx.guild:
                statusMessage = await ctx.channel.fetch_message(statusMessage.id)
                if reactions != [r.emoji for r in statusMessage.reactions]: await statusMessage.clear_reactions()
                else: await statusMessage.remove_reaction(*result)
        return await scheduleHandler()

    try:
        schedule = getUserData(bot)[ctx.author.id]['schedule']
        initialSchedule = copy.deepcopy(schedule)
        if desiredDate:
            if 'set' == desiredDate.lower(): raise KeyError
            elif 'edit' == desiredDate.lower(): wantsToEdit = True
        if type(schedule) is list: #User has not built their schedule after the update rework, so ask them what they would like to do
            choiceEmbed=discord.Embed(title='Schedule Module', description=f"Since this is your first time using the command since the rework and new features [(Patch notes here)]({'https://youtu.be/dQw4w9WgXcQ'}), please choose your desired option by reacting:\n\n{emojis['edit']}: Migrate old data (last name, core classes), walk through the new options (teacher names, room numbers, lunches, get schedule delivered daily, and other settings), then view your schedule\n{emojis['next']}: Migrate old data only, view your schedule now, and explore the new options later\n\n{'Note that if you choose the first option, Privacy Guard will not block your schedule from showing up in this server, due to code structure' if ctx.guild else ''}", color=yellow[1])
            statusMessage = await ctx.send(embed=choiceEmbed)
            reactions = [emojis['edit'], emojis['next']]
            for r in reactions: await statusMessage.add_reaction(r)
            result = await bot.wait_for('reaction_add', check=reactionCheck)
            statusMessage = await ctx.send(f'{loading}Migrating data...')
            oldSchedule = (await database.GetUser(ctx.author))['schedule']
            schedule = {'classes': [oldSchedule[0]] + ['Advisory'] + oldSchedule[1:-1], 'teachers': [], 'rooms': [], 'lunches': [], 'lastInitial': oldSchedule[-1], 'guard': True, 'announce': True, 'daily': False}
            for k in ('teachers', 'rooms', 'lunches'):
                for i in range(9): schedule[k].append('N/A' if i == 1 and k == 'lunches' else None)
            initialSchedule = copy.deepcopy(schedule)
            await database.SetSchedule(ctx.author, schedule)
            if result[0].emoji == emojis['next']: pass
            else: 
                if not ctx.guild: await statusMessage.delete()
                raise KeyError
    except KeyError:
        desiredDate = None
        if not schedule: schedule = getUserData(bot)[ctx.author.id].get('schedule')
        if type(schedule) is list or not schedule: 
            schedule = {'classes': [], 'teachers': [], 'rooms': [], 'lunches': [], 'lastInitial': '', 'guard': True, 'announce': True, 'daily': False}
            for k in ('teachers', 'rooms', 'lunches'):
                for i in range(9): schedule[k].append('N/A' if i == 1 and k == 'lunches' else None)
        memberRoleList = [m.roles for m in bot.get_all_members() if ctx.author.id == m.id]
        totalRoleList = []
        for roleList in memberRoleList: totalRoleList.extend(roleList)
        if not any([r.id in pRoles for r in totalRoleList]):
            locked = await ctx.send('🔒This is a private command, and you don\'t have a permitted role. If you believe this is a mistake, use this command in the presence of my developer and he can bypass this lock')
            def unlock(r, u): return str(r) == '🔓' and r.message.id == locked.id and u.id == 247412852925661185
            await bot.wait_for('reaction_add', check=unlock)
            await ctx.send('🔓My developer has unlocked this command for you')
        await lastNameInput() #Starts the editing cycle if a keyError is raised
    
    async def scheduleHandler():
        nonlocal desiredDate
        nonlocal initialPassedDate
        nonlocal statusMessage
        nonlocal reactions
        nonlocal schedule
        try: await statusMessage.edit(content=f'{loading}Building schedule...')
        except: statusMessage = await ctx.send(f'{loading}Building schedule...')
        withAdvisory = copy.deepcopy(schedule)
        embed, contentLog = await buildSchedule(desiredDate, initialPassedDate, ctx.author, ctx.message, schedule)
        await statusMessage.edit(content=contentLog[-1] if len(contentLog) > 0 else None, embed=embed)
        reactions = [emojis['settings']]
        for r in reactions: await statusMessage.add_reaction(r)
        await bot.wait_for('reaction_add', check=reactionCheck)
        if ctx.guild: await statusMessage.clear_reactions()
        else: await statusMessage.delete()
        schedule = withAdvisory
        return await editMode()

    #Main segment of the command; not inside of any methods        
    if ctx.guild:
        if schedule['guard']: 
            if statusMessage: await statusMessage.edit(content="🔒You're using this command publicly in a server. By 🔓unlocking your schedule, you're aware that others may view your schedule. Alternatively, react 🔒 and I'll DM you your schedule")
            else: statusMessage = await ctx.send("🔒You're using this command publicly in a server. By 🔓unlocking your schedule, you're aware that others may view your schedule. Alternatively, react 🔒 and I'll DM you your schedule")
            def lockedOut(r, u): return str(r) in ('🔓', '🔒') and r.message.id == statusMessage.id and u.id == ctx.author.id
            for r in ('🔓', '🔒'): await statusMessage.add_reaction(r)
            result = await bot.wait_for('reaction_add', check=lockedOut)
            if str(result[0]) == '🔒':
                if not ctx.author.dm_channel: await ctx.author.create_dm()
                ctx.channel = ctx.author.dm_channel
                statusMessage = None #to trigger the error, causing the bot to send a new message instead of trying to edit one
            else: await statusMessage.clear_reactions()
    if wantsToEdit: await editMode()
    else: await scheduleHandler()

async def buildSchedule(desiredDate, initialPassedDate, author, message, schedule):
    '''Returns an embed'''
    contentLog = []
    firstDay = datetime.date(2021, 1, 4) #First day of classes
    #firstLetter = 'T' If this is to be uncommented, do something complicated with rotating the schedule
    try: noClasses = getUserData(bot)[247412852925661185]['highSchoolDaysOffSpring2021'] #dict of days when there aren't classes - MM-DD-YYYY
    except: noClasses = {}
    try: dailyEvents = getUserData(bot)[247412852925661185]['highSchoolEventDaysSpring2021']
    except: dailyEvents = {}
    today = datetime.date.today()
    if initialPassedDate == '': initialPassedDate = desiredDate
    else: desiredDate = initialPassedDate
    date = today
    if not desiredDate:
        desiredDate = today
        if datetime.datetime.now() > datetime.datetime(today.year, today.month, today.day, 14, 50) and int(f'{today:%w}') not in (0, 5, 6):  #If it's later than 2:50PM and it's not a weekend, pull up tomorrow's schedule
            contentLog.append(f"{emojis['information']}It's after 2:50PM, so tomorrow's schedule will be displayed")
            date = today + datetime.timedelta(days=1)
    elif type(desiredDate) is str: 
        dt = Birthdays.calculateDate(message, datetime.datetime.now())
        if not dt:
            contentLog.append(f"{emojis['alert']} Unable to calculate a date from `{desiredDate}`; switching to today's schedule")
            date = today
            desiredDate = today
        else: 
            date = datetime.date(dt.year, dt.month, dt.day)
            desiredDate = date
    while int(f'{date:%w}') in (0, 6) or (int(f'{date:%w}') == 5 and datetime.datetime.now() > datetime.datetime(today.year, today.month, today.day, 14, 50)) or f'{date:%m-%d-%Y}' in noClasses.keys() or date < firstDay: #If it's not a weekend, there are classes today, or it's not the first day of classes yet
        dateAtStart = date
        date += datetime.timedelta(days=1) #If the provided date is a weekend day, or a day without classes, we jump ahead to the next available day
        if f'{dateAtStart:%m-%d-%Y}' in noClasses.keys():  contentLog.append(f"{emojis['information']}Classes are not in session during the date you provided ({desiredDate:%A, %B %d}) because {noClasses[f'{dateAtStart:%m-%d-%Y}']['reason']}. \n\nThe next date with classes ({date:%A, %B %d}) will be displayed") #Manually-defined days off
        elif dateAtStart < firstDay: contentLog.append(f"{emojis['information']}School hasn't started on the provided date ({desiredDate:%A, %B %d}), so the first day of class ({date:%A, %B %d}) will be displayed.")
        elif int(f'{dateAtStart:%w}') in (0, 6) or (int(f'{dateAtStart:%w}') == 5 and datetime.datetime.now() > datetime.datetime(today.year, today.month, today.day, 14, 50)): contentLog.append(f"{emojis['information']}It's the weekend, so the next date with classes ({date:%A, %B %d}) will be displayed.")
    lastInitial = schedule['lastInitial'] #Last initial of user
    #schedule = copy.deepcopy(schedule)
    #schedule.pop(-1) #Remove the last initial since it's not part of the schedule and was simply placed there for convenience
    #letters = 'PANTHERS'
    letters = 'THERSPAN'
    lettersFromStart = 'PANTHERS'
    onlineLetters = 'PAHE' if lastInitial.lower() > 'k' else 'NTRS'
    daySpan = []
    daysSince = (date - firstDay).days
    while daysSince > 0: #This is used to calculate the current letter day. First, just go through every day, backwards, from now to the start of the year/semester, adding every day
        if len(daySpan) == 0: daySpan.append(date - datetime.timedelta(days=1))
        else: daySpan.append(daySpan[-1] - datetime.timedelta(days=1))
        daysSince -= 1
    daySpan = [d for d in daySpan if int(f'{d:%w}') not in (0, 6) and f'{d:%m-%d-%Y}' not in noClasses.keys()] #get the days that are not weekend days or days without classes
    currentDayLetter = letters[len(daySpan) % len(letters)]
    online = currentDayLetter in onlineLetters
    if lettersFromStart.index(currentDayLetter) % 2 == 0: #Periods 1, 3, 4, 5
        start, stop = 0, 4
    else: #Periods 6, 7, 8, 9
        start, stop = 4, 8
    fullClassList = [{'class': schedule['classes'][i], 'teacher': schedule['teachers'][i], 'room': schedule['rooms'][i], 'lunch': schedule['lunches'][i]} for i in range(9)]
    for k in ['classes', 'teachers', 'rooms', 'lunches']:
        schedule[k].pop(1) #Remove advisory
    dailyClasses = [{'class': schedule['classes'][i], 'teacher': schedule['teachers'][i], 'room': schedule['rooms'][i], 'lunch': schedule['lunches'][i]} for i in range(start, stop)] #take either the first or last half of classes depending on letter day
    try: rotationFactor = lettersFromStart.index(currentDayLetter) // 2
    except ZeroDivisionError: rotationFactor = 0
    #A series of rotations to determine the proper schedule
    rotatedClasses = collections.deque(copy.deepcopy(dailyClasses))
    rotatedClasses.rotate(rotationFactor)
    rotatedClasses = list(rotatedClasses) #the four daily classes, rotated depending on the schedule
    rotatedClasses.insert(3, {'class': 'Advisory', 'teacher': fullClassList[1]['teacher'], 'room': fullClassList[1]['room']}) #Insert advisory back at the right spot
    #schedule.insert(1, 'Advisory')
    lunchIndexDict = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
    def time(s): return datetime.time(int(s[:s.find(':')]), int(s[s.find(':') + 1:])) #String to datetime.time
    def fTime(t): return f'{t:%I:%M %p}' #Format time in 10:00 AM format
    nowTime = datetime.datetime.now()
    dayDescription = f'{"Today" if date == today else "Tomorrow" if date == today + datetime.timedelta(days=1) else "Yesterday" if date == today - datetime.timedelta(days=1) else f"{date:%A}" if 1 < (date - today).days < 7 else f"{date:%A, %B %d}"}' #Embed header, based on if desired date is today, tomorrow, or another day
    eventsToday = dailyEvents.get(f'{date:%m-%d-%Y}', [])
    if len(eventsToday) > 0: 
        todaysEvents = '\n'.join([f'•{event}' for event in dailyEvents[f'{date:%m-%d-%Y}']])
        embedFlavor = f'''\n\n{f"{dayDescription.upper()}'S EVENTS":-^70}\n{todaysEvents}'''
    else: embedFlavor = ''
    liturgyDay = any(['liturgy' in e.lower() for e in eventsToday])
    if liturgyDay:
        times = [(time('7:45'), time('9:00')), (time('9:05'), time('10:10')), (time('10:20'), time('11:35')), (time('11:40'), time('13:35')), (time('13:40'), time('14:50'))] #The times classes start and end on liturgy days
        lunchTimes = [(time('11:40'), time('12:05')), (time('12:10'), time('12:35')), (time('12:40'), time('13:05')), (time('13:10'), time('13:35'))] #The times lunches start and end on liturgy days
    else:
        times = [(time('7:45'), time('9:20')), (time('9:25'), time('10:55')), (time('11:00'), time('12:55')), (time('13:00'), time('13:15')), (time('13:20'), time('14:50'))] #The times classes start and end
        lunchTimes = [(time('11:00'), time('11:25')), (time('11:30'), time('11:55')), (time('12:00'), time('12:25')), (time('12:30'), time('12:55'))] #The times lunches start and end on normal days
    dateTimes = [(datetime.datetime(date.year, date.month, date.day, t[0].hour, t[0].minute), datetime.datetime(date.year, date.month, date.day, t[1].hour, t[1].minute)) for t in times] #Times list, but datetime format for comparisons (of current real day, not current schedule day)
    dateLunchTimes = [(datetime.datetime(date.year, date.month, date.day, t[0].hour, t[0].minute), datetime.datetime(date.year, date.month, date.day, t[1].hour, t[1].minute)) for t in lunchTimes] #Times list, but datetime format for comparisons (of current real day, not current schedule day)
    embed = discord.Embed(title=f'{date:%B %d} - {currentDayLetter} day', color=yellow[1])
    embed.description=f'''{emojis["pc"] if online else emojis["members"]}{dayDescription if any([w in dayDescription for w in ("Today", "Tomorrow", "Yesterday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday")]) else f"On {f'{date:%A}' if (datetime.date(nowTime.year, nowTime.month, nowTime.day) - date).days > 0 else f'{date:%A, %B %d}'},"}  your classes are {"online" if online else "in person"}'''
    if liturgyDay:
        haveLink = False
        for e in eventsToday:
            if 'https://' in e:
                eventsToday.remove(e)
                haveLink = e
                break
        embed.description += f"\n**{emojis['cross']} Liturgy Schedule**"
        if haveLink: embed.description += f"\n{'⌛' if nowTime < datetime.datetime(nowTime.year, nowTime.month, nowTime.day, 9, 20) else '🔴' if datetime.datetime(nowTime.year, nowTime.month, nowTime.day, 9, 20) <= nowTime < datetime.datetime(nowTime.year, nowTime.month, nowTime.day, 11, 25) else emojis['camera']} {haveLink}"
    embed.description += f'''{embedFlavor}\n\n{f"{f'{dayDescription.upper()}'}'S SCHEDULE":-^70}'''
    for i, period in enumerate(rotatedClasses):
        compareTime = (datetime.datetime(date.year, date.month, date.day, times[i][0].hour, times[i][0].minute), datetime.datetime(date.year, date.month, date.day, times[i][1].hour, times[i][1].minute)) #Start and end of the current period
        def classStatus(): #Emoji if a class is complete or currently in progress, otherwise blank
            return emojis['greenCheck'] if nowTime > compareTime[1] else emojis['online'] if nowTime > compareTime[0] else ''
        def timeUntil(lunch=False):
            if lunch: 
                useTimes = dateLunchTimes
                index = lunchIndexDict[period['lunch']]
            else: 
                useTimes = dateTimes
                index = i
            if useTimes[index][0] > nowTime: #This class hasn't started yet
                display = Cyberlog.elapsedDuration(useTimes[index][0] - nowTime, False, onlyTimes=True)
                string = 'Begins'
            else: 
                display = Cyberlog.elapsedDuration(useTimes[index][1] - nowTime, False, onlyTimes=True)
                string = 'Ends'
            if display[0] > 0 or display[1] > 0: return f"{'> ' if not lunch else ''}{string} in {f'{display[0]}d' if display[0] > 0 else ''} {f'{display[1]}h' if display[1] > 0 else ''} {f'{display[2]}m' if display[2] > 0 else ''}" #Starts or ends in over an hour
            else: return f"{'> ' if not lunch else ''}{string} in {display[2]} minutes"
        def lunchFiller():
            lunchPeriod = period['lunch']
            lunchString = f"> {period['lunch']} Lunch: {lunchTimes[lunchIndexDict[period['lunch']]][0]:%I:%M} - {lunchTimes[lunchIndexDict[period['lunch']]][1]:%I:%M}"
            classString = f'''> {period['class']}{f" • {period['teacher']}" if period['teacher'] else ''}{f" • Rm {period['room']}" if period['room'] else ''}: <StartEndTime>'''
            if lunchPeriod == 'A':
                #ordering: between end of last class & end of A lunch, then between end of A lunch and end of D lunch
                string = f'''
                    {lunchString}{f" • {timeUntil(True)}" if dateTimes[2][1] < nowTime < dateLunchTimes[0][1] else ""}
                    {classString.replace('<StartEndTime>', f'{dateLunchTimes[1][0]:%I:%M} - {dateLunchTimes[3][1]:%I:%M}')}{f" • {timeUntil()}" if dateLunchTimes[0][1] < nowTime < dateLunchTimes[3][1] else ""}
                '''
            elif lunchPeriod == 'B':
                #ordering: between end of last class & end of A lunch, then between end of A lunch and end of B lunch, then between end of B lunch and end of D lunch
                string = f'''
                    {classString.replace('<StartEndTime>', f'{dateLunchTimes[0][0]:%I:%M} - {dateLunchTimes[0][1]:%I:%M}')}{f" • {timeUntil()}" if dateTimes[2][1] < nowTime < dateLunchTimes[0][1] else ""}
                    {lunchString}{f" • {timeUntil(True)}" if dateLunchTimes[0][1] < nowTime < dateLunchTimes[1][1] else ""}
                    {classString.replace('<StartEndTime>', f'{dateLunchTimes[2][0]:%I:%M} - {dateLunchTimes[3][1]:%I:%M}')}{f" • {timeUntil()}" if dateLunchTimes[1][1] < nowTime < dateLunchTimes[3][1] else ""}
                '''
            elif lunchPeriod == 'C':
                #ordering: between end of last class & end of B lunch, then between end of B lunch and end of C lunch, then between end of C lunch and end of D lunch
                string = f'''
                    {classString.replace('<StartEndTime>', f'{dateLunchTimes[0][0]:%I:%M} - {dateLunchTimes[1][1]:%I:%M}')}{f" • {timeUntil()}" if dateTimes[2][1] < nowTime < dateLunchTimes[1][1] else ""}
                    {lunchString}{f" • {timeUntil(True)}" if dateLunchTimes[1][1] < nowTime < dateLunchTimes[2][1] else ""}
                    {classString.replace('<StartEndTime>', f'{dateLunchTimes[3][0]:%I:%M} - {dateLunchTimes[3][1]:%I:%M}')}{f" • {timeUntil()}" if dateLunchTimes[2][1] < nowTime < dateLunchTimes[3][1] else ""}
                '''
            else: #D lunch
                #ordering: between end of last class & end of C lunch, then between end of C lunch and end of D lunch
                string = f'''
                    {classString.replace('<StartEndTime>', f'{dateLunchTimes[0][0]:%I:%M} - {dateLunchTimes[2][1]:%I:%M}')}{f" • {timeUntil()}" if dateTimes[2][1] < nowTime < dateLunchTimes[2][1] else ""}
                    {lunchString}{f" • {timeUntil(True)}" if dateLunchTimes[2][1] < nowTime < dateLunchTimes[3][1] else ""}
                '''
            return string
        value = f'''> {period['class']}{f" • {period['teacher']}" if period['teacher'] else ''}{f" • Rm {period['room']}" if period['room'] else ''}\n{timeUntil() if (nowTime < dateTimes[i][0] and i == 0) or (dateTimes[i][0] < nowTime < dateTimes[i][1] and i == 0) or (dateTimes[i - 1][1] < nowTime < dateTimes[i][1] and i != 0) else ''}''' if i != 2 else lunchFiller() if period['lunch'] else '<To see lunch schedule breakdown, configure a lunch for this class>'
        if liturgyDay: value += f'\n\nMass Group 1:\n> Mass: 9:20 - 10:10\n> Class: 10:20 - 11:35\n\nMass Group 2:\n> Class: 9:05 - 10:15\nMass: 10:30 - 11:25'
        embed.add_field(
            name=f'''{classStatus()}{"P" if i != 3 or liturgyDay else ""}{fullClassList.index(period) + 1 if period['class'] != "Advisory" else period['class']}{" & lunch" if i == 2 else "& Mass" if liturgyDay and i == 1 else f" • {fTime(times[i][0])} - {fTime(times[i][1])}"}''',
            value=value,
            inline=False)
    embed.set_author(name=author.name, icon_url=author.avatar_url_as(format='png', size=1024))
    return embed, contentLog

@commands.is_owner()
@bot.command()
async def scheduleManagement(ctx, mode='events'):
    snowBlue = 0x66ccff
    daysOff = getUserData(bot)[247412852925661185].get('highSchoolDaysOffSpring2021')
    if not daysOff: daysOff = {}
    emojis = bot.get_cog('Cyberlog').emojis
    def messageCheck(m): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
    def reactionCheck(r, u): return r.emoji in reactions and r.message.id == prompt.id and u.id == ctx.author.id
    def calculateDatePrompt(i):
        temp = copy.deepcopy(i)
        while temp.month == i.month:
            d = data.get(f"{temp:%m-%d-%Y}")
            off = daysOff.get(f"{temp:%m-%d-%Y}")
            if not d and not off and temp > datetime.date.today() and not int(f'{temp:%w}') in (0, 6) and f'{temp:%m-%d-%y}' not in skipped: return temp
            temp += datetime.timedelta(days=1)
        return temp

    if 'd' in mode:
        prompt = await ctx.send('Please enter the list of days off you wish to add to the system (MM/DD/YY)')
        m = await bot.wait_for('message', check=messageCheck)
        if ',' in m.content: split = m.content.split(', ')
        else: split = m.content.split('\n')
        for d in split:
            try: date = datetime.datetime.strptime(d, '%m/%d/%y')
            except:
                await ctx.send(f'Date parsing error for input `{d}`')
                continue
            prompt = await ctx.send(f'Enter the reason for there being no classes on {date:%b %d}')
            m = await bot.wait_for('message', check=messageCheck)
            prompt = await ctx.channel.fetch_message(prompt.id)
            data = {'reason': m.content, 'snowDay': len(prompt.reactions) > 0 and '❄️' in [r.emoji for r in prompt.reactions], 'announce': len(prompt.reactions) > 0 and ('❄️' in [r.emoji for r in prompt.reactions] or '🔔'in [r.emoji for r in prompt.reactions])}
            daysOff[f'{date:%m-%d-%Y}'] = data
            if data['announce']:
                await m.add_reaction(loading)
                for u in getUserData(bot).values():
                    try:
                        notifications = u['schedule']['announce']
                        if notifications:
                            embed=discord.Embed(title=f"{'❄️' if data['snowDay'] else ''}No school on {date:%B %d}", description=f"Reason: {data['reason']}\n\n(Reason for DM: {emojis['slideToggleOn']} DM notifications • PANTHERS schedule module)", color=snowBlue if data['snowDay'] else yellow[1])
                            try:
                                user = bot.get_user(u['user_id'])
                                await user.send(embed=embed)
                            except: pass
                    except (KeyError, TypeError): pass
                await m.remove_reaction(loading, bot.user)
            await m.add_reaction(emojis['greenCheck'])
        status = await ctx.send('Pushing to database...')
        await database.SetHSDaysOff(daysOff)
        await status.edit(content='Done!')
    elif 'e' in mode:
        prompt = await ctx.send(f'{loading} Building calendar...')
        data = getUserData(bot)[247412852925661185].get('highSchoolEventDaysSpring2021')
        if not data: data = {}
        t = datetime.date.today()
        i = datetime.date(t.year, t.month, 1)
        datePrompt = None
        skipped = []
        while True:
            embed = discord.Embed(title=f'HS Schedule - Events', description = f'{i:%B}\n\n', color = blue[1])
            temp = copy.deepcopy(i)
            datePrompt = calculateDatePrompt(i)
            while temp.month == i.month:
                d = data.get(f"{temp:%m-%d-%Y}")
                embed.description += f'{emojis["arrowForward"] if temp == datePrompt else "❌" if daysOff.get(f"{temp:%m-%d-%Y}") else qlf}{temp:%m/%d}: {"Weekend" if int(f"{temp:%w}") in (0, 6) else ", ".join([event[:50] + ("..." if len(event) > 50 else "") for event in d]) if d else "----"}\n'
                temp += datetime.timedelta(days=1)
            await prompt.edit(content = None, embed = embed)
            reactions = [emojis['previous'], emojis['next'], '❌', emojis['greenCheck']]
            for r in reactions: await prompt.add_reaction(r)
            d, p = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=reactionCheck)], return_when=asyncio.FIRST_COMPLETED)
            try: result = d.pop().result()
            except: result = None
            for f in p: f.cancel()
            if type(result) is discord.Message:
                if ':' in result.content[:5]: 
                    day = datetime.date(i.year, i.month, int(result.content[:result.content.find(':')]))
                    description = result.content[result.content.find(':') + 1:].split(', ')
                else:
                    day = datePrompt
                    description = result.content.split(', ')
                if 'skip' in description[0].lower(): skipped.append(f'{day:%m-%d-%y}')
                else:
                    events = data.get(f"{day:%m-%d-%Y}")
                    if not events: events = []
                    events += description
                    data[f"{day:%m-%d-%Y}"] = events
                if ctx.guild: 
                    bot.get_cog('Cyberlog').AvoidDeletionLogging(r)
                    await result.delete()
            else:
                if result[0].emoji in (emojis['previous'], emojis['next']):
                    n = result[0].emoji == emojis['next']
                    newMonth = i.month + (1 if n else -1)
                    newYear = i.year
                    if newMonth == 0:
                        newMonth = 12
                        newYear -= 1
                    elif newMonth == 13:
                        newMonth = 0
                        newYear += 1
                    i = datetime.date(newYear, newMonth, 1)
                    if ctx.guild: await prompt.remove_reaction(*result)
                elif result[0].emoji == emojis['greenCheck']:
                    break
                else:
                    return await prompt.edit(content=f'Cancelled', embed=None)
        await prompt.edit(content=f'{loading} Saving...')
        await database.SetHSEventDays(data)
        await prompt.edit(content=f'{emojis["greenCheck"]} Saved!')

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
    fileName = f'Attachments/Temp/MessageAttachments_{convertToFilename(user.name)}_{(datetime.datetime.utcnow() + datetime.timedelta(hours=getData(bot)[ctx.guild.id]["offset"] if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
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
async def scheduleAnnounce(ctx):
    status = await ctx.send(f'{loading}Working...')
    users = [u for u in getUserData(bot).values() if u.get('schedule')]
    for u in users:
        user = bot.get_user(u['user_id'])
        embed = discord.Embed(title='PANTHERS schedule module: Major update', color=0xffff66)
        embed.description = f'Hello {user.name}, since you have a PVI schedule saved in my database, this announcement is letting you know that my schedule feature got a major rework including new features and improvements. Some of the biggest features include adding teachers, room numbers, and lunch periods to your classes, and an option to have your schedule delivered to you each school day.\n\n[View the update patch notes here](https://pastebin.com/URySgHaM)\n\nUse the `.schedule` command to check out the new features.\n\nP.S. If you know anyone who would be interested in the schedule feature, please spread the word - I enjoy putting work into fun features to serve my friends.'
        try: await user.send(embed=embed)
        except: pass
    await status.edit(content=f'Done!')

@commands.is_owner()
@bot.command()
async def test(ctx):
    status = await ctx.send('Working')
    
    for u in bot.lightningUsers.values():
        if u.get('age') and (u['age'] < 13 or u['age'] > 110):
            user = bot.get_user(u['user_id'])
            await database.SetAge(user, None)
            message = f"Hello {user.name}, this message is to inform you that it's no longer possible to store age values for my birthday module smaller than 13 or larger than 110. Your currently stored age, {u['age']}, falls outside of this range and has been reset. The birthday module only works in servers, so head to a server to update your age if you wish, otherwise it'll stay stored as null.\n\n(You are receiving this message because you have an age value for my birthday module outside of the new acceptable range, and it has been reset)"
            try: await user.send(message)
            except: pass

    await status.edit(content='Done')

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
