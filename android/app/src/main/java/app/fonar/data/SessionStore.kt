package app.fonar.data

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Stores the session token encrypted with an AES-GCM key that lives in the Android
 * Keystore (hardware-backed where available, non-exportable). The ciphertext sits in
 * private SharedPreferences; backups are disabled, so a restored/cloned copy cannot
 * be decrypted and is treated as a lost session.
 */
class SessionStore(context: Context, private val cipher: TokenCipher = TokenCipher.forDevice()) {
    private val prefs = context.getSharedPreferences("fonar_session", Context.MODE_PRIVATE)

    data class Session(val token: String, val userId: String, val nick: String)

    sealed interface State {
        data object None : State
        data class Active(val session: Session) : State
        /** There was a session on this device but it can no longer be used. */
        data class Lost(val nick: String?) : State
    }

    fun load(): State {
        val ct = prefs.getString(KEY_TOKEN, null)
        val nick = prefs.getString(KEY_NICK, null)
        val uid = prefs.getString(KEY_UID, null)
        if (ct == null) {
            return if (prefs.getBoolean(KEY_LOST, false)) State.Lost(nick) else State.None
        }
        val token = runCatching { cipher.decrypt(ct) }.getOrNull()
        if (token == null || nick == null || uid == null) {
            markLost()
            return State.Lost(nick)
        }
        return State.Active(Session(token, uid, nick))
    }

    fun save(token: String, user: UserDto) {
        prefs.edit()
            .putString(KEY_TOKEN, cipher.encrypt(token))
            .putString(KEY_NICK, user.nick)
            .putString(KEY_UID, user.id)
            .putBoolean(KEY_LOST, false)
            .commit()
    }

    /** The server rejected the token, or it can not be decrypted any more. */
    fun markLost() {
        prefs.edit().remove(KEY_TOKEN).putBoolean(KEY_LOST, true).commit()
    }

    /** User chose to start over with a new nickname. */
    fun clear() {
        prefs.edit().clear().commit()
    }

    companion object {
        private const val KEY_TOKEN = "token_ct"
        private const val KEY_NICK = "nick"
        private const val KEY_UID = "uid"
        private const val KEY_LOST = "lost"
    }
}

interface TokenCipher {
    fun encrypt(plain: String): String
    fun decrypt(encoded: String): String

    companion object {
        fun forDevice(): TokenCipher =
            if (Build.FINGERPRINT == "robolectric") PlainCipherForJvmTests else KeystoreCipher()
    }
}

class KeystoreCipher(private val alias: String = "fonar_session_key") : TokenCipher {
    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return gen.generateKey()
    }

    override fun encrypt(plain: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, key())
        val ct = c.doFinal(plain.toByteArray(Charsets.UTF_8))
        val out = ByteArray(1 + c.iv.size + ct.size)
        out[0] = c.iv.size.toByte()
        System.arraycopy(c.iv, 0, out, 1, c.iv.size)
        System.arraycopy(ct, 0, out, 1 + c.iv.size, ct.size)
        return Base64.encodeToString(out, Base64.NO_WRAP)
    }

    override fun decrypt(encoded: String): String {
        val raw = Base64.decode(encoded, Base64.NO_WRAP)
        val ivLen = raw[0].toInt()
        val iv = raw.copyOfRange(1, 1 + ivLen)
        val ct = raw.copyOfRange(1 + ivLen, raw.size)
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        return String(c.doFinal(ct), Charsets.UTF_8)
    }
}

/** Robolectric has no AndroidKeyStore provider; used only in JVM unit tests. */
object PlainCipherForJvmTests : TokenCipher {
    override fun encrypt(plain: String) = "plain:" + plain
    override fun decrypt(encoded: String) = encoded.removePrefix("plain:")
}
