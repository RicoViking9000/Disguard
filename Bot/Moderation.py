import discord
from discord.ext import commands
import database
import datetime
import Cyberlog #Used to prevent delete logs upon purging

current = None

class PurgeObject(object):
    def __init__(self, message=None, botMessage=None, limit=100, author=None, contains=None, startsWith=None, endsWith=None, links=None, invites=None, images=None, embeds=None, mentions=None, bots=None, channel=None, files=None, reactions=None, appMessages=None, startDate=None, endDate=None):
        self.message = message
        self.botMessage = botMessage
        self.limit = limit
        self.author = author
        self.contains = contains
        self.startsWith = startsWith
        self.endsWith = endsWith
        self.links = links
        self.invites = invites
        self.images = images
        self.embeds = embeds
        self.mentions = mentions
        self.bots = bots
        self.channel = channel
        self.files = files
        self.reactions = reactions
        self.appMessages = appMessages
        self.startDate = startDate
        self.endDate = endDate

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def purge(self, ctx, *args):
        '''Purge messages'''
        global current
        current = PurgeObject()
        if not (GetManageMessagePermissions(ctx.author) and GetManageMessagePermissions(ctx.guild.me)):
            return await ctx.send("Both you and I must have Manage Message permissions to utilize the purge command")
        if len(args) < 1:
            return await ctx.send("Please provide filters for the purge, or at the minimum, a number of messages to purge:\n`.purge 5`, for example, is the minimum\nRefer to `.help` documentation for advanced usage")
        status = await ctx.send("Parsing filters...")
        actuallyPurge = False
        current.channel = ctx.channel
        current.message = ctx.message
        current.botMessage = status
        try:
            for arg in args:
                meat = arg[arg.find(":")+1:].strip()
                body = arg.lower()
                if "count" in body: current.limit = int(meat)
                elif "purge" in body: actuallyPurge = True if "true" in meat.lower() else False
                elif "author" in body: current.author = ctx.guild.get_member_named(meat)
                elif "contains" in body: current.contains = meat
                elif "startswith" in body: current.startsWith = meat
                elif "endswith" in body: current.endsWith = meat
                elif "links" in body: current.links = True if "true" in meat.lower() else False
                elif "invites" in body: current.invites = True if "true" in meat.lower() else False
                elif "images" in body: current.images = True if "true" in meat.lower() else False
                elif "embeds" in body: current.embeds = True if "true" in meat.lower() else False
                elif "mentions" in body: current.mentions = True if "true" in meat.lower() else False
                elif "bots" in body: current.bots = True if "true" in meat.lower() else False
                elif "channel" in body: current.channel = ctx.message.channel_mentions[0] if len(ctx.message.channel_mentions) > 0 else ctx.channel
                elif "attachments" in body: current.files = True if "true" in meat.lower() else False
                elif "reactions" in body: current.reactions = True if "true" in meat.lower() else False
                elif "external_messages" in body: current.appMessages = True if "true" in meat.lower() else False
                elif "after" in body: current.startDate = ConvertToDatetime(meat)
                elif "before" in body: current.endDate = ConvertToDatetime(meat)
                else:
                    try: 
                        current.limit = int(body) #for example, .purge 10 wouldn't fall into the above categories, but is used due to rapid ability
                    except:
                        current = None
                        return await ctx.send("I don't think **"+body+"** is a number... please try again, or use the website documentation for filters")
                    actuallyPurge = True
            if actuallyPurge:
                await status.edit(content="Purging...")
                messages = await current.channel.purge(limit=current.limit, check=PurgeFilter, before=current.endDate, after=current.startDate)
                await status.edit(content="**Successfully purged "+str(len(messages))+" messages :ok_hand:**")
            else:
                await status.edit(content="Indexing... please be patient")
                count = 0
                async for message in current.channel.history(limit=current.limit, before=current.endDate, after=current.startDate):
                    if PurgeFilter(message): count += 1
                embed=discord.Embed(title="Purge pre-scan",description="__Filters:__\nLimit: "+str(current.limit)+" messages\n",color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
                if current.author is not None: embed.description += "Author: "+current.author.mention+"\n"
                if current.channel is not None: embed.description += "In channel: "+current.channel.mention+"\n"
                if current.contains is not None: embed.description += "Contains: "+current.contains+"\n"
                if current.startsWith is not None: embed.description += "Starts with: "+current.startsWith+"\n"
                if current.endsWith is not None: embed.description += "Ends with: "+current.endsWith+"\n"
                if current.startDate is not None: embed.description += "Posted after: "+current.startDate.strftime("%b %d, %Y")+"\n"
                if current.endDate is not None: embed.description += "Posted before: "+current.endDate.strftime("%b %d, %Y")+"\n"
                if current.links is True: embed.description += "Contains URLs\n"
                if current.invites is True: embed.description += "Contains server invites\n"
                if current.images is True: embed.description += "Contains Images\n"
                if current.embeds is True: embed.description += "Contains URLs\n"
                if current.mentions is True: embed.description += "Contains @mentions\n"
                if current.bots is True: embed.description += "Authored by bots\n"
                if current.files is True: embed.description += "Contains files (incl. images)\n"
                if current.reactions is True: embed.description += "Contains reactions\n"
                if current.appMessages is True: embed.description += "Contains external invites (e.g. Spotify)\n"
                embed.set_footer(text="To actually purge, copy & paste your command message, but add 'purge:true' to the filters")
                embed.description+="\n**"+str(count)+" messages matched the filters**"
                await status.edit(content=None,embed=embed)
            current = None
        except Exception as e:
            await ctx.send("Error - send this to my dev to decode:\n"+str(e))

def PurgeFilter(m: discord.Message):
    '''Used to determine if a message should be purged'''
    global current
    if m == current.message or m == current.botMessage:
        return False
    if current.contains is not None:
        if current.contains not in m.content:
            return False
    if current.author is not None: 
        if current.author != m.author:
            return False
    if current.startsWith is not None:
        if not m.content.startswith(current.startsWith):
            return False
    if current.endsWith is not None:
        if not m.content.endswith(current.endsWith):
            return False
    if current.links is True:
        if "https://" not in m.content and "http://" not in m.content:
            return False
    if current.invites is True:
        if "discord.gg/" not in m.content:
            return False
    if current.images is True:
        if len(m.attachments) < 1:
            return False
        else:
            if m.attachments[0].width is None:
                return False
    if current.embeds is True:
        if len(m.embeds) < 1:
            return False
    if current.mentions is True:
        if len(m.mentions) < 1:
            return False
    if current.bots is True:
        if not m.author.bot:
            return False
    if current.files is True:
        if len(m.attachments) < 1:
            return False
    if current.reactions is True:
        if len(m.reactions) < 1:
            return False
    if current.appMessages is True:
        if m.activity is None:
            return False
    return True

def GetManageMessagePermissions(member: discord.Member):
    for role in member.roles:
        if role.permissions.manage_messages or role.permissions.administrator:
            return True
    return False

def ConvertToDatetime(string: str):
    try:
        return datetime.datetime.strptime(string, "%b %d, %Y")
    except:
        try:
            return datetime.datetime.strptime(string, "%m/%d/%y")
        except:
            pass
    return None

def setup(bot):
    bot.add_cog(Moderation(bot))
