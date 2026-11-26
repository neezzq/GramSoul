package app.fonar.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import app.fonar.data.AvatarStyle
import app.fonar.ui.theme.Fonar

/** Styles of AI pictures (avatars and scene pictures). The server sends the same list; this is the fallback. */
val DEFAULT_STYLES = listOf(
    AvatarStyle("aesthetic", "Эстетика"), AvatarStyle("anime", "Аниме"), AvatarStyle("realism", "Реализм"),
    AvatarStyle("painted", "Нарисованный"), AvatarStyle("manhwa", "Манхва"), AvatarStyle("sketch", "Ч/б рисунок"),
)

fun styleLabel(id: String?): String = DEFAULT_STYLES.firstOrNull { it.id == id }?.label ?: "Эстетика"

/** Preview pictures generated with our own style prompts (res/drawable-nodpi/style_*.jpg). */
fun stylePreview(id: String): Int? = when (id) {
    "anime" -> app.fonar.R.drawable.style_anime
    "realism" -> app.fonar.R.drawable.style_realism
    "painted" -> app.fonar.R.drawable.style_painted
    "manhwa" -> app.fonar.R.drawable.style_manhwa
    "sketch" -> app.fonar.R.drawable.style_sketch
    else -> null
}

fun styleBrush(id: String): Brush = Brush.linearGradient(
    when (id) {
        // warm window light and muted film tones
        "aesthetic" -> listOf(Color(0xFFE7BC92), Color(0xFF8A6250), Color(0xFF2A1D18))
        "anime" -> listOf(Color(0xFFFFC6E5), Color(0xFFB9A6FF), Color(0xFF8FD3FF))
        "realism" -> listOf(Color(0xFFE2B48E), Color(0xFF7A4B33), Color(0xFF2A1A14))
        "painted" -> listOf(Color(0xFF1F4E5F), Color(0xFFC79A3A), Color(0xFF2B1B3D))
        "manhwa" -> listOf(Color(0xFFF2F2F2), Color(0xFF6B6B6B), Color(0xFF0D0D0D))
        else -> listOf(Color(0xFFE9D8B4), Color(0xFFA6875A), Color(0xFF4A3A26))
    },
)

/** All styles visible at once, three per row; the chosen one has a pink frame. */
@Composable
fun StyleGrid(
    styles: List<AvatarStyle>,
    selected: String,
    onSelect: (String) -> Unit,
    tagPrefix: String = "style_",
    enabled: Boolean = true,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        styles.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEach { st ->
                    val on = st.id == selected
                    val frame by androidx.compose.animation.core.animateDpAsState(if (on) 3.dp else 1.dp, label = "frame")
                    Column(
                        Modifier.weight(1f).clip(RoundedCornerShape(14.dp))
                            .clickable(enabled = enabled) { onSelect(st.id) }
                            .testTag(tagPrefix + st.id),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Box(
                            Modifier.fillMaxWidth().aspectRatio(2f / 3f).clip(RoundedCornerShape(14.dp)).background(styleBrush(st.id))
                                .border(frame, if (on) Fonar.Lamp else Fonar.SurfaceHigher, RoundedCornerShape(14.dp)),
                        ) {
                            stylePreview(st.id)?.let { res ->
                                androidx.compose.foundation.Image(
                                    painterResource(res), contentDescription = st.label, contentScale = ContentScale.Crop,
                                    modifier = Modifier.fillMaxSize().clip(RoundedCornerShape(14.dp)),
                                )
                            }
                        }
                        Text(st.label, style = MaterialTheme.typography.labelSmall, maxLines = 1, overflow = TextOverflow.Ellipsis,
                            color = if (on) Fonar.Lamp else Fonar.Muted, modifier = Modifier.padding(top = 4.dp))
                    }
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}
