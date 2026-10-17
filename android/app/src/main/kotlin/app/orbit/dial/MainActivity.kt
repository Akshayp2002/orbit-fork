package app.orbit.dial

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.orbit.dial.core.DialEvent
import app.orbit.dial.core.Kind

/** Orbit's dark world as Material roles (same palette as the wheel overlay and desktop). */
val OrbitColors = darkColorScheme(
    primary = Color(0xFF8FA8FF), onPrimary = Color(0xFF0B1230),
    primaryContainer = Color(0xFF26325C), onPrimaryContainer = Color(0xFFDCE3FF),
    secondary = Color(0xFFB7C1DE), onSecondary = Color(0xFF1E2538),
    tertiary = Color(0xFFF2B46B), onTertiary = Color(0xFF3A2400),
    background = Color(0xFF101217), onBackground = Color(0xFFF2F4F8),
    surface = Color(0xFF101217), onSurface = Color(0xFFF2F4F8),
    surfaceVariant = Color(0xFF20242D), onSurfaceVariant = Color(0xFFA4AAB8),
    surfaceContainerLowest = Color(0xFF0B0D11), surfaceContainerLow = Color(0xFF151820),
    surfaceContainer = Color(0xFF1A1D25), surfaceContainerHigh = Color(0xFF20242D),
    surfaceContainerHighest = Color(0xFF272B35),
    outline = Color(0xFF4A5060), outlineVariant = Color(0xFF262A34),
)

/** Setup checklist (each step re-checked on resume), test buttons, live log. */
class MainActivity : ComponentActivity() {
    private var refresh by mutableIntStateOf(0)
    private var customizing by mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        applyDebugExtras(intent)
        setContent {
            MaterialTheme(colorScheme = OrbitColors) {
                if (customizing) {
                    BackHandler { customizing = false }
                    CustomizeScreen { customizing = false }
                } else Setup(refresh)
            }
        }
    }

    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); applyDebugExtras(intent) }
    override fun onResume() { super.onResume(); refresh++ ; if (a11yOn()) OrbitMediaService.start(this) }

    /** adb shell am start -n app.orbit.dial/.MainActivity --ez require_bt false  (emulator testing) */
    private fun applyDebugExtras(i: Intent) {
        if (i.getBooleanExtra("customize", false)) customizing = true
        if (i.hasExtra("require_bt")) Orbit.setRequireBluetooth(this, i.getBooleanExtra("require_bt", true))
        i.getStringExtra("emit")?.let { spec ->           // --es emit "rotate:1" | "double" | "click" ...
            val (k, d) = (spec.split(":") + "0").let { it[0] to it[1].toIntOrNull() }
            runCatching { Orbit.emit(DialEvent(Kind.valueOf(k.uppercase()), d ?: 0, "intent")) }
        }
    }

    // ---- status checks
    fun a11yOn(): Boolean {
        val want = ComponentName(this, OrbitAccessibilityService::class.java).flattenToString()
        val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false
        return TextUtils.SimpleStringSplitter(':').apply { setString(enabled) }.any { it.equals(want, true) }
    }
    fun listenerOn(): Boolean = (Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: "")
        .contains(ComponentName(this, OrbitNotificationListener::class.java).flattenToString())
    fun holdIsOurs(): Boolean = packageManager.resolveActivity(Intent(Intent.ACTION_VOICE_COMMAND),
        PackageManager.MATCH_DEFAULT_ONLY)?.activityInfo?.packageName == packageName
    fun notifOn(): Boolean = Build.VERSION.SDK_INT < 33 ||
        checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    fun writeOn(): Boolean = Settings.System.canWrite(this)

    @Composable
    private fun Setup(@Suppress("UNUSED_PARAMETER") tick: Int) {
        val log by Orbit.logLines.collectAsState()
        var disclosure by remember { mutableStateOf(false) }
        var requireBt by remember { mutableStateOf(Orbit.requireBluetooth(this)) }
        Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            Column(Modifier.systemBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Orbit", color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.Bold)
                Text("Turn the CMF Buds Pro 2 dial into a controller. Double-press: wheel. Turn: pick. Press: select.",
                    color = Color(0xB3FFFFFF), fontSize = 14.sp)
                Spacer(Modifier.size(4.dp))
                Step("1", "Notifications", "Shows the 'dial active' notification.", notifOn()) {
                    if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
                }
                Step("2", "Accessibility service", "Draws the wheel and performs actions.", a11yOn()) { disclosure = true }
                Step("3", "Notification access", "Lets a single press still play/pause your music app.", listenerOn()) {
                    startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                }
                Step("4", "Press-and-hold", "Hold opens Claude. Tap, then pick Orbit and 'Always'.", holdIsOurs()) {
                    startActivity(Intent(Intent.ACTION_VOICE_COMMAND).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }
                Step("5", "Modify system settings", "Optional: for the Brightness tool.", writeOn()) {
                    startActivity(Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:$packageName")))
                }
                Button({ customizing = true }, Modifier.fillMaxWidth()) { Text("Customize wheel and gestures") }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Only with Bluetooth earbuds", color = Color.White, fontSize = 15.sp)
                        Text("Off = any volume change counts as the dial (emulator / testing).", color = Color(0x99FFFFFF), fontSize = 12.sp)
                    }
                    Switch(requireBt, { requireBt = it; Orbit.setRequireBluetooth(this@MainActivity, it) })
                }
                Text("Try it without the buds", color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("Double" to DialEvent(Kind.DOUBLE), "◀" to DialEvent(Kind.ROTATE, -1),
                        "▶" to DialEvent(Kind.ROTATE, 1), "Press" to DialEvent(Kind.CLICK)).forEach { (l, e) ->
                        OutlinedButton({ Orbit.emit(e.copy(source = "test")) }) { Text(l) }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Log", color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    TextButton({
                        val cm = getSystemService(android.content.ClipboardManager::class.java)
                        cm.setPrimaryClip(android.content.ClipData.newPlainText("Orbit log",
                            "Orbit ${BuildConfig.VERSION_NAME} · Android ${Build.VERSION.RELEASE} · ${Build.MANUFACTURER} ${Build.MODEL}\n" +
                                Orbit.logLines.value.joinToString("\n")))
                        android.widget.Toast.makeText(this@MainActivity, "Log copied", android.widget.Toast.LENGTH_SHORT).show()
                    }) { Text("Copy log") }
                }
                Column(Modifier.fillMaxWidth().background(Color(0xFF16181D), RoundedCornerShape(10.dp)).padding(10.dp)) {
                    (if (log.isEmpty()) listOf("(nothing yet)") else log.takeLast(18)).forEach {
                        Text(it, color = Color(0xCCFFFFFF), fontSize = 11.sp, fontFamily = FontFamily.Monospace)
                    }
                }
            }
        }
        if (disclosure) AlertDialog(
            onDismissRequest = { disclosure = false },
            title = { Text("Accessibility permission") },
            text = { Text(getString(R.string.a11y_description) + "\n\nNext: Accessibility settings → Orbit → turn on. " +
                "If the switch is greyed out: App info → ⋮ → Allow restricted settings.") },
            confirmButton = { Button({ disclosure = false; startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }) { Text("I agree, continue") } },
            dismissButton = { TextButton({ disclosure = false }) { Text("Not now") } },
        )
    }

    @Composable
    private fun Step(n: String, title: String, sub: String, done: Boolean, action: () -> Unit) {
        Row(Modifier.fillMaxWidth().background(Color(0xFF16181D), RoundedCornerShape(14.dp)).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(28.dp).background(if (done) Color(0xFF3DDC97) else Color(0x33FFFFFF), CircleShape),
                contentAlignment = Alignment.Center) { Text(if (done) "✓" else n, color = Color.Black, fontWeight = FontWeight.Bold) }
            Column(Modifier.weight(1f)) {
                Text(title, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                Text(sub, color = Color(0x99FFFFFF), fontSize = 12.sp)
            }
            if (!done) Button(action, colors = ButtonDefaults.buttonColors()) { Text("Set up") }
        }
    }
}
