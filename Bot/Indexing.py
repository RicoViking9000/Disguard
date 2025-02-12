"""Message indexing, attachment storage, and upcoming Disguard Drive functionality"""

import os
import traceback

import discord
import emoji as pymoji
from discord.ext import commands

import lightningdb
import models
import utility


class Indexing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

    def convert_emoji(self, emoji: discord.Emoji | str):
        """
        Converts a discord.Emoji object to a MessageEmoji object
        """
        custom = isinstance(emoji, discord.Emoji)
        return models.Emoji(
            name=emoji.name if custom else pymoji.demojize(emoji).strip(':'),
            custom=custom,
            source=models.CustomEmojiAttributes(
                id=emoji.id,
                creator_id=emoji.user.id,
                created_at=emoji.created_at,
                animated=emoji.animated,
                managed=emoji.managed(),
                guild_id=emoji.guild.id,
                url=emoji.url,  # permanence
            )
            if custom
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
            color=embed.color.to_rgb(),
            footer=models.EmbedFooter(text=embed.footer.text, icon_url=embed.footer.icon_url),
            image=models.EmbedImage(url=embed.image.url, proxy_url=embed.image.proxy_url, width=embed.image.width, height=embed.image.height),
            thumbnail=models.EmbedImage(
                url=embed.thumbnail.url, proxy_url=embed.thumbnail.proxy_url, width=embed.thumbnail.width, height=embed.thumbnail.height
            ),
            video=models.EmbedVideo(url=embed.video.url, width=embed.video.width, height=embed.video.height),
            provider=models.EmbedProvider(name=embed.provider.name, url=embed.provider.url),
            author=models.EmbedAuthor(name=embed.author.name, url=embed.author.url, icon_url=embed.author.icon_url),
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
            # filepath=attachment.fp.name,
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
            content_type=attachment.content_type,
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
            for mention in [message.mentions + message.role_mentions + message.channel_mentions]
        ]

    def components_from_message(self, message: discord.Message):
        """
        Extracts components from a message
        """

        def to_button(component: discord.ui.Button):
            return models.Button(
                type='button',
                style=component.style,
                label=component.label,
                emoji=self.convert_emoji(component.emoji),
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
                        emoji=self.convert_emoji(option.emoji),
                        default=option.default,
                    )
                    for option in component.options
                ],
                placeholder=component.placeholder,
                min_values=component.min_values,
                max_values=component.max_values,
                disabled=component.disabled,
            )

        def process_child(component):
            if isinstance(component, discord.ui.Button):
                return to_button(component)
            else:
                return to_dropdown(component)

        return [
            models.ActionRow(
                type='action_row',
                children=[process_child(component) for component in message.components],
            )
            if type(component) is discord.ActionRow
            else process_child(component)
            for component in message.components
        ]

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
            timestamp=message.created_at,
            attachments=[self.convert_attachment(attachment) for attachment in message.attachments],
            embeds=[self.convert_embed(embed) for embed in message.embeds],
            reactions=[],  # [await self.convert_reaction(reaction) for reaction in message.reactions],
            pinned=message.pinned,
            deleted=False,
            mentions=[],  # later
            components=[],  # later
            activity=None,  # later
        )

    async def convert_message(self, message: discord.Message):
        """
        Converts a discord.Message object to a MessageIndex object
        """
        try:
            message_index = models.MessageIndex(
                _id=message.id,
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

    async def on_message(self, message: discord.Message):
        try:
            if message.channel.type == discord.ChannelType.private:
                return
            message_index = await self.convert_message(message)
            await lightningdb.post_message_2024(message_index)  # Prisma delayed due to no composite support for Python
            if message.author.bot:
                return
            # save attachments
            await self.save_attachments(message)
        except Exception:
            traceback.print_exc()

    async def save_attachments(self, message: discord.Message):
        # needs to be converted to a thread
        saving_enabled = (await utility.get_server(message.guild)).get('cyberlog', {}).get('image')
        if saving_enabled and len(message.attachments) > 0 and not message.channel.is_nsfw():
            path = f'Attachments/{message.guild.id}/{message.channel.id}/{message.id}'
            for attachment in message.attachments:
                # for now, only save attachments under 8mb
                if attachment.size < 8_000_000:
                    # if the path doesn't exist, create it
                    if not os.path.exists(path):
                        os.makedirs(path)
                    try:
                        await attachment.save(f'path/{attachment.filename}')
                    except discord.HTTPException:
                        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Indexing(bot))
