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

filters = {}
members = {} #serverID_memberID: member

yellow=0xffff00
green=0x008000
red=0xff0000
blue=0x0000FF

class ParodyMessage(object):
    def __init__(self, content, created):
        self.content = content
        self.created = created


class Antispam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')
        self.checkTimedEvents.start()

    @tasks.loop(minutes=15)
    async def checkTimedEvents(self):
        if self.checkTimedEvents.current_loop == 0: await asyncio.sleep(120)
        try:
            for g in self.bot.guilds:
                events = self.bot.lightningLogging.get(g.id).get('antispam').get('timedEvents')
                for e in events:
                    if datetime.datetime.utcnow() > e.get('expires'):
                        if e.get('type') == 'ban':
                            try: await g.get_member(e.get('target')).unban(reason=f'{e.get("flavor")} Ban duration expired')
                            except discord.Forbidden as e: print(f'Timed ban error: {e.text}')
                        elif e.get('type') == 'mute':
                            member = g.get_member(e.get('target'))
                            try: 
                                await member.remove_roles(g.get_role(e.get('role')))
                                await member.add_roles(*[g.get_role(r) for r in e.get('roleList')])
                                for p in e.get('permissionsTaken'): await g.get_channel(p.get('id')).set_permissions(member, overwrite=discord.PermissionOverwrite.from_pair(discord.Permissions(p.get('overwrites')[0]), discord.Permissions(p.get('overwrites')[1])))
                            except discord.Forbidden as e: print(f'Timed mute error: {e.text}')
                        await database.RemoveTimedEvent(g, e)
        except: traceback.print_exc()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        '''[DISCORD API METHOD] Called when message is sent'''
        if message.author.bot or type(message.channel) is not discord.TextChannel: #Return if a bot sent the message or it's a DM
            return
        server = self.bot.lightningLogging.get(message.guild.id)
        try: spam = server.get('antispam')
        except AttributeError: return
        if not spam or not (spam.get('enabled') or spam.get('attachments')[-1]): return #return if antispam isn't enabled
        self.bot.loop.create_task(self.filterAntispam(message, spam))


    async def filterAntispam(self, message: discord.Message, spam):
        try: person = [m for m in self.bot.lightningLogging[message.guild.id]['members'] if m['id'] == message.author.id][0]
        except: return
        if not person: return

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
                        if Cyberlog.logEnabled(message.guild, 'message') and self.bot.lightningLogging.get(message.guild.id).get('cyberlog').get('image'): await asyncio.sleep(2) #Wait two seconds if image logging is enabled
                        try: await message.delete()
                        except discord.Forbidden: pass
                        return await message.channel.send(embed=discord.Embed(description=f'Please avoid sending {aFlag}s in this server', color=0xD2691E), delete_after=15)
        if not (any([spam.get('attachments')[:-1], spam.get('enabled')])): return
        try: lastMessages = person.get("lastMessages")
        except AttributeError: lastMessages = []
        try: quickMessages = person.get("quickMessages")
        except AttributeError: quickMessages = []
        cRE = CheckRoleExclusions(message.author)
        if message.content is not None and len(message.content) > 0: lastMessages.append(vars(ParodyMessage(message.content, message.created_at))) #Adds a ParodyMessage object (simplified discord.Message; two variables)
        if message.channel.id not in GetChannelExclusions(message.guild) and not cRE and message.author.id not in GetMemberExclusions(message.guild):
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
            #await database.UpdateMemberLastMessages(message.guild.id, message.author.id, lastMessages)
            #await database.UpdateMemberQuickMessages(message.guild.id, message.author.id, quickMessages)
            #members[f'{message.guild.id}_{message.author.id}'].update({'lastMessages': lastMessages, 'quickMessages': quickMessages})
            self.bot.lightningUsers[message.author.id].update({'lastMessages': lastMessages, 'quickMessages': quickMessages})
        if spam.get('exclusionMode') == 0:
            if not (message.channel.id in spam.get('channelExclusions') and cRE or message.author.id in spam.get('memberExclusions')): return
        else:
            if message.channel.id in spam.get('channelExclusions') or message.author.id in spam.get('memberExclusions') or cRE: return        
        if spam.get('ignoreRoled') and len(message.author.roles) > 1:
            return #Return if we're ignoring members with roles and they have a role that's not the @everyone role that everyone has (which is why we can tag @everyone)
        if spam.get("congruent")[0] != 0 or 0 not in spam.get("quickMessages"): 
            #Checking for lastMessages and quickMessages
            lastMessages = person.get("lastMessages")
            quickMessages = person.get("quickMessages")
            if spam.get("congruent")[0] != 0:
                likenessCounter = 1 #How many congruent messages were found while iterating over the list
                cont = None #Message content to be displayed in detailed log
                for a in range(len(lastMessages)):
                    for b in range(len(lastMessages)):
                        if a < b:
                            if lastMessages[a].get("content") == lastMessages[b].get("content"):
                                likenessCounter += 1
                                cont = lastMessages[a].get("content")
                                a += 1
                                break
                if likenessCounter >= spam.get("congruent")[0]:
                    flag = True
                    reason.append("Repeated messages: **" + cont + "**\n\n" + str(likenessCounter) + " repeats found; " + str(spam.get("congruent")[0]) + " in last " + str(spam.get("congruent")[1]) + " messages tolerated")
                    short.append("Repeated messages")
                    #members[f'{message.guild.id}_{message.author.id}'].update({'lastMessages': []})
                    self.bot.lightningUsers[message.author.id].update({'lastMessages': []})
                    lastMessages = []
                    #await database.UpdateMemberLastMessages(message.guild.id, message.author.id, lastMessages)
            if 0 not in spam.get("quickMessages") and len(quickMessages) > 0:
                timeOne = quickMessages[0].get("created")
                timeLast = quickMessages[-1].get("created")
                if (timeLast - timeOne).seconds < spam.get("quickMessages")[1] and len(quickMessages) >= spam.get("quickMessages")[0]:
                    flag = True
                    reason.append("Sending too many messages too quickly\n" + str(message.author) + " sent " + str(len(quickMessages)) + " messages in " + str((timeLast - timeOne).seconds) + " seconds")
                    short.append("Spamming messages too fast")
                    #members[f'{message.guild.id}_{message.author.id}'].update({'quickMessages': []})
                    self.bot.lightningUsers[message.author.id].update({'quickMessages': []})
                    quickMessages = []
                    #await database.UpdateMemberQuickMessages(message.guild.id, message.author.id, quickMessages)
        if spam.get('consecutiveMessages')[0] != 0:
            messages = await message.channel.history(limit=spam.get('consecutiveMessages')[0]).flatten()
            if len(messages) >= spam.get('consecutiveMessages')[0] and all([m.author.id == message.author.id for m in messages]) and (messages[0].created_at - messages[-1].created_at).seconds < spam.get('consecutiveMessages')[1]:
                flag = True
                reason.append(f'Sending too many messages in a row\n\n{message.author.name} sent {len(messages)} messages consecutively over {(messages[0].created_at - messages[-1].created_at).seconds} seconds (Server flag threshold: {spam.get("consecutiveMessages")[0]} messages over {spam.get("consecutiveMessages")[1]} seconds)')
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
            if any([w.startswith('ping') for w in message.content.lower().split(' ')]) and any([w.endswith('ms') for w in message.content.lower().split(' ')]):
                flag = True
                reason.append("Appearing to selfbot: Latency ping message")
                short.append("Selfbotting (ping message)")
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
        #if not flag:
        #    if person != self.bot.lightningUsers[message.author.id]:
        #        if person.get('lastMessages') != self.bot.lightningUsers.get('lastMessages'): asyncio.create_task(database.UpdateMemberLastMessages(message.guild.id, message.author.id, lastMessages))
        #        if person.get('quickMessages') != self.bot.lightningUsers.get('quickMessages'): asyncio.create_task(database.UpdateMemberQuickMessages(message.guild.id, message.author.id, quickMessages))
        #    return
        await message.channel.trigger_typing()
        if spam.get("action") in [1, 4] and not GetRoleManagementPermissions(message.guild.me):
            return await message.channel.send("I flagged user `" + str(message.author) + "`, but need Manage Role permissions for the current consequence to be given. There are two solutions:\n  •Add the Manage Role permissions to me\n  •Enter your server's web dashboard and change the punishment for being flagged")
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
                #await database.UpdateMemberWarnings(message.guild, message.author, person.get("warnings") - 1)
                #members[f'{message.guild.id}_{message.author.id}'].update({'warnings': person.get('warnings') - 1})
                self.bot.lightningUsers[message.author.id].update({'warnings': person['warnings'] - 1})
                successful = True
                warned = True
            except:
                desc.append("Unable to warn member")
        else:
            if spam.get("action") in [1, 4]:
                if spam.get("action") == 1:
                    for a in message.guild.roles:
                        if a.name == "RicobotAutoMute":
                            role = a
                            for a in message.guild.text_channels:
                                try: await a.set_permissions(role, send_messages=False)
                                except discord.Forbidden: pass
                            successful = True
                            break
                    if role is None:
                        try:
                            role = await message.guild.create_role(name="RicobotAutoMute", reason="Anti-Spam: AutoMute consequence")
                            successful = True
                        except discord.Forbidden:
                            desc.append("Unable to create new role for Automatic Mute")
                        try:
                            await role.edit(position=message.guild.me.top_role.position - 1)
                        except discord.Forbidden:
                            desc.append("Unable to move role to below my top role (so some members may not be muted)")
                        try:
                            for a in message.guild.channels:
                                if type(a) is discord.TextChannel:
                                    await a.set_permissions(role, send_messages=False)
                        except discord.Forbidden:
                            successful = False
                            desc.append("Unable to create permission overrides for RicobotAutoMute, so mute can't be enforced")  
                else:
                    role = message.guild.get_role(spam.get("customRole"))
                    successful = True
                memberRolesTaken = [r for r in message.author.roles if r != message.guild.default_role]
                permissionsTaken = []
                #rawPermissionsTaken = []
                try:
                    await message.author.add_roles(role)
                    await message.author.remove_roles(*memberRolesTaken)
                    for c in message.author.guild.text_channels:
                        if message.author in c.overwrites.keys():
                            before, after = c.overwrites.get(message.author).pair()
                            #permissionsTaken.append({'id': c.id, 'overwrites': c.overwrites.get(message.author)})
                            permissionsTaken.append({'id': c.id, 'overwrites': (before.value, after.value)})
                            await c.set_permissions(message.author, overwrite=None, reason='Automute')
                    roled = True
                except discord.Forbidden:
                    desc.append("Unable to add role " + role.name + " to member upon being flagged")
                    successful = False
                muteTimedEvent = {'type': 'mute', 'target': message.author.id, 'flavor': '[Antispam: AutoMute]', 'role': role.id, 'roleList': [r.id for r in memberRolesTaken], 'permissionsTaken': permissionsTaken, 'expires': datetime.datetime.utcnow() + datetime.timedelta(seconds=spam.get('muteTime'))}
                await database.AppendTimedEvent(message.guild, muteTimedEvent)
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
        shorter=discord.Embed(title=message.author.name+" got busted",description="Hey " + message.author.mention + ", looks like you got flagged for spam for **" + str(len(short)) + "** reason(s). The reason(s) is/are below, but to see these reasons in detail, please contact a moderator of " + message.guild.name + ".\n\n",timestamp=datetime.datetime.utcnow(),color=0xD2691E)
        for a in short:
            shorter.description += "• " + a + "\n"
        if person.get("warnings") >= 0 and warned:
            shorter.add_field(name="Your consequence",value="Warning (" + str(person.get("warnings") - 1) + " left)")
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
                directShorter.description += f'\n\n*You are receiving this DM because {flavorText}**'
                await message.author.send(embed=directShorter)
                whispered = 2
            except discord.Forbidden:
                whispered = 1
        if not spam.get("whisper") or whispered != 2:
            await message.channel.send(embed=shorter)
        if person.get('warnings') != self.bot.lightningUsers[message.author.id].get('warnings'): asyncio.create_task(database.UpdateMemberWarnings(message.guild, message.author, person.get('warnings') - 1))
        if None not in spam.get("log"):
            longer = discord.Embed(title=message.author.name + " was flagged for spam",description=message.author.mention + " was flagged for **" + str(len(short)) + " reasons**, details below",timestamp=datetime.datetime.utcnow(),color=0xFF00FF)
            for a in range(len(reason)):
                longer.add_field(name="Reason " + str(a + 1),value=reason[a],inline=False)
            if warned:
                longer.add_field(name="Member's consequence",value="Warning (" + str(person.get("warnings") - 1) + " / " + str(spam.get("warn")) + " left)")
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
        if not roled:
            return
        await asyncio.sleep(spam.get("muteTime"))
        if not message.channel.permissions_for(message.author).read_messages:
            try: await message.author.send(f'You are now unmuted in {message.guild.name}')
            except discord.Forbidden: pass
        lcEmbed = None
        if role not in message.guild.get_member(message.author.id).roles:
            lcEmbed = discord.Embed(title="Mute time is up for "+message.author.name,description="It appears somebody else already removed role **" + role.name + "** from __" + message.author.mention + "__, but I'll make sure the rest of the roles they had before were given back.",timestamp=datetime.datetime.utcnow(),color=0x3fd8e9)
        try:
            await message.author.remove_roles(role)
            lcEmbed = discord.Embed(title="Mute time is up for " + message.author.name,description="Successfully removed role **" + role.name + "** from __" + message.author.mention + "__",timestamp=datetime.datetime.utcnow(),color=0x00FF00)
        except discord.Forbidden:
            lcEmbed = discord.Embed(title="Mute time is up for " + message.author.name,description="Unable to remove role **" + role.name + "** from __" + message.author.mention + "__",timestamp=datetime.datetime.utcnow(),color=0x800000)
        try: await message.author.add_roles(*memberRolesTaken)
        except discord.Forbidden: lcEmbed.description+=f'Unable to add some roles back to {message.author.name}, make sure they have these roles: {" • ".join([r.name for r in memberRolesTaken])}'
        try:
            for p in permissionsTaken: await message.guild.get_channel(p.get('id')).set_permissions(message.author, overwrite=discord.PermissionOverwrite.from_pair(discord.Permissions(p.get('overwrites')[0]), discord.Permissions(p.get('overwrites')[1])))
        except discord.Forbidden: lcEmbed.description+=f'Unable to recreate channel permission overwrites for {message.author.name}'
        await database.RemoveTimedEvent(message.guild, muteTimedEvent)
        if spam.get("log"):
            try:
                await message.guild.get_channel(spam.get("log")[1]).send(embed=lcEmbed)
            except discord.Forbidden:
                pass
    
    @commands.command()
    async def ageKick(self, ctx, *args):
        await ctx.trigger_typing()
        newline = '\n'
        if not await database.ManageServer(ctx.author): return await ctx.send('You need manage server, administrator, or server owner permissions to use this')
        config = self.bot.lightningLogging.get(ctx.guild.id).get('antispam')
        wl = config.get('ageKickWhitelist')
        if len(args) == 0:
            e=discord.Embed(title=f'Age Kick Information: {ctx.guild.name}', description=f'''**{"WHITELIST ENTRIES":–^70}**\n{newline.join([f'•{(await self.bot.fetch_user(w)).name} ({w})' for w in wl]) if wl is not None and len(wl) > 0 else '(Whitelist is empty)'}\n**{"RECIPIENT DM MESSAGE":–^70}**\n{config.get("ageKickDM")}''', color=yellow, timestamp=datetime.datetime.utcnow())
            e.add_field(name='Kick Accounts',value=f'Under {config.get("ageKick")} days old')
            e.add_field(name=f'Manageable by {ctx.guild.owner.name} only',value=config.get('ageKickOwner'))
            await ctx.send(embed=e)
        else:
            if config.get('ageKickOwner') and ctx.author.id != ctx.guild.owner.id: return await ctx.send(f'Only the owner of this server ({ctx.guild.owner.name}) can edit the ageKick configuration.')
            arg = args[0]
            e = discord.Embed(title='Age Kick Configuration',description='{} Saving...'.format(self.loading),color=yellow,timestamp=datetime.datetime.utcnow())
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
            e.set_footer(text='React 🔄 to view ageKick configuration')
            await m.edit(embed=e)
            await m.add_reaction('🔄')
            await Cyberlog.updateServer(ctx.guild)
            config = self.bot.lightningLogging.get(ctx.guild.id).get('antispam')
            wl = config.get('ageKickWhitelist')
            def configCheck(r, u): return str(r) == '🔄' and r.message.id == m.id and u.id == ctx.author.id
            await self.bot.wait_for('reaction_add', check=configCheck)
            await m.clear_reactions()
            return await m.edit(embed=discord.Embed(title=f'Age Kick Information: {ctx.guild.name}', description=f'''**{"WHITELIST IDs":–^70}**\n{newline.join([f'•{(await self.bot.fetch_user(w)).name} ({w})' for w in wl]) if wl is not None and len(wl) > 0 else '(Whitelist is empty)'}\n**{"RECIPIENT DM MESSAGE":–^70}**\n{config.get('ageKickDM')}''', color=yellow, timestamp=datetime.datetime.utcnow()))
        
def CheckRoleExclusions(member: discord.Member):
    '''Checks a member's roles to determine if their roles are in the exceptions list
        Return True if a member's role is in the list'''
    exclusions = Cyberlog.lightningLogging.get(member.guild.id).get('antispam').get('roleExclusions')
    for role in member.roles:
        if role.id in exclusions:
            return True
    return False

def GetChannelExclusions(s: discord.Guild):
    '''Returns the list of channel IDs (exclusions) for the given server'''
    return Cyberlog.lightningLogging.get(s.id).get('antispam').get('channelExclusions')

def GetMemberExclusions(s: discord.Guild):
    '''Returns the list of member IDs (exclusions) for the given server'''
    return Cyberlog.lightningLogging.get(s.id).get('antispam').get('memberExclusions')

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
            for m in bot.lightningLogging.get(server.id).get('members'): members[f'{server.id}_{m.get("id")}'] = m
        except Exception as e: print(f'Passing - {e}')
    print(members)

def setup(bot):
    bot.add_cog(Antispam(bot))
