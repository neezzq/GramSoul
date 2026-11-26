package app.fonar.ui.personas

import app.fonar.ui.components.glow
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.navigation.NavHostController
import app.fonar.Routes
import app.fonar.data.PersonaDto
import app.fonar.graph
import app.fonar.openChat
import app.fonar.ui.components.CenterLoading
import app.fonar.ui.components.ErrorBox
import app.fonar.ui.components.Pill
import app.fonar.ui.components.SectionTitle
import app.fonar.ui.components.actionText
import app.fonar.ui.components.exposeTags
import app.fonar.ui.theme.Fonar
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun PersonaScreen(nav: NavHostController, id: String) {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    var persona by remember { mutableStateOf<PersonaDto?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmDelete by remember { mutableStateOf(false) }

    fun load() {
        scope.launch {
            try {
                persona = graph.api.persona(id).persona
                error = null
            } catch (e: Exception) {
                error = errText(e)
            }
        }
    }
    LifecycleResumeEffect(id) {
        load()
        onPauseOrDispose { }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(persona?.name?.ifBlank { "Без имени" } ?: "", maxLines = 1) },
                navigationIcon = {
                    IconButton(onClick = { nav.popBackStack() }, modifier = Modifier.testTag("back")) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад")
                    }
                },
                actions = {
                    if (persona?.mine == true) {
                        IconButton(onClick = { nav.navigate(Routes.personaEdit(id)) }, modifier = Modifier.testTag("persona_edit")) {
                            Icon(Icons.Outlined.Edit, "Редактировать", tint = Fonar.Lamp)
                        }
                        IconButton(onClick = { confirmDelete = true }, modifier = Modifier.testTag("persona_delete")) {
                            Icon(Icons.Outlined.Delete, "Удалить", tint = Fonar.Muted)
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Fonar.Night),
            )
        },
        containerColor = Fonar.Night,
    ) { pad ->
        val p = persona
        when {
            p == null && error != null -> ErrorBox(error!!, onRetry = { load() }, modifier = Modifier.padding(pad))
            p == null -> CenterLoading(Modifier.padding(pad))
            else -> Column(
                Modifier.padding(pad).fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)
                    .testTag("persona_view"),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                val name = p.name.ifBlank { "Без имени" }
                Box(
                    Modifier.width(220.dp).aspectRatio(2f / 3f).clip(RoundedCornerShape(22.dp)).background(personaBrush(name)),
                    contentAlignment = Alignment.Center,
                ) {
                    val url = graph.api.personaAvatarUrl(p)
                    if (url != null) AsyncImage(model = url, contentDescription = name, contentScale = ContentScale.Crop,
                        modifier = Modifier.fillMaxSize().testTag("persona_avatar"))
                    else Text(name.take(1).uppercase(), color = Color.White.copy(alpha = 0.4f), fontSize = 96.sp, fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.height(14.dp))
                Text(name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold,
                    modifier = Modifier.testTag("persona_name"))
                Text(
                    when {
                        p.is_demo -> "Персонаж GramSoul"
                        p.mine -> "Твой персонаж"
                        else -> "Автор: ${p.author?.nick ?: "—"}"
                    },
                    color = Fonar.Muted, style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(Modifier.height(12.dp))
                var starting by remember { mutableStateOf(false) }
                androidx.compose.foundation.layout.Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    androidx.compose.material3.Button(
                        onClick = {
                            starting = true
                            scope.launch {
                                try {
                                    val room = graph.api.startChat(p.id).room
                                    nav.openChat(room.id)
                                } catch (e: Exception) {
                                    error = errText(e)
                                } finally {
                                    starting = false
                                }
                            }
                        },
                        enabled = !starting,
                        modifier = Modifier.weight(1f).glow().testTag("persona_chat_new"),
                    ) { Text(if (p.chats.isEmpty()) "Начать чат" else "Новый чат") }
                    p.chats.firstOrNull()?.let { last ->
                        androidx.compose.material3.OutlinedButton(
                            onClick = { nav.openChat(last.id) },
                            modifier = Modifier.weight(1f).testTag("persona_chat_continue"),
                        ) { Text("Продолжить") }
                    }
                }
                error?.let { Text(it, color = Fonar.Error, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 6.dp)) }
                Spacer(Modifier.height(8.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
                    verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                    if (p.status == "draft") Pill("Черновик", Fonar.LampSoft, Modifier.testTag("persona_status_draft"))
                    if (p.mine) Pill(if (p.visibility == "public") "Публичный" else "Личный", Fonar.Sea)
                    Pill("18+", Fonar.Muted)
                    p.tags.forEach { Pill("#$it", Fonar.Lamp) }
                }
                Column(Modifier.fillMaxWidth()) {
                    if (p.description.isNotBlank()) {
                        SectionTitle("Описание", Modifier.padding(top = 18.dp))
                        Text(p.description, color = Fonar.Text, style = MaterialTheme.typography.bodyLarge)
                    }
                    if (p.first_message.isNotBlank()) {
                        SectionTitle("Первое сообщение", Modifier.padding(top = 18.dp))
                        Text(actionText(p.first_message), color = Fonar.Text, style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier.testTag("persona_first_message"))
                    }
                    if (p.mine) {
                        if (!p.personality.isNullOrBlank()) {
                            SectionTitle("Характер · видно только тебе", Modifier.padding(top = 18.dp))
                            Text(p.personality, color = Fonar.Muted)
                        }
                        if (!p.backstory.isNullOrBlank()) {
                            SectionTitle("Предыстория · видно только тебе", Modifier.padding(top = 18.dp))
                            Text(p.backstory, color = Fonar.Muted)
                        }
                    }
                }
                Spacer(Modifier.height(32.dp))
            }
        }
    }

    if (confirmDelete) AlertDialog(
        onDismissRequest = { confirmDelete = false },
        title = { Text("Удалить персонажа?") },
        text = { Text("Карточка исчезнет у всех. Это нельзя отменить.") },
        confirmButton = {
            TextButton(onClick = {
                confirmDelete = false
                scope.launch {
                    try {
                        graph.api.deletePersona(id)
                        nav.popBackStack()
                    } catch (e: Exception) {
                        error = errText(e)
                    }
                }
            }, modifier = Modifier.testTag("persona_delete_confirm")) { Text("Удалить", color = Fonar.Error) }
        },
        dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Отмена") } },
        modifier = Modifier.exposeTags(),
    )
}
