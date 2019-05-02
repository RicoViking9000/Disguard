import discord
from discord.ext import commands
import database
import datetime

bot = None
imageLogChannel = discord.TextChannel
globalLogChannel = discord.TextChannel
pauseDelete = 0
serverDelete = None
loading = None

class Cyberlog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        '''[DISCORD API METHOD] Called when message is sent
        Unlike RicoBot, I don't need to spend over 1000 lines of code doing things here due to web dashboard :D'''
        global imageLogChannel
        if message.author.bot:
            return
        if database.GetImageLogPerms(message.guild) and len(message.attachments) > 0:
            embed=discord.Embed(title="Image", description=" ")
            embed.set_image(url=message.attachments[0].url)
            await imageLogChannel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        '''[DISCORD API METHOD] Called when message is edited'''
        if before.author.bot or len(before.embeds) > 0 or before.content == after.content or not database.GetEnabled(before.guild, "message"):
            return
        if database.GetLogChannel(before.guild, "message") is not None:
            beforeWordList = before.content.split(" ")
            afterWordList = after.content.split(" ")
            beforeC = ""
            afterC = ""
            for b in beforeWordList:
                if b not in afterWordList:
                    beforeC += "**" + b + "** "
                else:
                    beforeC += b + " "
            for b in afterWordList:
                if b not in beforeWordList:
                    afterC += "**" + b + "** "
                else:
                    afterC += b + " "
            embed=discord.Embed(title="Message was edited",description="Author: "+before.author.mention+" ("+before.author.name+")",color=0x0000FF,timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Previously: ", value=beforeC,inline=False)
            embed.add_field(name="Now: ", value=afterC,inline=False)
            embed.add_field(name="Channel: ", value=str(before.channel.mention))
            embed.set_footer(text="Message ID: " + str(after.id))
            embed.set_thumbnail(url=before.author.avatar_url)
            await database.GetLogChannel(before.guild, 'message').send(content=None,embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        '''[DISCORD API METHOD] Called when message is deleted'''
        global pauseDelete
        global serverDelete
        if pauseDelete > 0 and message.guild == serverDelete:
            pauseDelete -= 1
            return
        else:
            serverDelete = None
        if message.author.bot or message.author not in message.guild.members or not database.GetEnabled(message.guild, "message"):
            return
        embed=discord.Embed(title="Message was deleted",description="Author: "+message.author.mention+" ("+message.author.name+")\nChannel: "+message.channel.mention+"\nSent: "+(message.created_at - datetime.timedelta(hours=4)).strftime("%b %d, %Y - %I:%M %p")+" EST",timestamp=datetime.datetime.utcnow(),color=0xff0000)
        embed.set_thumbnail(url=message.author.avatar_url)
        content=None
        if len(message.attachments) > 0 and database.GetImageLogPerms(message.guild):
            embed.set_image(url=message.attachments[0].url)
        if database.GetReadPerms(message.guild, "message"):
            try:
                async for log in message.guild.audit_logs(limit=1):
                    if (datetime.datetime.utcnow() - log.created_at).seconds < 2:
                        if log.action == discord.AuditLogAction.message_delete:
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
            except discord.Forbidden:
                content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
        embed.set_footer(text="Message ID: "+str(message.id))
        embed.add_field(name="Content",value="(No content)" if message.content is None or len(message.content)<1 else message.content)
        await database.GetLogChannel(message.guild, "message").send(content=content,embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is created'''
        global bot
        content=None
        if database.GetEnabled(channel.guild, "channel"):
            chan = "Text" if type(channel) is discord.TextChannel else None
            chan = "Voice" if type(channel) is discord.VoiceChannel else chan
            chan = "Category" if type(channel) is discord.CategoryChannel else chan
            embed=discord.Embed(title=chan + " Channel was created", description=channel.mention+" ("+channel.name+")" if type(channel) is discord.TextChannel else channel.name,color=0x008000,timestamp=datetime.datetime.utcnow())
            if type(channel) is not discord.CategoryChannel:
                embed.add_field(name="Category",value=str(channel.category.name))
            if database.GetReadPerms(channel.guild, "channel"):
                try:
                    async for log in channel.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_create:
                            embed.description+="\nCreated by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.set_footer(text="Channel ID: "+str(channel.id))
            await database.GetLogChannel(channel.guild, "channel").send(content=content,embed=embed)
        database.VerifyServer(channel.guild, bot) #Update database to reflect creation. This call is used frequently here. Placed at bottom to avoid delay before logging

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when server channel is updated'''
        global bot
        if database.GetEnabled(before.guild, "channel"):
            content=None
            chan = "Text" if type(before) is discord.TextChannel else None
            chan = "Voice" if type(before) is discord.VoiceChannel else chan
            chan = "Category" if type(before) is discord.CategoryChannel else chan
            embed=discord.Embed(title=chan + " Channel was updated", description=before.mention if type(before) is discord.TextChannel else before.name,color=0x0000FF,timestamp=datetime.datetime.utcnow())
            if database.GetReadPerms(before.guild, "channel"):
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_update:
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.set_footer(text="Channel ID: "+str(before.id))
            embed.add_field(name="Name",value=before.name+" → "+after.name if before.name != after.name else "(No change)")
            if type(before) is discord.TextChannel:
                beforeTopic = before.topic if before.topic is not None else "<No topic>"
                afterTopic = after.topic if after.topic is not None else "<No topic>"
                embed.add_field(name="Topic",value=str(beforeTopic)+" → "+str(afterTopic) if before.topic != after.topic else "(No change)")
                embed.add_field(name="NSFW",value=str(before.is_nsfw())+" → "+str(after.is_nsfw()) if before.is_nsfw() != after.is_nsfw() else "(No change)")
            elif type(before) is discord.VoiceChannel:
                embed.add_field(name="Bitrate",value=str(before.bitrate)+" → "+str(after.bitrate) if before.bitrate != after.bitrate else "(No change)")
                embed.add_field(name="User limit",value=str(before.user_limit)+" → "+str(after.user_limit) if before.user_limit != after.user_limit else "(No change)")
            beforeCat = str(before.category) if before.category is not None else "<No category>"
            afterCat = str(after.category) if after.category is not None else "<No category>"
            if type(before) is not discord.CategoryChannel:
                embed.add_field(name="Category",value=str(beforeCat)+" → "+str(afterCat) if before.category != after.category else "(No change)")
            if type(before) is discord.TextChannel and before.topic != after.topic or before.name != after.name or before.category != after.category or before.is_nsfw() != after.is_nsfw():
                await database.GetLogChannel(before.guild, "channel").send(content=content,embed=embed)
            elif type(before) is discord.VoiceChannel and before.name != after.name or before.bitrate != after.bitrate or before.user_limit != after.user_limit or before.category != after.category:
                await database.GetLogChannel(before.guild, "channel").send(content=content,embed=embed)
            elif type(before) is discord.CategoryChannel and before.name != after.name:
                 await database.GetLogChannel(before.guild, "channel").send(content=content,embed=embed)
        database.VerifyServer(before.guild, bot)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        '''[DISCORD API METHOD] Called when channel is deleted'''
        global bot
        if database.GetEnabled(channel.guild, "channel"):
            content=None
            chan = "Text" if type(channel) is discord.TextChannel else None
            chan = "Voice" if type(channel) is discord.VoiceChannel else chan
            chan = "Category" if type(channel) is discord.CategoryChannel else chan
            embed=discord.Embed(title=chan + " Channel was deleted", description=channel.name,color=0xff0000,timestamp=datetime.datetime.utcnow())
            if type(channel) is not discord.CategoryChannel:
                embed.add_field(name="Category",value=str(channel.category.name))
            if database.GetReadPerms(channel.guild, "channel"):
                try:
                    async for log in channel.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.channel_delete:
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            embed.set_footer(text="Channel ID: "+str(channel.id))
            await database.GetLogChannel(channel.guild, "channel").send(content=content,embed=embed)
        database.VerifyServer(channel.guild, bot)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member joins a server'''
        global bot
        if database.GetEnabled(member.guild, "doorguard"):
            embed=discord.Embed(title="New member",description=member.mention+"("+member.name+")",timestamp=datetime.datetime.utcnow(),color=0x008000)
            embed.add_field(name="Mutual Servers",value=len([a for a in iter(bot.guilds) if member in a.members]))
            embed.add_field(name="Reputation",value="N/A")
            embed.set_thumbnail(url=member.avatar_url)
            await database.GetLogChannel(member.guild, "doorguard").send(embed=embed)
        database.VerifyServer(member.guild, bot)
        database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        '''[DISCORD API METHOD] Called when member leaves a server'''
        global bot
        if database.GetEnabled(member.guild, "doorguard"):
            embed=discord.Embed(title="Member left",description=member.mention+"("+member.name+")",timestamp=datetime.datetime.utcnow(),color=0xff0000)
            span = datetime.datetime.utcnow() - member.joined_at
            hours = span.seconds//3600
            minutes = (span.seconds//60)%60
            embed.add_field(name="Here for",value=str(span.days)+" days, "+str(hours)+" hours, "+str(minutes)+" minutes, "+str(span.seconds - hours*3600 - minutes*60)+" seconds")
            embed.set_thumbnail(url=member.avatar_url)
            await database.GetLogChannel(member.guild, "doorguard").send(embed=embed)
        database.VerifyServer(member.guild, bot)
        database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        '''[DISCORD API METHOD] Called when member changes status/game, roles, or nickname; only the two latter events used with this bot'''
        if (before.nick != after.nick or before.roles != after.roles) and database.GetEnabled(before.guild, "member"):
            content=None
            embed=discord.Embed(title="Member's server attributes updated",description=before.mention+"("+before.name+")",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
            if before.roles != after.roles:
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.member_role_update and (datetime.datetime.utcnow() - log.created_at).seconds < 2: 
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
                for f in after.roles:
                    if f not in before.roles:
                        if f.name != "RicobotAutoMute" and f != before.guild.get_role(database.GetAntiSpamObject(before.guild).get("customRoleID")):
                            embed.add_field(name="Role added",value=f.name)
                for f in before.roles:
                    if f not in after.roles:
                        if f.name != "RicobotAutoMute" and f != before.guild.get_role(database.GetAntiSpamObject(before.guild).get("customRoleID")):
                            embed.add_field(name="Role removed",value=f.name)
            if before.nick != after.nick:
                try:
                    async for log in before.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.member_update and (datetime.datetime.utcnow() - log.created_at).seconds < 2: 
                            embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
                oldNick = before.nick if before.nick is not None else "<No nickname>"
                newNick = after.nick if after.nick is not None else "<No nickname>"
                embed.add_field(name="Nickname change",value=oldNick+" → "+newNick)
            embed.set_thumbnail(url=before.avatar_url)
            embed.set_footer(text="Member ID: "+str(before.id))
            await database.GetLogChannel(before.guild, "member").send(content=content,embed=embed)
        global bot
        database.VerifyUser(before, bot)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        '''[DISCORD API METHOD] Called when a user changes their global username, avatar, or discriminator'''
        servers = []
        print("user update")
        global bot
        membObj = None
        for server in bot.guilds: #Since this method doesn't supply a server, we need to get every server this member is a part of, to
            for member in server.members: #log to when they change their username, discriminator, or avatar
                if member.id == before.id:
                    servers.append(server)
                    membObj = member
                    break
        embed=discord.Embed(title="User's global attributes updated",description=before.mention+"("+before.name+")",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
        if before.avatar_url != after.avatar_url:
            if before.avatar_url is not None:
                embed.set_thumbnail(url=before.avatar_url)
            if after.avatar_url is not None:
                embed.set_image(url=after.avatar_url)
            embed.add_field(name="Profile Picture updated",value="Old: Thumbnail to the right\nNew: Image below")
        else:
            embed.set_thumbnail(url=before.avatar_url)
        if before.discriminator != after.discriminator:
            embed.add_field(name="Discriminator updated",value=before.discriminator+" → "+after.discriminator)
        if before.name != after.name:
            embed.add_field(name="Username updated",value=before.name+" → "+after.name)
        embed.set_footer(text="User ID: "+str(after.id))
        for server in servers:
            database.VerifyServer(server, bot)
            if database.GetEnabled(server, "member"):
                await database.GetLogChannel(server, "member").send(embed=embed)
        database.VerifyUser(membObj, bot)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot joins a server'''
        global bot
        global globalLogChannel
        await globalLogChannel.send(embed=discord.Embed(title="Joined server",description=guild.name,timestamp=datetime.datetime.utcnow(),color=0x008000))
        database.VerifyServer(guild, bot)
        database.VerifyUsers(bot)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        global bot
        if database.GetEnabled(before, 'server'):
            embed=discord.Embed(title="Server updated",description="",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
            content=None
            if database.GetReadPerms(before, 'server'):
                try:
                    async for log in before.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.guild_update:
                            embed.description= "By: "+log.user.mention+" ("+log.user.name+")"
                            embed.set_thumbnail(url=log.user.avatar_url)
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            if before.afk_channel != after.afk_channel:
                b4 = before.afk_channel.name if before.afk_channel is not None else "(None)"
                af = after.afk_channel.name if after.afk_channel is not None else "(None)"
                embed.add_field(name="AFK Channel",value=b4+" → "+af)
            if before.afk_timeout != after.afk_timeout:
                embed.add_field(name="AFK Timeout",value=str(before.afk_timeout)+"s → "+str(after.afk_timeout)+"s")
            if before.mfa_level != after.mfa_level:
                b4 = True if before.mfa_level == 1 else False
                af = True if after.mfa_level == 1 else False
                embed.add_field(name="Mods need 2FA",value=b4+" → "+af)
            if before.name != after.name:
                embed.add_field(name="Name",value=before.name+" → "+after.name)
            if before.owner != after.owner:
                embed.add_field(name="Owner",value=before.owner.mention+" → "+after.owner.mention)
            if before.default_notifications != after.default_notifications:
                embed.add_field(name="Default notifications",value=before.default_notifications.name+" → "+after.default_notifications.name)
            if before.explicit_content_filter != after.explicit_content_filter:
                embed.add_field(name="Explicit content filter",value=before.explicit_content_filter.name+" → "+after.explicit_content_filter.name)
            if before.system_channel != after.system_channel:
                b4 = before.system_channel.mention if before.system_channel is not None else "(None)"
                af = after.system_channel.mention if after.system_channel is not None else "(None)"
                embed.add_field(name="System channel",value=b4+" → "+af)
            if len(embed.fields) > 0: await database.GetLogChannel(before, 'server').send(content=content,embed=embed)
        database.VerifyServer(after, bot)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        '''[DISCORD API METHOD] Called when the bot leaves a server'''
        global bot
        global globalLogChannel
        await globalLogChannel.send(embed=discord.Embed(title="Left server",description=guild.name,timestamp=datetime.datetime.utcnow(),color=0xff0000))
        database.VerifyServer(guild, bot)
        database.VerifyUsers(bot)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is created'''
        global bot
        if database.GetEnabled(role.guild, "role"):
            content=None
            embed=discord.Embed(title="Role created",timestamp=datetime.datetime.utcnow(),description=" ",color=0x008000)
            embed.description="Name: "+role.name if role.name != "new role" else ""
            if database.GetReadPerms(role.guild, "role"):
                try:
                    async for log in role.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.role_create: 
                            embed.description+="\nCreated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            await database.GetLogChannel(role.guild, "role").send(content=content,embed=embed)
        database.VerifyServer(role.guild, bot)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is deleted'''
        global bot
        if database.GetEnabled(role.guild, "role"):
            content=None
            embed=discord.Embed(title="Role deleted",description="Role: "+role.name,timestamp=datetime.datetime.utcnow(),color=0xff0000)
            if database.GetReadPerms(role.guild, "role"):
                try:
                    async for log in role.guild.audit_logs(limit=1):
                        if log.action == discord.AuditLogAction.role_delete: 
                            embed.description+="\nDeleted by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            await database.GetLogChannel(role.guild, "role").send(content=content,embed=embed)
        database.VerifyServer(role.guild, bot)
        for member in role.members:
            database.VerifyUser(member, bot)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        '''[DISCORD API METHOD] Called when a server role is updated'''
        global bot
        if database.GetEnabled(before.guild, "role"):
            content=None
            color=0x0000FF if before.color == after.color else after.color
            embed=discord.Embed(title="Role was updated",description="Name: "+ after.name if before.name == after.name else "Name: "+before.name+" → "+after.name,color=color,timestamp=datetime.datetime.utcnow())
            if database.GetReadPerms(before.guild, "role"):
                try:
                    async for log in before.guild.audit_logs(limit=1): #Color too
                            if log.action == discord.AuditLogAction.role_update:
                                embed.description+="\nUpdated by: "+log.user.mention+" ("+log.user.name+")"
                except discord.Forbidden:
                    content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
            if before.color != after.color: embed.description+="\nEmbed color represents new role color"
            embed.description+="\n:warning: "+str(len(after.members))+" members received updated permissions :warning:"
            if before.permissions.administrator != after.permissions.administrator: embed.add_field(name="Admin",value=str(before.permissions.administrator+" → "+after.permissions.administrator),inline=False)
            if before.hoist != after.hoist: embed.add_field(name="Displayed separately",value=str(before.hoist)+" → "+str(after.hoist))
            if before.mentionable != after.mentionable: embed.add_field(name="Mentionable",value=str(before.mentionable)+" → "+str(after.mentionable))
            if before.permissions.create_instant_invite != after.permissions.create_instant_invite: embed.add_field(name="Create invites",value=str(before.permissions.create_instant_invite)+" → "+str(after.permissions.create_instant_invite))
            if before.permissions.kick_members != after.permissions.kick_members: embed.add_field(name="Kick",value=str(before.permissions.kick_members)+" → "+str(after.permissions.kick_members))
            if before.permissions.ban_members != after.permissions.ban_members: embed.add_field(name="Ban",value=str(before.permissions.ban_members)+" → "+str(after.permissions.ban_members))
            if before.permissions.manage_channels != after.permissions.manage_channels: embed.add_field(name="Manage channels",value=str(before.permissions.manage_channels)+" → "+str(after.permissions.manage_channels))
            if before.permissions.manage_guild != after.permissions.manage_guild: embed.add_field(name="Manage server",value=str(before.permissions.manage_guild)+" → "+str(after.permissions.manage_guild))
            if before.permissions.add_reactions != after.permissions.add_reactions: embed.add_field(name="Add reactions",value=str(before.permissions.add_reactions)+" → "+str(after.permissions.add_reactions))
            if before.permissions.view_audit_log != after.permissions.view_audit_log: embed.add_field(name="View audit log",value=str(before.permissions.view_audit_log)+" → "+str(after.permissions.view_audit_log))
            if before.permissions.priority_speaker != after.permissions.priority_speaker: embed.add_field(name="[VC] Priority speaker",value=str(before.permissions.priority_speaker)+" → "+str(after.permissions.priority_speaker))
            if before.permissions.read_messages != after.permissions.read_messages: embed.add_field(name="Read messages",value=str(before.permissions.read_messages)+" → "+str(after.permissions.read_messages))
            if before.permissions.send_messages != after.permissions.send_messages: embed.add_field(name="Send messages",value=str(before.permissions.send_messages)+" → "+str(after.permissions.send_messages))
            if before.permissions.send_tts_messages != after.permissions.send_tts_messages: embed.add_field(name="Use /TTS",value=str(before.permissions.send_tts_messages)+" → "+str(after.permissions.send_tts_messages))
            if before.permissions.manage_messages != after.permissions.manage_messages: embed.add_field(name="Manage messages",value=str(before.permissions.manage_messages)+" → "+str(after.permissions.manage_messages))
            if before.permissions.embed_links != after.permissions.embed_links: embed.add_field(name="Embed URLs",value=str(before.permissions.embed_links)+" → "+str(after.permissions.embed_links))
            if before.permissions.attach_files != after.permissions.attach_files: embed.add_field(name="Attach files",value=str(before.permissions.attach_files)+" → "+str(after.permissions.attach_files))
            if before.permissions.read_message_history != after.permissions.read_message_history: embed.add_field(name="Read message history",value=str(before.permissions.read_message_history)+" → "+str(after.permissions.read_message_history))
            if before.permissions.mention_everyone != after.permissions.mention_everyone: embed.add_field(name="@everyone/@here",value=str(before.permissions.mention_everyone)+" → "+str(after.permissions.mention_everyone))
            if before.permissions.external_emojis != after.permissions.external_emojis: embed.add_field(name="Use global/nitro emotes",value=str(before.permissions.external_emojis)+" → "+str(after.permissions.external_emojis))
            if before.permissions.connect != after.permissions.connect: embed.add_field(name="[VC] Connect",value=str(before.permissions.connect)+" → "+str(after.permissions.connect))
            if before.permissions.speak != after.permissions.speak: embed.add_field(name="[VC] Speak",value=str(before.permissions.speak)+" → "+str(after.permissions.speak))
            if before.permissions.mute_members != after.permissions.mute_members: embed.add_field(name="[VC] Mute others",value=str(before.permissions.mute_members)+" → "+str(after.permissions.mute_members))
            if before.permissions.deafen_members != after.permissions.deafen_members: embed.add_field(name="[VC] Deafen others",value=str(before.permissions.deafen_members)+" → "+str(after.permissions.deafen_members))
            if before.permissions.move_members != after.permissions.move_members: embed.add_field(name="[VC] Move others",value=str(before.permissions.move_members)+" → "+str(after.permissions.move_members))
            if before.permissions.use_voice_activation != after.permissions.use_voice_activation: embed.add_field(name="[VC] Push to talk required",value=str(not(before.permissions.use_voice_activation))+" → "+str(not(after.permissions.use_voice_activation)))
            if before.permissions.change_nickname != after.permissions.change_nickname: embed.add_field(name="Change own nickname",value=str(before.permissions.change_nickname)+" → "+str(after.permissions.change_nickname))
            if before.permissions.manage_nicknames != after.permissions.manage_nicknames: embed.add_field(name="Change other nicknames",value=str(before.permissions.manage_nicknames)+" → "+str(after.permissions.manage_nicknames))
            if before.permissions.manage_roles != after.permissions.manage_roles: embed.add_field(name="Manage roles",value=str(before.permissions.manage_roles)+" → "+str(after.permissions.manage_roles))
            if before.permissions.manage_webhooks != after.permissions.manage_webhooks: embed.add_field(name="Manage webhooks",value=str(before.permissions.manage_webhooks)+" → "+str(after.permissions.manage_webhooks))
            if before.permissions.manage_emojis != after.permissions.manage_emojis: embed.add_field(name="Manage emoji", value=str(before.permissions.manage_emojis)+" → "+str(after.permissions.manage_emojis))
            embed.set_footer(text="Role ID: "+str(before.id))
            if len(embed.fields)>0 or before.name != after.name:
                await database.GetLogChannel(before.guild, "role").send(content=content,embed=embed)
        database.VerifyServer(before.guild, bot)
        for member in after.members:
            database.VerifyUser(member, bot)
    
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        '''[DISCORD API METHOD] Called when emoji list is updated (creation, update, deletion)'''
        if not database.GetEnabled(guild, "emoji"):
            return
        content=None
        embed=None
        if len(before) > len(after):
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0xff0000)
        elif len(after) > len(before):
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0x008000)
        else:
            embed=discord.Embed(title=" ",description=" ",timestamp=datetime.datetime.utcnow(),color=0x0000FF)
        if database.GetReadPerms(guild, "emoji"):
            try:
                async for log in guild.audit_logs(limit=1):
                    if log.action == discord.AuditLogAction.emoji_delete or log.action==discord.AuditLogAction.emoji_create or log.action==discord.AuditLogAction.emoji_update:
                        embed.description = "By: "+log.user.mention+" ("+log.user.name+")"
                        embed.set_thumbnail(url=log.user.avatar_url)
            except discord.Forbidden:
                content="You have enabled audit log reading for your server, but I am missing the required permission for that feature: <View Audit Log>"
        if len(before) > len(after): #Emoji was removed
            embed.title="Emoji removed"
            for emoji in before:
                if emoji not in after:
                    embed.add_field(name=emoji.name,value=str(emoji))
                    embed.set_footer(text="Emoji ID: "+str(emoji.id))
                    embed.set_image(url=emoji.url)
        elif len(after) > len(before): #Emoji was added
            embed.title="Emoji created"
            for emoji in after:
                if emoji not in before:
                    embed.add_field(name=emoji.name,value=str(emoji))
                    embed.set_footer(text="Emoji ID: "+str(emoji.id))
                    embed.set_image(url=emoji.url)
        else: #Emoji was updated
            embed.title="Emoji list updated"
            embed.set_footer(text="")
            for a in range(len(before)):
                if before[a].name != after[a].name:
                    embed.add_field(name=before[a].name+" → "+after[a].name,value=str(before[a]))
                    embed.set_footer(text=embed.footer.text+"Emoji ID: "+str(before[a].id))
                    embed.set_image(url=before[a].url)
        if len(embed.fields)>0:
            await database.GetLogChannel(guild, "emoji").send(content=content,embed=embed)

def AvoidDeletionLogging(messages: int, server: discord.Guild):
    '''Don't log the next [messages] deletions if they belong to particular passed server'''
    global pauseDelete
    global serverDelete
    pauseDelete = messages
    serverDelete = server

            
def setup(Bot):
    global bot
    global imageLogChannel
    global globalLogChannel
    global loading
    Bot.add_cog(Cyberlog(Bot))
    bot = Bot
    imageLogChannel = bot.get_channel(534439214289256478)
    globalLogChannel = bot.get_channel(566728691292438538)
    loading = bot.get_emoji(573298271775227914)