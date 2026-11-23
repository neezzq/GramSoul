package app.fonar.data

import android.content.Context
import kotlinx.serialization.Serializable
import java.io.File

/** Local drafts of the story editor so nothing typed is lost if the app is closed. */
@Serializable
data class StoryDraft(
    val draftId: String,
    val serverId: String? = null,
    val story: StoryDto,
    val savedAt: Long = System.currentTimeMillis(),
)

@Serializable
data class QuickDraft(
    val name: String = "",
    val avatarImageId: String? = null,
    val personality: String = "",
    val speechStyle: String = "",
    val startLine: String = "",
)

class DraftStore(context: Context) {
    private val dir = File(context.filesDir, "drafts").apply { mkdirs() }

    private fun file(id: String) = File(dir, id.replace(Regex("[^A-Za-z0-9_-]"), "_") + ".json")

    fun saveStory(d: StoryDraft) {
        val f = file(d.draftId)
        val tmp = File(f.path + ".tmp")
        tmp.writeText(json.encodeToString(StoryDraft.serializer(), d))
        tmp.renameTo(f)
    }

    fun loadStory(id: String): StoryDraft? =
        runCatching { json.decodeFromString(StoryDraft.serializer(), file(id).readText()) }.getOrNull()

    fun deleteStory(id: String) {
        file(id).delete()
    }

    /** Unsaved drafts of new stories (shown in the story list). */
    fun newStoryDrafts(): List<StoryDraft> =
        (dir.listFiles() ?: emptyArray())
            .filter { it.name.startsWith("new-") && it.name.endsWith(".json") }
            .mapNotNull { runCatching { json.decodeFromString(StoryDraft.serializer(), it.readText()) }.getOrNull() }
            .sortedByDescending { it.savedAt }

    fun saveQuick(d: QuickDraft) {
        file("quick").writeText(json.encodeToString(QuickDraft.serializer(), d))
    }

    fun loadQuick(): QuickDraft? =
        runCatching { json.decodeFromString(QuickDraft.serializer(), file("quick").readText()) }.getOrNull()

    fun deleteQuick() {
        file("quick").delete()
    }

    fun clearAll() {
        dir.listFiles()?.forEach { it.delete() }
    }
}
