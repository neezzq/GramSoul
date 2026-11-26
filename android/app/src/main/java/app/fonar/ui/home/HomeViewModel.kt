package app.fonar.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.fonar.AppGraph
import app.fonar.data.ApiException
import app.fonar.data.FriendsRes
import app.fonar.data.NetworkException
import app.fonar.data.RoomDto
import app.fonar.data.RoomListItem
import app.fonar.data.SearchRes
import app.fonar.data.StoryDraft
import app.fonar.data.StoryDto
import app.fonar.data.InviteDto
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class HomeState(
    val loading: Boolean = true,
    val offline: Boolean = false,
    val stories: List<StoryDto> = emptyList(),
    /** Published stories of other players (catalog). */
    val publicStories: List<StoryDto>? = null,
    val drafts: List<StoryDraft> = emptyList(),
    val rooms: List<RoomListItem> = emptyList(),
    val invites: List<InviteDto> = emptyList(),
    val friends: FriendsRes = FriendsRes(),
    val message: String? = null,
    // friend search
    val searchBusy: Boolean = false,
    val searchQuery: String = "",
    val searchResults: List<SearchRes> = emptyList(),
    val searchError: String? = null,
)

class HomeViewModel(private val g: AppGraph) : ViewModel() {
    private val _state = MutableStateFlow(HomeState())
    val state: StateFlow<HomeState> = _state
    private var inboxJob: Job? = null

    init {
        refresh()
        startInbox()
    }

    private fun err(e: Throwable): String = when (e) {
        is ApiException -> e.message
        is NetworkException -> "Нет связи с сервером"
        else -> "Что-то пошло не так"
    }

    fun refresh() {
        viewModelScope.launch {
            try {
                val stories = g.api.stories().stories
                val rooms = g.api.rooms()
                val friends = g.api.friends()
                _state.update {
                    it.copy(loading = false, offline = false, stories = stories, rooms = rooms.rooms,
                        invites = rooms.invites, friends = friends, drafts = g.drafts.newStoryDrafts())
                }
            } catch (e: Exception) {
                _state.update { it.copy(loading = false, offline = e is NetworkException, drafts = g.drafts.newStoryDrafts(),
                    message = if (e is NetworkException) null else err(e)) }
            }
        }
    }

    /** Long-poll on the user's inbox: friend requests and game invites arrive within a second. */
    private fun startInbox() {
        inboxJob?.cancel()
        inboxJob = viewModelScope.launch {
            var version = -1L
            var backoff = 1000L
            while (isActive) {
                try {
                    val v = g.api.inboxWait(if (version < 0) Long.MAX_VALUE else version, if (version < 0) 0 else 25).version
                    if (version >= 0 && v != version) refreshSocial()
                    version = v
                    backoff = 1000L
                    if (_state.value.offline) refresh()
                } catch (e: NetworkException) {
                    _state.update { it.copy(offline = true) }
                    delay(backoff)
                    backoff = (backoff * 2).coerceAtMost(15_000L)
                } catch (e: ApiException) {
                    delay(5_000)
                }
            }
        }
    }

    private suspend fun refreshSocial() {
        runCatching {
            val friends = g.api.friends()
            val rooms = g.api.rooms()
            _state.update { it.copy(friends = friends, rooms = rooms.rooms, invites = rooms.invites, offline = false) }
        }
    }

    fun consumeMessage() = _state.update { it.copy(message = null) }

    // ---------------------------------------------------------------- friends
    private var searchJob: Job? = null

    /** Search by the start or any part of a nick; the screen debounces typing. */
    fun search(query: String) {
        val q = query.trim()
        searchJob?.cancel()
        if (q.length < 2) {
            _state.update { it.copy(searchQuery = q, searchResults = emptyList(), searchBusy = false, searchError = null) }
            return
        }
        _state.update { it.copy(searchQuery = q, searchBusy = true, searchError = null) }
        searchJob = viewModelScope.launch {
            try {
                val r = g.api.searchPeople(q)
                _state.update { it.copy(searchBusy = false, searchResults = r.users) }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update { it.copy(searchBusy = false, searchError = err(e)) }
            }
        }
    }

    private fun setRelation(match: (SearchRes) -> Boolean, rel: String, requestId: String? = null) =
        _state.update { s ->
            s.copy(searchResults = s.searchResults.map { if (match(it)) it.copy(relation = rel, request_id = requestId ?: it.request_id) else it })
        }

    fun sendRequest(nick: String) {
        viewModelScope.launch {
            try {
                val r = g.api.sendFriendRequest(nick)
                val rel = if (r.already_friends) "friends" else "outgoing_${r.request.status}"
                setRelation({ it.user.nick == nick }, rel, r.request.id)
                refreshSocial()
            } catch (e: Exception) {
                _state.update { it.copy(searchError = err(e)) }
            }
        }
    }

    fun answerRequest(id: String, accept: Boolean) {
        viewModelScope.launch {
            try {
                if (accept) g.api.acceptFriend(id) else g.api.declineFriend(id)
                refreshSocial()
                setRelation({ it.request_id == id }, if (accept) "friends" else "none")
            } catch (e: Exception) {
                _state.update { it.copy(message = err(e)) }
            }
        }
    }

    // ---------------------------------------------------------------- rooms
    fun answerInvite(id: String, accept: Boolean, onJoined: (String) -> Unit) {
        viewModelScope.launch {
            try {
                val r = if (accept) g.api.acceptInvite(id) else g.api.declineInvite(id)
                refreshSocial()
                if (accept) r.invite.room_id?.let(onJoined)
            } catch (e: Exception) {
                _state.update { it.copy(message = err(e)) }
                refreshSocial()
            }
        }
    }

    fun startRoom(storyId: String, withFriend: String?, onReady: (RoomDto) -> Unit) {
        viewModelScope.launch {
            try {
                val room = g.api.createRoom(storyId).room
                if (withFriend != null) g.api.invite(room.id, withFriend)
                onReady(room)
                refresh()
            } catch (e: Exception) {
                _state.update { it.copy(message = err(e)) }
            }
        }
    }

    fun loadPublicStories(q: String = "") {
        viewModelScope.launch {
            try {
                val list = g.api.publicStories(q).stories
                _state.update { it.copy(publicStories = list) }
            } catch (e: Exception) {
                _state.update { it.copy(message = err(e), publicStories = it.publicStories ?: emptyList()) }
            }
        }
    }

    /** Publish or hide a story (also when scenes in it already exist). */
    fun setStoryVisibility(id: String, public: Boolean) {
        viewModelScope.launch {
            try {
                g.api.setStoryVisibility(id, if (public) "public" else "private")
                _state.update { it.copy(message = if (public) "История опубликована" else "История снова личная") }
                refresh()
            } catch (e: Exception) {
                _state.update { it.copy(message = err(e)) }
            }
        }
    }

    fun deleteStory(id: String) {
        viewModelScope.launch {
            try {
                g.api.deleteStory(id); refresh()
            } catch (e: Exception) {
                _state.update { it.copy(message = err(e)) }
            }
        }
    }

    fun deleteDraft(id: String) {
        g.drafts.deleteStory(id)
        _state.update { it.copy(drafts = g.drafts.newStoryDrafts()) }
    }


    fun leaveRoom(id: String) {
        viewModelScope.launch {
            try {
                g.api.deleteRoom(id); refresh()
            } catch (e: Exception) {
                _state.update { it.copy(message = err(e)) }
            }
        }
    }
}
