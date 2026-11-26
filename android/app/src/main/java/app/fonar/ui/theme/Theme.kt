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

/** GramSoul palette, iOS-26-like: pure black, system greys, a soft pink accent with a light glow. */
object Fonar {
    val Night = Color(0xFF000000)          // background: pure black
    val Surface = Color(0xFF1C1C1E)        // grouped surfaces (iOS secondarySystemBackground)
    val SurfaceHigh = Color(0xFF2C2C2E)
    val SurfaceHigher = Color(0xFF3A3A3C)
    val Lamp = Color(0xFFFF8CC6)           // accent: soft pink
    val LampSoft = Color(0xFFFFC1DF)
    val OnLamp = Color(0xFF240816)
    val Sea = Color(0xFFC8B4FF)            // secondary: soft lilac
    val Text = Color(0xFFFFFFFF)
    val Muted = Color(0xFFA1A1A8)          // secondary label
    val Faint = Color(0xFF636366)          // tertiary label
    val Error = Color(0xFFFF6961)
    val MyBubble = Color(0xFF4A1C35)       // pink-tinted
    val FriendBubble = Color(0xFF25213A)   // lilac-tinted
    val CharBubble = Color(0xFF1C1C1E)
    val NarratorBg = Color(0xFF0E0E10)
    val Action = Color(0xFFF5B3D4)
    val Glow = Color(0xFFFF8CC6)
}

private val scheme = darkColorScheme(
    primary = Fonar.Lamp,
    onPrimary = Fonar.OnLamp,
    primaryContainer = Color(0xFF4A1C35),
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
    outline = Color(0xFF3A3A3C),
    outlineVariant = Color(0xFF2C2C2E),
    error = Fonar.Error,
    onError = Color(0xFF2A0703),
)

val Serif = FontFamily.Serif

// iOS-like type: bold large titles with tight tracking, 17sp-ish body
private val typography = Typography().let { t ->
    t.copy(
        headlineLarge = t.headlineLarge.copy(fontWeight = FontWeight.Bold, fontSize = 34.sp, lineHeight = 41.sp, letterSpacing = (-0.4).sp),
        headlineMedium = t.headlineMedium.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.3).sp),
        headlineSmall = t.headlineSmall.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.2).sp),
        titleLarge = t.titleLarge.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.2).sp),
        titleMedium = t.titleMedium.copy(fontWeight = FontWeight.SemiBold, fontSize = 17.sp),
        bodyLarge = t.bodyLarge.copy(fontSize = 16.5.sp, lineHeight = 23.sp, letterSpacing = 0.sp),
        bodyMedium = t.bodyMedium.copy(fontSize = 15.sp, lineHeight = 21.sp, letterSpacing = 0.sp),
        labelLarge = t.labelLarge.copy(fontWeight = FontWeight.SemiBold, letterSpacing = 0.sp),
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
            extraSmall = RoundedCornerShape(10.dp),
            small = RoundedCornerShape(14.dp),
            medium = RoundedCornerShape(20.dp),
            large = RoundedCornerShape(26.dp),
            extraLarge = RoundedCornerShape(32.dp),
        ),
        content = content,
    )
}
