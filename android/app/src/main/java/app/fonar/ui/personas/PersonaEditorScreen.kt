package app.fonar.ui.personas

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.AddAPhoto
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.navigation.NavHostController
import app.fonar.Routes
import app.fonar.data.AvatarStyle
import app.fonar.data.PersonaReq
import app.fonar.graph
import app.fonar.ui.components.CenterLoading
import app.fonar.ui.components.Field
import app.fonar.ui.components.exposeTags
import app.fonar.ui.theme.Fonar
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch

/** The five avatar styles; prompts live on the server, the app only shows the names. */
private val DEFAULT_STYLES = listOf(
    AvatarStyle("anime", "Аниме"), AvatarStyle("realism", "Реализм"), AvatarStyle("painted", "Нарисованный"),
    AvatarStyle("manhwa", "Манхва"), AvatarStyle("sketch", "Ч/б рисунок"),
)

private fun styleBrush(id: String): Brush = Brush.linearGradient(
    when (id) {
        "anime" -> listOf(Color(0xFFFFC6E5), Color(0xFFB9A6FF), Color(0xFF8FD3FF))
        "realism" -> listOf(Color(0xFFE2B48E), Color(0xFF7A4B33), Color(0xFF2A1A14))
        "painted" -> listOf(Color(0xFF1F4E5F), Color(0xFFC79A3A), Color(0xFF2B1B3D))
        "manhwa" -> listOf(Color(0xFFF2F2F2), Color(0xFF6B6B6B), Color(0xFF0D0D0D))
        else -> listOf(Color(0xFFE9D8B4), Color(0xFFA6875A), Color(0xFF4A3A26))
    },
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PersonaEditorScreen(nav: NavHostController, id: String?) {
    val graph = LocalContext.current.graph
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    var loaded by rememberSaveable { mutableStateOf(id == null) }
    var name by rememberSaveable { mutableStateOf("") }
    var firstMessage by rememberSaveable { mutableStateOf("") }
    var description by rememberSaveable { mutableStateOf("") }
    var backstory by rememberSaveable { mutableStateOf("") }
    var personality by rememberSaveable { mutableStateOf("") }
    var tags by rememberSaveable { mutableStateOf("") }
    var visibility by rememberSaveable { mutableStateOf("private") }
    var avatarId by rememberSaveable { mutableStateOf<String?>(null) }
    var more by rememberSaveable { mutableStateOf(false) }
    var idea by rememberSaveable { mutableStateOf("") }
    var filling by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var uploading by remember { mutableStateOf(false) }
    var avatarDialog by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(id) {
        if (id != null && !loaded) {
            try {
                val p = graph.api.persona(id).persona
                name = p.name; firstMessage = p.first_message; description = p.description
                backstory = p.backstory.orEmpty(); personality = p.personality.orEmpty()
                tags = p.tags.joinToString(", "); visibility = p.visibility; avatarId = p.avatar_image_id
                more = backstory.isNotBlank() || personality.isNotBlank() || tags.isNotBlank()
                loaded = true
            } catch (e: Exception) {
                message = errText(e)
            }
        }
    }
    LaunchedEffect(message) { message?.let { snackbar.showSnackbar(it); message = null } }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch {
            uploading = true
            try {
                avatarId = graph.api.uploadImage(context, uri, 1024).id
                avatarDialog = false
            } catch (e: Exception) {
                message = errText(e)
            } finally {
                uploading = false
            }
        }
    }

    fun save(publish: Boolean) {
        if (publish && (name.isBlank() || firstMessage.isBlank())) {
            message = "Чтобы опубликовать, заполни имя и первое сообщение."
            return
        }
        saving = true
        scope.launch {
            try {
                val req = PersonaReq(
                    name = name.trim(), first_message = firstMessage.trim(), description = description.trim(),
                    backstory = backstory.trim(), personality = personality.trim(),
                    tags = tags.split(',', ';').map { it.trim() }.filter { it.isNotEmpty() },
                    visibility = visibility, status = if (publish) "published" else "draft", avatar_image_id = avatarId,
                )
                val saved = if (id == null) graph.api.createPersona(req).persona else graph.api.updatePersona(id, req).persona
                nav.popBackStack()
                if (id == null) nav.navigate(Routes.persona(saved.id))
            } catch (e: Exception) {
                message = errText(e)
            } finally {
                saving = false
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (id == null) "Новый персонаж" else "Редактирование") },
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
        if (!loaded) {
            CenterLoading(Modifier.padding(pad))
            return@Scaffold
        }
        Column(
            Modifier.padding(pad).fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // AI fill from a short idea
            Card(colors = CardDefaults.cardColors(containerColor = Fonar.Surface)) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Придумать с ИИ", fontWeight = FontWeight.SemiBold, color = Fonar.Lamp)
                    Field("Идея персонажа", idea, { idea = it }, hint = "Например: травница-оборотень на перекрёстке дорог",
                        maxLength = 1000, minLines = 2, testTag = "fill_idea")
                    OutlinedButton(
                        onClick = {
                            filling = true
                            scope.launch {
                                try {
                                    val f = graph.api.fillPersona(idea.trim()).persona
                                    if (f.name.isNotBlank()) name = f.name
                                    description = f.description; personality = f.personality; backstory = f.backstory
                                    firstMessage = f.first_message; tags = f.tags.joinToString(", ")
                                    more = true
                                } catch (e: Exception) {
                                    message = errText(e)
                                } finally {
                                    filling = false
                                }
                            }
                        },
                        enabled = idea.isNotBlank() && !filling,
                        modifier = Modifier.fillMaxWidth().testTag("fill_button"),
                    ) {
                        if (filling) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                        else { Icon(Icons.Outlined.AutoAwesome, null, Modifier.size(18.dp)); Text("  Заполнить поля") }
                    }
                }
            }

            // avatar 2:3
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.width(120.dp).aspectRatio(2f / 3f).clip(RoundedCornerShape(16.dp))
                        .background(personaBrush(name.ifBlank { "?" }))
                        .border(1.dp, Fonar.SurfaceHigher, RoundedCornerShape(16.dp))
                        .clickable { avatarDialog = true }.testTag("avatar_tile"),
                    contentAlignment = Alignment.Center,
                ) {
                    val a = avatarId
                    if (a != null) AsyncImage(model = graph.api.ownImageUrl(a), contentDescription = "Аватар",
                        contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
                    else Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Outlined.AddAPhoto, null, tint = Color.White.copy(alpha = 0.8f))
                        Text("AI-аватар", color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.labelMedium)
                    }
                    if (uploading) CircularProgressIndicator(Modifier.size(28.dp))
                }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text("Портрет 2:3", fontWeight = FontWeight.SemiBold)
                    Text("Загрузи картинку или создай её с ИИ в одном из пяти стилей.", color = Fonar.Muted,
                        style = MaterialTheme.typography.bodySmall)
                    if (avatarId != null) TextButton(onClick = { avatarId = null }, modifier = Modifier.testTag("avatar_clear")) {
                        Text("Убрать", color = Fonar.Muted)
                    }
                }
            }

            Field("Имя персонажа *", name, { name = it }, maxLength = 60, testTag = "persona_name", counter = true)
            Field("Первое сообщение *", firstMessage, { firstMessage = it }, minLines = 4, maxLines = 12, maxLength = 5000,
                hint = "С него ИИ начинает каждый чат. *Действия* — в звёздочках, реплика — с тире.",
                testTag = "persona_first_message", counter = true)
            Field("Описание персонажа", description, { description = it }, minLines = 3, maxLines = 10, maxLength = 10000,
                hint = "Кратко для карточки: кто это, внешность, чем интересен", testTag = "persona_description", counter = true)

            Text("Видимость", fontWeight = FontWeight.SemiBold)
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                listOf("public" to "Публичный", "private" to "Личный").forEachIndexed { i, (v, label) ->
                    SegmentedButton(
                        selected = visibility == v, onClick = { visibility = v },
                        shape = SegmentedButtonDefaults.itemShape(i, 2),
                        modifier = Modifier.testTag("visibility_$v"),
                    ) { Text(label) }
                }
            }
            Text(if (visibility == "public") "Опубликованного персонажа увидят все игроки GramSoul." else "Видишь только ты.",
                color = Fonar.Faint, style = MaterialTheme.typography.bodySmall)

            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { more = !more }.padding(vertical = 6.dp)
                .testTag("persona_more"), verticalAlignment = Alignment.CenterVertically) {
                Text("Дополнительные настройки", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                Icon(if (more) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, null, tint = Fonar.Muted)
            }
            if (more) {
                Field("Предыстория", backstory, { backstory = it }, minLines = 3, maxLines = 10, maxLength = 2000,
                    hint = "История, черты, контекст", testTag = "persona_backstory", counter = true)
                Field("Характер", personality, { personality = it }, minLines = 3, maxLines = 10, maxLength = 2000,
                    hint = "Поведение, привычки, манера речи", testTag = "persona_personality", counter = true)
                Field("Теги через запятую", tags, { tags = it }, maxLength = 200, hint = "мистика, море, детектив",
                    testTag = "persona_tags")
                Text("Предыстория и характер видны только тебе — их получает ИИ.", color = Fonar.Faint,
                    style = MaterialTheme.typography.bodySmall)
            }

            Text("Все персонажи по умолчанию 18+.", color = Fonar.Muted, style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("adult_note"))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = { save(false) }, enabled = !saving, modifier = Modifier.weight(1f).testTag("save_draft")) {
                    Text("Черновик")
                }
                Button(onClick = { save(true) }, enabled = !saving, modifier = Modifier.weight(1f).testTag("publish")) {
                    if (saving) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = Fonar.OnLamp)
                    else Text("Опубликовать")
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }

    if (avatarDialog) AvatarDialog(
        name = name,
        initialDescription = description.take(400),
        uploading = uploading,
        onUpload = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
        onUse = { avatarId = it; avatarDialog = false },
        onDismiss = { avatarDialog = false },
    )
}

@Composable
private fun AvatarDialog(
    name: String,
    initialDescription: String,
    uploading: Boolean,
    onUpload: () -> Unit,
    onUse: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    var tab by rememberSaveable { mutableStateOf(1) }
    var desc by rememberSaveable { mutableStateOf(initialDescription) }
    var style by rememberSaveable { mutableStateOf("anime") }
    var styles by remember { mutableStateOf(DEFAULT_STYLES) }
    var busy by remember { mutableStateOf(false) }
    var result by rememberSaveable { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { runCatching { graph.api.avatarStyles().styles }.onSuccess { if (it.isNotEmpty()) styles = it } }

    fun generate() {
        busy = true
        error = null
        scope.launch {
            try {
                result = graph.api.generateAvatar(name.trim(), desc.trim(), style).image_id
            } catch (e: Exception) {
                error = errText(e)
            } finally {
                busy = false
            }
        }
    }

    Dialog(onDismissRequest = { if (!busy) onDismiss() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Card(
            colors = CardDefaults.cardColors(containerColor = Fonar.Surface),
            modifier = Modifier.fillMaxWidth().padding(16.dp).exposeTags().testTag("avatar_dialog"),
        ) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("AI-аватар", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                TabRow(selectedTabIndex = tab, containerColor = Fonar.Surface) {
                    Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Загрузить") }, modifier = Modifier.testTag("avatar_tab_upload"))
                    Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Создать с ИИ") }, modifier = Modifier.testTag("avatar_tab_ai"))
                }
                if (tab == 0) {
                    Text("Выбери картинку из галереи. Лучше всего — вертикальный портрет 2:3.", color = Fonar.Muted)
                    Button(onClick = onUpload, enabled = !uploading, modifier = Modifier.fillMaxWidth().testTag("avatar_upload")) {
                        if (uploading) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = Fonar.OnLamp)
                        else Text("Выбрать из галереи")
                    }
                } else {
                    val r = result
                    if (r != null) {
                        AsyncImage(model = graph.api.ownImageUrl(r), contentDescription = "Результат", contentScale = ContentScale.Crop,
                            modifier = Modifier.width(200.dp).aspectRatio(2f / 3f).clip(RoundedCornerShape(16.dp))
                                .align(Alignment.CenterHorizontally).testTag("avatar_result"))
                        Button(onClick = { onUse(r) }, modifier = Modifier.fillMaxWidth().testTag("avatar_use")) { Text("Использовать") }
                        OutlinedButton(onClick = { result = null; generate() }, enabled = !busy,
                            modifier = Modifier.fillMaxWidth().testTag("avatar_again")) { Text("Сгенерировать заново") }
                    } else {
                        Field("Опишите внешность", desc, { desc = it }, minLines = 3, maxLines = 6, maxLength = 1500,
                            hint = "Волосы, глаза, одежда, настроение…", testTag = "avatar_desc")
                        Text("Стиль", fontWeight = FontWeight.SemiBold)
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            styles.forEach { st ->
                                val selected = st.id == style
                                Column(
                                    Modifier.width(84.dp).clip(RoundedCornerShape(14.dp)).clickable { style = st.id }
                                        .testTag("style_${st.id}"),
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                ) {
                                    Box(
                                        Modifier.fillMaxWidth().aspectRatio(2f / 3f).clip(RoundedCornerShape(14.dp)).background(styleBrush(st.id))
                                            .border(if (selected) 3.dp else 1.dp, if (selected) Fonar.Lamp else Fonar.SurfaceHigher,
                                                RoundedCornerShape(14.dp)),
                                    )
                                    Text(st.label, style = MaterialTheme.typography.labelMedium,
                                        color = if (selected) Fonar.Lamp else Fonar.Muted, modifier = Modifier.padding(top = 4.dp))
                                }
                            }
                        }
                        Button(onClick = { generate() }, enabled = !busy && desc.trim().length >= 5,
                            modifier = Modifier.fillMaxWidth().testTag("avatar_generate")) {
                            if (busy) {
                                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = Fonar.OnLamp)
                                Text("  Рисую… 10–30 с")
                            } else Text("Сгенерировать")
                        }
                    }
                    error?.let { Text(it, color = Fonar.Error, modifier = Modifier.testTag("avatar_error")) }
                }
                TextButton(onClick = onDismiss, enabled = !busy, modifier = Modifier.align(Alignment.End)) { Text("Закрыть") }
            }
        }
    }
}
