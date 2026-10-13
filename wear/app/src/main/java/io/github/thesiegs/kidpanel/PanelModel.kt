package io.github.thesiegs.kidpanel

import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.max
import kotlin.math.roundToInt

/** A read-only value on the panel (screen time, bedtime, a temperature). */
data class ViewItem(
    val entityId: String,
    val name: String,
    val state: String,
    val unit: String? = null,
    val deviceClass: String? = null,
    val apps: List<Pair<String, Double>> = emptyList(),
)

/** Something the panel may operate, with the few fields it's given. */
data class Control(
    val entityId: String,
    val domain: String,
    val name: String,
    val state: String,
    val dimmable: Boolean = false,
    val brightnessPct: Int? = null,
    val volume: Double? = null,
    val muted: Boolean = false,
    val mediaTitle: String? = null,
    val positionable: Boolean = false,
    val position: Int? = null,
) {
    val unavailable get() = state == "unavailable"
    val on get() = state == "on" || state == "playing" || state == "open" || state == "opening"
}

data class Remote(val entityId: String, val name: String, val available: Boolean)

data class PanelState(
    val title: String,
    val views: List<ViewItem>,
    val controls: List<Control>,
    val remote: Remote?,
) {
    companion object {
        fun parse(json: String): PanelState {
            val o = JSONObject(json)
            val views = o.optJSONArray("views").objects().map { v ->
                ViewItem(
                    entityId = v.getString("entity_id"),
                    name = v.optString("name", v.getString("entity_id")),
                    state = v.optString("state", "unavailable"),
                    unit = v.optStringOrNull("unit"),
                    deviceClass = v.optStringOrNull("device_class"),
                    apps = v.optJSONArray("apps").objects().map { it.optString("name") to it.optDouble("minutes", 0.0) },
                )
            }
            val controls = o.optJSONArray("controls").objects().map { c ->
                Control(
                    entityId = c.getString("entity_id"),
                    domain = c.optString("domain", c.getString("entity_id").substringBefore('.')),
                    name = c.optString("name", c.getString("entity_id")),
                    state = c.optString("state", "unavailable"),
                    dimmable = c.optBoolean("dimmable", false),
                    brightnessPct = if (c.has("brightness_pct")) c.getInt("brightness_pct") else null,
                    volume = if (c.has("volume")) c.getDouble("volume") else null,
                    muted = c.optBoolean("muted", false),
                    mediaTitle = c.optStringOrNull("media_title"),
                    positionable = c.optBoolean("positionable", false),
                    position = if (c.has("position")) c.getInt("position") else null,
                )
            }
            val remote = o.optJSONObject("remote")?.let {
                Remote(it.getString("entity_id"), it.optString("name", "TV remote"), it.optBoolean("available", true))
            }
            return PanelState(o.optString("title", ""), views, controls, remote)
        }

        private fun JSONArray?.objects(): List<JSONObject> =
            if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

        private fun JSONObject.optStringOrNull(key: String): String? =
            if (has(key) && !isNull(key)) getString(key) else null
    }
}

/** How the panel shows values; the same rules as the web page. */
object Format {
    fun duration(minutes: Double): String {
        val m = max(0, minutes.roundToInt())
        return if (m >= 60) "${m / 60}h ${m % 60}m" else "${m}m"
    }

    fun value(item: ViewItem, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String {
        val raw = item.state
        if (raw == "unavailable" || raw == "unknown") return "—"
        val number = raw.toDoubleOrNull()
        if (item.unit == "min" && number != null) return duration(number)
        if (item.deviceClass == "timestamp") {
            runCatching {
                val t = OffsetDateTime.parse(raw).atZoneSameInstant(zone)
                return t.format(DateTimeFormatter.ofPattern("EEE h:mm a", locale))
            }
        }
        if (Regex("""\d{2}:\d{2}:\d{2}""").matches(raw)) {
            return LocalTime.parse(raw).format(DateTimeFormatter.ofPattern("h:mm a", locale))
        }
        if (raw == "on") return "On"
        if (raw == "off") return "Off"
        return if (item.unit != null) "$raw ${item.unit}" else raw
    }
}

/** The actions the panel accepts; anything else it refuses. */
object Actions {
    fun toggle(c: Control): String? = when (c.domain) {
        "light", "switch", "fan", "input_boolean" -> "toggle"
        "scene" -> "activate"
        "script" -> "run"
        "media_player" -> if (c.state == "off") "turn_on" else "play_pause"
        else -> null
    }

    fun body(entityId: String, action: String, value: Any? = null): String =
        JSONObject().put("entity_id", entityId).put("action", action).apply { if (value != null) put("value", value) }
            .toString()
}
