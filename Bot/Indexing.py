"""Message indexing, attachment storage, and upcoming Disguard Drive functionality"""

import asyncio
import logging
import os
import traceback

import aiofiles.os as aios
import aioshutil
import discord
import emoji as pymoji
from discord.ext import commands, tasks
from pymongo.errors import DuplicateKeyError

import lightningdb
import models
import utility

logger = logging.getLogger('discord')
storage_dir = 'storage'  # /server_id/attachments/...
bytes_per_gigabyte = 1_073_741_824  # 1024 * 1024 * 1024


class Indexing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_and_free_server_attachment_storage.start()
        self.verify_indices.start()

    async def poll_from_message(self, message: discord.Message):
        """
        Extracts poll data from a message
        """
        if message.poll is None:
            return None
        poll = message.poll
        snowflake_id = discord.utils.time_snowflake(poll.created_at)
        return models.MessagePoll(
            id=snowflake_id,
            message_id=message.id,
            question=poll.question,
            answers=[
                models.PollAnswer(
                    id=answer.id,
                    parent_poll_id=snowflake_id,
                    media=models.PollMedia(text=answer.media.text, emoji=str(answer.media.emoji)),
                    text=answer.text,
                    emoji=str(answer.emoji),
                    vote_count=answer.vote_count,
                    voters=[user.id async for user in answer.voters()],
                )
                for answer in poll.answers
            ],
            expires_at=poll.expires_at,
            created_at=poll.created_at,
            total_votes=poll.total_votes,
            is_closed=poll.is_finalized(),
        )

    async def stickers_from_message(self, message: discord.Message):
        """
        Extracts sticker data from a message
        """
        fetched_stickers = [await sticker.fetch() for sticker in message.stickers]
        return [
            models.Sticker(
                sticker_id=sticker.id,
                message_id=message.id,
                format=str(sticker.format),
                url=sticker.url,
                type='standard' if models(fetched_stickers[index]).__name__ == 'StandardSticker' else 'guild',
                data=models.StandardSticker(
                    name=sticker.name,
                    description=fetched_stickers[index].description,
                    tags=fetched_stickers[index].tags,
                    sort_value=fetched_stickers[index].sort_value,
                    pack_id=fetched_stickers[index].pack_id,
                )
                if models(fetched_stickers[index]).__name__ == 'StandardSticker'
                else models.GuildSticker(
                    name=sticker.name,
                    description=fetched_stickers[index].description,
                    available=fetched_stickers[index].available,
                    guild_id=fetched_stickers[index].guild_id,
                    creator_id=fetched_stickers[index].user.id,
                    reference_emoji=fetched_stickers[index].emoji,
                ),
            )
            for index, sticker in enumerate(message.stickers)
        ]

    def convert_emoji(self, emoji: discord.Emoji | discord.PartialEmoji | str):
        """
        Converts a discord.Emoji object to a MessageEmoji object
        """
        custom = isinstance(emoji, discord.Emoji)
        unicode = isinstance(emoji, discord.PartialEmoji) and emoji.is_unicode_emoji()
        return models.Emoji(
            name=emoji.name if not unicode else pymoji.demojize(str(emoji)).strip(':'),
            custom=custom,
            source=models.CustomEmojiAttributes(
                id=emoji.id,
                creator_id=emoji.user.id,
                created_at=emoji.created_at,
                animated=emoji.animated,
                managed=emoji.managed,
                guild_id=emoji.guild.id,
                url=emoji.url,  # permanence
            )
            if custom
            else models.PartialEmojiAttributes(
                id=emoji.id,
                created_at=emoji.created_at,
                unicode=unicode,
                animated=emoji.animated,
                url=emoji.url,
            )
            if isinstance(emoji, discord.PartialEmoji)
            else emoji,
        )

    def convert_embed(self, embed: discord.Embed, message_id: int = 0):
        """
        Converts a discord.Embed object to a MessageEmbed object
        """
        return models.MessageEmbed(
            message_id=message_id,
            title=embed.title,
            type=embed.type,
            description=embed.description,
            url=embed.url,
            timestamp=embed.timestamp,
            color=embed.color.to_rgb() if embed.color else None,
            footer=models.EmbedFooter(text=embed.footer.text, icon_url=embed.footer.icon_url)
            if any((embed.footer.text, embed.footer.icon_url))
            else None,
            image=models.EmbedImage(url=embed.image.url, proxy_url=embed.image.proxy_url, width=embed.image.width, height=embed.image.height)
            if any((embed.image.url, embed.image.proxy_url, embed.image.width, embed.image.height))
            else None,
            thumbnail=models.EmbedImage(
                url=embed.thumbnail.url, proxy_url=embed.thumbnail.proxy_url, width=embed.thumbnail.width, height=embed.thumbnail.height
            )
            if any((embed.thumbnail.url, embed.thumbnail.proxy_url, embed.thumbnail.width, embed.thumbnail.height))
            else None,
            video=models.EmbedVideo(url=embed.video.url, width=embed.video.width, height=embed.video.height)
            if any((embed.video.url, embed.video.width, embed.video.height))
            else None,
            provider=models.EmbedProvider(name=embed.provider.name, url=embed.provider.url)
            if any((embed.provider.name, embed.provider.url))
            else None,
            author=models.EmbedAuthor(
                name=embed.author.name,
                url=embed.author.url,
                icon_url=embed.author.icon_url,
            )
            if any((embed.author.name, embed.author.url, embed.author.icon_url))
            else None,
            fields=[models.EmbedField(name=field.name, value=field.value, inline=field.inline) for field in embed.fields],
        )

    def convert_attachment(self, attachment: discord.Attachment, message_id: int = 0):
        """
        Converts a discord.Attachment object to a MessageAttachment object
        """
        return models.MessageAttachment(
            id=attachment.id,
            message_id=message_id,
            hash=hash(attachment),
            size=attachment.size,
            filename=attachment.filename,
            filepath=attachment.filename,
            url=attachment.url,
            proxy_url=attachment.proxy_url,
            media_attributes=models.MediaAttributes(
                attachment_id=attachment.id, height=attachment.height, width=attachment.width, description=attachment.description
            )
            if attachment.content_type in ['image', 'video']
            else None,
            voice_attributes=models.VoiceAttributes(attachment_id=attachment.id, duration=attachment.duration, waveform=attachment.waveform)
            if attachment.is_voice_message()
            else None,
            content_type=attachment.content_type or '',
            ephemeral=attachment.ephemeral,
            flags=models.AttachmentFlags(
                clip=attachment.flags.clip,
                thumbnail=attachment.flags.thumbnail,
                remix=attachment.flags.remix,
            ),
            spoiler=attachment.is_spoiler(),
            voice_message=attachment.is_voice_message(),
            image=attachment.content_type == 'image',
        )

    def type_from_message(self, message: discord.Message):
        """
        Extracts message type from a message
        """
        return models.MESSAGE_TYPES[message.type]

    def flags_from_message(self, message: discord.Message) -> models.MessageFlags:
        """
        Extracts message flags from a message
        """
        return models.MessageFlags(
            crossposted=message.flags.crossposted,
            ephemeral=message.flags.ephemeral,
            failed_to_mention_some_roles_in_thread=message.flags.failed_to_mention_some_roles_in_thread,
            has_thread=message.flags.has_thread,
            is_crossposted=message.flags.is_crossposted,
            loading=message.flags.loading,
            silent=message.flags.suppress_notifications,
            source_message_deleted=message.flags.source_message_deleted,
            suppress_embeds=message.flags.suppress_embeds,
            urgent=message.flags.urgent,
            voice=message.flags.voice,
        )

    # async def convert_reaction(self, reaction: discord.Reaction):
    #     """
    #     Converts a discord.Reaction object to a ReactionChangeEvent object
    #     """
    #     return ReactionChangeEvent(
    #         message_id=reaction.message.id,
    #         emoji=Emoji(
    #             name=reaction.emoji.name,
    #             custom=reaction.emoji.is_custom(),
    #             source=CustomEmojiAttributes(
    #                 id=reaction.emoji.id,
    #                 creator_id=reaction.emoji.user.id,
    #                 created_at=reaction.emoji.created_at,
    #                 animated=reaction.emoji.animated,
    #                 twitch=reaction.emoji.is_usable(),
    #                 guild_id=reaction.emoji.guild.id,
    #                 url=reaction.emoji.url,
    #             )
    #             if reaction.emoji.is_custom()
    #             else reaction.emoji.url,
    #         ),
    #         users=[user.id for user in await reaction.users().flatten()],
    #         static_count=reaction.count,
    #         burst_count=reaction.count,
    #         total_count=reaction.count,
    #         custom_emoji=reaction.emoji.is_custom(),
    #         timestamp=datetime.datetime.now(),
    #     )

    def mentions_from_message(self, message: discord.Message):
        """
        Extracts mentions from a message
        """
        return [
            models.Mention(
                type='user' if isinstance(mention, discord.User) else 'role' if isinstance(mention, discord.Role) else 'channel',
                target=mention.id,
            )
            for mention in message.mentions + message.role_mentions + message.channel_mentions
        ]

    def components_from_message(self, message: discord.Message):
        """
        Extracts components from a message
        """

        BUTTON_STYLE_MAP = {
            discord.ButtonStyle.primary: 'primary',
            discord.ButtonStyle.secondary: 'secondary',
            discord.ButtonStyle.success: 'success',
            discord.ButtonStyle.danger: 'danger',
            discord.ButtonStyle.link: 'link',
            discord.ButtonStyle.premium: 'premium',
        }

        def to_button(component: discord.ui.Button):
            return models.Button(
                type='button',
                style=BUTTON_STYLE_MAP.get(component.style, 'secondary'),
                label=component.label,
                emoji=self.convert_emoji(component.emoji) if component.emoji else None,
                custom_id=component.custom_id,
                url=component.url,
                sku_id=component.sku_id,
                disabled=component.disabled,
            )

        def to_dropdown(
            component: discord.ui.Select | discord.ui.ChannelSelect | discord.ui.MentionableSelect | discord.ui.RoleSelect | discord.ui.UserSelect,
        ):
            return models.Dropdown(
                type='select_menu'
                if isinstance(component, discord.ui.Select)
                else 'channel_select'
                if isinstance(component, discord.ui.ChannelSelect)
                else 'mentionable_select'
                if isinstance(component, discord.ui.MentionableSelect)
                else 'role_select'
                if isinstance(component, discord.ui.RoleSelect)
                else 'user_select',
                custom_id=component.custom_id,
                options=[
                    models.SelectOption(
                        label=option.label,
                        value=option.value,
                        description=option.description,
                        emoji=self.convert_emoji(option.emoji) if option.emoji else None,
                        default=option.default,
                    )
                    for option in component.options
                ],
                placeholder=component.placeholder,
                min_values=component.min_values,
                max_values=component.max_values,
                disabled=component.disabled,
            )

        def process_child(component: discord.Component):
            if component.type is discord.ComponentType.button:
                return to_button(component)
            else:
                return to_dropdown(component)

        return [
            models.ActionRow(
                type='action_row',
                children=[process_child(child) for child in component.children],
            )
            if type(component) is discord.ActionRow
            else process_child(component)
            for component in message.components
        ]

    def convert_activity(self, application: discord.MessageApplication, activity: dict):
        """
        Converts a discord.Activity object to a MessageActivity object
        """
        return models.Activity(
            application=models.MessageApplication(
                id=application.id,
                name=application.name,
                description=application.description,
                cover=models.Asset(key=application.cover.key, url=application.cover.url, animated=application.cover.is_animated())
                if application.cover
                else None,
                icon=models.Asset(key=application.icon.key, url=application.icon.url, animated=application.icon.is_animated())
                if application.icon
                else None,
            )
            if application
            else None,
            activity_type=activity.get('type'),
            party_id=activity.get('party_id'),
        )

    def message_content(self, message: discord.Message):
        """
        Extracts message content from a message
        """
        if message.channel.is_nsfw():
            return '<Hidden due to NSFW channel>'
        if message.content:
            return message.content
        if message.attachments:
            return f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>"
        if message.embeds:
            return f'<{len(message.embeds)} embed>'
        return '<No content>'

    async def edition_from_message(self, message: discord.Message):
        """
        Converts a discord.Message object to a MessageEdition object
        """
        return models.MessageEdition(
            content=message.content,
            timestamp=int(message.created_at.timestamp()),
            attachments=[self.convert_attachment(attachment) for attachment in message.attachments],
            embeds=[self.convert_embed(embed) for embed in message.embeds],
            reactions=[],  # [await self.convert_reaction(reaction) for reaction in message.reactions],
            pinned=message.pinned,
            deleted=False,
            mentions=self.mentions_from_message(message),
            components=self.components_from_message(message),
            activity=self.convert_activity(message.application, message.activity) if any((message.application, message.activity)) else None,
        )

    async def convert_message(self, message: discord.Message):
        """
        Converts a discord.Message object to a MessageIndex object
        """
        try:
            message_index = models.MessageIndex(
                id=message.id,
                editions=[],
                author_id=message.author.id,
                created_at=int(message.created_at.timestamp()),
                channel_id=message.channel.id,
                guild_id=message.guild.id,
                pinned=message.pinned,
                deleted=False,
                jump_url=message.jump_url,
                poll=await self.poll_from_message(message),
                stickers=await self.stickers_from_message(message),
                thread_id=message.thread.id if message.thread else 0,
                parent_interaction_id=message.interaction_metadata.id if message.interaction_metadata else 0,
                reference_message_id=message.reference.message_id if message.reference else 0,
                tts=message.tts,
                type=models.MESSAGE_TYPES[message.type],
                webhook_id=message.webhook_id,
                system=message.is_system(),
                flags=self.flags_from_message(message),
                nsfw_channel=message.channel.is_nsfw(),
            )
            # the first edition is the current message data
            message_index.editions.append(await self.edition_from_message(message))
            return message_index
        except Exception:
            print(f'Error converting message {message.id}: {traceback.print_exc()}')
            logger.error(f'Error converting message {message.id}', exc_info=True)

    async def get_attachment_storage(self, server: discord.Guild):
        """
        Checks how much attachment storage is used by this server
        """
        # check if the server has storage enabled
        dir = f'{storage_dir}/{server.id}/attachments'
        storage_used = utility.get_dir_size(dir)
        storage_limit = (await utility.get_server(server)).get('cyberlog', {}).get('storageCap', 0)
        over_capacity = storage_used > (storage_limit * bytes_per_gigabyte)
        delta = storage_used - (storage_limit * bytes_per_gigabyte)

        return storage_limit, storage_used, over_capacity, delta

    async def delete_oldest_attachments(self, server: discord.Guild):
        """
        Deletes the oldest attachments in a server, supporting unlimited folder nesting depth.
        """
        storage_limit, storage_used, over_capacity, space_to_free = await self.get_attachment_storage(server)
        # If this server hasn't reached capacity, no need to delete old attachments
        if not over_capacity:
            return
        if storage_used >= storage_limit * bytes_per_gigabyte:
            dir = f'{storage_dir}/{server.id}/attachments'
            space_freed = 0

            def get_all_files_sorted_by_oldest(directory):
                """
                Recursively collects all files in the directory and its subdirectories,
                sorted by their last modified time (oldest first).
                """
                all_files = []
                for root, _, files in os.walk(directory):
                    for file in files:
                        file_path = os.path.join(root, file)
                        all_files.append(file_path)
                return sorted(all_files, key=lambda x: os.path.getmtime(x))

            # Get all files sorted by oldest first
            files = get_all_files_sorted_by_oldest(dir)

            # Delete files until enough space is freed
            for file_path in files:
                if space_freed >= space_to_free:
                    break
                try:
                    file_size = await aios.path.getsize(file_path)
                    await aios.remove(file_path)
                    space_freed += file_size
                except FileNotFoundError:
                    logger.error(f'delete_oldest_attachments - File not found: {file_path}', exc_info=True)
                except Exception:
                    logger.error(f'delete_oldest_attachments - Error deleting file {file_path}', exc_info=True)

            # Remove empty folders
            for root, dirs, _ in os.walk(dir, topdown=False):
                for folder in dirs:
                    folder_path = os.path.join(root, folder)
                    try:
                        await aios.rmdir(folder_path)
                    except OSError:
                        logger.error(f'delete_oldest_attachments - Directory not empty: {folder_path}')
            return space_freed

    async def delete_all_attachments(self, *, server: discord.Guild = None, channel: discord.TextChannel = None):
        """
        Deletes all attachments in a server or channel.
        """
        full_nuke = False
        if not server and not channel:
            full_nuke = True
        elif server and not channel:
            dir = f'{storage_dir}/{server.id}/attachments'
        elif channel:
            dir = f'{storage_dir}/{channel.guild.id}/attachments/{channel.id}'
        if not full_nuke:
            try:
                await aioshutil.rmtree(dir)
                logger.info(f'Deleted all attachments in {dir}')
            except FileNotFoundError:
                logger.error(f'delete_all_attachments - Directory not found: {dir}')
            except Exception:
                logger.error(f'delete_all_attachments - Error deleting directory {dir}', exc_info=True)
        else:
            servers = self.bot.guilds
            for server in servers:
                dir = f'{storage_dir}/{server.id}/attachments'
                try:
                    await aioshutil.rmtree(dir)
                    logger.info(f'Deleted all attachments in {dir}')
                except FileNotFoundError:
                    logger.error(f'delete_all_attachments - Directory not found: {dir}')
                except Exception:
                    logger.error(f'delete_all_attachments - Error deleting directory {dir}', exc_info=True)

    async def save_attachments(self, message: discord.Message):
        # needs to be converted to a task
        saving_enabled = (await utility.get_server(message.guild)).get('cyberlog', {}).get('image')
        if saving_enabled and len(message.attachments) > 0 and not message.channel.is_nsfw():
            path = f'{storage_dir}/{message.guild.id}/attachments/{message.channel.id}/{message.id}'
            # if the path doesn't exist, create it
            if not await aios.path.exists(path):
                await aios.makedirs(path)
            for attachment in message.attachments:
                # for now, only save attachments under 10mb
                if attachment.size < 10_000_000:
                    # check if the file already exists
                    if not await aios.path.exists(f'{path}/{attachment.filename}'):
                        # save the attachment
                        try:
                            await attachment.save(f'{path}/{attachment.filename}')
                        except discord.HTTPException:
                            pass

    # need to handle tasks to index messages in the background and/or on bot bootup

    async def index_channels(self, channels: list[discord.TextChannel], full: bool = False):
        """
        Indexes a list of channels
        """
        # split channels into groups of five for task grouping
        for i in range(0, len(channels), 5):
            try:
                await asyncio.gather(*[self.index_channel(channel, full=full) for channel in channels[i : i + 5]])
            except Exception as e:
                print(f'Error indexing channels {channels[i : i + 5]}: {e}')
                logger.error(f'Error indexing channels {channels[i : i + 5]}: {e}', exc_info=True)
                traceback.print_exc()

    async def index_channel(self, channel: discord.TextChannel, full: bool = False):
        """
        Indexes a channel
        """
        indexing_enabled = (await utility.get_server(channel.guild))['cyberlog'].get('indexing')
        if not indexing_enabled:
            return
        # make sure this is not a private channel
        if channel.type == discord.ChannelType.private:
            return
        if channel.id in (534439214289256478, 910598159963652126):
            return
        start = discord.utils.utcnow()
        try:
            save_images = (await utility.get_server(channel.guild))['cyberlog'].get('image') and not channel.is_nsfw()
        except KeyError:
            save_images = False
        # if there's no indexes in the DB for this channel, index everything
        if await lightningdb.is_channel_empty(channel.id):
            full = True
        # if 15 messages in a row are already indexed, stop indexing
        existing_message_counter = 0
        async for message in channel.history(limit=None, oldest_first=full):
            try:
                message_data = await self.convert_message(message)
                if message_data:
                    await lightningdb.post_message_2024(message_data)
            except DuplicateKeyError:
                if not full:
                    existing_message_counter += 1
                    if existing_message_counter >= 15:
                        break
            if message.attachments and not message.author.bot and save_images:
                await self.save_attachments(message)
            if full:
                await asyncio.sleep(0.000025)
        print(f'Indexed channel ...{str(channel.id)[-4:]}')
        logger.info(f'Indexed channel {channel.id} in {(discord.utils.utcnow() - start)} delta')

    async def index_messages(self, messages: list[discord.Message]):
        """
        Indexes a list of messages. Messages are not necessarily from the same server.
        """
        server_indexing_enabled = {}
        channel_images_enabled = {}
        for message in messages:
            # build a cache of channel's servers with attachment saving enabled
            if channel_images_enabled.get(message.channel.id) is None:
                save_images = (await utility.get_server(message.guild))['cyberlog'].get('image') and not message.channel.is_nsfw()
                channel_images_enabled[message.channel.id] = save_images
            # build a cache of servers with indexing enabled, and continue if it's not enabled
            if server_indexing_enabled.get(message.guild.id) is None:
                server_indexing_enabled[message.guild.id] = (await utility.get_server(message.guild))['cyberlog'].get('indexing')
            if not server_indexing_enabled[message.guild.id]:
                continue
            try:
                message_data = await self.convert_message(message)
                if message_data:
                    await lightningdb.post_message_2024(message_data)
            except DuplicateKeyError:
                logger.info(f'Message {message.id} already indexed')
            # save attachments if saving is enabled
            if message.attachments and not message.author.bot and channel_images_enabled.get(message.channel.id, False):
                await self.save_attachments(message)

    async def index_message(self, message: discord.Message):
        """
        Indexes a message
        """
        # check if indexing is enabled
        cyberlog = (await utility.get_server(message.guild)).get('cyberlog', {})
        if not cyberlog.get('indexing'):
            return
        await self.bot.wait_until_ready()
        try:
            message_data = await self.convert_message(message)
            if message_data:
                await lightningdb.post_message_2024(message_data)
        except DuplicateKeyError:
            logger.info(f'Message {message.id} already indexed')
        if message.attachments and cyberlog.get('image') and not message.channel.is_nsfw():
            await self.save_attachments(message)

    @tasks.loop(hours=6)
    async def check_and_free_server_attachment_storage(self):
        """
        Checks if the server has reached its storage limit and frees up space if necessary
        """
        for server in self.bot.guilds:
            # check if the server has storage enabled
            if not (await utility.get_server(server)).get('cyberlog', {}).get('image'):
                continue
            _, _, over_capacity, _ = await self.get_attachment_storage(server)
            if over_capacity:
                await self.delete_oldest_attachments(server)

    @tasks.loop(hours=24)
    async def verify_indices(self):
        """
        Verifies that all indexes are valid and removes any invalid ones
        """
        print('Daily task - verifying indexes')
        logger.info('Daily task - verifying indexes')
        await self.bot.wait_until_ready()
        for server in self.bot.guilds:
            # check if the server has indexing enabled
            if (await utility.get_server(server)).get('cyberlog', {}).get('indexing'):
                await self.index_channels(server.text_channels, full=False)
        print('Finished verifying indexes')
        logger.info('Finished verifying indexes')

    async def on_message(self, message: discord.Message):
        try:
            if message.channel.type == discord.ChannelType.private:
                return
            await self.index_message(message)
        except Exception:
            logger.error(f'Error in Indexing on_message: {message.id}', exc_info=True)
            traceback.print_exc()


async def setup(bot: commands.Bot):
    await bot.add_cog(Indexing(bot))
