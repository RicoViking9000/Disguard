'''Contains code relating to various bonus/extra features of Disguard
This will initially only contain the Easter/April Fools Day events code, but over time will be expanded to include things that don't belong in other files
'''

import discord
import secure
from discord.ext import commands, tasks
from discord import app_commands
import database
import utility
import lyricsgenius
import re
import asyncio
import datetime
import emoji
import traceback
import typing
import textwrap
import utility
import Cyberlog
import copy
import re

yellow = (0xffff00, 0xffff66)
placeholderURL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
qlf = '  ' #Two special characters to represent quoteLineFormat
qlfc = ' '
NEWLINE = '\n'
units = ['second', 'minute', 'hour', 'day']

class Misc(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis: typing.Dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis
        self.loading = self.emojis['loading']

    async def on_message(self, message: discord.Message):
        if message.content == f'<@!{self.bot.user.id}>': await self.sendGuideMessage(message) #See if this will work in Disguard.py
        try:
            if (await utility.get_server(message.guild)).get('jumpContext') and message.content: await self.jump_link_quote_context(message)
        except AttributeError: pass

    async def jump_link_quote_context(self, message: discord.Message):
        matches = re.findall(r'^https:\/\/(?:canary\.)?discord(?:app)?\.com\/channels\/\d+\/\d+\/\d+$', message.content)
        for match in matches:
            context = await self.bot.get_context(message)
            messageConverter = commands.MessageConverter()
            result = await messageConverter.convert(context, match)
            if not result: return
            if result.channel.is_nsfw() and not message.channel.is_nsfw():
                return await message.channel.send(f'[Jump Context] {self.emojis["alert"]} | This message links to a NSFW channel, so I can\'t reshare the message')
            if result.embeds and not message.author.bot:
                if not result.embeds[0].footer.text: result.embeds[0].set_footer(text=f'{(result.created_at + datetime.timedelta(hours=await utility.time_zone(message.guild))):%b %d, %Y - %I:%M %p} {await utility.name_zone(message.guild)}')
                if not result.embeds[0].author.name: result.embeds[0].set_author(name=result.author.name, icon_url=result.author.avatar.url)
                return await message.channel.send(content=result.content, embed=result.embeds[0])
            else:
                embed=discord.Embed(description=result.content)
                embed.set_footer(text=f'{(result.created_at + datetime.timedelta(hours=await utility.time_zone(message.guild))):%b %d, %Y • %I:%M %p} {await utility.name_zone(message.guild)}')
                embed.set_author(name=result.author.name, icon_url=result.author.avatar.url)
                if len(result.attachments) > 0 and result.attachments[0].height is not None:
                    try: embed.set_image(url=result.attachments[0].url)
                    except: pass
                return await message.channel.send(embed=embed)
                
    async def sendGuideMessage(self, message: discord.Message):
        await message.channel.send(embed=discord.Embed(title=f'Quick Guide - {message.guild}', description=f'Yes, I am online! Ping: {round(self.bot.latency * 1000)}ms\n\n**Prefix:** `{await utility.prefix(message.guild)}`\n\nHave a question or a problem? Use the `/ticket` command to open a support ticket with my developer, or [click to join my support server](https://discord.com/invite/xSGujjz)', color=yellow[1]))
    
    @commands.hybrid_command()
    async def privacy(self, ctx: commands.Context):
        '''
        View and edit your privacy settings
        '''
        user = await utility.get_user(ctx.author)
        # users = await database.GetUserCollection()
        privacy = user['privacy']
        prefix = await utility.prefix(ctx.guild) if ctx.guild else '.'
        def slideToggle(i): return self.emojis['slideToggleOff'] if i == 0 else self.emojis['slideToggleOn'] if i == 1 else slideToggle(privacy['default'][0]) #Uses recursion to use default value if specific setting says to
        def viewerEmoji(i): return '🔒' if i == 0 else '🔓' if i == 1 else viewerEmoji(privacy['default'][1]) if i == 2 else self.emojis['members']
        def viewerText(i): return 'only you' if i == 0 else 'everyone you share a server with' if i == 1 else viewerText(privacy['default'][1]) if i == 2 else f'{len(i)} users'
        def enabled(i): return False if i == 0 else True if i == 1 else enabled(privacy['default'][0])
        #embed = discord.Embed(title=f'Privacy Settings » {ctx.author.name} » Overview', color=user['profile'].get('favColor') or yellow[user['profile']['color_theme']])
        embed = discord.Embed(title=f'Privacy Settings » {ctx.author.name} » Overview', color=yellow[1])
        embed.description = f'''To view Disguard's privacy policy, [click here](https://disguard.netlify.app/privacybasic)\nTo view and edit all settings, visit your profile on my [web dashboard](http://disguard.herokuapp.com/manage/profile)'''
        embed.add_field(name='Default Settings', value=f'''{slideToggle(privacy['default'][0])}Allow Disguard to use your customization settings for its features: {"Enabled" if enabled(privacy['default'][0]) else "Disabled"}\n{viewerEmoji(privacy['default'][1])}Default visibility of your customization settings: {viewerText(privacy['default'][1])}''', inline=False)
        embed.add_field(name='Personal Profile Features', value=f'''{slideToggle(privacy['profile'][0])}{"Enabled" if enabled(privacy['profile'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['profile'][1])}Personal profile features: Visible to {viewerText(privacy['profile'][1])}" if enabled(privacy['profile'][0]) else ""}''', inline=False)
        embed.add_field(name='Birthday Module Features', value=f'''{slideToggle(privacy['birthdayModule'][0])}{"Enabled" if enabled(privacy['birthdayModule'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['birthdayModule'][1])}Birthday profile features: Visible to {viewerText(privacy['birthdayModule'][1])}" if enabled(privacy['birthdayModule'][0]) else ""}''', inline=False)
        embed.add_field(name='Attribute History', value=f'''{slideToggle(privacy['attributeHistory'][0])}{"Enabled" if enabled(privacy['attributeHistory'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['attributeHistory'][1])}Attribute History: Visible to {viewerText(privacy['attributeHistory'][1])}" if enabled(privacy['attributeHistory'][0]) else ""}''', inline=False)
        m = await ctx.send(embed=embed)

    @commands.hybrid_command(description='Pause the logging or antispam module for a specified duration')
    @commands.has_guild_permissions(manage_guild=True)
    async def pause(self, ctx: commands.Context, module: str, seconds: typing.Optional[int] = 0):
        '''Pause the logging or antispam module
        --------------------------------------
        parameters:
        module: str
            The module to pause
        seconds: int, optional
            The duration (in seconds) to pause the module for. If omitted, pause indefinitely until manually resumed
        '''
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        status = await ctx.send(f'{self.emojis["loading"]}Pausing...')
        server_data = await utility.get_server(ctx.guild)
        defaultChannel = self.bot.get_channel(server_data['cyberlog']['defaultChannel'])
        if not defaultChannel:
            defaultChannel = self.bot.get_channel(server_data['antispam']['log'][1])
            if not defaultChannel:
                defaultChannel = ctx.channel
        if module == 'logging':
            key = 'cyberlog'
        if module == 'antispam':
            key = 'antispam'
        seconds = self.ParsePauseDuration(seconds)
        duration = datetime.timedelta(seconds = seconds)
        if seconds > 0: 
            rawUntil = datetime.datetime.utcnow() + duration
            until = rawUntil + await utility.time_zone(ctx.guild)
        else: 
            rawUntil = datetime.datetime.max
            until = datetime.datetime.max
        embed = discord.Embed(
            title=f'The {module[0].upper()}{module[1:]} module was paused',
            description=textwrap.dedent(f'''
                👮‍♂️Moderator: {ctx.author.mention} ({ctx.author.name})
                {utility.clockEmoji(datetime.datetime.now() + datetime.timedelta(hours=await utility.time_zone(ctx.guild)))}Paused at: {utility.DisguardIntermediateTimestamp(datetime.datetime.now())}
                ⏰Paused until: {'Manually resumed' if seconds == 0 else f"{utility.DisguardIntermediateTimestamp(until)} ({utility.DisguardRelativeTimestamp(until)})"}
                '''),
            color=yellow[await utility.color_theme(ctx.guild)])
        url = cyber.imageToURL(ctx.author.avatar)
        embed.set_thumbnail(url=url)
        embed.set_author(name=ctx.author.name, icon_url=url)
        await status.edit(content=None, embed=embed)
        await database.PauseMod(ctx.guild, key)
        # self.bot.lightningLogging[ctx.guild.id][key]['enabled'] = False
        pauseTimedEvent = {'type': 'pause', 'target': key, 'server': ctx.guild.id}
        if seconds == 0: return #If the duration is infinite, we don't wait
        await database.AppendTimedEvent(ctx.guild, pauseTimedEvent)
        await asyncio.sleep(duration)
        await database.ResumeMod(ctx.guild, key)
        # self.bot.lightningLogging[ctx.guild.id][key]['enabled'] = True
        embed.title = f'The {module[0].upper()}{module[1:]} module was resumed'
        embed.description = ''
        await status.edit(embed=embed)
        
    @commands.hybrid_command(description='Resume the logging or antispam module')
    async def unpause(self, ctx: commands.Context, module: str):
        '''Resume the logging or antispam module
        ---------------------------------------
        parameters:
        module: str
            The module to resume
        '''
        if module == 'antispam':
            await database.ResumeMod(ctx.guild, 'antispam')
            # self.bot.lightningLogging[ctx.guild.id]['antispam']['enabled'] = True
            await ctx.send("✅Successfully resumed antispam moderation")
        elif module == 'logging':
            await database.ResumeMod(ctx.guild, 'cyberlog')
            # self.bot.lightningLogging[ctx.guild.id]['cyberlog']['enabled'] = True
            await ctx.send("✅Successfully resumed logging")
    @pause.autocomplete('module')
    @unpause.autocomplete('module')
    async def unpause_autocomplete(self, interaction: discord.Interaction, argument: str):
        options = ['logging', 'antispam']
        return [app_commands.Choice(name=mod, value=mod) for mod in options if argument.lower() in mod]

    @commands.hybrid_command(description='View a member\'s avatar, username, or custom status history')
    async def history(self, ctx: commands.Context, target: typing.Optional[discord.Member] = None, mod: str = ''):
        '''Viewer for custom status, username, and avatar history
        •If no member is provided, it will default to the command author
        •If no module is provided, it will default to the homepage'''
        if target is None: target = ctx.author
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        p = await utility.prefix(ctx.guild)
        embed=discord.Embed(color=yellow[await utility.color_theme(ctx.guild)])
        if not await cyber.privacyEnabledChecker(target, 'default', 'attributeHistory'):
            if await cyber.privacyVisibilityChecker(target, 'default', 'attributeHistory'):
                embed.title = 'Attribute History » Feature Disabled' 
                embed.description = f'{target.name} has disabled their attribute history' if target.id != ctx.author.id else 'You have disabled your attribute history'
            else:
                if not ctx.guild and target.id != ctx.author.id:
                    embed.title = 'Attribute History » Access Restricted' 
                    embed.description = f'{target.name} has privated their attribute history' if target.id != ctx.author.id else 'You have privated your attribute history. Use this command in DMs to access it.'
            return await ctx.send(embed=embed)
        letters = [letter for letter in ('🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿')]
        def navigationCheck(r: discord.Reaction, u: discord.User): return str(r) in navigationList and u.id == ctx.author.id and r.message.id == message.id
        async def viewerAbstraction():
            e = copy.deepcopy(embed)
            if not await cyber.privacyEnabledChecker(target, 'attributeHistory', f'{mod}History'):
                e.description = f'{target.name} has disabled their {mod} history feature' if target != ctx.author else f'You have disabled your {mod} history.'
                return e, []
            if not await cyber.privacyVisibilityChecker(target, 'attributeHistory', f'{mod}History'):
                e.description = f'{target.name} has privated their {mod} history feature' if target != ctx.author else f'You have privated your {mod} history. Use this command in DMs to access it.'
                return e, []
            e.description = ''
            tailMappings = {'avatar': 'imageURL', 'username': 'name', 'customStatus': 'name'}
            backslash = '\\'
            data = (await utility.get_user(target)).get(f'{mod}History')
            e.description = f'{len(data) if len(data) < 19 else 19} / {len(data)} entries shown; oldest on top'
            if mod == 'avatar': e.description += '\nTo set an entry as the embed thumbnail, react with that letter'
            if mod == 'customStatus': e.description += '\nTo set a custom emoji as the embed thumbnail, react with that letter'
            for i, entry in enumerate(data[-19:]): #first twenty entries because that is the max number of reactions
                if i > 0:
                    span = entry.get('timestamp') - prior.get('timestamp')
                    hours, minutes, seconds = span.seconds // 3600, (span.seconds // 60) % 60, span.seconds - (span.seconds // 3600) * 3600 - ((span.seconds // 60) % 60) * 60
                    times = [seconds, minutes, hours, span.days]
                    distanceDisplay = []
                    for j in range(len(times) - 1, -1, -1):
                        if times[j] != 0: distanceDisplay.append(f'{times[j]} {units[j]}{"s" if times[j] != 1 else ""}')
                    if len(distanceDisplay) == 0: distanceDisplay = ['0 seconds']
                prior = entry
                timestampString = f'{utility.DisguardIntermediateTimestamp(entry.get("timestamp") - datetime.timedelta(hours=utility.daylightSavings()))}'
                if mod in ('avatar', 'customStatus'): timestampString += f' {"• " + (backslash + letters[i]) if mod == "avatar" or (mod == "customStatus" and entry.get("emoji") and len(entry.get("emoji")) > 1) else ""}'
                e.add_field(name=timestampString if i == 0 else f'**{distanceDisplay[0]} later** • {timestampString}', value=f'''> {entry.get("emoji") if entry.get("emoji") and len(entry.get("emoji")) == 1 else f"[Custom Emoji]({entry.get('emoji')})" if entry.get("emoji") else ""} {entry.get(tailMappings.get(mod)) if entry.get(tailMappings.get(mod)) else ""}''', inline=False)
            headerTail = f'{"🏠 Home" if mod == "" else "🖼 Avatar History" if mod == "avatar" else "📝 Username History" if mod == "username" else "💭 Custom Status History"}'
            header = f'📜 Attribute History / 👮 / {headerTail}'
            header = f'📜 Attribute History / 👮 {target.name:.{63 - len(header)}} / {headerTail}'
            footerText = 'Data from June 10, 2020 and on'
            e.set_footer(text=footerText)
            e.title = header
            return e, data[-19:]
        while not self.bot.is_closed():
            embed=discord.Embed(color=yellow[await utility.color_theme(ctx.guild)])
            if any(attempt in mod.lower() for attempt in ['avatar', 'picture', 'pfp']): mod = 'avatar'
            elif any(attempt in mod.lower() for attempt in ['name']): mod = 'username'
            elif any(attempt in mod.lower() for attempt in ['status', 'emoji', 'presence', 'quote']): mod = 'customStatus'
            elif mod != '': 
                members = await utility.FindMoreMembers(ctx.guild.members, mod)
                members.sort(key = lambda x: x.get('check')[1], reverse=True)
                if len(members) == 0: return await ctx.send(embed=discord.Embed(description=f'Unknown history module type or invalid user \"{mod}\"\n\nUsage: `{"." if ctx.guild is None else p}history |<member>| |<module>|`\n\nSee the [help page](https://disguard.netlify.app/history.html) for more information'))
                target = members[0].get('member')
                mod = ''
            headerTail = f'{"🏠 Home" if mod == "" else "🖼 Avatar History" if mod == "avatar" else "📝 Username History" if mod == "username" else "💭 Custom Status History"}'
            header = f'📜 Attribute History / 👮 / {headerTail}'
            header = f'📜 Attribute History / 👮 {target.name:.{63 - len(header)}} / {headerTail}'
            embed.title = header
            navigationList = ['🖼', '📝', '💭']
            if mod == '':
                try: await message.clear_reactions()
                except UnboundLocalError: pass
                embed.description=f'Welcome to the attribute history viewer! Currently, the following options are available:\n🖼: Avatar History (`{p}history avatar`)\n📝: Username History(`{p}history username`)\n💭: Custom Status History(`{p}history status`)\n\nReact with your choice to enter the respective module'
                try: await message.edit(embed=embed)
                except UnboundLocalError: message = await ctx.send(embed=embed)
                for emoji in navigationList: await message.add_reaction(emoji)
                result = await self.bot.wait_for('reaction_add', check=navigationCheck)
                if str(result[0]) == '🖼': mod = 'avatar'
                elif str(result[0]) == '📝': mod = 'username'
                elif str(result[0]) == '💭': mod = 'customStatus'
            newEmbed, data = await viewerAbstraction()
            try: await message.edit(embed=newEmbed)
            except UnboundLocalError: message = await ctx.send(embed=newEmbed)
            await message.clear_reactions()
            navigationList = ['🏠']
            if mod == 'avatar': navigationList += letters[:len(data)]
            if mod == 'customStatus':
                for letter in letters[:len(data)]:
                    if newEmbed.fields[letters.index(letter)].name.endswith(letter): navigationList.append(letter)
            for emoji in navigationList: await message.add_reaction(emoji)
            cache = '' #Stores last letter reaction, if applicable, to remove reaction later on
            while mod != '':
                result = await self.bot.wait_for('reaction_add', check=navigationCheck)
                if str(result[0]) == '🏠': mod = ''
                else: 
                    value = newEmbed.fields[letters.index(str(result[0]))].value
                    newEmbed.set_thumbnail(url=value[value.find('>')+1:].strip() if mod == 'avatar' else value[value.find('(')+1:value.find(')')])
                    headerTail = '🏠 Home' if mod == '' else '🖼 Avatar History' if mod == 'avatar' else '📝 Username History' if mod == 'username' else '💭 Custom Status History'
                    header = f'📜 Attribute History / 👮 / {headerTail}'
                    header = f'📜 Attribute History / 👮 {target.name:.{50 - len(header)}} / {headerTail}'
                    newEmbed.title = header
                    if cache: await message.remove_reaction(cache, result[1])
                    cache = str(result[0])
                    await message.edit(embed=newEmbed)
    
    @commands.hybrid_command()
    @commands.guild_only()
    @commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
    async def say(self, ctx: commands.Context, member: discord.Member = None, channel: discord.TextChannel = None, *, message: str = 'Hello World'):
        '''
        Create a temporary webhook to mimic <member> by sending <message> in <channel>
        Parameters
        ----------
        member : discord.Member, optional
            The member to imitate, defaults to yourself
        channel : discord.TextChannel, optional
            The channel to send the message in, defaults to the current channel
        message : str, optional
            The message to send, defaults to "Hello World"
        '''
        if not channel: channel = ctx.channel
        if not member: member = ctx.author
        webhook = await channel.create_webhook(name='automationSayCommand', avatar=await member.avatar.with_static_format('png').read(), reason=f'Initiated by {ctx.author.name} to imitate {member.name} by saying "{message}"')
        await webhook.send(message, username=member.name)
        await ctx.interaction.response.pong()
        await webhook.delete()
    
    def ParsePauseDuration(self, s: str):
        '''Convert a string into a number of seconds to ignore antispam or logging'''
        args = s.split(' ')                             #convert string into a list, separated by space
        duration = 0                                    #in seconds
        for a in args:                                  #loop through words
            number = ""                                 #each int is added to the end of a number string, to be converted later
            for b in a:                                 #loop through each character in a word
                try:
                    c = int(b)                          #attempt to convert the current character to an int
                    number+=str(c)                      #add current int, in string form, to number
                except ValueError:                      #if we can't convert character to int... parse the current word
                    if b.lower() == "m":                #Parsing minutes
                        duration+=60*int(number)
                    elif b.lower() == "h":              #Parsing hours
                        duration+=60*60*int(number)
                    elif b.lower() == "d":              #Parsing days
                        duration+=24*60*60*int(number)
        return duration                                 #return the total duration in seconds

def clean(s: str):
    return re.sub(r'[^\w\s]', '', s.lower())

async def setup(bot: commands.Bot):
    await bot.add_cog(Misc(bot))
