package app.fonar.ui.card

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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import app.fonar.data.ApiException
import app.fonar.data.CharacterDto
import app.fonar.data.CharacterPatch
import app.fonar.data.RoomDto
import app.fonar.data.json
import app.fonar.graph
import app.fonar.ui.components.Avatar
import app.fonar.ui.components.CenterLoading
import app.fonar.ui.components.ErrorBox
import app.fonar.ui.components.SectionTitle
import app.fonar.ui.components.actionText
import app.fonar.ui.editor.CharacterFields
import app.fonar.ui.editor.RelTarget
import app.fonar.ui.theme.Fonar
import kotlinx.coroutines.launch

/** Character card opened from the chat. The story owner can edit it and go straight
 *  back to the scene; changes apply from the next AI reaction for both players. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CharacterCardScreen(nav: NavHostController, roomId: String, charId: String) {
    val context = LocalContext.current
    val graph = context.graph
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    var room by remember { mutableStateOf<RoomDto?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var draftJson by rememberSaveable { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    var uploading by remember { mutableStateOf(false) }

    suspend fun load() {
        try {
            val r = graph.api.room(roomId).room
            room = r
            if (draftJson == null) {
                r.story.characters.firstOrNull { it.id == charId }?.let { draftJson = json.encodeToString(CharacterDto.serializer(), it) }
            }
            error = null
        } catch (e: Exception) {
            error = (e as? ApiException)?.message ?: "Нет связи с сервером"
        }
    }
    LaunchedEffect(Unit) { load() }

    val r = room
    val original = r?.story?.characters?.firstOrNull { it.id == charId }
    val draft = draftJson?.let { json.decodeFromString(CharacterDto.serializer(), it) }
    val owner = r?.my_role == "owner"

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null && draft != null) {
            uploading = true
            scope.launch {
                try {
                    val img = graph.api.uploadImage(context, uri, 512)
                    draftJson = json.encodeToString(CharacterDto.serializer(), draft.copy(avatar_image_id = img.id))
                } catch (e: Exception) {
                    snackbar.showSnackbar((e as? ApiException)?.message ?: "Не удалось загрузить картинку")
                } finally {
                    uploading = false
                }
            }
        }
    }

    fun save() {
        val d = draft ?: return
        val o = original ?: return
        if (d.name.isBlank()) { scope.launch { snackbar.showSnackbar("Имя не может быть пустым") }; return }
        saving = true
        scope.launch {
            try {
                graph.api.patchCharacter(
                    r!!.story.id!!, charId,
                    CharacterPatch(
                        name = d.name.takeIf { it != o.name },
                        avatar_image_id = d.avatar_image_id.takeIf { it != o.avatar_image_id && it != null },
                        age = d.age, appearance = d.appearance, habits = d.habits, personality = d.personality,
                        motivation = d.motivation, backstory = d.backstory, speech_style = d.speech_style,
                        relationships = d.relationships, example_lines = d.example_lines,
                    ),
                )
                nav.popBackStack()
            } catch (e: Exception) {
                snackbar.showSnackbar((e as? ApiException)?.message ?: "Нет связи — изменения не сохранены")
            } finally {
                saving = false
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                navigationIcon = { IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад") } },
                title = { Text(original?.name ?: "Персонаж") },
                actions = {
                    if (owner && draft != null) {
                        if (saving) CircularProgressIndicator(Modifier.size(22.dp).padding(end = 4.dp), strokeWidth = 2.dp)
                        else Button(onClick = { save() }, enabled = !uploading, modifier = Modifier.padding(end = 8.dp).testTag("card_save")) {
                            Text("Сохранить и в сцену")
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Fonar.Surface),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Fonar.Night,
    ) { pad ->
        val base = Modifier.fillMaxSize().padding(pad).consumeWindowInsets(pad).imePadding()
        when {
            r == null && error != null -> ErrorBox(error!!, { scope.launch { load() } }, base)
            r == null -> CenterLoading(base)
            original == null || draft == null -> ErrorBox("Персонаж не найден", null, base)
            owner -> Column(base.verticalScroll(rememberScrollState()).padding(16.dp)) {
                Text("Правки начнут действовать со следующего ответа ИИ — у обоих игроков.",
                    color = Fonar.Muted, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(12.dp))
                val targets = r.story.characters.filter { it.id != charId }.map { RelTarget(it.id!!, it.name) }
                CharacterFields(
                    c = draft,
                    onChange = { draftJson = json.encodeToString(CharacterDto.serializer(), it) },
                    relTargets = targets,
                    avatarUrl = draft.avatar_image_id?.let { graph.api.ownImageUrl(it) },
                    uploading = uploading,
                    onPickAvatar = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                    showRole = false,
                    canBeHero = false,
                )
            }
            else -> ReadOnlyCard(original, r, roomId, base)
        }
    }
}

@Composable
private fun ReadOnlyCard(c: CharacterDto, room: RoomDto, roomId: String, modifier: Modifier) {
    val graph = LocalContext.current.graph
    Column(modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Avatar(c.name, c.avatar_image_id?.let { graph.api.roomImageUrl(roomId, it) }, 84.dp)
            Spacer(Modifier.width(16.dp))
            Column {
                Text(c.name, style = MaterialTheme.typography.headlineSmall)
                if (c.age.isNotBlank()) Text(c.age, color = Fonar.Muted)
                Text(if (c.role == "hero") "Герой игрока" else "Ведёт ИИ", color = Fonar.Sea, style = MaterialTheme.typography.labelMedium)
            }
        }
        listOf(
            "Характер" to c.personality, "Манера речи" to c.speech_style, "Привычки" to c.habits, "Внешность" to c.appearance,
            "Мотивация" to c.motivation, "Предыстория" to c.backstory,
        ).filter { it.second.isNotBlank() }.forEach { (label, value) ->
            SectionTitle(label)
            Text(value, style = MaterialTheme.typography.bodyLarge)
        }
        val rels = c.relationships.mapNotNull { (k, v) -> room.story.characters.firstOrNull { it.id == k }?.let { it.name to v } }
        if (rels.isNotEmpty()) {
            SectionTitle("Отношение")
            rels.forEach { (n, v) -> Text("$n — $v", style = MaterialTheme.typography.bodyLarge) }
        }
        if (c.example_lines.isNotBlank()) {
            SectionTitle("Примеры реплик")
            c.example_lines.lines().filter { it.isNotBlank() }.forEach { Text(actionText(it), style = MaterialTheme.typography.bodyLarge) }
        }
        Text("Менять карточку может только хозяин истории.", color = Fonar.Faint, style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Normal, modifier = Modifier.padding(top = 20.dp))
    }
}
