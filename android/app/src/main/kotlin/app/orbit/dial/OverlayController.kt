package app.orbit.dial

import android.accessibilityservice.AccessibilityService
import android.graphics.PixelFormat
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.WindowManager
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.SavedStateRegistry
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import app.orbit.dial.core.Hud
import app.orbit.dial.core.Tool
import app.orbit.dial.core.Ui

/** One wheel entry as the UI needs it. */
data class WheelItem(val id: String, val label: String, val icon: String, val sticky: Boolean)

/** Observable state the overlay composables render; mutated on the main thread only. */
class OverlayState {
    var items by mutableStateOf(emptyList<WheelItem>())
    var index by mutableIntStateOf(0)
    var shown by mutableStateOf(false)
    var selSteps by mutableIntStateOf(0)            // cumulative, so wrap-around animates forward
    var lastDir by mutableIntStateOf(0)
    var openSeq by mutableIntStateOf(0)
    var commitSeq by mutableIntStateOf(0)
    var cancelSeq by mutableIntStateOf(0)
    var hud by mutableStateOf<Hud?>(null)
    var hudShown by mutableStateOf(false)
    var hudSeq by mutableIntStateOf(0)
}

/**
 * Two small TYPE_ACCESSIBILITY_OVERLAY windows (wheel, HUD). Trusted overlays never
 * block touches underneath (Android 12 untrusted-touch rule) and need no extra
 * permission. Both stay attached; the composables animate in and out.
 */
class OverlayController(private val svc: AccessibilityService) : Ui {
    val state = OverlayState()
    private val wm = svc.getSystemService(WindowManager::class.java)
    private val main = Handler(Looper.getMainLooper())
    private val owner = OverlayOwner().also { it.create() }
    private val hideHud = Runnable { state.hudShown = false }
    private val views = listOf(
        add(Gravity.CENTER, 0) { WheelOverlay(state) },
        add(Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL, (110 * svc.resources.displayMetrics.density).toInt()) { HudOverlay(state) },
    )

    private fun add(gravity: Int, y: Int, content: @androidx.compose.runtime.Composable () -> Unit): ComposeView {
        val v = ComposeView(svc).apply {
            setViewTreeLifecycleOwner(owner)
            setViewTreeSavedStateRegistryOwner(owner)
            setViewTreeViewModelStoreOwner(owner)
            setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnDetachedFromWindow)
            setContent { content() }
        }
        val lp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
            PixelFormat.TRANSLUCENT,
        ).apply { this.gravity = gravity; this.y = y; title = "Orbit" }
        wm.addView(v, lp)
        return v
    }

    fun destroy() {
        views.forEach { runCatching { wm.removeView(it) } }
        owner.destroy()
    }

    // ---- Ui
    override fun wheelOpen(items: List<Tool>, index: Int) = main.post {
        state.items = items.map { WheelItem(it.id, it.label, it.icon, it.sticky) }
        state.index = index
        state.selSteps = index
        state.lastDir = 0
        state.hudShown = false
        state.shown = true
        state.openSeq++
    }.let {}

    override fun wheelMove(index: Int, direction: Int) = main.post {
        val n = state.items.size.coerceAtLeast(1)
        var d = ((index - state.index) % n + n) % n
        if (direction < 0 && d != 0) d -= n
        state.selSteps += d
        state.index = index
        state.lastDir = direction
    }.let {}

    override fun wheelCommit(index: Int) = main.post {
        state.index = index; state.shown = false; state.commitSeq++
    }.let {}

    override fun wheelCancel() = main.post { state.shown = false; state.cancelSeq++ }.let {}

    override fun hud(h: Hud) = main.post {
        if (state.shown) return@post
        state.hud = h
        state.hudShown = true
        state.hudSeq++
        main.removeCallbacks(hideHud)
        main.postDelayed(hideHud, 1400)
    }.let {}
}

/** Lifecycle/saved-state owners a ComposeView needs outside an Activity. */
private class OverlayOwner : LifecycleOwner, SavedStateRegistryOwner, ViewModelStoreOwner {
    private val lc = LifecycleRegistry(this)
    private val ss = SavedStateRegistryController.create(this)
    override val lifecycle: Lifecycle get() = lc
    override val savedStateRegistry: SavedStateRegistry get() = ss.savedStateRegistry
    override val viewModelStore = ViewModelStore()
    fun create() { ss.performRestore(null); lc.currentState = Lifecycle.State.RESUMED }
    fun destroy() { lc.currentState = Lifecycle.State.DESTROYED; viewModelStore.clear() }
}
