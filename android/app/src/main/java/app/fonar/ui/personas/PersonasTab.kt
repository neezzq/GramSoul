package app.fonar.ui.personas

import app.fonar.ui.components.glow
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import app.fonar.AppGraph
import app.fonar.Routes
import app.fonar.data.ApiException
import app.fonar.data.PersonaDto
import app.fonar.graph
import app.fonar.ui.components.CenterLoading
import app.fonar.ui.components.ErrorBox
import app.fonar.ui.components.Pill
import app.fonar.ui.theme.Fonar
import coil3.compose.AsyncImage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

internal fun errText(e: Exception) = if (e is ApiException) e.message else "Нет связи с сервером. Попробуй ещё раз."

data class PersonasState(
    val loading: Boolean = true,
    val items: List<PersonaDto> = emptyList(),
    val error: String? = null,
    val q: String = "",
    val scope: String = "all",
)

class PersonasViewModel(private val g: AppGraph) : ViewModel() {
    private val _state = MutableStateFlow(PersonasState())
    val state: StateFlow<PersonasState> = _state
    private var job: Job? = null

    fun load(q: String = _state.value.q, scope: String = _state.value.scope, debounce: Boolean = false) {
        _state.update { it.copy(q = q, scope = scope) }
        job?.cancel()
        job = viewModelScope.launch {
            if (debounce) delay(300)
            try {
                val r = g.api.personas(q.trim(), scope)
                _state.update { it.copy(loading = false, items = r.personas, error = null) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update { it.copy(loading = false, error = errText(e)) }
            }
        }
    }
}

/** Placeholder colours for a card without a picture. */
internal fun personaBrush(name: String): Brush {
    val palettes = listOf(
        listOf(Color(0xFF7A1E52), Color(0xFF2A0F22)), listOf(Color(0xFF4B2A7A), Color(0xFF160F25)),
        listOf(Color(0xFF8A3A2A), Color(0xFF221010)), listOf(Color(0xFF1F5468), Color(0xFF0D1A22)),
        listOf(Color(0xFF6B5A1E), Color(0xFF1E1A0C)),
    )
    return Brush.verticalGradient(palettes[(name.hashCode() and 0x7fffffff) % palettes.size])
}

@Composable
fun PersonasTab(nav: NavHostController) {
    val graph = LocalContext.current.graph
    val vm: PersonasViewModel = viewModel { PersonasViewModel(graph) }
    val s by vm.state.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") }
    LifecycleResumeEffect(Unit) {
        vm.load()
        onPauseOrDispose { }
    }
    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = query,
            onValueChange = { if (it.length <= 60) { query = it; vm.load(q = it, debounce = true) } },
            placeholder = { Text("Имя или #тег", color = Fonar.Faint) },
            leadingIcon = { Icon(Icons.Outlined.Search, null, tint = Fonar.Muted) },
            singleLine = true,
            shape = RoundedCornerShape(16.dp),
            colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 12.dp).testTag("persona_search"),
        )
        Row(Modifier.padding(horizontal = 16.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("all" to "Все", "mine" to "Мои", "drafts" to "Черновики").forEach { (id, label) ->
                FilterChip(
                    selected = s.scope == id,
                    onClick = { vm.load(scope = id) },
                    label = { Text(label) },
                    colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Fonar.Lamp.copy(alpha = 0.22f),
                        selectedLabelColor = Fonar.Text),
                    modifier = Modifier.testTag("persona_scope_$id"),
                )
            }
        }
        when {
            s.loading && s.items.isEmpty() -> CenterLoading()
            s.error != null && s.items.isEmpty() -> ErrorBox(s.error!!, onRetry = { vm.load() })
            else -> LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 24.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.fillMaxSize().testTag("personas_grid"),
            ) {
                item(span = { GridItemSpan(2) }) {
                    Button(onClick = { nav.navigate(Routes.personaEdit(null)) }, modifier = Modifier.fillMaxWidth().glow().testTag("create_persona")) {
                        Icon(Icons.Outlined.Add, null, Modifier.size(18.dp))
                        Text("  Создать персонажа")
                    }
                }
                if (s.items.isEmpty()) item(span = { GridItemSpan(2) }) {
                    Text(
                        if (s.scope == "drafts") "Черновиков нет." else "Ничего не нашли.",
                        color = Fonar.Muted, modifier = Modifier.padding(top = 12.dp).testTag("personas_empty"),
                    )
                }
                items(s.items, key = { it.id }) { p ->
                    PersonaCard(p, graph.api.personaAvatarUrl(p)) { nav.navigate(Routes.persona(p.id)) }
                }
            }
        }
    }
}

@Composable
fun PersonaCard(p: PersonaDto, imageUrl: String?, onClick: () -> Unit) {
    val name = p.name.ifBlank { "Без имени" }
    Box(
        Modifier.fillMaxWidth().aspectRatio(2f / 3f).clip(RoundedCornerShape(18.dp)).background(personaBrush(name))
            .clickable(onClick = onClick).testTag("persona_card_$name"),
    ) {
        if (imageUrl != null) {
            AsyncImage(model = imageUrl, contentDescription = name, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        } else {
            Text(name.take(1).uppercase(), color = Color.White.copy(alpha = 0.35f), fontSize = 72.sp,
                fontWeight = FontWeight.Bold, modifier = Modifier.align(Alignment.Center))
        }
        Box(Modifier.fillMaxWidth().height(120.dp).align(Alignment.BottomCenter)
            .background(Brush.verticalGradient(listOf(Color.Transparent, Color(0xEE0A090C)))))
        Column(Modifier.align(Alignment.BottomStart).padding(10.dp)) {
            Text(name, color = Color.White, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis,
                style = MaterialTheme.typography.titleSmall)
            if (p.description.isNotBlank()) Text(p.description, color = Color.White.copy(alpha = 0.75f), maxLines = 2,
                overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodySmall)
        }
        Row(Modifier.align(Alignment.TopStart).padding(8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            if (p.status == "draft") Pill("Черновик", Fonar.LampSoft)
            else if (p.mine && p.visibility == "private") Pill("Личный", Fonar.Sea)
        }
    }
}
