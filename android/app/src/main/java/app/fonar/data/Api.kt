package app.fonar.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.serializer
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resumeWithException

/** Server answered with an error the user should see. */
class ApiException(val status: Int, val code: String, override val message: String) : Exception(message)

/** No connection / timeout. */
class NetworkException(cause: Throwable) : Exception("Нет связи с сервером", cause)

val json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    encodeDefaults = true
}

class Api(
    baseUrl: String,
    /** Where results are delivered; null = on the network thread (JVM tests only). */
    private val resultDispatcher: kotlinx.coroutines.CoroutineDispatcher? = Dispatchers.Main.immediate,
    private val tokenProvider: () -> String?,
) {
    val base = baseUrl.trimEnd('/')

    /** Emits when the server rejects our token (session lost). */
    private val _unauthorized = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val unauthorized: SharedFlow<Unit> = _unauthorized

    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .addInterceptor { chain ->
            val req = chain.request()
            val token = tokenProvider()
            // only ever send the token to our own backend
            val sameHost = req.url.host == base.toHttpUrl().host
            chain.proceed(
                if (token != null && sameHost) req.newBuilder().header("Authorization", "Bearer $token").build() else req
            )
        }
        .build()

    // ------------------------------------------------------------------ plumbing
    private suspend fun Call.await(): Response = suspendCancellableCoroutine { cont ->
        enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (!cont.isCancelled) cont.resumeWithException(NetworkException(e))
            }

            override fun onResponse(call: Call, response: Response) {
                cont.resume(response) { _, _, _ -> response.close() }
            }
        })
        cont.invokeOnCancellation { runCatching { cancel() } }
    }

    /** Always completes on the main thread, whatever thread OkHttp answered on. */
    private suspend fun <T> exec(req: Request, ser: KSerializer<T>, client: OkHttpClient = http): T =
        resultDispatcher?.let { withContext(it) { execInner(req, ser, client) } } ?: execInner(req, ser, client)

    private suspend fun <T> execInner(req: Request, ser: KSerializer<T>, client: OkHttpClient): T {
        val resp = client.newCall(req).await()
        resp.use { r ->
            val body = withContext(Dispatchers.IO) { r.body?.string().orEmpty() }
            if (r.isSuccessful) return json.decodeFromString(ser, body)
            val detail = runCatching { json.decodeFromString(ApiErrorBody.serializer(), body).detail }.getOrNull()
            if (r.code == 401 && tokenProvider() != null) _unauthorized.tryEmit(Unit)
            throw ApiException(
                r.code,
                detail?.code ?: "http_${r.code}",
                detail?.message ?: when (r.code) {
                    429 -> "Слишком часто. Подожди немного."
                    in 500..599 -> "Сервер временно недоступен. Попробуй ещё раз."
                    else -> "Ошибка ${r.code}"
                },
            )
        }
    }

    private inline fun <reified B> jsonBody(body: B) =
        json.encodeToString(serializer<B>(), body).toRequestBody("application/json".toMediaType())

    private fun url(path: String) = base + path

    private suspend inline fun <reified T> get(path: String, client: OkHttpClient = http): T =
        exec(Request.Builder().url(url(path)).get().build(), serializer<T>(), client)

    private suspend inline fun <reified B, reified T> post(path: String, body: B): T =
        exec(Request.Builder().url(url(path)).post(jsonBody(body)).build(), serializer<T>())

    private suspend inline fun <reified T> postEmpty(path: String): T =
        exec(Request.Builder().url(url(path)).post(ByteArray(0).toRequestBody(null)).build(), serializer<T>())

    private suspend inline fun <reified B, reified T> put(path: String, body: B): T =
        exec(Request.Builder().url(url(path)).put(jsonBody(body)).build(), serializer<T>())

    private suspend inline fun <reified B, reified T> patch(path: String, body: B): T =
        exec(Request.Builder().url(url(path)).patch(jsonBody(body)).build(), serializer<T>())

    private suspend inline fun <reified T> delete(path: String): T =
        exec(Request.Builder().url(url(path)).delete().build(), serializer<T>())

    private val longPoll: OkHttpClient by lazy { http.newBuilder().readTimeout(40, TimeUnit.SECONDS).build() }

    private fun q(s: String) = java.net.URLEncoder.encode(s, "UTF-8")

    // ------------------------------------------------------------------ endpoints
    suspend fun register(nick: String): RegisterRes = post("/v1/register", RegisterReq(nick))
    suspend fun me(): MeRes = get("/v1/me")
    suspend fun setAbout(about: String): MeRes = patch("/v1/me", AboutReq(about))
    suspend fun setAvatar(imageId: String?): MeRes = patch("/v1/me", AvatarReq(imageId ?: ""))
    suspend fun transferCode(): TransferCodeRes = postEmpty("/v1/me/transfer-code")
    suspend fun loginWithTransferCode(nick: String, code: String): LoginRes =
        post("/v1/login/transfer", TransferLoginReq(nick, code))
    suspend fun searchPeople(q: String): PeopleSearchRes = get("/v1/users/search?q=${q(q)}")
    fun avatarUrl(u: UserDto): String? = u.avatar_image_id?.let { url("/v1/users/${u.id}/avatar?v=$it") }

    suspend fun search(nick: String): SearchRes = get("/v1/users/search?nick=${q(nick)}")
    suspend fun sendFriendRequest(nick: String): FriendRequestRes = post("/v1/friends/requests", FriendRequestReq(nick))
    suspend fun friends(): FriendsRes = get("/v1/friends")
    suspend fun acceptFriend(id: String): FriendRequestRes = postEmpty("/v1/friends/requests/$id/accept")
    suspend fun declineFriend(id: String): FriendRequestRes = postEmpty("/v1/friends/requests/$id/decline")
    suspend fun inboxWait(since: Long, wait: Int = 25): InboxRes = get("/v1/inbox/wait?since=$since&wait=$wait", longPoll)

    suspend fun stories(): StoriesRes = get("/v1/stories")
    suspend fun story(id: String): StoryRes = get("/v1/stories/$id")
    suspend fun createStory(s: StoryReq): StoryRes = post("/v1/stories", s)
    suspend fun updateStory(id: String, s: StoryReq): StoryRes = put("/v1/stories/$id", s)
    suspend fun quickStory(q: QuickStoryReq): StoryRes = post("/v1/stories/quick", q)
    suspend fun demoStory(): StoryRes = postEmpty("/v1/stories/demo")
    suspend fun deleteStory(id: String): OkRes = delete("/v1/stories/$id")
    suspend fun patchCharacter(storyId: String, charId: String, p: CharacterPatch): CharacterRes =
        patch("/v1/stories/$storyId/characters/$charId", p)

    suspend fun createRoom(storyId: String): RoomRes = postEmpty("/v1/stories/$storyId/rooms")
    suspend fun rooms(): RoomsRes = get("/v1/rooms")
    suspend fun room(id: String): RoomRes = get("/v1/rooms/$id")
    suspend fun deleteRoom(id: String): OkRes = delete("/v1/rooms/$id")
    suspend fun invite(roomId: String, userId: String): InviteRes = post("/v1/rooms/$roomId/invite", InviteReq(userId))
    suspend fun acceptInvite(id: String): InviteRes = postEmpty("/v1/invites/$id/accept")
    suspend fun declineInvite(id: String): InviteRes = postEmpty("/v1/invites/$id/decline")
    suspend fun sync(roomId: String, since: Long, pv: Long, wait: Int): SyncRes =
        get("/v1/rooms/$roomId/sync?since=$since&pv=$pv&wait=$wait", if (wait > 0) longPoll else http)

    suspend fun postMessage(roomId: String, clientId: String, text: String): PostMessageRes =
        post("/v1/rooms/$roomId/messages", MessageReq(clientId, text))

    suspend fun continueScene(roomId: String, clientId: String): GenerationRes = post("/v1/rooms/$roomId/continue", ActionReq(clientId))
    suspend fun regenerate(roomId: String, clientId: String): GenerationRes = post("/v1/rooms/$roomId/regenerate", ActionReq(clientId))
    suspend fun retry(roomId: String, clientId: String): GenerationRes = post("/v1/rooms/$roomId/retry", ActionReq(clientId))
    suspend fun setScene(roomId: String, location: String): SceneReq = patch("/v1/rooms/$roomId/scene", SceneReq(location))
    suspend fun lastPrompt(roomId: String): LastPromptRes = get("/v1/rooms/$roomId/last-prompt")
    suspend fun setAiMode(roomId: String, mode: String): RoomSettingsRes = patch("/v1/rooms/$roomId/settings", RoomSettingsReq(mode))
    suspend fun photo(roomId: String, clientId: String, prompt: String): PhotoRes =
        post("/v1/rooms/$roomId/photo", PhotoReq(clientId, prompt))

    suspend fun personas(q: String = "", scope: String = "all"): PersonasRes =
        get("/v1/personas?q=${q(q)}&scope=$scope")
    suspend fun persona(id: String): PersonaRes = get("/v1/personas/$id")
    suspend fun createPersona(p: PersonaReq): PersonaRes = post("/v1/personas", p)
    suspend fun updatePersona(id: String, p: PersonaReq): PersonaRes = put("/v1/personas/$id", p)
    suspend fun deletePersona(id: String): OkRes = delete("/v1/personas/$id")
    suspend fun fillPersona(idea: String): FillRes = post("/v1/personas/fill", FillReq(idea))
    suspend fun avatarStyles(): AvatarStylesRes = get("/v1/avatar-styles")
    suspend fun generateAvatar(name: String, description: String, style: String): AvatarGenRes =
        post("/v1/avatars/generate", AvatarGenReq(name, description, style))
    fun personaAvatarUrl(p: PersonaDto): String? = p.avatar_image_id?.let { url("/v1/personas/${p.id}/avatar?v=$it") }

    fun ownImageUrl(id: String) = url("/v1/images/$id")
    fun roomImageUrl(roomId: String, id: String) = url("/v1/rooms/$roomId/images/$id")

    /** Downscales the picked picture on the device and uploads it. */
    suspend fun uploadImage(context: Context, uri: Uri, maxSide: Int = 1024): ImageRes {
        val bytes = withContext(Dispatchers.IO) { prepareJpeg(context, uri, maxSide) }
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("file", "image.jpg", bytes.toRequestBody("image/jpeg".toMediaType()))
            .build()
        return exec(Request.Builder().url(url("/v1/images")).post(body).build(), ImageRes.serializer())
    }

    private fun prepareJpeg(context: Context, uri: Uri, maxSide: Int): ByteArray {
        val cr = context.contentResolver
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        cr.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
            ?: throw ApiException(0, "bad_image", "Не удалось открыть картинку")
        var sample = 1
        while (bounds.outWidth / (sample * 2) >= maxSide || bounds.outHeight / (sample * 2) >= maxSide) sample *= 2
        val opts = BitmapFactory.Options().apply { inSampleSize = sample }
        var bmp = cr.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) }
            ?: throw ApiException(0, "bad_image", "Не удалось прочитать картинку")
        val rotation = runCatching {
            cr.openInputStream(uri)?.use {
                when (ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
                    ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                    ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                    ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                    else -> 0f
                }
            } ?: 0f
        }.getOrDefault(0f)
        val scale = minOf(1f, maxSide.toFloat() / maxOf(bmp.width, bmp.height))
        if (scale < 1f || rotation != 0f) {
            val m = Matrix().apply { postScale(scale, scale); postRotate(rotation) }
            bmp = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
        }
        return ByteArrayOutputStream().use { out ->
            bmp.compress(Bitmap.CompressFormat.JPEG, 85, out)
            out.toByteArray()
        }
    }
}
