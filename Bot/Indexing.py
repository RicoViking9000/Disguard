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


class AttachmentFlags(TypedDict):
    """
    Flags for attachments
    """

    spoiler: bool
    voice_message: bool
    image: bool


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
    # discord.MessageType.guild_incident_alert_mode_enabled: 'guild_incident_alert_mode_enabled', # TODO - v2.4
    # discord.MessageType.guild_incident_alert_mode_disabled: 'guild_incident_alert_mode_disabled', # TODO - v2.4
    # discord.MessageType.guild_incident_report_raid: 'guild_incident_report_raid', # TODO - v2.4
    # discord.MessageType.guild_incident_report_false_alarm: 'guild_incident_report_false_alarm', # TODO - v2.4
}


class Activity(pydantic.BaseModel):
    """
    An activity
    """

    type: Literal['join', 'spectate', 'listen', 'join_request', 'streaming', 'custom']
    party_id: str
    party_size: tuple[int, int]
    party_max: int
    join_secret: str
    spectate_secret: str
    match: str
    instance: bool
    flags: int


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
    pinned: bool
    deleted: bool
    jump_url: str
    poll: MessagePoll
    stickers: list[Sticker]
    thread_id: int
    parent_interaction_id: int
    reference_message_id: int
    components_count: int  # do I want to fully map out components?
    tts: bool
    type: str
    webhook_id: int
    system: bool
    activity: dict
    flags: dict
    nsfw_channel: bool  # don't post in logs unless log channel is NSFW


class Indexing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.type == discord.ChannelType.private:
            return

    async def convert_message(self, message: discord.Message):
        """
        Converts a discord.Message object to a MessageIndex object
        """
        message_index = MessageIndex(
            _id=message.id,
            editions=[
                MessageEdition(
                    content=message.content,
                    timestamp=message.created_at,
                    attachments=message.attachments,
                    embeds=message.embeds,
                    reactions=message.reactions,
                    pinned=message.pinned,
                    deleted=False,
                    mentions=message.raw_mentions,
                )
            ],
            author_id=message.author.id,
            content=message.content,
            created_at=message.created_at.timestamp(),
            channel_id=message.channel.id,
            guild_id=message.guild.id,
            pinned=message.pinned,
            deleted=False,
            jump_url=message.jump_url,
            poll={},
            stickers=[],
            tts=message.tts,
            type=message.type,
            webhook_id=message.webhook_id,
            system=message.system,
            activity={},
            flags={},
            nsfw_channel=message.channel.is_nsfw(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Indexing(bot))
