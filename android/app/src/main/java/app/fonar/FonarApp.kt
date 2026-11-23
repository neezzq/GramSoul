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

    override fun newImageLoader(context: PlatformContext): ImageLoader = graph.imageLoader
}

/** Simple manual dependency container. */
class AppGraph(context: Context, backendUrl: String) {
    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    val sessionStore = SessionStore(context)
    private val _session = MutableStateFlow(sessionStore.load())
    val session: StateFlow<SessionStore.State> = _session

    val api = Api(backendUrl) { (session.value as? SessionStore.State.Active)?.session?.token }
    val drafts = DraftStore(context)

    val imageLoader: ImageLoader = ImageLoader.Builder(context)
        .components { add(OkHttpNetworkFetcherFactory(callFactory = { api.http })) }
        .crossfade(true)
        .build()

    init {
        appScope.launch {
            api.unauthorized.collect {
                sessionStore.markLost()
                _session.value = sessionStore.load()
            }
        }
    }

    val me: UserDto?
        get() = (session.value as? SessionStore.State.Active)?.session?.let { UserDto(it.userId, it.nick) }

    fun onRegistered(token: String, user: UserDto) {
        sessionStore.save(token, user)
        _session.value = sessionStore.load()
    }

    fun startOver() {
        sessionStore.clear()
        drafts.clearAll()
        _session.value = sessionStore.load()
    }
}

val Context.graph: AppGraph get() = (applicationContext as FonarApp).graph
