package app.fonar.ui.profile

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
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
fun ProfileScreen(nav: NavHostController) {
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
            Text(u?.nick ?: "", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.testTag("profile_nick"))
            Spacer(Modifier.height(20.dp))
            OutlinedTextField(
                value = about,
                onValueChange = { if (it.length <= 300) about = it },
                label = { Text("О себе") },
                placeholder = { Text("Пара слов для друзей — необязательно", color = Fonar.Faint) },
                minLines = 3,
                supportingText = { Text("${about.length}/300") },
                colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = Fonar.Surface, unfocusedContainerColor = Fonar.Surface),
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
                                modifier = Modifier.fillMaxWidth().testTag("transfer_code"))
                            val s = left / 1000
                            Text("Действует ещё ${s / 60}:${"%02d".format(s % 60)}", color = Fonar.Muted,
                                textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
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
            Spacer(Modifier.height(32.dp))
        }
    }
}
