package io.github.thesiegs.kidpanel

import android.app.RemoteInput
import android.os.Bundle
import android.util.Log
import android.view.inputmethod.EditorInfo
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.wear.compose.foundation.lazy.ScalingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberScalingLazyListState
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.ButtonDefaults
import androidx.wear.compose.material.Chip
import androidx.wear.compose.material.ChipDefaults
import androidx.wear.compose.material.CompactChip
import androidx.wear.compose.material.InlineSlider
import androidx.wear.compose.material.InlineSliderDefaults
import androidx.wear.compose.material.ListHeader
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.PositionIndicator
import androidx.wear.compose.material.Scaffold
import androidx.wear.compose.material.Switch
import androidx.wear.compose.material.Text
import androidx.wear.compose.material.TimeText
import androidx.wear.compose.material.ToggleChip
import androidx.wear.input.RemoteInputIntentHelper
import androidx.wear.input.wearableExtender
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

private const val TAG = "KidPanel"

class MainActivity : ComponentActivity() {
    private lateinit var panel: Panel
    private var state by mutableStateOf<PanelState?>(null)
    private var paired by mutableStateOf(false)
    private var message by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        panel = Panel(this)
        paired = panel.paired
        state = panel.cached()
        // While the app is on screen, keep its state fresh
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.RESUMED) {
                while (true) {
                    if (panel.paired) refresh()
                    delay(5_000)
                }
            }
        }
        setContent {
            MaterialTheme {
                var showRemote by remember { mutableStateOf(false) }
                BackHandler(enabled = showRemote) { showRemote = false }
                val current = state
                when {
                    !paired -> PairScreen(message, onCode = ::pair)
                    showRemote && current?.remote != null -> RemoteScreen(current.remote, ::act)
                    else -> PanelScreen(current, message, ::act, onRemote = { showRemote = true }, onUnpair = ::unpair)
                }
            }
        }
    }

    private suspend fun refresh() {
        try {
            state = panel.refresh()
            message = null
        } catch (e: PanelError.Unpaired) {
            paired = false
            state = null
            message = "This watch needs pairing again"
        } catch (e: PanelError) {
            message = if (e is PanelError.Busy) "Slow down a little" else "Can't reach home"
        }
    }

    private fun act(entityId: String, action: String, value: Any?) {
        lifecycleScope.launch {
            try {
                panel.act(entityId, action, value)
                message = null
            } catch (e: PanelError.Unpaired) {
                paired = false
                state = null
                message = "This watch needs pairing again"
                return@launch
            } catch (e: PanelError) {
                message = when (e) {
                    is PanelError.Busy -> "Slow down a little"
                    is PanelError.Refused -> "That didn't work"
                    else -> "Can't reach home"
                }
            }
            refresh()
        }
    }

    private fun pair(code: String) {
        lifecycleScope.launch {
            try {
                panel.pair(code)
                paired = true
                message = null
                refresh()
            } catch (e: PanelError) {
                Log.w(TAG, "Pairing failed", e)
                message = when (e) {
                    is PanelError.Busy -> "Too many tries; wait a few minutes"
                    is PanelError.Offline -> "Can't reach home"
                    else -> "That code didn't work"
                }
            } catch (e: Exception) {
                Log.w(TAG, "Pairing failed", e)
                message = "That code didn't work"
            }
        }
    }

    private fun unpair() {
        panel.unpair()
        paired = false
        state = null
        message = null
    }
}

@Composable
private fun PairScreen(message: String?, onCode: (String) -> Unit) {
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val code = result.data?.let { RemoteInput.getResultsFromIntent(it) }?.getCharSequence("code")?.toString()
            ?.filter(Char::isDigit)
        if (code != null && code.length == 6) onCode(code)
    }
    Scaffold(timeText = { TimeText() }) {
        Column(
            Modifier.fillMaxSize().padding(horizontal = 22.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Ask a parent for a pairing code", textAlign = TextAlign.Center, fontSize = 14.sp)
            if (message != null) {
                Text(message, color = Color(0xFFFF6B6B), fontSize = 12.sp, textAlign = TextAlign.Center,
                    modifier = Modifier.padding(top = 6.dp))
            }
            Chip(
                modifier = Modifier.padding(top = 10.dp),
                label = { Text("Enter code") },
                onClick = {
                    val intent = RemoteInputIntentHelper.createActionRemoteInputIntent()
                    val input = RemoteInput.Builder("code")
                        .setLabel("6-digit code")
                        .wearableExtender {
                            setEmojisAllowed(false)
                            setInputActionType(EditorInfo.IME_ACTION_DONE)
                        }
                        .build()
                    RemoteInputIntentHelper.putRemoteInputsExtra(intent, listOf(input))
                    launcher.launch(intent)
                },
            )
        }
    }
}

@Composable
private fun PanelScreen(
    state: PanelState?,
    message: String?,
    act: (String, String, Any?) -> Unit,
    onRemote: () -> Unit,
    onUnpair: () -> Unit,
) {
    val list = rememberScalingLazyListState()
    var confirmUnpair by remember { mutableStateOf(false) }
    Scaffold(timeText = { TimeText() }, positionIndicator = { PositionIndicator(list) }) {
        ScalingLazyColumn(state = list, modifier = Modifier.fillMaxSize()) {
            item { ListHeader { Text(state?.title ?: "Kid Panel", fontWeight = FontWeight.Bold) } }
            if (message != null) {
                item { Text(message, color = Color(0xFFFF6B6B), fontSize = 12.sp, textAlign = TextAlign.Center) }
            }
            if (state == null) {
                item { Text("Loading…", fontSize = 13.sp) }
            } else {
                state.views.forEach { v -> item(key = "v:${v.entityId}") { ViewRow(v) } }
                state.controls.forEach { c -> item(key = "c:${c.entityId}") { ControlRow(c, act) } }
                state.remote?.let { r ->
                    item(key = "remote") {
                        Chip(
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text(r.name, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                            secondaryLabel = { Text("Remote") },
                            enabled = r.available,
                            onClick = onRemote,
                            colors = ChipDefaults.secondaryChipColors(),
                        )
                    }
                }
            }
            item {
                CompactChip(
                    modifier = Modifier.padding(top = 8.dp),
                    label = { Text(if (confirmUnpair) "Tap again to unpair" else "Unpair this watch") },
                    onClick = { if (confirmUnpair) onUnpair() else confirmUnpair = true },
                    colors = ChipDefaults.childChipColors(),
                )
            }
        }
    }
}

@Composable
private fun ViewRow(v: ViewItem) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 2.dp)) {
        Text(v.name, fontSize = 11.sp, color = Color(0xFF8B93A1), maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(Format.value(v), fontSize = 18.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        v.apps.take(3).forEach { (name, minutes) ->
            Row(Modifier.fillMaxWidth()) {
                Text(name, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                Text(Format.duration(minutes), fontSize = 11.sp, color = Color(0xFF8B93A1))
            }
        }
    }
}

@Composable
private fun ControlRow(c: Control, act: (String, String, Any?) -> Unit) {
    when (c.domain) {
        "light", "switch", "fan", "input_boolean" -> Column(Modifier.fillMaxWidth()) {
            ToggleChip(
                modifier = Modifier.fillMaxWidth(),
                checked = c.state == "on",
                enabled = !c.unavailable,
                onCheckedChange = { act(c.entityId, "toggle", null) },
                label = { Text(c.name, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                secondaryLabel = {
                    Text(
                        when {
                            c.unavailable -> "Offline"
                            c.state == "on" && c.brightnessPct != null -> "On · ${c.brightnessPct}%"
                            c.state == "on" -> "On"
                            else -> "Off"
                        }
                    )
                },
                toggleControl = { Switch(checked = c.state == "on") },
            )
            if (c.domain == "light" && c.dimmable && c.state == "on") {
                InlineSlider(
                    modifier = Modifier.padding(top = 4.dp),
                    value = (((c.brightnessPct ?: 100) / 10.0).roundToInt() * 10).coerceIn(10, 100),
                    onValueChange = { act(c.entityId, "brightness", it) },
                    valueProgression = IntProgression.fromClosedRange(10, 100, 10),
                    increaseIcon = { Text("+") },
                    decreaseIcon = { Text("−") },
                    segmented = false,
                    colors = InlineSliderDefaults.colors(),
                )
            }
        }
        "scene", "script" -> Chip(
            modifier = Modifier.fillMaxWidth(),
            label = { Text(c.name, maxLines = 1, overflow = TextOverflow.Ellipsis) },
            secondaryLabel = { Text("Tap to run") },
            onClick = { act(c.entityId, if (c.domain == "scene") "activate" else "run", null) },
            colors = ChipDefaults.secondaryChipColors(),
        )
        "media_player" -> Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            Chip(
                modifier = Modifier.fillMaxWidth(),
                label = { Text(c.name, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                secondaryLabel = { Text(c.mediaTitle ?: if (c.unavailable) "Offline" else c.state) },
                enabled = !c.unavailable,
                onClick = { act(c.entityId, if (c.state == "off") "turn_on" else "play_pause", null) },
                colors = ChipDefaults.secondaryChipColors(),
            )
            if (!c.unavailable && c.state != "off") {
                ButtonRow(
                    listOf("−" to "volume_down", "⏯" to "play_pause", "+" to "volume_up"),
                ) { action -> act(c.entityId, action, null) }
            }
        }
        "cover" -> Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            Chip(
                modifier = Modifier.fillMaxWidth(),
                label = { Text(c.name, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                secondaryLabel = {
                    Text(if (c.unavailable) "Offline" else listOfNotNull(c.state, c.position?.let { "$it%" }).joinToString(" · "))
                },
                onClick = {},
                colors = ChipDefaults.secondaryChipColors(),
            )
            if (!c.unavailable) {
                ButtonRow(listOf("▲" to "open", "■" to "stop", "▼" to "close")) { action -> act(c.entityId, action, null) }
            }
        }
        else -> Unit
    }
}

@Composable
private fun ButtonRow(buttons: List<Pair<String, String>>, onClick: (String) -> Unit) {
    Row(Modifier.padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        buttons.forEach { (label, action) ->
            Button(
                onClick = { onClick(action) },
                modifier = Modifier.size(ButtonDefaults.SmallButtonSize),
                colors = ButtonDefaults.secondaryButtonColors(),
            ) { Text(label) }
        }
    }
}

@Composable
private fun RemoteScreen(remote: Remote, act: (String, String, Any?) -> Unit) {
    val keys = listOf(
        listOf("↩" to "BACK", "▲" to "DPAD_UP", "⌂" to "HOME"),
        listOf("◀" to "DPAD_LEFT", "OK" to "DPAD_CENTER", "▶" to "DPAD_RIGHT"),
        listOf("⏪" to "MEDIA_REWIND", "▼" to "DPAD_DOWN", "⏩" to "MEDIA_FAST_FORWARD"),
    )
    Scaffold {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                keys.forEach { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        row.forEach { (label, command) ->
                            Button(
                                onClick = { act(remote.entityId, "command", command) },
                                modifier = Modifier.size(46.dp),
                                colors = if (command == "DPAD_CENTER") ButtonDefaults.primaryButtonColors()
                                else ButtonDefaults.secondaryButtonColors(),
                            ) { Text(label) }
                        }
                    }
                }
            }
        }
    }
}
