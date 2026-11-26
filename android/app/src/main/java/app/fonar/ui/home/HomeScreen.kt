package app.fonar.ui.home

import androidx.compose.animation.togetherWith

import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.Face
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Bolt
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.Forum
import androidx.compose.material.icons.outlined.Group
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material.icons.outlined.Public
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.RadioButton
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import app.fonar.Routes
import app.fonar.data.FriendRequestDto
import app.fonar.data.InviteDto
import app.fonar.data.StoryDto
import app.fonar.data.UserDto
import app.fonar.graph
import app.fonar.ui.components.glass
import androidx.compose.foundation.layout.navigationBarsPadding
import app.fonar.openChat
import app.fonar.ui.components.Avatar
import app.fonar.ui.components.Banner
import app.fonar.ui.components.CenterLoading
import app.fonar.ui.components.Pill
import app.fonar.ui.components.SectionTitle
import app.fonar.ui.components.exposeTags
import app.fonar.ui.theme.Fonar

// the same tabs as the web version: stories live inside «Персонажи» (switch «Персонажи | Истории»)
private enum class Tab(val title: String) { CHARACTERS("Персонажи"), CHATS("Чаты"), FRIENDS("Друзья"), PROFILE("Профиль") }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(nav: NavHostController) {
    val graph = LocalContext.current.graph
    val vm: HomeViewModel = viewModel { HomeViewModel(graph) }
    val state by vm.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableStateOf(Tab.CHARACTERS) }
    var kind by rememberSaveable { mutableStateOf(0) }  // in «Персонажи»: 0 = characters, 1 = stories
    val snackbar = remember { SnackbarHostState() }
    var pickFriendFor by remember { mutableStateOf<StoryDto?>(null) }

    LifecycleResumeEffect(Unit) {
        vm.refresh()
        onPauseOrDispose { }
    }
    LaunchedEffect(state.message) {
        state.message?.let { snackbar.showSnackbar(it); vm.consumeMessage() }
    }

    Scaffold(
        topBar = {
            if (tab != Tab.PROFILE) TopAppBar(
                title = {
                    Column {
                        Text(
                            androidx.compose.ui.text.buildAnnotatedString {
                                append("Gram")
                                pushStyle(androidx.compose.ui.text.SpanStyle(color = Fonar.Lamp)); append("Soul"); pop()
                            },
                            style = MaterialTheme.typography.titleLarge,
                        )
                        Text(graph.me?.nick ?: "", style = MaterialTheme.typography.labelMedium, color = Fonar.Muted,
                            modifier = Modifier.testTag("my_nick"))
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Fonar.Night),
            )
        },
        bottomBar = {
            // iOS-26-style floating glass tab bar
            Box(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 18.dp, vertical = 10.dp)) {
                Row(
                    Modifier.fillMaxWidth().height(66.dp).glass(RoundedCornerShape(33.dp)).padding(horizontal = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Tab.entries.forEach { t ->
                        val badge = when (t) {
                            Tab.CHATS -> state.invites.size
                            Tab.FRIENDS -> state.friends.incoming.size
                            else -> 0
                        }
                        val selected = tab == t
                        Column(
                            Modifier.weight(1f).height(54.dp).clip(RoundedCornerShape(27.dp))
                                .then(if (selected) Modifier.background(Fonar.Lamp.copy(alpha = 0.16f)) else Modifier)
                                .clickable { tab = t }.testTag("tab_${t.name.lowercase()}"),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center,
                        ) {
                            BadgedBox(badge = { if (badge > 0) Badge(containerColor = Fonar.Lamp, contentColor = Fonar.OnLamp) { Text("$badge") } }) {
                                Icon(
                                    when (t) {
                                        Tab.CHARACTERS -> Icons.Outlined.Face
                                        Tab.CHATS -> Icons.Outlined.Forum
                                        Tab.FRIENDS -> Icons.Outlined.Group
                                        Tab.PROFILE -> Icons.Outlined.AccountCircle
                                    }, null,
                                    tint = if (selected) Fonar.Lamp else Fonar.Muted,
                                    modifier = Modifier.size(24.dp),
                                )
                            }
                            Text(t.title, style = MaterialTheme.typography.labelSmall,
                                color = if (selected) Fonar.Lamp else Fonar.Muted, maxLines = 1)
                        }
                    }
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Fonar.Night,
    ) { pad ->
        Box(Modifier.padding(pad).fillMaxSize()) {
            if (state.loading) CenterLoading()
            else androidx.compose.animation.AnimatedContent(
                targetState = tab, label = "tabs",
                transitionSpec = {
                    (androidx.compose.animation.fadeIn(androidx.compose.animation.core.tween(220)) +
                        androidx.compose.animation.slideInVertically(androidx.compose.animation.core.tween(260)) { it / 24 })
                        .togetherWith(androidx.compose.animation.fadeOut(androidx.compose.animation.core.tween(120)))
                },
            ) { t ->
                when (t) {
                    Tab.CHARACTERS -> Column(Modifier.fillMaxSize()) {
                        app.fonar.ui.components.Segmented(
                            listOf("Персонажи", "Истории"), kind, { kind = it },
                            tags = listOf("kind_personas", "kind_stories"),
                            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 4.dp),
                        )
                        if (kind == 0) app.fonar.ui.personas.PersonasTab(nav)
                        else StoriesTab(state, vm, nav, onPlayWithFriend = { pickFriendFor = it }, onOpenInvites = { tab = Tab.CHATS })
                    }
                    Tab.CHATS -> ScenesTab(state, vm, nav)
                    Tab.FRIENDS -> FriendsTab(state, vm)
                    Tab.PROFILE -> app.fonar.ui.profile.ProfileScreen(nav, asTab = true)
                }
            }
        }
    }

    pickFriendFor?.let { story ->
        FriendPickerDialog(
            friends = state.friends.friends,
            title = "Играть с другом",
            onDismiss = { pickFriendFor = null },
            onPick = { friend ->
                pickFriendFor = null
                vm.startRoom(story.id!!, friend.id) { room -> nav.openChat(room.id) }
            },
            onGoToFriends = { pickFriendFor = null; tab = Tab.FRIENDS },
        )
    }
}

@Composable
fun FriendPickerDialog(
    friends: List<UserDto>,
    title: String,
    onDismiss: () -> Unit,
    onPick: (UserDto) -> Unit,
    onGoToFriends: (() -> Unit)? = null,
) {
    var selected by remember { mutableStateOf<UserDto?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            if (friends.isEmpty()) {
                Text("У тебя пока нет друзей, принявших заявку. Найди друга по нику во вкладке «Друзья».", color = Fonar.Muted)
            } else {
                Column(Modifier.exposeTags()) {
                    Text("Выбери одного друга — он получит приглашение в приложении.", color = Fonar.Muted,
                        style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(8.dp))
                    friends.forEach { f ->
                        Row(
                            Modifier.fillMaxWidth().clickable { selected = f }.padding(vertical = 6.dp).testTag("pick_${f.nick}"),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(selected = selected?.id == f.id, onClick = { selected = f })
                            Avatar(f.nick, null, 32.dp)
                            Spacer(Modifier.width(10.dp))
                            Text(f.nick)
                        }
                    }
                }
            }
        },
        confirmButton = {
            if (friends.isEmpty()) {
                if (onGoToFriends != null) TextButton(onClick = onGoToFriends) { Text("К друзьям") }
            } else {
                Button(onClick = { selected?.let(onPick) }, enabled = selected != null, modifier = Modifier.exposeTags().testTag("invite_confirm")) {
                    Text("Пригласить")
                }
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } },
        containerColor = Fonar.Surface,
    )
}

// ------------------------------------------------------------------- stories
@Composable
private fun StoriesTab(
    state: HomeState,
    vm: HomeViewModel,
    nav: NavHostController,
    onPlayWithFriend: (StoryDto) -> Unit,
    onOpenInvites: () -> Unit,
) {
    val graph = LocalContext.current.graph
    var scope by rememberSaveable { mutableStateOf(0) }  // 0 = mine, 1 = published by others
    LaunchedEffect(scope) { if (scope == 1) vm.loadPublicStories() }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.testTag("stories_list")) {
        item {
            // chips, like in the web version (one big switch above is enough)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("Мои" to "stories_mine", "Общие" to "stories_public").forEachIndexed { i, (label, tag) ->
                    androidx.compose.material3.FilterChip(
                        selected = scope == i, onClick = { scope = i }, label = { Text(label) },
                        colors = androidx.compose.material3.FilterChipDefaults.filterChipColors(
                            selectedContainerColor = Fonar.Lamp.copy(alpha = 0.22f), selectedLabelColor = Fonar.Text),
                        modifier = Modifier.testTag(tag),
                    )
                }
            }
        }
        if (scope == 1) {
            val list = state.publicStories
            when {
                list == null -> item { CenterLoading(Modifier.height(120.dp)) }
                list.isEmpty() -> item {
                    Text("Пока никто не опубликовал историю. Опубликуй свою — в меню ⋯ на её карточке.",
                        color = Fonar.Muted, modifier = Modifier.testTag("public_stories_empty"))
                }
                else -> items(list, key = { "pub" + it.id }) { st ->
                    Box(Modifier.animateItem()) {
                        StoryCard(
                            st,
                            coverUrl = st.cover_image_id?.let { graph.api.storyImageUrl(st.id!!, it) },
                            avatarUrl = st.avatar_image_id?.let { graph.api.storyImageUrl(st.id!!, it) },
                            onPlay = { vm.startRoom(st.id!!, null) { room -> nav.openChat(room.id) } },
                            onPlayWithFriend = { onPlayWithFriend(st) },
                            onEdit = null, onDelete = null, onToggleVisibility = null,
                        )
                    }
                }
            }
            return@LazyColumn
        }
        if (state.offline) item { Banner("Нет связи с сервером — показываю, что есть", Fonar.Error) }
        if (state.invites.isNotEmpty()) item {
            Banner("Тебя зовут в сцену: ${state.invites.size}", Fonar.Sea) {
                TextButton(onClick = onOpenInvites) { Text("Открыть") }
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                FilledTonalButton(onClick = { nav.navigate(Routes.QUICK) }, modifier = Modifier.weight(1f).testTag("create_quick")) {
                    Icon(Icons.Outlined.Bolt, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Быстро")
                }
                OutlinedButton(onClick = { nav.navigate(Routes.editor()) }, modifier = Modifier.weight(1f).testTag("create_full")) {
                    Icon(Icons.Outlined.AutoAwesome, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Редактор")
                }
            }
        }
        if (state.drafts.isNotEmpty()) {
            item { SectionTitle("Черновики") }
            items(state.drafts, key = { it.draftId }) { d ->
                Card(colors = CardDefaults.cardColors(containerColor = Fonar.Surface),
                    modifier = Modifier.animateItem().fillMaxWidth().clickable { nav.navigate(Routes.editor(draftId = d.draftId)) }) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(d.story.title.ifBlank { "Без названия" }, fontWeight = FontWeight.SemiBold)
                            Text("Не сохранено на сервере", color = Fonar.Muted, style = MaterialTheme.typography.bodySmall)
                        }
                        IconButton(onClick = { vm.deleteDraft(d.draftId) }) { Icon(Icons.Outlined.Delete, "Удалить черновик", tint = Fonar.Muted) }
                    }
                }
            }
        }
        item { SectionTitle("Мои истории") }
        if (state.stories.isEmpty()) item {
            Text("Пока нет историй. Создай свою — быстро или в полном редакторе.", color = Fonar.Muted,
                modifier = Modifier.testTag("stories_empty"))
        }
        items(state.stories, key = { it.id!! }) { s ->
            Box(Modifier.animateItem()) {
            StoryCard(
                s,
                coverUrl = s.cover_image_id?.let { graph.api.ownImageUrl(it) },
                avatarUrl = s.avatar_image_id?.let { graph.api.ownImageUrl(it) },
                onPlay = { vm.startRoom(s.id!!, null) { room -> nav.openChat(room.id) } },
                onPlayWithFriend = { onPlayWithFriend(s) },
                onEdit = { nav.navigate(Routes.editor(storyId = s.id)) },
                onDelete = { vm.deleteStory(s.id!!) },
                onToggleVisibility = { vm.setStoryVisibility(s.id!!, s.visibility != "public") },
            )
            }
        }
    }
}

@Composable
private fun StoryCard(
    s: StoryDto,
    coverUrl: String?,
    avatarUrl: String?,
    onPlay: () -> Unit,
    onPlayWithFriend: () -> Unit,
    onEdit: (() -> Unit)?,
    onDelete: (() -> Unit)?,
    onToggleVisibility: (() -> Unit)?,
) {
    var menu by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    Card(
        colors = CardDefaults.cardColors(containerColor = Fonar.Surface),
        shape = RoundedCornerShape(20.dp),
        modifier = Modifier.fillMaxWidth().testTag("story_${s.title}"),
    ) {
        if (coverUrl != null) {
            coil3.compose.AsyncImage(
                model = coverUrl, contentDescription = null,
                contentScale = androidx.compose.ui.layout.ContentScale.Crop,
                modifier = Modifier.fillMaxWidth().height(120.dp),
            )
        }
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(s.character_names.firstOrNull() ?: s.title, avatarUrl, 44.dp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(s.title, style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (s.character_names.isNotEmpty()) {
                        Text(s.character_names.joinToString(" · "), color = Fonar.Muted, style = MaterialTheme.typography.bodySmall,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                if (s.is_demo) Pill("демо", Fonar.Lamp)
                if (s.mine && s.visibility == "public") Pill("публичная", Fonar.Sea, Modifier.testTag("story_public_pill"))
                if (!s.mine) s.author?.let { Pill(it.nick, Fonar.Muted) }
                if (onEdit != null || onDelete != null || onToggleVisibility != null) Box {
                    IconButton(onClick = { menu = true }, modifier = Modifier.testTag("story_menu_${s.title}")) { Icon(Icons.Outlined.MoreVert, "Ещё") }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        if (onEdit != null) DropdownMenuItem(text = { Text("Изменить") }, leadingIcon = { Icon(Icons.Outlined.Edit, null) },
                            onClick = { menu = false; onEdit() })
                        if (onToggleVisibility != null) DropdownMenuItem(
                            text = { Text(if (s.visibility == "public") "Сделать личной" else "Опубликовать для всех") },
                            leadingIcon = { Icon(Icons.Outlined.Public, null) },
                            onClick = { menu = false; onToggleVisibility() },
                            modifier = Modifier.exposeTags().testTag("story_publish"),
                        )
                        if (onDelete != null) DropdownMenuItem(text = { Text("Удалить") }, leadingIcon = { Icon(Icons.Outlined.Delete, null) },
                            onClick = { menu = false; confirmDelete = true })
                    }
                }
            }
            if (s.description.isNotBlank()) {
                Text(s.description, color = Fonar.Muted, style = MaterialTheme.typography.bodyMedium,
                    maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 10.dp))
            }
            Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = onPlayWithFriend, modifier = Modifier.weight(1f).testTag("play_friend_${s.title}")) {
                    Icon(Icons.Outlined.PersonAdd, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Играть с другом")
                }
                OutlinedButton(onClick = onPlay, modifier = Modifier.testTag("play_${s.title}")) {
                    Icon(Icons.Outlined.PlayArrow, null, Modifier.size(18.dp)); Spacer(Modifier.width(4.dp)); Text("Одному")
                }
            }
        }
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Удалить историю?") },
            text = { Text("Все сцены этой истории тоже удалятся у обоих игроков.") },
            confirmButton = { TextButton(onClick = { confirmDelete = false; onDelete?.invoke() }) { Text("Удалить", color = Fonar.Error) } },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Отмена") } },
            containerColor = Fonar.Surface,
        )
    }
}

// ------------------------------------------------------------------- scenes
@Composable
private fun ScenesTab(state: HomeState, vm: HomeViewModel, nav: NavHostController) {
    val graph = LocalContext.current.graph
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (state.invites.isNotEmpty()) {
            item { SectionTitle("Приглашения в игру") }
            items(state.invites, key = { it.id }) { inv -> InviteCard(inv, vm) { nav.openChat(it) } }
        }
        item { SectionTitle("Мои сцены") }
        if (state.rooms.isEmpty()) item {
            Text("Пока пусто. Открой историю и нажми «Играть с другом» или «Одному».", color = Fonar.Muted)
        }
        items(state.rooms, key = { it.id }) { r ->
            Card(
                colors = CardDefaults.cardColors(containerColor = Fonar.Surface),
                modifier = Modifier.animateItem().fillMaxWidth().clickable { nav.openChat(r.id) }.testTag("room_${r.story_title}"),
            ) {
                Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Avatar(r.story_title, null, 42.dp)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(r.story_title, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(
                            when {
                                r.partner != null -> "с ${r.partner.nick}"
                                else -> "пока одна/один"
                            } + if (r.my_role == "guest") " · ты гость" else "",
                            color = Fonar.Sea, style = MaterialTheme.typography.labelMedium,
                        )
                        if (r.last_message.isNotBlank()) {
                            Text(r.last_message.replace("*", ""), color = Fonar.Muted, style = MaterialTheme.typography.bodySmall,
                                maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }
        item { Spacer(Modifier.height(8.dp)) }
    }
}

@Composable
private fun InviteCard(inv: InviteDto, vm: HomeViewModel, onJoined: (String) -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = Fonar.SurfaceHigh), modifier = Modifier.fillMaxWidth().testTag("invite_card")) {
        Column(Modifier.padding(14.dp)) {
            Text("${inv.from?.nick ?: "Друг"} зовёт тебя играть", fontWeight = FontWeight.SemiBold)
            Text("«${inv.story_title ?: ""}»", color = Fonar.Muted, style = MaterialTheme.typography.bodyMedium)
            Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = { vm.answerInvite(inv.id, true, onJoined) }, modifier = Modifier.testTag("invite_accept")) { Text("Принять") }
                OutlinedButton(onClick = { vm.answerInvite(inv.id, false) {} }) { Text("Отклонить") }
            }
        }
    }
}

// ------------------------------------------------------------------- friends
@Composable
private fun FriendsTab(state: HomeState, vm: HomeViewModel) {
    val graph = LocalContext.current.graph
    var query by rememberSaveable { mutableStateOf("") }
    // search as you type, 300 ms after the last keystroke
    LaunchedEffect(query) {
        if (query.trim() != state.searchQuery) {
            if (query.trim().length >= 2) kotlinx.coroutines.delay(300)
            vm.search(query)
        }
    }
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.imePadding(),
    ) {
        item {
            OutlinedTextField(
                value = query,
                onValueChange = { if (it.length <= 24) query = it },
                label = { Text("Найти по нику") },
                singleLine = true,
                trailingIcon = {
                    if (state.searchBusy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    else IconButton(onClick = { vm.search(query) }, modifier = Modifier.testTag("friend_search_button")) {
                        Icon(Icons.Outlined.Search, "Найти")
                    }
                },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search, autoCorrectEnabled = false),
                keyboardActions = KeyboardActions(onSearch = { vm.search(query) }),
                colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
                modifier = Modifier.fillMaxWidth().testTag("friend_search_input"),
            )
            Text("По началу или части ника, от 2 символов", color = Fonar.Faint,
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp, start = 4.dp))
        }
        state.searchError?.let { e -> item { Text(e, color = Fonar.Error, modifier = Modifier.testTag("friend_search_error")) } }
        if (state.searchQuery.length >= 2 && !state.searchBusy && state.searchError == null && state.searchResults.isEmpty()) item {
            Text("Никого не нашли по «${state.searchQuery}».", color = Fonar.Muted, modifier = Modifier.testTag("search_empty"))
        }
        items(state.searchResults, key = { "s" + it.user.id }) { r ->
            Card(colors = CardDefaults.cardColors(containerColor = Fonar.SurfaceHigh), modifier = Modifier.testTag("search_result_${r.user.nick}")) {
                Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Avatar(r.user.nick, graph.api.avatarUrl(r.user), 44.dp)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(r.user.nick, fontWeight = FontWeight.SemiBold)
                        if (r.user.about.isNotBlank()) Text(r.user.about, color = Fonar.Muted, maxLines = 1,
                            overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, style = MaterialTheme.typography.bodySmall)
                    }
                    Spacer(Modifier.width(8.dp))
                    when (r.relation) {
                        "none", "outgoing_declined" -> Button(onClick = { vm.sendRequest(r.user.nick) },
                            modifier = Modifier.testTag("add_friend_${r.user.nick}")) { Text(if (r.relation == "none") "В друзья" else "Ещё раз") }
                        "outgoing_pending" -> Pill("Заявка отправлена", Fonar.Lamp, Modifier.testTag("request_sent_${r.user.nick}"))
                        "friends", "outgoing_accepted" -> Pill("В друзьях", Fonar.Sea)
                        "incoming_pending" -> Button(onClick = { r.request_id?.let { vm.answerRequest(it, true) } }) { Text("Принять") }
                        "self" -> Pill("Это ты", Fonar.Muted)
                    }
                }
            }
        }
        if (state.friends.incoming.isNotEmpty()) {
            item { SectionTitle("Входящие заявки") }
            items(state.friends.incoming, key = { "in" + it.id }) { req -> IncomingRow(req, vm) }
        }
        if (state.friends.outgoing.isNotEmpty()) {
            item { SectionTitle("Мои заявки") }
            items(state.friends.outgoing, key = { "out" + it.id }) { req ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp).testTag("outgoing_${req.user.nick}"),
                    verticalAlignment = Alignment.CenterVertically) {
                    Avatar(req.user.nick, graph.api.avatarUrl(req.user), 36.dp)
                    Spacer(Modifier.width(10.dp))
                    Text(req.user.nick, modifier = Modifier.weight(1f))
                    when (req.status) {
                        "pending" -> Pill("отправлена", Fonar.Lamp)
                        "accepted" -> Pill("принята", Fonar.Sea)
                        "declined" -> Pill("отклонена", Fonar.Error)
                    }
                }
            }
        }
        item { SectionTitle("Друзья") }
        if (state.friends.friends.isEmpty()) item {
            Text("Пока никого. Найди друга по нику и отправь заявку.", color = Fonar.Muted)
        }
        items(state.friends.friends, key = { "f" + it.id }) { f ->
            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp).testTag("friend_${f.nick}"), verticalAlignment = Alignment.CenterVertically) {
                Box {
                    Avatar(f.nick, graph.api.avatarUrl(f), 40.dp)
                    if (f.online) Box(
                        Modifier.align(Alignment.BottomEnd).size(12.dp).clip(CircleShape).background(Fonar.Night)
                            .padding(2.dp).clip(CircleShape).background(OnlineGreen).testTag("online_${f.nick}"),
                    )
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(f.nick, style = MaterialTheme.typography.bodyLarge)
                    Text(
                        if (f.online) "в сети" else lastSeenText(f.last_seen_at),
                        color = if (f.online) OnlineGreen else Fonar.Faint,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

private val OnlineGreen = androidx.compose.ui.graphics.Color(0xFF4CD787)

private fun lastSeenText(ts: Long?): String {
    if (ts == null || ts <= 0) return "давно не заходил(а)"
    val min = (System.currentTimeMillis() - ts) / 60_000
    return when {
        min < 60 -> "был(а) ${maxOf(min, 1)} мин назад"
        min < 24 * 60 -> "был(а) ${min / 60} ч назад"
        else -> "был(а) ${min / (24 * 60)} дн назад"
    }
}

@Composable
private fun IncomingRow(req: FriendRequestDto, vm: HomeViewModel) {
    Card(colors = CardDefaults.cardColors(containerColor = Fonar.Surface), modifier = Modifier.testTag("incoming_${req.user.nick}")) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Avatar(req.user.nick, LocalContext.current.graph.api.avatarUrl(req.user), 40.dp)
            Spacer(Modifier.width(12.dp))
            Text(req.user.nick, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            TextButton(onClick = { vm.answerRequest(req.id, false) }, modifier = Modifier.testTag("decline_${req.user.nick}")) {
                Text("Отклонить", color = Fonar.Muted)
            }
            Button(onClick = { vm.answerRequest(req.id, true) }, modifier = Modifier.testTag("accept_${req.user.nick}")) { Text("Принять") }
        }
    }
}
