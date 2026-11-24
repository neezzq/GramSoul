package app.fonar.ui.register

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

private val NICK_RE = Regex("^[A-Za-z0-9_\\u0410-\\u044F\\u0401\\u0451]+$")

/** Mirrors the server rules so most mistakes are explained before a request is sent. */
fun localNickError(nick: String): String? {
    val n = nick.trim()
    return when {
        n.isEmpty() -> null
        n.length < 3 -> "Ник должен быть не короче 3 символов."
        n.length > 20 -> "Ник должен быть не длиннее 20 символов."
        n.contains(' ') -> "В нике не должно быть пробелов. Можно использовать «_»."
        !NICK_RE.matches(n) -> "Можно использовать только буквы (латиница или кириллица), цифры и «_»."
        n.all { it == '_' } -> "Ник не может состоять только из «_»."
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
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val localError = localNickError(nick)

    fun submit() {
        val n = nick.trim()
        if (n.isEmpty()) { error = "Введи ник."; return }
        if (localError != null || busy) return
        busy = true
        error = null
        scope.launch {
            try {
                val res = graph.api.register(n)
                graph.onRegistered(res.token, res.user)
            } catch (e: ApiException) {
                error = e.message
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
            .background(Brush.verticalGradient(listOf(Color3(0xFF3D0F27), Fonar.Night, Fonar.Night)))
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
            "Ролевые истории на двоих\nс живым ИИ-рассказчиком",
            style = MaterialTheme.typography.bodyLarge,
            color = Fonar.Muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 6.dp),
        )
        Spacer(Modifier.height(40.dp))
        OutlinedTextField(
            value = nick,
            onValueChange = { if (it.length <= 24) { nick = it; error = null } },
            label = { Text("Твой ник") },
            singleLine = true,
            isError = (localError ?: error) != null,
            supportingText = {
                Text(localError ?: error ?: "3–20 символов: буквы, цифры и «_»")
            },
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false, imeAction = ImeAction.Go),
            keyboardActions = KeyboardActions(onGo = { submit() }),
            colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = Fonar.Surface, unfocusedContainerColor = Fonar.Surface),
            modifier = Modifier.fillMaxWidth().testTag("nick_input"),
        )
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = { submit() },
            enabled = !busy && nick.isNotBlank() && localError == null,
            modifier = Modifier.fillMaxWidth().height(54.dp).testTag("start_button"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = Fonar.OnLamp)
            else Text("Начать", style = MaterialTheme.typography.titleMedium)
        }
        Spacer(Modifier.height(24.dp))
        Text(
            "Без пароля и почты: ник привязывается к этому телефону. " +
                "Если удалить приложение или его данные, войти под этим ником снова не получится.",
            color = Fonar.Faint,
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.Center,
        )
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
                "Вход по одному нику невозможен — так никто не сможет войти в чужой аккаунт. " +
                "Восстановления аккаунта в этой версии нет, поэтому старый ник останется занятым.\n\n" +
                "Зарегистрируй новый ник и снова добавь друзей.",
            color = Fonar.Muted,
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(28.dp))
        OutlinedButton(onClick = { graph.startOver() }, modifier = Modifier.fillMaxWidth().testTag("start_over")) {
            Text("Зарегистрировать новый ник")
        }
    }
}
