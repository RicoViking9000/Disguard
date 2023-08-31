'''Contains Disguard's support ticket system'''

import discord
from discord.ext import commands
import traceback
import re
import datetime
import database
import utility
import textwrap
import asyncio

STATUS_DICT = {0: 'Unopened', 1: 'Viewed', 2: 'In progress', 3: 'Closed', 4: 'Locked'}
SORT_FLAVOR = {0: 'Recently active first', 1: 'Recently active last', 2: 'Ticket number (descending)', 3: 'Ticket number (ascending)'}

class Support(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis: dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis
        self.loading = self.emojis['loading']
    
    async def system_support(self, ctx: commands.Context, opener: str):
        '''Non-command method to create a support ticket'''
        opener = re.search(r'(?<=System:).+', opener).group(0)
        ticket = await self.create_support_ticket(ctx, opener, True)
    
    @commands.hybrid_command(aliases=['feedback', 'ticket'])
    async def support(self, ctx: commands.Context):
        '''
        Opens a support ticket with Disguard\'s developer
        ----------------
        Parameters:
        None
        '''
        # '''Command to initiate a feedback ticket. Anything typed after the command name will be used to start the support ticket
        # Ticket status
        # 0: unopened by dev
        # 1: opened (dev has viewed)
        # 2: in progress (dev has replied)
        # 3: closed'''
        await ctx.interaction.response.send_modal(SupportModal(ctx, self.bot))

    async def create_support_ticket(self, ctx: commands.Context, server: discord.Guild | None, message: str, system: bool = False) -> dict[str, str | int]:
        if ctx.guild:
            permissions = server.get_member(ctx.author.id).guild_permissions
        else:
            permissions = None
        ticket = {'number': ctx.message.id, 'id': ctx.message.id, 'author': ctx.author.id, 'channel': str(ctx.channel), 'server': server.id if server else None, 'notifications': True,
                'prestige': 
                    'N/A' if not server else \
                    'Server Owner' if ctx.author.id == server.owner.id else \
                    'Server Administrator' if permissions.administrator else \
                    'Server Moderator' if permissions.manage_guild else \
                    'Junior Server Moderator' if any((permissions.kick_members, permissions.ban_members, permissions.manage_channels, permissions.manage_roles, permissions.moderate_members)) else \
                    'Server Member',
                'status': 0, 'conversation': []}
        if system: firstEntry = {'author': self.bot.user.id, 'timestamp': datetime.datetime.utcnow(), 'message': f'*{message}*'}
        else: firstEntry = {'author': ctx.author.id, 'timestamp': datetime.datetime.utcnow(), 'message': message}
        ticket['conversation'].append(firstEntry)
        authorMember, devMember, botMember = {'id': ctx.author.id, 'bio': 'Created this ticket', 'permissions': 2, 'notifications': True}, {'id': 247412852925661185, 'bio': 'Bot developer', 'permissions': 1, 'notifications': True}, {'id': self.bot.user.id, 'bio': 'System messages', 'permissions': 1, 'notifications': False} #2: Owner, 1: r/w, 0: r 
        ticket['members'] = [authorMember, devMember, botMember]
        try: ticketList = await database.GetSupportTickets()
        except AttributeError: ticketList = []
        ticket['number'] = len(ticketList)
        await database.CreateSupportTicket(ticket)
        return ticket

    @commands.hybrid_command(name='tickets')
    async def view_tickets_command(self, ctx: commands.Context, ticket_number: int = -1):
        '''View the support tickets you\'ve opened with Disguard
        --------------------------------
        Parameters:
        ticket_number: int, optional
            The number of the ticket you want to view. If not provided, a list of all your tickets will be shown.
        '''
        # No autocomplete support unless retrieving tickets moves to local storage
        trashcan = self.emojis['delete']
        # message = await ctx.send(embed=discord.Embed(description=f'{self.loading}Downloading ticket data'))
        tickets = await database.GetSupportTickets()
        embed = discord.Embed(title=f'🎟 Disguard Ticket System', color=utility.YELLOW[color_theme])
        basic_view = discord.ui.View(timeout=300)
        basic_view.add_item(CreateTicketButton(self.bot, ctx))
        if not tickets: 
            color_theme = await utility.color_theme(ctx.guild) if ctx.guild else 1
            embed.description = 'There are no tickets currently in the system'
            return await ctx.interaction.response.send_message(embed=embed, view=basic_view)
        filtered_tickets = [t for t in tickets if ctx.author.id in [m['id'] for m in t['members']]] #only tickets involving the user
        if not filtered_tickets:
            embed.description = 'There are currently no tickets in the system created by or involving you, and you have no pending invites.'
            return await ctx.interaction.response.send_message(embed=embed, view=basic_view)
        if ticket_number == -1:
            return await ctx.interaction.response.send_message(embed=embed, view=TicketBrowseView(ctx, self.bot, filtered_tickets))
        try: ticket = tickets[ticket_number]
        except IndexError: 
            return await ctx.interaction.response.send_message(embed=embed, view=TicketBrowseView(ctx, self.bot, filtered_tickets, f'Ticket {ticket_number} doesn\'t exist in the system.'))
        if check_member_access(ctx.author, ticket): await ctx.interaction.response.send_message(embed=embed, view=SingleTicketView(self.bot, ticket))
        else: await ctx.interaction.response.send_message(embed=embed, view=TicketBrowseView(ctx, self.bot, filtered_tickets, f'You don\'t have access to ticket {ticket_number}.'))

    async def notify_members(ticket: dict[str, str | int]):
        ''' Notify ticket members of a new reply '''
        e = discord.Embed(title=f"New activity in ticket {ticket['number']}", description=f"To view the ticket, use the tickets command (`.tickets {ticket['number']}`)\n\n{'Highlighted message':-^50}", color=yellow[ticketcolor_theme])
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

def paginate(iterable: list, per_page=10):
    '''Splits a list into pages of a given size'''
    for i in range(0, len(iterable), per_page): yield iterable[i : i + per_page]

def check_member_access(member: discord.Member, ticket: dict) -> int:
    '''Checks if a member has access to a ticket
    --------------------------------
    Parameters:
    member: discord.Member
        The member to check
    ticket: dict
        The ticket to check
    --------------------------------
    Returns:
    int
        The member's permission level
        0: No access
        1: Read-only
        2: Read/write
        3: Pending invite
    '''
    for m in ticket['members']:
        if m['id'] == member.id: return m['permissions']
    return 0

class TicketBrowseView(discord.ui.View):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, tickets: list[dict], special_message: str = '') -> None:
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.tickets = tickets
        self.special_message = special_message
        self.support: Support = self.bot.get_cog('Support')
        self.pages = list(paginate(self.tickets, 5))
        self.current_page = 0
        self.sort_mode = 0
        self.add_item(self.SelectTicketDropdown(bot, tickets))
        self.add_item(self.CloseViewerButton(bot))
        if len(self.pages) > 1: 
            self.add_item(self.PreviousPageButton(bot))
            self.add_item(self.NextPageButton(bot))
        self.add_item(self.AdjustSortButton(bot))
        asyncio.create_task(self.create_embed())
        asyncio.create_task(self.build_viewer())
    
    def sort_tickets(self, mode: int):
        '''Sorts the tickets by the given mode'''
        if mode < 2: self.tickets.sort(key = lambda x: x['conversation'][-1]['timestamp'], reverse = mode == 0) #Sort by most recent activity
        elif mode >= 2: self.tickets.sort(key = lambda x: x['number'], reverse = mode == 2) #Sort by ticket number
    
    async def create_embed(self):
        color_theme = await utility.color_theme(self.ctx.guild) if self.ctx.guild else 1
        self.embed = discord.Embed(title=f"🎟 {self.support.emojis['details']} Browse Tickets", color=utility.YELLOW[color_theme])
        self.embed.set_author(name=self.ctx.author, icon_url=self.ctx.author.avatar.with_static_format('png').url)
    
    async def populate_embed(self):
        '''Builds the browse tickets embed'''
        self.embed.clear_fields()
        self.embed.description = textwrap.dedent(f'''
            {f"⚠ | {self.special_message}{utility.NEWLINE}{utility.NEWLINE}" if self.special_message else ''}
            {f"{self.ctx.author.name}'s Tickets":-^50}
            Page {self.current_page + 1} of {len(self.pages)}
            Viewing {len(self.pages[self.current_page])} of {len(self.tickets)} tickets
            Sort: {SORT_FLAVOR[self.sort_mode]}''')
        for i, ticket in enumerate(self.pages[self.current_page]):
            ticket_server = self.ctx.guild
            if not ticket_server and ticket['server']: ticket_server = self.bot.get_guild(ticket['server'])
            self.embed.add_field(
                name=f'Ticket {ticket["number"]}',
                value=textwrap.dedent(f'''
                > Members: {', '.join([self.bot.get_user(user['id']).name for user in ticket['members'] if user['id'] not in (self.bot.user.id, utility.rv9k)])}
                > Status: {STATUS_DICT[ticket['status']]}
                > Latest reply: {self.bot.get_user(ticket['conversation'][-1]['author']).name} • {(ticket['conversation'][-1]['timestamp'] + datetime.timedelta(hours=(await utility.time_zone(ticket_server) if ticket_server else 0))):%b %d, %Y • %I:%M %p} {await utility.name_zone(ticket_server) if ticket_server else 'UTC'}
                > {utility.INDENT}{ticket['conversation'][-1]['message']}
                '''),
                inline=False)
    
    async def build_viewer(self):
        self.sort_tickets(self.sort_mode)
        await self.populate_embed()
        self.ctx.interaction.edit_original_response(embed=self.embed, view=self)
    
    class SelectTicketDropdown(discord.ui.Select):
        def __init__(self, bot: commands.Bot, tickets: list[dict]) -> None:
            super().__init__(placeholder='Select a ticket to view')
            self.bot = bot
            self.tickets = tickets
            self.support: Support = self.bot.get_cog('Support')
            for ticket in tickets:
                prefix = f'{self.bot.get_user(ticket["conversation"][-1]["author"]).name}: '
                message = ticket['conversation'][-1]['message']
                self.add_option(label=f'Ticket {ticket["number"]}', value=str(ticket['number']), description=f'{prefix}{message[:99 - len(prefix)]}{"…" if len(message) > 99 - len(prefix) else ""}')
        
        async def callback(self, interaction: discord.Interaction):
            # switch to single ticket view
            pass
    
    class CloseViewerButton(discord.ui.Button):
        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.red, emoji=bot.get_emoji(support.emojis['close']), label='Close viewer')
            
        async def callback(self, interaction: discord.Interaction):
            await interaction.message.delete()
    
    class PreviousPageButton(discord.ui.Button):
        def __init__(self, bot: commands.Bot) -> None:
            self.view: TicketBrowseView = self.view
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=bot.get_emoji(support.emojis['previous']), label='Previous page')
        
        async def callback(self, interaction: discord.Interaction):
            self.view.current_page -= 1
            if self.view.current_page == 0: self.disabled = True
            elif self.view.current_page != 0 and self.disabled: self.disabled = False
            await self.view.populate_embed()
            await interaction.response.edit_message(embed=self.view.embed, view=self.view)
    
    class NextPageButton(discord.ui.Button):
        def __init__(self, bot: commands.Bot) -> None:
            self.view: TicketBrowseView = self.view
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=bot.get_emoji(support.emojis['next']), label='Next page')
        
        async def callback(self, interaction: discord.Interaction):
            self.view.current_page += 1
            if self.view.current_page == len(self.view.pages) - 1: self.disabled = True
            elif self.view.current_page != len(self.view.pages) - 1 and self.disabled: self.disabled = False
            await self.view.populate_embed()
            await interaction.response.edit_message(embed=self.view.embed, view=self.view)
    
    class AdjustSortButton(discord.ui.Button):
        def __init__(self, bot: commands.Bot) -> None:
            self.view: TicketBrowseView = self.view
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=bot.get_emoji(support.emojis['details']), label=f'Sort: {SORT_FLAVOR[self.view.sort_mode]}')
        
        async def callback(self, interaction: discord.Interaction):
            self.view.sort_mode = (self.view.sort_mode + 1) % len(SORT_FLAVOR)
            self.view.sort_tickets(self.view.sort_mode)
            await self.view.populate_embed()
            await interaction.response.edit_message(embed=self.view.embed, view=self.view)


class SingleTicketView(discord.ui.View):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, ticket: dict) -> None:
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.ticket = ticket
        self.support: Support = self.bot.get_cog('Support')

    async def create_embed(self):
        color_theme = await utility.color_theme(self.ctx.guild) if self.ctx.guild else 1
        self.embed = discord.Embed(title=f"🎟 Ticket {self.ticket['number']}", color=utility.YELLOW[color_theme])
        self.embed.set_author(name=self.ctx.author, icon_url=self.ctx.author.avatar.with_static_format('png').url)
    
    async def populate_embed(self):
        self.embed.clear_fields()
    
    async def setup(self):
        def messageCheck(m: discord.Message): return m.channel.id == self.ctx.channel.id and m.author.id == self.ctx.author.id
        # if self.ctx.author.id == utility.rv9k and self.ticket['status'] == 0: self.ticket['status'] = 1 #If I view the ticket and it's marked as not viewed yet, mark it as viewed
        ticket_member = [m for m in self.ticket['members'] if m['id'] == self.ctx.author.id][0]
        conversation_pages = list(paginate(self.ticket['conversation'], 7))
        current_conversation_page = len(conversationPages) - 1
        
        server = self.bot.get_guild(self.ticket['server'])
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
        embed.title = f'🎟 Disguard Ticket System / Ticket {ticket_number}'
        embed.description = f'''{'TICKET DATA':-^50}\n{self.emojis['member']}Author: {self.bot.get_user(ticket['author'])}\n⭐Prestige: {ticket['prestige']}\n{self.emojis['members']}Other members involved: {', '.join([self.bot.get_user(u["id"]).name for u in ticket['members'] if u["id"] not in (247412852925661185, self.bot.user.id, ctx.author.id)]) if len(ticket['members']) > 3 else f'None - react {self.emojis["members"]} to add'}\n⛓Server: {self.bot.get_guild(ticket['server'])}\n{returnPresence(ticket['status'])}Dev visibility status: {statusDict.get(ticket['status'])}\n{self.emojis['bell'] if member['notifications'] else self.emojis['bellMute']}Notifications: {member['notifications']}\n\n{f'CONVERSATION - {self.emojis["reply"]} to reply' if member['permissions'] > 0 else 'CONVERSATION':-^50}\nPage {currentConversationPage + 1} of {len(conversationPages)}{f'{NEWLINE}{self.emojis["arrowBackward"]} and {self.emojis["arrowForward"]} to navigate' if len(conversationPages) > 1 else ''}\n\n'''
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
            ticket_number = None #deselect the ticket
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
                memberFillerText = [f'{self.bot.get_user(u["id"])}{NEWLINE}> {u["bio"]}{NEWLINE}> Permissions: {permissionsDict[u["permissions"]]}' for u in ticket['members']]
                embed.description = f'''**__{'TICKET SHARING SETTINGS':-^50}__\n\n{'Permanently included':-^40}**\n{NEWLINE.join([f'👤{f}' for f in memberFillerText[:3]])}'''
                embed.description += f'''\n\n**{'Additional members':-^40}**\n{NEWLINE.join([f'{self.emojis["member"]}{f}{f"{NEWLINE}> {alphabet[i]} to manage" if ctx.author.id == ticket["author"] else ""}' for i, f in enumerate(memberFillerText[3:])]) if len(memberFillerText) > 2 else 'None yet'}'''
                if ctx.author.id == ticket['author']: embed.description += f'''\n\n**{'Add a member':-^40}**\nSend a message to search for a member to add, then react with the corresponding letter to add them{f'{NEWLINE}{NEWLINE}Moderators of {self.bot.get_guild(ticket["server"])} are listed below as suggestions. You may react with the letter next to their name to quickly add them, otherwise send a message to search for someone else' if ticket['server'] and len(staffMemberResults) > 0 else ''}'''
                reactions = [self.emojis['arrowLeft']]
                if memberIndex > 2: 
                    embed.description += '\n\nIf you would like to leave the ticket, react 🚪'
                    reactions.append('🚪')
                offset = len([a for a in alphabet if a in embed.description])
                if server and len(memberResults) == 0: memberResults = staffMemberResults
                embed.description += f'''\n\n{NEWLINE.join([f'{alphabet[i + offset]}{m.name} - {calculateBio(m)}' for i, m in enumerate(memberResults)])}'''
                reactions += [l for l in alphabet if l in embed.description]
                if ctx.guild: 
                    if clearReactions: await message.clear_reactions()
                    else: clearReactions = True
                    await message.edit(content=None, embed=embed)
                else:
                    await message.delete()
                    message = await ctx.send(embed=embed)
                for r in reactions: await message.add_reaction(r)
                d, p = await asyncio.wait([
                    asyncio.create_task(self.bot.wait_for('reaction_add', check=optionNavigation)),
                    asyncio.create_task(self.bot.wait_for('message', check=messageCheck))
                    ], return_when=asyncio.FIRST_COMPLETED)
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
                                embed.description=f'''**{f'Manage {user.name}':-^50}**\n{'🔒' if not ctx.guild or ticketUser['permissions'] == 0 else '🔓'}Permissions: {permissionsDict[ticketUser['permissions']]}\n\n{self.emojis['details']}Responses: {len([r for r in ticket['conversation'] if r['author'] == user.id])}\n\n{f'{self.emojis["bell"]}Notifications: True' if ticketUser['notifications'] else f'{self.emojis["bellMute"]}Notifications: False'}\n\n❌: Remove this member'''
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
            d, p = await asyncio.wait([
                asyncio.create_task(self.bot.wait_for('reaction_add', check=optionNavigation)),
                asyncio.create_task(self.bot.wait_for('message', check=messageCheck))
                ], return_when=asyncio.FIRST_COMPLETED)
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
        else: ticket_number = None #Triggers browse mode
        try:
            if clearAt and datetime.datetime.now() > clearAt: await message.edit(content=None)
        except UnboundLocalError: await message.edit(content=None)
    
    
class SelectASupportServerView(discord.ui.View):
    def __init__(self, bot: commands.Bot, servers: list[discord.Guild], dropdown: discord.ui.Select, custom_id) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.servers = servers
        self.custom_id = custom_id
        support: Support = self.bot.get_cog('Support')
        self.add_item(dropdown)

class SelectASupportServer(discord.ui.Select):
    def __init__(self, servers: list[discord.Guild], custom_id) -> None:
        super().__init__(placeholder='Select a server', min_values=1, max_values=1, custom_id=custom_id)
        self.servers = servers
        for server in servers:
            self.add_option(label=server.name, value=server.id)
        self.add_option(label='Prefer not to answer', value='None')
    
    async def callback(self, interaction: discord.Interaction):
        # await interaction.response.pong()
        await interaction.message.delete()

class SupportModal(discord.ui.Modal):
    def __init__(self, ctx: commands.Context, bot: commands.Bot):
        super().__init__(title="Create a support ticket")
        self.ctx = ctx
        self.bot = bot

    body = discord.ui.TextInput(style=discord.TextStyle.long, label="Please describe your scenario", placeholder="Blank space", max_length=2000)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        traceback.print_exc()
    
    async def on_submit(self, interaction: discord.Interaction):
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        misc: Misc = self.bot.get_cog('Misc')
        color_theme = await utility.color_theme(interaction.guild) if interaction.guild else 1
        #If the user didn't provide a message with the command, prompt them with one here
        if not interaction.guild:
            serverList = [g for g in self.bot.guilds if g.get_member(self.ctx.author.id)]
            if len(serverList) > 2: #If the member is in more than one server with the bot, prompt for which server they're in
                dropdown = misc.SelectASupportServer(serverList, str(self.ctx.message.id))
                view = misc.SelectASupportServerView(self.bot, serverList, dropdown, str(self.ctx.message.id))
                await interaction.channel.send('If this issue relates to a specific server, select it from the dropdown menu below', view=view)
                def interaction_check(i: discord.Interaction): return i.data['custom_id'] == str(self.ctx.message.id) and i.user.id == self.ctx.author.id
                try: response = await self.bot.wait_for('interaction', check=interaction_check, timeout=600)
                except asyncio.TimeoutError: return await interaction.edit_original_response(content='Timed out')
                if not dropdown.values[0]: server = None
                else: server = self.bot.get_guild(int(response.data['values'][0]))
            else: server = serverList[0]
        else: server = interaction.guild
        embed=discord.Embed(title='🎟 Disguard Ticket System', description=f'{misc.loading} Creating Ticket...', color=yellow[color_theme])
        await interaction.response.send_message(embed=embed)
        ticket = await misc.create_support_ticket(self.ctx, server, self.body.value)
        embed.description = f'''Your support ticket has successfully been created.\n\nTicket number: {ticket['number']}\nAuthor: {self.ctx.author.name}\nMessage: `{self.body.value}`\n\nTo view or manage this ticket, use the button below or the `/tickets` command.'''
        new_view = SupportTicketFollowUp(self.ctx, self.bot, ticket['number'])
        await interaction.edit_original_response(embed=embed, view=new_view)
        devManagement = self.bot.get_channel(681949259192336406)
        await devManagement.send(embed=embed)
    
class SupportTicketFollowUp(discord.ui.View):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, ticket_number: int):
        super().__init__()
        self.ctx = ctx
        self.bot = bot
        self.ticket_number = ticket_number
        self.add_item(OpenTicketButton(ctx, bot, ticket_number))

class OpenTicketButton(discord.ui.Button):
    '''A customizable button to open a support ticket with the given number'''
    def __init__(self, ctx: commands.Context, bot: commands.Bot, ticket_number: int, label: str = 'Open ticket', emoji: str = '🎟', custom_id: str = 'openTicket'):
        super().__init__(style=discord.ButtonStyle.gray, label=label, emoji=emoji, custom_id=custom_id)
        self.ctx = ctx
        self.bot = bot
        self.ticket_number = ticket_number
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.ctx.invoke(self.bot.get_command('tickets'), number=self.ticket_number)

class CreateTicketButton(discord.ui.Button):
    '''A customizable button to open the interactive modal to create a new support ticket'''
    def __init__(self, ctx: commands.Context, bot: commands.Bot, label: str = 'Create a ticket', emoji: str = '🎟', custom_id: str = 'createTicket'):
        super().__init__(style=discord.ButtonStyle.gray, label=label, emoji=emoji, custom_id=custom_id)
        self.ctx = ctx
        self.bot = bot
    
    async def callback(self, interaction: discord.Interaction):
        misc: Misc = self.bot.get_cog('Misc')
        await interaction.response.send_modal(misc.Support(self.ctx, self.bot))

async def setup(bot: commands.Bot):
    await bot.add_cog(Support(bot))