"""Contains all the code for Disguard's reddit-related features"""

import asyncio
import datetime
import re
import traceback

import asyncpraw
import colour
import discord
from discord import app_commands
from discord.ext import commands, tasks

import database
import utility

NEWLINE = '\n'
REDDIT_COLOR = 0xFF5700
TOGGLES = {True: 'slideToggleOn', False: 'slideToggleOff'}


class Reddit(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot: commands.Bot = bot
        self.redditThreads: dict[int, dict[str, dict]] = {}
        self.reddit = asyncpraw.Reddit(user_agent='Portal for Disguard - Auto link & reddit feed functionality. --RV9k--')
        self.emojis: dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis

    @tasks.loop(hours=1)
    async def syncRedditFeeds(self):
        """Goes through all servers and ensures reddit feeds are working"""
        print('Syncing Reddit feeds')
        try:
            for server in self.bot.guilds:
                asyncio.create_task(self.redditFeedHandler(server), name=f'Reddit feed handler for {server.name}')
        except:
            print('Reddit sync fail: ')
            traceback.print_exc()

    async def redditFeedHandler(self, server: discord.Guild):
        """Handles starting/stopping of reddit feeds for servers, along with ensuring there are no duplicates, etc."""
        runningFeeds = [feed for feed in self.redditThreads.get(server.id, {}).keys()]
        server_data = await utility.get_server(server)
        if not server_data:
            return
        proposedFeeds = [subreddit for subreddit, data in server_data.get('redditFeeds', {}).items() if self.bot.get_channel(data['channel'])]
        feedsToCreate = [
            entry
            for subreddit, entry in server_data.get('redditFeeds', {}).items()
            if subreddit not in runningFeeds and self.bot.get_channel(entry['channel'])
        ]
        feedsToDelete = [entry for entry in runningFeeds if entry not in proposedFeeds]
        for feed in feedsToCreate:
            asyncio.create_task(self.createRedditStream(server, feed), name=f'Create Reddit stream for {server.name}: {feed["subreddit"]}')
        for feed in feedsToDelete:
            self.redditThreads[server.id].pop(feed, None)

    async def createRedditStream(self, server: discord.Guild, data: dict, attempt=0):
        """Data represents a singular subreddit customization data"""
        print(f'creating reddit stream for {server.name}: {data["subreddit"]}', attempt)
        if attempt > 2:
            return self.redditThreads[server.id].pop(data['subreddit'])  # This will get picked up in the next syncRedditFeeds loop
        if self.redditThreads.get(server.id) and data['subreddit'] in self.redditThreads[server.id].keys():
            return  # We already have a thread running for this server & subreddit
        channel = self.bot.get_channel(data['channel'])
        subreddit = await self.reddit.subreddit(data['subreddit'], fetch=True)
        try:
            self.redditThreads[server.id][data['subreddit']] = data  # Marks that we have a running thread for this server & subreddit
        except KeyError:
            self.redditThreads[server.id] = {data['subreddit']: data}
        try:
            async for submission in subreddit.stream.submissions(skip_existing=True):
                try:
                    if data['subreddit'] not in self.redditThreads[server.id].keys():
                        return  # This feed has been cancelled
                    embed = await self.redditSubmissionEmbed(
                        server,
                        submission,
                        True,
                        data['truncateTitle'],
                        data['truncateText'],
                        data['media'],
                        data['creditAuthor'],
                        data['color'],
                        data['timestamp'],
                        channel=channel,
                    )
                    await channel.send(embed=embed)
                except:
                    print('reddit feed submission error')
                    traceback.print_exc()
        except:
            print(f'reddit feed error: {server.name} {server.id}')
            traceback.print_exc()
            await asyncio.sleep(60)
            asyncio.create_task(
                self.createRedditStream(server, data, attempt + 1), name=f'Retry - Create Reddit stream for {server.name}: {data["subreddit"]}'
            )

    async def on_message(self, message: discord.Message):
        await asyncio.gather(*[self.redditAutocomplete(message), self.redditEnhance(message)])

    async def redditAutocomplete(self, message: discord.Message):
        try:
            config = (await utility.get_server(message.guild))['redditComplete']
        except KeyError:
            return
        if not config:
            return  # Feature is disabled
        matches = re.findall(r'^r\/([A-Za-z0-9_]+)$', message.content)
        for match in matches:
            result = await self.subredditEmbed(match, config == 1)
            if config == 1:
                await message.channel.send(result)
            else:
                await message.channel.send(embed=result)

    async def redditEnhance(self, message: discord.Message):
        try:
            config = (await utility.get_server(message.guild))['redditEnhance']
        except KeyError:
            return
        if not config:
            return  # Feature is disabled
        if config[0]:
            matches_submission = re.findall(r'^https?:\/\/(?:www\.)?(?:old\.)?reddit\.com\/r\/\w+\/comments\/([A-Za-z0-9]+\w+)', message.content)
        else:
            matches_submission = []
        if config[1]:
            matches_subreddit = re.findall(r'^https?:\/\/(?:www\.)?(?:old\.)?reddit\.com\/r\/([A-Za-z0-9_]+)\/$', message.content)
        else:
            matches_subreddit = []
        if not any([matches_subreddit, matches_submission]):
            return
        for match in matches_subreddit:
            try:
                embed = await self.subredditEmbed(match, False)
                await message.channel.send(embed=embed)
            except Exception as e:
                await message.channel.send(f'Error retrieving subreddit info: {e}')
        for match in matches_submission:
            try:
                embed = await self.redditSubmissionEmbed(message.guild, match, False, channel=message.channel)
                await message.channel.send(embed=embed)
            except Exception as e:
                await message.channel.send(f'Error retrieving submission info: {e}')
                traceback.print_exc()
        if message.channel.permissions_for(message.guild.me).manage_messages:
            message = await message.channel.fetch_message(message.id)
            # Suppress the Discord embed for the user's link
            if not message.embeds:

                def check(b: discord.Message, a: discord.Message):
                    return b.id == message.id and len(a.embeds) > len(b.embeds)

                result = (await self.bot.wait_for('message_edit', check=check))[1]
            else:
                result = message
            await result.edit(suppress=True)

    async def subredditEmbed(self, search, plainText=False):
        subreddit = await self.reddit.subreddit(search, fetch=True)
        url = f'https://www.reddit.com{subreddit.url}'
        if plainText:
            return f'<{url}>'
        else:
            keyColor = subreddit.key_color or subreddit.primary_color or '#2E97E5'  # The last one is the default blue
            embed = discord.Embed(
                title=f'r/{subreddit.display_name}',
                description=f"""{subreddit.public_description}\n\n{subreddit.subscribers} subscribers • {subreddit.active_user_count} online\n{f"{self.emojis['alert']}This subreddit is NSFW" if subreddit.over18 else ""}""",
                color=utility.hexToColor(keyColor),
                url=url,
            )
            embed.set_thumbnail(url=subreddit.icon_img)
            embed.set_image(url=subreddit.banner_background_image)
            return embed

    async def redditSubmissionEmbed(
        self,
        g,
        source,
        redditFeed=False,
        truncateTitle=100,
        truncateText=400,
        media=3,
        creditAuthor=True,
        color='colorCode',
        timestamp=True,
        channel=None,
    ):
        """Media - 0: All off, 1: Only thumbnail, 2: Only images, 3: All on"""
        if truncateTitle < 1:
            truncateTitle = 256
        if truncateText < 1:
            truncateText = 1900
        if type(source) is str:
            if 'https://' in source:
                submission = await self.reddit.submission(url=source)
            else:
                submission = await self.reddit.submission(id=source)
        else:
            submission = source
        author = submission.author
        await author.load()
        subreddit = submission.subreddit
        await subreddit.load()
        if submission.is_self:
            submissionType, linkFlavor = 'text', ''
        elif submission.is_video:
            submissionType, url = (
                'video',
                submission.media['reddit_video']['fallback_url'][: submission.media['reddit_video']['fallback_url'].find('?source=')],
            )
            linkFlavor = f"\n[Direct video link]({url} '{url}')"
        elif 'i.redd.it' in submission.url:
            submissionType, linkFlavor = 'image', ''
        elif 'www.reddit.com/gallery' in submission.url:
            submissionType, linkFlavor = 'gallery', f"\n[Gallery view]({submission.url} '{submission.url}')"
        else:
            submissionType, linkFlavor = 'link', f"\n[{utility.basicURL(submission.url)}]({submission.url} '{submission.url}')"
        flagForNSFW = submission.over_18 and channel and not channel.is_nsfw()
        typeKeys = {'text': '📜', 'video': self.emojis['camera'], 'image': self.emojis['images'], 'link': '🔗', 'gallery': self.emojis['details']}
        awards = submission.total_awards_received
        keyColor = subreddit.key_color or subreddit.primary_color or '#2E97E5'  # The last one is the default blue
        if redditFeed:
            description = f"""{typeKeys[submissionType]}{submissionType[0].upper()}{submissionType[1:]} post • r/{subreddit.display_name}{linkFlavor}{f"{NEWLINE}👀(Spoiler)" if submission.spoiler else ""}{f"{NEWLINE}{self.emojis['alert']} NSFW" if submission.over_18 else ""}"""
        else:
            description = f"""{submissionType[0].upper()}{submissionType[1:]} post\n{submission.score} upvote{"s" if submission.score != 1 else ""} • {round(submission.upvote_ratio * 100)}% upvoted{f" • {awards} awards" if awards > 0 else ""}{f" • {submission.view_count} " if submission.view_count else ""} • {submission.num_comments} comment{"s" if submission.num_comments != 1 else ""} on r/{subreddit.display_name}{linkFlavor}{f"{NEWLINE}👀(Spoiler)" if submission.spoiler else ""}{f"{NEWLINE}{self.emojis['alert']}(NSFW)" if submission.over_18 else ""}"""
        embed = discord.Embed(
            title=f'{"🔒" if submission.locked and not redditFeed else ""}{"📌" if submission.stickied and not redditFeed else ""}{(submission.title[:truncateTitle] + "…") if len(submission.title) > truncateTitle else submission.title}',
            description=description,
            color=utility.hexToColor(keyColor) if color == 'colorCode' else utility.hexToColor(color),
            url=f'https://www.reddit.com{submission.permalink}',
        )
        if submissionType == 'text':
            embed.description += (
                f'\n\n{(submission.selftext[:truncateText] + "…") if len(submission.selftext) > truncateText else submission.selftext}'
            )
        if creditAuthor > 0:
            embed.set_author(name=author.name if creditAuthor != 2 else None, icon_url=author.icon_img if creditAuthor != 1 else None)
        if media > 0 and not flagForNSFW:
            if media != 2:
                embed.set_thumbnail(url=subreddit.icon_img)
            if submissionType == 'image':
                if redditFeed and media != 1:
                    embed.set_image(url=submission.url)
                elif not redditFeed:
                    embed.set_thumbnail(url=submission.url)
        if timestamp and not flagForNSFW:
            embed.set_footer(
                text=f'{"Posted " if not redditFeed else ""}{(datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=submission.created_utc) + datetime.timedelta(hours=await utility.time_zone(g))):%b %d, %Y • %I:%M %p} {await utility.name_zone(g)}'
            )
        if channel and flagForNSFW:
            embed.title = f"{self.emojis['alert']} | Title hidden: NSFW submission & this is not a NSFW channel"
            embed.description = f'r/{subreddit.display_name}\n\nTo comply with Discord guidelines, I cannot share content from NSFW reddit submissions to SFW Discord channels'
        return (embed, submission.over_18) if not channel else embed

    @commands.hybrid_group(fallback='settings')
    @commands.guild_only()
    async def reddit(self, ctx: commands.Context):
        """View the Reddit features & settings for this server"""
        server_data = await utility.get_server(ctx.guild)
        embed = self.reddit_settings_embed(ctx.guild, server_data)
        await ctx.send(embed=embed, view=self.RedditSettingsView(self.bot, ctx, server_data))

    @reddit.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True, manage_channels=True)
    async def create_feed(self, ctx: commands.Context, subreddit: str, channel: discord.TextChannel = None):
        """
        Create a Reddit feed
        ----------------------
        Parameters:
        subreddit: str
            The name or URL of the subreddit to create a feed for
        channel: discord.TextChannel
            The channel to send the feed to, defaults to the current channel
        """
        matches = re.findall(r'(?:r\/)?([A-Za-z0-9_]+)$', subreddit)
        if matches:
            subreddit = matches[0]
        else:
            return await ctx.send(f'No results found for `r/{subreddit}`. Please ensure the subreddit exists, and is public, and try again.')
        if subreddit in self.redditThreads.get(ctx.guild.id, {}).keys():
            return await ctx.send(
                f'There is already a feed in this server for r/{subreddit}. Use `/reddit edit_feed {subreddit}` to edit the settings for this feed or `/reddit delete_feed {subreddit}` to delete it.'
            )
        feed = {
            'subreddit': subreddit.lower(),
            'channel': channel.id if channel else ctx.channel.id,
            'truncateTitle': 100,
            'truncateText': 400,
            'media': 3,
            'creditAuthor': 3,
            'color': 'colorCode',
            'timestamp': True,
        }
        asyncio.create_task(self.createRedditStream(ctx.guild, feed), name=f'command - Create Reddit stream for {ctx.guild.name}: {subreddit}')
        await database.create_reddit_feed(ctx.guild, feed)
        await ctx.send(
            f'Successfully set up a feed for r/{subreddit} inside {channel.mention if channel else ctx.channel.mention}.\nEdit the default settings with `/reddit edit_feed {subreddit}` or on the web dashboard.'
        )

    @reddit.command()
    @commands.guild_only()
    async def edit_feed(
        self,
        ctx: commands.Context,
        subreddit: str,
        channel: discord.TextChannel = None,
        truncate_title: int = None,
        truncate_text: int = None,
        media: int = None,
        display_author: int = None,
        color: str = None,
        timestamp: bool = None,
    ):
        """
        Edit a Reddit feed
        ----------------------
        Parameters:
        subreddit: str
            The subreddit to edit a feed for
        channel: discord.TextChannel
            The channel to send the feed to
        truncate_title: int
            The number of characters to truncate the title to
        truncate_text: int
            The number of characters to truncate the body text to
        media: int
            Whether to display subreddit logo: 0 for False, 1 for thumbnail, 2 for image, 3 for both
        display_author: int
            Whether to display submission author: 0 for False, 1 for avatar, 2 for name, 3 for both
        color: str
            The embed color: search for a common color or type a hex code for a custom color
        timestamp: str
            Whether to include submission timestamp: either "True" or "False"
        """
        current_feed = self.redditThreads.get(ctx.guild.id, {}).get(subreddit.lower(), None)
        if not current_feed:
            return await ctx.send(f'There is no feed set up for r/{subreddit}')
        settings = {
            'subreddit': subreddit.lower(),
            'channel': channel.id if channel else current_feed['channel'],
            'truncateTitle': truncate_title if truncate_title else current_feed['truncateTitle'],
            'truncateText': truncate_text if truncate_text else current_feed['truncateText'],
            'media': media if media else current_feed['media'],
            'creditAuthor': display_author if display_author else current_feed['creditAuthor'],
            'color': color if color else current_feed['color'],
            'timestamp': timestamp if timestamp else current_feed['timestamp'],
        }
        self.redditThreads[ctx.guild.id].update({subreddit: settings})
        await ctx.send(f'Successfully edited the feed for r/{subreddit}.')

    @reddit.command()
    @commands.guild_only()
    async def delete_feed(self, ctx: commands.Context, subreddit: str):
        """
        Delete a Reddit feed
        ----------------------
        Parameters:
        subreddit: str
            The subreddit name to delete the feed for
        """
        self.redditThreads[ctx.guild.id].pop(subreddit.lower(), None)
        await database.delete_reddit_feed(ctx.guild, subreddit.lower())
        await ctx.send(f'Successfully deleted the feed for r/{subreddit}.')

    """Autocompletes"""

    @edit_feed.autocomplete('subreddit')
    @delete_feed.autocomplete('subreddit')
    async def autocomplete_subreddit(self, interaction: discord.Interaction, argument: str):
        return [
            app_commands.Choice(name=subreddit, value=subreddit)
            for subreddit in self.redditThreads[interaction.guild_id].keys()
            if subreddit.startswith(argument.lower())
        ][:25]

    @edit_feed.autocomplete('media')
    async def autocomplete_media(self, interaction: discord.Interaction, argument: str):
        return [
            app_commands.Choice(name=value, value=key)
            for key, value in {
                '0': 'Disabled',
                '1': 'Only subreddit logo',
                '2': 'Only submission media, when applicable',
                '3': 'Both (default)',
            }.items()
            if argument in value or argument == key
        ]

    @edit_feed.autocomplete('display_author')
    async def autocomplete_creditAuthor(self, interaction: discord.Interaction, argument: str):
        return [
            app_commands.Choice(name=value, value=key)
            for key, value in {'0': 'Disabled', '1': 'Only avatar', '2': 'Only name', '3': 'Both (default)'}.items()
            if argument in value or argument == key
        ]

    @edit_feed.autocomplete('color')
    async def autocomplete_color(self, interaction: discord.Interaction, argument: str):
        has_hex = re.search(r'#(?:[0-9a-fA-F]{3}){1,2}', argument)
        if has_hex:
            color = colour.Color(argument)
            return [app_commands.Choice(name=f'Custom color: {color}', value=argument)]
        else:
            color_classmethods = [func if func != 'default' else 'black' for func, obj in vars(discord.Color).items() if isinstance(obj, classmethod)]
            color_classmethods.remove('from_rgb')
            color_classmethods.remove('from_hsv')
            color_classmethods.remove('from_str')
            color_classmethods.remove('random')
            colors = {str(func): eval(f'discord.Color.{func}()') for func in color_classmethods}
            choices = [] if argument else [app_commands.Choice(name='Match subreddit color (default)', value='colorCode')]
            choices += [app_commands.Choice(name=name, value=str(hex)) for name, hex in colors.items() if name.startswith(argument)]
            return choices[:25]

    class RedditSettingsView(discord.ui.View):
        class AutocompleteButton(discord.ui.Button):
            def __init__(self, bot: commands.Bot, emojis: dict, server_data: dict):
                colored = True if server_data['redditComplete'] else False
                flavor = {0: 'disabled', 1: 'link only', 2: 'link + embed'}
                super().__init__(
                    emoji=emojis[TOGGLES[colored]],
                    label=f'Autolink: {flavor[server_data["redditComplete"]]}',
                    style=discord.ButtonStyle.blurple if colored else discord.ButtonStyle.gray,
                    custom_id='autocomplete',
                )
                self.reddit: Reddit = bot.get_cog('Reddit')
                self.emojis = emojis
                self.server_data = server_data

            async def callback(self, interaction: discord.Interaction):
                reverse_flavor = {'disabled': 0, 'link only': 1, 'link + embed': 2}
                current_value = reverse_flavor[self.label.split(': ')[1]]
                new_value = (current_value + 1) % 3
                self.label = f'Autolink: {list(reverse_flavor.keys())[new_value]}'
                await database.edit_server_data(interaction.guild, 'redditComplete', new_value)
                self.server_data['redditComplete'] = new_value
                self.style = discord.ButtonStyle.blurple if new_value else discord.ButtonStyle.gray
                self.emoji = self.emojis[TOGGLES[bool(new_value)]]
                new_embed = self.reddit.reddit_settings_embed(interaction.guild, self.server_data)
                await interaction.response.edit_message(embed=new_embed, view=self.view)

        class EnhanceButtonSubreddit(discord.ui.Button):
            def __init__(self, bot: commands.Bot, emojis: dict, server_data: dict):
                colored = True if server_data['redditEnhance'][1] else False
                super().__init__(
                    emoji=emojis[TOGGLES[server_data['redditEnhance'][1]]],
                    label='Enhanced Reddit embeds (subreddit)',
                    style=discord.ButtonStyle.blurple if colored else discord.ButtonStyle.gray,
                    custom_id='enhanced_subreddit',
                )
                self.reddit: Reddit = bot.get_cog('Reddit')
                self.emojis = emojis
                self.server_data = server_data

            async def callback(self, interaction: discord.Interaction):
                await database.edit_server_data(
                    interaction.guild, 'redditEnhance', [self.server_data['redditEnhance'][0], 1 if self.style == discord.ButtonStyle.blurple else 0]
                )
                self.server_data['redditEnhance'][1] = not self.style == discord.ButtonStyle.blurple
                self.style = discord.ButtonStyle.blurple if self.server_data['redditEnhance'][1] else discord.ButtonStyle.gray
                self.emoji = self.emojis[TOGGLES[self.server_data['redditEnhance'][1]]]
                new_embed = self.reddit.reddit_settings_embed(interaction.guild, self.server_data)
                await interaction.response.edit_message(embed=new_embed, view=self.view)

        class EnhanceButtonSubmission(discord.ui.Button):
            def __init__(self, bot: commands.Bot, emojis: dict, server_data: dict):
                colored = True if server_data['redditEnhance'][0] else False
                super().__init__(
                    emoji=emojis[TOGGLES[server_data['redditEnhance'][0]]],
                    label='Enhanced Reddit embeds (submission)',
                    style=discord.ButtonStyle.blurple if colored else discord.ButtonStyle.gray,
                    custom_id='enhanced_submission',
                )
                self.reddit: Reddit = bot.get_cog('Reddit')
                self.emojis = emojis
                self.server_data = server_data

            async def callback(self, interaction: discord.Interaction):
                await database.edit_server_data(
                    interaction.guild, 'redditEnhance', [1 if self.style == discord.ButtonStyle.blurple else 0, self.server_data['redditEnhance'][1]]
                )
                self.server_data['redditEnhance'][0] = not self.style == discord.ButtonStyle.blurple
                self.style = discord.ButtonStyle.blurple if self.server_data['redditEnhance'][0] else discord.ButtonStyle.gray
                new_embed = self.reddit.reddit_settings_embed(interaction.guild, self.server_data)
                self.emoji = self.emojis[TOGGLES[self.server_data['redditEnhance'][0]]]
                await interaction.response.edit_message(embed=new_embed, view=self.view)

        def __init__(self, bot: commands.Bot, ctx: commands.Context, server_data: dict):
            super().__init__(timeout=None)
            self.reddit: Reddit = bot.get_cog('Reddit')
            self.ctx = ctx
            self.server_data = server_data
            self.add_item(self.AutocompleteButton(bot, self.reddit.emojis, server_data))
            self.add_item(self.EnhanceButtonSubreddit(bot, self.reddit.emojis, server_data))
            self.add_item(self.EnhanceButtonSubmission(bot, self.reddit.emojis, server_data))

    def reddit_settings_embed(self, server: discord.Guild, server_data: dict):
        embed = discord.Embed(title='Reddit features', description='', color=REDDIT_COLOR)
        server_feeds = self.redditThreads.get(server.id, {})
        embed.description += f'\n\nReddit feeds [{len(server_feeds)}]: {" • ".join(subreddit for subreddit in server_feeds.keys()) if self.redditThreads.get(server.id, {}) else "None"}\nUse `/create_feed` to create a feed, `/edit_feed` to edit a feed, and `/delete_feed` to delete a feed\n\n'
        embed.description += f'{self.emojis[TOGGLES[bool(server_data["redditComplete"])]]}**r/subreddit autolink**\nType `r/` followed by a subreddit name to get a URL to the subreddit\n\n'
        embed.description += f'{self.emojis[TOGGLES[server_data["redditEnhance"][1]]]}**Enhanced Reddit embeds - subreddits**\nReplace the default Discord embeds from subreddit URLs typed in chat with a more informational one\n\n'
        embed.description += f'{self.emojis[TOGGLES[server_data["redditEnhance"][0]]]}**Enhanced Reddit embeds - submissions**\nSame as above, but for posts submitted to a subreddit\n\n'
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(Reddit(bot))
