package app.fonar

import app.fonar.data.Api
import app.fonar.data.UserDto
import kotlinx.coroutines.runBlocking

/** A second "phone" driven through the public API only (same endpoints the app uses). */
class RemotePlayer(base: String, nick: String) {
    private var token: String? = null
    val api = Api(base, resultDispatcher = null) { token }
    val user: UserDto

    init {
        val res = runBlocking { api.register(nick) }
        token = res.token
        user = res.user
    }

    fun <T> call(block: suspend Api.() -> T): T = runBlocking { api.block() }
}

fun uniq(prefix: String) = prefix + "_" + (System.nanoTime() % 100000).toString()

/** The app's own account, queried from the test thread without touching the main looper. */
fun appApi(app: FonarApp, base: String) = Api(base, resultDispatcher = null) {
    (app.graph.session.value as? app.fonar.data.SessionStore.State.Active)?.session?.token
}
