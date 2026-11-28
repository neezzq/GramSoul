package app.fonar.ui.register

import app.fonar.ui.components.glow
import androidx.compose.foundation.background
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
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

/** Same limits as the server: 8–128 characters, not only spaces. */
fun localPasswordError(pw: String): String? = when {
    pw.isEmpty() -> null
    pw.length < 8 -> "Пароль — не короче 8 символов."
    pw.length > 128 -> "Пароль слишком длинный (максимум 128 символов)."
    pw.isBlank() -> "Пароль не может состоять из пробелов."
    else -> null
}

@Composable
fun AppLogo(modifier: Modifier = Modifier) {
    androidx.compose.foundation.Image(
        painter = androidx.compose.ui.res.painterResource(app.fonar.R.drawable.logo_full),
        contentDescription = "GramSoul",
        // smaller on short screens so the form and its button stay in view
        modifier = modifier.size(if (androidx.compose.ui.platform.LocalConfiguration.current.screenHeightDp < 640) 120.dp else 190.dp)
            .testTag("app_logo"),
    )
}

@Composable
fun PasswordField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    tag: String,
    error: String? = null,
    hint: String? = null,
    imeAction: ImeAction = ImeAction.Next,
    onDone: () -> Unit = {},
) {
    var shown by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value,
        onValueChange = { if (it.length <= 128) onChange(it) },
        label = { Text(label) },
        singleLine = true,
        isError = error != null,
        supportingText = (error ?: hint)?.let { t -> { Text(t, modifier = Modifier.testTag(tag + "_hint")) } },
        visualTransformation = if (shown) androidx.compose.ui.text.input.VisualTransformation.None
            else androidx.compose.ui.text.input.PasswordVisualTransformation(),
        trailingIcon = {
            androidx.compose.material3.IconButton(onClick = { shown = !shown }) {
                androidx.compose.material3.Icon(
                    if (shown) androidx.compose.material.icons.Icons.Outlined.VisibilityOff
                    else androidx.compose.material.icons.Icons.Outlined.Visibility,
                    contentDescription = if (shown) "Скрыть пароль" else "Показать пароль",
                    tint = Fonar.Muted,
                )
            }
        },
        keyboardOptions = KeyboardOptions(
            keyboardType = androidx.compose.ui.text.input.KeyboardType.Password,
            autoCorrectEnabled = false, imeAction = imeAction,
        ),
        keyboardActions = KeyboardActions(onGo = { onDone() }, onDone = { onDone() }),
        colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
        modifier = Modifier.fillMaxWidth().testTag(tag),
    )
}

private enum class AuthMode { SIGNUP, LOGIN, CODE }

@Composable
fun RegisterScreen() {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    var nick by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var password2 by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var mode by rememberSaveable { mutableStateOf(AuthMode.SIGNUP) }
    var nickTaken by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val localError = if (mode == AuthMode.SIGNUP) localNickError(nick) else null
    val pwError = if (mode == AuthMode.SIGNUP) localPasswordError(password) else null
    val mismatch = mode == AuthMode.SIGNUP && password2.isNotEmpty() && password2 != password

    fun switchTo(m: AuthMode) { mode = m; error = null; nickTaken = false }

    fun submit() {
        val n = nick.trim()
        if (n.isEmpty()) { error = "Введи ник."; return }
        if (localError != null || busy) return
        when (mode) {
            AuthMode.CODE -> if (code.count { it.isLetterOrDigit() } < 8) { error = "Введи код переноса — 8 символов."; return }
            AuthMode.LOGIN -> if (password.isEmpty()) { error = "Введи пароль."; return }
            AuthMode.SIGNUP -> {
                if (password.isEmpty()) { error = "Придумай пароль."; return }
                if (pwError != null) return
                if (password2 != password) { error = "Пароли не совпадают."; return }
            }
        }
        busy = true
        error = null
        scope.launch {
            try {
                when (mode) {
                    AuthMode.CODE -> graph.api.loginWithTransferCode(n, code.trim()).let { graph.onRegistered(it.token, it.user) }
                    AuthMode.LOGIN -> graph.api.login(n, password).let { graph.onRegistered(it.token, it.user) }
                    AuthMode.SIGNUP -> graph.api.register(n, password).let { graph.onRegistered(it.token, it.user) }
                }
            } catch (e: ApiException) {
                nickTaken = e.code == "nick_taken"
                error = when {
                    nickTaken -> "Ник занят. Если он твой — нажми «Вход»."
                    e.code == "bad_credentials" -> "Неверный ник или пароль. Если пароля ещё нет — войди по коду переноса."
                    else -> e.message
                }
            } catch (e: NetworkException) {
                error = "Нет связи с сервером. Проверь интернет и попробуй ещё раз."
            } finally {
                busy = false
            }
        }
    }

    val ready = !busy && nick.isNotBlank() && localError == null && when (mode) {
        AuthMode.SIGNUP -> password.isNotEmpty() && pwError == null && password2.isNotEmpty() && !mismatch
        AuthMode.LOGIN -> password.isNotEmpty()
        AuthMode.CODE -> code.isNotBlank()
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
        Spacer(Modifier.height(16.dp))
        AppLogo()
        Text(
            "Ролевые чаты с ИИ-персонажами\nвместе с друзьями",
            style = MaterialTheme.typography.bodyLarge,
            color = Fonar.Muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 4.dp),
        )
        Spacer(Modifier.height(24.dp))
        if (mode != AuthMode.CODE) {
            app.fonar.ui.components.Segmented(
                options = listOf("Регистрация", "Вход"),
                selected = if (mode == AuthMode.SIGNUP) 0 else 1,
                onSelect = { switchTo(if (it == 0) AuthMode.SIGNUP else AuthMode.LOGIN) },
                tags = listOf("mode_signup", "mode_login"),
            )
            Spacer(Modifier.height(14.dp))
        } else {
            Text("Вход по коду переноса", style = MaterialTheme.typography.titleMedium, color = Fonar.Text,
                modifier = Modifier.padding(bottom = 10.dp))
        }
        val nickErrorShown = localError ?: if (mode == AuthMode.SIGNUP && nickTaken) error else null
        OutlinedTextField(
            value = nick,
            onValueChange = { if (it.length <= 24) { nick = it; error = null; nickTaken = false } },
            label = { Text("Ник") },
            singleLine = true,
            isError = nickErrorShown != null,
            supportingText = {
                Text(nickErrorShown ?: if (mode == AuthMode.SIGNUP) "3–20 символов: буквы, цифры, «_» и «.»" else "",
                    modifier = Modifier.testTag("nick_hint"))
            },
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false,
                imeAction = ImeAction.Next),
            colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
            modifier = Modifier.fillMaxWidth().testTag("nick_input"),
        )
        when (mode) {
            AuthMode.SIGNUP -> {
                PasswordField(password, { password = it; error = null }, "Пароль", "password_input",
                    error = pwError, hint = "Не короче 6 символов")
                PasswordField(password2, { password2 = it; error = null }, "Повтори пароль", "password2_input",
                    error = if (mismatch) "Пароли не совпадают." else null,
                    imeAction = ImeAction.Go, onDone = { submit() })
            }
            AuthMode.LOGIN -> PasswordField(password, { password = it; error = null }, "Пароль", "password_input",
                imeAction = ImeAction.Go, onDone = { submit() })
            AuthMode.CODE -> OutlinedTextField(
                value = code,
                onValueChange = { if (it.length <= 12) { code = it.uppercase(); error = null } },
                label = { Text("Код переноса") },
                placeholder = { Text("ABCD-EFGH", color = Fonar.Faint) },
                singleLine = true,
                supportingText = { Text("Создай код в профиле на старом телефоне — он действует 10 минут") },
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, autoCorrectEnabled = false, imeAction = ImeAction.Go),
                keyboardActions = KeyboardActions(onGo = { submit() }),
                colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
                modifier = Modifier.fillMaxWidth().testTag("transfer_code_input"),
            )
        }
        val shownError = error?.takeIf { nickErrorShown != it }
        if (shownError != null) {
            Text(shownError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 4.dp).testTag("auth_error"))
        }
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = { submit() },
            enabled = ready,
            modifier = Modifier.fillMaxWidth().height(54.dp)
                .then(if (ready) Modifier.glow() else Modifier)
                .testTag("start_button"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = Fonar.OnLamp)
            else Text(if (mode == AuthMode.SIGNUP) "Создать аккаунт" else "Войти", style = MaterialTheme.typography.titleMedium)
        }
        Spacer(Modifier.height(8.dp))
        androidx.compose.material3.TextButton(
            onClick = { switchTo(if (mode == AuthMode.CODE) AuthMode.LOGIN else AuthMode.CODE) },
            modifier = Modifier.testTag("transfer_toggle"),
        ) {
            Text(
                if (mode == AuthMode.CODE) "Войти по паролю" else "Вход с другого телефона по коду переноса",
                color = Fonar.Muted,
            )
        }
        Spacer(Modifier.height(12.dp))
        Text(
            "Без почты: ник и пароль — это весь аккаунт. Без пароля можно войти по коду переноса из профиля на старом телефоне.",
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

/** Accounts made before passwords existed land here once and cannot go further until a password is set. */
@Composable
fun SetPasswordScreen() {
    val graph = LocalContext.current.graph
    val activity = LocalContext.current as? android.app.Activity
    val scope = rememberCoroutineScope()
    var password by rememberSaveable { mutableStateOf("") }
    var password2 by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val pwError = localPasswordError(password)
    val mismatch = password2.isNotEmpty() && password2 != password
    val ready = !busy && password.isNotEmpty() && pwError == null && password2 == password
    androidx.activity.compose.BackHandler { activity?.finish() }

    fun submit() {
        if (!ready) { if (password2 != password) error = "Пароли не совпадают."; return }
        busy = true; error = null
        scope.launch {
            try {
                graph.api.setPassword(password)
                graph.onPasswordSet()
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
        Modifier.fillMaxSize().background(Fonar.Night).systemBarsPadding().imePadding()
            .verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).testTag("set_password_screen"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(28.dp))
        AppLogo()
        Spacer(Modifier.height(8.dp))
        Text("Придумай пароль", style = MaterialTheme.typography.headlineSmall, color = Fonar.Text)
        Text(
            "Теперь вход — по нику и паролю. Без пароля дальше не пустит: так аккаунт можно открыть на любом телефоне, а чужой — нельзя.",
            color = Fonar.Muted, style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 8.dp, bottom = 18.dp),
        )
        PasswordField(password, { password = it; error = null }, "Новый пароль", "new_password_input",
            error = pwError, hint = "Не короче 6 символов")
        PasswordField(password2, { password2 = it; error = null }, "Повтори пароль", "new_password2_input",
            error = if (mismatch) "Пароли не совпадают." else error, imeAction = ImeAction.Go, onDone = { submit() })
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = { submit() }, enabled = ready,
            modifier = Modifier.fillMaxWidth().height(54.dp).then(if (ready) Modifier.glow() else Modifier)
                .testTag("save_password_button"),
        ) {
            if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = Fonar.OnLamp)
            else Text("Сохранить пароль", style = MaterialTheme.typography.titleMedium)
        }
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
