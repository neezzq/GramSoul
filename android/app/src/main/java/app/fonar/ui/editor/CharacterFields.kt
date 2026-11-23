package app.fonar.ui.editor

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.fonar.data.CharacterDto
import app.fonar.ui.components.Field
import app.fonar.ui.components.ImagePickBox
import app.fonar.ui.components.SectionTitle
import app.fonar.ui.theme.Fonar

/** A target for "отношение к …": another character or player hero of the same story. */
data class RelTarget(val key: String, val name: String)

@Composable
fun CharacterFields(
    c: CharacterDto,
    onChange: (CharacterDto) -> Unit,
    relTargets: List<RelTarget>,
    avatarUrl: String?,
    uploading: Boolean,
    onPickAvatar: () -> Unit,
    showRole: Boolean,
    canBeHero: Boolean,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ImagePickBox(avatarUrl, "Аватар", uploading, round = true, size = 84.dp, onPick = onPickAvatar)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Field("Имя", c.name, { onChange(c.copy(name = it)) }, maxLength = 40, testTag = "char_name")
                Field("Возраст", c.age, { onChange(c.copy(age = it)) }, maxLength = 40, modifier = Modifier.padding(top = 8.dp))
            }
        }
        if (showRole) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = c.role == "npc", onClick = { onChange(c.copy(role = "npc")) },
                    label = { Text("Ведёт ИИ") })
                FilterChip(selected = c.role == "hero", enabled = canBeHero || c.role == "hero",
                    onClick = { onChange(c.copy(role = "hero")) }, label = { Text("Герой игрока") })
            }
            Text(
                if (c.role == "hero") "Героем управляет игрок: первый герой — хозяин сцены, второй — приглашённый друг."
                else "Этого персонажа ведёт ИИ.",
                color = Fonar.Faint, style = MaterialTheme.typography.bodySmall,
            )
        }
        Field("Характер", c.personality, { onChange(c.copy(personality = it)) }, minLines = 2, testTag = "char_personality",
            hint = "Тихая, упрямая, боится темноты…")
        Field("Манера речи", c.speech_style, { onChange(c.copy(speech_style = it)) }, minLines = 2, maxLength = 1000,
            hint = "Коротко, полушёпотом, с морскими сравнениями", testTag = "char_speech")
        Field("Привычки", c.habits, { onChange(c.copy(habits = it)) }, minLines = 2, testTag = "char_habits")
        Field("Внешность", c.appearance, { onChange(c.copy(appearance = it)) }, minLines = 2)
        Field("Мотивация", c.motivation, { onChange(c.copy(motivation = it)) }, minLines = 2)
        Field("Предыстория", c.backstory, { onChange(c.copy(backstory = it)) }, minLines = 3, maxLength = 3000)
        if (relTargets.isNotEmpty()) {
            SectionTitle("Отношение к героям")
            relTargets.forEach { t ->
                Field("К: ${t.name}", c.relationships[t.key].orEmpty(), { v ->
                    val m = c.relationships.toMutableMap()
                    if (v.isBlank()) m.remove(t.key) else m[t.key] = v
                    onChange(c.copy(relationships = m))
                }, minLines = 1, maxLines = 4, maxLength = 500)
            }
        }
        Field("Примеры реплик", c.example_lines, { onChange(c.copy(example_lines = it)) }, minLines = 3,
            hint = "*крутит ракушку* Море сегодня дышит неровно.\nКаждая реплика — с новой строки")
        Spacer(Modifier.fillMaxWidth().padding(4.dp))
    }
}
