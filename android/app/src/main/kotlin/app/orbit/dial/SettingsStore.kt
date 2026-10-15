package app.orbit.dial

import android.content.Context
import android.content.SharedPreferences
import app.orbit.dial.core.Kind
import app.orbit.dial.core.OrbitSettings
import app.orbit.dial.core.defaultTools

/** OrbitSettings in SharedPreferences. The accessibility service listens and rebuilds its engine. */
object SettingsStore {
    private const val ORDER = "wheel_order"
    private const val ENABLED = "wheel_enabled"
    private const val START = "default_tool"
    private fun gKey(k: Kind) = "gesture_${k.name.lowercase()}"
    val KEYS = setOf(ORDER, ENABLED, START) + OrbitSettings.GESTURES.map(::gKey)

    fun load(ctx: Context): OrbitSettings {
        val all = defaultTools()
        val d = OrbitSettings.defaults(all)
        val p = Orbit.prefs(ctx)
        fun list(key: String): List<String>? = p.getString(key, null)?.split(",")?.filter { it.isNotBlank() }
        return OrbitSettings(
            order = list(ORDER) ?: d.order,
            enabled = list(ENABLED)?.toSet() ?: d.enabled,
            defaultTool = p.getString(START, null) ?: d.defaultTool,
            gestures = OrbitSettings.GESTURES.associateWith { p.getString(gKey(it), null) ?: d.gestures.getValue(it) },
        ).normalized(all)
    }

    fun save(ctx: Context, s: OrbitSettings) {
        Orbit.prefs(ctx).edit().apply {
            putString(ORDER, s.order.joinToString(","))
            putString(ENABLED, s.order.filter { it in s.enabled }.joinToString(","))
            putString(START, s.defaultTool)
            s.gestures.forEach { (k, v) -> putString(gKey(k), v) }
        }.apply()
    }

    fun reset(ctx: Context) {
        Orbit.prefs(ctx).edit().apply { KEYS.forEach(::remove) }.apply()
    }

    fun listen(ctx: Context, onChange: () -> Unit): SharedPreferences.OnSharedPreferenceChangeListener {
        val l = SharedPreferences.OnSharedPreferenceChangeListener { _, key -> if (key == null || key in KEYS) onChange() }
        Orbit.prefs(ctx).registerOnSharedPreferenceChangeListener(l)
        return l
    }
}
