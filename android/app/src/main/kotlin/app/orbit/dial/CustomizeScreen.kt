package app.orbit.dial

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import app.orbit.dial.core.Kind
import app.orbit.dial.core.OrbitSettings
import app.orbit.dial.core.Tool
import app.orbit.dial.core.defaultTools
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

private val GESTURE_NAMES = mapOf(Kind.CLICK to "Press", Kind.DOUBLE to "Double press",
    Kind.TRIPLE to "Triple press", Kind.HOLD to "Press and hold")

private val PRESETS = listOf(
    "Open the wheel" to OrbitSettings.OPEN_WHEEL,
    "Play / pause" to "media:play_pause",
    "Next track" to "media:next",
    "Previous track" to "media:previous",
    "Back to previous tool" to "last_tool",
    "Open Claude" to "launch:com.anthropic.claude",
    "Screenshot" to "global:screenshot",
    "Home" to "global:home",
    "Back" to "global:back",
    "Recent apps" to "global:recents",
    "Notifications" to "global:notifications",
    "Nothing" to "none",
)
private const val MAX_ITEMS = 12

/** Wheel items (Yes/No + order), the tool to start with, and what each press does.
 *  Every change is saved at once; the accessibility service rebuilds its engine. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CustomizeScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val all = remember { defaultTools() }
    val byId = remember { all.associateBy { it.id } }
    var s by remember { mutableStateOf(SettingsStore.load(ctx)) }
    fun update(n: OrbitSettings) { s = n; SettingsStore.save(ctx, n) }
    val options = PRESETS + all.filter { it.sticky }.map { "Switch to ${it.label}" to "tool:${it.id}" }
    fun nameOf(v: String) = options.firstOrNull { it.second == v }?.first ?: v
    val wheel = s.wheel(all)
    val opens = OrbitSettings.GESTURES.filter { s.gestures[it] == OrbitSettings.OPEN_WHEEL }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopAppBar(
                title = { Text("Customize") },
                navigationIcon = {
                    IconButton(onBack) { Icon(painterResource(R.drawable.ic_arrow_left), "Back") }
                },
                actions = {
                    TextButton({ SettingsStore.reset(ctx); s = SettingsStore.load(ctx) }) {
                        Icon(painterResource(R.drawable.ic_rotate_ccw), null, Modifier.size(16.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Reset")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { pad ->
        LazyColumn(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = pad.calculateTopPadding(),
            bottom = pad.calculateBottomPadding() + 24.dp)) {
            item {
                WheelPreview(wheel, s.defaultTool)
                Text(
                    (if (opens.isEmpty()) "Open it with a triple press." else
                        "Open it with a " + opens.joinToString(" or ") { GESTURE_NAMES.getValue(it).lowercase() } + ".") +
                        " Turn to pick, press to choose.",
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 4.dp),
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
            item { Section("Wheel items", "Switch on what the wheel shows. The order runs clockwise from the top.") }
            item {
                Group {
                    s.order.forEachIndexed { i, id ->
                        val t = byId[id] ?: return@forEachIndexed
                        if (i > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        ToolRow(t, id in s.enabled, first = i == 0, last = i == s.order.lastIndex,
                            onToggle = { on ->
                                val en = if (on) s.enabled + id else s.enabled - id
                                if (en.isNotEmpty() && en.size <= MAX_ITEMS) update(s.copy(enabled = en))
                            },
                            onMove = { d ->
                                val j = i + d
                                if (j in s.order.indices) update(s.copy(order = s.order.toMutableList().also {
                                    it[i] = it[j]; it[j] = id
                                }))
                            })
                    }
                }
                if (s.enabled.size == 1) Hint("The wheel needs at least one item.")
            }
            item { Section("Dial", "What the dial does when the wheel is closed.") }
            item {
                Group {
                    PickerRow({ Icon(painterResource(R.drawable.ic_star), null, Modifier.size(20.dp)) },
                        "Start with", byId[s.defaultTool]?.label ?: s.defaultTool,
                        all.filter { it.sticky }.map { it.label to it.id }, s.defaultTool) { update(s.copy(defaultTool = it)) }
                    OrbitSettings.GESTURES.forEach { k ->
                        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        val v = s.gestures.getValue(k)
                        PickerRow({ Pips(k) }, GESTURE_NAMES.getValue(k), nameOf(v), options, v) {
                            update(s.copy(gestures = s.gestures + (k to it)))
                        }
                    }
                }
                if (opens.isEmpty()) Hint("No gesture opens the wheel, so a triple press will.", warn = true)
            }
        }
    }
}

// ---------------------------------------------------------------- pieces
@Composable
private fun Section(title: String, sub: String) {
    Column(Modifier.padding(start = 4.dp, end = 4.dp, top = 28.dp, bottom = 12.dp)) {
        Text(title, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onSurface)
        Spacer(Modifier.height(4.dp))
        Text(sub, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun Group(content: @Composable () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surfaceContainer, shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth()) { Column { content() } }
}

@Composable
private fun Hint(text: String, warn: Boolean = false) {
    Text(text, style = MaterialTheme.typography.bodySmall,
        color = if (warn) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(start = 4.dp, top = 8.dp))
}

@Composable
private fun ToolRow(t: Tool, on: Boolean, first: Boolean, last: Boolean,
                    onToggle: (Boolean) -> Unit, onMove: (Int) -> Unit) {
    val ink by animateColorAsState(
        if (on) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
        label = "rowInk")
    ListItem(
        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        leadingContent = { Icon(painterResource(orbitIcon(t.icon)), null, Modifier.size(22.dp), tint = ink) },
        headlineContent = { Text(t.label, color = ink, fontWeight = FontWeight.Medium) },
        supportingContent = {
            Text((if (on) "Yes" else "No") + if (t.sticky) "" else " · runs once",
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        },
        trailingContent = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton({ onMove(-1) }, enabled = !first) {
                    Icon(painterResource(R.drawable.ic_chevron_up), "Move ${t.label} up", Modifier.size(20.dp))
                }
                IconButton({ onMove(1) }, enabled = !last) {
                    Icon(painterResource(R.drawable.ic_chevron_down), "Move ${t.label} down", Modifier.size(20.dp))
                }
                Spacer(Modifier.width(4.dp))
                Switch(on, onToggle, Modifier.semantics { contentDescription = "Show ${t.label} on the wheel" })
            }
        },
    )
}

@Composable
private fun PickerRow(lead: @Composable () -> Unit, label: String, value: String,
                      options: List<Pair<String, String>>, current: String, onPick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        ListItem(
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
            modifier = Modifier.fillMaxWidth().clickable { open = true },
            leadingContent = { Box(Modifier.width(28.dp), contentAlignment = Alignment.Center) { lead() } },
            headlineContent = { Text(label, fontWeight = FontWeight.Medium) },
            supportingContent = { Text(value, color = MaterialTheme.colorScheme.primary) },
            trailingContent = {
                Icon(painterResource(R.drawable.ic_chevron_down), null, Modifier.size(20.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
            },
        )
        DropdownMenu(open, { open = false }, offset = androidx.compose.ui.unit.DpOffset(56.dp, 0.dp)) {
            options.forEachIndexed { i, (l, v) ->
                if (i > 0 && v.startsWith("tool:") && !options[i - 1].second.startsWith("tool:")) {
                    HorizontalDivider(Modifier.padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant)
                }
                DropdownMenuItem(
                    text = { Text(l, color = if (v == current) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface) },
                    onClick = { open = false; onPick(v) })
            }
        }
    }
}

/** One, two or three taps, or one long press: how the gesture feels on the dial. */
@Composable
private fun Pips(k: Kind) {
    val c = MaterialTheme.colorScheme.onSurfaceVariant
    Canvas(Modifier.size(28.dp, 16.dp)) {
        val cy = size.height / 2
        if (k == Kind.HOLD) {
            drawLine(c, Offset(3.dp.toPx(), cy), Offset(size.width - 3.dp.toPx(), cy), 6.dp.toPx(), StrokeCap.Round)
        } else {
            val n = when (k) { Kind.CLICK -> 1; Kind.DOUBLE -> 2; else -> 3 }
            for (i in 0 until n) drawCircle(c, 3.dp.toPx(), Offset((5 + i * 8).dp.toPx(), cy))
        }
    }
}

/** The wheel as the overlay draws it: enabled items around the ring, the start tool lit.
 *  Items glide to their new places when switched or reordered. */
@Composable
private fun WheelPreview(items: List<Tool>, start: String) {
    val accent = MaterialTheme.colorScheme.primary
    val n = items.size.coerceAtLeast(1)
    val dia = 248.dp
    val orbit = 84.dp
    Box(Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 12.dp), contentAlignment = Alignment.Center) {
        Box(Modifier.size(dia).shadow(16.dp, CircleShape).background(Color(0xFF13151A), CircleShape),
            contentAlignment = Alignment.Center) {
            val startIdx = items.indexOfFirst { it.id == start }
            val litAngle by animateFloatAsState(if (startIdx < 0) 0f else startIdx * 360f / n,
                spring(0.7f, Spring.StiffnessMediumLow), label = "lit")
            Canvas(Modifier.size(dia)) {
                val c = Offset(size.width / 2, size.height / 2)
                val rim = size.width / 2 - 12.dp.toPx()
                drawCircle(Color.White.copy(alpha = 0.07f), rim, c, style = Stroke(1.dp.toPx()))
                if (startIdx >= 0) {
                    drawArc(accent, litAngle - 90f - 14f, 28f, false, Offset(c.x - rim, c.y - rim), Size(rim * 2, rim * 2),
                        style = Stroke(3.dp.toPx(), cap = StrokeCap.Round))
                }
            }
            items.forEachIndexed { i, t ->
                val a by animateFloatAsState(i * 360f / n, spring(0.75f, Spring.StiffnessLow), label = "a_${t.id}")
                val rad = Math.toRadians(a.toDouble())
                val lit = t.id == start
                Box(Modifier.offset { IntOffset((orbit.toPx() * sin(rad)).roundToInt(), (-orbit.toPx() * cos(rad)).roundToInt()) }
                    .size(40.dp).background(if (lit) accent.copy(alpha = 0.18f) else Color.Transparent, CircleShape),
                    contentAlignment = Alignment.Center) {
                    Icon(painterResource(orbitIcon(t.icon)), t.label, Modifier.size(20.dp),
                        tint = if (lit) Color.White else Color.White.copy(alpha = 0.62f))
                }
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(items.firstOrNull { it.id == start }?.label ?: "—", color = Color.White,
                    style = MaterialTheme.typography.titleMedium)
                Text("${items.size} item${if (items.size == 1) "" else "s"}", color = Color.White.copy(alpha = 0.55f),
                    style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}
