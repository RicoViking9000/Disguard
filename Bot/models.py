import datetime
from typing import Literal, Optional

import discord
import pydantic
from typing_extensions import Annotated, TypedDict


class MediaAttributes(pydantic.BaseModel):
    """Contains attachment data for images and videos"""

    attachment_id: int
    height: int | None
    width: int | None
    description: str | None


class VoiceAttributes(pydantic.BaseModel):
    """Contains attachment data for voice messages"""

    attachment_id: int
    duration: int | None
    waveform: bytes | None


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
    hash: int
    size: int  # size in bytes
    filename: str
    filepath: str  # in database or local machine
    url: str
    proxy_url: str
    media_attributes: MediaAttributes | None = pydantic.Field(default=None)
    voice_attributes: VoiceAttributes | None = pydantic.Field(default=None)
    content_type: str = pydantic.Field(default='')  # MIME type
    ephemeral: bool
    flags: AttachmentFlags
    spoiler: bool
    voice_message: bool
    image: bool


class EmbedFooter(pydantic.BaseModel):
    """A message embed footer"""

    text: Annotated[str, pydantic.StringConstraints(max_length=2048)] | None
    icon_url: str | None


class EmbedImage(pydantic.BaseModel):
    """A message embed image"""

    url: str | None
    proxy_url: str | None
    width: int | None
    height: int | None


class EmbedVideo(pydantic.BaseModel):
    """A message embed video"""

    url: str | None
    width: int | None
    height: int | None


class EmbedProvider(pydantic.BaseModel):
    """A message embed provider"""

    name: str | None
    url: str | None


class EmbedAuthor(pydantic.BaseModel):
    """A message embed author"""

    name: Annotated[str, pydantic.StringConstraints(max_length=256)] | None
    url: str | None
    icon_url: str | None


class EmbedField(pydantic.BaseModel):
    """A message embed field"""

    name: Annotated[str, pydantic.StringConstraints(max_length=256)]
    value: Annotated[str, pydantic.StringConstraints(max_length=1024)]
    inline: bool


class MessageEmbed(pydantic.BaseModel):
    """A message embed. Each edition may have multiple embeds."""

    message_id: int
    title: Optional[Annotated[str, pydantic.StringConstraints(max_length=256)]]
    description: Optional[Annotated[str, pydantic.StringConstraints(max_length=4096)]]
    url: Optional[str]
    type: Literal['rich', 'image', 'video', 'gifv', 'article', 'link', 'poll_result', 'auto_moderation_notification', 'auto_moderation_message']
    timestamp: Optional[datetime.datetime]
    color: tuple[int, int, int] | None
    footer: EmbedFooter | None
    image: EmbedImage | None
    thumbnail: EmbedImage | None
    video: EmbedVideo | None
    provider: EmbedProvider | None
    author: EmbedAuthor | None
    fields: list[EmbedField]


class CustomEmojiAttributes(pydantic.BaseModel):
    """
    Custom emoji attributes
    """

    id: int
    created_at: datetime.datetime
    require_colons: bool
    animated: bool
    managed: bool
    guild_id: int
    creator_id: int
    url: str
    usable_roles: list[int]
    # application_owned: bool # d.py 2.5


class PartialEmojiAttributes(pydantic.BaseModel):
    """
    Partial emoji attributes
    """

    id: int | None
    created_at: datetime.datetime | None
    unicode: bool
    animated: bool
    url: str | None = pydantic.Field(default=None)


class Emoji(pydantic.BaseModel):
    """
    An emoji
    """

    name: str | None
    custom: bool  # False + source existing = partial
    source: str | CustomEmojiAttributes | PartialEmojiAttributes


class Button(pydantic.BaseModel):
    """A message button"""

    type: str = pydantic.Field(default='button')
    style: Literal['primary', 'secondary', 'success', 'danger', 'link', 'premium']
    label: str | None = pydantic.Field(max_length=80)
    emoji: Emoji | None
    custom_id: str | None = pydantic.Field(max_length=100)
    url: str | None
    sku_id: int | None
    disabled: bool


class TextInput(pydantic.BaseModel):
    """A message text input"""

    type: str = pydantic.Field(default='text_input')
    custom_id: str | None = pydantic.Field(max_length=100)
    label: str = pydantic.Field(max_length=45)
    style: Literal['short', 'long']
    placeholder: str = pydantic.Field(max_length=100)
    default_value: str | None = pydantic.Field(max_length=4000)
    required: bool
    min_length: int | None = pydantic.Field(ge=0, le=4000)
    max_length: int | None = pydantic.Field(ge=1, le=4000)


class SelectOption(pydantic.BaseModel):
    """A message select option"""

    label: str = pydantic.Field(max_length=100)
    value: str = pydantic.Field(max_length=100)
    description: str | None = pydantic.Field(max_length=100)
    emoji: Emoji | None
    default: bool


class Dropdown(pydantic.BaseModel):
    """A message dropdown"""

    type: Literal['select_menu', 'channel_select', 'role_select', 'user_select', 'mentionable_select']
    custom_id: str | None = pydantic.Field(max_length=100)
    options: list[SelectOption]  # will be empty if it's a channel, role, or user select
    placeholder: str | None = pydantic.Field(max_length=150)
    min_values: int = pydantic.Field(ge=0, le=25)
    max_values: int = pydantic.Field(ge=1, le=25)
    disabled: bool


class ActionRow(pydantic.BaseModel):
    """A message component (button, select, etc.)"""

    type: str = pydantic.Field(default='action_row')
    children: list[Button | TextInput | Dropdown]  # children can be buttons, selects, etc.


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
    A channel, role, or user mention in a message
    """

    type: Literal['channel', 'role', 'user']
    target: int


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
    total_votes: int
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
    available: bool
    guild_id: int
    creator_id: int
    reference_emoji: str


class Sticker(pydantic.BaseModel):
    """A message sticker"""

    sticker_id: int
    message_id: int
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
    discord.MessageType.chat_input_command: 'application_command',
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
    discord.MessageType.guild_incident_alert_mode_enabled: 'guild_incident_alert_mode_enabled',
    discord.MessageType.guild_incident_alert_mode_disabled: 'guild_incident_alert_mode_disabled',
    discord.MessageType.guild_incident_report_raid: 'guild_incident_report_raid',
    discord.MessageType.guild_incident_report_false_alarm: 'guild_incident_report_false_alarm',
}


class MessageFlags(pydantic.BaseModel):
    """
    Message flags
    """

    crossposted: bool
    ephemeral: bool
    failed_to_mention_some_roles_in_thread: bool
    has_thread: bool
    is_crossposted: bool
    loading: bool
    silent: bool
    source_message_deleted: bool
    suppress_embeds: bool
    urgent: bool
    voice: bool


class Asset(pydantic.BaseModel):
    """
    An asset or image
    """

    key: str
    url: str  # 1024x1024 png or gif
    animated: bool


class MessageApplication(pydantic.BaseModel):
    """
    A message application
    """

    id: int
    name: str
    description: str
    icon: Asset | None
    cover: Asset | None  # permanence paradox


class Activity(pydantic.BaseModel):
    """
    Activity sent with a message
    """

    application: MessageApplication | None
    activity_type: int | None
    party_id: str | None


class MessageEdition(pydantic.BaseModel):
    """Data specific to each edition of a message"""

    content: str
    timestamp: int
    attachments: list[MessageAttachment]
    embeds: list[MessageEmbed]
    reactions: list[ReactionChangeEvent]
    pinned: bool
    deleted: bool  # Deleted + edition timestamp = deletion time
    mentions: list[Mention]  # will need to combine member, channel & role here
    components: list[ActionRow | Button | Dropdown] = pydantic.Field(default_factory=list)
    activity: Optional[Activity] = pydantic.Field(default=None)


class MessageIndex(pydantic.BaseModel):
    """One per message, contains revision instances & data constant between revisions"""

    id: int
    editions: list[MessageEdition]
    author_id: int
    created_at: int
    channel_id: int
    guild_id: int | None = pydantic.Field(default=0)
    pinned: bool = pydantic.Field(default=False)
    deleted: bool = pydantic.Field(default=False)
    jump_url: str
    poll: MessagePoll | None = pydantic.Field(default=None)
    stickers: list[Sticker] | list = pydantic.Field(default_factory=list)
    thread_id: int | None = pydantic.Field(default=0)
    parent_interaction_id: int | None = pydantic.Field(default=0)
    reference_message_id: int | None = pydantic.Field(default=0)
    tts: bool
    type: str  # using MESSAGE_TYPES dict
    webhook_id: int | None = pydantic.Field(default=0)
    system: bool
    flags: MessageFlags
    nsfw_channel: bool  # don't post in logs unless log channel is NSFW
