package app.orbit.dial

import android.annotation.SuppressLint
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin

// Same palette and proportions as the desktop QML overlay.
private val Accent = Color(0xFF7C9CFF)
private val Ink = Color(0xFFF4F6FB)
private val InkDim = Color(0x85FFFFFF)
private val Glass = Color(0xFF13151A)

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
    Box(Modifier.size(dia + 40.dp), contentAlignment = Alignment.Center) {
        if (alpha.value <= 0.001f && !s.shown) return@Box
        Box(
            Modifier.size(dia).graphicsLayer {
                this.alpha = alpha.value; scaleX = scale.value; scaleY = scale.value; rotationZ = spin.value
            }.shadow(18.dp, CircleShape).background(Glass, CircleShape)
                .border(1.dp, Color.White.copy(alpha = 0.08f), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Canvas(Modifier.size(dia)) {
                val c = Offset(size.width / 2, size.height / 2)
                val rimR = size.width / 2 - 12.dp.toPx()
                drawCircle(Color.White.copy(alpha = 0.07f), rimR, c, style = Stroke(1.dp.toPx()))
                for (i in 0 until n) {
                    if (i == s.index) continue
                    val a = Math.toRadians((i * step).toDouble())
                    val p1 = Offset(c.x + (rimR - 3.dp.toPx()) * sin(a).toFloat(), c.y - (rimR - 3.dp.toPx()) * cos(a).toFloat())
                    val p2 = Offset(c.x + (rimR + 3.dp.toPx()) * sin(a).toFloat(), c.y - (rimR + 3.dp.toPx()) * cos(a).toFloat())
                    drawLine(Color.White.copy(alpha = 0.18f), p1, p2, 2.dp.toPx(), StrokeCap.Round)
                }
                val sweep = min(step * 0.62f, 70f)
                val tl = Offset(c.x - rimR, c.y - rimR)
                val sz = Size(rimR * 2, rimR * 2)
                drawArc(Accent.copy(alpha = 0.22f), sel - 90f - sweep / 2, sweep, false, tl, sz, style = Stroke(12.dp.toPx(), cap = StrokeCap.Round))
                drawArc(Accent, sel - 90f - sweep / 2, sweep, false, tl, sz, style = Stroke(3.5f.dp.toPx(), cap = StrokeCap.Round))
                val a = Math.toRadians(sel.toDouble())
                val pc = Offset(c.x + rad.toPx() * sin(a).toFloat(), c.y - rad.toPx() * cos(a).toFloat())
                val pr = 26.dp.toPx() * pulse.value
                drawCircle(Accent.copy(alpha = 0.20f), pr, pc)
                drawCircle(Accent.copy(alpha = 0.55f), pr, pc, style = Stroke(1.dp.toPx()))
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
                    Icon(painterResource(orbitIcon(item.icon)), item.label, Modifier.size(22.dp), tint = if (selected) Ink else InkDim)
                    if (!item.sticky) Box(Modifier.align(Alignment.BottomCenter).padding(bottom = 4.dp).size(4.dp).background(Accent, CircleShape))
                }
            }
            val cur = s.items.getOrNull(s.index)
            Column(Modifier.offset { IntOffset(shift.value.dp.roundToPx(), 0) }, horizontalAlignment = Alignment.CenterHorizontally) {
                if (cur != null) {
                    Icon(painterResource(orbitIcon(cur.icon)), cur.label, Modifier.size(34.dp), tint = Accent)
                    Spacer(Modifier.size(6.dp))
                    Text(cur.label, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    Text(if (cur.sticky) "press to use" else "press to run", color = Color.White.copy(alpha = 0.38f), fontSize = 11.sp)
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
    // padding inside the window: room for the slide-in offset and the shadow, which
    // would otherwise be clipped by the WRAP_CONTENT window bounds
    Box(Modifier.padding(horizontal = 20.dp, vertical = 28.dp)) { HudPill(h, a, lift, nudge.value) }
}

@Composable
private fun HudPill(h: app.orbit.dial.core.Hud, a: Float, lift: Float, nudge: Float) {
    Row(
        Modifier.graphicsLayer { alpha = a; translationY = lift * density }
            .shadow(10.dp, RoundedCornerShape(50)).background(Glass, RoundedCornerShape(50))
            .border(1.dp, Color.White.copy(alpha = 0.08f), RoundedCornerShape(50))
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
                Box(Modifier.width(140.dp).size(140.dp, 4.dp).background(Color.White.copy(alpha = 0.10f), RoundedCornerShape(2.dp))) {
                    Box(Modifier.fillMaxHeight().width(140.dp * pw).background(Accent, RoundedCornerShape(2.dp)))
                }
            }
        }
    }
}
