package app.fonar.ui.editor

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.ArrowDropDown
import androidx.compose.material.icons.outlined.ArrowUpward
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import app.fonar.data.StartMessageDto
import app.fonar.data.StoryDraft
import app.fonar.data.StoryDto
import app.fonar.data.StoryReq
import app.fonar.graph
import app.fonar.ui.components.Avatar
import app.fonar.ui.components.Banner
import app.fonar.ui.components.CenterLoading
import app.fonar.ui.components.ErrorBox
import app.fonar.ui.components.Field
import app.fonar.ui.components.ImagePickBox
import app.fonar.ui.components.Pill
import app.fonar.ui.components.SectionTitle
import app.fonar.ui.theme.Fonar
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.UUID

private const val MAX_CHARACTERS = 10

private fun CharacterDto.ref(): String = id ?: key!!

private fun newStory() = StoryDto(
    title = "",
    characters = listOf(CharacterDto(key = "k-" + UUID.randomUUID(), role = "npc", name = "")),
    start_messages = listOf(StartMessageDto("narrator", "")),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StoryEditorScreen(nav: NavHostController, storyId: String?, draftId: String?) {
    val context = LocalContext.current
    val graph = context.graph
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    val effectiveDraftId = rememberSaveable { draftId ?: storyId?.let { "story-$it" } ?: ("new-" + UUID.randomUUID()) }
    var story by remember { mutableStateOf<StoryDto?>(null) }
    var serverId by remember { mutableStateOf(storyId) }
    var restored by remember { mutableStateOf(false) }
    var dirty by remember { mutableStateOf(false) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    var editing by rememberSaveable { mutableStateOf<Int?>(null) }
    var uploadingFor by remember { mutableStateOf<String?>(null) } // "cover" or character ref
    var pickTarget by remember { mutableStateOf<String?>(null) }

    suspend fun load() {
        val local = graph.drafts.loadStory(effectiveDraftId)
        if (local != null) {
            story = local.story; serverId = local.serverId ?: storyId; restored = true; return
        }
        if (storyId == null) { story = newStory(); return }
        try {
            story = graph.api.story(storyId).story
            loadError = null
        } catch (e: Exception) {
            loadError = (e as? ApiException)?.message ?: "Нет связи с сервером"
        }
    }
    LaunchedEffect(Unit) { if (story == null) load() }

    // autosave the draft locally
    LaunchedEffect(story, dirty) {
        val s = story ?: return@LaunchedEffect
        if (!dirty) return@LaunchedEffect
        delay(400)
        graph.drafts.saveStory(StoryDraft(effectiveDraftId, serverId, s))
    }

    fun update(s: StoryDto) { story = s; dirty = true }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        val target = pickTarget
        if (uri != null && target != null) {
            uploadingFor = target
            scope.launch {
                try {
                    val img = graph.api.uploadImage(context, uri, if (target == "cover") 1280 else 512)
                    val s = story ?: return@launch
                    update(
                        if (target == "cover") s.copy(cover_image_id = img.id)
                        else s.copy(characters = s.characters.map { if (it.ref() == target) it.copy(avatar_image_id = img.id) else it })
                    )
                } catch (e: Exception) {
                    snackbar.showSnackbar((e as? ApiException)?.message ?: "Не удалось загрузить картинку")
                } finally {
                    uploadingFor = null
                }
            }
        }
    }
    fun pick(target: String) {
        pickTarget = target
        picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
    }

    fun save() {
        val s = story ?: return
        val problem = when {
            s.title.isBlank() -> "Дай истории название"
            s.characters.any { it.name.isBlank() } -> "У каждого персонажа должно быть имя"
            s.characters.none { it.role == "npc" } -> "Нужен хотя бы один персонаж, которого ведёт ИИ"
            else -> null
        }
        if (problem != null) { scope.launch { snackbar.showSnackbar(problem) }; return }
        val req = StoryReq(
            title = s.title.trim(), description = s.description, intro = s.intro, world_rules = s.world_rules,
            start_scene = s.start_scene, cover_image_id = s.cover_image_id,
            characters = s.characters.map { it.copy(key = it.key ?: it.id) },
            start_messages = s.start_messages.filter { it.text.isNotBlank() },
            visibility = s.visibility,
        )
        saving = true
        scope.launch {
            try {
                val id = serverId
                if (id == null) graph.api.createStory(req) else graph.api.updateStory(id, req)
                graph.drafts.deleteStory(effectiveDraftId)
                nav.popBackStack()
            } catch (e: Exception) {
                snackbar.showSnackbar((e as? ApiException)?.message ?: "Нет связи. Черновик сохранён на телефоне.")
            } finally {
                saving = false
            }
        }
    }

    BackHandler(enabled = editing != null) { editing = null }

    val s = story
    val editIdx = editing
    Scaffold(
        topBar = {
            TopAppBar(
                navigationIcon = {
                    IconButton(onClick = { if (editIdx != null) editing = null else nav.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад")
                    }
                },
                title = {
                    Text(
                        if (editIdx != null) (s?.characters?.getOrNull(editIdx)?.name?.ifBlank { "Персонаж" } ?: "Персонаж")
                        else if (serverId == null) "Новая история" else "Редактор истории"
                    )
                },
                actions = {
                    if (editIdx == null && s != null) {
                        if (saving) CircularProgressIndicator(Modifier.size(22.dp).padding(end = 6.dp), strokeWidth = 2.dp)
                        else Button(onClick = { save() }, enabled = uploadingFor == null, modifier = Modifier.padding(end = 8.dp)
                            .testTag("editor_save")) { Text("Сохранить") }
                    } else if (editIdx != null) {
                        TextButton(onClick = { editing = null }) { Text("Готово") }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Fonar.Night),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Fonar.Night,
    ) { pad ->
        val base = Modifier.fillMaxSize().padding(pad).consumeWindowInsets(pad).imePadding()
        when {
            s == null && loadError != null -> ErrorBox(loadError!!, { scope.launch { load() } }, base)
            s == null -> CenterLoading(base)
            editIdx != null && editIdx in s.characters.indices -> {
                val c = s.characters[editIdx]
                Column(base.verticalScroll(rememberScrollState()).padding(16.dp)) {
                    CharacterFields(
                        c = c,
                        onChange = { nc -> update(s.copy(characters = s.characters.mapIndexed { i, x -> if (i == editIdx) nc else x })) },
                        relTargets = s.characters.filter { it.ref() != c.ref() }.map { RelTarget(it.ref(), it.name.ifBlank { "без имени" }) },
                        avatarUrl = c.avatar_image_id?.let { graph.api.ownImageUrl(it) },
                        uploading = uploadingFor == c.ref(),
                        onPickAvatar = { pick(c.ref()) },
                        showRole = true,
                        canBeHero = s.characters.count { it.role == "hero" } < 2,
                    )
                    TextButton(
                        onClick = {
                            val ref = c.ref()
                            editing = null
                            update(s.copy(
                                characters = s.characters.filterIndexed { i, _ -> i != editIdx }
                                    .map { it.copy(relationships = it.relationships - ref) },
                                start_messages = s.start_messages.filter { it.speaker != ref },
                            ))
                        },
                        enabled = s.characters.size > 1,
                    ) { Text("Удалить персонажа", color = Fonar.Error) }
                }
            }
            else -> Column(base.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (restored) Banner("Восстановлен несохранённый черновик", Fonar.Sea)
                ImagePickBox(s.cover_image_id?.let { graph.api.ownImageUrl(it) }, "Обложка", uploadingFor == "cover",
                    round = false, size = 140.dp, onPick = { pick("cover") })
                Field("Название", s.title, { update(s.copy(title = it)) }, maxLength = 80, testTag = "story_title")
                Field("Описание", s.description, { update(s.copy(description = it)) }, minLines = 2,
                    hint = "О чём история — видно в списке")
                Field("Вступление", s.intro, { update(s.copy(intro = it)) }, minLines = 3, maxLength = 2000,
                    hint = "Показывается игрокам в начале сцены")
                Field("Правила мира", s.world_rules, { update(s.copy(world_rules = it)) }, minLines = 3, maxLength = 3000,
                    hint = "Эпоха, магия, тон, запреты…")
                Field("Стартовая сцена", s.start_scene, { update(s.copy(start_scene = it)) }, minLines = 2, maxLength = 1000,
                    hint = "Где начинается действие и что вокруг")
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 4.dp).testTag("story_public_row"),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text("Публичная история", fontWeight = FontWeight.SemiBold)
                        Text(if (s.visibility == "public") "Её видят все; другие играют свою копию и не меняют твою."
                            else "Видишь только ты.", color = Fonar.Faint, style = MaterialTheme.typography.bodySmall)
                    }
                    androidx.compose.material3.Switch(
                        checked = s.visibility == "public",
                        onCheckedChange = { on -> update(s.copy(visibility = if (on) "public" else "private")) },
                        modifier = Modifier.testTag("story_public"),
                    )
                }

                SectionTitle("Персонажи · ${s.characters.size}/$MAX_CHARACTERS")
                s.characters.forEachIndexed { i, c ->
                    Card(
                        colors = CardDefaults.cardColors(containerColor = Fonar.Surface),
                        modifier = Modifier.fillMaxWidth().clickable { editing = i }.testTag("editor_char_$i"),
                    ) {
                        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Avatar(c.name.ifBlank { "?" }, c.avatar_image_id?.let { graph.api.ownImageUrl(it) }, 42.dp)
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(c.name.ifBlank { "Без имени" }, fontWeight = FontWeight.SemiBold)
                                Text(c.personality.ifBlank { "нажми, чтобы заполнить карточку" }, color = Fonar.Muted,
                                    style = MaterialTheme.typography.bodySmall, maxLines = 1)
                            }
                            Pill(if (c.role == "hero") "герой игрока" else "ведёт ИИ", if (c.role == "hero") Fonar.Sea else Fonar.Lamp)
                        }
                    }
                }
                if (s.characters.size < MAX_CHARACTERS) {
                    OutlinedButton(onClick = {
                        update(s.copy(characters = s.characters + CharacterDto(key = "k-" + UUID.randomUUID(), role = "npc")))
                        editing = s.characters.size
                    }, modifier = Modifier.testTag("editor_add_char")) {
                        Icon(Icons.Outlined.Add, null); Spacer(Modifier.width(6.dp)); Text("Добавить персонажа")
                    }
                }

                SectionTitle("Стартовые сообщения")
                Text("Первые реплики сцены: от рассказчика или любого персонажа.", color = Fonar.Faint,
                    style = MaterialTheme.typography.bodySmall)
                s.start_messages.forEachIndexed { i, m ->
                    StartMessageRow(
                        m = m,
                        speakers = listOf("narrator" to "Рассказчик") + s.characters.map { it.ref() to it.name.ifBlank { "без имени" } },
                        onChange = { nm -> update(s.copy(start_messages = s.start_messages.mapIndexed { j, x -> if (j == i) nm else x })) },
                        onRemove = { update(s.copy(start_messages = s.start_messages.filterIndexed { j, _ -> j != i })) },
                        onUp = if (i > 0) ({
                            val l = s.start_messages.toMutableList(); val t = l[i]; l[i] = l[i - 1]; l[i - 1] = t
                            update(s.copy(start_messages = l))
                        }) else null,
                    )
                }
                if (s.start_messages.size < 12) {
                    OutlinedButton(onClick = { update(s.copy(start_messages = s.start_messages + StartMessageDto("narrator", ""))) }) {
                        Icon(Icons.Outlined.Add, null); Spacer(Modifier.width(6.dp)); Text("Добавить сообщение")
                    }
                }
                Text("Черновик сохраняется на телефоне автоматически.", color = Fonar.Faint, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

@Composable
private fun StartMessageRow(
    m: StartMessageDto,
    speakers: List<Pair<String, String>>,
    onChange: (StartMessageDto) -> Unit,
    onRemove: () -> Unit,
    onUp: (() -> Unit)?,
) {
    var open by remember { mutableStateOf(false) }
    Card(colors = CardDefaults.cardColors(containerColor = Fonar.Surface)) {
        Column(Modifier.padding(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) {
                    TextButton(onClick = { open = true }) {
                        Text(speakers.firstOrNull { it.first == m.speaker }?.second ?: "Рассказчик")
                        Icon(Icons.Outlined.ArrowDropDown, null)
                    }
                    DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                        speakers.forEach { (k, n) ->
                            DropdownMenuItem(text = { Text(n) }, onClick = { open = false; onChange(m.copy(speaker = k)) })
                        }
                    }
                }
                if (onUp != null) IconButton(onClick = onUp) { Icon(Icons.Outlined.ArrowUpward, "Выше", tint = Fonar.Muted) }
                IconButton(onClick = onRemove) { Icon(Icons.Outlined.Close, "Удалить", tint = Fonar.Muted) }
            }
            Field("Текст", m.text, { onChange(m.copy(text = it)) }, minLines = 2,
                hint = if (m.speaker == "narrator") "Полночь. Маяк темен…" else "*поднимает взгляд* Ты пришёл?")
        }
    }
}
