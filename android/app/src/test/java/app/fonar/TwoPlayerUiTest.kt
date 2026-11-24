package app.fonar

import android.content.Context
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.longClick
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.fonar.data.CharacterPatch
import app.fonar.data.SessionStore
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.util.UUID

/**
 * Drives the real UI against a running backend (FONAR_TEST_BACKEND=http://127.0.0.1:8001).
 * Each test is one fresh install; the other phone is played through the API.
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
@Config(sdk = [35], qualifiers = "w360dp-h740dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class TwoPlayerUiTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private val backend = System.getProperty("fonar.backend").orEmpty()
    private lateinit var app: FonarApp

    @Before
    fun setUp() {
        assumeTrue("set FONAR_TEST_BACKEND to run UI flow tests", backend.isNotEmpty())
        app = ApplicationProvider.getApplicationContext<Context>() as FonarApp
        app.resetForTests(backend)
    }

    private var failShot = 0
    private fun <T> orShot(name: String, block: () -> T): T = try {
        block()
    } catch (e: Throwable) {
        runCatching { shot("fail_${++failShot}_" + name.replace(Regex("[^A-Za-z0-9_]"), "_")) }
        throw e
    }

    private fun ComposeTestRule.waitTag(tag: String, timeout: Long = 20_000) = orShot(tag) {
        waitUntil(timeout) { onAllNodesWithTag(tag, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
    }

    private fun ComposeTestRule.waitText(text: String, timeout: Long = 20_000, substring: Boolean = true) = orShot("text") {
        waitUntil(timeout) { onAllNodesWithText(text, substring = substring, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
    }

    /** Server-side count of AI reactions that are visible (the list itself is lazy). */
    private fun reactions(api: app.fonar.data.Api, roomId: String): Int = kotlinx.coroutines.runBlocking {
        api.sync(roomId, 0, -1, 0).messages.filter { !it.hidden && it.kind == "narrator" && it.text.contains("Ответ №") }.size
    }

    private fun shot(name: String) = compose.onRoot().captureRoboImage("build/screens/$name.png")

    private fun register(nick: String) {
        compose.waitTag("nick_input")
        shot("01_register")
        compose.onNodeWithTag("nick_input").performTextInput(nick)
        compose.onNodeWithTag("start_button").performClick()
        compose.waitTag("my_nick")
        compose.waitTag("stories_list")
    }

    @Test
    fun registrationErrorsAndTakenNick() {
        val taken = uniq("Mira")
        RemotePlayer(backend, taken)
        ActivityScenario.launch(MainActivity::class.java).use {
            compose.waitTag("nick_input")
            compose.onNodeWithTag("nick_input").performTextInput("ab cd")
            compose.waitText("пробелов")
            compose.onNodeWithTag("nick_input").performTextReplacement(taken.lowercase())
            compose.onNodeWithTag("start_button").performClick()
            compose.waitText("Ник занят")
            shot("02_register_taken")
            // the taken nick did not log us in
            assertTrue(app.graph.session.value is SessionStore.State.None)
            val mine = uniq("Ёжик")
            compose.onNodeWithTag("nick_input").performTextReplacement(mine)
            compose.onNodeWithTag("start_button").performClick()
            compose.waitTag("my_nick")
            assertEquals(mine, (app.graph.session.value as SessionStore.State.Active).session.nick)
        }
        // relaunch: automatic login from the stored session
        ActivityScenario.launch(MainActivity::class.java).use {
            compose.waitTag("my_nick")
        }
    }

    /** A new phone signs into an existing nick with a one-time transfer code; profile and people search. */
    @Test
    fun transferCodeProfileAndSearch() {
        val nick = uniq("Mira.k")
        val old = RemotePlayer(backend, nick)
        val other = RemotePlayer(backend, uniq("Kirill"))
        other.call { setAbout("Играю за мага") }
        val code = old.call { transferCode() }.code
        ActivityScenario.launch(MainActivity::class.java).use {
            compose.waitTag("nick_input")
            compose.onNodeWithTag("transfer_toggle").performClick()
            compose.waitTag("transfer_code_input")
            compose.onNodeWithTag("nick_input").performTextInput(nick.uppercase())
            compose.onNodeWithTag("transfer_code_input").performTextInput("WRONG-CODE")
            compose.onNodeWithTag("start_button").performClick()
            compose.waitText("Неверный ник или код")
            compose.onNodeWithTag("transfer_code_input").performTextReplacement(code)
            shot("02b_transfer_login")
            compose.onNodeWithTag("start_button").performClick()
            compose.waitTag("my_nick")
            val s = (app.graph.session.value as SessionStore.State.Active).session
            assertEquals(nick, s.nick)
            assertEquals(old.user.id, s.userId)

            // profile: about + a new transfer code
            compose.onNodeWithTag("profile_button").performClick()
            compose.waitTag("profile_nick")
            compose.waitUntil(10_000) { compose.onAllNodesWithText(nick, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithTag("about_input").performTextInput("Люблю маяки")
            compose.onNodeWithTag("about_save").performClick()
            compose.waitUntil(10_000) { old.call { me() }.user.about == "Люблю маяки" }
            compose.onNodeWithTag("transfer_code_button").performClick()
            compose.waitTag("transfer_code")
            shot("05b_profile")
            compose.onNodeWithTag("back").performClick()

            // people search by a part of the nick
            compose.waitTag("tab_friends")
            compose.onNodeWithTag("tab_friends").performClick()
            compose.onNodeWithTag("friend_search_input").performTextInput(other.user.nick.drop(2).lowercase())
            compose.waitTag("search_result_${other.user.nick}")
            compose.waitText("Играю за мага")
            shot("05c_people_search")
            compose.onNodeWithTag("add_friend_${other.user.nick}").performClick()
            compose.waitTag("request_sent_${other.user.nick}")
        }
    }

    /** Personal chat: greeting first, a streamed reply, three suggestions, edit by long press, regenerate. */
    @Test
    fun personalChatWithCharacter() {
        ActivityScenario.launch(MainActivity::class.java).use {
            register(uniq("Mira"))
            compose.onNodeWithTag("tab_characters").performClick()
            compose.waitTag("persona_card_Вера Солнцева")
            compose.onNodeWithTag("persona_card_Вера Солнцева").performClick()
            compose.waitTag("persona_chat_new")
            compose.onNodeWithTag("persona_chat_new").performClick()
            compose.waitTag("chat_input")
            compose.waitText("Личный чат")
            compose.waitText("стеклянную дверь")  // the character's first message
            shot("30_chat_greeting")
            compose.onNodeWithTag("chat_input").performTextInput("*снимаю шляпу* Добрый вечер")
            compose.onNodeWithTag("send_button").performClick()
            compose.waitText("Ответ №", 30_000)
            compose.waitUntil(20_000) {
                compose.onAllNodesWithTag("regenerate_button").fetchSemanticsNodes().firstOrNull()
                    ?.config?.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.Disabled) == null
            }
            // three options for my next turn; picking one fills the input
            compose.onNodeWithTag("suggest_button").performClick()
            compose.waitTag("suggestion_2")
            shot("31_suggestions")
            compose.onNodeWithTag("suggestion_1").performClick()
            compose.waitText("Кто ты такой?")
            // fix my own line by a long press
            compose.onAllNodesWithText("Добрый вечер", substring = true, useUnmergedTree = true)[0].performTouchInput { longClick() }
            compose.waitTag("edit_panel")
            compose.onNodeWithTag("edit_input").performTextReplacement("*снимаю шляпу* Доброй ночи")
            compose.onNodeWithTag("edit_save").performClick()
            compose.waitText("Доброй ночи")
            compose.waitText("изменено")
            shot("32_edited")
            // regenerate the character's reply
            val before = compose.onAllNodesWithText("Ответ №", substring = true, useUnmergedTree = true).fetchSemanticsNodes()
                .map { it.config.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.Text)?.joinToString() }
            compose.onNodeWithTag("regenerate_button").performClick()
            compose.waitUntil(30_000) {
                val now = compose.onAllNodesWithText("Ответ №", substring = true, useUnmergedTree = true).fetchSemanticsNodes()
                    .map { it.config.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.Text)?.joinToString() }
                now.isNotEmpty() && now != before
            }
            // the avatar opens the character's page
            compose.onAllNodesWithTag("avatar_Вера Солнцева", useUnmergedTree = true)[0].performClick()
            compose.waitTag("persona_view")
            compose.waitTag("persona_chat_continue")
        }
    }

    /** Characters: demo list, AI fill from an idea, AI avatar in a chosen style, publish; others see it. */
    @Test
    fun createPersonaWithAiAndPublish() {
        val other = RemotePlayer(backend, uniq("Kira"))
        ActivityScenario.launch(MainActivity::class.java).use {
            compose.waitTag("app_version")  // version on the login screen
            val me = uniq("Mira")
            register(me)
            compose.onNodeWithTag("tab_characters").performClick()
            compose.waitTag("persona_card_Вера Солнцева")
            shot("20_personas")
            compose.onNodeWithTag("create_persona").performClick()
            compose.waitTag("fill_idea")
            compose.onNodeWithTag("fill_idea").performTextInput("хозяйка маяка с секретом")
            compose.onNodeWithTag("fill_button").performClick()
            compose.waitText("Ветта")
            compose.waitText("Опоздал")
            // AI avatar: description is taken from the card, pick a style, generate, use
            compose.onNodeWithTag("avatar_tile").performClick()
            compose.waitTag("avatar_dialog")
            compose.onNodeWithTag("style_manhwa", useUnmergedTree = true).performClick()
            compose.waitForIdle()
            compose.onNodeWithText("Манхва", useUnmergedTree = true).assertExists()
            shot("21a_avatar_styles")
            compose.onNodeWithTag("avatar_generate", useUnmergedTree = true).performClick()
            compose.waitTag("avatar_result")
            shot("21_avatar_ai")
            compose.onNodeWithTag("avatar_use", useUnmergedTree = true).performClick()
            compose.onNodeWithTag("visibility_public").performScrollTo().performClick()
            shot("22_persona_editor")
            compose.onNodeWithTag("publish").performScrollTo().performClick()
            compose.waitTag("persona_view")
            compose.waitTag("persona_avatar")
            compose.waitText("Твой персонаж")
            shot("23_persona_view")
            // another player finds the published character by name, without the hidden fields
            val seen = other.call { personas("ветта") }.personas.single { it.author?.nick == me }
            assertEquals("Ветта", seen.name)
            assertTrue(seen.personality == null && seen.avatar_image_id != null)
            compose.onNodeWithTag("back").performClick()
            compose.waitTag("persona_card_Ветта")
            // version in the profile
            compose.onNodeWithTag("profile_button").performClick()
            compose.waitTag("app_version")
        }
    }

    /** Phone A (UI): finds B by nick, sends a request, invites B, plays, edits a card, regenerates. */
    @Test
    fun ownerFlow() {
        val nickA = uniq("Mira")
        val b = RemotePlayer(backend, uniq("Лев"))
        ActivityScenario.launch(MainActivity::class.java).use {
            register(nickA)
            shot("03_home_stories")
            compose.onNodeWithTag("tab_friends").performClick()
            compose.onNodeWithTag("friend_search_input").performTextInput(b.user.nick.uppercase())
            compose.onNodeWithTag("friend_search_button").performClick()
            compose.waitTag("add_friend_${b.user.nick}")
            compose.onNodeWithTag("add_friend_${b.user.nick}").performClick()
            compose.waitTag("request_sent_${b.user.nick}")
            compose.waitTag("outgoing_${b.user.nick}")
            shot("04_friends_sent")
            // B accepts on the other phone
            val req = b.call { friends() }.incoming.single()
            b.call { acceptFriend(req.id) }
            compose.waitTag("friend_${b.user.nick}", 30_000)
            compose.waitText("принята")
            // B has just been active → shown online
            compose.waitTag("online_${b.user.nick}")
            // "Играть с другом" on the demo story
            compose.onNodeWithTag("tab_stories").performClick()
            compose.waitTag("play_friend_Маяк на Стеклянном берегу")
            compose.onNodeWithTag("play_friend_Маяк на Стеклянном берегу").performClick()
            compose.waitTag("pick_${b.user.nick}")
            compose.onNodeWithTag("pick_${b.user.nick}").performClick()
            compose.onNodeWithTag("invite_confirm").performClick()
            compose.waitTag("chat_list")
            compose.waitText("ждём ${b.user.nick}")
            // B accepts the invite
            val inv = b.call { rooms() }.invites.single()
            b.call { acceptInvite(inv.id) }
            compose.waitText("Лада — ${b.user.nick}", 30_000)
            // A acts
            compose.onNodeWithTag("chat_input").performTextInput("*сажусь рядом и беру её за руку* Ты чего притихла?")
            compose.onNodeWithTag("send_button").performClick()
            compose.waitText("Ответ №", 30_000)
            shot("05_chat_reaction")
            val roomId = inv.room_id!!
            // B sees exactly the same messages
            val mine = kotlinx.coroutines.runBlocking { appApi(app, backend).sync(roomId, 0, -1, 0) }.messages.filter { !it.hidden }.map { it.id }
            val theirs = b.call { sync(roomId, 0, -1, 0) }.messages.filter { !it.hidden }.map { it.id }
            assertEquals(mine, theirs)
            // B writes from the other phone → appears here
            b.call { postMessage(roomId, UUID.randomUUID().toString(), "*щёлкает зажигалкой* Я с вами.") }
            compose.waitText("щёлкает зажигалкой", 30_000)
            compose.waitUntil(30_000) { b.call { sync(roomId, 0, -1, 0) }.generation?.status == "done" }
            // open Iva's card from the chat, edit, return to the scene
            compose.onNodeWithTag("chat_list").performScrollToNode(hasTestTag("name_Ива"))
            compose.onAllNodesWithTag("name_Ива", useUnmergedTree = true)[0].performClick()
            compose.waitTag("char_personality")
            shot("06_card_edit")
            compose.onNodeWithTag("char_personality").performTextReplacement("Дерзкая и насмешливая, обожает подшучивать.")
            compose.onNodeWithTag("card_save").performClick()
            compose.waitTag("chat_input")
            // next request to the model contains the edit
            compose.onNodeWithTag("chat_input").performTextInput("Ива, ты как?")
            compose.onNodeWithTag("send_button").performClick()
            compose.waitUntil(30_000) {
                runCatching { b.call { lastPrompt(roomId) } }.getOrNull()?.prompt?.contains("Дерзкая и насмешливая") == true &&
                    b.call { sync(roomId, 0, -1, 0) }.generation?.status == "done"
            }
            // regenerate the last reaction
            compose.waitUntil(20_000) { compose.onNodeWithTag("regenerate_button").fetchSemanticsNode().config.contains(
                androidx.compose.ui.semantics.SemanticsProperties.Disabled).not() }
            val before = b.call { sync(roomId, 0, -1, 0) }.messages.filter { !it.hidden && it.generation_id != null }.last().generation_id
            compose.onNodeWithTag("regenerate_button").performClick()
            compose.waitUntil(30_000) {
                val s = b.call { sync(roomId, 0, -1, 0) }
                s.generation?.kind == "regenerate" && s.generation?.status == "done"
            }
            val after = b.call { sync(roomId, 0, -1, 0) }.messages.filter { !it.hidden && it.generation_id != null }.last().generation_id
            assertTrue(before != after)
            compose.waitUntil(20_000) {
                val visible = kotlinx.coroutines.runBlocking { appApi(app, backend).sync(roomId, 0, -1, 0) }.messages.filter { !it.hidden }.map { it.id }
                visible == b.call { sync(roomId, 0, -1, 0) }.messages.filter { !it.hidden }.map { it.id }
            }
            shot("07_chat_after_regenerate")
            // AI mode: the owner switches the scene to the local model (the test backend has cloud enabled)
            compose.onNodeWithTag("ai_mode").performClick()
            compose.waitTag("mode_local")
            shot("07a_ai_mode")
            compose.onNodeWithTag("mode_local").performClick()
            compose.onNodeWithTag("mode_apply").performClick()
            compose.waitUntil(20_000) { b.call { room(roomId) }.room.ai_mode == "local" }
            // scene photo: drawn by the image model and shown to both players
            compose.onNodeWithTag("photo_button").performClick()
            compose.waitTag("photo_confirm")
            compose.onNodeWithTag("photo_prompt").performTextInput("маяк в тумане")
            shot("07c_photo_panel")
            compose.onNodeWithTag("photo_confirm").performClick()
            compose.waitTag("msg_photo", 30_000)
            assertTrue(b.call { sync(roomId, 0, -1, 0) }.messages.any { it.image_id != null && it.text == "маяк в тумане" })
            shot("07b_photo")
            // failure keeps the turn and offers a retry
            compose.onNodeWithTag("chat_input").performTextInput("Проверка ошибки #fail")
            compose.onNodeWithTag("send_button").performClick()
            compose.waitTag("retry_button", 30_000)
            shot("08_chat_failed")
            compose.waitText("Проверка ошибки #fail")
        }
    }

    /** Phone B (UI): gets a friend request and a game invite, accepts both and plays. */
    @Test
    fun guestFlow() {
        val nickB = uniq("Лев")
        val a = RemotePlayer(backend, uniq("Mira"))
        ActivityScenario.launch(MainActivity::class.java).use {
            register(nickB)
            a.call { sendFriendRequest(nickB.lowercase()) }
            compose.onNodeWithTag("tab_friends").performClick()
            compose.waitTag("incoming_${a.user.nick}", 30_000)
            shot("09_friends_incoming")
            compose.onNodeWithTag("accept_${a.user.nick}").performClick()
            compose.waitTag("friend_${a.user.nick}")
            // A starts a scene and invites B
            val demo = a.call { stories() }.stories.first { it.is_demo }
            val room = a.call { createRoom(demo.id!!) }.room
            a.call { invite(room.id, (app.graph.me)!!.id) }
            compose.onNodeWithTag("tab_scenes").performClick()
            compose.waitTag("invite_card", 30_000)
            shot("10_invite")
            compose.onNodeWithTag("invite_accept").performClick()
            compose.waitTag("chat_input")
            compose.waitText("присоединяется")
            a.call { postMessage(room.id, UUID.randomUUID().toString(), "*зажигает фонарь* Начнём.") }
            compose.waitText("зажигает фонарь", 30_000)
            compose.waitText("Ответ №", 30_000)
            compose.onNodeWithTag("chat_input").performTextInput("*подхожу к линзе* Дай-ка я.")
            compose.onNodeWithTag("send_button").performClick()
            orShot("guest_second") { compose.waitUntil(30_000) { reactions(appApi(app, backend), room.id) >= 2 } }
            compose.waitText("Ответ №", 30_000)
            // guest sees cards read-only
            compose.onNodeWithTag("chat_list").performScrollToNode(hasTestTag("name_Ива"))
            compose.onAllNodesWithTag("name_Ива", useUnmergedTree = true)[0].performClick()
            compose.waitText("Менять карточку может только хозяин")
            shot("11_card_readonly")
        }
    }

    /** A long scene on a small screen with the keyboard area taken away. */
    @Test
    @Config(qualifiers = "w320dp-h480dp-xhdpi")
    fun longSceneOnSmallScreen() {
        val nick = uniq("Tim")
        ActivityScenario.launch(MainActivity::class.java).use {
            register(nick)
            compose.onNodeWithTag("play_Маяк на Стеклянном берегу").performClick()
            compose.waitTag("chat_input")
            repeat(3) { i ->
                compose.onNodeWithTag("chat_input").performTextInput(
                    "*долго смотрю на туман, потом медленно поднимаю фонарь над головой и делаю шаг к лестнице* " +
                        "Ход номер $i. Если мы не зажжём линзу до третьего удара, туман поднимется к деревне, и тогда уже никто не поможет."
                )
                compose.onNodeWithTag("send_button").performClick()
                val roomId = kotlinx.coroutines.runBlocking { appApi(app, backend).rooms() }.rooms.first().id
                orShot("long_$i") { compose.waitUntil(30_000) { reactions(appApi(app, backend), roomId) > i } }
            }
            compose.onNodeWithTag("chat_input").performTextInput("Длинный черновик реплики, который занимает несколько строк в поле ввода и не должен закрывать кнопки")
            shot("12_small_screen_long_scene")
        }
    }

    @Test
    fun lostSessionIsExplained() {
        val nick = uniq("Lost")
        ActivityScenario.launch(MainActivity::class.java).use {
            register(nick)
        }
        // simulate server-side loss of the session: wipe tokens on the server is not possible from here,
        // so corrupt the stored ciphertext instead (as after a restore to another phone)
        app.getSharedPreferences("fonar_session", Context.MODE_PRIVATE).edit().putString("token_ct", "garbage").commit()
        app.resetForTestsKeepPrefs(backend)
        ActivityScenario.launch(MainActivity::class.java).use {
            compose.waitTag("start_over")
            compose.waitText("Сессия потеряна")
            compose.waitText(nick)
            shot("13_session_lost")
        }
    }
}
