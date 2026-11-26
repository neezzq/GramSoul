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
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
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
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import app.fonar.ui.theme.Fonar
import coil3.compose.AsyncImage

/**
 * "*сажусь рядом* Ты чего?" → action in italics (slightly dimmed), speech as plain text.
 * paragraphs = true puts every action and every spoken part on its own line
 * (how AI replies read best: "*усмехается*" / "— Молчу…" / "*кивает на парня*" / "— А ты кто?").
 */
fun actionText(text: String, actionColor: Color = Fonar.Action, paragraphs: Boolean = false): AnnotatedString =
    if (paragraphs) actionParagraphs(text, actionColor) else actionInline(text, actionColor)

private fun actionParagraphs(text: String, actionColor: Color): AnnotatedString = buildAnnotatedString {
    // split into (isAction, part) keeping the model's own line breaks
    val parts = mutableListOf<Pair<Boolean, String>>()
    var i = 0
    while (i < text.length) {
        val start = text.indexOf('*', i)
        val end = if (start >= 0) text.indexOf('*', start + 1) else -1
        if (start < 0 || end < 0) { parts += false to text.substring(i); break }
        parts += false to text.substring(i, start)
        parts += true to text.substring(start + 1, end)
        i = end + 1
    }
    var first = true
    for ((isAction, raw) in parts) {
        for (piece in raw.split('\n')) {
            val t = piece.trim()
            if (t.isEmpty() || t.all { it in ".,;:!?—–-" }) continue
            if (!first) append("\n")
            first = false
            if (isAction) withStyle(SpanStyle(fontStyle = FontStyle.Italic, color = actionColor)) { append(t) } else append(t)
        }
    }
}

private fun actionInline(text: String, actionColor: Color): AnnotatedString = buildAnnotatedString {
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
        colors = app.fonar.ui.components.glassFieldColors(Fonar.Surface),
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


// ---------------------------------------------------------------- iOS-26-like surfaces

/** A soft coloured halo around an opaque element (buttons, the send button, the active tab). */
fun Modifier.glow(
    color: Color = Fonar.Glow,
    radius: Dp = 14.dp,
    alpha: Float = 0.45f,
    corner: Dp = 999.dp,
): Modifier = this.drawBehind {
    val r = radius.toPx()
    val c = minOf(corner.toPx(), size.minDimension / 2f)
    drawIntoCanvas { canvas ->
        val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
            this.color = color.copy(alpha = alpha).toArgb()
            setShadowLayer(r, 0f, 0f, color.copy(alpha = alpha).toArgb())
        }
        canvas.nativeCanvas.drawRoundRect(0f, 0f, size.width, size.height, c, c, paint)
    }
}

/** Frosted-glass panel: a light vertical sheen and a hairline highlight on the edge. */
fun Modifier.glass(shape: androidx.compose.ui.graphics.Shape = RoundedCornerShape(28.dp), strength: Float = 1f): Modifier =
    this.clip(shape)
        .background(Brush.verticalGradient(listOf(Color.White.copy(alpha = 0.13f * strength), Color.White.copy(alpha = 0.06f * strength))))
        .border(0.8.dp, Brush.verticalGradient(listOf(Color.White.copy(alpha = 0.30f), Color.White.copy(alpha = 0.06f))), shape)

/** Text fields as filled rounded wells (no heavy outline), pink when focused. */
@Composable
fun glassFieldColors(container: Color = Fonar.Surface) = OutlinedTextFieldDefaults.colors(
    focusedContainerColor = container,
    unfocusedContainerColor = container,
    disabledContainerColor = container,
    focusedBorderColor = Fonar.Lamp.copy(alpha = 0.75f),
    unfocusedBorderColor = Color.White.copy(alpha = 0.08f),
    cursorColor = Fonar.Lamp,
    focusedLabelColor = Fonar.Lamp,
)

/** iOS-like segmented control: a glass capsule with the chosen option as a pink pill. */
@Composable
fun Segmented(options: List<String>, selected: Int, onSelect: (Int) -> Unit, tags: List<String> = emptyList(), modifier: Modifier = Modifier) {
    androidx.compose.foundation.layout.Row(
        modifier.fillMaxWidth().glass(RoundedCornerShape(999.dp)).padding(4.dp),
    ) {
        options.forEachIndexed { i, label ->
            val on = i == selected
            val bg by androidx.compose.animation.animateColorAsState(if (on) Fonar.Lamp else Color.Transparent,
                androidx.compose.animation.core.tween(220), label = "segment")
            val fg by androidx.compose.animation.animateColorAsState(if (on) Fonar.OnLamp else Fonar.Muted,
                androidx.compose.animation.core.tween(220), label = "segmentText")
            Box(
                Modifier.weight(1f).height(40.dp).clip(RoundedCornerShape(999.dp))
                    .background(bg)
                    .clickable { onSelect(i) }
                    .then(tags.getOrNull(i)?.let { Modifier.testTag(it) } ?: Modifier)
                    .semantics { this.selected = on },
                contentAlignment = Alignment.Center,
            ) {
                Text(label, color = fg, style = MaterialTheme.typography.titleSmall)
            }
        }
    }
}
