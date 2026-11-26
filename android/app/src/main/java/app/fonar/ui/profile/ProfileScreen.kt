package app.fonar.ui.profile

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.animation.togetherWith
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import app.fonar.data.ApiException
import app.fonar.data.TransferCodeRes
import app.fonar.data.UserDto
import app.fonar.graph
import app.fonar.ui.components.Avatar
import app.fonar.ui.theme.Fonar
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private fun errText(e: Exception) = if (e is ApiException) e.message else "Нет связи с сервером. Попробуй ещё раз."

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(nav: NavHostController, asTab: Boolean = false) {
    val graph = LocalContext.current.graph
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    var me by remember { mutableStateOf<UserDto?>(graph.me) }
    var about by rememberSaveable { mutableStateOf("") }
    var aboutLoaded by rememberSaveable { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    var code by remember { mutableStateOf<TransferCodeRes?>(null) }
    var codeAt by remember { mutableLongStateOf(0L) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }

    LaunchedEffect(Unit) {
        try {
            val u = graph.api.me().user
            me = u
            if (!aboutLoaded) { about = u.about; aboutLoaded = true }
        } catch (e: Exception) {
            message = errText(e)
        }
    }
    LaunchedEffect(message) { message?.let { snackbar.showSnackbar(it); message = null } }
    LaunchedEffect(code) {
        while (code != null) { now = System.currentTimeMillis(); delay(1000) }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch {
            busy = true
            try {
                val img = graph.api.uploadImage(context, uri, 512)
                me = graph.api.setAvatar(img.id).user
                message = "Фото профиля обновлено"
            } catch (e: Exception) {
                message = errText(e)
            } finally {
                busy = false
            }
        }
    }
    fun pick() = picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Профиль") },
                navigationIcon = {
                    if (!asTab) IconButton(onClick = { nav.popBackStack() }, modifier = Modifier.testTag("back")) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Fonar.Night),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Fonar.Night,
    ) { pad ->
        Column(
            Modifier.padding(pad).fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(8.dp))
            val u = me
            Avatar(u?.nick ?: "?", u?.let { graph.api.avatarUrl(it) }, 104.dp,
                modifier = Modifier.testTag("profile_avatar"), onClick = { if (!busy) pick() })
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                TextButton(onClick = { pick() }, enabled = !busy, modifier = Modifier.testTag("avatar_pick")) {
                    Text(if (u?.avatar_image_id == null) "Добавить фото" else "Сменить фото")
                }
                if (u?.avatar_image_id != null) TextButton(
                    onClick = {
                        scope.launch {
                            try { me = graph.api.setAvatar(null).user } catch (e: Exception) { message = errText(e) }
                        }
                    },
                    enabled = !busy, modifier = Modifier.testTag("avatar_remove"),
                ) { Text("Убрать", color = Fonar.Muted) }
            }
            var editNick by remember { mutableStateOf(false) }
            androidx.compose.animation.AnimatedContent(editNick && u != null, label = "nick",
                transitionSpec = { androidx.compose.animation.fadeIn(tween(200)) togetherWith androidx.compose.animation.fadeOut(tween(150)) }) { editing ->
                if (editing && u != null) {
                    NickEditor(u.nick, onDone = { nu ->
                        me = nu
                        graph.onNickChanged(nu)
                        editNick = false
                        message = "Ник изменён"
                    }, onCancel = { editNick = false })
                } else {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(u?.nick ?: "", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.testTag("profile_nick"))
                        IconButton(onClick = { editNick = true }, enabled = u != null, modifier = Modifier.testTag("nick_edit")) {
                            Icon(androidx.compose.material.icons.Icons.Outlined.Edit, "Изменить ник", tint = Fonar.Muted)
                        }
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            // characters address the player by this gender
            Text("Пол — так к тебе будут обращаться персонажи", color = Fonar.Muted, style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp))
            val genders = listOf("" to "Не указан", "male" to "Мужской", "female" to "Женский")
            app.fonar.ui.components.Segmented(
                options = genders.map { it.second },
                selected = genders.indexOfFirst { it.first == (me?.gender ?: "") }.coerceAtLeast(0),
                onSelect = { i ->
                    val g = genders[i].first
                    if (g != (me?.gender ?: "")) scope.launch {
                        try { me = graph.api.setGender(g).user } catch (e: Exception) { message = errText(e) }
                    }
                },
                tags = listOf("gender_none", "gender_male", "gender_female"),
            )
            Spacer(Modifier.height(20.dp))
            OutlinedTextField(
                value = about,
                onValueChange = { if (it.length <= 300) about = it },
                label = { Text("О себе") },
                placeholder = { Text("Пара слов для друзей — необязательно", color = Fonar.Faint) },
                minLines = 3,
                supportingText = { Text("${about.length}/300") },
                colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
                modifier = Modifier.fillMaxWidth().testTag("about_input"),
            )
            Button(
                onClick = {
                    scope.launch {
                        busy = true
                        try {
                            me = graph.api.setAbout(about.trim()).user
                            message = "Сохранено"
                        } catch (e: Exception) {
                            message = errText(e)
                        } finally {
                            busy = false
                        }
                    }
                },
                enabled = !busy && aboutLoaded && about.trim() != (me?.about ?: ""),
                modifier = Modifier.fillMaxWidth().testTag("about_save"),
            ) { Text("Сохранить") }

            Spacer(Modifier.height(24.dp))
            Card(colors = CardDefaults.cardColors(containerColor = Fonar.Surface), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("Вход с другого телефона", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "На новом телефоне открой GramSoul, выбери «Вход с другого телефона по коду переноса» " +
                            "и введи свой ник и этот код. Код одноразовый, действует 10 минут. Никому его не показывай.",
                        color = Fonar.Muted, style = MaterialTheme.typography.bodyMedium,
                    )
                    val c = code
                    val left = if (c == null) 0L else c.ttl_s * 1000L - (now - codeAt)
                    if (c != null) {
                        Spacer(Modifier.height(14.dp))
                        if (left > 0) {
                            Text(c.code, fontFamily = FontFamily.Monospace, fontSize = 34.sp, fontWeight = FontWeight.Bold,
                                color = Fonar.Lamp, textAlign = TextAlign.Center,
                                modifier = Modifier.fillMaxWidth()
                                    .clickable(onClickLabel = "Скопировать код") {
                                        copyText(context, "Код переноса", c.code)
                                        message = "Код скопирован"
                                    }
                                    .testTag("transfer_code"))
                            val s = left / 1000
                            Text("Нажми на код, чтобы скопировать · ещё ${s / 60}:${"%02d".format(s % 60)}", color = Fonar.Muted,
                                textAlign = TextAlign.Center, style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.fillMaxWidth())
                        } else {
                            Text("Код истёк — получи новый.", color = Fonar.Error, modifier = Modifier.fillMaxWidth(),
                                textAlign = TextAlign.Center)
                        }
                    }
                    Spacer(Modifier.height(14.dp))
                    OutlinedButton(
                        onClick = {
                            scope.launch {
                                try {
                                    code = graph.api.transferCode()
                                    codeAt = System.currentTimeMillis()
                                    now = codeAt
                                } catch (e: Exception) {
                                    message = errText(e)
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth().testTag("transfer_code_button"),
                    ) { Text(if (code == null) "Получить код переноса" else "Новый код") }
                }
            }
            Spacer(Modifier.height(16.dp))
            PasswordCard(hasPassword = me?.has_password == true, onDone = { u -> me = u; message = "Пароль сохранён" },
                onError = { message = it })
            Spacer(Modifier.height(8.dp))
            MyStuff(nav, onMessage = { message = it })
            Spacer(Modifier.height(20.dp))
            var askLogout by remember { mutableStateOf(false) }
            OutlinedButton(
                onClick = { askLogout = true },
                colors = androidx.compose.material3.ButtonDefaults.outlinedButtonColors(contentColor = Fonar.Error),
                modifier = Modifier.fillMaxWidth().testTag("logout"),
            ) { Text("Выйти из аккаунта") }
            if (askLogout) ConfirmDelete(
                title = "Выйти из аккаунта?", text = "Войти снова можно по нику и паролю.", confirm = "Выйти",
                onYes = {
                    askLogout = false
                    scope.launch {
                        runCatching { graph.api.logout() }
                        graph.startOver()
                    }
                },
                onNo = { askLogout = false },
            )
            Spacer(Modifier.height(24.dp))
            Text("GramSoul ${app.fonar.BuildConfig.VERSION_NAME}", color = Fonar.Faint,
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("app_version"))
            Spacer(Modifier.height(24.dp))
        }
    }
}

private fun copyText(context: android.content.Context, label: String, text: String) {
    val cm = context.getSystemService(android.content.ClipboardManager::class.java) ?: return
    cm.setPrimaryClip(android.content.ClipData.newPlainText(label, text))
}

@Composable
private fun ConfirmDelete(title: String, text: String, confirm: String = "Удалить", onYes: () -> Unit, onNo: () -> Unit) {
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onNo,
        title = { Text(title) },
        text = { Text(text, color = Fonar.Muted) },
        confirmButton = {
            TextButton(onClick = onYes, modifier = Modifier.testTag("confirm_yes")) { Text(confirm, color = Fonar.Error) }
        },
        dismissButton = { TextButton(onClick = onNo) { Text("Отмена") } },
        containerColor = Fonar.Surface,
    )
}

@Composable
private fun PasswordCard(hasPassword: Boolean, onDone: (UserDto) -> Unit, onError: (String) -> Unit) {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    var open by rememberSaveable { mutableStateOf(false) }
    var old by rememberSaveable { mutableStateOf("") }
    var pw by rememberSaveable { mutableStateOf("") }
    var pw2 by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val pwError = app.fonar.ui.register.localPasswordError(pw)
    val mismatch = pw2.isNotEmpty() && pw2 != pw
    val ready = !busy && pw.isNotEmpty() && pwError == null && pw2 == pw && (!hasPassword || old.isNotEmpty())
    Card(colors = CardDefaults.cardColors(containerColor = Fonar.Surface), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Пароль", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f))
                TextButton(onClick = { open = !open }, modifier = Modifier.testTag("password_toggle")) {
                    Text(if (open) "Скрыть" else if (hasPassword) "Сменить" else "Задать")
                }
            }
            if (open) {
                if (hasPassword) app.fonar.ui.register.PasswordField(old, { old = it }, "Старый пароль", "old_password_input")
                app.fonar.ui.register.PasswordField(pw, { pw = it }, "Новый пароль", "change_password_input",
                    error = pwError, hint = "Не короче 6 символов")
                app.fonar.ui.register.PasswordField(pw2, { pw2 = it }, "Повтори пароль", "change_password2_input",
                    error = if (mismatch) "Пароли не совпадают." else null, imeAction = androidx.compose.ui.text.input.ImeAction.Done)
                Button(
                    onClick = {
                        busy = true
                        scope.launch {
                            try {
                                onDone(graph.api.setPassword(pw, old.ifEmpty { null }).user)
                                old = ""; pw = ""; pw2 = ""; open = false
                            } catch (e: Exception) {
                                onError(errText(e))
                            } finally {
                                busy = false
                            }
                        }
                    },
                    enabled = ready,
                    modifier = Modifier.fillMaxWidth().padding(top = 6.dp).testTag("password_save"),
                ) { Text("Сохранить пароль") }
            }
        }
    }
}

private class Ask(val title: String, val text: String, val action: suspend () -> Unit)

/** The player's own characters, stories and chats, each with a delete button. */
@Composable
private fun MyStuff(nav: NavHostController, onMessage: (String) -> Unit) {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    var personas by remember { mutableStateOf<List<app.fonar.data.PersonaDto>?>(null) }
    var stories by remember { mutableStateOf<List<app.fonar.data.StoryDto>?>(null) }
    var rooms by remember { mutableStateOf<List<app.fonar.data.RoomListItem>?>(null) }
    var ask by remember { mutableStateOf<Ask?>(null) }

    suspend fun load() {
        runCatching { graph.api.personas(scope = "mine").personas }.onSuccess { personas = it }.onFailure { onMessage(errText(it as Exception)) }
        runCatching { graph.api.stories().stories }.onSuccess { stories = it }
        runCatching { graph.api.rooms().rooms }.onSuccess { rooms = it }
    }
    LaunchedEffect(Unit) { load() }

    @Composable
    fun Section(title: String, tag: String, empty: Boolean, content: @Composable () -> Unit) {
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp, bottom = 6.dp).testTag(tag))
        if (empty) Text("Пусто.", color = Fonar.Faint, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.fillMaxWidth())
        else content()
    }

    @Composable
    fun Item(title: String, sub: String, tag: String, onOpen: (() -> Unit)?, deleteLabel: String, onDelete: () -> Unit) {
        Row(
            Modifier.fillMaxWidth().padding(vertical = 2.dp)
                .then(if (onOpen != null) Modifier.clickable(onClick = onOpen) else Modifier)
                .testTag(tag),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f).padding(vertical = 6.dp)) {
                Text(title.ifBlank { "Без названия" }, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                if (sub.isNotBlank()) Text(sub, color = Fonar.Muted, style = MaterialTheme.typography.bodySmall, maxLines = 1,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            }
            IconButton(onClick = onDelete, modifier = Modifier.testTag(tag + "_delete")) {
                Icon(androidx.compose.material.icons.Icons.Outlined.Delete, deleteLabel, tint = Fonar.Error)
            }
        }
    }

    val ps = personas
    Section("Мои персонажи", "my_personas", ps != null && ps.isEmpty()) {
        ps?.forEach { p ->
            Item(p.name, if (p.status == "draft") "черновик" else if (p.visibility == "public") "публичный" else "личный",
                "my_persona", { nav.navigate(app.fonar.Routes.persona(p.id)) }, "Удалить персонажа") {
                ask = Ask("Удалить персонажа «${p.name}»?", "Карточка исчезнет у всех. Чаты с ним останутся, но новых ответов не будет.") {
                    graph.api.deletePersona(p.id)
                }
            }
        }
    }
    val ss = stories
    Section("Мои истории", "my_stories", ss != null && ss.isEmpty()) {
        ss?.forEach { st ->
            val sid = st.id ?: return@forEach
            Item(st.title, if (st.is_demo) "демо-история" else "своя история", "my_story", null, "Удалить историю") {
                ask = Ask("Удалить историю «${st.title}»?", "Вместе с ней удалятся все её сцены и переписка в них.") {
                    graph.api.deleteStory(sid)
                }
            }
        }
    }
    val rs = rooms
    Section("Мои чаты", "my_rooms", rs != null && rs.isEmpty()) {
        rs?.forEach { r ->
            val owner = r.my_role == "owner"
            Item(r.story_title, r.last_message, "my_room", { nav.navigate(app.fonar.Routes.chat(r.id)) },
                if (owner) "Удалить переписку" else "Выйти из сцены") {
                ask = Ask(if (owner) "Удалить переписку «${r.story_title}»?" else "Выйти из сцены «${r.story_title}»?",
                    if (owner) "Переписка удалится навсегда." else "Ты больше не увидишь эту сцену.") {
                    graph.api.deleteRoom(r.id)
                }
            }
        }
    }
    ask?.let { a ->
        ConfirmDelete(a.title, a.text, onYes = {
            ask = null
            scope.launch {
                try { a.action(); load() } catch (e: Exception) { onMessage(errText(e)) }
            }
        }, onNo = { ask = null })
    }
}


/** A new nick, edited in place: same rules as at registration; the server checks that it is free. */
@Composable
private fun NickEditor(current: String, onDone: (UserDto) -> Unit, onCancel: () -> Unit) {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    var nick by rememberSaveable { mutableStateOf(current) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val local = app.fonar.ui.register.localNickError(nick)
    val ready = !busy && nick.trim().isNotEmpty() && local == null && nick.trim() != current
    Column(Modifier.fillMaxWidth().padding(top = 8.dp)) {
        OutlinedTextField(
            value = nick, onValueChange = { if (it.length <= 24) { nick = it; error = null } },
            label = { Text("Новый ник") },
            singleLine = true, isError = local != null || error != null,
            supportingText = { Text(local ?: error ?: "Друзья увидят его сразу; входить нужно будет по нему") },
            keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(autoCorrectEnabled = false),
            colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
            modifier = Modifier.fillMaxWidth().testTag("nick_new_input"),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onCancel, enabled = !busy, modifier = Modifier.weight(1f)) { Text("Отмена") }
            Button(onClick = {
                busy = true
                scope.launch {
                    try {
                        onDone(graph.api.setNick(nick.trim()).user)
                    } catch (e: Exception) {
                        error = errText(e)
                    } finally {
                        busy = false
                    }
                }
            }, enabled = ready, modifier = Modifier.weight(1f).testTag("nick_save")) { Text("Сохранить") }
        }
    }
}
