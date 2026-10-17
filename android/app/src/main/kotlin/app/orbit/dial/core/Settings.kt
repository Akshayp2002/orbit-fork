package app.orbit.dial.core

/**
 * What the user picked on the "Customize wheel" screen. Same model as the desktop
 * settings.json (orbit/core/settings.py): every tool in wheel order, which are on,
 * the tool to start with, and an action string per press gesture.
 *
 * Gesture strings (shared with desktop): open_wheel | media:play_pause|next|previous |
 * launch:<package> | global:home|back|recents|notifications|quick_settings|screenshot|lock |
 * last_tool | tool:<id> | none
 */
data class OrbitSettings(
    val order: List<String>,
    val enabled: Set<String>,
    val defaultTool: String,
    val gestures: Map<Kind, String>,
    /** system | dark | light */
    val appearance: String = "system",
) {
    companion object {
        val GESTURES = listOf(Kind.CLICK, Kind.DOUBLE, Kind.TRIPLE, Kind.HOLD)
        const val OPEN_WHEEL = "open_wheel"
        /** On the list (switch them on in Customize), off the wheel until then. */
        val HIDDEN_BY_DEFAULT = setOf("zoom", "claude")
        val APPEARANCES = listOf("system", "dark", "light")

        fun defaults(tools: List<Tool>) = OrbitSettings(
            order = tools.map { it.id },
            enabled = tools.map { it.id }.toSet() - HIDDEN_BY_DEFAULT,
            defaultTool = "volume",
            gestures = mapOf(
                Kind.CLICK to "media:play_pause",
                Kind.DOUBLE to OPEN_WHEEL,
                Kind.TRIPLE to "last_tool",
                Kind.HOLD to "launch:com.anthropic.claude",
            ),
        )

        fun parseGesture(spec: String): Gesture? {
            val (kind, arg) = spec.split(":", limit = 2).let { it[0] to it.getOrElse(1) { "" } }
            return when (kind) {
                OPEN_WHEEL -> Gesture.OpenWheel
                "media" -> Gesture.Media(arg)
                "launch" -> Gesture.Launch(arg)
                "global" -> Gesture.Global(arg)
                "last_tool" -> Gesture.LastTool
                "tool" -> Gesture.SwitchTo(arg)
                else -> null
            }
        }
    }

    /** Tools in wheel order, only the enabled ones; never empty. */
    fun wheel(all: List<Tool>): List<Tool> {
        val byId = all.associateBy { it.id }
        val ordered = (order.filter { it in byId } + all.map { it.id }.filter { it !in order }).distinct()
        return ordered.filter { it in enabled }.mapNotNull { byId[it] }.ifEmpty { all.take(1) }
    }

    /** Settings with every tool id known (new tools appended, enabled), unknown ones dropped. */
    fun normalized(all: List<Tool>): OrbitSettings {
        val ids = all.map { it.id }
        val newIds = ids.filter { it !in order }
        return copy(
            order = order.filter { it in ids } + newIds,
            enabled = enabled.filter { it in ids }.toSet() + (newIds - HIDDEN_BY_DEFAULT),
            defaultTool = defaultTool.takeIf { it in ids } ?: ids.first(),
            appearance = appearance.takeIf { it in APPEARANCES } ?: "system",
        )
    }

    /** Gestures that open the wheel; triple if none was left (there must be a way in). */
    fun openWith(): Set<Kind> =
        gestures.filterValues { it == OPEN_WHEEL }.keys.ifEmpty { setOf(Kind.TRIPLE) }

    fun globalGestures(): Map<Kind, Gesture> =
        gestures.filterValues { it != OPEN_WHEEL }.mapNotNull { (k, v) -> parseGesture(v)?.let { k to it } }.toMap()

    fun buildEngine(actions: Actions, ui: Ui, rotation: RotationControl?, all: List<Tool>): Engine {
        val s = normalized(all)
        return Engine(actions, ui, rotation, all, s.defaultTool, s.globalGestures(), s.openWith(),
                      duck = null, wheelIds = s.wheel(all).map { it.id })
    }
}
