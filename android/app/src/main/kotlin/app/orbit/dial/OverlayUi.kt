package app.orbit.dial

import android.annotation.SuppressLint
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.graphics.drawable.toBitmap
import kotlinx.coroutines.launch
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin

// Same palette and proportions as the desktop QML overlay.
/** The overlay palette for dark or light; the highlighted item is the light source. */
data class OverlayLook(val dark: Boolean) {
    val accent = if (dark) Color(0xFF7C9CFF) else Color(0xFF4F67C4)
    val ink = if (dark) Color(0xFFF4F6FB) else Color(0xFF12141A)
    val inkDim = if (dark) Color(0x80FFFFFF) else Color(0x7A0D0F17)
    val surface = if (dark) Color(0xFF0A0B0F) else Color(0xFFFBFBFE)
    val edge = if (dark) Color(0x12FFFFFF) else Color(0x14000000)
    val light = if (dark) 1f else 0.8f
    fun fg(a: Float) = if (dark) Color.White.copy(alpha = a) else Color(0xFF0D0F17).copy(alpha = a)
}

val LocalOverlayLook = staticCompositionLocalOf { OverlayLook(dark = true) }

@Composable
fun rememberOverlayLook(appearance: String): OverlayLook {
    val system = isSystemInDarkTheme()
    val dark = when (appearance) { "dark" -> true; "light" -> false; else -> system }
    return remember(dark) { OverlayLook(dark) }
}

private val Accent: Color @Composable get() = LocalOverlayLook.current.accent
private val Ink: Color @Composable get() = LocalOverlayLook.current.ink
private val InkDim: Color @Composable get() = LocalOverlayLook.current.inkDim
private val Glass: Color @Composable get() = LocalOverlayLook.current.surface

@SuppressLint("DiscouragedApi")
@Composable
fun orbitIcon(name: String): Int {
    val ctx = LocalContext.current
    return remember(name) { ctx.resources.getIdentifier("ic_$name", "drawable", ctx.packageName).takeIf { it != 0 } ?: R.drawable.ic_star }
}

@Composable
fun WheelOverlay(s: OverlayState) {
    val alpha = remember { Animatable(0f) }
    val scale = remember { Animatable(0.86f) }
    val spin = remember { Animatable(-12f) }
    val openT = remember { Animatable(0f) }
    val pulse = remember { Animatable(1f) }
    val n = s.items.size.coerceAtLeast(1)
    val step = 360f / n
    val sel by animateFloatAsState(s.selSteps * step,
        spring(dampingRatio = 0.45f, stiffness = Spring.StiffnessMediumLow), label = "sel")
    val shift = remember { Animatable(0f) }

    LaunchedEffect(s.openSeq) {
        if (s.openSeq == 0) return@LaunchedEffect
        launch { alpha.snapTo(0f); alpha.animateTo(1f, tween(140)) }
        launch { scale.snapTo(0.86f); scale.animateTo(1f, spring(0.55f, Spring.StiffnessMediumLow)) }
        launch { spin.snapTo(-12f); spin.animateTo(0f, spring(0.5f, Spring.StiffnessLow)) }
        launch { openT.snapTo(0f); openT.animateTo(1f, tween(420, easing = FastOutSlowInEasing)) }
    }
    LaunchedEffect(s.commitSeq) {
        if (s.commitSeq == 0) return@LaunchedEffect
        pulse.animateTo(1.35f, tween(90)); launch { pulse.animateTo(1f, tween(160)) }
        launch { scale.animateTo(1.08f, tween(220)) }
        alpha.animateTo(0f, tween(220))
    }
    LaunchedEffect(s.cancelSeq) {
        if (s.cancelSeq == 0) return@LaunchedEffect
        launch { scale.animateTo(0.9f, tween(170)) }
        alpha.animateTo(0f, tween(170))
    }
    LaunchedEffect(s.index, s.lastDir) {
        if (s.lastDir != 0) { shift.snapTo(s.lastDir * 14f); shift.animateTo(0f, spring(0.5f, Spring.StiffnessMedium)) }
    }

    val dia = 300.dp
    val rad = 103.dp
    val look = LocalOverlayLook.current
    Box(Modifier.size(dia + 92.dp), contentAlignment = Alignment.Center) {
        if (alpha.value <= 0.001f && !s.shown) return@Box
        Box(Modifier.size(dia + 92.dp).graphicsLayer {
            this.alpha = alpha.value; scaleX = scale.value; scaleY = scale.value; rotationZ = spin.value
        }, contentAlignment = Alignment.Center) {
            // light spilling past the rim, nearest the highlighted item (drawn under the disc)
            Canvas(Modifier.size(dia + 92.dp)) {
                val c = Offset(size.width / 2, size.height / 2)
                val R = dia.toPx() / 2
                val a = Math.toRadians(sel.toDouble())
                val lp = Offset(c.x + rad.toPx() * sin(a).toFloat(), c.y - rad.toPx() * cos(a).toFloat())
                val k = look.light * (0.75f + 0.25f * pulse.value)
                drawCircle(
                    Brush.radialGradient(
                        0f to look.accent.copy(alpha = 0.30f * k), 0.18f to look.accent.copy(alpha = 0.20f * k),
                        0.40f to look.accent.copy(alpha = 0.07f * k), 0.70f to look.accent.copy(alpha = 0.015f * k),
                        1f to Color.Transparent, center = lp, radius = R * 0.84f),
                    radius = R + 23.dp.toPx(), center = c, style = Stroke(46.dp.toPx()))
            }
            Box(
                Modifier.size(dia).shadow(18.dp, CircleShape).background(Glass, CircleShape)
                    .border(1.dp, look.edge, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Canvas(Modifier.size(dia)) {
                    val c = Offset(size.width / 2, size.height / 2)
                    val R = size.width / 2
                    val a = Math.toRadians(sel.toDouble())
                    val lp = Offset(c.x + rad.toPx() * sin(a).toFloat(), c.y - rad.toPx() * cos(a).toFloat())
                    val k = look.light * (0.75f + 0.25f * pulse.value)
                    // light across the disc, natural falloff from the item
                    drawCircle(
                        Brush.radialGradient(
                            0f to look.accent.copy(alpha = 0.34f * k), 0.08f to look.accent.copy(alpha = 0.24f * k),
                            0.20f to look.accent.copy(alpha = 0.12f * k), 0.38f to look.accent.copy(alpha = 0.05f * k),
                            0.60f to look.accent.copy(alpha = 0.015f * k), 1f to Color.Transparent,
                            center = lp, radius = size.width * 0.62f),
                        radius = R - 1f, center = c)
                    // the rim catching it: brightest nearest the item, fading both ways
                    val rr = R - 0.75.dp.toPx()
                    val sw = min(step * 1.1f, 96f)
                    val tl = Offset(c.x - rr, c.y - rr)
                    val sz = Size(rr * 2, rr * 2)
                    for ((span, al) in listOf(2f to 0.10f, 1.1f to 0.25f, 0.5f to 0.55f)) {
                        drawArc(look.accent.copy(alpha = al * k), sel - 90f - sw * span / 2, sw * span, false, tl, sz,
                            style = Stroke(1.5.dp.toPx(), cap = if (span < 1f) StrokeCap.Round else StrokeCap.Butt))
                    }
                    // faint track + ticks
                    val rimR = R - 12.dp.toPx()
                    drawCircle(look.fg(0.06f), rimR, c, style = Stroke(1.dp.toPx()))
                    for (i in 0 until n) {
                        if (i == s.index) continue
                        val t = Math.toRadians((i * step).toDouble())
                        val p1 = Offset(c.x + (rimR - 3.dp.toPx()) * sin(t).toFloat(), c.y - (rimR - 3.dp.toPx()) * cos(t).toFloat())
                        val p2 = Offset(c.x + (rimR + 3.dp.toPx()) * sin(t).toFloat(), c.y - (rimR + 3.dp.toPx()) * cos(t).toFloat())
                        drawLine(look.fg(0.16f), p1, p2, 2.dp.toPx(), StrokeCap.Round)
                    }
                }
            s.items.forEachIndexed { i, item ->
                val t = ((openT.value * 1.6f) - i * 0.06f).coerceIn(0f, 1f)
                val r = rad.value * (0.72f + 0.28f * t)
                val a = Math.toRadians((i * step).toDouble())
                val selected = i == s.index
                val itemScale by animateFloatAsState(if (selected) 1.16f else 1f, spring(0.4f, Spring.StiffnessMedium), label = "is$i")
                Box(
                    Modifier.offset { IntOffset((r * sin(a)).dp.roundToPx(), (-r * cos(a)).dp.roundToPx()) }
                        .size(48.dp).alpha(t * if (selected) 1f else 0.7f).scale(itemScale),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(painterResource(orbitIcon(item.icon)), item.label, Modifier.size(22.dp), tint = if (selected) (if (look.dark) Color.White else Accent) else InkDim)
                    if (!item.sticky) Box(Modifier.align(Alignment.BottomCenter).padding(bottom = 4.dp).size(4.dp).background(Accent, CircleShape))
                }
            }
            val cur = s.items.getOrNull(s.index)
            Column(Modifier.offset { IntOffset(shift.value.dp.roundToPx(), 0) }, horizontalAlignment = Alignment.CenterHorizontally) {
                if (cur != null) {
                    Icon(painterResource(orbitIcon(cur.icon)), cur.label, Modifier.size(34.dp), tint = Accent)
                    Spacer(Modifier.size(6.dp))
                    Text(cur.label, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    Text(if (cur.sticky) "press to use" else "press to run", color = look.fg(0.40f), fontSize = 11.sp)
                }
            }
            }
        }
    }
}

@Composable
fun HudOverlay(s: OverlayState) {
    val h = s.hud
    val a by animateFloatAsState(if (s.hudShown) 1f else 0f, tween(if (s.hudShown) 150 else 260), label = "hudA")
    val lift by animateFloatAsState(if (s.hudShown) 0f else 16f, spring(0.5f, Spring.StiffnessMediumLow), label = "hudY")
    val nudge = remember { Animatable(0f) }
    LaunchedEffect(s.hudSeq) {
        val d = h?.direction ?: 0
        if (d != 0) { nudge.snapTo(d * 16f); nudge.animateTo(0f, spring(0.3f, Spring.StiffnessMedium)) }
    }
    if (h == null || a <= 0.001f) { Box(Modifier.size(1.dp)); return }
    h.strip?.let { strip ->
        Box(Modifier.padding(horizontal = 20.dp, vertical = 28.dp)) { AppStripPanel(strip, h.title, a, lift, s.hudSeq) }
        return
    }
    // padding inside the window: room for the slide-in offset and the shadow, which
    // would otherwise be clipped by the WRAP_CONTENT window bounds
    Box(Modifier.padding(horizontal = 20.dp, vertical = 28.dp)) { HudPill(h, a, lift, nudge.value) }
}

private const val SLOT_DP = 58
private const val VISIBLE_SLOTS = 5

/** App switcher: recent apps in a row, the highlighted one centred and lifted, its
 *  name below, and a bar that fills until it opens (restarts with every click). */
@Composable
private fun AppStripPanel(strip: app.orbit.dial.core.AppStrip, title: String, a: Float, lift: Float, seq: Int) {
    val ctx = LocalContext.current
    val icons = remember(strip.apps) {
        strip.apps.associate { app ->
            app.pkg to runCatching {
                ctx.packageManager.getApplicationIcon(app.pkg).toBitmap(96, 96).asImageBitmap()
            }.getOrNull()
        }
    }
    val pos by animateFloatAsState(strip.index.toFloat(), spring(0.75f, Spring.StiffnessMediumLow), label = "stripPos")
    val countdown = remember { Animatable(0f) }
    val pulse = remember { Animatable(1f) }
    LaunchedEffect(seq) {
        if (strip.opened) {
            countdown.snapTo(1f)
            pulse.animateTo(1.18f, tween(110)); pulse.animateTo(1f, tween(170))
        } else {
            countdown.snapTo(0f)
            countdown.animateTo(1f, tween(strip.commitInMs.toInt(), easing = androidx.compose.animation.core.LinearEasing))
        }
    }
    val slot = SLOT_DP.dp
    Column(
        Modifier.graphicsLayer { alpha = a; translationY = lift * density }
            .shadow(14.dp, RoundedCornerShape(26.dp)).background(Glass, RoundedCornerShape(26.dp))
            .border(1.dp, LocalOverlayLook.current.edge, RoundedCornerShape(26.dp))
            .padding(top = 14.dp, bottom = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(Modifier.width(slot * VISIBLE_SLOTS).height(64.dp).clipToBounds()) {
            strip.apps.forEachIndexed { i, app ->
                val off = i - pos                                   // slots from the centre
                val near = (1f - kotlin.math.abs(off) / 2.6f).coerceIn(0f, 1f)
                val selected = i == strip.index
                Box(
                    Modifier.offset { IntOffset(((VISIBLE_SLOTS / 2 + off) * SLOT_DP).dp.roundToPx(), 0) }
                        .size(slot, 64.dp)
                        .graphicsLayer {
                            val sc = (0.78f + 0.3f * near) * if (selected) pulse.value else 1f
                            scaleX = sc; scaleY = sc; alpha = 0.25f + 0.75f * near
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    if (selected) Box(Modifier.size(54.dp).border(2.dp, Accent, RoundedCornerShape(16.dp)))
                    val img = icons[app.pkg]
                    if (img != null) Image(img, app.label, Modifier.size(44.dp))
                    else Icon(painterResource(orbitIcon("app")), app.label, Modifier.size(28.dp), tint = Ink)
                }
            }
        }
        Spacer(Modifier.size(6.dp))
        Text(title, color = Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.size(8.dp))
        Box(Modifier.size(96.dp, 3.dp).background(LocalOverlayLook.current.fg(0.10f), RoundedCornerShape(2.dp))) {
            Box(Modifier.fillMaxHeight().width(96.dp * countdown.value).background(Accent, RoundedCornerShape(2.dp)))
        }
    }
}

@Composable
private fun HudPill(h: app.orbit.dial.core.Hud, a: Float, lift: Float, nudge: Float) {
    Row(
        Modifier.graphicsLayer { alpha = a; translationY = lift * density }
            .shadow(10.dp, RoundedCornerShape(50)).background(Glass, RoundedCornerShape(50))
            .border(1.dp, LocalOverlayLook.current.edge, RoundedCornerShape(50))
            .padding(start = 10.dp, end = 18.dp, top = 9.dp, bottom = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(34.dp).background(Accent.copy(alpha = 0.18f), CircleShape), contentAlignment = Alignment.Center) {
            Icon(painterResource(orbitIcon(h.icon)), h.title, Modifier.size(17.dp).graphicsLayer { rotationZ = nudge }, tint = Accent)
        }
        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(h.title, color = Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                if (h.detail.isNotEmpty()) Text(h.detail, color = InkDim, fontSize = 15.sp)
            }
            h.progress?.let { p ->
                val pw by animateFloatAsState(p.coerceIn(0f, 1f), spring(0.6f, Spring.StiffnessMedium), label = "hudP")
                Box(Modifier.width(140.dp).size(140.dp, 4.dp).background(LocalOverlayLook.current.fg(0.10f), RoundedCornerShape(2.dp))) {
                    Box(Modifier.fillMaxHeight().width(140.dp * pw).background(Accent, RoundedCornerShape(2.dp)))
                }
            }
        }
    }
}
