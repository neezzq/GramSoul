package app.fonar.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** GramSoul palette: deep black with hot-pink neon. */
object Fonar {
    val Night = Color(0xFF0A090C)
    val Surface = Color(0xFF151117)
    val SurfaceHigh = Color(0xFF1F1922)
    val SurfaceHigher = Color(0xFF2A2230)
    val Lamp = Color(0xFFFF4FA3)       // primary hot pink
    val LampSoft = Color(0xFFFF9BCB)   // light pink
    val OnLamp = Color(0xFF1A0710)
    val Sea = Color(0xFFC9A2FF)        // secondary lilac
    val Text = Color(0xFFF4E9F0)
    val Muted = Color(0xFFA796A3)
    val Faint = Color(0xFF66586A)
    val Error = Color(0xFFFF6B6B)
    val MyBubble = Color(0xFF3A1430)
    val FriendBubble = Color(0xFF241A33)
    val CharBubble = Color(0xFF1A1520)
    val NarratorBg = Color(0xFF140F16)
    val Action = Color(0xFFE6A8C8)
}

private val scheme = darkColorScheme(
    primary = Fonar.Lamp,
    onPrimary = Fonar.OnLamp,
    primaryContainer = Color(0xFF4A1034),
    onPrimaryContainer = Fonar.LampSoft,
    secondary = Fonar.Sea,
    onSecondary = Color(0xFF1C0B33),
    secondaryContainer = Color(0xFF2E1D47),
    onSecondaryContainer = Color(0xFFE8DAFF),
    background = Fonar.Night,
    onBackground = Fonar.Text,
    surface = Fonar.Night,
    onSurface = Fonar.Text,
    surfaceVariant = Fonar.SurfaceHigh,
    onSurfaceVariant = Fonar.Muted,
    surfaceContainerLowest = Fonar.Night,
    surfaceContainerLow = Fonar.Surface,
    surfaceContainer = Fonar.Surface,
    surfaceContainerHigh = Fonar.SurfaceHigh,
    surfaceContainerHighest = Fonar.SurfaceHigher,
    outline = Color(0xFF4A3A4E),
    outlineVariant = Color(0xFF2E2432),
    error = Fonar.Error,
    onError = Color(0xFF2A0703),
)

val Serif = FontFamily.Serif

private val typography = Typography().let { t ->
    t.copy(
        headlineLarge = t.headlineLarge.copy(fontWeight = FontWeight.ExtraBold),
        headlineMedium = t.headlineMedium.copy(fontWeight = FontWeight.Bold),
        headlineSmall = t.headlineSmall.copy(fontWeight = FontWeight.Bold),
        titleLarge = t.titleLarge.copy(fontWeight = FontWeight.Bold),
        bodyLarge = t.bodyLarge.copy(fontSize = 16.sp, lineHeight = 23.sp),
        bodyMedium = t.bodyMedium.copy(fontSize = 15.sp, lineHeight = 21.sp),
    )
}

/** Narration reads like stage directions: light italic, not a heavy block (and the same sans font as the rest). */
val NarratorStyle = TextStyle(fontSize = 15.sp, lineHeight = 22.sp, fontStyle = androidx.compose.ui.text.font.FontStyle.Italic,
    color = Color(0xFFB9AAB4))

@Composable
fun FonarTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = scheme,
        typography = typography,
        shapes = Shapes(
            small = RoundedCornerShape(10.dp),
            medium = RoundedCornerShape(16.dp),
            large = RoundedCornerShape(22.dp),
        ),
        content = content,
    )
}
