package io.github.thesiegs.kidpanel

import androidx.concurrent.futures.SuspendToFutureAdapter
import androidx.wear.protolayout.ActionBuilders
import androidx.wear.protolayout.DeviceParametersBuilders.DeviceParameters
import androidx.wear.protolayout.LayoutElementBuilders
import androidx.wear.protolayout.ModifiersBuilders
import androidx.wear.protolayout.ResourceBuilders
import androidx.wear.protolayout.TimelineBuilders
import androidx.wear.protolayout.material.ChipColors
import androidx.wear.protolayout.material.Colors
import androidx.wear.protolayout.material.CompactChip
import androidx.wear.protolayout.material.Text
import androidx.wear.protolayout.material.Typography
import androidx.wear.protolayout.material.layouts.PrimaryLayout
import androidx.wear.tiles.RequestBuilders
import androidx.wear.tiles.TileBuilders
import androidx.wear.tiles.TileService
import com.google.common.util.concurrent.ListenableFuture

/**
 * The panel as a tile: its first two values (time left, bedtime) and up to two quick controls that work in place.
 * Tapping a control comes back here as a tile request naming it; the action runs, then the tile is drawn afresh.
 */
class PanelTileService : TileService() {

    override fun onTileRequest(requestParams: RequestBuilders.TileRequest): ListenableFuture<TileBuilders.Tile> =
        SuspendToFutureAdapter.launchFuture {
            val panel = Panel(this@PanelTileService)
            val clicked = requestParams.currentState.lastClickableId
            if (panel.paired && clicked.startsWith(ACT)) {
                val (entityId, action) = clicked.removePrefix(ACT).split('|', limit = 2).let { it[0] to it[1] }
                runCatching { panel.act(entityId, action) }
            }
            val state = if (panel.paired) runCatching { panel.refresh() }.getOrElse { panel.cached() } else null
            tile(layout(requestParams.deviceConfiguration, panel.paired, state))
        }

    override fun onTileResourcesRequest(
        requestParams: RequestBuilders.ResourcesRequest,
    ): ListenableFuture<ResourceBuilders.Resources> =
        SuspendToFutureAdapter.launchFuture {
            ResourceBuilders.Resources.Builder().setVersion(RESOURCES).build()
        }

    private fun tile(root: LayoutElementBuilders.LayoutElement) =
        TileBuilders.Tile.Builder()
            .setResourcesVersion(RESOURCES)
            .setFreshnessIntervalMillis(10 * 60 * 1000L)
            .setTileTimeline(TimelineBuilders.Timeline.fromLayoutElement(root))
            .build()

    private fun layout(device: DeviceParameters, paired: Boolean, state: PanelState?): LayoutElementBuilders.LayoutElement {
        val open = ModifiersBuilders.Clickable.Builder()
            .setId("open")
            .setOnClick(
                ActionBuilders.LaunchAction.Builder()
                    .setAndroidActivity(
                        ActionBuilders.AndroidActivity.Builder()
                            .setPackageName(packageName)
                            .setClassName(MainActivity::class.java.name)
                            .build()
                    )
                    .build()
            )
            .build()
        val openChip = CompactChip.Builder(this, if (paired) "Open" else "Pair", open, device).build()

        if (!paired || state == null) {
            return PrimaryLayout.Builder(device)
                .setContent(text(if (paired) "Can't reach home" else "Open Kid Panel to pair", Typography.TYPOGRAPHY_BODY1))
                .setPrimaryChipContent(openChip)
                .build()
        }

        // The values open the app when tapped; the controls go in the chip under them and in the bottom chip, so two
        // fit (the bottom chip is "Open" when there's only one, or none)
        val values = LayoutElementBuilders.Column.Builder()
            .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
            .setModifiers(ModifiersBuilders.Modifiers.Builder().setClickable(open).build())
        state.views.firstOrNull()?.let { first ->
            values.addContent(text(first.name, Typography.TYPOGRAPHY_CAPTION2))
            values.addContent(text(Format.value(first), Typography.TYPOGRAPHY_DISPLAY3))
        }
        state.views.getOrNull(1)?.let { second ->
            values.addContent(text("${second.name}: ${Format.value(second)}", Typography.TYPOGRAPHY_CAPTION2))
        }
        val quick = quickControls(state)
        val column = LayoutElementBuilders.Column.Builder()
            .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
            .addContent(values.build())
        if (quick.size == 2) {
            column.addContent(LayoutElementBuilders.Spacer.Builder().setHeight(androidx.wear.protolayout.DimensionBuilders.dp(4f)).build())
            column.addContent(controlChip(device, quick[0]))
        }
        return PrimaryLayout.Builder(device)
            .setContent(column.build())
            .setPrimaryChipContent(quick.lastOrNull()?.let { controlChip(device, it) } ?: openChip)
            .build()
    }

    private fun controlChip(device: DeviceParameters, c: Control): LayoutElementBuilders.LayoutElement {
        val action = Actions.toggle(c) ?: "toggle"
        val clickable = ModifiersBuilders.Clickable.Builder()
            .setId("$ACT${c.entityId}|$action")
            .setOnClick(ActionBuilders.LoadAction.Builder().build())
            .build()
        val status = when {
            c.unavailable -> "Offline"
            c.domain == "scene" || c.domain == "script" -> "Run"
            c.on -> "On"
            else -> "Off"
        }
        val colours = if (c.on) ChipColors.primaryChipColors(Colors.DEFAULT) else ChipColors.secondaryChipColors(Colors.DEFAULT)
        val label = if (c.domain == "scene" || c.domain == "script") c.name else "${c.name} · $status"
        return CompactChip.Builder(this, label, clickable, device)
            .setChipColors(colours)
            .build()
    }

    private fun text(value: String, typography: Int) =
        Text.Builder(this, value)
            .setTypography(typography)
            .setColor(androidx.wear.protolayout.ColorBuilders.argb(0xFFE7EAF0.toInt()))
            .setMaxLines(1)
            .build()

    companion object {
        private const val RESOURCES = "1"
        private const val ACT = "act|"

        /** The controls that fit a tile: ones a single tap fully operates. */
        fun quickControls(state: PanelState): List<Control> =
            state.controls.filter { it.domain in setOf("light", "switch", "fan", "input_boolean", "scene", "script") }
                .take(2)
    }
}
