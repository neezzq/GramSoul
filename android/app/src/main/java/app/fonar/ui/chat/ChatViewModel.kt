package app.fonar.ui.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.fonar.AppGraph
import app.fonar.data.ApiException
import app.fonar.data.FriendsRes
import app.fonar.data.GenerationDto
import app.fonar.data.ImageJobDto
import app.fonar.data.LastPromptRes
import app.fonar.data.MessageDto
import app.fonar.data.NetworkException
import app.fonar.data.RoomDto
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.UUID

data class Pending(val clientId: String, val text: String, val failed: Boolean = false, val error: String? = null)

data class ChatState(
    val room: RoomDto? = null,
    val messages: List<MessageDto> = emptyList(),
    val pending: List<Pending> = emptyList(),
    val generation: GenerationDto? = null,
    val imageJob: ImageJobDto? = null,
    val rev: Long = 0,
    val online: Boolean = true,
    val loadError: String? = null,
    val closed: Boolean = false,
    val toast: String? = null,
    val actionBusy: Boolean = false,
    val friends: FriendsRes? = null,
    val lastPrompt: LastPromptRes? = null,
)

class ChatViewModel(private val g: AppGraph, val roomId: String) : ViewModel() {
    private val _state = MutableStateFlow(ChatState())
    val state: StateFlow<ChatState> = _state
    private val all = LinkedHashMap<String, MessageDto>()
    private var pv = -1L
    private var syncJob: Job? = null

    val myUserId: String? get() = g.me?.id

    init {
        startSync()
    }

    /** Keeps the chat in sync: long-poll with the last known revision, so after any
     *  network drop the server returns everything that was missed. */
    fun startSync() {
        syncJob?.cancel()
        syncJob = viewModelScope.launch {
            var backoff = 1000L
            var first = true
            while (isActive) {
                try {
                    val res = g.api.sync(roomId, _state.value.rev, pv, if (first) 0 else 25)
                    first = false
                    backoff = 1000L
                    apply(res.rev, res.messages, res.generation, res.room, res.pv)
                    _state.update { it.copy(imageJob = res.image_job) }
                    if (!_state.value.online) {
                        _state.update { it.copy(online = true) }
                        resendFailed()
                    }
                } catch (e: NetworkException) {
                    _state.update { it.copy(online = false) }
                    delay(backoff)
                    backoff = (backoff * 2).coerceAtMost(10_000L)
                } catch (e: ApiException) {
                    if (e.status == 404) {
                        _state.update { it.copy(closed = true, loadError = "Сцена недоступна: её удалили или тебя в ней больше нет.") }
                        return@launch
                    }
                    _state.update { it.copy(loadError = e.message) }
                    delay(3000)
                }
            }
        }
    }

    private fun apply(rev: Long, msgs: List<MessageDto>, gen: GenerationDto?, room: RoomDto?, newPv: Long) {
        msgs.forEach { all[it.id] = it }
        pv = newPv
        val visible = all.values.filter { !it.hidden }.sortedBy { it.seq }
        val confirmed = msgs.mapNotNull { it.client_id }.toSet()
        _state.update { s ->
            s.copy(
                rev = maxOf(rev, s.rev),
                messages = visible,
                generation = gen,
                room = room ?: s.room,
                pending = s.pending.filterNot { it.clientId in confirmed },
                loadError = null,
            )
        }
    }

    fun send(text: String) {
        val t = text.trim()
        if (t.isEmpty()) return
        val p = Pending(UUID.randomUUID().toString(), t)
        _state.update { it.copy(pending = it.pending + p) }
        post(p)
    }

    private fun post(p: Pending) {
        viewModelScope.launch {
            try {
                val res = g.api.postMessage(roomId, p.clientId, p.text)
                all[res.message.id] = res.message
                _state.update { s ->
                    s.copy(
                        pending = s.pending.filterNot { it.clientId == p.clientId },
                        messages = all.values.filter { !it.hidden }.sortedBy { it.seq },
                        generation = res.generation ?: s.generation,
                    )
                }
            } catch (e: NetworkException) {
                markFailed(p, "Не отправлено — нет связи")
            } catch (e: ApiException) {
                markFailed(p, e.message)
            }
        }
    }

    private fun markFailed(p: Pending, error: String) {
        _state.update { s -> s.copy(pending = s.pending.map { if (it.clientId == p.clientId) it.copy(failed = true, error = error) else it }) }
    }

    /** Same client id → the server never stores the message twice. */
    fun resend(clientId: String) {
        val p = _state.value.pending.firstOrNull { it.clientId == clientId } ?: return
        _state.update { s -> s.copy(pending = s.pending.map { if (it.clientId == clientId) it.copy(failed = false, error = null) else it }) }
        post(p)
    }

    fun discard(clientId: String) {
        _state.update { s -> s.copy(pending = s.pending.filterNot { it.clientId == clientId }) }
    }

    private fun resendFailed() {
        _state.value.pending.filter { it.failed && it.error?.startsWith("Не отправлено") == true }.forEach { resend(it.clientId) }
    }

    private fun action(block: suspend (String) -> Unit) {
        if (_state.value.actionBusy) return
        _state.update { it.copy(actionBusy = true) }
        viewModelScope.launch {
            try {
                block(UUID.randomUUID().toString())
            } catch (e: ApiException) {
                _state.update { it.copy(toast = e.message) }
            } catch (e: NetworkException) {
                _state.update { it.copy(toast = "Нет связи с сервером") }
            } finally {
                _state.update { it.copy(actionBusy = false) }
            }
        }
    }

    fun continueScene() = action { id -> g.api.continueScene(roomId, id).generation?.let { gen -> _state.update { it.copy(generation = gen) } } }
    fun regenerate() = action { id -> g.api.regenerate(roomId, id).generation?.let { gen -> _state.update { it.copy(generation = gen) } } }
    fun retry() = action { id -> g.api.retry(roomId, id).generation?.let { gen -> _state.update { it.copy(generation = gen) } } }

    fun setScene(location: String) = action { g.api.setScene(roomId, location) }

    fun setAiMode(mode: String) = action {
        g.api.setAiMode(roomId, mode)
        _state.update { s -> s.copy(room = s.room?.copy(ai_mode = mode)) }
    }

    fun requestPhoto(prompt: String) = action { id ->
        val res = g.api.photo(roomId, id, prompt.trim())
        _state.update { it.copy(imageJob = res.image_job ?: it.imageJob) }
    }

    fun loadFriends() {
        viewModelScope.launch { runCatching { g.api.friends() }.onSuccess { f -> _state.update { it.copy(friends = f) } } }
    }

    fun invite(userId: String) = action {
        g.api.invite(roomId, userId)
        _state.update { it.copy(toast = "Приглашение отправлено") }
    }

    fun loadLastPrompt() {
        viewModelScope.launch {
            try {
                val p = g.api.lastPrompt(roomId)
                _state.update { it.copy(lastPrompt = p) }
            } catch (e: Exception) {
                _state.update { it.copy(toast = (e as? ApiException)?.message ?: "Нет связи") }
            }
        }
    }

    fun clearLastPrompt() = _state.update { it.copy(lastPrompt = null) }
    fun consumeToast() = _state.update { it.copy(toast = null) }

    fun leave(onDone: () -> Unit) = action {
        g.api.deleteRoom(roomId)
        onDone()
    }
}
