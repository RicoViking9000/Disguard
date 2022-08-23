'''Contains code relating to various bonus/extra features of Disguard
This will initially only contain the Easter/April Fools Day events code, but over time will be expanded to include things that don't belong in other files
'''

import discord
import secure
from discord.ext import commands, tasks
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

yellow = (0xffff00, 0xffff66)
placeholderURL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
qlf = '  ' #Two special characters to represent quoteLineFormat
qlfc = ' '
newline = '\n'
units = ['second', 'minute', 'hour', 'day']

class Misc(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis: typing.Dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis
        self.loading = self.emojis['loading']

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.content == f'<@!{self.bot.user.id}>': await self.sendGuideMessage(message) #See if this will work in Disguard.py
        asyncio.create_task(self.jumpLinkQuoteContext(message))

    async def jumpLinkQuoteContext(self, message: discord.Message):
        try: enabled = (await utility.get_server(message.guild)).get('jumpContext')
        except AttributeError: return
        if message.author.id == self.bot.user.id: return
        if enabled:
            words = message.content.split(' ')
            for w in words:
                if 'https://discord.com/channels/' in w or 'https://canary.discord.com/channels' in w or 'https://discordapp.com/channels' in w: #This word is a hyperlink to a message
                    context = await self.bot.get_context(message)
                    messageConverter = commands.MessageConverter()
                    result = await messageConverter.convert(context, w)
                    if result is None: return
                    if result.channel.is_nsfw() and not message.channel.is_nsfw():
                        return await message.channel.send(f'{self.emojis["alert"]} | This message links to a NSFW channel, so its content can\'t be shared')
                    if len(result.embeds) == 0:
                        embed=discord.Embed(description=result.content)
                        embed.set_footer(text=f'{(result.created_at + datetime.timedelta(hours=await utility.time_zone(message.guild))):%b %d, %Y • %I:%M %p} {await utility.name_zone(message.guild)}')
                        embed.set_author(name=result.author.name, icon_url=result.author.avatar.url)
                        if len(result.attachments) > 0 and result.attachments[0].height is not None:
                            try: embed.set_image(url=result.attachments[0].url)
                            except: pass
                        return await message.channel.send(embed=embed)
                    else:
                        if result.embeds[0].footer.text is discord.Embed.Empty: result.embeds[0].set_footer(text=f'{(result.created_at + datetime.timedelta(hours=await utility.time_zone(message.guild))):%b %d, %Y - %I:%M %p} {await utility.name_zone(message.guild)}')
                        if result.embeds[0].author.name is discord.Embed.Empty: result.embeds[0].set_author(name=result.author.name, icon_url=result.author.avatar.url)
                        return await message.channel.send(content=result.content, embed=result.embeds[0])

    async def sendGuideMessage(self, message: discord.Message):
        await message.channel.send(embed=discord.Embed(title=f'Quick Guide - {message.guild}', description=f'Yes, I am online! Ping: {round(self.bot.latency * 1000)}ms\n\n**Prefix:** `{await utility.prefix(message.guild)}`\n\nHave a question or a problem? Use the `ticket` command to open a support ticket with my developer, or [click to join my support server](https://discord.com/invite/xSGujjz)', color=yellow[1]))
    
    @commands.command()
    async def privacy(self, ctx: commands.Context):
        user = await utility.get_user(ctx.author)
        users = database.GetUserCollection()
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

    @commands.command(aliases=['feedback', 'ticket'])
    async def support(self, ctx: commands.Context, *, opener=''):
        '''Command to initiate a feedback ticket. Anything typed after the command name will be used to start the support ticket
        Ticket status
        0: unopened by dev
        1: opened (dev has viewed)
        2: in progress (dev has replied)
        3: closed'''
        await ctx.trigger_typing()
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        color_theme = await utility.color_theme(ctx.guild) if ctx.guild else 1
        details = cyber.emojis['details']
        def navigationCheck(r, u): return str(r) in reactions and r.message.id == status.id and u.id == ctx.author.id
        #If the user didn't provide a message with the command, prompt them with one here
        if opener.startswith('System:'):
            specialCase = opener[opener.find(':') + 1:].strip()
            opener = ''
        else:
            specialCase = False
        if not opener:
            embed=discord.Embed(title='Disguard Support Menu', description=f"Welcome to Disguard support!\n\nIf you would easily like to get support, you may join my official server: https://discord.gg/xSGujjz\n\nIf you would like to get in touch with my developer without joining servers, react 🎟 to open a support ticket\n\nIf you would like to view your active support tickets, type `{await utility.prefix() if ctx.guild else '.'}tickets` or react {details}", color=yellow[color_theme])
            status = await ctx.send(embed=embed)
            reactions = ['🎟', details]
            for r in reactions: await status.add_reaction(r)
            result: typing.Tuple[discord.Reaction, discord.User] = await self.bot.wait_for('reaction_add', check=navigationCheck)
            if result[0].emoji == details:
                await status.delete()
                return await self.ticketsCommand(ctx)
            await ctx.send('Please type the message you would like to use to start the support thread, such as a description of your problem or a question you have')
            def ticketCreateCheck(m: discord.Message): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
            try: result2: discord.Message = await self.bot.wait_for('message', check=ticketCreateCheck, timeout=300)
            except asyncio.TimeoutError: return await ctx.send('Timed out')
            opener = result2.content
        #If the command was used in DMs, ask the user if they wish to represent one of their servers
        if not ctx.guild:
            await ctx.trigger_typing()
            serverList = [g for g in self.bot.guilds if ctx.author in g.members] + ['<Prefer not to answer>']
            if len(serverList) > 2: #If the member is in more than one server with the bot, prompt for which server they're in
                alphabet = '🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿'
                newline = '\n'
                awaitingServerSelection = await ctx.send(f'Because we\'re in DMs, please provide the server you\'re representing by reacting with the corresponding letter\n\n{newline.join([f"{alphabet[i]}: {g}" for i, g in enumerate(serverList)])}')
                possibleLetters = [l for l in alphabet if l in awaitingServerSelection.content]
                for letter in possibleLetters: await awaitingServerSelection.add_reaction(letter)
                def selectionCheck(r:discord.Reaction, u:discord.User): return str(r) in possibleLetters and r.message.id == awaitingServerSelection.id and u.id == ctx.author.id
                try: selection = await self.bot.wait_for('reaction_add', check=selectionCheck, timeout=300)
                except asyncio.TimeoutError: return await ctx.send('Timed out')
                server = serverList[alphabet.index(str(selection[0]))]
                if type(server) is str: server = None
            else: server = serverList[0]
        else: server = ctx.guild
        embed=discord.Embed(title=f'🎟 Disguard Ticket System / {self.loading} Creating Ticket...', color=yellow[color_theme])
        status = await ctx.send(embed=embed)
        #Obtain server permissions for the member to calculate their prestige (rank of power in the server)
        if server: p = server.get_member(ctx.author.id).guild_permissions
        else: p = discord.Permissions.none()
        #Create ticket dictionary (number here is a placeholder)
        ticket = {'number': ctx.message.id, 'id': ctx.message.id, 'author': ctx.author.id, 'channel': str(ctx.channel), 'server': server.id if server else None, 'notifications': True, 'prestige': 'N/A' if not server else 'Server Owner' if ctx.author.id == server.owner.id else 'Server Administrator' if p.administrator else 'Server Moderator' if p.manage_server else 'Junior Server Moderator' if p.kick_members or p.ban_members or p.manage_channels or p.manage_roles or p.manage_members else 'Server Member', 'status': 0, 'conversation': []}
        #If a ticket was created in a special manner, this system message will be the first message
        if specialCase: ticket['conversation'].append({'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{specialCase}*'})
        firstEntry = {'author': ctx.author.id, 'timestamp': datetime.datetime.utcnow(), 'message': opener}
        ticket['conversation'].append(firstEntry)
        authorMember, devMember, botMember = {'id': ctx.author.id, 'bio': 'Created this ticket', 'permissions': 2, 'notifications': True}, {'id': 247412852925661185, 'bio': 'Bot developer', 'permissions': 1, 'notifications': True}, {'id': self.bot.user.id, 'bio': 'System messages', 'permissions': 1, 'notifications': False} #2: Owner, 1: r/w, 0: r 
        ticket['members'] = [authorMember, devMember, botMember]
        try: ticketList = await database.GetSupportTickets()
        except AttributeError: ticketList = []
        ticket['number'] = len(ticketList)
        await database.CreateSupportTicket(ticket)
        whiteCheck = discord.utils.get(self.bot.get_guild(560457796206985216).emojis, name='whiteCheck')
        embed.title = f'🎟 Disguard Ticket System / {whiteCheck} Support Ticket Created!'
        embed.description = f'''Your support ticket has successfully been created\n\nTicket number: {ticket['number']}\nAuthor: {ctx.author.name}\nMessage: {opener}\n\nTo view this ticket, react 🎟 or type `{await utility.prefix(ctx.guild) if ctx.guild else "."}tickets {ticket['number']}`, which will allow you to add members to the support thread if desired, disable DM notifications, reply, and more.'''
        await status.edit(embed=embed)
        reactions = ['🎟']
        await status.add_reaction('🎟')
        devManagement = self.bot.get_channel(681949259192336406)
        await devManagement.send(embed=embed)
        result = await self.bot.wait_for('reaction_add', check=navigationCheck)
        await self.ticketsCommand(ctx, number=ticket['number'])

    @commands.command(name='tickets')
    async def ticketsCommand(self, ctx: commands.Context, number:int = -1):
        '''Command to view feedback tickets'''
        g = ctx.guild
        alphabet = [l for l in ('🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿')]
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        color_theme = await utility.color_theme(ctx.guild) if ctx.guild else 1
        trashcan = self.emojis['delete']
        statusDict = {0: 'Unopened', 1: 'Viewed', 2: 'In progress', 3: 'Closed', 4: 'Locked'}
        message = await ctx.send(embed=discord.Embed(description=f'{self.loading}Downloading ticket data'))
        tickets = await database.GetSupportTickets()
        embed=discord.Embed(title=f"🎟 Disguard Ticket System / {self.emojis['details']} Browse Your Tickets", color=yellow[color_theme])
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar.with_static_format('png').url)
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
        async def populateEmbed(pages, index, sortDescription):
            embed.clear_fields()
            embed.description = f'''{f'NAVIGATION':-^70}\n{trashcan}: Delete this embed\n{self.emojis['details']}: Adjust sort\n◀: Previous page\n🇦 - {alphabet[len(pages[index]) - 1]}: View ticket\n▶: Next page\n{f'Tickets for {ctx.author.name}':-^70}\nPage {index + 1} of {len(pages)}\nViewing {len(pages[index])} of {len(filtered)} results\nSort: {sortDescription}'''
            for i, ticket in enumerate(pages[index]):
                tg = g #probably stands for 'ticketGuild'
                if not tg and ticket['server']: tg = self.bot.get_guild(ticket['server'])
                embed.add_field(
                    name=f"{alphabet[i]}Ticket {ticket['number']}",
                    value=f'''> Members: {", ".join([self.bot.get_user(u['id']).name for i, u in enumerate(ticket['members']) if i not in (1, 2)])}\n> Status: {statusDict[ticket['status']]}\n> Latest reply: {self.bot.get_user(ticket['conversation'][-1]['author']).name} • {(ticket['conversation'][-1]['timestamp'] + datetime.timedelta(hours=(await utility.time_zone(tg) if tg else -5))):%b %d, %Y • %I:%M %p} {await utility.name_zone(tg) if tg else 'EST'}\n> {qlf}{ticket['conversation'][-1]['message']}''',
                    inline=False)
        async def notifyMembers(ticket):
            e = discord.Embed(title=f"New activity in ticket {ticket['number']}", description=f"To view the ticket, use the tickets command (`.tickets {ticket['number']}`)\n\n{'Highlighted message':-^70}", color=yellow[ticketcolor_theme])
            entry = ticket['conversation'][-1]
            messageAuthor = self.bot.get_user(entry['author'])
            e.set_author(name=messageAuthor, icon_url=messageAuthor.avatar.with_static_format('png').url)
            e.add_field(
                name=f"{messageAuthor.name} • {(entry['timestamp'] + datetime.timedelta(hours=(await utility.time_zone(tg) if tg else -5))):%b %d, %Y • %I:%M %p} {await utility.name_zone(tg) if tg else 'EST'}",
                value=f'> {entry["message"]}',
                inline=False)
            e.set_footer(text=f"You are receiving this DM because you have notifications enabled for ticket {ticket['number']}. View the ticket to disable notifications.")
            for m in ticket['members']:
                if m['notifications'] and m['id'] != entry['author']:
                    try: await self.bot.get_user(m['id']).send(embed=e)
                    except: pass
        clearReactions = True
        currentPage = 0
        sortMode = 0
        sortDescriptions = ['Recently Active (Newest first)', 'Recently Active (Oldest first)', 'Ticket Number (Descending)', 'Ticket Number (Ascending)']
        filtered = [t for t in tickets if ctx.author.id in [m['id'] for m in t['members']]]
        if len(filtered) == 0:
            embed.description = f"There are currently no tickets in the system created by or involving you. To create a feedback ticket, type `{await utility.prefix(ctx.guild) if ctx.guild else '.'}ticket`"
            return await message.edit(embed=embed)
        def optionNavigation(r: discord.Reaction, u: discord.User): return r.emoji in reactions and r.message.id == message.id and u.id == ctx.author.id and not u.bot
        def messageCheck(m: discord.Message): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
        while not self.bot.is_closed():
            filtered = [t for t in tickets if ctx.author.id in [m['id'] for m in t['members']]]
            organize(sortMode)
            pages = list(paginate(filtered, 5))
            sortDescription = sortDescriptions[sortMode]
            await populateEmbed(pages, currentPage, sortDescription)
            if number and number > len(tickets): 
                await message.edit(content=f'The ticket number you provided ({number}) is invalid. Switching to browse view.')
                number, option = None, [None]
            if number == -1 or number == None:
                if ctx.guild: 
                    if clearReactions: await message.clear_reactions()
                    else: clearReactions = True
                    await message.edit(embed=embed)
                else:
                    await message.delete()
                    message = await ctx.send(content=message.content, embed=embed)
                reactions = [trashcan, self.emojis['details'], self.emojis['arrowBackward']] + alphabet[:len(pages[currentPage])] + [self.emojis['arrowForward']]
                for r in reactions: await message.add_reaction(r)
                option = await self.bot.wait_for('reaction_add', check=optionNavigation)
                try: await message.remove_reaction(*option)
                except: pass
            else: option = [alphabet[0]]
            async def clearMessageContent():
                await asyncio.sleep(5)
                if datetime.datetime.now() > clearAt: await message.edit(content=None)
            clearAt = None
            if type(option[0]) is discord.Reaction and str(option[0]) not in alphabet[:len(pages[currentPage])]:
                if option[0].emoji == trashcan: return await message.delete()
                elif option[0].emoji == self.emojis['details']:
                    clearReactions = False
                    sortMode += 1 if sortMode != 3 else -3
                    messageContent = '--SORT MODE--\n' + '\n'.join([f'> **{d}**' if i == sortMode else f'{qlfc}{d}' for i, d in enumerate(sortDescriptions)])
                    await message.edit(content=messageContent)
                    clearAt = datetime.datetime.now() + datetime.timedelta(seconds=4)
                    asyncio.create_task(clearMessageContent())
                elif option[0].emoji in (self.emojis['arrowBackward'], self.emojis['arrowForward']):
                    if option[0].emoji == self.emojis['arrowBackward']: currentPage -= 1
                    else: currentPage += 1
                    if currentPage < 0: currentPage = 0
                    if currentPage == len(pages): currentPage = len(pages) - 1
            elif option[0] and str(option[0]) in alphabet[:len(pages[currentPage])]:
                if not number or number < 0: number = pages[currentPage][alphabet.index(str(option[0]))]['number']
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
                    back = self.emojis['arrowLeft']
                    greenCheck = self.emojis['greenCheck']
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
                    result = await self.bot.wait_for('reaction_add', check=optionNavigation)
                    if result[0].emoji == greenCheck:
                        ticket['conversation'].append({'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} accepted their invite*'})
                        member.update({'permissions': 1, 'notifications': True})
                        asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                    else:
                        if str(result[0]) == '❌':
                            ticket['members'].remove(member)
                            ticket['conversation'].append({'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} declined their invite*'})
                            asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                        number = None
                        continue
                conversationPages = list(paginate(ticket['conversation'], 7))
                currentConversationPage = len(conversationPages) - 1
                while not self.bot.is_closed():
                    embed.clear_fields()
                    server = self.bot.get_guild(ticket['server'])
                    member = [m for m in ticket['members'] if m['id'] == ctx.author.id][0]
                    memberIndex = ticket['members'].index(member)
                    tg = g
                    if not tg and ticket['server']: tg = self.bot.get_guild(ticket['server'])
                    ticketcolor_theme = self.bot.get_cog('Cyberlog').color_theme(tg) if tg else 1
                    def returnPresence(status): return self.emojis['hiddenVoiceChannel'] if status == 4 else self.emojis['online'] if status == 3 else self.emojis['idle'] if status in (1, 2) else self.emojis['dnd']
                    reactions = [self.emojis['arrowLeft'], self.emojis['members'], self.emojis['reply']]
                    reactions.insert(2, self.emojis['bell'] if not ctx.guild or not member['notifications'] else self.emojis['bellMute'])
                    conversationPages = list(paginate(ticket['conversation'], 7))
                    if len(conversationPages) > 0 and currentConversationPage != 0: reactions.insert(reactions.index(self.emojis['members']) + 2, self.emojis['arrowBackward'])
                    if len(conversationPages) > 0 and currentConversationPage != len(conversationPages) - 1: reactions.insert(reactions.index(self.emojis['reply']) + 1, self.emojis['arrowForward'])
                    if member['permissions'] == 0: reactions.remove(self.emojis['reply'])
                    if ctx.author.id == 247412852925661185: reactions.append(self.emojis['hiddenVoiceChannel'])
                    embed.title = f'🎟 Disguard Ticket System / Ticket {number}'
                    embed.description = f'''{'TICKET DATA':-^70}\n{self.emojis['member']}Author: {self.bot.get_user(ticket['author'])}\n⭐Prestige: {ticket['prestige']}\n{self.emojis['members']}Other members involved: {', '.join([self.bot.get_user(u["id"]).name for u in ticket['members'] if u["id"] not in (247412852925661185, self.bot.user.id, ctx.author.id)]) if len(ticket['members']) > 3 else f'None - react {self.emojis["members"]} to add'}\n⛓Server: {self.bot.get_guild(ticket['server'])}\n{returnPresence(ticket['status'])}Dev visibility status: {statusDict.get(ticket['status'])}\n{self.emojis['bell'] if member['notifications'] else self.emojis['bellMute']}Notifications: {member['notifications']}\n\n{f'CONVERSATION - {self.emojis["reply"]} to reply' if member['permissions'] > 0 else 'CONVERSATION':-^70}\nPage {currentConversationPage + 1} of {len(conversationPages)}{f'{newline}{self.emojis["arrowBackward"]} and {self.emojis["arrowForward"]} to navigate' if len(conversationPages) > 1 else ''}\n\n'''
                    for entry in conversationPages[currentConversationPage]: embed.add_field(name=f"{self.bot.get_user(entry['author']).name} • {(entry['timestamp'] + datetime.timedelta(hours=(await utility.time_zone(tg) if tg else -4))):%b %d, %Y • %I:%M %p} {await utility.name_zone(tg) if tg else 'EST'}", value=f'> {entry["message"]}', inline=False)
                    if ctx.guild: 
                        if clearReactions: await message.clear_reactions()
                        else: clearReactions = True
                        await message.edit(content=None, embed=embed)
                    else:
                        await message.delete()
                        message = await ctx.send(embed=embed)
                    for r in reactions: await message.add_reaction(r)
                    result: typing.Tuple[discord.Reaction, discord.User] = await self.bot.wait_for('reaction_add', check=optionNavigation)
                    if result[0].emoji == self.emojis['arrowLeft']:
                        number = None #deselect the ticket
                        break
                    elif result[0].emoji == self.emojis['hiddenVoiceChannel']:
                        ticket['status'] = 3
                        ticket['conversation'].append({'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*My developer has closed this support ticket. If you still need assistance on this matter, you may reopen it by responding to it. Otherwise, it will silently lock in 7 days.*'})
                        await notifyMembers(ticket)
                    elif result[0].emoji in (self.emojis['arrowBackward'], self.emojis['arrowForward']):
                        if result[0].emoji == self.emojis['arrowBackward']: currentConversationPage -= 1
                        else: currentConversationPage += 1
                        if currentConversationPage < 0: currentConversationPage = 0
                        if currentConversationPage == len(conversationPages): currentConversationPage = len(conversationPages) - 1
                    elif result[0].emoji == self.emojis['members']:
                        embed.clear_fields()
                        permissionsDict = {0: 'View ticket', 1: 'View and respond to ticket', 2: 'Ticket Owner (View, Respond, Manage Sharing)', 3: 'Invite sent'}
                        memberResults = []
                        while not self.bot.is_closed():
                            def calculateBio(m): 
                                return '(No description)' if type(m) is not discord.Member else "Server Owner" if server.owner.id == m.id else "Server Administrator" if m.guild_permissions.administrator else "Server Moderator" if m.guild_permissions.manage_guild else "Junior Server Moderator" if m.guild_permissions.manage_roles or m.guild_permissions.manage_channels else '(No description)'
                            if len(memberResults) == 0: staffMemberResults = [m for m in server.members if any([m.guild_permissions.administrator, m.guild_permissions.manage_guild, m.guild_permissions.manage_channels, m.guild_permissions.manage_roles, m.id == server.owner.id]) and not m.bot and m.id not in [mb['id'] for mb in ticket['members']]][:15]
                            memberFillerText = [f'{self.bot.get_user(u["id"])}{newline}> {u["bio"]}{newline}> Permissions: {permissionsDict[u["permissions"]]}' for u in ticket['members']]
                            embed.description = f'''**__{'TICKET SHARING SETTINGS':-^85}__\n\n{'Permanently included':-^40}**\n{newline.join([f'👤{f}' for f in memberFillerText[:3]])}'''
                            embed.description += f'''\n\n**{'Additional members':-^40}**\n{newline.join([f'{self.emojis["member"]}{f}{f"{newline}> {alphabet[i]} to manage" if ctx.author.id == ticket["author"] else ""}' for i, f in enumerate(memberFillerText[3:])]) if len(memberFillerText) > 2 else 'None yet'}'''
                            if ctx.author.id == ticket['author']: embed.description += f'''\n\n**{'Add a member':-^40}**\nSend a message to search for a member to add, then react with the corresponding letter to add them{f'{newline}{newline}Moderators of {self.bot.get_guild(ticket["server"])} are listed below as suggestions. You may react with the letter next to their name to quickly add them, otherwise send a message to search for someone else' if ticket['server'] and len(staffMemberResults) > 0 else ''}'''
                            reactions = [self.emojis['arrowLeft']]
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
                            d, p = await asyncio.wait([self.bot.wait_for('reaction_add', check=optionNavigation), self.bot.wait_for('message', check=messageCheck)], return_when=asyncio.FIRST_COMPLETED)
                            try: result = d.pop().result()
                            except: pass
                            for f in p: f.cancel()
                            if type(result) is tuple: #Meaning a reaction, rather than a message search
                                if str(result[0]) in alphabet:
                                    if not embed.description[embed.description.find(str(result[0])) + 2:].startswith('to manage'):
                                        addMember = memberResults[alphabet.index(str(result[0]))]
                                        invite = discord.Embed(title='🎟 Invited to ticket', description=f"Hey {addMember.name},\n{ctx.author.name} has invited you to **support ticket {ticket['number']}** with [{', '.join([self.bot.get_user(m['id']).name for i, m in enumerate(ticket['members']) if i not in (1, 2)])}].\n\nThe Disguard support ticket system is a tool for server members to easily get in touch with my developer for issues, help, and questions regarding the bot\n\nTo join the support ticket, type `.tickets {ticket['number']}`", color=yellow[ticketcolor_theme])
                                        invite.set_footer(text=f'You are receiving this DM because {ctx.author} invited you to a Disguard support ticket')
                                        try: 
                                            await addMember.send(embed=invite)
                                            ticket['members'].append({'id': addMember.id, 'bio': calculateBio(addMember), 'permissions': 3, 'notifications': False})
                                            ticket['conversation'].append({'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} invited {addMember} to the ticket*'})
                                            memberResults.remove(addMember)
                                        except Exception as e: await ctx.send(f'Error inviting {addMember} to ticket: {e}.\n\nBTW, error code 50007 means that the recipient disabled DMs from server members - they will need to temporarily allow this in the `Server Options > Privacy Settings` or `User Settings > Privacy & Safety` in order to be invited')
                                    else:
                                        user = self.bot.get_user([mb['id'] for mb in ticket['members']][2 + len([l for l in alphabet if l in embed.description])]) #Offset - the first three members in the ticket are permanent
                                        while not self.bot.is_closed():
                                            if ctx.author.id != ticket['author']: break #If someone other than the ticket owner gets here, deny them
                                            ticketUser = [mb for mb in ticket['members'] if mb['id'] == user.id][0]
                                            embed.description=f'''**{f'Manage {user.name}':-^70}**\n{'🔒' if not ctx.guild or ticketUser['permissions'] == 0 else '🔓'}Permissions: {permissionsDict[ticketUser['permissions']]}\n\n{self.emojis['details']}Responses: {len([r for r in ticket['conversation'] if r['author'] == user.id])}\n\n{f'{self.emojis["bell"]}Notifications: True' if ticketUser['notifications'] else f'{self.emojis["bellMute"]}Notifications: False'}\n\n❌: Remove this member'''
                                            reactions = [self.emojis['arrowLeft'], '🔓' if ctx.guild and ticketUser['permissions'] == 0 else '🔒', '❌'] #The reason we don't use the unlock if the command is used in DMs is because we can't remove user reactions ther
                                            if ctx.guild: 
                                                if clearReactions: await message.clear_reactions()
                                                else: clearReactions = True
                                                await message.edit(content=None, embed=embed)
                                            else:
                                                await message.delete()
                                                message = await ctx.send(embed=embed)
                                            for r in reactions: await message.add_reaction(r)
                                            result = await self.bot.wait_for('reaction_add', check=optionNavigation)
                                            if result[0].emoji == self.emojis['arrowLeft']: break
                                            elif str(result[0]) == '❌':
                                                ticket['members'] = [mbr for mbr in ticket['members'] if mbr['id'] != user.id]
                                                ticket['conversation'].append({'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} removed {user} from the ticket*'})
                                                break
                                            else:
                                                if str(result[0]) == '🔒':
                                                    if ctx.guild: reactions = [self.emojis['arrowLeft'], '🔓', '❌']
                                                    else: clearReactions = False
                                                    ticketUser['permissions'] = 0
                                                else:
                                                    if ctx.guild: reactions = [self.emojis['arrowLeft'], '🔒', '❌']
                                                    else: clearReactions = False
                                                    ticketUser['permissions'] = 1
                                                ticket['conversation'].append({'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} updated {ticketUser}\'s permissions to `{permissionsDict[ticketUser["permissions"]]}`*'})
                                                ticket['members'] = [m if m['id'] != user.id else ticketUser for m in ticket['members']]
                                            asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                                elif str(result[0]) == '🚪':
                                    ticket['members'] = [mbr for mbr in ticket['members'] if mbr['id'] != ctx.author.id]
                                    ticket['conversation'].append({'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{ctx.author.name} left the ticket*'})
                                    await message.delete()
                                    asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                                    return await self.ticketsCommand(ctx)
                                else: break
                            else:
                                try: 
                                    cyber.AvoidDeletionLogging(result)
                                    await result.delete()
                                except: pass
                                memberResults = (await self.bot.get_cog('Cyberlog').FindMoreMembers([u for u in self.bot.users if any([u.id in [m.id for m in s.members] for s in self.bot.guilds])], result.content))[:15]
                                memberResults.sort(key = lambda x: x.get('check')[1], reverse=True)
                                memberResults = [r['member'] for r in memberResults if r['member'].id not in [m['id'] for m in ticket['members']]]
                                staffMemberResults = []
                            asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
                    elif result[0].emoji == self.emojis['reply']:
                        embed.description = f'**__Please type your response (under 1024 characters) to the conversation, or react {self.emojis["arrowLeft"]} to cancel__**'
                        reactions = [self.emojis['arrowLeft']]
                        if ctx.guild: 
                            if clearReactions: await message.clear_reactions()
                            else: clearReactions = True
                            await message.edit(content=None, embed=embed)
                        else:
                            await message.delete()
                            message = await ctx.send(embed=embed)
                        for r in reactions: await message.add_reaction(r)
                        d, p = await asyncio.wait([self.bot.wait_for('reaction_add', check=optionNavigation), self.bot.wait_for('message', check=messageCheck)], return_when=asyncio.FIRST_COMPLETED)
                        try: result = d.pop().result()
                        except: pass
                        for f in p: f.cancel()
                        if type(result) is discord.Message:
                            try: 
                                cyber.AvoidDeletionLogging(result)
                                await result.delete()
                            except: pass
                            ticket['conversation'].append({'author': ctx.author.id, 'timestamp': datetime.datetime.utcnow(), 'message': result.content})
                            if ticket['status'] != 2: ticket['status'] = 2
                            conversationPages = list(paginate(ticket['conversation'], 7))
                            if len(ticket['conversation']) % 7 == 1 and len(ticket['conversation']) > 7 and currentConversationPage + 1 < len(conversationPages): currentConversationPage += 1 #Jump to the next page if the new response is on a new page
                            await notifyMembers(ticket)
                    elif result[0].emoji in (self.emojis['bell'], self.emojis['bellMute']): member['notifications'] = not member['notifications']
                    ticket['members'] = [member if i == memberIndex else m for i, m in enumerate(ticket['members'])]
                    asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
            else: number = None #Triggers browse mode
            try:
                if clearAt and datetime.datetime.now() > clearAt: await message.edit(content=None)
            except UnboundLocalError: await message.edit(content=None)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command()
    async def pause(self, ctx: commands.Context, *args):
        '''Pause logging or antispam for a duration'''
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        status = await ctx.send(str(self.loading) + "Please wait...")
        status = await ctx.send(f'{self.emojis["loading"]}Pausing...')
        args = [a.lower() for a in args]
        server_data = await utility.get_server(ctx.guild)
        defaultChannel = self.bot.get_channel(server_data['cyberlog']['defaultChannel'])
        if not defaultChannel:
            defaultChannel = self.bot.get_channel(server_data['antispam']['log'][1])
            if not defaultChannel:
                defaultChannel = ctx.channel
        if 'logging' in args:
            if 'logging' != args[0]:
                return
            key = 'cyberlog'
        if 'antispam' in args:
            if 'antispam' != args[0]:
                return
            key = 'antispam'
        seconds = self.ParsePauseDuration((' ').join(args[1:]))
        duration = datetime.timedelta(seconds = seconds)
        if seconds > 0: 
            rawUntil = datetime.datetime.utcnow() + duration
            until = rawUntil + await utility.time_zone(ctx.guild)
        else: 
            rawUntil = datetime.datetime.max
            until = datetime.datetime.max
        embed = discord.Embed(
            title=f'The {args[0][0].upper()}{args[0][1:]} module was paused',
            description=textwrap.dedent(f'''
                👮‍♂️Moderator: {ctx.author.mention} ({ctx.author.name})
                {utility.clockEmoji(datetime.datetime.now() + datetime.timedelta(hours=await utility.time_zone(ctx.guild)))}Paused at: {utility.DisguardIntermediateTimestamp(datetime.datetime.now())}
                ⏰Paused until: {'Manually resumed' if seconds == 0 else f"{utility.DisguardIntermediateTimestamp(until)} ({utility.DisguardRelativeTimestamp(until)})"}
                '''),
            color=yellow[await utility.color_theme(ctx.guild)])
        embed.set_footer(text='Resuming at: ')
        embed.timestamp = rawUntil
        url = cyber.imageToURL(ctx.author.avatar)
        embed.set_thumbnail(url=url)
        embed.set_author(name=ctx.author.name, icon_url=url)
        await status.edit(content=None, embed=embed)
        await database.PauseMod(ctx.guild, key)
        # self.bot.lightningLogging[ctx.guild.id][key]['enabled'] = False
        pauseTimedEvent = {'type': 'pause', 'target': key, 'server': ctx.guild.id}
        if len(args) == 1: return #If the duration is infinite, we don't wait
        await database.AppendTimedEvent(ctx.guild, pauseTimedEvent)
        await asyncio.sleep(duration)
        await database.ResumeMod(ctx.guild, key)
        # self.bot.lightningLogging[ctx.guild.id][key]['enabled'] = True
        embed.title = f'The {args[0][0].upper()}{args[0][1:]} module has resumed'
        embed.description = ''
        await status.edit(embed=embed)
        
    @commands.command()
    async def unpause(self, ctx: commands.Context, *args):
        if len(args) < 1: return await ctx.send('Please provide module `antispam` or `logging` to unpause')
        args = [a.lower() for a in args]
        if 'antispam' in args:
            await database.ResumeMod(ctx.guild, 'antispam')
            # self.bot.lightningLogging[ctx.guild.id]['antispam']['enabled'] = True
            await ctx.send("✅Successfully resumed antispam moderation")
        if 'logging' in args:
            await database.ResumeMod(ctx.guild, 'cyberlog')
            # self.bot.lightningLogging[ctx.guild.id]['cyberlog']['enabled'] = True
            await ctx.send("✅Successfully resumed logging")

    @commands.command()
    async def history(self, ctx: commands.Context, target: typing.Optional[discord.Member] = None, *, mod = ''):
        '''Viewer for custom status, username, and avatar history
        •If no member is provided, it will default to the command author
        •If no module is provided, it will default to the homepage'''
        await ctx.trigger_typing()
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
            e.description = f'{len(data) if len(data) < 19 else 19} / {len(data)} entries shown; oldest on top\nWebsite portal coming soon™'
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
        return duration

def clean(s):
    return re.sub(r'[^\w\s]', '', s.lower())

async def setup(bot: commands.Bot):
    await bot.add_cog(Misc(bot))
