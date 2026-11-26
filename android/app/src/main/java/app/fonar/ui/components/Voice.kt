package app.fonar.ui.components

import android.content.Context
import android.media.MediaPlayer
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material.icons.outlined.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.fonar.data.ApiException
import app.fonar.data.VoiceOption
import app.fonar.data.VoicesRes
import app.fonar.graph
import app.fonar.ui.theme.Fonar
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Plays one voice-over at a time (MP3 bytes from the server). */
object VoicePlayer {
    private var player: MediaPlayer? = null
    private val _playing = MutableStateFlow<String?>(null)
    /** Key of what is playing now (a message id, "preview"), or null. */
    val playing: StateFlow<String?> = _playing

    suspend fun play(context: Context, key: String, data: ByteArray) {
        stop()
        val file = withContext(Dispatchers.IO) {
            File(context.cacheDir, "voice_${key.hashCode().toUInt()}.mp3").also { it.writeBytes(data) }
        }
        val p = MediaPlayer()
        try {
            p.setDataSource(file.absolutePath)
            p.setOnCompletionListener { if (player === it) stop() }
            p.prepare()
            p.start()
            player = p
            _playing.value = key
        } catch (e: Exception) {
            p.release()
            throw ApiException(0, "play_failed", "Не удалось воспроизвести озвучку.")
        }
    }

    fun stop() {
        player?.let { runCatching { it.stop() }; it.release() }
        player = null
        _playing.value = null
    }
}

private val FALLBACK_VOICES = VoicesRes(
    available = true,
    voices = listOf(
        VoiceOption("alloy", "Alloy — нейтральный, ровный"), VoiceOption("ash", "Ash — мужской, мягкий"),
        VoiceOption("cedar", "Cedar — мужской, глубокий"), VoiceOption("coral", "Coral — женский, тёплый"),
        VoiceOption("echo", "Echo — мужской, спокойный"), VoiceOption("fable", "Fable — рассказчик, выразительный"),
        VoiceOption("marin", "Marin — женский, естественный"), VoiceOption("nova", "Nova — женский, живой"),
        VoiceOption("onyx", "Onyx — мужской, низкий"), VoiceOption("sage", "Sage — женский, спокойный"),
        VoiceOption("shimmer", "Shimmer — женский, светлый"), VoiceOption("verse", "Verse — мужской, эмоциональный"),
    ),
    manners = listOf("спокойно и мягко", "тепло и нежно", "игриво, с улыбкой", "дерзко и насмешливо",
        "холодно и сдержанно", "взволнованно", "шёпотом, интимно"),
    timbres = listOf("низкий, бархатный", "глубокий, с хрипотцой", "средний, чистый", "высокий, звонкий", "мягкий, тёплый"),
)

/** Voice of a character: a voice, a manner of speaking and a timbre (free text with ready-made options),
 *  and a button to hear it. Used in the character editor, story cards and the story editor. */
@Composable
fun VoiceFields(
    voice: String,
    manner: String,
    timbre: String,
    onVoice: (String) -> Unit,
    onManner: (String) -> Unit,
    onTimbre: (String) -> Unit,
    tagPrefix: String = "voice",
    enabled: Boolean = true,
) {
    val graph = LocalContext.current.graph
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var options by remember { mutableStateOf(FALLBACK_VOICES) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val playing by VoicePlayer.playing.collectAsState()
    LaunchedEffect(Unit) { runCatching { graph.api.voices() }.onSuccess { if (it.voices.isNotEmpty()) options = it } }

    val chipColors = FilterChipDefaults.filterChipColors(
        selectedContainerColor = Fonar.Lamp.copy(alpha = 0.22f), selectedLabelColor = Fonar.Text,
    )
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Голос для озвучки", fontWeight = FontWeight.SemiBold)
        if (!options.available) {
            Text("Озвучка не настроена на сервере.", color = Fonar.Faint, style = MaterialTheme.typography.bodySmall)
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip(selected = voice.isBlank(), enabled = enabled, onClick = { onVoice("") },
                label = { Text("Авто") }, colors = chipColors, modifier = Modifier.testTag("${tagPrefix}_auto"))
            options.voices.forEach { v ->
                FilterChip(selected = voice == v.id, enabled = enabled, onClick = { onVoice(v.id) },
                    label = { Text(v.label) }, colors = chipColors, modifier = Modifier.testTag("${tagPrefix}_${v.id}"))
            }
        }
        OutlinedTextField(
            value = manner, onValueChange = { if (it.length <= 200) onManner(it) }, enabled = enabled,
            label = { Text("Манера речи") }, placeholder = { Text("например: дерзко и насмешливо", color = Fonar.Faint) },
            singleLine = true, colors = glassFieldColors(Fonar.Surface),
            modifier = Modifier.fillMaxWidth().testTag("${tagPrefix}_manner"),
        )
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            options.manners.forEach { m ->
                FilterChip(selected = manner == m, enabled = enabled, onClick = { onManner(m) }, label = { Text(m) }, colors = chipColors)
            }
        }
        OutlinedTextField(
            value = timbre, onValueChange = { if (it.length <= 200) onTimbre(it) }, enabled = enabled,
            label = { Text("Тембр") }, placeholder = { Text("например: низкий, с хрипотцой", color = Fonar.Faint) },
            singleLine = true, colors = glassFieldColors(Fonar.Surface),
            modifier = Modifier.fillMaxWidth().testTag("${tagPrefix}_timbre"),
        )
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            options.timbres.forEach { t ->
                FilterChip(selected = timbre == t, enabled = enabled, onClick = { onTimbre(t) }, label = { Text(t) }, colors = chipColors)
            }
        }
        val isPlaying = playing == "preview"
        OutlinedButton(
            onClick = {
                if (isPlaying) { VoicePlayer.stop(); return@OutlinedButton }
                busy = true
                error = null
                scope.launch {
                    try {
                        VoicePlayer.play(context, "preview", graph.api.voicePreview(voice, manner, timbre))
                    } catch (e: Exception) {
                        error = (e as? ApiException)?.message ?: "Нет связи с сервером."
                    } finally {
                        busy = false
                    }
                }
            },
            enabled = !busy && options.available,
            shape = RoundedCornerShape(999.dp),
            modifier = Modifier.testTag("${tagPrefix}_preview"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
            else Icon(if (isPlaying) Icons.Outlined.Stop else Icons.Outlined.PlayArrow, null, Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text(if (isPlaying) "Стоп" else "Прослушать голос")
        }
        error?.let { Text(it, color = Fonar.Error, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("${tagPrefix}_error")) }
    }
}
