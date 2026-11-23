package app.fonar

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import app.fonar.data.SessionStore
import app.fonar.ui.card.CharacterCardScreen
import app.fonar.ui.chat.ChatScreen
import app.fonar.ui.editor.QuickCreateScreen
import app.fonar.ui.editor.StoryEditorScreen
import app.fonar.ui.home.HomeScreen
import app.fonar.ui.register.RegisterScreen
import app.fonar.ui.register.SessionLostScreen
import app.fonar.ui.theme.Fonar
import app.fonar.ui.theme.FonarTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Fonar.Night.toArgb()),
        )
        super.onCreate(savedInstanceState)
        setContent { FonarRoot() }
    }
}

object Routes {
    const val REGISTER = "register"
    const val LOST = "lost"
    const val HOME = "home"
    const val QUICK = "quick"
    const val EDITOR = "editor?storyId={storyId}&draftId={draftId}"
    const val CHAT = "chat/{roomId}"
    const val CARD = "card/{roomId}/{charId}"

    fun editor(storyId: String? = null, draftId: String? = null) =
        "editor?storyId=${storyId ?: ""}&draftId=${draftId ?: ""}"

    fun chat(roomId: String) = "chat/$roomId"
    fun card(roomId: String, charId: String) = "card/$roomId/$charId"
}

@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun FonarRoot() {
    val graph = LocalContext.current.graph
    val session by graph.session.collectAsStateWithLifecycle()
    FonarTheme {
        val nav = rememberNavController()
        fun routeFor(s: SessionStore.State) = when (s) {
            is SessionStore.State.Active -> Routes.HOME
            is SessionStore.State.Lost -> Routes.LOST
            SessionStore.State.None -> Routes.REGISTER
        }
        val start = remember { routeFor(session) }
        // react to session changes (registered / lost / started over)
        LaunchedEffect(session) {
            val target = routeFor(session)
            val current = nav.currentDestination?.route
            val onAuthScreens = current == Routes.REGISTER || current == Routes.LOST
            val needsSwitch = when (session) {
                is SessionStore.State.Active -> onAuthScreens
                else -> current != target
            }
            if (current != null && needsSwitch) {
                nav.navigate(target) { popUpTo(0) { inclusive = true } }
            }
        }
        NavHost(
            navController = nav,
            startDestination = start,
            modifier = Modifier.fillMaxSize().background(Fonar.Night).semantics { testTagsAsResourceId = true },
        ) {
            composable(Routes.REGISTER) { RegisterScreen() }
            composable(Routes.LOST) { SessionLostScreen((session as? SessionStore.State.Lost)?.nick) }
            composable(Routes.HOME) { HomeScreen(nav) }
            composable(Routes.QUICK) { QuickCreateScreen(nav) }
            composable(
                Routes.EDITOR,
                arguments = listOf(
                    navArgument("storyId") { type = NavType.StringType; defaultValue = "" },
                    navArgument("draftId") { type = NavType.StringType; defaultValue = "" },
                ),
            ) { e ->
                StoryEditorScreen(
                    nav,
                    storyId = e.arguments?.getString("storyId")?.ifBlank { null },
                    draftId = e.arguments?.getString("draftId")?.ifBlank { null },
                )
            }
            composable(Routes.CHAT) { e -> ChatScreen(nav, e.arguments!!.getString("roomId")!!) }
            composable(Routes.CARD) { e ->
                CharacterCardScreen(nav, e.arguments!!.getString("roomId")!!, e.arguments!!.getString("charId")!!)
            }
        }
    }
}

fun NavHostController.openChat(roomId: String) {
    navigate(Routes.chat(roomId)) { launchSingleTop = true }
}
