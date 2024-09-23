"""Message indexing, attachment storage, and upcoming Disguard Drive functionality"""

import datetime
from typing import Literal, Optional, TypedDict

import discord
import pydantic
from discord.ext import commands


class MediaAttributes(pydantic.BaseModel):
    """Contains attachment data for images and videos"""

    attachment_id: int
    height: int
    width: int
    description: Optional[str]


class VoiceAttributes(pydantic.BaseModel):
    """Contains attachment data for voice messages"""

    attachment_id: int
    duration: int
    waveform: bytes


class AttachmentFlags(pydantic.BaseModel):
    """
    Flags for attachments
    """

    clip: bool
    thumbnail: bool
    remix: bool


class MessageAttachment(pydantic.BaseModel):
    """
    A message attachment, to be expanded later with Disguard Drive
    https://discordpy.readthedocs.io/en/latest/api.html#attachment
    """

    id: int
    message_id: int
    hash: str
    size: int  # size in bytes
    filename: str
    filepath: str
    url: str
    proxy_url: str
    media_attributes: Optional[MediaAttributes]
    voice_attributes: Optional[VoiceAttributes]
    content_type: str
    ephemeral: bool
    flags: AttachmentFlags
    spoiler: bool
    voice_message: bool
    image: bool


class EmbedFooter(pydantic.BaseModel):
    """A message embed footer"""

    text: str
    icon_url: str


class EmbedImage(pydantic.BaseModel):
    """A message embed image"""

    url: str
    proxy_url: str
    width: int
    height: int


class EmbedVideo(pydantic.BaseModel):
    """A message embed video"""

    url: str
    width: int
    height: int


class EmbedProvider(pydantic.BaseModel):
    """A message embed provider"""

    name: str
    url: str


class EmbedAuthor(pydantic.BaseModel):
    """A message embed author"""

    name: str
    url: str
    icon_url: str


class EmbedField(pydantic.BaseModel):
    """A message embed field"""

    name: str
    value: str
    inline: bool


class MessageEmbed(pydantic.BaseModel):
    """A message embed. Each edition may have multiple embeds."""

    message_id: int
    title: str
    type: Literal['rich', 'image', 'video', 'gifv', 'article', 'link']
    description: str
    url: str
    type: str
    timestamp: Optional[datetime.datetime]
    color: tuple[int, int, int]
    footer: EmbedFooter
    image: EmbedImage
    thumbnail: EmbedImage
    video: EmbedVideo
    provider: EmbedProvider
    author: EmbedAuthor
    fields: list[EmbedField]


class CustomEmojiAttributes(pydantic.BaseModel):
    """
    Custom emoji attributes
    """

    id: int
    creator_id: int
    created_at: datetime.datetime
    animated: bool
    twitch: bool
    guild_id: int
    url: str


class Emoji(pydantic.BaseModel):
    """
    An emoji
    """

    name: str
    custom: bool
    source: str | CustomEmojiAttributes


class ReactionChangeEvent(pydantic.BaseModel):
    """
    A message reaction - this is separate per emoji. I don't think this is feasible due to how frequently reactions are added/removed.
    On the flip side, it would be really cool to keep a hot log of everything, including every reaction.
    I think this should be separated from the Editions array.
    """

    message_id: int
    emoji: Emoji
    users: list[int]
    static_count: int
    burst_count: int
    total_count: int
    custom_emoji: bool
    timestamp: datetime.datetime


class Mention(TypedDict):
    """
    A channel, role, or member mention in a message
    """

    type: Literal['channel', 'role', 'member']
    id: int


class PollMedia(pydantic.BaseModel):
    text: str
    emoji: str


class PollAnswer(pydantic.BaseModel):
    """A poll answer"""

    id: int
    parent_poll_id: int
    media: PollMedia
    self_voted: bool
    text: str
    emoji: str
    vote_count: int
    voters: list[int]


class MessagePoll(pydantic.BaseModel):
    """A message poll"""

    id: int
    message_id: int
    question: str
    answers: list[PollAnswer]
    expires_at: datetime.datetime
    created_at: datetime.datetime
    total_votes: dict
    is_closed: bool


class StandardSticker(pydantic.BaseModel):
    """A standard message sticker"""

    name: str
    description: str
    tags: list[str]
    sort_value: int
    pack_id: int


class GuildSticker(pydantic.BaseModel):
    """A guild message sticker"""

    name: str
    description: str
    avaulable: bool
    guild_id: int
    creator_id: int
    reference_emoji: str


class Sticker(pydantic.BaseModel):
    """A message sticker"""

    message_id: int
    sticker_id: int
    format: Literal['png', 'apng', 'lottie', 'gif']
    url: str
    type: Literal['standard', 'guild']
    data: StandardSticker | GuildSticker


MESSAGE_TYPES = {
    discord.MessageType.default: 'default',
    discord.MessageType.recipient_add: 'recipient_add',
    discord.MessageType.recipient_remove: 'recipient_remove',
    discord.MessageType.call: 'call',
    discord.MessageType.channel_name_change: 'channel_name_change',
    discord.MessageType.channel_icon_change: 'channel_icon_change',
    discord.MessageType.pins_add: 'pins_add',
    discord.MessageType.new_member: 'new_member',
    discord.MessageType.premium_guild_subscription: 'premium_guild_subscription',
    discord.MessageType.premium_guild_tier_1: 'premium_guild_tier_1',
    discord.MessageType.premium_guild_tier_2: 'premium_guild_tier_2',
    discord.MessageType.premium_guild_tier_3: 'premium_guild_tier_3',
    discord.MessageType.channel_follow_add: 'channel_follow_add',
    discord.MessageType.guild_stream: 'guild_stream',
    discord.MessageType.guild_discovery_disqualified: 'guild_discovery_disqualified',
    discord.MessageType.guild_discovery_requalified: 'guild_discovery_requalified',
    discord.MessageType.guild_discovery_grace_period_initial_warning: 'guild_discovery_grace_period_initial_warning',
    discord.MessageType.guild_discovery_grace_period_final_warning: 'guild_discovery_grace_period_final_warning',
    discord.MessageType.thread_created: 'thread_created',
    discord.MessageType.reply: 'reply',
    discord.MessageType.chat_input_command: 'chat_input_command',
    discord.MessageType.thread_starter_message: 'thread_starter_message',
    discord.MessageType.context_menu_command: 'context_menu_command',
    discord.MessageType.auto_moderation_action: 'auto_moderation_action',
    discord.MessageType.role_subscription_purchase: 'role_subscription_purchase',
    discord.MessageType.interaction_premium_upsell: 'interaction_premium_upsell',
    discord.MessageType.stage_start: 'stage_start',
    discord.MessageType.stage_end: 'stage_end',
    discord.MessageType.stage_speaker: 'stage_speaker',
    discord.MessageType.stage_raise_hand: 'stage_raise_hand',
    discord.MessageType.stage_topic: 'stage_topic',
    discord.MessageType.guild_application_premium_subscription: 'guild_application_premium_subscription',
    discord.MessageType.guild_incident_alert_mode_enabled: 'guild_incident_alert_mode_enabled',  # TODO - v2.4
    discord.MessageType.guild_incident_alert_mode_disabled: 'guild_incident_alert_mode_disabled',  # TODO - v2.4
    discord.MessageType.guild_incident_report_raid: 'guild_incident_report_raid',  # TODO - v2.4
    discord.MessageType.guild_incident_report_false_alarm: 'guild_incident_report_false_alarm',  # TODO - v2.4
}


class MessageEdition(pydantic.BaseModel):
    """Data specific to each edition of a message"""

    content: str
    timestamp: datetime.datetime
    attachments: list[MessageAttachment]
    embeds: list[MessageEmbed]
    reactions: list[ReactionChangeEvent]
    pinned: bool
    deleted: bool  # Deleted + edition timestamp = deletion time
    mentions: list[Mention]  # will need to combine member, channel & role here


class MessageIndex(pydantic.BaseModel):
    """One per message, contains revision instances & data constant between revisions"""

    _id: int
    editions: list[MessageEdition]
    author_id: int
    created_at: int
    channel_id: int
    guild_id: int
    pinned: bool = pydantic.Field(default=False)
    deleted: bool = pydantic.Field(default=False)
    jump_url: str
    poll: MessagePoll
    stickers: list[Sticker]
    thread_id: int
    parent_interaction_id: int
    reference_message_id: int
    components_count: int  # do I want to fully map out components?
    tts: bool
    type: str  # using MESSAGE_TYPES dict
    webhook_id: int
    system: bool
    activity: dict
    flags: dict
    nsfw_channel: bool  # don't post in logs unless log channel is NSFW


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
        return MessagePoll(
            id=snowflake_id,
            message_id=message.id,
            question=poll.question,
            answers=[
                PollAnswer(
                    id=answer.id,
                    parent_poll_id=snowflake_id,
                    media=PollMedia(text=answer.media.text, emoji=str(answer.media.emoji)),
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

    def stickers_from_message(self, message: discord.Message):
        """
        Extracts sticker data from a message
        """
        fetched_stickers = [await sticker.fetch() for sticker in message.stickers]
        return [
            Sticker(
                message_id=message.id,
                sticker_id=sticker.id,
                format=str(sticker.format),
                url=sticker.url,
                type='standard' if type(fetched_stickers[index]).__name__ == 'StandardSticker' else 'guild',
                data=StandardSticker(
                    name=sticker.name,
                    description=fetched_stickers[index].description,
                    tags=fetched_stickers[index].tags,
                    sort_value=fetched_stickers[index].sort_value,
                    pack_id=fetched_stickers[index].pack_id,
                )
                if type(fetched_stickers[index]).__name__ == 'StandardSticker'
                else GuildSticker(
                    name=sticker.name,
                    description=fetched_stickers[index].description,
                    avaulable=fetched_stickers[index].available,
                    guild_id=fetched_stickers[index].guild_id,
                    creator_id=fetched_stickers[index].user.id,
                    reference_emoji=fetched_stickers[index].emoji,
                ),
            )
            for index, sticker in enumerate(message.stickers)
        ]

    def convert_embed(self, embed: discord.Embed, message_id: int = 0):
        """
        Converts a discord.Embed object to a MessageEmbed object
        """
        return MessageEmbed(
            message_id=message_id,
            title=embed.title,
            type=embed.type,
            description=embed.description,
            url=embed.url,
            timestamp=embed.timestamp,
            color=embed.color.to_rgb(),
            footer=EmbedFooter(text=embed.footer.text, icon_url=embed.footer.icon_url),
            image=EmbedImage(url=embed.image.url, proxy_url=embed.image.proxy_url, width=embed.image.width, height=embed.image.height),
            thumbnail=EmbedImage(
                url=embed.thumbnail.url, proxy_url=embed.thumbnail.proxy_url, width=embed.thumbnail.width, height=embed.thumbnail.height
            ),
            video=EmbedVideo(url=embed.video.url, width=embed.video.width, height=embed.video.height),
            provider=EmbedProvider(name=embed.provider.name, url=embed.provider.url),
            author=EmbedAuthor(name=embed.author.name, url=embed.author.url, icon_url=embed.author.icon_url),
            fields=[EmbedField(name=field.name, value=field.value, inline=field.inline) for field in embed.fields],
        )

    def convert_attachment(self, attachment: discord.Attachment, message_id: int = 0):
        """
        Converts a discord.Attachment object to a MessageAttachment object
        """
        return MessageAttachment(
            id=attachment.id,
            message_id=message_id,
            hash=hash(attachment),
            size=attachment.size,
            filename=attachment.filename,
            # filepath=attachment.fp.name,
            url=attachment.url,
            proxy_url=attachment.proxy_url,
            media_attributes=MediaAttributes(
                attachment_id=attachment.id, height=attachment.height, width=attachment.width, description=attachment.description
            )
            if attachment.content_type in ['image', 'video']
            else None,
            voice_attributes=VoiceAttributes(attachment_id=attachment.id, duration=attachment.duration, waveform=attachment.waveform)
            if attachment.is_voice_message()
            else None,
            content_type=attachment.content_type,
            ephemeral=attachment.ephemeral,
            flags=AttachmentFlags(
                clip=attachment.flags.clip,
                thumbnail=attachment.flags.thumbnail,
                remix=attachment.flags.remix,
            ),
            spoiler=attachment.is_spoiler(),
            voice_message=attachment.is_voice_message(),
            image=attachment.content_type == 'image',
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

    async def edition_from_message(self, message: discord.Message):
        """
        Converts a discord.Message object to a MessageEdition object
        """
        return MessageEdition(
            content=message.content,
            timestamp=message.created_at,
            attachments=[self.convert_attachment(attachment) for attachment in message.attachments],
            embeds=[self.convert_embed(embed) for embed in message.embeds],
            reactions=[],  # [await self.convert_reaction(reaction) for reaction in message.reactions],
            pinned=message.pinned,
            deleted=False,
            mentions=[],  # later
        )

    async def convert_message(self, message: discord.Message):
        """
        Converts a discord.Message object to a MessageIndex object
        """
        message_index = MessageIndex(
            _id=message.id,
            editions=[],
            author_id=message.author.id,
            created_at=message.created_at.timestamp(),
            channel_id=message.channel.id,
            guild_id=message.guild.id,
            pinned=message.pinned,
            deleted=False,
            jump_url=message.jump_url,
            poll=self.poll_from_message(message),  # later
            stickers=[self.stickers_from_message(message)],
            thread_id=message.thread.id if message.thread else 0,
            parent_interaction_id=message.interaction.id if message.interaction else 0,
            reference_message_id=message.reference.message_id if message.reference else 0,
            components_count=len(message.components),
            tts=message.tts,
            type=MESSAGE_TYPES[message.type],
            webhook_id=message.webhook_id,
            system=message.is_system(),
            activity=message.activity,
            flags=message.flags,
            nsfw_channel=message.channel.is_nsfw(),
        )
        # the first edition is the current message data
        message_index.editions.append(await self.edition_from_message(message))

        return message_index

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.type == discord.ChannelType.private:
            return
        message_index = await self.convert_message(message)


async def setup(bot: commands.Bot):
    await bot.add_cog(Indexing(bot))
