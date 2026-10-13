package io.github.thesiegs.kidpanel

import android.content.Context
import androidx.wear.tiles.TileService

/** The panel as both the app and the tile see it: paired or not, its last state, and what it can do. */
class Panel(context: Context, private val client: PanelClient = PanelClient()) {
    private val appContext = context.applicationContext
    val store = PairingStore(appContext)

    val paired get() = store.path != null

    /** The last state seen, for showing something before the network answers. */
    fun cached(): PanelState? = store.lastState?.let { runCatching { PanelState.parse(it) }.getOrNull() }

    /** Fetches the state; forgets the pairing when the panel no longer knows this watch. */
    suspend fun refresh(): PanelState {
        val path = store.path ?: throw PanelError.Unpaired()
        try {
            val json = client.stateJson(path)
            store.lastState = json
            return PanelState.parse(json)
        } catch (e: PanelError.Unpaired) {
            unpair()
            throw e
        }
    }

    suspend fun act(entityId: String, action: String, value: Any? = null) {
        val path = store.path ?: throw PanelError.Unpaired()
        try {
            client.act(path, entityId, action, value)
        } catch (e: PanelError.Unpaired) {
            unpair()
            throw e
        }
        updateTile()
    }

    suspend fun pair(code: String) {
        val (path, title) = client.pair(code)
        store.path = path
        store.title = title
        store.lastState = null
        updateTile()
    }

    fun unpair() {
        store.clear()
        updateTile()
    }

    /** Asks the system to redraw the tile; best effort, since a tile that isn't added can refuse. */
    fun updateTile() {
        runCatching { TileService.getUpdater(appContext).requestUpdate(PanelTileService::class.java) }
    }
}
