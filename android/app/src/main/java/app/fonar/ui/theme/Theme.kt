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

/** "Фонарь" palette: a night sea lit by a warm lantern. */
object Fonar {
    val Night = Color(0xFF0E0F1A)
    val Surface = Color(0xFF171A2B)
    val SurfaceHigh = Color(0xFF20243A)
    val SurfaceHigher = Color(0xFF2A2F49)
    val Lamp = Color(0xFFF2A541)
    val LampSoft = Color(0xFFFFD58A)
    val OnLamp = Color(0xFF1B1206)
    val Sea = Color(0xFF6FC7B8)
    val Text = Color(0xFFEDE7DA)
    val Muted = Color(0xFF9A97A8)
    val Faint = Color(0xFF5F5D70)
    val Error = Color(0xFFFF7A6B)
    val MyBubble = Color(0xFF2D2645)
    val FriendBubble = Color(0xFF1C2C33)
    val CharBubble = Color(0xFF1B1E31)
    val NarratorBg = Color(0xFF17141F)
    val Action = Color(0xFFCDB89A)
}

private val scheme = darkColorScheme(
    primary = Fonar.Lamp,
    onPrimary = Fonar.OnLamp,
    primaryContainer = Color(0xFF4A3414),
    onPrimaryContainer = Fonar.LampSoft,
    secondary = Fonar.Sea,
    onSecondary = Color(0xFF06201C),
    secondaryContainer = Color(0xFF173A35),
    onSecondaryContainer = Color(0xFFBDEDE4),
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
    outline = Color(0xFF3B3F5A),
    outlineVariant = Color(0xFF2B2F47),
    error = Fonar.Error,
    onError = Color(0xFF2A0703),
)

val Serif = FontFamily.Serif

private val typography = Typography().let { t ->
    t.copy(
        headlineLarge = t.headlineLarge.copy(fontFamily = Serif, fontWeight = FontWeight.SemiBold),
        headlineMedium = t.headlineMedium.copy(fontFamily = Serif, fontWeight = FontWeight.SemiBold),
        headlineSmall = t.headlineSmall.copy(fontFamily = Serif, fontWeight = FontWeight.SemiBold),
        titleLarge = t.titleLarge.copy(fontFamily = Serif, fontWeight = FontWeight.SemiBold),
        bodyLarge = t.bodyLarge.copy(fontSize = 16.sp, lineHeight = 23.sp),
        bodyMedium = t.bodyMedium.copy(fontSize = 15.sp, lineHeight = 21.sp),
    )
}

val NarratorStyle = TextStyle(fontFamily = Serif, fontSize = 16.sp, lineHeight = 24.sp, color = Color(0xFFE4D8C2))

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
