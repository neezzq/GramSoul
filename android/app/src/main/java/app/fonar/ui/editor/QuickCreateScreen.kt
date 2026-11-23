package app.fonar.ui.editor

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import app.fonar.Routes
import app.fonar.data.ApiException
import app.fonar.data.QuickDraft
import app.fonar.data.QuickStoryReq
import app.fonar.graph
import app.fonar.ui.components.Field
import app.fonar.ui.components.ImagePickBox
import app.fonar.ui.theme.Fonar
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuickCreateScreen(nav: NavHostController) {
    val context = LocalContext.current
    val graph = context.graph
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    var d by remember { mutableStateOf(graph.drafts.loadQuick() ?: QuickDraft()) }
    var busy by remember { mutableStateOf(false) }
    var uploading by remember { mutableStateOf(false) }

    LaunchedEffect(d) {
        delay(400)
        graph.drafts.saveQuick(d)
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) {
            uploading = true
            scope.launch {
                try {
                    d = d.copy(avatarImageId = graph.api.uploadImage(context, uri, 512).id)
                } catch (e: Exception) {
                    snackbar.showSnackbar((e as? ApiException)?.message ?: "Не удалось загрузить картинку")
                } finally {
                    uploading = false
                }
            }
        }
    }

    fun create() {
        if (d.name.isBlank()) { scope.launch { snackbar.showSnackbar("Дай персонажу имя") }; return }
        busy = true
        scope.launch {
            try {
                val story = graph.api.quickStory(
                    QuickStoryReq(d.name.trim(), d.avatarImageId, d.personality.trim(), d.speechStyle.trim(), d.startLine.trim())
                ).story
                val room = graph.api.createRoom(story.id!!).room
                graph.drafts.deleteQuick()
                nav.navigate(Routes.chat(room.id)) { popUpTo(Routes.HOME) }
            } catch (e: Exception) {
                snackbar.showSnackbar((e as? ApiException)?.message ?: "Нет связи с сервером. Черновик сохранён.")
            } finally {
                busy = false
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                navigationIcon = { IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад") } },
                title = { Text("Быстрый персонаж") },
                actions = {
                    TextButton(onClick = { nav.navigate(Routes.editor()) { popUpTo(Routes.HOME) } }) { Text("Полный редактор") }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Fonar.Night),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Fonar.Night,
    ) { pad ->
        Column(
            Modifier.fillMaxSize().padding(pad).consumeWindowInsets(pad).imePadding().verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ImagePickBox(
                    d.avatarImageId?.let { graph.api.ownImageUrl(it) }, "Аватар", uploading, round = true, size = 88.dp,
                    onPick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                )
                Spacer(Modifier.width(14.dp))
                Field("Имя персонажа", d.name, { d = d.copy(name = it) }, maxLength = 40, testTag = "quick_name",
                    modifier = Modifier.weight(1f))
            }
            Field("Характер", d.personality, { d = d.copy(personality = it) }, minLines = 3, testTag = "quick_personality",
                hint = "Весёлая бариста, любит подкалывать посетителей")
            Field("Манера речи", d.speechStyle, { d = d.copy(speechStyle = it) }, minLines = 2, maxLength = 1000,
                testTag = "quick_speech", hint = "Говорит быстро, с шутками и сленгом")
            Field("Стартовая реплика", d.startLine, { d = d.copy(startLine = it) }, minLines = 2, testTag = "quick_start",
                hint = "*ставит перед тобой чашку* Тебе как обычно?")
            Text("Черновик сохраняется автоматически.", color = Fonar.Faint, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(4.dp))
            Button(onClick = { create() }, enabled = !busy && !uploading, modifier = Modifier.fillMaxWidth().height(52.dp)
                .testTag("quick_create")) {
                if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = Fonar.OnLamp)
                else Text("Создать и начать сцену")
            }
        }
    }
}
