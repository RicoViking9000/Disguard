'''Contains code relating to various bonus/extra features of Disguard
This will initially only contain the Easter/April Fools Day events code, but over time will be expanded to include things that don't belong in other files
'''

import discord
import secure
from discord.ext import commands, tasks
from discord import app_commands
import database
import lightningdb
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
        if message.content == f'<@{self.bot.user.id}>': await self.sendGuideMessage(message) #See if this will work in Disguard.py
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
                if not result.embeds[0].author.name: result.embeds[0].set_author(name=result.author.display_name, icon_url=result.author.display_avatar.url)
                return await message.channel.send(content=result.content, embed=result.embeds[0])
            else:
                embed=discord.Embed(description=result.content)
                embed.set_footer(text=f'{(result.created_at + datetime.timedelta(hours=await utility.time_zone(message.guild))):%b %d, %Y • %I:%M %p} {await utility.name_zone(message.guild)}')
                embed.set_author(name=result.author.display_name, icon_url=result.author.display_avatar.url)
                if len(result.attachments) > 0 and result.attachments[0].height is not None:
                    try: embed.set_image(url=result.attachments[0].url)
                    except: pass
                return await message.channel.send(embed=embed)
                
    async def sendGuideMessage(self, message: discord.Message):
        await message.channel.send(embed=discord.Embed(
            title=f'Quick Guide - {message.guild}',
            description=f'Yes, I am online! Ping: {round(self.bot.latency * 1000)}ms\n\n**Commands:** Slash commands preferred, but this server\'s prefix is `{await utility.prefix(message.guild)}`\n\nHave a question or a problem? Use the `/ticket` command to open a support ticket with my developer, or [click to join my support server](https://discord.com/invite/xSGujjz)',
            color=yellow[1]))

    @commands.hybrid_command(aliases=['config', 'configuration'])
    async def view_configuration(self, ctx: commands.Context):
        '''View Disguard's setup configuration for your server'''
        g = ctx.guild
        config = await utility.get_server(ctx.guild)
        cyberlog = config.get('cyberlog')
        antispam = config.get('antispam')
        baseURL = f'http://disguard.herokuapp.com/manage/{ctx.guild.id}'
        green = self.emojis['online']
        red = self.emojis['dnd']
        embed=discord.Embed(title=f'Server Configuration - {g}', color=yellow[await utility.color_theme(ctx.guild)])
        embed.description=textwrap.dedent(f'''
            **Prefix:** `{config.get("prefix")}`\n
            ⚙ General Server Settings [(Edit full settings on web dashboard)]({baseURL}/server)
            > Time zone: {config.get("tzname")} ({discord.utils.utcnow() + datetime.timedelta(hours=config.get("offset")):%I:%M %p})
            > {red if config.get("birthday") == 0 else green}Birthday announcements: {"<Disabled>" if config.get("birthday") == 0 else f"Announce daily to {self.bot.get_channel(config.get('birthday')).mention} at {config.get('birthdate'):%I:%M %p}"}
            > {red if not config.get("jumpContext") else green}Send embed for posted jump URLs: {"Enabled" if config.get("jumpContext") else "Disabled"}
            🔨Antispam [(Edit full settings)]({baseURL}/antispam)
            > {f"{green}Antispam: Enabled" if antispam.get("enabled") else f"{red}Antispam: Disabled"}
            > ℹMember warnings: {antispam.get("warn")}; after losing warnings: {"Nothing" if antispam.get("action") == 0 else f"Automute for {antispam.get('muteTime') // 60} minute(s)" if antispam.get("action") == 1 else "Kick" if antispam.get("action") == 2 else "Ban" if antispam.get("action") == 3 else f"Give role {g.get_role(antispam.get('customRoleID'))} for {antispam.get('muteTime') // 60} minute(s)"}
            📜 Logging [(Edit full settings)]({baseURL}/cyberlog)
            > {f"{green}Logging: Enabled" if cyberlog.get("enabled") else f"{red}Logging: Disabled"}
            > ℹDefault log channel: {self.bot.get_channel(cyberlog.get("defaultChannel")).mention if self.bot.get_channel(cyberlog.get("defaultChannel")) else "<Not configured>" if not cyberlog.get("defaultChannel") else "<Invalid channel>"}
        ''')
        await ctx.send(embed=embed)
    
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
            rawUntil = discord.utils.utcnow() + duration
            until = rawUntil + await utility.time_zone(ctx.guild)
        else: 
            rawUntil = datetime.datetime.max
            until = datetime.datetime.max
        embed = discord.Embed(
            title=f'The {module[0].upper()}{module[1:]} module was paused',
            description=textwrap.dedent(f'''
                👮‍♂️Moderator: {ctx.author.mention} ({ctx.author.display_name})
                {utility.clockEmoji(discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(ctx.guild)))}Paused at: {utility.DisguardIntermediateTimestamp(discord.utils.utcnow())}
                ⏰Paused until: {'Manually resumed' if seconds == 0 else f"{utility.DisguardIntermediateTimestamp(rawUntil)} ({utility.DisguardRelativeTimestamp(rawUntil)})"}
                '''),
            color=yellow[await utility.color_theme(ctx.guild)])
        url = cyber.imageToURL(ctx.author.display_avatar)
        embed.set_thumbnail(url=url)
        embed.set_author(name=ctx.author.display_name, icon_url=url)
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
    async def history(self, ctx: commands.Context, *, member: typing.Optional[discord.Member] = None, attribute: str = ''):
        '''
        View a member's avatar, username, or custom status history
        ----------------------------------------------------------
        Parameters
        ----------
        member : discord.Member, optional
            The member to view the history for. If omitted, defaults to the command author
        attribute : str, optional
            The attribute to view the history for. If omitted, defaults to the homepage
        '''
        # Also handle privacy settings within the other view
        # TODO - d.py 2.4: default values
        view = self.AttributeHistoryView(self.bot, ctx, member, attribute)
        await view.setup()
        return await ctx.send(embed=view.embed, view=view, ephemeral=view.private)
    @history.autocomplete('attribute')
    async def history_autocomplete(self, interaction: discord.Interaction, argument: str):
        options = ['avatar', 'username', 'display name', 'status']
        return [app_commands.Choice(name=attr, value=attr) for attr in options if argument.lower() in attr]
    
    class AttributeHistoryView(discord.ui.View):
        def __init__(self, bot: commands.Bot, ctx: commands.Context, member: typing.Optional[discord.Member] = None, attribute: str = ''):
            super().__init__()
            self.ctx = ctx
            self.bot = bot
            self.member = member
            self.attribute = attribute
            self.current_page = 0
            self.page_count: int = 0
            self.embed = None
            self.data = None
            self.private = False
            self.misc: Misc = bot.get_cog('Misc')
            self.attributes = ['avatar', 'username', 'displayname', 'status']
            self.module = f'{self.attribute}History'
            self.member_select = self.SelectAMemberDropdown()
            self.attr_select = self.SelectAnAttributeDropdown()
            self.prev_button = self.PreviousPageButton(self.misc.emojis['arrowBackward'])
            self.next_button = self.NextPageButton(self.misc.emojis['arrowForward'])
            self.add_item(self.member_select)
            self.add_item(self.attr_select)
        
        class SelectAMemberDropdown(discord.ui.UserSelect):
            def __init__(self):
                super().__init__(placeholder='Select a member to view...')
            
            async def callback(self, interaction: discord.Interaction):
                view: Misc.AttributeHistoryView = self.view
                view.member = self.values[0]
                if view.attribute:
                    result = await view.check_permissions_and_continue()
                    if result == 1:
                        view.add_item(view.EnableAttributeHistory(view.member, view.module))
                        view.add_item(view.LinkToAllSettings())
                    await interaction.response.edit_message(embed=view.embed, view=view)
                else: 
                    await interaction.response.edit_message(view=view)
        
        class SelectAnAttributeDropdown(discord.ui.Select):
            def __init__(self):
                options = [
                    discord.SelectOption(label='Avatar History', value='avatar', emoji='🖼'),
                    discord.SelectOption(label='Username History', value='username', emoji='📝'),
                    discord.SelectOption(label='Display Name History', value='displayname', emoji='📝'),
                    discord.SelectOption(label='Custom Status History', value='status', emoji='💭')
                ]
                super().__init__(placeholder='Select an attribute to view...', options=options)
            
            async def callback(self, interaction: discord.Interaction):
                try:
                    view: Misc.AttributeHistoryView = self.view
                    if view.attribute: self.options[view.attributes.index(view.attribute)].default = False
                    view.attribute = self.values[0]
                    view.module = f'{self.values[0]}History'
                    self.options[view.attributes.index(view.attribute)].default = True
                    if view.member:
                        result = await view.check_permissions_and_continue()
                        if result == 1:
                            view.add_item(view.EnableAttributeHistory(view.member, view.module))
                            view.add_item(view.LinkToAllSettings())
                        await interaction.response.edit_message(embed=view.embed, view=view)
                    else: await interaction.response.edit_message(view=view)
                except: traceback.print_exc()
        
        class SelectAnAvatarDropdown(discord.ui.Select):
            def __init__(self, data: list[str]):
                # this will need to be updated after the URL schema is updated
                super().__init__(
                    placeholder='Select an avatar to display as an image...',
                    options=[discord.SelectOption(label='Clear image', value='clear')] + [discord.SelectOption(label=f'Avatar {i+1}', value=str(i)) for i, _ in enumerate(data)]
                )
                self.data = data
                self.selected_display = 0
            
            async def callback(self, interaction: discord.Interaction):
                view: Misc.AttributeHistoryView = self.view
                self.options[self.selected_display + 1].default = False
                self.selected_display = int(self.values[0])
                view.embed.set_thumbnail(url=self.data[self.selected_display]['imageURL'] if self.values[0] != 'clear' else None)
                self.options[self.selected_display + 1].default = True
                await interaction.response.edit_message(embed=view.embed, view=view)
        
        class SelectACustomStatusDropdown(discord.ui.Select):
            def __init__(self, data: list[dict[str, str]]):
                super().__init__(
                    placeholder='Select a status emoji to display as an image...',
                    options=[discord.SelectOption(label='Clear image', value='clear')] + [discord.SelectOption(label=f'Status emoji {i+1}', value=str(i)) for i, _ in enumerate(data)]
                )
                self.data = data
                self.selected_display = 0
            
            async def callback(self, interaction: discord.Interaction):
                view: Misc.AttributeHistoryView = self.view
                self.options[self.selected_display].default = False
                self.selected_display = int(self.values[0])
                view.embed.set_thumbnail(url=self.data[self.selected_display]['emoji'] if self.values[0] != 'clear' else None)
                self.options[self.selected_display].default = True
                await interaction.response.edit_message(embed=view.embed, view=view)
        
        class PreviousPageButton(discord.ui.Button):
            def __init__(self, emoji: discord.Emoji = None):
                super().__init__(style=discord.ButtonStyle.secondary, label='Newer entries', emoji=emoji)
            
            async def callback(self, interaction: discord.Interaction):
                view: Misc.AttributeHistoryView = self.view
                view.current_page -= 1
                await view.update_display()
                await view.update_page_buttons()
                await interaction.response.edit_message(embed=view.embed, view=view)
        
        class NextPageButton(discord.ui.Button):
            def __init__(self, emoji: discord.Emoji = None):
                super().__init__(style=discord.ButtonStyle.secondary, label='Older entries', emoji=emoji)
            
            async def callback(self, interaction: discord.Interaction):
                view: Misc.AttributeHistoryView = self.view
                view.current_page += 1
                await view.update_display()
                await view.update_page_buttons()
                await interaction.response.edit_message(embed=view.embed, view=view)
        
        class EnableAttributeHistory(discord.ui.Button):
            '''Enables attribute history & opens viewer'''
            def __init__(self, user: discord.User, module: str):
                super().__init__(style=discord.ButtonStyle.blurple, label='Enable & continue')
                self.user = user
                self.module = module
            
            async def callback(self, interaction: discord.Interaction):
                view: Misc.AttributeHistoryView = self.view
                current = (await lightningdb.get_user(self.user.id)).get('privacy', {}).get(self.module, [0, 0])
                await database.patch_privacy(self.user, self.module, 1, current[1])
                await lightningdb.patch_user(self.user.id, {'privacy': {self.module: [1, current[1]]}})
                while len(view.children) > 2:
                    view.remove_item(view.children[-1])
                await view.setup()
                await interaction.response.edit_message(embed=view.embed, view=view)
        
        class LinkToAllSettings(discord.ui.Button):
            def __init__(self):
                super().__init__(style=discord.ButtonStyle.link, label='Manage all privacy settings', url='https://disguard.heroku.app/manage/profile')
        
        async def setup(self):
            self.embed = discord.Embed(title='Attribute History Viewer', color=yellow[await utility.color_theme(self.ctx.guild)])
            if self.member and self.attribute:
                result = await self.check_permissions_and_continue()
                if result in (0, 2):
                    return 0
                elif result == 1:
                    self.add_item(self.EnableAttributeHistory(self.member, self.module))
                    self.add_item(self.LinkToAllSettings())
                    return 1
            else:
                self.embed.description=f'Select a member and history attribute to view history data'
                return -1

        def update_page_buttons(self):
            '''Updates the next/previous page buttons'''
            if self.current_page == 0: self.prev_button.disabled = True
            elif self.current_page != 0 and self.prev_button.disabled: self.prev_button.disabled = False
            if self.current_page == len(self.page_count) - 1: self.next_button.disabled = True
            elif self.current_page != len(self.page_count) - 1 and self.next_button.disabled: self.next_button.disabled = False
        
        async def fetch_data(self):
            self.data = list(utility.paginate((await utility.get_user(self.member)).get(f'{self.attribute}History', []), 15))
            self.current_page = 0
            self.page_count = len(self.data)
        
        async def check_permissions_and_continue(self) -> int:
            '''
            Returns
            -------
            0: Other member has disabled attribute history
            1: Command user has disabled attribute history
            2: Other member has privated attribute history
            3: Command user has privated attribute history
            '''
            cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
            if not await cyber.privacyEnabledChecker(self.member, 'attributeHistory', self.module):
                if self.member != self.ctx.author:
                    self.embed.description = f'{self.member.global_name} has disabled their {self.attribute} history feature. Please select another member or attribute to view.'
                    return 0
                else:
                    self.embed.description = f'You have disabled your {self.attribute} history. You may use the button below to enable this feature.'
                    if not await cyber.privacyVisibilityChecker(self.member, 'attributeHistory', self.module):
                        self.private = True
                    return 1
            if not await cyber.privacyVisibilityChecker(self.member, 'attributeHistory', self.module):
                if self.member != self.ctx.author:
                    self.embed.description = f'{self.member.global_name} has privated their {self.attribute} history feature. Please select another member or attribute to view.'
                    return 2
                else:
                    self.private = True
            await self.fetch_data()
            await self.update_display()
            return 99
        
        async def update_display(self):
            self.embed.description = ''
            self.embed.clear_fields()
            while len(self.children) > 2:
                self.remove_item(self.children[-1])
            if self.attribute in ('username', 'displayname'): self.embed.set_thumbnail(url=self.member.display_avatar.url)
            tail_mappings = {'avatar': 'imageURL', 'username': 'name', 'status': 'name'}
            data = self.data[self.current_page] if self.data else []
            self.embed.description = f'{len(data) if len(data) < 15 else 15} / {len(data)} entries shown; oldest on top'
            if self.attribute == 'avatar' and self.data:
                self.embed.description += '\nTo set an entry as the embed thumbnail, use the dropdown below'
                self.add_item(self.SelectAnAvatarDropdown(data))
            elif self.attribute == 'status' and self.data:
                self.embed.description += '\nTo set a custom emoji as the embed thumbnail, use the dropdown below'
                self.add_item(self.SelectACustomStatusDropdown(data))
            for i, entry in enumerate(data):
                if i > 0:
                    delta: datetime.timedelta = entry['timestamp'] - prior['timestamp']
                    hours = delta.seconds // 3600
                    minutes = (delta.seconds // 60) % 60
                    seconds = delta.seconds - (delta.seconds // 3600) * 3600 - ((delta.seconds // 60) % 60) * 60
                    times = [seconds, minutes, hours, delta.days]
                    distanceDisplay = []
                    for j in range(len(times) - 1, -1, -1):
                        if times[j] != 0: distanceDisplay.append(f'{times[j]} {units[j]}{"s" if times[j] != 1 else ""}')
                    if len(distanceDisplay) == 0: distanceDisplay = ['0 seconds']
                prior = entry
                timestampString = f'{utility.DisguardIntermediateTimestamp(entry["timestamp"])}'
                if self.attribute in ('avatar', 'status'):
                    timestampString += f' {"• Avatar " + str(i + 1) if self.attribute == "avatar" or (self.attribute == "status" and entry["emoji"] and len(entry.get("emoji", "")) > 1) else ""}'
                self.embed.add_field(
                    name=timestampString if i == 0 else f'**{distanceDisplay[0]} later** • {timestampString}',
                    value=f'''> {entry["emoji"] if entry.get("emoji") and len(entry.get("emoji", "")) == 1 else f"[Custom Emoji]({entry.get('emoji')})" if entry.get("emoji") else ""} {entry.get(tail_mappings.get(self.attribute)) if entry.get(tail_mappings.get(self.attribute)) else ""}''',
                    inline=False
                )
            if not data: self.embed.description += '\n\nNo entries found, go make some history!'
            if self.page_count > 1:
                self.embed.description += f'\nPage {self.current_page + 1} / {self.page_count}'
                self.add_item(self.prev_button)
                self.add_item(self.next_button)
            self.embed.title = f'{self.member.global_name}\'s {self.attribute} history'
            self.embed.set_author(name=self.member.display_name, icon_url=self.member.display_avatar.url)
            return self.embed
    
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
        webhook = await channel.create_webhook(name='automationSayCommand', avatar=await member.display_avatar.with_static_format('png').read(), reason=f'Initiated by {ctx.author.display_name} to imitate {member.display_name} by saying "{message}"')
        await webhook.send(message, username=member.display_name)
        await ctx.interaction.response.pong()
        await webhook.delete()
        await ctx.send('Done!', ephemeral=True)
    
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
