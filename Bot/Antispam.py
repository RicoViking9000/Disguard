import discord
from discord.ext import commands, tasks
import database
import datetime
import profanityfilter
import emoji
import Cyberlog
import asyncio
import traceback
import copy
import collections
import utility
import lightningdb

filters = {}
members = {} #serverID_memberID: member

green = (0x008000, 0x66ff66)
blue = (0x0000FF, 0x6666ff)
red = (0xff0000, 0xff6666)
orange = (0xD2691E, 0xffc966)
yellow = (0xffff00, 0xffff66)
purple = (0xFF00FF, 0xff66ff)


class ParodyMessage(object):
    def __init__(self, content, created):
        self.content = content
        self.created = created


class Antispam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')
        self.emojis = self.bot.get_cog('Cyberlog').emojis
        self.antispamProcessTimes = [] #stores 5,000 antispam events received in on_message for data evaluation/statistical purposes
        self.fullAntispamProcessTimes = [] #stores 100 antispam events - full effect (meaning only actions with consequences, be it warnings, bans, mutes, etc)
        self.checkTimedEvents.start()

    @tasks.loop(minutes=15)
    async def checkTimedEvents(self):
        if self.checkTimedEvents.current_loop == 0: await asyncio.sleep(300)
        try:
            for g in self.bot.guilds:
                events = (await utility.get_server(g)).get('antispam').get('timedEvents')
                for e in events:
                    if datetime.datetime.utcnow() > e.get('expires'):
                        try:
                            if e.get('type') == 'ban':
                                try: await g.unban(await self.bot.fetch_user(e.get('target')), reason=f'{e.get("flavor")} Ban duration expired')
                                except discord.Forbidden as error: print(f'Timed ban error: {error.text}')
                            elif e.get('type') == 'mute':
                                member = g.get_member(e.get('target'))
                                if member:
                                    try: 
                                        await member.remove_roles(g.get_role(e.get('role')))
                                        await member.add_roles(*[g.get_role(r) for r in e.get('roleList')])
                                        for k, v in e.get('permissionsTaken').items(): await g.get_channel(int(k)).set_permissions(member, overwrite=discord.PermissionOverwrite.from_pair(discord.Permissions(v[0]), discord.Permissions(v[1])))
                                    except discord.Forbidden as error: 
                                        try: await self.bot.get_channel((await utility.get_server(g))['cyberlog']['defaultChannel']).send(f'Unable to unmute {member} because {error.text}')
                                        except: pass
                                        print(f'Timed mute error: {error.text}')
                                else: await database.RemoveTimedEvent(g, e)
                            elif e.get('type') == 'pause':
                                g = self.bot.get_guild(e['server'])
                                await database.ResumeMod(g, e['key'])
                        except discord.NotFound: await database.RemoveTimedEvent(g, e)
                        await database.RemoveTimedEvent(g, e)
        except: traceback.print_exc()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        '''[DISCORD API METHOD] Called when message is sent'''
        if message.author.bot or type(message.channel) is not discord.TextChannel: #Return if a bot sent the message or it's a DM
            return
        server = await utility.get_server(message.guild)
        try: spam = server.get('antispam')
        except AttributeError: return
        if not spam or not (spam.get('enabled') or spam.get('attachments')[-1]): return #return if antispam isn't enabled
        self.bot.loop.create_task(self.filterAntispam(message, spam))


    async def filterAntispam(self, message: discord.Message, spam):
        received = datetime.datetime.now()
        try:
            for person in (await utility.get_server(message.guild))['members']:
                if person['id'] == message.author.id: break #we found our current member
        except: return
        #dont store quick/last messages in the database - they'll be local only... just figure out how to do this without looping through all the members each time to find the person
        if not person: return
        warningsAtStart = person['warnings']

        '''IMPLEMENT QUICKMESSAGE/LASTMESSAGE MESSAGE ARRAYS'''
        #The following lines of code deal with a member's lastMessages and quickMessages:
        #Sending eqivalent messages/sending too many messages too quickly, respectively
        #Probably the least fun part of antispam to code due to constant updating and reading, but it beats storing locally,
        #Partially due to readibility(I can view things online) and reliability
        '''Adding newly sent messages to DB'''
        '''Removal if messages are too old'''

        '''FEB 29: I realize the previous code dealt with *every server member* during every message...  yeah, that won't fly anymore, and never should have. Bot will be a *lot* faster and more responsive now :)'''
        reason = [] #List of reasons (long version) that a member was flagged for
        short = [] #list of reasons (short version) that a member was flagged for
        flag = False
        if any(spam.get('attachments')[:-1]) and len(message.attachments) > 0: #Check for attachments
            #[All attachments, media attachments, non-common attachments, pics, audio, video, static pictures, gifs, tie with flagging system]
            #File extensions from https://www.computerhope.com/issues/ch001789.htm
            t = spam.get('attachments')
            descriptions = ['All attachments', 'Media attachments', 'Uncommon attachments', 'Images', 'Audio attachments', 'Video attachments', 'Static images', 'Gif images']
            aFlag = ''
            for a in message.attachments:
                if t[0]: aFlag = 'Attachment'
                ext = a.filename[a.filename.rfind('.') + 1:].lower()
                audioExt = ['mp3', 'ogg', 'wav', 'flac']
                videoExt = ['mp4', 'webm', 'mov']
                staticExt = ['jpeg', 'jpg', 'png', 'webp']
                #Start with most general category and end with most specific
                if t[1] and ext in audioExt + videoExt + staticExt + ['gif']: aFlag = 'Media attachment'
                if t[3] and (ext in staticExt or ext == 'gif'): aFlag = 'Image attachment'
                if t[7] and ext == 'gif': aFlag = 'Animated image attachment' #gif filtering
                if t[6] and ext in staticExt: aFlag = 'Static image attachment' #static image filtering
                if t[5] and ext in videoExt: aFlag = 'Video attachment' #video file filtering
                if t[4] and ext in audioExt: aFlag = 'Audio attachment'
                if t[2] and ext not in audioExt + videoExt + staticExt + ['gif', 'txt']: aFlag = 'Uncommon attachment'
            if aFlag:
                if t[-1]:
                    flag = True
                    reason.append(f'Sending a .{ext} attachment ({aFlag})\n\nServer antispam policy blocks the following attachment types: {", ".join([descriptions[d] for d in range(len(t[:-1])) if t[d]])}')
                    short.append(f'Sending a {aFlag} attachment')
                else:
                    p = message.author.guild_permissions
                    if not p.administrator or p.manage_guild or message.author.id == message.guild.owner.id:
                        await message.channel.trigger_typing()
                        if await Cyberlog.logEnabled(message.guild, 'message') and (await utility.get_server(message.guild)).get('cyberlog').get('image'): await asyncio.sleep(2) #Wait two seconds if image logging is enabled
                        try: await message.delete()
                        except discord.Forbidden: pass
                        return await message.channel.send(embed=discord.Embed(description=f'Please avoid sending `{aFlag}`s in this server', color=await utility.color_theme(message.guild)), delete_after=15)
        if not (any([spam.get('attachments')[:-1], spam.get('enabled')])): return
        cRE = await CheckRoleExclusions(message.author)
        if spam.get('exclusionMode') == 0:
            if not (message.channel.id in spam.get('channelExclusions') and cRE or message.author.id in spam.get('memberExclusions')): return
        else:
            if message.channel.id in spam.get('channelExclusions') or message.author.id in spam.get('memberExclusions') or cRE: return
        try: lastMessages = person.get("lastMessages", [])
        except AttributeError: lastMessages = []
        try: quickMessages = person.get("quickMessages", [])
        except AttributeError: quickMessages = []
        if message.content is not None and len(message.content) > 0: lastMessages.append(vars(ParodyMessage(message.content, message.created_at))) #Adds a ParodyMessage object (simplified discord.Message; two variables)
        if message.channel.id not in await GetChannelExclusions(message.guild) and not cRE and message.author.id not in await GetMemberExclusions(message.guild):
            quickMessages.append(vars(ParodyMessage(message.content, message.created_at)))
            for msg in lastMessages:
                try:
                    if datetime.datetime.utcnow() - msg.get("created") > datetime.timedelta(seconds=spam.get("congruent")[2]):
                        lastMessages.remove(msg)
                    if len(lastMessages) > spam.get("congruent")[1]:
                        lastMessages.pop(0)
                except: 
                    lastMessages = []
                    print('Resetting lastmessages for {}, {}'.format(message.author.name, message.guild.name))
            for msg in quickMessages:
                try:
                    if datetime.datetime.utcnow() - msg.get("created") > datetime.timedelta(seconds=spam.get("quickMessages")[1]):
                        quickMessages.remove(msg)
                    if len(quickMessages) > spam.get("quickMessages")[0]:
                        quickMessages.pop(0)
                except:
                    quickMessages = []
                    print('Resetting quickmessages for {}, {}'.format(message.author.name, message.guild.name))
            person.update({'lastMessages': lastMessages, 'quickMessages': quickMessages})
        if spam.get('ignoreRoled') and len(message.author.roles) > 1:
            return #Return if we're ignoring members with roles and they have a role that's not the @everyone role that everyone has (which is why we can tag @everyone)
        if spam.get("congruent")[0] != 0: 
            #Checking for lastMessages and quickMessages
            try:
                lastMessages = person.get("lastMessages")
                if spam.get("congruent")[0] != 0:
                    counter = collections.Counter(msg['content'] for msg in lastMessages)
                    most = counter.most_common(1)[0]
                    if most[1] >= spam['congruent'][0]:
                        flag = True
                        reason.append(f'Duplicated messages: Member sent `{most[0]}` {most[1]} times\n\n(Server flag threshold: {spam["congruent"][0]} duplicates over {spam["congruent"][1]} most recent messages)')
                        short.append(f'Duplicated messages (`{most[0]}`)')
                        person['lastMessages'] = []
            except IndexError: pass
        if 0 not in spam.get("quickMessages") and len(quickMessages) > 0:
            quickMessages = person.get("quickMessages")
            timeOne = quickMessages[0].get("created")
            timeLast = quickMessages[-1].get("created")
            if (timeLast - timeOne).seconds < spam.get("quickMessages")[1] and len(quickMessages) >= spam.get("quickMessages")[0]:
                flag = True
                reason.append("Sending too many messages too quickly\n" + str(message.author) + " sent " + str(len(quickMessages)) + " messages in " + str((timeLast - timeOne).seconds) + " seconds")
                short.append("Sending messages too fast")
                person['quickMessages'] = []
        if spam.get('consecutiveMessages')[0] != 0:
            messages = await message.channel.history(limit=spam.get('consecutiveMessages')[0]).flatten()
            if len(messages) >= spam.get('consecutiveMessages')[0] and all([m.author.id == message.author.id for m in messages]) and (messages[0].created_at - messages[-1].created_at).seconds < spam.get('consecutiveMessages')[1]:
                flag = True
                reason.append(f'Sending too many messages in a row\n\n{message.author.name} sent {len(messages)} messages consecutively in under {(messages[0].created_at - messages[-1].created_at).seconds} seconds (Server flag threshold: {spam.get("consecutiveMessages")[0]} messages over {spam.get("consecutiveMessages")[1]} seconds)')
                short.append('Sending too many consecutive messages')
        if spam.get("emoji") != 0:
            #Work on emoji so more features are available
            changes = 0
            spaces = 0
            parsed = ""
            for a in message.content:
                if a == " ":
                    spaces += 1
                if emoji.demojize(a) != a:
                    changes += 1
                    parsed += "**<" + a + ">**"
                else:
                    parsed += a
            if changes >= spam.get("emoji"):
                flag = True
                reason.append("Too many emoji: " + parsed + "\n\n(" + str(changes) + " emoji detected; " + str(spam.get("emoji")) + " tolerated)")
                short.append("Too many emoji")
        if spam.get("mentions") != 0:
            if len(message.mentions) >= spam.get("mentions"):
                flag = True
                reason.append("Tagging too many members: " + message.content + "\n\n(" + str(len(message.mentions)) + " mentions; " + str(spam.get("mentions")) + " tolerated)")
                short.append("Tagging too many members")
        if spam.get("roleTags") != 0:
            if len(message.role_mentions) >= spam.get('roleTags'):
                flag = True
                reason.append("Tagging too many roles: " + message.content + "\n\n(" + str(len(message.role_mentions)) + " mentions; " + str(spam.get("roleTags")) + " tolerated)")
                short.append("Tagging too many roles")
        if spam.get("selfbot"):
            if not message.author.bot and len(message.embeds) > 0 and "http" not in message.content:
                flag = True
                reason.append("Appearing to selfbot: Sending an embed")
                short.append("Selfbotting (embed)")
            for word in message.content.lower().split(' '):
                if word.endswith('ms') and all([letter in '1234567890' for letter in word[:word.find('ms')]]):
                    if any(w.startswith('ping') for w in message.content.lower().split(' ')):
                        flag = True
                        reason.append("Appearing to selfbot: Latency ping message")
                        short.append("Selfbotting (ping message)")
                        break
        if int(spam.get("caps")) != 0:
            changes = 0
            spaces = 0
            for a in message.content:
                if a == " ":
                    spaces += 1
            parsed = ""
            for a in range(len(message.content)):
                if message.content[a].lower() != message.content[a]:
                    changes += 1
                    if a > 0:
                        if message.content[a - 1].lower() != message.content[a-1]:
                            parsed += message.content[a]
                        else:
                            parsed += "**" + message.content[a]
                    else:
                        parsed += "**" + message.content[a]
                else:
                    if a > 0:
                        if message.content[a-1].lower() != message.content[a-1]:
                            parsed += "**" + message.content[a]
                        else:
                            parsed += message.content[a]
                    else:
                        parsed += message.content[a]
            asteriskCount = 0
            for a in parsed:
                if a == "*":
                    asteriskCount += 1
            if asteriskCount % 4 != 0:
                parsed += "**"
            if len(message.content) > 0:
                if changes / (len(message.content) - spaces) >= spam.get("caps") / 100.0:
                    flag = True
                    reason.append("Too many capital letters: " + parsed + "\n\n(" + str(round(changes / (len(message.content) - spaces) * 100)) + "% capital letters detected; " + str(spam.get("caps")) + "% tolerated)")
                    short.append("Too many caps")
        if not spam.get("links"):
            if "http" in message.content and "://" in message.content:
                flag = True
                reason.append("Sending a web URL link: " + message.content)
                short.append("Sending a URL")
        if not spam.get("invites"):
            if "discord.gg/" in message.content:
                flag = True
                reason.append("Sending a Discord invite link: " + message.content)
                short.append("Sending a Discord invite link")
        if spam.get("everyoneTags") != 0 or spam.get("hereTags") != 0:
            everyone = 0
            here = 0
            parsed = ""
            lst = message.content.split(" ")
            for a in lst:
                if "@everyone" in a and not message.mention_everyone and spam.get("everyoneTags") != 0:
                    everyone += 1
                    parsed += "**" + a + "** "
                elif "@here" in a and not message.mention_everyone and spam.get("hereTags") != 0:
                    here += 1
                    parsed += "**" + a + "** "
                else:
                    parsed += a + " "
            if everyone >= spam.get("everyoneTags") and spam.get("everyoneTags") != 0:
                flag = True
                reason.append("Attempting to tag `@everyone` without permission to\n\n" + parsed)
                short.append("Attempting to tag `everyone`")
            if here >= spam.get("hereTags") and spam.get("hereTags") != 0:
                flag = True
                reason.append("Attempting to tag `@here` without permission to\n\n" + parsed)
                short.append("Attempting to tag `here`")
        if spam.get("profanityEnabled"):
            try:
                if len(message.content) > 0:
                    parsed = ""
                    spaces = 0
                    for a in message.content:
                        if a == " ":
                            spaces += 1
                    currentFilter = profanityfilter.ProfanityFilter()
                    currentFilter._censor_list = spam.get('filter')
                    filtered = currentFilter.censor(message.content.lower())
                    arr = message.content.lower().split(" ")
                    prof = filtered.split(" ")
                    for a in range(len(arr)):
                        if arr[a] != prof[a]:
                            parsed += "**" + arr[a] + "** "
                        else:
                            parsed += arr[a] + " "
                    if filtered != message.content.lower():
                        censorCount = 0
                        for a in filtered:
                            if a == "*":
                                censorCount += 1
                        if censorCount / (len(filtered) - spaces) >= spam.get('profanityTolerance'):
                            flag = True
                            reason.append("Profanity: " + parsed + "\n\nMessage is " + str(round(censorCount / (len(filtered) - spaces) * 100)) + "% profanity; " + str(spam.get('profanityTolerance') * 100) + "% tolerated")
                            short.append("Profanity")
            except TypeError: pass
        if not flag:
            if len(self.antispamProcessTimes) > 5000: self.antispamProcessTimes.pop(0)
            self.antispamProcessTimes.append((datetime.datetime.now() - received).seconds)
            return
        await message.channel.trigger_typing()
        if spam.get("delete"):
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(message)
                await message.delete()
            except discord.Forbidden as e:
                await message.channel.send(f"Unable to delete flagged message by {message.author.name} because {e.text}.")
        successful = False #Was a member's consequence carried out successfully?
        desc = [] #List of error messages, if applicable
        warned = False #Was a member warned?
        roled = False #Did member receive a role upon their consequence?
        role = None #The role to use if applicable
        if person.get("warnings") >= 1:
            try:
                person['warnings'] -= 1
                successful = True
                warned = True
            except:
                desc.append("Unable to warn member")
        else:
            if spam.get("action") in [1, 4]:
                if spam['action'] == 4: role = message.guild.get_role(spam.get('customRole', 0))
                successful = await self.bot.get_cog('Moderation').muteMembers([message.author], message.guild.me, duration=spam.get('muteTime', 0), reason='[Antispam: Automute]', waitToUnmute=False, muteRole=role)
            if spam.get("action") == 2:
                try:
                    await message.guild.kick(message.author)
                    successful = True
                except discord.Forbidden:
                    desc.append("Unable to kick member")
            if spam.get("action") == 3:
                try:
                    await message.guild.ban(message.author)
                    successful = True
                except discord.Forbidden:
                    desc.append("Unable to ban member")
            if spam.get("action") == 0:
                successful = True
        theme = await utility.color_theme(message.guild)
        shorter=discord.Embed(title=message.author.name+" got busted",description="Hey " + message.author.mention + ", looks like you got flagged for spam for **" + str(len(short)) + "** reason(s). The reason(s) is/are below, but to see these reasons in detail, please contact a moderator of " + message.guild.name + ".\n\n",timestamp=datetime.datetime.utcnow(),color=orange[theme])
        for a in short:
            shorter.description += "• " + a + "\n"
        if person.get("warnings") >= 0 and warned:
            shorter.add_field(name="Your consequence",value="Warning (" + str(person.get("warnings")) + " left)")
        else:
            if spam.get("action") == 0:
                shorter.add_field(name="Your consequence",value="Nothing :)")
            if spam.get("action") == 1:
                shorter.add_field(name="Your consequence",value="AutoMute for " + str(spam.get("muteTime")) + " seconds")
            if spam.get("action") == 2:
                shorter.add_field(name="Your consequence",value="Kicked :(")
            if spam.get("action") == 3:
                shorter.add_field(name="Your consequence",value="Banned :(")
            if spam.get("action") == 4:
                shorter.add_field(name="Your consequence",value=message.guild.get_role(spam.get("customRole")).name + " role for " + str(spam.get("muteTime")) + " seconds")
        whispered = 0 #Status for if bot is able to DM a member, if applicable
        if spam.get("whisper") or not message.channel.permissions_for(message.author).read_messages:
            if not message.channel.permissions_for(message.author).read_messages: flavorText = f'The automute has temporarily prevented you from accessing the channel {message.channel.name}, so you would not have known you were muted otherwise. You will receive a DM update when your mute time is up.'
            else: flavorText = f'{message.guild.name} has set their antispam notice to DM members upon being flagged.'
            try:
                directShorter = copy.deepcopy(shorter)
                directShorter.description += f'\n\n*You are receiving this DM because {flavorText}*'
                await message.author.send(embed=directShorter)
                whispered = 2
            except discord.Forbidden:
                whispered = 1
        if not spam.get("whisper") or whispered != 2:
            await message.channel.send(embed=shorter)
        if person.get('warnings') != warningsAtStart: asyncio.create_task(database.UpdateMemberWarnings(message.guild, message.author, warningsAtStart - 1))
        if None not in spam.get("log"):
            longer = discord.Embed(title=message.author.name + " was flagged for spam",description=message.author.mention + " was flagged for **" + str(len(short)) + " reasons**, details below",timestamp=datetime.datetime.utcnow(),color=orange[theme])
            for a in range(len(reason)):
                longer.add_field(name="Reason " + str(a + 1),value=reason[a],inline=False)
            if warned:
                longer.add_field(name="Member's consequence",value="Warning (" + str(person.get("warnings")) + " / " + str(spam.get("warn")) + " left)")
            else:
                if spam.get("action") == 0:
                    longer.add_field(name="Member's consequence",value="Nothing :)")
                if spam.get("action") == 1:
                    longer.add_field(name="Member's consequence",value="AutoMute for " + str(spam.get("muteTime")) + " seconds")
                if spam.get("action") == 2:
                    longer.add_field(name="Member's consequence",value="Kicked :(")
                if spam.get("action") == 3:
                    longer.add_field(name="Member's consequence",value="Banned :(")
                if spam.get("action") == 4:
                    longer.add_field(name="Member's consequence",value=message.guild.get_role(spam.get("customRole")).name + " role for " + str(spam.get("muteTime")) + " seconds")
            if successful:
                longer.add_field(name="Consequence carried out successfully?",value=successful)
            else:
                longer.add_field(name="Consequence carried out successfully",value="False - see details below")
                if len(desc) > 0:
                    longer.add_field(name="Failure details",value="\n• ".join(desc))
            if whispered == 1:
                longer.set_footer(text="Also, I was unable to DM this user")
            await message.guild.get_channel(spam.get("log")[1]).send(embed=longer)
        if len(self.fullAntispamProcessTimes) > 100: self.fullAntispamProcessTimes.pop(0)
        self.fullAntispamProcessTimes.append((datetime.datetime.now() - received).seconds)
        if not roled:
            return
        await asyncio.sleep(spam.get("muteTime"))
        if not message.channel.permissions_for(message.author).read_messages:
            try: await message.author.send(f'You are now unmuted in {message.guild.name}')
            except discord.Forbidden: pass
        try:
            await self.bot.get_cog('Moderation').unmuteMembers([message.author], message.guild.me, {})
            lcEmbed = discord.Embed(title="Mute time is up for " + message.author.name,description="Successfully removed role **" + role.name + "** from __" + message.author.mention + "__",timestamp=datetime.datetime.utcnow(),color=orange[theme])
        except discord.Forbidden:
            lcEmbed = discord.Embed(title="Mute time is up for " + message.author.name,description="Unable to remove role **" + role.name + "** from __" + message.author.mention + "__",timestamp=datetime.datetime.utcnow(),color=orange[theme])
        if spam.get("log"):
            try:
                await message.guild.get_channel(spam.get("log")[1]).send(embed=lcEmbed)
            except discord.Forbidden:
                pass
    
    @commands.command()
    async def ageKick(self, ctx, *args):
        await ctx.trigger_typing()
        newline = '\n'
        if not await utility.ManageServer(ctx.author): return await ctx.send('You need manage server, administrator, or server owner permissions to use this')
        config = (await utility.get_server(ctx.guild)).get('antispam')
        wl = config.get('ageKickWhitelist')
        theme = await utility.color_theme(ctx.guild)
        if len(args) == 0:
            e=discord.Embed(title=f'Age Kick Information: {ctx.guild.name}', description=f'''**{"WHITELIST ENTRIES":–^70}**\n{newline.join([f'•{(await self.bot.fetch_user(w)).name} ({w})' for w in wl]) if wl is not None and len(wl) > 0 else '(Whitelist is empty)'}\n**{"RECIPIENT DM MESSAGE":–^70}**\n{config.get("ageKickDM")}''', color=yellow[theme], timestamp=datetime.datetime.utcnow())
            e.add_field(name='Kick Accounts',value=f'Under {config.get("ageKick")} days old')
            e.add_field(name=f'Manageable by {self.emojis["owner"]}{ctx.guild.owner.name} only',value=config.get('ageKickOwner'))
            await ctx.send(embed=e)
        else:
            if config.get('ageKickOwner') and ctx.author.id != ctx.guild.owner.id: return await ctx.send(f'Only the owner of this server ({ctx.guild.owner.name}) can edit the ageKick configuration.')
            arg = args[0]
            e = discord.Embed(title='Age Kick Configuration',description='{} Saving...'.format(self.loading),color=yellow[theme], timestamp=datetime.datetime.utcnow())
            m = await ctx.send(embed=e)
            if len(args) == 1:
                try: 
                    arg = int(arg)
                    if arg > 1000:
                        try: user = await self.bot.fetch_user(arg)
                        except discord.NotFound: return await m.edit(content=f'I was unable to find a valid user matching the ID of `{arg}`.')
                        if user.id not in wl:
                            await database.AppendWhitelistEntry(ctx.guild, user.id)
                            e.description=f'**Successful addition to ageKick whitelist**\nName: {user.name}\nID: {user.id}\n\nTo remove this user from the whitelist, use the agekick command with their ID again. They will be automatically removed when they join this server.'
                        else:
                            await database.RemoveWhitelistEntry(ctx.guild, user.id)
                            e.description=f'Successfully removed {user.name} ({user.id}) from the ageKick whitelist.'
                    else:
                        await database.SetAgeKick(ctx.guild, arg)
                        e.description=f'Successfully updated ageKick configuration from kicking accounts under {config.get("ageKick")} days old to kicking accounts **under {arg} days old.**'
                except ValueError:
                    if 'clear' == arg.lower():
                        await database.ResetWhitelist(ctx.guild)
                        e.description=f'Successfully cleared the agekick whitelist for {ctx.guild.name}. {len(wl)} entries were removed.'
                    elif 'owner' == arg.lower():
                        if ctx.author.id != ctx.guild.owner.id: return await m.edit(content='You need to be the server owner in order to edit this', embed=None)
                        ownerStatus = config.get('ageKickOwner')
                        if not ownerStatus: e.description=f'Successfully updated server ageKick configuration: Now, **only the server owner ({ctx.guild.owner.name})** can edit the ageKick configuration for this server. Type this command again to allow any manager to edit the ageKick configuration.'
                        else: e.description='Successfully updated server ageKick configuration: Now, **any manager** (person with `manager server` or higher) can edit the ageKick configuration for this server. Type this command again to restrict ageKick editability to yourself only.'
                        await database.SetAgeKickOwner(ctx.guild, not ownerStatus)
                    else: return await m.edit(content=f'No actions found for `{arg}`. Acceptable single-word arguments are `owner` to toggle owner-only editability or `clear` to clear the whitelist. To view the ageKick configuration for this server, simpy type `agekick` with no arguments.', embed=None)
            else:
                arg = ' '.join(args)
                e.set_author(name='Please wait....')
                e.description=('Because of the flexibility with customizing the custom DM message, my developer must approve of this message to make sure there are no security flaws. This message will be updated when that happens. My developer will not know any identifying information; all that will be sent is the following text:\n\n{}').format(arg)
                await m.edit(embed=e)
                mm = await self.bot.get_channel(681949259192336406).send(embed=discord.Embed(title='Approve or Deny',description=arg))
                for r in ['✅', '❌']: await mm.add_reaction(r)
                def ownerCheck(r, u): return str(r) in ['✅', '❌'] and u.id == 247412852925661185 and r.message.id == mm.id 
                r = await self.bot.wait_for('reaction_add', check=ownerCheck)
                if str(r[0]) == '✅':
                    await database.SetAgeKickDM(ctx.guild,arg)
                    e.description='My developer has approved your request\n\nUpdated DM members receive upon being kicked to say `{}`'.format(arg)
                    r[0].message.embeds[0].description+='\n\n**Successful approval'
                    await r[0].message.edit(embed=r[0].message.embeds[0])
                else: e.description='My developer has denied your request on the grounds of security, please try another custom message or join [my support server](https://discord.gg/xSGujjz) for assistance.'
            e.set_author(name='Success')
            e.set_footer(text=f'React {self.emojis["reload"]} to view ageKick configuration')
            await m.edit(embed=e)
            await m.add_reaction(self.emojis['reload'])
            # await Cyberlog.updateServer(ctx.guild)
            config = (await utility.get_server(ctx.guild)).get('antispam')
            wl = config.get('ageKickWhitelist')
            def configCheck(r, u): return r.emoji == self.emojis['reload'] and r.message.id == m.id and u.id == ctx.author.id
            await self.bot.wait_for('reaction_add', check=configCheck)
            await m.clear_reactions()
            return await m.edit(embed=discord.Embed(title=f'Age Kick Information: {ctx.guild.name}', description=f'''**{"WHITELISTED USERS":–^70}**\n{newline.join([f'•{(await self.bot.fetch_user(w)).name} ({w})' for w in wl]) if wl is not None and len(wl) > 0 else '(Whitelist is empty)'}\n**{"RECIPIENT DM MESSAGE":–^70}**\n{config.get('ageKickDM')}''', color=yellow[theme], timestamp=datetime.datetime.utcnow()))
        
    @commands.is_owner()
    @commands.command()
    async def setWarnings(self, ctx, members: commands.Greedy[discord.Member], setTo: int = 0):
        embed=discord.Embed(title='Set Member Warnings', description=f'{self.loading}Updating member data...', color=yellow[await utility.color_theme(ctx.guild)])
        if len(members) == 0: members = ctx.guild.members
        server_data = await utility.get_server(ctx.guild)
        if setTo == 0: 
            try: setTo = server_data['antispam']['warn']
            except KeyError: setTo = 3
        status = await ctx.send(embed=embed)
        oldWarnings = {}
        for m in server_data['members']:
            if m['id'] in [member.id for member in members]: oldWarnings[m['id']] = copy.deepcopy(m)['warnings'] 
        await database.SetWarnings(members, setTo)
        configured = [k for k, v in oldWarnings.items() if v != setTo]
        if len(configured) == 0:
            embed.description='All members up to date already'
        elif len(configured) <= 15:
            for identification in configured: 
                embed.add_field(name=m.name, value=f'> {oldWarnings[identification]} → **{setTo}** warnings', inline=False)
                embed.description = ''
        else: embed.description = f'Updated warnings for {len(configured)} members\n> Set to {setTo} warnings'
        await status.edit(embed=embed)

    @commands.is_owner()
    @commands.command()
    async def antispamStats(self, ctx):
        averageSecondsPartial = sum(self.antispamProcessTimes) / len(self.antispamProcessTimes)
        averageSecondsFull = sum(self.fullAntispamProcessTimes) / len(self.fullAntispamProcessTimes)
        await ctx.send(f'Partial avg: {averageSecondsPartial}\nFull average: {averageSecondsFull}\nLast 20 partial: {self.antispamProcessTimes[-20:]}\nLast 20 full: {self.fullAntispamProcessTimes[-20:]}')

    @commands.command()
    async def warnings(self, ctx):
        warningCount = await self.FetchWarnings(ctx.author)
        mentions = discord.AllowedMentions(users=False)
        if warningCount: await ctx.send(f'{ctx.author.mention}, you have {warningCount} warning{"s" if warningCount != 1 else ""} in my antispam system', allowed_mentions = mentions)
        else: await ctx.send(f'{ctx.author.mention}, I was unable to retrieve your warning count')

    async def FetchWarnings(self, member: discord.Member):
        for m in (await utility.get_server(member.guild))['members']:
            if m['id'] == member.id: return m['warnings']
        return -1

async def CheckRoleExclusions(member: discord.Member):
    '''Checks a member's roles to determine if their roles are in the exceptions list
        Return True if a member's role is in the list'''
    exclusions = (await utility.get_server(member.guild)).get('antispam').get('roleExclusions')
    for role in member.roles:
        if role.id in exclusions:
            return True
    return False

async def GetChannelExclusions(s: discord.Guild):
    '''Returns the list of channel IDs (exclusions) for the given server'''
    return (await utility.get_server(s)).get('antispam').get('channelExclusions')

async def GetMemberExclusions(s: discord.Guild):
    '''Returns the list of member IDs (exclusions) for the given server'''
    return (await utility.get_server(s)).get('antispam').get('memberExclusions')

def GetRoleManagementPermissions(member: discord.Member):
    '''Returns True if a member has Manage Role permissions'''
    for role in member.roles:
        if role.permissions.manage_roles or role.permissions.administrator:
            return True
    return False

async def PrepareMembers(bot: commands.Bot):
    '''Initialize the local profanityfilter objects'''
    global members
    for server in bot.guilds:
        try:
            for m in (await utility.get_server(server)).get('members'): members[f'{server.id}_{m.get("id")}'] = m
        except Exception as e: print(f'Passing - {e}')
    print(members)

async def setup(bot: commands.Bot):
    await bot.add_cog(Antispam(bot))
