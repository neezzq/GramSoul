package app.fonar.data

import kotlinx.serialization.Serializable

@Serializable
data class UserDto(val id: String, val nick: String)

@Serializable
data class RegisterReq(val nick: String)

@Serializable
data class RegisterRes(val token: String, val user: UserDto, val demo_story_id: String? = null)

@Serializable
data class MeRes(val user: UserDto)

@Serializable
data class ApiErrorBody(val detail: ApiErrorDetail? = null)

@Serializable
data class ApiErrorDetail(val code: String = "error", val message: String = "Ошибка")

// ---------------------------------------------------------------- friends
@Serializable
data class SearchRes(val user: UserDto, val relation: String, val request_id: String? = null)

@Serializable
data class FriendRequestReq(val nick: String)

@Serializable
data class FriendRequestDto(
    val id: String,
    val status: String,
    val direction: String,
    val user: UserDto,
    val updated_at: Long = 0,
)

@Serializable
data class FriendRequestRes(val request: FriendRequestDto, val created: Boolean = false, val already_friends: Boolean = false)

@Serializable
data class InviteDto(
    val id: String,
    val status: String,
    val room_id: String? = null,
    val story_title: String? = null,
    val from: UserDto? = null,
    val to: UserDto? = null,
)

@Serializable
data class FriendsRes(
    val friends: List<UserDto> = emptyList(),
    val incoming: List<FriendRequestDto> = emptyList(),
    val outgoing: List<FriendRequestDto> = emptyList(),
    val invites: List<InviteDto> = emptyList(),
)

@Serializable
data class InboxRes(val version: Long)

// ---------------------------------------------------------------- stories
@Serializable
data class CharacterDto(
    val id: String? = null,
    val key: String? = null,
    val role: String = "npc",
    val position: Int = 0,
    val name: String = "",
    val avatar_image_id: String? = null,
    val age: String = "",
    val appearance: String = "",
    val habits: String = "",
    val personality: String = "",
    val motivation: String = "",
    val backstory: String = "",
    val speech_style: String = "",
    val relationships: Map<String, String> = emptyMap(),
    val example_lines: String = "",
    val version: Int = 0,
)

@Serializable
data class StartMessageDto(val speaker: String = "narrator", val text: String = "")

@Serializable
data class StoryDto(
    val id: String? = null,
    val title: String = "",
    val description: String = "",
    val intro: String = "",
    val world_rules: String = "",
    val start_scene: String = "",
    val cover_image_id: String? = null,
    val is_demo: Boolean = false,
    val version: Int = 0,
    val updated_at: Long = 0,
    val characters: List<CharacterDto> = emptyList(),
    val start_messages: List<StartMessageDto> = emptyList(),
    val character_names: List<String> = emptyList(),
    val avatar_image_id: String? = null,
)

@Serializable
data class StoryRes(val story: StoryDto)

@Serializable
data class StoriesRes(val stories: List<StoryDto>)

@Serializable
data class QuickStoryReq(
    val name: String,
    val avatar_image_id: String? = null,
    val personality: String = "",
    val speech_style: String = "",
    val start_line: String = "",
)

@Serializable
data class StoryReq(
    val title: String,
    val description: String,
    val intro: String,
    val world_rules: String,
    val start_scene: String,
    val cover_image_id: String?,
    val characters: List<CharacterDto>,
    val start_messages: List<StartMessageDto>,
)

@Serializable
data class CharacterPatch(
    val name: String? = null,
    val avatar_image_id: String? = null,
    val clear_avatar: Boolean = false,
    val age: String? = null,
    val appearance: String? = null,
    val habits: String? = null,
    val personality: String? = null,
    val motivation: String? = null,
    val backstory: String? = null,
    val speech_style: String? = null,
    val relationships: Map<String, String>? = null,
    val example_lines: String? = null,
)

@Serializable
data class CharacterRes(val character: CharacterDto)

@Serializable
data class ImageRes(val id: String, val width: Int = 0, val height: Int = 0)

// ---------------------------------------------------------------- rooms
@Serializable
data class SeatDto(
    val index: Int,
    val user: UserDto? = null,
    val hero_character_id: String? = null,
    val hero_name: String = "",
)

@Serializable
data class RoomDto(
    val id: String,
    val story: StoryDto,
    val my_role: String,
    val my_seat: Int,
    val seats: List<SeatDto>,
    val scene_location: String = "",
    val summary: String = "",
    val invite: InviteDto? = null,
    val rev: Long = 0,
    val meta_rev: Long = 0,
    val ai_mode: String = "local",
    val cloud_available: Boolean = false,
    val images_available: Boolean = false,
    val ai_models: Map<String, String> = emptyMap(),
)

@Serializable
data class RoomRes(val room: RoomDto)

@Serializable
data class RoomListItem(
    val id: String,
    val story_title: String,
    val cover_image_id: String? = null,
    val my_role: String,
    val partner: UserDto? = null,
    val last_message: String = "",
    val updated_at: Long = 0,
)

@Serializable
data class RoomsRes(val rooms: List<RoomListItem> = emptyList(), val invites: List<InviteDto> = emptyList())

@Serializable
data class InviteReq(val user_id: String)

@Serializable
data class InviteRes(val invite: InviteDto)

@Serializable
data class MessageDto(
    val id: String,
    val seq: Long,
    val rev: Long = 0,
    val kind: String,
    val user_id: String? = null,
    val character_id: String? = null,
    val speaker_name: String = "",
    val text: String,
    val generation_id: String? = null,
    val image_id: String? = null,
    val hidden: Boolean = false,
    val client_id: String? = null,
    val created_at: Long = 0,
)

@Serializable
data class GenerationStats(
    val prompt_tokens: Int? = null,
    val output_tokens: Int? = null,
    val prompt_ms: Long? = null,
    val output_ms: Long? = null,
    val total_ms: Long? = null,
)

@Serializable
data class GenerationDto(
    val id: String,
    val kind: String,
    val status: String,
    val error: String? = null,
    val partial: String? = null,
    val queue_position: Int? = null,
    val stats: GenerationStats? = null,
)

@Serializable
data class SyncRes(
    val rev: Long,
    val messages: List<MessageDto> = emptyList(),
    val generation: GenerationDto? = null,
    val image_job: ImageJobDto? = null,
    val room: RoomDto? = null,
    val full: Boolean = false,
    val pv: Long = -1,
)

@Serializable
data class MessageReq(val client_id: String, val text: String)

@Serializable
data class PostMessageRes(val message: MessageDto, val generation: GenerationDto? = null, val duplicate: Boolean = false)

@Serializable
data class ActionReq(val client_id: String)

@Serializable
data class GenerationRes(val generation: GenerationDto? = null, val duplicate: Boolean = false)

@Serializable
data class SceneReq(val location: String)

@Serializable
data class LastPromptRes(
    val generation_id: String,
    val kind: String,
    val status: String,
    val model: String? = null,
    val prompt: String,
    val card_versions: Map<String, Int> = emptyMap(),
    val raw_output: String? = null,
    val error: String? = null,
    val stats: GenerationStats? = null,
)

@Serializable
data class OkRes(val ok: Boolean = true)

@Serializable
data class ImageJobDto(
    val id: String,
    val status: String,
    val error: String? = null,
    val prompt: String? = null,
    val image_id: String? = null,
)

@Serializable
data class RoomSettingsReq(val ai_mode: String)

@Serializable
data class RoomSettingsRes(val ai_mode: String)

@Serializable
data class PhotoReq(val client_id: String, val prompt: String = "")

@Serializable
data class PhotoRes(val image_job: ImageJobDto? = null, val duplicate: Boolean = false)
