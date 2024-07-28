"""Contains Disguard's support ticket system"""

import asyncio
import copy
import datetime
import re
import textwrap
import traceback

import discord
from discord.ext import commands

import database
import utility

STATUS_DICT = {0: 'Unopened', 1: 'Viewed', 2: 'In progress', 3: 'Closed', 4: 'Locked'}
SORT_FLAVOR = {0: 'Recently active first', 1: 'Recently active last', 2: 'Ticket number (descending)', 3: 'Ticket number (ascending)'}
PERMISSIONS = {
    0: 'Invited to ticket',
    1: 'View ticket',
    2: 'View and reply to ticket',
    3: 'View, reply, manage ticket members',
    4: 'Ticket Owner (all permissions)',
}


class Support(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis: dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis
        self.loading = self.emojis['loading']

    async def system_support(self, ctx: commands.Context, opener: str):
        """Non-command method to create a support ticket"""
        opener = re.search(r'(?<=System:).+', opener).group(0)
        await self.create_support_ticket(ctx, opener, True)

    @commands.hybrid_command(aliases=['feedback', 'ticket'])
    async def support(self, ctx: commands.Context):
        """
        Opens a support ticket with Disguard\'s developer
        ----------------
        Parameters:
        None
        """
        # '''Command to initiate a feedback ticket. Anything typed after the command name will be used to start the support ticket
        # Ticket status
        # 0: unopened by dev
        # 1: opened (dev has viewed)
        # 2: in progress (dev has replied)
        # 3: closed'''
        await ctx.interaction.response.send_modal(SupportModal(ctx, self.bot))

    async def create_support_ticket(
        self, ctx: commands.Context, server: discord.Guild | None, message: str, system: bool = False
    ) -> dict[str, str | int]:
        if ctx.guild:
            permissions = server.get_member(ctx.author.id).guild_permissions
        else:
            permissions = None
        ticket = {
            'number': ctx.message.id,
            'id': ctx.message.id,
            'author': ctx.author.id,
            'channel': str(ctx.channel),
            'server': server.id if server else None,
            'notifications': True,
            'prestige': 'N/A'
            if not server
            else 'Server Owner'
            if ctx.author.id == server.owner.id
            else 'Server Administrator'
            if permissions.administrator
            else 'Server Moderator'
            if permissions.manage_guild
            else 'Junior Server Moderator'
            if any(
                (
                    permissions.kick_members,
                    permissions.ban_members,
                    permissions.manage_channels,
                    permissions.manage_roles,
                    permissions.moderate_members,
                )
            )
            else 'Server Member',
            'status': 0,
            'conversation': [],
            'created': discord.utils.utcnow(),
        }
        if system:
            firstEntry = {'author': self.bot.user.id, 'timestamp': discord.utils.utcnow(), 'message': f'*{message}*'}
        else:
            firstEntry = {'author': ctx.author.id, 'timestamp': discord.utils.utcnow(), 'message': message}
        ticket['conversation'].append(firstEntry)
        authorMember = {'id': ctx.author.id, 'bio': 'Created this ticket', 'permissions': 4, 'notifications': True}
        devMember = {'id': 247412852925661185, 'bio': 'Bot developer team', 'permissions': 2, 'notifications': True}
        botMember = {'id': self.bot.user.id, 'bio': 'System messages', 'permissions': 2, 'notifications': False}
        ticket['members'] = [authorMember, devMember, botMember]
        try:
            ticketList = await database.GetSupportTickets()
        except AttributeError:
            ticketList = []
        ticket['number'] = len(ticketList)
        await database.CreateSupportTicket(ticket)
        return ticket

    @commands.hybrid_command(name='tickets')
    async def view_tickets_command(self, ctx: commands.Context, ticket_number: int = -1):
        """View the support tickets you\'ve opened with Disguard
        --------------------------------
        Parameters:
        ticket_number: int, optional
            The number of the ticket you want to view. If not provided, a list of all your tickets will be shown.
        """
        # No autocomplete support unless retrieving tickets moves to local storage
        self.emojis['delete']
        # message = await ctx.send(embed=discord.Embed(description=f'{self.loading}Downloading ticket data'))
        tickets = await database.GetSupportTickets()
        color_theme = await utility.color_theme(ctx.guild) if ctx.guild else 1
        embed = discord.Embed(title='🎟 Disguard Ticket System', color=utility.YELLOW[color_theme])
        basic_view = discord.ui.View(timeout=300)
        basic_view.add_item(CreateTicketButton(self.bot, ctx))
        if not tickets:
            embed.description = 'There are no tickets currently in the system'
            return await ctx.interaction.response.send_message(embed=embed, view=basic_view)
        filtered_tickets = [t for t in tickets if ctx.author.id in [m['id'] for m in t['members']]]  # only tickets involving the user
        if not filtered_tickets:
            embed.description = 'There are currently no tickets in the system created by or involving you, and you have no pending invites.'
            return await ctx.interaction.response.send_message(embed=embed, view=basic_view)
        if ticket_number == -1:
            browse_view = TicketBrowseView(ctx, self.bot, filtered_tickets)
            await browse_view.setup()
            return await ctx.interaction.response.send_message(embed=embed, view=browse_view)
        try:
            ticket = tickets[ticket_number]
        except IndexError:
            browse_view = TicketBrowseView(ctx, self.bot, filtered_tickets, f"Ticket {ticket_number} doesn't exist in the system.")
            await browse_view.setup()
            return await ctx.interaction.response.send_message(embed=embed, view=browse_view)
        if check_member_access(ctx.author, ticket):
            ticket_view = SingleTicketView(ctx, self.bot, tickets, ticket)
            await ticket_view.setup()
            await ctx.interaction.response.send_message(embed=ticket_view.embed, view=ticket_view)
        else:
            await ctx.interaction.response.send_message(
                embed=embed, view=TicketBrowseView(ctx, self.bot, filtered_tickets, f"You don't have access to ticket {ticket_number}.")
            )

    async def notify_members(self, ctx: commands.Context, ticket: dict[str, str | int], **kwargs):
        """Notify ticket members of an action"""
        entry = ticket['conversation'][-1]
        author = self.bot.get_user(entry['author'])
        embed = discord.Embed(
            title=kwargs.get('title') or f"New activity in ticket {ticket['number']}",
            description=kwargs.get('description')
            or f'{author.display_name} replied: {entry["message"]}\n\nTo view the full ticket, use the button below or `/tickets {ticket["number"]}`',
            color=utility.YELLOW[1],
        )
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.with_static_format('png').url)
        embed.set_footer(text=f"You're receiving this DM because you have notifications enabled for ticket {ticket['number']}")
        for member in ticket['members']:
            if member['notifications'] and member['id'] != entry['author']:
                try:
                    await self.bot.get_user(member['id']).send(
                        embed=embed, view=DMNotificationView(ctx, self.bot, ticket, self.bot.get_user(member['id']))
                    )
                except:
                    pass


def paginate(iterable: list, per_page=10):
    """Splits a list into pages of a given size"""
    for i in range(0, len(iterable), per_page):
        yield iterable[i : i + per_page]


def check_member_access(member: discord.Member, ticket: dict) -> int:
    """Checks if a member has access to a ticket
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
    """
    for m in ticket['members']:
        if m['id'] == member.id:
            return m['permissions']
    return 0


def member_server_prestige(member: discord.Member) -> str:
    """Returns a string describing a member's prestige in the server"""
    match member:
        case member.guild.owner:
            return 'Server Owner'
        case member.guild_permissions.administrator:
            return 'Server Administrator'
        case member.guild_permissions.manage_guild:
            return 'Server Moderator'
        case member.guild_permissions.manage_roles | member.guild_permissions.manage_channels:
            return 'Junior Server Moderator'
        case (
            member.guild_permissions.kick_members
            | member.guild_permissions.ban_members
            | member.guild_permissions.moderate_members
            | member.guild_permissions.manage_messages
        ):
            return 'Chat Moderator'
        case _:
            return 'Server Member'


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
        self.add_item(self.AdjustSortButton(bot, self.sort_mode))

    def sort_tickets(self, mode: int):
        """Sorts the tickets by the given mode"""
        if mode < 2:
            self.tickets.sort(key=lambda x: x['conversation'][-1]['timestamp'], reverse=mode == 0)  # Sort by most recent activity
        elif mode >= 2:
            self.tickets.sort(key=lambda x: x['number'], reverse=mode == 2)  # Sort by ticket number

    async def create_embed(self):
        color_theme = await utility.color_theme(self.ctx.guild) if self.ctx.guild else 1
        self.embed = discord.Embed(title=f"🎟 {self.support.emojis['details']} Browse Tickets", color=utility.YELLOW[color_theme])
        self.embed.set_author(name=self.ctx.author, icon_url=self.ctx.author.display_avatar.with_static_format('png').url)

    async def populate_embed(self):
        """Builds the browse tickets embed"""
        self.embed.clear_fields()
        self.embed.description = textwrap.dedent(f"""
            {f"⚠ | {self.special_message}{utility.NEWLINE}{utility.NEWLINE}" if self.special_message else ''}
            {f"{self.ctx.author.display_name}'s Tickets":-^50}
            Page {self.current_page + 1} of {len(self.pages)}
            Viewing {len(self.pages[self.current_page])} of {len(self.tickets)} tickets
            Sort: {SORT_FLAVOR[self.sort_mode]}""")
        for i, ticket in enumerate(self.pages[self.current_page]):
            ticket_server = self.ctx.guild
            if not ticket_server and ticket['server']:
                ticket_server = self.bot.get_guild(ticket['server'])
            self.embed.add_field(
                name=f'Ticket {ticket["number"]}',
                value=textwrap.dedent(f"""
                > Members: {', '.join([self.bot.get_user(user['id']).display_name for user in ticket['members'] if user['id'] not in (self.bot.user.id, utility.rv9k)])}
                > Status: {STATUS_DICT[ticket['status']]}
                > Latest reply: {self.bot.get_user(ticket['conversation'][-1]['author']).display_name} • {(ticket['conversation'][-1]['timestamp'] + datetime.timedelta(hours=(await utility.time_zone(ticket_server) if ticket_server else 0))):%b %d, %Y • %I:%M %p} {await utility.name_zone(ticket_server) if ticket_server else 'UTC'}
                > {utility.INDENT}{ticket['conversation'][-1]['message']}
                """),
                inline=False,
            )

    async def setup(self):
        """Sets up the view"""
        await self.create_embed()
        await self.populate_embed()

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
                self.add_option(
                    label=f'Ticket {ticket["number"]}',
                    value=str(ticket['number']),
                    description=f'{prefix}{message[:99 - len(prefix)]}{"…" if len(message) > 99 - len(prefix) else ""}',
                )

        async def callback(self, interaction: discord.Interaction):
            # switch to single ticket view
            try:
                view: TicketBrowseView = self.view
                new_view = SingleTicketView(view.ctx, self.bot, self.tickets, self.tickets[int(self.values[0])])
                await new_view.setup()
                await interaction.response.edit_message(embed=new_view.embed, view=new_view)
            except:
                traceback.print_exc()

    class CloseViewerButton(discord.ui.Button):
        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.red, emoji=support.emojis['delete'], label='Close viewer')

        async def callback(self, interaction: discord.Interaction):
            await interaction.message.delete()

    class PreviousPageButton(discord.ui.Button):
        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=support.emojis['arrowBackward'], label='Previous page')

        async def callback(self, interaction: discord.Interaction):
            view: TicketBrowseView = self.view
            view.current_page -= 1
            if view.current_page == 0:
                self.disabled = True
            elif view.current_page != 0 and self.disabled:
                self.disabled = False
            await view.populate_embed()
            await interaction.response.edit_message(embed=view.embed, view=view)

    class NextPageButton(discord.ui.Button):
        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=support.emojis['arrowForward'], label='Next page')

        async def callback(self, interaction: discord.Interaction):
            view: TicketBrowseView = self.view
            view.current_page += 1
            if view.current_page == len(view.pages) - 1:
                self.disabled = True
            elif view.current_page != len(view.pages) - 1 and self.disabled:
                self.disabled = False
            await view.populate_embed()
            await interaction.response.edit_message(embed=view.embed, view=view)

    class AdjustSortButton(discord.ui.Button):
        def __init__(self, bot: commands.Bot, sort_mode: int) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=support.emojis['details'], label=f'Sort: {SORT_FLAVOR[sort_mode]}')

        async def callback(self, interaction: discord.Interaction):
            view: TicketBrowseView = self.view
            view.sort_mode = (view.sort_mode + 1) % len(SORT_FLAVOR)
            view.sort_tickets(view.sort_mode)
            await view.populate_embed()
            await interaction.response.edit_message(embed=view.embed, view=view)


class SingleTicketView(discord.ui.View):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, tickets: list[dict], ticket: dict) -> None:
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.tickets = tickets
        self.ticket = ticket
        self.ticket_member = [m for m in ticket['members'] if m['id'] == self.ctx.author.id][0]
        self.show_details = len(self.ticket['conversation']) < 4
        self.current_page = 0
        self.paginate_pages()
        self.support: Support = self.bot.get_cog('Support')
        self.prev_button = self.PreviousConversationPageButton(bot, self.current_page)
        self.next_button = self.NextConversationPageButton(bot, self.current_page, len(self.conversation_pages))
        self.add_item(self.BackButton(bot))
        self.add_item(self.prev_button)
        self.add_item(self.ReplyButton(bot))
        self.add_item(self.next_button)
        self.add_item(self.TicketDetailsToggle(bot, self.show_details))
        self.add_item(self.NotificationsToggleButton(bot, self.ticket_member['notifications']))
        self.add_item(self.MembersButton(bot, self.ticket_member['permissions'], len(self.ticket['members'])))
        if self.ctx.author.id == utility.rv9k:
            if self.ticket['status'] == 0:
                self.ticket['status'] = 1
            self.add_item(self.CloseTicketButton(bot, self.ticket['status']))

    def paginate_pages(self):
        """Paginates the ticket's conversation"""
        self.conversation_pages = list(paginate(list(reversed(self.ticket['conversation'])), 7 if self.show_details else 10))
        return self.conversation_pages

    async def create_embed(self):
        color_theme = await utility.color_theme(self.ctx.guild) if self.ctx.guild else 1
        self.embed = discord.Embed(title=f"🎟 Ticket {self.ticket['number']}", color=utility.YELLOW[color_theme])
        self.embed.set_author(name=self.ctx.author, icon_url=self.ctx.author.display_avatar.with_static_format('png').url)

    async def populate_embed(self):
        self.embed.description = ''
        self.embed.clear_fields()
        ticket = self.ticket
        # member_index = ticket['members'].index(ticket_member)
        ticket_server = self.bot.get_guild(ticket['server'])
        # current_conversation_page = len(conversation_pages) - 1
        # color_theme = await utility.color_theme(ticket_server) if ticket_server else 1
        other_ticket_members = [
            self.bot.get_user(m['id']).display_name for m in ticket['members'] if m['id'] not in (self.bot.user.id, utility.rv9k, self.ctx.author.id)
        ]
        reply_emoji = self.support.emojis['reply']
        conversation_header = f'CONVERSATION - {reply_emoji} to reply' if self.ticket_member['permissions'] >= 2 else 'CONVERSATION'
        conversation_header = f'{conversation_header:-^85}' if self.ticket_member['permissions'] >= 2 else f'{conversation_header:-^50}'
        if self.show_details:
            self.embed.description = textwrap.dedent(f"""
            {'TICKET INFO':-^50}
            {self.support.emojis['member']}Author: {self.bot.get_user(ticket['author'])}
            ⭐Author prestige: {ticket['prestige']}
            {self.support.emojis['members']}Other ticket members: {', '.join(other_ticket_members) if other_ticket_members else 'None'}
            🏠Server: {self.bot.get_guild(ticket['server'])}
            {self.presence_icon(ticket['status'])}Ticket status: {STATUS_DICT.get(ticket['status'], 'Unknown')}
            {self.support.emojis['bell'] if self.ticket_member['notifications'] else self.support.emojis['bellMute']}DM Notifications: {self.ticket_member['notifications']}
            """)
        self.embed.description += textwrap.dedent(f"""
            \n{conversation_header}
            Page {self.current_page + 1} of {len(self.conversation_pages)}\n
            """)
        for entry in self.conversation_pages[self.current_page]:
            self.embed.add_field(
                name=f"{self.bot.get_user(entry['author']).display_name} • {(entry['timestamp'] + datetime.timedelta(hours=(await utility.time_zone(ticket_server) if ticket_server else -4))):%b %d, %Y • %I:%M %p} {await utility.name_zone(ticket_server) if ticket_server else 'EST'}",
                value=f'> {entry["message"]}',
                inline=False,
            )

    def update_page_buttons(self):
        """Updates the next/previous page buttons"""
        if self.current_page == 0:
            self.prev_button.disabled = True
        elif self.current_page != 0 and self.prev_button.disabled:
            self.prev_button.disabled = False
        if self.current_page == len(self.conversation_pages) - 1:
            self.next_button.disabled = True
        elif self.current_page != len(self.conversation_pages) - 1 and self.next_button.disabled:
            self.next_button.disabled = False

    def presence_icon(self, status: int) -> discord.Emoji:
        """Returns the emoji corresponding to the ticket's status integer"""
        match status:
            case 0:
                return self.support.emojis['dnd']
            case 1 | 2:
                return self.support.emojis['idle']
            case 3:
                return self.support.emojis['online']
            case 4:
                return self.support.emojis['hiddenVoiceChannel']
            case _:
                return self.support.emojis['offline']

    async def setup(self):
        await self.create_embed()
        await self.populate_embed()

    class BackButton(discord.ui.Button):
        """Returns to the ticket browser"""

        def __init__(self, bot: commands.Bot) -> None:
            # can't do self.view emojis here, need to use support.emojis
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=support.emojis['arrowLeft'], label='All tickets', row=0)
            self.bot: commands.Bot = bot

        async def callback(self, interaction: discord.Interaction):
            # Multi-ticket view
            view: SingleTicketView = self.view
            await view.populate_embed()
            await interaction.response.edit_message(embed=view.embed, view=TicketBrowseView(view.ctx, self.bot, view.tickets))

    class PreviousConversationPageButton(discord.ui.Button):
        """View the previous page of the ticket's conversation"""

        def __init__(self, bot: commands.Bot, current_page: int) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.gray, emoji=support.emojis['arrowBackward'], label='Previous page', disabled=current_page == 0, row=0
            )

        async def callback(self, interaction: discord.Interaction):
            # Previous page of ticket conversation
            view: SingleTicketView = self.view
            view.current_page -= 1
            await view.populate_embed()
            view.update_page_buttons()
            await interaction.response.edit_message(embed=view.embed, view=view)

    class ReplyButton(discord.ui.Button):
        """Reply to the ticket"""

        # only add this button if the member's permissions value is > 0
        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.blurple, emoji=support.emojis['reply'], label='Reply', row=0)

        async def callback(self, interaction: discord.Interaction):
            # Reply to the ticket
            view: SingleTicketView = self.view
            await interaction.response.send_modal(ReplyModal(view, view.ticket))
            # re-paginate conversation pages
            await view.populate_embed()

    class NextConversationPageButton(discord.ui.Button):
        """View the next page of the ticket's conversation"""

        def __init__(self, bot: commands.Bot, current_page: int, total_pages: int) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.gray,
                emoji=support.emojis['arrowForward'],
                label='Next page',
                disabled=current_page == total_pages - 1,
                row=0,
            )

        async def callback(self, interaction: discord.Interaction):
            # Next page of ticket conversation
            view: SingleTicketView = self.view
            view.current_page += 1
            await view.populate_embed()
            view.update_page_buttons()
            await interaction.response.edit_message(embed=view.embed, view=view)

    class NotificationsToggleButton(discord.ui.Button):
        """Toggle notifications for the ticket"""

        # need to retrieve ticket data for this one
        def __init__(self, bot: commands.Bot, notifications: bool) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.blurple if notifications else discord.ButtonStyle.gray,
                emoji=support.emojis[utility.TOGGLES[notifications]],
                label='Notifications',
                row=1,
            )

        async def callback(self, interaction: discord.Interaction):
            # Toggle notifications
            view: SingleTicketView = self.view
            view.ticket_member['notifications'] = not view.ticket_member['notifications']
            self.style = discord.ButtonStyle.blurple if view.ticket_member['notifications'] else discord.ButtonStyle.gray
            self.emoji = view.support.emojis[utility.TOGGLES[view.ticket_member['notifications']]]
            view.ticket['members'] = [view.ticket_member if member['id'] == view.ticket_member['id'] else member for member in view.ticket['members']]
            await database.UpdateSupportTicket(view.ticket['number'], view.ticket)
            await view.populate_embed()
            view.update_page_buttons()
            await interaction.response.edit_message(embed=view.embed, view=view)

    class MembersButton(discord.ui.Button):
        """View and manage members in the ticket"""

        def __init__(self, bot: commands.Bot, permissions: int, member_count: list) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.gray,
                emoji=support.emojis['members'],
                label='Add Members' if member_count < 4 else 'Add/Manage Members',
                disabled=permissions < 3,
                row=1,
            )

        async def callback(self, interaction: discord.Interaction):
            # Ticket member management
            try:
                view: SingleTicketView = self.view
                new_view = ManageTicketMembersView(view.tickets, view)
                await new_view.populate_embed()
                await interaction.response.edit_message(embed=view.embed, view=new_view)
            except:
                traceback.print_exc()

    class TicketDetailsToggle(discord.ui.Button):
        """Toggle the ticket details"""

        def __init__(self, bot: commands.Bot, show_details: bool) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.blurple if show_details else discord.ButtonStyle.gray,
                emoji=support.emojis[utility.TOGGLES[show_details]],
                label='Show ticket info',
                row=1,
            )

        async def callback(self, interaction: discord.Interaction):
            # Toggle the ticket details
            view: SingleTicketView = self.view
            view.show_details = not view.show_details
            self.style = discord.ButtonStyle.blurple if view.show_details else discord.ButtonStyle.gray
            self.emoji = view.support.emojis[utility.TOGGLES[view.show_details]]
            view.paginate_pages()
            await view.populate_embed()
            await interaction.response.edit_message(embed=view.embed, view=view)
            # if the ticket pagination changes, update the next/previous buttons

    class CloseTicketButton(discord.ui.Button):
        """Close the ticket"""

        # only add this button if a bot dev is viewing the ticket
        def __init__(self, bot: commands.Bot, ticket_status: int) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.red,
                emoji=bot.get_emoji(support.emojis['hiddenVoiceChannel']),
                label='Close ticket',
                disabled=ticket_status == 3,
                row=1,
            )
            self.bot = bot
            self.support = support

        async def callback(self, interaction: discord.Interaction):
            # Close the ticket
            view: SingleTicketView = self.view
            view.ticket['status'] = 3
            view.ticket['conversation'].append(
                {
                    'author': self.bot.user.id,
                    'timestamp': discord.utils.utcnow(),
                    'message': '*My developer has closed this support ticket. If you need further help, you may reopen this ticket by replying. Otherwise, it will automatically lock in 7 days.*',
                }
            )
            await database.UpdateSupportTicket(view.ticket['number'], view.ticket)
            await self.support.notify_members(view.ctx, view.ticket)
            # add an event to the antispam timed events queue to lock the ticket in 7 days
            lock_at = discord.utils.utcnow() + datetime.timedelta(days=7)
            event = {'type': 'lock_ticket', 'flavor': 'Automatically lock ticket', 'target': view.ticket['number'], 'expires': lock_at}
            if view.ticket['server']:
                await database.AppendTimedEvent(event)  # need to update this at some point
            await interaction.response.edit_message(embed=view.embed, view=view)


class ManageTicketMembersView(discord.ui.View):
    def __init__(self, tickets: list[dict], prev_view: SingleTicketView) -> None:
        super().__init__(timeout=600)
        self.tickets = tickets
        self.prev_view = prev_view
        self.embed = prev_view.embed
        self.support: Support = self.prev_view.bot.get_cog('Support')
        self.add_item(self.BackButton(self.prev_view.bot))
        if len(self.prev_view.ticket['members']) > 3 and self.prev_view.ctx.author.id in [m['id'] for m in self.prev_view.ticket['members'][3:]]:
            self.add_item(self.LeaveTicketButton(self.prev_view.bot))
        if len(self.prev_view.ticket['members']) > 3 and self.prev_view.ticket_member['permissions'] >= 3:
            self.add_item(
                self.ManageMembersDropdown(
                    self.prev_view.ctx,
                    self.prev_view.bot,
                    self.tickets,
                    self.prev_view.ticket,
                    self.prev_view.ticket['members'],
                    self.prev_view,
                    this_view=self,
                )
            )
        if self.prev_view.ticket_member['permissions'] >= 3:
            self.add_item(self.AddMembersDropdown(self.prev_view.bot))

    async def populate_embed(self, **kwargs):
        self.embed.clear_fields()
        ticket_server = self.prev_view.bot.get_guild(self.prev_view.ticket['server'])

        def messageCheck(message: discord.Message):
            return message.channel.id == self.prev_view.ctx.channel.id and message.author.id == self.prev_view.ctx.author.id

        def is_staff_member(member: discord.Member):
            return any(
                (
                    member.guild_permissions.administrator,
                    member.guild_permissions.manage_guild,
                    member.guild_permissions.manage_channels,
                    member.guild_permissions.manage_roles,
                    member.id == ticket_server.owner.id,
                )
            )

        member_flavor = [
            f'{self.prev_view.bot.get_user(u["id"])}{utility.NEWLINE}> {u["bio"]}{utility.NEWLINE}> Permissions: {PERMISSIONS[u["permissions"]]}'
            for u in self.prev_view.ticket['members']
        ]
        self.embed.description = f"""{kwargs.get("description", "")}\n\n**__{'TICKET MEMBERS': ^50}__\n\n{'Permanently included':-^40}**\n{utility.NEWLINE.join([f'👤{f}' for f in member_flavor[:3]])}"""
        if len(self.prev_view.ticket['members']) > 3:
            self.embed.description += textwrap.dedent(f"""
                \n**{'Added members':-^40}**
                *Manage an added member using the select menu*
                {utility.NEWLINE.join(
                    [f'{self.prev_view.support.emojis["member"]}{flavor}' for flavor in member_flavor[3:]]
                    ) if len(member_flavor) > 2 else 'None yet'
                }""")
        if self.prev_view.ctx.author.id == self.prev_view.ticket['author']:
            # self.embed.description += f'''\n\n**{'Add a member':-^40}**\nSend a message to search for a member to add, then react with the corresponding letter to add them{f'{NEWLINE}{NEWLINE}Moderators of {self.bot.get_guild(ticket["server"])} are listed below as suggestions. You may react with the letter next to their name to quickly add them, otherwise send a message to search for someone else' if ticket['server'] and len(staffMemberResults) > 0 else ''}'''
            self.embed.description += textwrap.dedent(f"""
                \n**{'Add a member':-^40}**
                *Use the dropdown menu to invite a member to this support ticket*
            """)

    class BackButton(discord.ui.Button):
        """Returns to the ticket viewer"""

        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=support.emojis['arrowLeft'], label='Back to conversation')

        async def callback(self, interaction: discord.Interaction):
            # Single ticket view
            view: ManageTicketMembersView = self.view
            prev_view: SingleTicketView = view.prev_view
            await prev_view.populate_embed()
            await interaction.response.edit_message(embed=prev_view.embed, view=prev_view)

    class LeaveTicketButton(discord.ui.Button):
        """Only visible to added members"""

        def __init__(self, bot: commands.Bot) -> None:
            super().__init__(style=discord.ButtonStyle.red, emoji='🚪', label='Leave ticket')

        async def callback(self, interaction: discord.Interaction):
            # Leave the ticket
            view: ManageTicketMembersView = self.view
            ticket = view.prev_view.ticket
            ticket['members'] = [member for member in ticket['members'] if member['id'] != interaction.user.id]
            ticket['conversation'].append(
                {
                    'author': view.prev_view.bot.user.id,
                    'timestamp': discord.utils.utcnow(),
                    'message': f'*{interaction.user.display_name} ({interaction.user.name}) left the ticket*',
                }
            )
            asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
            await view.prev_view.populate_embed()
            await interaction.response.edit_message(embed=view.prev_view.embed, view=view.prev_view)

    class AddMembersDropdown(discord.ui.MentionableSelect):
        """Only visible to members with permissions >= 2"""

        def __init__(self, bot: commands.Bot) -> None:
            super().__init__(placeholder='Add members...', custom_id='add_members', max_values=25)
            self.members: list[discord.Member] = []

        async def callback(self, interaction: discord.Interaction):
            # Update members
            self.members = []
            view: ManageTicketMembersView = self.view
            for mentionable in self.values:
                if isinstance(mentionable, discord.Member):
                    self.members.append(mentionable)
                else:
                    self.members += mentionable.members
            new_view = AddMembersConfirmationView(view.prev_view.ctx, view.prev_view.bot, view.prev_view.ticket, self.members, view)
            await new_view.populate_embed()
            await interaction.response.edit_message(embed=new_view.embed, view=new_view)

    class ManageMembersDropdown(discord.ui.Select):
        """Used to manage added members. Visible only to members with permissions >= 2, and if the ticket has an added member"""

        def __init__(
            self,
            ctx: commands.Context,
            bot: commands.Bot,
            tickets: list[dict],
            ticket: dict,
            members: list,
            prev_view: SingleTicketView,
            this_view,
            default: discord.Member = None,
        ) -> None:
            super().__init__(placeholder='Manage an added member...', min_values=1, max_values=1, custom_id='manage_members')
            self.ctx = ctx
            self.bot = bot
            self.tickets = tickets
            self.ticket = ticket
            self.members = members
            self.prev_view = prev_view
            self.this_view: ManageTicketMembersView = this_view
            for member in members[3:]:
                user = bot.get_user(member['id'])
                self.add_option(
                    label=f'{user.display_name} ({user.name})', value=member['id'], default=member['id'] == default.id if default else False
                )

        async def callback(self, interaction: discord.Interaction):
            # Bring up individual member management view
            try:
                view: ManageTicketMembersView = self.view
                new_view = ManageMemberView(
                    self.ctx,
                    self.bot,
                    self.bot.get_user(int(self.values[0])),
                    [m for m in self.members if m['id'] == int(self.values[0])][0],
                    self.tickets,
                    self.ticket,
                    view.embed,
                    self.this_view,
                    self.prev_view,
                )
                await interaction.response.edit_message(view=new_view)
            except:
                traceback.print_exc()


class AddMembersConfirmationView(discord.ui.View):
    def __init__(
        self, ctx: commands.Context, bot: commands.Bot, ticket: dict, members: list[discord.Member], prev_view: ManageTicketMembersView
    ) -> None:
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.ticket = ticket
        self.members = members
        self.prev_view = prev_view
        self.support: Support = self.bot.get_cog('Support')
        self.notify = False
        self.read_only = False
        self.add_item(self.CancelButton(self.bot))
        self.add_item(self.NotifyMembersToggle(self.bot, self.notify))
        self.add_item(self.ReadOnlyPermissionsToggle(self.bot, self.read_only))
        self.add_item(self.ConfirmButton(self.bot))

    async def populate_embed(self):
        self.embed = copy.deepcopy(self.prev_view.embed)
        self.embed.description += f'\n\n**__{"CONFIRM ADDING MEMBERS": ^50}__**\nCurrently adding {", ".join([m.display_name for m in self.members])}\nMembers with DMs disabled will need to use the `tickets` command to view their invite if you choose to notify them'

    class CancelButton(discord.ui.Button):
        """Cancel adding members"""

        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.red, emoji=support.emojis['arrowLeft'], label='Cancel')

        async def callback(self, interaction: discord.Interaction):
            # Cancel adding members
            view: AddMembersConfirmationView = self.view
            await interaction.response.edit_message(embed=view.prev_view.embed, view=view.prev_view)

    class NotifyMembersToggle(discord.ui.Button):
        """Toggle whether to notify members"""

        def __init__(self, bot: commands.Bot, notify: bool) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.blurple if notify else discord.ButtonStyle.gray,
                emoji=support.emojis[utility.TOGGLES[notify]],
                label='Notify members via DM',
            )

        async def callback(self, interaction: discord.Interaction):
            # Toggle whether to notify members
            view: AddMembersConfirmationView = self.view
            view.notify = not view.notify
            self.emoji = view.support.emojis[utility.TOGGLES[view.notify]]
            self.style = discord.ButtonStyle.blurple if view.notify else discord.ButtonStyle.gray
            await interaction.response.edit_message(view=view)

    class ReadOnlyPermissionsToggle(discord.ui.Button):
        """Toggle whether to give members read-only permissions"""

        def __init__(self, bot: commands.Bot, read_only: bool) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.blurple if read_only else discord.ButtonStyle.gray,
                emoji=support.emojis[utility.TOGGLES[read_only]],
                label='Add members as read-only',
            )

        async def callback(self, interaction: discord.Interaction):
            # Toggle whether to give members read-only permissions
            view: AddMembersConfirmationView = self.view
            view.read_only = not view.read_only
            self.emoji = view.support.emojis[utility.TOGGLES[view.read_only]]
            self.style = discord.ButtonStyle.blurple if view.read_only else discord.ButtonStyle.gray
            await interaction.response.edit_message(view=view)

    class ConfirmButton(discord.ui.Button):
        """Confirm adding members"""

        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.green, emoji=support.emojis['whiteCheck'], label='Confirm')

        async def callback(self, interaction: discord.Interaction):
            # Confirm adding members
            try:
                view: AddMembersConfirmationView = self.view
                ticket = view.ticket
                for member in view.members:
                    ticket['members'].append(
                        {'id': member.id, 'bio': member_server_prestige(member), 'permissions': 1 if view.read_only else 2, 'notifications': True}
                    )
                    ticket['conversation'].append(
                        {
                            'author': view.bot.user.id,
                            'timestamp': discord.utils.utcnow(),
                            'message': f'*{interaction.user.display_name} added {member.display_name} ({member.name}) to the ticket*',
                        }
                    )
                kwargs = {'notify': view.notify, 'read_only': view.read_only, 'description': ''}
                if view.notify:
                    for member in view.members:
                        try:
                            embed = discord.Embed(
                                title='🎟 Added to ticket',
                                description=f"{member.display_name},\n{interaction.user.display_name} ({interaction.user.name}) added you to *Disguard support ticket {ticket['number']}* with [{', '.join([view.bot.get_user(m['id']).display_name for i, m in enumerate(ticket['members']) if i not in (1, 2)])}].\n\nThe Disguard support ticket system is a tool for server members to easily contact my developer team for issues, help, and questions regarding Disguard",
                                color=utility.YELLOW[1],
                            )
                            embed.set_footer(
                                text=f'You are receiving this DM because {interaction.user.display_name} added you to a Disguard support ticket'
                            )
                            await member.send(embed=embed, view=AddedToTicketView(view.ctx, view.bot, ticket, embed))
                            kwargs['description'] += f'{member.display_name} successfully notified\n'
                        except Exception as e:
                            kwargs['description'] += f'Error notifying {member}: {e}\n'
                            # BTW, error code 50007 means that the recipient disabled DMs from server members - they will need to temporarily allow this in the `Server Options > Privacy Settings` or `User Settings > Privacy & Safety` in order to be invited')
                else:
                    kwargs['description'] = f'Successfully added {", ".join([m.display_name for m in view.members])} to the ticket'
                single_ticket_view = SingleTicketView(view.ctx, view.bot, view.prev_view.prev_view.tickets, ticket)
                await single_ticket_view.setup()
                new_view = ManageTicketMembersView(view.prev_view.prev_view.tickets, single_ticket_view)
                await new_view.populate_embed(**kwargs)
                await interaction.response.edit_message(embed=new_view.embed, view=new_view)
                asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
            except:
                traceback.print_exc()


class AddedToTicketView(discord.ui.View):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, ticket: dict, embed: discord.Embed) -> None:
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.ticket = ticket
        self.embed = embed
        self.support: Support = self.bot.get_cog('Support')
        self.add_item(self.LeaveButton(self.bot))
        self.add_item(OpenTicketButton(self.ctx, self.bot, self.ticket['number'], label='View ticket'))

    class LeaveButton(discord.ui.Button):
        """Leave the ticket"""

        def __init__(self, bot: commands.Bot) -> None:
            super().__init__(style=discord.ButtonStyle.red, emoji='🚪', label='Leave ticket')

        async def callback(self, interaction: discord.Interaction):
            # Leave the ticket
            view: AddedToTicketView = self.view
            ticket = view.ticket
            ticket['members'] = [member for member in ticket['members'] if member['id'] != interaction.user.id]
            ticket['conversation'].append(
                {
                    'author': view.bot.user.id,
                    'timestamp': discord.utils.utcnow(),
                    'message': f'*{interaction.user.display_name} ({interaction.user.name}) left the ticket*',
                }
            )
            asyncio.create_task(database.UpdateSupportTicket(ticket['number'], ticket))
            view.embed.description = 'You have left this ticket'
            await interaction.response.edit_message(embed=view.embed, view=None)


class ManageMemberView(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        bot: commands.Bot,
        member: discord.User,
        ticket_member: dict,
        tickets: list[dict],
        ticket: dict,
        embed: discord.Embed,
        prev_view: ManageTicketMembersView,
        ticket_view: SingleTicketView,
    ) -> None:
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.member = member
        self.ticket_member = ticket_member
        self.tickets = tickets
        self.ticket = ticket
        self.embed = embed
        self.prev_view = prev_view
        self.ticket_view = ticket_view
        self.support: Support = self.bot.get_cog('Support')
        self.add_item(
            prev_view.ManageMembersDropdown(
                self.ctx, self.bot, self.tickets, self.ticket, self.ticket['members'], self.ticket_view, self.prev_view, self.member
            )
        )
        self.add_item(self.AdjustPermissionsDropdown(self.bot, self.ticket_member))
        self.add_item(self.BackButton(self.bot))
        self.add_item(self.RemoveMemberButton(self.bot, self.member))

    class BackButton(discord.ui.Button):
        """Returns to the ticket viewer"""

        def __init__(self, bot: commands.Bot) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.gray, emoji=support.emojis['arrowLeft'], label='Back to members')

        async def callback(self, interaction: discord.Interaction):
            # Manage members view
            view: ManageMemberView = self.view
            new_view = ManageTicketMembersView(view.tickets, view.ticket_view)
            await new_view.populate_embed()
            await interaction.response.edit_message(embed=new_view.embed, view=new_view)

    class AdjustPermissionsDropdown(discord.ui.Select):
        """Used to adjust permissions for an added member"""

        def __init__(self, bot: commands.Bot, ticket_member: dict) -> None:
            super().__init__(
                placeholder=f'Permissions: {PERMISSIONS[ticket_member["permissions"]]}', min_values=1, max_values=1, custom_id='adjust_permissions'
            )
            self.fill_options(ticket_member)

        def fill_options(self, ticket_member: dict):
            self.options = []
            for index, permission in PERMISSIONS.items():
                if 1 <= index <= 3:
                    self.add_option(label=f'Permissions: {permission}', value=index, default=index == ticket_member['permissions'])

        async def callback(self, interaction: discord.Interaction):
            # Adjust permissions
            try:
                view: ManageMemberView = self.view
                view.ticket_member['permissions'] = int(self.values[0])
                self.fill_options(view.ticket_member)
                view.ticket['members'] = [m if m['id'] != view.ticket_member['id'] else view.ticket_member for m in view.ticket['members']]
                view.ticket['conversation'].append(
                    {
                        'author': view.bot.user.id,
                        'timestamp': discord.utils.utcnow(),
                        'message': f'*{interaction.user.display_name} updated {view.member.display_name}\'s permissions to `{PERMISSIONS[view.ticket_member["permissions"]]}`*',
                    }
                )
                asyncio.create_task(database.UpdateSupportTicket(view.ticket['number'], view.ticket))
                await interaction.response.edit_message(view=view)
            except:
                traceback.print_exc()

    class RemoveMemberButton(discord.ui.Button):
        """Remove an added member"""

        def __init__(self, bot: commands.Bot, member: discord.User) -> None:
            bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.red, emoji='🥾', label=f'Remove {member.display_name} from ticket')

        async def callback(self, interaction: discord.Interaction):
            # Remove an added member
            try:
                view: ManageMemberView = self.view
                view.ticket['members'] = [m for m in view.ticket['members'] if m['id'] != view.ticket_member['id']]
                view.ticket['conversation'].append(
                    {
                        'author': view.bot.user.id,
                        'timestamp': discord.utils.utcnow(),
                        'message': f'*{interaction.user.display_name} removed {view.member.display_name} ({view.member.name}) from the ticket*',
                    }
                )
                asyncio.create_task(database.UpdateSupportTicket(view.ticket['number'], view.ticket))
                kwargs = {'description': f'Successfully removed {view.member.display_name} from the ticket'}
                await view.prev_view.populate_embed(**kwargs)
                await interaction.response.edit_message(embed=view.prev_view.embed, view=view.prev_view)
            except:
                traceback.print_exc()


class DMNotificationView(discord.ui.View):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, ticket: dict, user: discord.User) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx
        self.bot = bot
        self.ticket = ticket
        self.user = user
        self.support: Support = self.bot.get_cog('Support')
        self.add_item(self.NotificationsButton(self.bot, [m for m in self.ticket['members'] if m['id'] == self.user.id][0]['notifications']))
        self.add_item(OpenTicketButton(self.ctx, self.bot, self.ticket['number'], label='View ticket'))

    class NotificationsButton(discord.ui.Button):
        """Toggle whether to receive notifications for this ticket"""

        def __init__(self, bot: commands.Bot, notifications: bool) -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(
                style=discord.ButtonStyle.blurple if notifications else discord.ButtonStyle.gray,
                emoji=support.emojis[utility.TOGGLES[notifications]],
                label='Notifications',
            )
            self.notifications = notifications

        async def callback(self, interaction: discord.Interaction):
            # Toggle whether to receive notifications for this ticket
            view: DMNotificationView = self.view
            self.notifications = not self.notifications
            self.style = discord.ButtonStyle.blurple if self.notifications else discord.ButtonStyle.gray
            self.emoji = view.support.emojis[utility.TOGGLES[self.notifications]]
            view.ticket['members'] = [
                m
                if m['id'] != view.user.id
                else {'id': m['id'], 'bio': m['bio'], 'permissions': m['permissions'], 'notifications': not m['notifications']}
                for m in view.ticket['members']
            ]
            asyncio.create_task(database.UpdateSupportTicket(view.ticket['number'], view.ticket))
            await interaction.response.edit_message(view=view)

    class OpenTicketButton(discord.ui.Button):
        """Open the ticket"""

        def __init__(self, bot: commands.Bot, ticket_number: int, label: str = 'View ticket') -> None:
            support: Support = bot.get_cog('Support')
            super().__init__(style=discord.ButtonStyle.blurple, emoji=support.emojis['reply'], label=label)
            self.ticket_number = ticket_number

        async def callback(self, interaction: discord.Interaction):
            # Open the ticket
            view: DMNotificationView = self.view
            tickets = await database.GetSupportTickets()
            single_ticket_view = SingleTicketView(view.ctx, view.bot, tickets, tickets[self.ticket_number])
            await single_ticket_view.setup()
            await interaction.response.edit_message(embed=single_ticket_view.embed, view=single_ticket_view)


class SelectASupportServerView(discord.ui.View):
    def __init__(self, bot: commands.Bot, servers: list[discord.Guild], dropdown: discord.ui.Select, custom_id) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.servers = servers
        self.custom_id = custom_id
        self.add_item(dropdown)


class SelectASupportServer(discord.ui.Select):
    def __init__(self, servers: list[discord.Guild], custom_id) -> None:
        super().__init__(placeholder='Select a server...', min_values=1, max_values=1, custom_id=custom_id)
        self.servers = servers
        for server in servers:
            self.add_option(label=server.name, value=server.id)
        self.add_option(label='Prefer not to answer', value='None')

    async def callback(self, interaction: discord.Interaction):
        # await interaction.response.pong()
        await interaction.message.delete()


class SupportModal(discord.ui.Modal):
    def __init__(self, ctx: commands.Context, bot: commands.Bot):
        super().__init__(title='Create a support ticket')
        self.support: Support = bot.get_cog('Support')
        self.ctx = ctx
        self.bot = bot

    body = discord.ui.TextInput(style=discord.TextStyle.long, label='Please describe your scenario', placeholder='Blank space', max_length=2000)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        traceback.print_exc()

    async def on_submit(self, interaction: discord.Interaction):
        color_theme = await utility.color_theme(interaction.guild) if interaction.guild else 1
        # If the user didn't provide a message with the command, prompt them with one here
        if not interaction.guild:
            serverList = [g for g in self.bot.guilds if g.get_member(self.ctx.author.id)]
            if len(serverList) > 2:  # If the member is in more than one server with the bot, prompt for which server they're in
                dropdown = SelectASupportServer(serverList, str(self.ctx.message.id))
                view = SelectASupportServerView(self.bot, serverList, dropdown, str(self.ctx.message.id))
                await interaction.channel.send('If this issue relates to a specific server, select it from the dropdown menu below', view=view)

                def interaction_check(i: discord.Interaction):
                    return i.data['custom_id'] == str(self.ctx.message.id) and i.user.id == self.ctx.author.id

                try:
                    response = await self.bot.wait_for('interaction', check=interaction_check, timeout=600)
                except asyncio.TimeoutError:
                    return await interaction.edit_original_response(content='Timed out')
                if not dropdown.values[0]:
                    server = None
                else:
                    server = self.bot.get_guild(int(response.data['values'][0]))
            else:
                server = serverList[0]
        else:
            server = interaction.guild
        embed = discord.Embed(
            title='🎟 Disguard Ticket System', description=f'{self.support.loading} Creating Ticket...', color=utility.YELLOW[color_theme]
        )
        await interaction.response.send_message(embed=embed)
        ticket = await self.support.create_support_ticket(self.ctx, server, self.body.value)
        embed.description = f"""Your support ticket has successfully been created.\n\nTicket number: {ticket['number']}\nAuthor: {self.ctx.author.name}\nMessage: `{self.body.value}`\n\nTo view or manage this ticket, use the button below or the `/tickets` command."""
        new_view = SupportTicketFollowUp(self.ctx, self.bot, ticket['number'])
        await interaction.edit_original_response(embed=embed, view=new_view)
        devManagement = self.bot.get_channel(681949259192336406)
        await devManagement.send(embed=embed)


class ReplyModal(discord.ui.Modal):
    """Popup modal to respond to a ticket"""

    def __init__(self, view: SingleTicketView, ticket: dict) -> None:
        super().__init__(title=f'Reply to ticket {ticket["number"]}')
        self.view = view
        self.ticket = ticket
        self.last_message = ticket['conversation'][-1]

    body = discord.ui.TextInput(style=discord.TextStyle.long, label='Reply to the ticket...', placeholder='Reply to the ticket...', max_length=1024)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        traceback.print_exc()

    async def on_submit(self, interaction: discord.Interaction):
        self.view.ticket['conversation'].append({'author': interaction.user.id, 'timestamp': discord.utils.utcnow(), 'message': self.body.value})
        if self.view.ticket['status'] != 2:
            self.view.ticket['status'] = 2
        asyncio.create_task(database.UpdateSupportTicket(self.view.ticket['number'], self.view.ticket))
        await self.view.populate_embed()
        await self.view.support.notify_members(self.view.ctx, self.view.ticket)
        await interaction.response.edit_message(embed=self.view.embed, view=self.view)


class SupportTicketFollowUp(discord.ui.View):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, ticket_number: int):
        super().__init__()
        self.ctx = ctx
        self.bot = bot
        self.ticket_number = ticket_number
        self.add_item(OpenTicketButton(ctx, bot, ticket_number))


class OpenTicketButton(discord.ui.Button):
    """A customizable button to open a support ticket with the given number"""

    def __init__(
        self,
        ctx: commands.Context,
        bot: commands.Bot,
        ticket_number: int,
        label: str = 'Open ticket',
        emoji: str = '🎟',
        custom_id: str = 'openTicket',
    ):
        super().__init__(style=discord.ButtonStyle.blurple, label=label, emoji=emoji, custom_id=custom_id)
        self.ctx = ctx
        self.bot = bot
        self.ticket_number = ticket_number

    async def callback(self, interaction: discord.Interaction):
        try:
            tickets = await database.GetSupportTickets()
            single_ticket_view = SingleTicketView(self.view.ctx, self.view.bot, tickets, tickets[self.ticket_number])
            await single_ticket_view.setup()
            await interaction.response.edit_message(embed=single_ticket_view.embed, view=single_ticket_view)
        except:
            traceback.print_exc()


class CreateTicketButton(discord.ui.Button):
    """A customizable button to open the interactive modal to create a new support ticket"""

    def __init__(self, ctx: commands.Context, bot: commands.Bot, label: str = 'Create a ticket', emoji: str = '🎟', custom_id: str = 'createTicket'):
        super().__init__(style=discord.ButtonStyle.gray, label=label, emoji=emoji, custom_id=custom_id)
        self.ctx = ctx
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SupportModal(self.ctx, self.bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(Support(bot))
