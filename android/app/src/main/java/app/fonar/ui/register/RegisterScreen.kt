package app.fonar.ui.register

import app.fonar.ui.components.glow
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import app.fonar.data.ApiException
import app.fonar.data.NetworkException
import app.fonar.graph
import app.fonar.ui.theme.Fonar
import kotlinx.coroutines.launch

private val NICK_RE = Regex("^[A-Za-z0-9_.\\u0410-\\u044F\\u0401\\u0451]+$")

/** Mirrors the server rules so most mistakes are explained before a request is sent. */
fun localNickError(nick: String): String? {
    val n = nick.trim()
    return when {
        n.isEmpty() -> null
        n.length < 3 -> "Ник должен быть не короче 3 символов."
        n.length > 20 -> "Ник должен быть не длиннее 20 символов."
        n.contains(' ') -> "В нике не должно быть пробелов. Можно использовать «_» и «.»."
        !NICK_RE.matches(n) -> "Можно использовать только буквы (латиница или кириллица), цифры, «_» и «.»."
        n.all { it == '_' || it == '.' } -> "Ник не может состоять только из «_» и «.»."
        else -> null
    }
}

@Composable
fun Lantern(modifier: Modifier = Modifier) {
    Box(
        modifier
            .size(96.dp)
            .clip(CircleShape)
            .background(Brush.radialGradient(listOf(Color3(0xFFFFD1E8), Fonar.Lamp.copy(alpha = 0.6f), Fonar.Night.copy(alpha = 0f))))
    )
}

@Composable
fun RegisterScreen() {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    var nick by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var transferMode by rememberSaveable { mutableStateOf(false) }
    var nickTaken by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val localError = localNickError(nick)

    fun submit() {
        val n = nick.trim()
        if (n.isEmpty()) { error = "Введи ник."; return }
        if (localError != null || busy) return
        if (transferMode && code.count { it.isLetterOrDigit() } < 8) { error = "Введи код переноса — 8 символов."; return }
        busy = true
        error = null
        scope.launch {
            try {
                if (transferMode) {
                    val res = graph.api.loginWithTransferCode(n, code.trim())
                    graph.onRegistered(res.token, res.user)
                } else {
                    val res = graph.api.register(n)
                    graph.onRegistered(res.token, res.user)
                }
            } catch (e: ApiException) {
                nickTaken = e.code == "nick_taken"
                error = if (nickTaken) "Ник занят. Если это твой ник с другого телефона — войди с кодом переноса." else e.message
            } catch (e: NetworkException) {
                error = "Нет связи с сервером. Проверь интернет и попробуй ещё раз."
            } finally {
                busy = false
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(Fonar.Night)
            .background(Brush.radialGradient(listOf(Fonar.Lamp.copy(alpha = 0.16f), Color3(0x00000000)),
                center = androidx.compose.ui.geometry.Offset(540f, 260f), radius = 900f))
            .systemBarsPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(56.dp))
        Lantern()
        Spacer(Modifier.height(18.dp))
        Text(
            androidx.compose.ui.text.buildAnnotatedString {
                append("Gram")
                pushStyle(androidx.compose.ui.text.SpanStyle(color = Fonar.Lamp)); append("Soul"); pop()
            },
            style = MaterialTheme.typography.headlineLarge, color = Fonar.Text,
        )
        Text(
            "Ролевые чаты с ИИ-персонажами\nвместе с друзьями",
            style = MaterialTheme.typography.bodyLarge,
            color = Fonar.Muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 6.dp),
        )
        Spacer(Modifier.height(40.dp))
        OutlinedTextField(
            value = nick,
            onValueChange = { if (it.length <= 24) { nick = it; error = null; nickTaken = false } },
            label = { Text("Ник") },
            singleLine = true,
            isError = localError != null || (!transferMode && error != null),
            supportingText = {
                Text(localError ?: (if (!transferMode) error else null) ?: "3–20 символов: буквы, цифры, «_» и «.»",
                    modifier = Modifier.testTag("nick_hint"))
            },
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false,
                imeAction = if (transferMode) ImeAction.Next else ImeAction.Go),
            keyboardActions = KeyboardActions(onGo = { submit() }),
            colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
            modifier = Modifier.fillMaxWidth().testTag("nick_input"),
        )
        if (transferMode) {
            Spacer(Modifier.height(4.dp))
            OutlinedTextField(
                value = code,
                onValueChange = { if (it.length <= 12) { code = it.uppercase(); error = null } },
                label = { Text("Код переноса") },
                placeholder = { Text("ABCD-EFGH", color = Fonar.Faint) },
                singleLine = true,
                isError = error != null,
                supportingText = { Text(error ?: "Создай код в профиле на старом телефоне — он действует 10 минут") },
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, autoCorrectEnabled = false, imeAction = ImeAction.Go),
                keyboardActions = KeyboardActions(onGo = { submit() }),
                colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
                modifier = Modifier.fillMaxWidth().testTag("transfer_code_input"),
            )
        }
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = { submit() },
            enabled = !busy && nick.isNotBlank() && localError == null,
            modifier = Modifier.fillMaxWidth().height(54.dp)
                .then(if (!busy && nick.isNotBlank() && localError == null) Modifier.glow() else Modifier)
                .testTag("start_button"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = Fonar.OnLamp)
            else Text("Войти", style = MaterialTheme.typography.titleMedium)
        }
        Spacer(Modifier.height(8.dp))
        androidx.compose.material3.TextButton(
            onClick = { transferMode = !transferMode; error = null; nickTaken = false },
            modifier = Modifier.testTag("transfer_toggle"),
        ) {
            Text(
                if (transferMode) "Я здесь впервые — создать ник" else "Вход с другого телефона по коду переноса",
                color = if (nickTaken && !transferMode) Fonar.Lamp else Fonar.Muted,
            )
        }
        Spacer(Modifier.height(16.dp))
        Text(
            "Без пароля и почты: новый ник сразу становится твоим аккаунтом, ключ входа хранится на этом телефоне. " +
                "Чтобы войти с другого телефона, создай в профиле код переноса.",
            color = Fonar.Faint,
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(16.dp))
        Text("Версия ${app.fonar.BuildConfig.VERSION_NAME}", color = Fonar.Faint.copy(alpha = 0.7f),
            style = MaterialTheme.typography.labelSmall, modifier = Modifier.testTag("app_version"))
        Spacer(Modifier.height(24.dp))
    }
}

private fun Color3(v: Long) = androidx.compose.ui.graphics.Color(v)

@Composable
fun SessionLostScreen(nick: String?) {
    val graph = LocalContext.current.graph
    Column(
        Modifier.fillMaxSize().systemBarsPadding().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Lantern(Modifier.size(72.dp))
        Spacer(Modifier.height(20.dp))
        Text("Сессия потеряна", style = MaterialTheme.typography.headlineSmall, color = Fonar.Text)
        Spacer(Modifier.height(12.dp))
        Text(
            (if (nick != null) "Ключ входа для ника «$nick» на этом устройстве больше недействителен. " else
                "Ключ входа на этом устройстве больше недействителен. ") +
                "Так бывает после переустановки, очистки данных или сброса сервера.\n\n" +
                "Вход по одному нику невозможен — так никто не сможет войти в чужой аккаунт.\n\n" +
                "Если ник ещё открыт на другом телефоне, создай там в профиле код переноса и войди с ним. " +
                "Иначе зарегистрируй новый ник.",
            color = Fonar.Muted,
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(28.dp))
        OutlinedButton(onClick = { graph.startOver() }, modifier = Modifier.fillMaxWidth().testTag("start_over")) {
            Text("Войти с кодом или создать новый ник")
        }
    }
}
