package app.fonar.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AddAPhoto
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.fonar.ui.theme.Fonar
import coil3.compose.AsyncImage

/**
 * "*сажусь рядом* Ты чего?" → action in italics (slightly dimmed), speech as plain text.
 */
fun actionText(text: String, actionColor: Color = Fonar.Action): AnnotatedString = buildAnnotatedString {
    var i = 0
    while (i < text.length) {
        val start = text.indexOf('*', i)
        if (start < 0) {
            append(text.substring(i)); break
        }
        val end = text.indexOf('*', start + 1)
        if (end < 0) {
            append(text.substring(i)); break
        }
        append(text.substring(i, start))
        withStyle(SpanStyle(fontStyle = FontStyle.Italic, color = actionColor)) {
            append(text.substring(start + 1, end))
        }
        i = end + 1
    }
}

private val avatarColors = listOf(
    Color(0xFF8E6BBF), Color(0xFF4E9F8F), Color(0xFFC27B4A), Color(0xFF5A7EC2), Color(0xFFB45C7E), Color(0xFF7D9A4B),
)

@Composable
fun Avatar(
    name: String,
    imageUrl: String?,
    size: Dp = 40.dp,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
) {
    val color = avatarColors[(name.hashCode() and 0x7fffffff) % avatarColors.size]
    Box(
        modifier
            .size(size)
            .clip(CircleShape)
            .background(Brush.linearGradient(listOf(color, color.copy(alpha = 0.55f))))
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            name.trim().take(1).uppercase().ifEmpty { "?" },
            color = Color.White,
            fontWeight = FontWeight.SemiBold,
            fontSize = (size.value * 0.42f).sp,
        )
        if (imageUrl != null) {
            AsyncImage(
                model = imageUrl,
                contentDescription = name,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

@Composable
fun ImagePickBox(
    imageUrl: String?,
    label: String,
    uploading: Boolean,
    round: Boolean,
    size: Dp,
    onPick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val shape = if (round) CircleShape else RoundedCornerShape(16.dp)
    Box(
        modifier
            .then(if (round) Modifier.size(size) else Modifier.fillMaxWidth().height(size))
            .clip(shape)
            .background(Fonar.SurfaceHigh)
            .border(1.dp, Fonar.SurfaceHigher, shape)
            .clickable(onClick = onPick),
        contentAlignment = Alignment.Center,
    ) {
        if (imageUrl != null) {
            AsyncImage(model = imageUrl, contentDescription = label, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        } else {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Outlined.AddAPhoto, null, tint = Fonar.Muted)
                if (!round) Text(label, color = Fonar.Muted, style = MaterialTheme.typography.labelMedium)
            }
        }
        if (uploading) CircularProgressIndicator(Modifier.size(28.dp), strokeWidth = 3.dp)
    }
}

@Composable
fun Field(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    minLines: Int = 1,
    maxLines: Int = if (minLines > 1) 8 else 1,
    hint: String? = null,
    maxLength: Int = 1500,
    testTag: String? = null,
    counter: Boolean = false,
) {
    OutlinedTextField(
        value = value,
        onValueChange = { if (it.length <= maxLength) onChange(it) },
        label = { Text(label) },
        placeholder = hint?.let { { Text(it, color = Fonar.Faint) } },
        supportingText = if (counter) ({ Text("${value.length}/$maxLength", color = Fonar.Faint) }) else null,
        minLines = minLines,
        maxLines = maxLines,
        singleLine = minLines == 1 && maxLines == 1,
        modifier = modifier.fillMaxWidth().let { m -> if (testTag != null) m.testTag(testTag) else m },
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = Fonar.Surface,
            unfocusedContainerColor = Fonar.Surface,
        ),
    )
}

/** Dialogs and popups are separate windows: expose test tags there too (UI automation, accessibility tools). */
@OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
fun Modifier.exposeTags(): Modifier =
    this.then(Modifier.semantics { testTagsAsResourceId = true })

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text.uppercase(),
        style = MaterialTheme.typography.labelMedium.copy(letterSpacing = 1.2.sp),
        color = Fonar.Lamp.copy(alpha = 0.85f),
        modifier = modifier.padding(top = 18.dp, bottom = 8.dp),
    )
}

@Composable
fun CenterLoading(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
}

@Composable
fun ErrorBox(message: String, onRetry: (() -> Unit)?, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(Icons.Outlined.CloudOff, null, tint = Fonar.Muted, modifier = Modifier.size(36.dp))
        Text(message, color = Fonar.Muted, style = MaterialTheme.typography.bodyMedium)
        if (onRetry != null) TextButton(onClick = onRetry) { Text("Повторить") }
    }
}

@Composable
fun Pill(text: String, color: Color, modifier: Modifier = Modifier) {
    Surface(color = color.copy(alpha = 0.16f), shape = RoundedCornerShape(50), modifier = modifier) {
        Text(text, color = color, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
    }
}

@Composable
fun Banner(text: String, color: Color = Fonar.Lamp, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null) {
    Surface(color = color.copy(alpha = 0.12f), shape = RoundedCornerShape(14.dp), modifier = modifier.fillMaxWidth()) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(text, color = color, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
            action?.invoke()
        }
    }
}
