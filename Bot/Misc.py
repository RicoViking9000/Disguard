'''Contains code relating to various bonus/extra features of Disguard
This will initially only contain the Easter/April Fools Day events code, but over time will be expanded to include things that don't belong in other files
'''

import discord
import secure
from discord.ext import commands, tasks
import database
import lyricsgenius
import re
import asyncio
import datetime

yellow = (0xffff00, 0xffff66)
placeholderURL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
qlf = '  ' #Two special characters to represent quoteLineFormat
qlfc = ' '
newline = '\n'

class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emojis = bot.get_cog('Cyberlog').emojis
        self.loading = self.emojis['loading']
        self.genius = lyricsgenius.Genius(secure.geniusToken(), remove_section_headers=True, verbose=False)
        self.songSessions = {} #Dict key: Channel ID, Dict value: String (if song is unconfirmed) or Genius Song object
        self.privacyUpdaterCache = {} #Key: UserID_ChannelID, Value: Message ID
    
    def getData(self):
        return self.bot.lightningLogging

    def getUserData(self):
        return self.bot.lightningUsers

    @commands.Cog.listener()
    async def on_message(self, message):
        '''This message listener is currently use for: April Fools Day event [Song Lyrics] automater'''
        return

    @commands.command()
    async def privacy(self, ctx):
        user = self.bot.lightningUsers[ctx.author.id]
        users = database.GetUserCollection()
        privacy = user['privacy']
        prefix = self.bot.lightningLogging[ctx.guild.id]['prefix'] if ctx.guild else '.'
        def slideToggle(i): return self.emojis['slideToggleOff'] if i == 0 else self.emojis['slideToggleOn'] if i == 1 else slideToggle(privacy['default'][0]) #Uses recursion to use default value if specific setting says to
        def viewerEmoji(i): return '🔒' if i == 0 else '🔓' if i == 1 else viewerEmoji(privacy['default'][1]) if i == 2 else self.emojis['members']
        def viewerText(i): return 'only you' if i == 0 else 'everyone you share a server with' if i == 1 else viewerText(privacy['default'][1]) if i == 2 else f'{len(i)} users'
        def enabled(i): return False if i == 0 else True if i == 1 else enabled(privacy['default'][0])
        #embed = discord.Embed(title=f'Privacy Settings » {ctx.author.name} » Overview', color=user['profile'].get('favColor') or yellow[user['profile']['colorTheme']])
        embed = discord.Embed(title=f'Privacy Settings » {ctx.author.name} » Overview', color=yellow[1])
        embed.description = f'''To view Disguard's privacy policy, [click here](https://disguard.netlify.app/privacybasic)\nTo view and edit all settings, visit your profile on my [web dashboard](http://disguard.herokuapp.com/manage/profile)'''
        embed.add_field(name='Default Settings', value=f'''{slideToggle(privacy['default'][0])}Allow Disguard to use your customization settings for its features: {"Enabled" if enabled(privacy['default'][0]) else "Disabled"}\n{viewerEmoji(privacy['default'][1])}Default visibility of your customization settings: {viewerText(privacy['default'][1])}''', inline=False)
        embed.add_field(name='Personal Profile Features', value=f'''{slideToggle(privacy['profile'][0])}{"Enabled" if enabled(privacy['profile'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['profile'][1])}Personal profile features: Visible to {viewerText(privacy['profile'][1])}" if enabled(privacy['profile'][0]) else ""}''', inline=False)
        embed.add_field(name='Birthday Module Features', value=f'''{slideToggle(privacy['birthdayModule'][0])}{"Enabled" if enabled(privacy['birthdayModule'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['birthdayModule'][1])}Birthday profile features: Visible to {viewerText(privacy['birthdayModule'][1])}" if enabled(privacy['birthdayModule'][0]) else ""}''', inline=False)
        embed.add_field(name='Attribute History', value=f'''{slideToggle(privacy['attributeHistory'][0])}{"Enabled" if enabled(privacy['attributeHistory'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['attributeHistory'][1])}Attribute History: Visible to {viewerText(privacy['attributeHistory'][1])}" if enabled(privacy['attributeHistory'][0]) else ""}''', inline=False)
        m = await ctx.send(embed=embed)

    @commands.command(aliases=['feedback', 'ticket'])
    async def support(self, ctx, *, opener=''):
        '''Command to initiate a feedback ticket. Anything typed after the command name will be used to start the support ticket
        Ticket status
        0: unopened by dev
        1: opened (dev has viewed)
        2: in progress (dev has replied)
        3: closed'''
        await ctx.trigger_typing()
        colorTheme = self.bot.get_cog('Cyberlog').colorTheme(ctx.guild) if ctx.guild else 1
        details = self.bot.get_cog('Cyberlog').emojis['details']
        def navigationCheck(r, u): return str(r) in reactions and r.message.id == status.id and u.id == ctx.author.id
        #If the user didn't provide a message with the command, prompt them with one here
        if opener.startsWith('System:'):
            specialCase = opener[opener.find(':') + 1:].strip()
            opener = ''
        else:
            specialCase = False
        if not opener:
            embed=discord.Embed(title='Disguard Support Menu', description=f"Welcome to Disguard support!\n\nIf you would easily like to get support, you may join my official server: https://discord.gg/xSGujjz\n\nIf you would like to get in touch with my developer without joining servers, react 🎟 to open a support ticket\n\nIf you would like to view your active support tickets, type `{self.getData()[ctx.guild.id]['prefix'] if ctx.guild else '.'}tickets` or react {details}", color=yellow[colorTheme])
            status = await ctx.send(embed=embed)
            reactions = ['🎟', details]
            for r in reactions: await status.add_reaction(r)
            result = await self.bot.wait_for('reaction_add', check=navigationCheck)
            if result[0].emoji == details:
                await status.delete()
                return await self.ticketsCommand(ctx)
            await ctx.send('Please type the message you would like to use to start the support thread, such as a description of your problem or a question you have')
            def ticketCreateCheck(m): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
            try: result = await self.bot.wait_for('message', check=ticketCreateCheck, timeout=300)
            except asyncio.TimeoutError: return await ctx.send('Timed out')
            opener = result.content
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
                def selectionCheck(r, u): return str(r) in possibleLetters and r.message.id == awaitingServerSelection.id and u.id == ctx.author.id
                try: selection = await self.bot.wait_for('reaction_add', check=selectionCheck, timeout=300)
                except asyncio.TimeoutError: return await ctx.send('Timed out')
                server = serverList[alphabet.index(str(selection[0]))]
                if type(server) is str: server = None
            else: server = serverList[0]
        else: server = ctx.guild
        embed=discord.Embed(title=f'🎟 Disguard Ticket System / {self.loading} Creating Ticket...', color=yellow[colorTheme])
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
        embed.description = f'''Your support ticket has successfully been created\n\nTicket number: {ticket['number']}\nAuthor: {ctx.author.name}\nMessage: {opener}\n\nTo view this ticket, react 🎟 or type `{self.getData()[ctx.guild.id]['prefix'] if ctx.guild else "."}tickets {ticket['number']}`, which will allow you to add members to the support thread if desired, disable DM notifications, reply, and more.'''
        await status.edit(embed=embed)
        reactions = ['🎟']
        await status.add_reaction('🎟')
        devManagement = self.bot.get_channel(681949259192336406)
        await devManagement.send(embed=embed)
        result = await self.bot.wait_for('reaction_add', check=navigationCheck)
        await self.ticketsCommand(ctx, number=ticket['number'])

    @commands.command(name='tickets')
    async def ticketsCommand(self, ctx, number:int = None):
        '''Command to view feedback tickets'''
        g = ctx.guild
        alphabet = [l for l in ('🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿')]
        colorTheme = self.bot.get_cog('Cyberlog').colorTheme(ctx.guild) if ctx.guild else 1
        #emojis = bot.get_cog('Cyberlog').emojis
        global emojis
        trashcan = self.emojis['delete']
        statusDict = {0: 'Unopened', 1: 'Viewed', 2: 'In progress', 3: 'Closed', 4: 'Locked'}
        message = await ctx.send(embed=discord.Embed(description=f'{self.loading}Downloading ticket data'))
        tickets = await database.GetSupportTickets()
        embed=discord.Embed(title=f"🎟 Disguard Ticket System / {self.emojis['details']} Browse Your Tickets", color=yellow[colorTheme])
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
            embed.description = f'''{f'NAVIGATION':-^70}\n{trashcan}: Delete this embed\n{self.emojis['details']}: Adjust sort\n◀: Previous page\n🇦 - {alphabet[len(pages[index]) - 1]}: View ticket\n▶: Next page\n{f'Tickets for {ctx.author.name}':-^70}\nPage {index + 1} of {len(pages)}\nViewing {len(pages[index])} of {len(filtered)} results\nSort: {sortDescription}'''
            for i, ticket in enumerate(pages[index]):
                tg = g #probably stands for 'ticketGuild'
                if not tg and ticket['server']: tg = self.bot.get_guild(ticket['server'])
                embed.add_field(
                    name=f"{alphabet[i]}Ticket {ticket['number']}",
                    value=f'''> Members: {", ".join([self.bot.get_user(u['id']).name for i, u in enumerate(ticket['members']) if i not in (1, 2)])}\n> Status: {statusDict[ticket['status']]}\n> Latest reply: {self.bot.get_user(ticket['conversation'][-1]['author']).name} • {(ticket['conversation'][-1]['timestamp'] + datetime.timedelta(hours=(self.getData()[tg.id]['offset'] if tg else -5))):%b %d, %Y • %I:%M %p} {self.getData()[tg.id]['tzname'] if tg else 'EST'}\n> {qlf}{ticket['conversation'][-1]['message']}''',
                    inline=False)
        async def notifyMembers(ticket):
            e = discord.Embed(title=f"New activity in ticket {ticket['number']}", description=f"To view the ticket, use the tickets command (`.tickets {ticket['number']}`)\n\n{'Highlighted message':-^70}", color=yellow[ticketColorTheme])
            entry = ticket['conversation'][-1]
            messageAuthor = self.bot.get_user(entry['author'])
            e.set_author(name=messageAuthor, icon_url=messageAuthor.avatar_url_as(static_format='png'))
            e.add_field(
                name=f"{messageAuthor.name} • {(entry['timestamp'] + datetime.timedelta(hours=(self.getData()[tg.id]['offset'] if tg else -5))):%b %d, %Y • %I:%M %p} {self.getData()[tg.id]['tzname'] if tg else 'EST'}",
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
            embed.description = f"There are currently no tickets in the system created by or involving you. To create a feedback ticket, type `{self.getData()[ctx.guild.id]['prefix'] if ctx.guild else '.'}ticket`"
            return await message.edit(embed=embed)
        def optionNavigation(r, u): return r.emoji in reactions and r.message.id == message.id and u.id == ctx.author.id and not u.bot
        def messageCheck(m): return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
        while not self.bot.is_closed():
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
                reactions = [trashcan, self.emojis['details'], self.emojis['arrowBackwards']] + alphabet[:len(pages[currentPage])] + [self.emojis['arrowForwards']]
                for r in reactions: await message.add_reaction(r)
                destination = await self.bot.wait_for('reaction_add', check=optionNavigation)
                try: await message.remove_reaction(*destination)
                except: pass
            else: destination = [alphabet[0]]
            async def clearMessageContent():
                await asyncio.sleep(5)
                if datetime.datetime.now() > clearAt: await message.edit(content=None)
            clearAt = None
            if destination[0].emoji == trashcan: return await message.delete()
            elif destination[0].emoji == self.emojis['details']:
                clearReactions = False
                sortMode += 1 if sortMode != 3 else -3
                messageContent = '--SORT MODE--\n' + '\n'.join([f'> **{d}**' if i == sortMode else f'{qlfc}{d}' for i, d in enumerate(sortDescriptions)])
                await message.edit(content=messageContent)
                clearAt = datetime.datetime.now() + datetime.timedelta(seconds=4)
                asyncio.create_task(clearMessageContent())
            elif destination[0].emoji in (self.emojis['arrowBackward'], self.emojis['arrowForward']):
                if destination[0].emoji == self.emojis['arrowBackward']: currentPage -= 1
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
                    ticketColorTheme = self.bot.get_cog('Cyberlog').colorTheme(tg) if tg else 1
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
                    for entry in conversationPages[currentConversationPage]: embed.add_field(name=f"{self.bot.get_user(entry['author']).name} • {(entry['timestamp'] + datetime.timedelta(hours=(self.getData()[tg.id]['offset'] if tg else -4))):%b %d, %Y • %I:%M %p} {self.getData()[tg.id]['tzname'] if tg else 'EST'}", value=f'> {entry["message"]}', inline=False)
                    if ctx.guild: 
                        if clearReactions: await message.clear_reactions()
                        else: clearReactions = True
                        await message.edit(content=None, embed=embed)
                    else:
                        await message.delete()
                        message = await ctx.send(embed=embed)
                    for r in reactions: await message.add_reaction(r)
                    result = await self.bot.wait_for('reaction_add', check=optionNavigation)
                    if result[0].emoji == self.emojis['arrowBackward']: break
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
                                        invite = discord.Embed(title='🎟 Invited to ticket', description=f"Hey {addMember.name},\n{ctx.author.name} has invited you to **support ticket {ticket['number']}** with [{', '.join([self.bot.get_user(m['id']).name for i, m in enumerate(ticket['members']) if i not in (1, 2)])}].\n\nThe Disguard support ticket system is a tool for server members to easily get in touch with my developer for issues, help, and questions regarding the bot\n\nTo join the support ticket, type `.tickets {ticket['number']}`", color=yellow[ticketColorTheme])
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
                                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
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
                                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
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
            number = None #Triggers browse mode
            try:
                if datetime.datetime.now() > clearAt: await message.edit(content=None)
            except UnboundLocalError: await message.edit(content=None)

def clean(s):
    return re.sub(r'[^\w\s]', '', s.lower())

def setup(bot):
    bot.add_cog(Misc(bot))
