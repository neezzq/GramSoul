package app.fonar

import app.fonar.data.Api
import app.fonar.data.UserDto
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

/** A second "phone" driven through the public API only (same endpoints the app uses). */
class RemotePlayer(private val base: String, nick: String, password: String? = TEST_PASSWORD) {
    private var token: String? = null
    val api = Api(base, resultDispatcher = null) { token }
    val user: UserDto

    init {
        // password = null makes an "old" account from before passwords existed
        val res = runBlocking { api.register(nick, password) }
        token = res.token
        user = res.user
    }

    fun <T> call(block: suspend Api.() -> T): T = runBlocking { api.block() }

    /** Sends a small generated JPEG as the player's own chat photo (what the photo picker does in the app). */
    fun uploadPhoto(roomId: String, jpeg: ByteArray, caption: String = ""): app.fonar.data.PostMessageRes {
        val body = okhttp3.MultipartBody.Builder().setType(okhttp3.MultipartBody.FORM)
            .addFormDataPart("file", "p.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))
            .addFormDataPart("caption", caption)
            .addFormDataPart("client_id", java.util.UUID.randomUUID().toString())
            .build()
        val req = okhttp3.Request.Builder().url("$base/v1/rooms/$roomId/upload").post(body).build()
        api.http.newCall(req).execute().use { r ->
            check(r.isSuccessful) { "upload failed: ${r.code}" }
            return app.fonar.data.json.decodeFromString(app.fonar.data.PostMessageRes.serializer(), r.body!!.string())
        }
    }
}

const val TEST_PASSWORD = "lighthouse-42"

fun uniq(prefix: String) = prefix + "_" + (System.nanoTime() % 100000).toString()

/** The app's own account, queried from the test thread without touching the main looper. */
fun appApi(app: FonarApp, base: String) = Api(base, resultDispatcher = null) {
    (app.graph.session.value as? app.fonar.data.SessionStore.State.Active)?.session?.token
}
