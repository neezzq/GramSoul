package app.fonar.ui.chat

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import app.fonar.data.ApiException
import app.fonar.data.RoomDto
import app.fonar.graph
import app.fonar.ui.components.CenterLoading
import app.fonar.ui.components.DEFAULT_STYLES
import app.fonar.ui.components.ErrorBox
import app.fonar.ui.components.StyleGrid
import app.fonar.ui.components.glassFieldColors
import app.fonar.ui.theme.Fonar
import kotlinx.coroutines.launch

/** Pictures of one chat: a fixed description of the scenes and a style. The AI keeps to them every time,
 *  so places and people do not change from picture to picture. Only the owner of the scene edits them. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ImageSettingsScreen(nav: NavHostController, roomId: String) {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    var room by remember { mutableStateOf<RoomDto?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var notes by rememberSaveable { mutableStateOf<String?>(null) }
    var style by rememberSaveable { mutableStateOf<String?>(null) }
    var styles by remember { mutableStateOf(DEFAULT_STYLES) }
    var busy by remember { mutableStateOf(false) }

    suspend fun load() {
        try {
            val r = graph.api.room(roomId).room
            room = r
            if (notes == null) notes = r.image_notes
            if (style == null) style = r.image_style.ifBlank { "aesthetic" }
            loadError = null
        } catch (e: Exception) {
            loadError = (e as? ApiException)?.message ?: "Нет связи с сервером."
        }
    }
    LaunchedEffect(Unit) {
        load()
        runCatching { graph.api.avatarStyles().styles }.onSuccess { if (it.isNotEmpty()) styles = it }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Картинки чата") },
                navigationIcon = {
                    IconButton(onClick = { nav.popBackStack() }, modifier = Modifier.testTag("back")) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Fonar.Night),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Fonar.Night,
    ) { pad ->
        val r = room
        when {
            r == null && loadError != null -> ErrorBox(loadError!!, { scope.launch { load() } }, Modifier.padding(pad))
            r == null -> CenterLoading(Modifier.padding(pad))
            else -> {
                val owner = r.my_role == "owner"
                Column(
                    Modifier.padding(pad).fillMaxSize().imePadding().verticalScroll(rememberScrollState())
                        .padding(horizontal = 20.dp).testTag("image_settings"),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(
                        "ИИ рисует сцены этого чата в выбранном стиле и всегда держится описания: место, обстановка, " +
                            "внешность героев. Так картинки не придумывают каждый раз что-то новое.",
                        color = Fonar.Muted, style = MaterialTheme.typography.bodyMedium,
                    )
                    OutlinedTextField(
                        value = notes.orEmpty(), onValueChange = { if (it.length <= 1000) notes = it }, enabled = owner,
                        label = { Text("Описание сцен") },
                        placeholder = { Text("Например: зимний посёлок у моря, вечер, тёплые окна. Ива — в чёрной куртке.", color = Fonar.Faint) },
                        minLines = 3, maxLines = 8,
                        supportingText = { Text("${notes.orEmpty().length}/1000") },
                        colors = glassFieldColors(Fonar.Surface),
                        modifier = Modifier.fillMaxWidth().testTag("image_notes"),
                    )
                    Text("Стиль", fontWeight = FontWeight.SemiBold)
                    StyleGrid(styles, style ?: "aesthetic", { style = it }, tagPrefix = "scene_style_", enabled = owner)
                    if (owner) {
                        Button(
                            onClick = {
                                busy = true
                                scope.launch {
                                    try {
                                        graph.api.setImageSettings(roomId, style ?: "aesthetic", notes.orEmpty().trim())
                                        nav.popBackStack()
                                    } catch (e: Exception) {
                                        snackbar.showSnackbar((e as? ApiException)?.message ?: "Нет связи с сервером.")
                                    } finally {
                                        busy = false
                                    }
                                }
                            },
                            enabled = !busy,
                            modifier = Modifier.fillMaxWidth().height(52.dp).testTag("image_settings_save"),
                        ) { Text("Сохранить") }
                    } else {
                        Text("Менять может только хозяин сцены.", color = Fonar.Faint, style = MaterialTheme.typography.bodySmall)
                    }
                    Spacer(Modifier.height(24.dp))
                }
            }
        }
    }
}
