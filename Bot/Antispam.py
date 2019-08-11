import discord
from discord.ext import commands
import database
import datetime
import profanityfilter
import emoji
import Cyberlog
import asyncio
import profanityfilter

filters = {}
loading = None

class ParodyMessage(object):
    def __init__(self, content, created):
        self.content = content
        self.created = created


class Antispam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await asyncio.sleep(2)
        '''[DISCORD API METHOD] Called when message is sent'''
        if message.author.bot or type(message.channel) is not discord.TextChannel: #Return if a bot sent the message or it's a DM
            return
        spam = await database.GetAntiSpamObject(message.guild)
        if not spam.get('enabled'): return #return if antispam isn't enabled
        servers = await database.GetMembersList(message.guild)
        person = None
        '''IMPLEMENT QUICKMESSAGE/LASTMESSAGE MESSAGE ARRAYS'''
        #The following lines of code deal with a member's lastMessages and quickMessages:
        #Sending eqivalent messages/sending too many messages too quickly, respectively
        #Probably the least fun part of antispam to code due to constant updating and reading, but it beats storing locally,
        #Partially due to readibility(I can view things online) and reliability
        '''Adding newly sent messages to DB'''
        '''Removal if messages are too old'''
        for member in servers:
            if member.get("id") == message.author.id:
                person = member
                lastMessages = member.get("lastMessages")
                quickMessages = member.get("quickMessages")
                if message.content is not None and len(message.content) > 0:
                    lastMessages.append(vars(ParodyMessage(message.content, message.created_at))) #Adds a ParodyMessage object (simplified discord.Message; two variables)
                if message.channel.id not in await database.GetChannelExclusions(message.guild) and not await CheckRoleExclusions(message.author) and message.author.id not in await database.GetMemberExclusions(message.guild):
                    quickMessages.append(vars(ParodyMessage(message.content, message.created_at)))
                    for msg in lastMessages:
                        if datetime.datetime.utcnow() - msg.get("created") > datetime.timedelta(seconds=spam.get("congruent")[2]):
                            lastMessages.remove(msg)
                        if len(lastMessages) > spam.get("congruent")[1]:
                            lastMessages.pop(0)
                    for msg in quickMessages:
                        if datetime.datetime.utcnow() - msg.get("created") > datetime.timedelta(seconds=spam.get("quickMessages")[1]):
                            quickMessages.remove(msg)
                        if len(quickMessages) > spam.get("quickMessages")[0]:
                            quickMessages.pop(0)
                    await database.UpdateMemberLastMessages(message.guild.id, message.author.id, lastMessages)
                    await database.UpdateMemberQuickMessages(message.guild.id, message.author.id, quickMessages)
                    break
        if spam.get('exclusionMode') == 0:
            if not (message.channel.id in spam.get('channelExclusions') and await CheckRoleExclusions(message.author) or message.author.id in spam.get('memberExclusions')): return
        else:
            if message.channel.id in spam.get('channelExclusions') or message.author.id in spam.get('memberExclusions') or await CheckRoleExclusions(message.author): return
        if spam.get('ignoreRoled') and len(message.author.roles) > 1:
            return #Return if we're ignoring members with roles and they have a role that's not the @everyone role that everyone has (which is why we can tag @everyone)
        reason = [] #List of reasons (long version) that a member was flagged for
        short = [] #list of reasons (short version) that a member was flagged for
        flag = False #was a member flagged?
        if spam.get("congruent")[0] != 0 or 0 not in spam.get("quickMessages"): 
            #Checking for lastMessages and quickMessages
            for member in servers:
                if member.get("id") == message.author.id:
                    lastMessages = member.get("lastMessages")
                    quickMessages = member.get("quickMessages")
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
                            lastMessages = []
                            await database.UpdateMemberLastMessages(message.guild.id, message.author.id, lastMessages)
                    if 0 not in spam.get("quickMessages"):
                        timeOne = quickMessages[0].get("created")
                        timeLast = quickMessages[-1].get("created")
                        if (timeLast - timeOne).seconds < spam.get("quickMessages")[1] and len(quickMessages) >= spam.get("quickMessages")[0]:
                            flag = True
                            reason.append("Sending too many messages in too little time\n" + str(message.author) + " sent " + str(len(quickMessages)) + " messages in " + str((timeLast - timeOne).seconds) + " seconds")
                            short.append("Spamming messages too fast")
                            quickMessages = []
                            await database.UpdateMemberQuickMessages(message.guild.id, message.author.id, quickMessages)
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
            if "ping" in message.content.lower() and "ms" in message.content.lower():
                flag = True
                reason.append("Appearing to selfbot: Latency ping message")
                short.append("Selfbotting (ping)")
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
            if "http" in message.content and ":" in message.content:
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
            if len(message.content) > 0:
                parsed = ""
                spaces = 0
                for a in message.content:
                    if a == " ":
                        spaces += 1
                global filters
                currentFilter = profanityfilter.ProfanityFilter()
                currentFilter._censor_list = filters.get(str(message.guild.id))
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
        if not flag: 
            return
        if spam.get("action") in [1, 4] and not GetRoleManagementPermissions(message.guild.me):
            return await message.channel.send("I flagged user `" + str(message.author) + "`, but need Manage Role permissions for the current consequence to be given. There are two solutions:\n  •Add the Manage Role permissions to me\n  •Enter your server's web dashboard and change the punishment for being flagged")
        if spam.get("delete"):
            try:
                Cyberlog.AvoidDeletionLogging(1, message.guild)
                await message.delete()
            except:
                await message.channel.send("I require Manage Message permissions to carry out deleting messages upon members being flagged")
        successful = False #Was a member's consequence carried out successfully?
        desc = [] #List of error messages, if applicable
        warned = False #Was a member warned?
        roled = False #Did member receive a role upon their consequence?
        role = None #The role to use if applicable
        if person.get("warnings") >= 1:
            try:
                await database.UpdateMemberWarnings(message.guild, message.author, person.get("warnings") - 1)
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
                try:
                    await message.author.add_roles(role)
                    roled = True
                except discord.Forbidden:
                    desc.append("Unable to add role " + role.name + " to member upon being flagged")
                    successful = False
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
        if spam.get("whisper"):
            try:
                await message.author.send(embed=shorter)
                whispered = 2
            except discord.Forbidden:
                whispered = 1
        if not spam.get("whisper") or whispered != 2:
            await message.channel.send(embed=shorter)
        if None not in spam.get("log"):
            longer = discord.Embed(title=message.author.name + " was flagged for spam",description=message.author.mention + " was flagged for **" + str(len(short)) + " reasons**, details below",timestamp=datetime.datetime.utcnow(),color=0xFF00FF)
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
        if not roled:
            return
        await asyncio.sleep(spam.get("muteTime"))
        lcEmbed = None
        if role not in message.author.roles:
            lcEmbed = discord.Embed(title="Mute time is up for "+message.author.name,description="It appears somebody else already removed role **" + role.name + "** from __" + message.author.mention + "__",timestamp=datetime.datetime.utcnow(),color=0x3fd8e9)
        try:
            await message.author.remove_roles(role)
            lcEmbed = discord.Embed(title="Mute time is up for " + message.author.name,description="Successfully removed role **" + role.name + "** from __" + message.author.mention + "__",timestamp=datetime.datetime.utcnow(),color=0x00FF00)
        except discord.Forbidden:
            lcEmbed = discord.Embed(title="Mute time is up for " + message.author.name,description="Unable to remove role **" + role.name + "** from __" + message.author.mention + "__",timestamp=datetime.datetime.utcnow(),color=0x800000)
        if spam.get("log"):
            try:
                await message.guild.get_channel(spam.get("log")[1]).send(embed=lcEmbed)
            except discord.Forbidden:
                pass
        
async def CheckRoleExclusions(member: discord.Member):
    '''Checks a member's roles to determine if their roles are in the exceptions list
        Return True if a member's role is in the list'''
    for role in member.roles:
        if role.id in await database.GetAntiSpamObject(member.guild).get('roleExclusions'):
            return True
    return False

def GetRoleManagementPermissions(member: discord.Member):
    '''Returns True if a member has Manage Role permissions'''
    for role in member.roles:
        if role.permissions.manage_roles or role.permissions.administrator:
            return True
    return False

async def PrepareFilters(bot: commands.Bot):
    '''Initialize the local profanityfilter objects'''
    global filters
    global loading
    for server in bot.guilds:
        filters[str(server.id)] = await database.GetProfanityFilter(server)
    for e in bot.emojis:
        if e.id == 573298271775227914:
            loading = e

def setup(bot):
    bot.add_cog(Antispam(bot))
