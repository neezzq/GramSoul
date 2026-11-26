package app.fonar

import android.app.Application
import android.content.Context
import app.fonar.data.Api
import app.fonar.data.DraftStore
import app.fonar.data.SessionStore
import app.fonar.data.UserDto
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import coil3.request.crossfade
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class FonarApp : Application(), SingletonImageLoader.Factory {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph(this, BuildConfig.BACKEND_URL)
    }

    // late-bound so that the loader always uses the current API client (and its session token)
    override fun newImageLoader(context: PlatformContext): ImageLoader = ImageLoader.Builder(context)
        .components { add(OkHttpNetworkFetcherFactory(callFactory = { graph.api.http })) }
        .crossfade(true)
        .build()

    /** JVM tests point the app at a local backend; the shipped app only uses BuildConfig.BACKEND_URL. */
    @androidx.annotation.VisibleForTesting
    fun resetForTests(backendUrl: String) {
        graph.sessionStore.clear()
        graph.drafts.clearAll()
        graph = AppGraph(this, backendUrl)
    }

    @androidx.annotation.VisibleForTesting
    fun resetForTestsKeepPrefs(backendUrl: String) {
        graph = AppGraph(this, backendUrl)
    }
}

/** Simple manual dependency container. */
class AppGraph(context: Context, backendUrl: String) {
    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    val sessionStore = SessionStore(context)
    private val _session = MutableStateFlow(sessionStore.load())
    val session: StateFlow<SessionStore.State> = _session

    val api = Api(backendUrl, tokenProvider = { (session.value as? SessionStore.State.Active)?.session?.token })
    val drafts = DraftStore(context)

    /** true = an account made before passwords existed: the app shows only "set a password" until it has one. */
    private val _needsPassword = MutableStateFlow(false)
    val needsPassword: StateFlow<Boolean> = _needsPassword

    init {
        appScope.launch {
            api.unauthorized.collect {
                sessionStore.markLost()
                _session.value = sessionStore.load()
            }
        }
        if (session.value is SessionStore.State.Active) checkPassword()
    }

    /** Asks the server whether this account still has no password (null from an older server = nothing to do). */
    fun checkPassword() {
        appScope.launch {
            runCatching { api.me() }.onSuccess { _needsPassword.value = it.user.has_password == false }
        }
    }

    fun onPasswordSet() {
        _needsPassword.value = false
    }

    /** The nick was changed in the profile: keep the stored session in step. */
    fun onNickChanged(user: UserDto) {
        val active = session.value as? SessionStore.State.Active ?: return
        sessionStore.save(active.session.token, user)
        _session.value = sessionStore.load()
    }

    val me: UserDto?
        get() = (session.value as? SessionStore.State.Active)?.session?.let { UserDto(it.userId, it.nick) }

    fun onRegistered(token: String, user: UserDto) {
        sessionStore.save(token, user)
        _needsPassword.value = user.has_password == false
        _session.value = sessionStore.load()
    }

    fun startOver() {
        sessionStore.clear()
        drafts.clearAll()
        _needsPassword.value = false
        _session.value = sessionStore.load()
    }
}

val Context.graph: AppGraph get() = (applicationContext as FonarApp).graph
