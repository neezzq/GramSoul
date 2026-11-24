package app.fonar.ui.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.outlined.AutoFixHigh
import androidx.compose.material.icons.outlined.Cloud
import androidx.compose.material.icons.outlined.Memory
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material.icons.outlined.FastForward
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.WifiOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import app.fonar.Routes
import app.fonar.data.CharacterDto
import app.fonar.data.MessageDto
import app.fonar.data.RoomDto
import app.fonar.graph
import app.fonar.ui.components.Avatar
import app.fonar.ui.components.CenterLoading
import app.fonar.ui.components.ErrorBox
import app.fonar.ui.components.actionText
import app.fonar.ui.components.exposeTags
import app.fonar.ui.home.FriendPickerDialog
import app.fonar.ui.theme.Fonar
import app.fonar.ui.theme.NarratorStyle

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(nav: NavHostController, roomId: String) {
    val graph = LocalContext.current.graph
    val vm: ChatViewModel = viewModel(key = "chat-$roomId") { ChatViewModel(graph, roomId) }
    val s by vm.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var menu by remember { mutableStateOf(false) }
    var showInvite by remember { mutableStateOf(false) }
    var showScene by remember { mutableStateOf(false) }
    var showAiMode by remember { mutableStateOf(false) }
    var showPhoto by remember { mutableStateOf(false) }
    var fullImage by remember { mutableStateOf<String?>(null) }
    val focusManager = androidx.compose.ui.platform.LocalFocusManager.current
    var confirmLeave by remember { mutableStateOf(false) }
    var input by rememberSaveable(stateSaver = TextFieldValue.Saver) { mutableStateOf(TextFieldValue("")) }
    val listState = rememberLazyListState()
    val room = s.room
    val me = vm.myUserId

    LaunchedEffect(s.toast) { s.toast?.let { snackbar.showSnackbar(it); vm.consumeToast() } }

    val itemCount = s.messages.size + s.pending.size + 1
    val partialLen = s.generation?.partial?.length ?: 0
    val atBottom by remember { derivedStateOf {
        val info = listState.layoutInfo
        val last = info.visibleItemsInfo.lastOrNull()?.index ?: 0
        last >= info.totalItemsCount - 3
    } }
    var initialScrollDone by remember { mutableStateOf(false) }
    val lastKey = (s.messages.lastOrNull()?.id ?: "") + ":" + s.pending.size
    LaunchedEffect(room != null, lastKey, s.generation?.status) {
        if (room == null) return@LaunchedEffect
        withFrameNanos { }  // let the list lay out the new items first
        val count = listState.layoutInfo.totalItemsCount
        if (count > 0) {
            if (initialScrollDone) listState.animateScrollToItem(count - 1) else listState.scrollToItem(count - 1)
            initialScrollDone = true
        }
    }
    LaunchedEffect(partialLen) {
        if (atBottom && itemCount > 0) listState.scrollToItem(listState.layoutInfo.totalItemsCount.coerceAtLeast(1) - 1)
    }

    fun openCard(charId: String?) {
        if (charId != null) nav.navigate(Routes.card(roomId, charId))
    }

    Scaffold(
        topBar = {
            TopAppBar(
                navigationIcon = { IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад") } },
                title = {
                    Column {
                        Text(room?.story?.title ?: "Сцена", maxLines = 1, overflow = TextOverflow.Ellipsis,
                            style = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Serif))
                        if (room != null) Text(seatLine(room), maxLines = 1, overflow = TextOverflow.Ellipsis,
                            style = MaterialTheme.typography.labelSmall, color = Fonar.Sea, modifier = Modifier.testTag("seat_line"))
                    }
                },
                actions = {
                    if (room != null) {
                        val cloud = room.ai_mode == "cloud"
                        IconButton(onClick = { focusManager.clearFocus(); showAiMode = true }, modifier = Modifier.testTag("ai_mode")) {
                            Icon(if (cloud) Icons.Outlined.Cloud else Icons.Outlined.Memory,
                                if (cloud) "Облачный ИИ" else "Локальный ИИ", tint = if (cloud) Fonar.Lamp else Fonar.Sea)
                        }
                    }
                    if (room != null && room.my_role == "owner" && room.seats.getOrNull(1)?.user == null) {
                        IconButton(onClick = { vm.loadFriends(); showInvite = true }, modifier = Modifier.testTag("chat_invite")) {
                            Icon(Icons.Outlined.PersonAdd, "Играть с другом", tint = Fonar.Lamp)
                        }
                    }
                    Box {
                        IconButton(onClick = { menu = true }, modifier = Modifier.testTag("chat_menu")) { Icon(Icons.Outlined.MoreVert, "Ещё") }
                        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                            if (room?.my_role == "owner") {
                                DropdownMenuItem(text = { Text("Место сцены") }, onClick = { menu = false; showScene = true })
                            }
                            DropdownMenuItem(text = { Text("Что видит ИИ") }, onClick = { menu = false; vm.loadLastPrompt() },
                                modifier = Modifier.exposeTags().testTag("menu_prompt"))
                            DropdownMenuItem(
                                text = { Text(if (room?.my_role == "owner") "Удалить сцену" else "Выйти из сцены", color = Fonar.Error) },
                                onClick = { menu = false; confirmLeave = true },
                            )
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Fonar.Surface),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Fonar.Night,
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).consumeWindowInsets(pad).imePadding()) {
            if (!s.online) {
                Row(
                    Modifier.fillMaxWidth().background(Fonar.Error.copy(alpha = 0.15f)).padding(horizontal = 16.dp, vertical = 6.dp)
                        .testTag("offline_banner"),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.WifiOff, null, tint = Fonar.Error, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Нет связи — переподключаюсь…", color = Fonar.Error, style = MaterialTheme.typography.labelMedium)
                }
            }
            when {
                room == null && s.loadError != null -> ErrorBox(s.loadError!!, if (s.closed) null else ({ vm.startSync() }),
                    Modifier.weight(1f))
                room == null -> CenterLoading(Modifier.weight(1f))
                else -> LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f).fillMaxWidth().testTag("chat_list"),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(s.messages, key = { it.id }) { m ->
                        if (m.image_id != null) {
                            PhotoMessage(m, graph.api.roomImageUrl(roomId, m.image_id)) { fullImage = it }
                        } else {
                            MessageItem(m, room, me, roomId, graph.api::roomImageUrl, ::openCard)
                        }
                    }
                    items(s.pending, key = { "p" + it.clientId }) { p -> PendingItem(p, vm) }
                    item(key = "photo_status") { PhotoStatus(s) { showPhoto = true } }
                    item(key = "status") { GenerationStatus(s, vm) }
                }
            }
            if (room != null && !s.closed) {
                Composer(
                    s = s,
                    input = input,
                    onInput = { input = it },
                    onSend = {
                        vm.send(input.text)
                        input = TextFieldValue("")
                    },
                    vm = vm,
                    imagesAvailable = room.images_available,
                    photoOpen = showPhoto,
                    onPhoto = { showPhoto = !showPhoto },
                    onPhotoSubmit = { what -> showPhoto = false; focusManager.clearFocus(); vm.requestPhoto(what) },
                )
            }
        }
    }

    if (showInvite) {
        FriendPickerDialog(
            friends = s.friends?.friends ?: emptyList(),
            title = "Играть с другом",
            onDismiss = { showInvite = false },
            onPick = { f -> showInvite = false; vm.invite(f.id) },
        )
    }
    if (showAiMode && room != null) {
        AiModeDialog(room, onDismiss = { showAiMode = false }, onPick = { mode -> showAiMode = false; vm.setAiMode(mode) })
    }
    fullImage?.let { url ->
        androidx.compose.ui.window.Dialog(
            onDismissRequest = { fullImage = null },
            properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false),
        ) {
            Box(Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Color.Black).clickable { fullImage = null },
                contentAlignment = Alignment.Center) {
                coil3.compose.AsyncImage(model = url, contentDescription = "Фото сцены",
                    contentScale = androidx.compose.ui.layout.ContentScale.Fit, modifier = Modifier.fillMaxSize())
            }
        }
    }
    if (showScene && room != null) {
        var loc by remember { mutableStateOf(room.scene_location) }
        AlertDialog(
            onDismissRequest = { showScene = false },
            title = { Text("Где сейчас герои?") },
            text = {
                OutlinedTextField(value = loc, onValueChange = { if (it.length <= 600) loc = it }, minLines = 3,
                    label = { Text("Место и обстановка") })
            },
            confirmButton = { TextButton(onClick = { showScene = false; vm.setScene(loc) }) { Text("Сохранить") } },
            dismissButton = { TextButton(onClick = { showScene = false }) { Text("Отмена") } },
            containerColor = Fonar.Surface,
        )
    }
    s.lastPrompt?.let { p ->
        AlertDialog(
            onDismissRequest = { vm.clearLastPrompt() },
            title = { Text("Последний запрос к модели") },
            text = {
                Column(Modifier.exposeTags().heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                    Text("${p.model ?: ""} · ${p.status}" + (p.stats?.total_ms?.let { " · ${it / 1000} с" } ?: ""),
                        color = Fonar.Muted, style = MaterialTheme.typography.labelSmall)
                    Spacer(Modifier.height(8.dp))
                    SelectionContainer {
                        Text(p.prompt, style = MaterialTheme.typography.bodySmall.copy(fontSize = 12.sp), modifier = Modifier.testTag("prompt_text"))
                    }
                }
            },
            confirmButton = { TextButton(onClick = { vm.clearLastPrompt() }) { Text("Закрыть") } },
            containerColor = Fonar.Surface,
        )
    }
    if (confirmLeave && room != null) {
        AlertDialog(
            onDismissRequest = { confirmLeave = false },
            title = { Text(if (room.my_role == "owner") "Удалить сцену?" else "Выйти из сцены?") },
            text = { Text(if (room.my_role == "owner") "Переписка удалится у обоих игроков." else "Ты больше не увидишь эту сцену.") },
            confirmButton = {
                TextButton(onClick = { confirmLeave = false; vm.leave { nav.popBackStack() } }) { Text("Да", color = Fonar.Error) }
            },
            dismissButton = { TextButton(onClick = { confirmLeave = false }) { Text("Отмена") } },
            containerColor = Fonar.Surface,
        )
    }
}

private fun seatLine(room: RoomDto): String {
    val a = room.seats.getOrNull(0)
    val b = room.seats.getOrNull(1)
    val first = a?.let { "${it.hero_name} — ${it.user?.nick ?: "?"}" } ?: ""
    val second = when {
        b?.user != null -> "${b.hero_name} — ${b.user.nick}"
        room.invite?.status == "pending" -> "ждём ${room.invite.to?.nick ?: "друга"}"
        else -> "второе место свободно"
    }
    return "$first · $second"
}

private fun characterById(room: RoomDto, id: String?): CharacterDto? =
    id?.let { cid -> room.story.characters.firstOrNull { it.id == cid } }

@Composable
private fun MessageItem(
    m: MessageDto,
    room: RoomDto,
    me: String?,
    roomId: String,
    imageUrl: (String, String) -> String,
    openCard: (String?) -> Unit,
) {
    when (m.kind) {
        "system" -> Text(
            m.text, color = Fonar.Muted, style = MaterialTheme.typography.bodySmall.copy(fontStyle = FontStyle.Italic),
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 4.dp),
        )
        "narrator" -> NarratorBlock(m.text)
        "character" -> {
            val c = characterById(room, m.character_id)
            val url = c?.avatar_image_id?.let { imageUrl(roomId, it) }
            Row(Modifier.fillMaxWidth().testTag("msg_character"), verticalAlignment = Alignment.Top) {
                Avatar(m.speaker_name, url, 40.dp, onClick = { openCard(c?.id) }, modifier = Modifier.testTag("avatar_${m.speaker_name}"))
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f, fill = false).widthIn(max = 520.dp)) {
                    Text(m.speaker_name, color = Fonar.Lamp, fontWeight = FontWeight.SemiBold,
                        style = MaterialTheme.typography.labelLarge,
                        modifier = Modifier.clickable { openCard(c?.id) }.padding(bottom = 3.dp).testTag("name_${m.speaker_name}"))
                    Bubble(m.text, Fonar.CharBubble, RoundedCornerShape(4.dp, 18.dp, 18.dp, 18.dp))
                }
            }
        }
        "player" -> {
            val mine = m.user_id == me
            val seat = room.seats.firstOrNull { it.user?.id == m.user_id }
            val hero = characterById(room, seat?.hero_character_id)
            val url = hero?.avatar_image_id?.let { imageUrl(roomId, it) }
            Row(
                Modifier.fillMaxWidth().testTag(if (mine) "msg_mine" else "msg_friend"),
                horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start,
                verticalAlignment = Alignment.Top,
            ) {
                if (!mine) {
                    Avatar(m.speaker_name, url, 40.dp, onClick = { openCard(hero?.id) })
                    Spacer(Modifier.width(8.dp))
                }
                Column(horizontalAlignment = if (mine) Alignment.End else Alignment.Start, modifier = Modifier.weight(1f, fill = false)) {
                    Text(
                        m.speaker_name + (seat?.user?.nick?.let { if (it != m.speaker_name) " · $it" else "" } ?: ""),
                        color = if (mine) Fonar.LampSoft.copy(alpha = 0.8f) else Fonar.Sea,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.clickable { openCard(hero?.id) }.padding(bottom = 3.dp),
                    )
                    Bubble(
                        m.text, if (mine) Fonar.MyBubble else Fonar.FriendBubble,
                        if (mine) RoundedCornerShape(18.dp, 4.dp, 18.dp, 18.dp) else RoundedCornerShape(4.dp, 18.dp, 18.dp, 18.dp),
                    )
                }
                if (mine) {
                    Spacer(Modifier.width(8.dp))
                    Avatar(m.speaker_name, url, 32.dp, onClick = { openCard(hero?.id) })
                }
            }
        }
    }
}

@Composable
private fun Bubble(text: String, color: androidx.compose.ui.graphics.Color, shape: RoundedCornerShape) {
    Surface(color = color, shape = shape) {
        Text(actionText(text), style = MaterialTheme.typography.bodyLarge, color = Fonar.Text,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp))
    }
}

@Composable
private fun NarratorBlock(text: String) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 2.dp).clip(RoundedCornerShape(12.dp)).background(Fonar.NarratorBg)
            .testTag("msg_narrator"),
    ) {
        Box(Modifier.width(3.dp).heightIn(min = 40.dp).background(Fonar.Lamp.copy(alpha = 0.55f)))
        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
            Text("РАССКАЗЧИК", style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 1.4.sp), color = Fonar.Lamp.copy(alpha = 0.7f))
            Spacer(Modifier.height(4.dp))
            Text(actionText(text, Fonar.LampSoft.copy(alpha = 0.85f)), style = NarratorStyle)
        }
    }
}

@Composable
private fun PendingItem(p: Pending, vm: ChatViewModel) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.End) {
        Surface(color = Fonar.MyBubble.copy(alpha = 0.6f), shape = RoundedCornerShape(18.dp, 4.dp, 18.dp, 18.dp)) {
            Text(actionText(p.text), style = MaterialTheme.typography.bodyLarge, color = Fonar.Text.copy(alpha = 0.75f),
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp))
        }
        if (p.failed) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(p.error ?: "Не отправлено", color = Fonar.Error, style = MaterialTheme.typography.labelSmall)
                TextButton(onClick = { vm.resend(p.clientId) }, modifier = Modifier.testTag("resend")) { Text("Повторить") }
                TextButton(onClick = { vm.discard(p.clientId) }) { Text("Убрать", color = Fonar.Muted) }
            }
        } else {
            Text("отправляется…", color = Fonar.Muted, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun GenerationStatus(s: ChatState, vm: ChatViewModel) {
    val g = s.generation ?: return
    when (g.status) {
        "queued" -> StatusRow(
            if ((g.queue_position ?: 0) > 0) "Рассказчик ждёт очереди… (перед вами: ${g.queue_position})"
            else "Рассказчик собирается с мыслями…",
        )
        "running" -> Column(Modifier.fillMaxWidth().testTag("generation_running")) {
            StatusRow(if (g.kind == "regenerate") "Рассказчик переписывает ответ…" else "Рассказчик пишет…")
            val partial = g.partial?.trim().orEmpty()
            if (partial.isNotEmpty()) {
                Text(actionText(partial), color = Fonar.Muted, style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(start = 30.dp, top = 4.dp))
            }
        }
        "failed" -> Surface(color = Fonar.Error.copy(alpha = 0.12f), shape = RoundedCornerShape(14.dp),
            modifier = Modifier.fillMaxWidth().testTag("generation_failed")) {
            Column(Modifier.padding(14.dp)) {
                Text("Ответ не получился", color = Fonar.Error, fontWeight = FontWeight.SemiBold)
                Text((g.error ?: "Ошибка модели") + "\nТвой ход сохранён, предыдущий ответ тоже.",
                    color = Fonar.Muted, style = MaterialTheme.typography.bodySmall)
                Button(onClick = { vm.retry() }, enabled = !s.actionBusy, modifier = Modifier.padding(top = 8.dp).testTag("retry_button")) {
                    Icon(Icons.Outlined.Refresh, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Повторить генерацию")
                }
            }
        }
        else -> Spacer(Modifier.height(2.dp))
    }
}

@Composable
private fun StatusRow(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 6.dp, top = 4.dp)) {
        CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = Fonar.Lamp)
        Spacer(Modifier.width(10.dp))
        Text(text, color = Fonar.Lamp, style = MaterialTheme.typography.labelLarge, modifier = Modifier.testTag("generation_status"))
    }
}

@Composable
private fun Composer(
    s: ChatState,
    input: TextFieldValue,
    onInput: (TextFieldValue) -> Unit,
    onSend: () -> Unit,
    vm: ChatViewModel,
    imagesAvailable: Boolean,
    photoOpen: Boolean,
    onPhoto: () -> Unit,
    onPhotoSubmit: (String) -> Unit,
) {
    val g = s.generation
    val active = g != null && (g.status == "queued" || g.status == "running")
    val lastIsAi = s.messages.lastOrNull { it.image_id == null && it.kind != "system" }?.generation_id != null
    val regenerating = active && g?.kind == "regenerate"
    Surface(color = Fonar.Surface, tonalElevation = 2.dp) {
        Column(Modifier.fillMaxWidth().padding(start = 10.dp, end = 10.dp, top = 6.dp, bottom = 8.dp)) {
            if (photoOpen) PhotoPanel(onSubmit = onPhotoSubmit, onClose = onPhoto)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AssistChip(
                    onClick = { vm.continueScene() },
                    enabled = !active && !s.actionBusy,
                    label = { Text("Продолжить сцену") },
                    leadingIcon = { Icon(Icons.Outlined.FastForward, null, Modifier.size(18.dp)) },
                    colors = AssistChipDefaults.assistChipColors(leadingIconContentColor = Fonar.Lamp),
                    modifier = Modifier.testTag("continue_button"),
                )
                AssistChip(
                    onClick = { vm.regenerate() },
                    enabled = !active && lastIsAi && !s.actionBusy,
                    label = { Text("Перегенерировать") },
                    leadingIcon = { Icon(Icons.Outlined.AutoFixHigh, null, Modifier.size(18.dp)) },
                    colors = AssistChipDefaults.assistChipColors(leadingIconContentColor = Fonar.Lamp),
                    modifier = Modifier.testTag("regenerate_button"),
                )
                AssistChip(
                    onClick = {
                        val sel = input.selection
                        val t = input.text
                        val chosen = t.substring(sel.min, sel.max)
                        val newText = t.substring(0, sel.min) + "*" + chosen + "* " + t.substring(sel.max)
                        onInput(TextFieldValue(newText, TextRange(sel.min + 1 + chosen.length)))
                    },
                    label = { Text("*действие*") },
                    modifier = Modifier.testTag("action_button"),
                )
            }
            Row(verticalAlignment = Alignment.Bottom, modifier = Modifier.padding(top = 4.dp)) {
                if (imagesAvailable) {
                    val photoBusy = s.imageJob?.status == "queued" || s.imageJob?.status == "running"
                    IconButton(
                        onClick = onPhoto,
                        enabled = !photoBusy && !s.actionBusy,
                        modifier = Modifier.padding(bottom = 4.dp).testTag("photo_button"),
                    ) { Icon(Icons.Outlined.PhotoCamera, "Фото сцены", tint = if (photoBusy) Fonar.Faint else Fonar.Lamp) }
                }
                OutlinedTextField(
                    value = input,
                    onValueChange = { if (it.text.length <= 2000) onInput(it) },
                    placeholder = {
                        Text(if (regenerating) "Идёт перегенерация…" else "*действие* и реплика…", color = Fonar.Faint)
                    },
                    minLines = 1,
                    maxLines = if (androidx.compose.ui.platform.LocalConfiguration.current.screenHeightDp < 600) 3 else 5,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                    colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = Fonar.Night, unfocusedContainerColor = Fonar.Night),
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier.weight(1f).testTag("chat_input"),
                )
                Spacer(Modifier.width(8.dp))
                FilledIconButton(
                    onClick = onSend,
                    enabled = input.text.isNotBlank() && !regenerating,
                    modifier = Modifier.size(52.dp).testTag("send_button"),
                    colors = IconButtonDefaults.filledIconButtonColors(containerColor = Fonar.Lamp, contentColor = Fonar.OnLamp),
                ) { Icon(Icons.AutoMirrored.Filled.Send, "Отправить") }
            }
        }
    }
}


@Composable
private fun PhotoMessage(m: MessageDto, url: String, onOpen: (String) -> Unit) {
    Column(Modifier.fillMaxWidth().testTag("msg_photo"), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("ФОТО СЦЕНЫ", style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 1.4.sp),
            color = Fonar.Lamp.copy(alpha = 0.8f), modifier = Modifier.padding(bottom = 6.dp))
        coil3.compose.AsyncImage(
            model = url, contentDescription = m.text,
            contentScale = androidx.compose.ui.layout.ContentScale.Crop,
            modifier = Modifier.widthIn(max = 340.dp).fillMaxWidth(0.85f)
                .aspectRatio(3f / 4f).clip(RoundedCornerShape(18.dp)).background(Fonar.SurfaceHigh)
                .clickable { onOpen(url) },
        )
        if (m.text.isNotBlank() && m.text != "Фото сцены") {
            Text(m.text, color = Fonar.Muted, style = MaterialTheme.typography.bodySmall.copy(fontStyle = FontStyle.Italic),
                textAlign = TextAlign.Center, modifier = Modifier.padding(top = 6.dp, start = 24.dp, end = 24.dp))
        }
    }
}

@Composable
private fun PhotoStatus(s: ChatState, onRetry: () -> Unit) {
    val j = s.imageJob ?: return
    when (j.status) {
        "queued", "running" -> StatusRow("Рисую фото сцены…")
        "failed" -> Surface(color = Fonar.Error.copy(alpha = 0.12f), shape = RoundedCornerShape(14.dp),
            modifier = Modifier.fillMaxWidth().testTag("photo_failed")) {
            Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Фото не получилось: " + (j.error ?: "ошибка"), color = Fonar.Error,
                    style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                TextButton(onClick = onRetry) { Text("Ещё раз") }
            }
        }
        else -> Spacer(Modifier.height(0.dp))
    }
}

@Composable
private fun AiModeDialog(room: RoomDto, onDismiss: () -> Unit, onPick: (String) -> Unit) {
    val owner = room.my_role == "owner"
    var choice by remember { mutableStateOf(room.ai_mode) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Какой ИИ ведёт сцену") },
        text = {
            Column(Modifier.exposeTags(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                ModeOption(
                    selected = choice == "local", enabled = owner, tag = "mode_local",
                    title = "Локальный", icon = Icons.Outlined.Memory,
                    desc = "Модель на твоём сервере (${room.ai_models["local"] ?: "Ollama"}). Бесплатно, но проще и медленнее.",
                ) { choice = "local" }
                ModeOption(
                    selected = choice == "cloud", enabled = owner && room.cloud_available, tag = "mode_cloud",
                    title = "Облачный", icon = Icons.Outlined.Cloud,
                    desc = if (room.cloud_available)
                        "OpenRouter (${room.ai_models["cloud"] ?: ""}). Пишет живее и подробнее, умеет рисовать фото сцены. Тратит баланс OpenRouter."
                    else "Недоступен: на сервере не задан ключ OpenRouter.",
                ) { choice = "cloud" }
                if (!owner) Text("Переключать может только хозяин сцены.", color = Fonar.Faint,
                    style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = {
            if (owner) Button(onClick = { onPick(choice) }, enabled = choice != room.ai_mode,
                modifier = Modifier.exposeTags().testTag("mode_apply")) { Text("Переключить") }
            else TextButton(onClick = onDismiss) { Text("Понятно") }
        },
        dismissButton = { if (owner) TextButton(onClick = onDismiss) { Text("Отмена") } },
        containerColor = Fonar.Surface,
    )
}

@Composable
private fun ModeOption(
    selected: Boolean, enabled: Boolean, tag: String, title: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector, desc: String, onClick: () -> Unit,
) {
    Surface(
        color = if (selected) Fonar.Lamp.copy(alpha = 0.14f) else Fonar.SurfaceHigh,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth().clickable(enabled = enabled, onClick = onClick).testTag(tag),
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.Top) {
            Icon(icon, null, tint = if (enabled) Fonar.Lamp else Fonar.Faint, modifier = Modifier.padding(top = 2.dp))
            Spacer(Modifier.width(10.dp))
            Column {
                Text(title, fontWeight = FontWeight.SemiBold, color = if (enabled) Fonar.Text else Fonar.Faint)
                Text(desc, color = Fonar.Muted, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}


/** Inline (no extra window) request for a scene photo, shown above the message input. */
@Composable
private fun PhotoPanel(onSubmit: (String) -> Unit, onClose: () -> Unit) {
    var what by rememberSaveable { mutableStateOf("") }
    Surface(color = Fonar.SurfaceHigh, shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp).testTag("photo_panel")) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.PhotoCamera, null, tint = Fonar.Lamp, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Фото сцены", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                TextButton(onClick = onClose) { Text("Отмена", color = Fonar.Muted) }
            }
            Text("ИИ нарисует, что сейчас происходит. Картинку увидите вы оба.",
                color = Fonar.Muted, style = MaterialTheme.typography.bodySmall)
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 8.dp)) {
                OutlinedTextField(
                    value = what, onValueChange = { if (it.length <= 300) what = it },
                    placeholder = { Text("что показать (необязательно)", color = Fonar.Faint) },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = Fonar.Night, unfocusedContainerColor = Fonar.Night),
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.weight(1f).testTag("photo_prompt"),
                )
                Spacer(Modifier.width(8.dp))
                Button(onClick = { onSubmit(what) }, modifier = Modifier.testTag("photo_confirm")) { Text("Нарисовать") }
            }
        }
    }
}
