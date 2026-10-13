package io.github.thesiegs.kidpanel

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId
import java.util.Locale

class PanelModelTest {
    private val sample = """
        {"title": "Alex",
         "views": [
           {"entity_id": "sensor.left", "name": "Time left today", "state": "45", "unit": "min"},
           {"entity_id": "sensor.bed", "name": "Bedtime tonight", "state": "21:30:00"},
           {"entity_id": "sensor.screen", "name": "Screen time", "state": "75.4", "unit": "min",
            "apps": [{"name": "Chat", "minutes": 40.2}, {"name": "Maps", "minutes": 5}]}],
         "controls": [
           {"entity_id": "light.desk", "domain": "light", "name": "Desk", "state": "on", "dimmable": true, "brightness_pct": 60},
           {"entity_id": "cover.blinds", "domain": "cover", "name": "Blinds", "state": "open", "positionable": true, "position": 70},
           {"entity_id": "media_player.echo", "domain": "media_player", "name": "Echo", "state": "off"},
           {"entity_id": "scene.bright", "domain": "scene", "name": "Bright", "state": "unknown"}],
         "remote": {"entity_id": "remote.tv", "name": "TV remote", "available": true}}
    """.trimIndent()

    @Test
    fun parsesEverythingThePanelSends() {
        val s = PanelState.parse(sample)
        assertEquals("Alex", s.title)
        assertEquals(3, s.views.size)
        assertEquals(listOf("Chat" to 40.2, "Maps" to 5.0), s.views[2].apps)
        val desk = s.controls[0]
        assertTrue(desk.dimmable)
        assertEquals(60, desk.brightnessPct)
        assertEquals(70, s.controls[1].position)
        assertEquals("remote.tv", s.remote?.entityId)
    }

    @Test
    fun missingPartsAreFine() {
        val s = PanelState.parse("""{"title": "Sam", "views": [], "controls": [], "remote": null}""")
        assertTrue(s.views.isEmpty())
        assertNull(s.remote)
    }

    @Test
    fun formatsLikeTheWebPage() {
        val s = PanelState.parse(sample)
        assertEquals("45m", Format.value(s.views[0]))
        assertEquals("9:30 PM", Format.value(s.views[1], locale = Locale.US))
        assertEquals("1h 15m", Format.value(s.views[2]))
        assertEquals("—", Format.value(ViewItem("x", "x", "unavailable")))
        assertEquals("21 °C", Format.value(ViewItem("x", "x", "21", unit = "°C")))
        assertEquals(
            "Mon 6:00 AM",
            Format.value(
                ViewItem("x", "x", "2026-10-12T10:00:00+00:00", deviceClass = "timestamp"),
                zone = ZoneId.of("America/New_York"),
                locale = Locale.US,
            ),
        )
    }

    @Test
    fun onlyActionsThePanelAccepts() {
        val s = PanelState.parse(sample)
        assertEquals("toggle", Actions.toggle(s.controls[0]))
        assertNull(Actions.toggle(s.controls[1]))
        assertEquals("turn_on", Actions.toggle(s.controls[2]))
        assertEquals("activate", Actions.toggle(s.controls[3]))
        val body = JSONObject(Actions.body("cover.blinds", "position", 50))
        assertEquals("cover.blinds", body.getString("entity_id"))
        assertEquals(50, body.getInt("value"))
        assertTrue(!JSONObject(Actions.body("light.desk", "toggle")).has("value"))
    }

    @Test
    fun tileTakesOnlyOneTapControls() {
        val quick = PanelTileService.quickControls(PanelState.parse(sample))
        assertEquals(listOf("light.desk", "scene.bright"), quick.map { it.entityId })
    }
}
