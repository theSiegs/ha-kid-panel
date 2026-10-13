package io.github.thesiegs.kidpanel

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Why a call to the panel didn't work. */
sealed class PanelError(message: String) : Exception(message) {
    /** The panel no longer knows this watch (its address was changed): pair again. */
    class Unpaired : PanelError("unpaired")
    class Refused : PanelError("refused")
    class Busy : PanelError("busy")
    class Offline(cause: Throwable? = null) : PanelError("offline") { init { initCause(cause) } }
}

/** Talks to Kid Panel over HTTPS: the server is fixed at build time, the panel's path comes from pairing. */
class PanelClient(private val server: String = BuildConfig.SERVER) {

    /** Trades a pairing code for the panel's path (`/kid_panel/<key>`). */
    suspend fun pair(code: String): Pair<String, String> {
        val (status, body) = request("POST", "$server/kid_panel/pair/api", JSONObject().put("code", code).toString())
        when (status) {
            200 -> {
                val o = JSONObject(body)
                val path = o.getString("path")
                require(path.startsWith("/kid_panel/")) { "unexpected path" }
                return path to o.optString("title", "")
            }
            429 -> throw PanelError.Busy()
            else -> throw PanelError.Refused()
        }
    }

    /** The panel's state as the server sent it (JSON), for parsing and for keeping as the last one seen. */
    suspend fun stateJson(path: String): String {
        val (status, body) = request("GET", "$server$path/api/state", null)
        return when (status) {
            200 -> body.also { PanelState.parse(it) }
            404 -> throw PanelError.Unpaired()
            429 -> throw PanelError.Busy()
            else -> throw PanelError.Offline()
        }
    }

    suspend fun act(path: String, entityId: String, action: String, value: Any? = null) {
        val (status, _) = request("POST", "$server$path/api/action", Actions.body(entityId, action, value))
        when (status) {
            200 -> Unit
            404 -> throw PanelError.Unpaired()
            429 -> throw PanelError.Busy()
            403 -> throw PanelError.Refused()
            else -> throw PanelError.Offline()
        }
    }

    private suspend fun request(method: String, url: String, body: String?): Pair<Int, String> =
        withContext(Dispatchers.IO) {
            try {
                val connection = URL(url).openConnection() as HttpURLConnection
                try {
                    connection.requestMethod = method
                    connection.connectTimeout = 10_000
                    connection.readTimeout = 15_000
                    connection.useCaches = false
                    connection.instanceFollowRedirects = false
                    if (body != null) {
                        val bytes = body.toByteArray()
                        connection.doOutput = true
                        connection.setRequestProperty("Content-Type", "application/json")
                        connection.setFixedLengthStreamingMode(bytes.size)
                        connection.outputStream.use { it.write(bytes) }
                    }
                    val status = connection.responseCode
                    val stream = if (status in 200..299) connection.inputStream else connection.errorStream
                    status to (stream?.bufferedReader()?.use { it.readText() } ?: "")
                } finally {
                    connection.disconnect()
                }
            } catch (e: IOException) {
                throw PanelError.Offline(e)
            }
        }
}

/** The panel's path, kept in the app's private storage (never backed up). */
class PairingStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("panel", Context.MODE_PRIVATE)

    var path: String?
        get() = prefs.getString("path", null)
        set(value) = prefs.edit().apply { if (value == null) remove("path") else putString("path", value) }.apply()

    var title: String
        get() = prefs.getString("title", "") ?: ""
        set(value) = prefs.edit().putString("title", value).apply()

    /** The last state seen, so the tile and app can show something at once. */
    var lastState: String?
        get() = prefs.getString("last_state", null)
        set(value) = prefs.edit().putString("last_state", value).apply()

    fun clear() = prefs.edit().clear().apply()
}
