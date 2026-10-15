import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import QtQuick.Effects

// Orbit overlay: wheel menu + HUD pill. Never takes focus, never eats clicks.
Window {
    id: win
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
           | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false
    title: "Orbit"

    readonly property real s: orbit.uiScale
    readonly property color accent: orbit.accent
    readonly property color ink: "#F4F6FB"
    readonly property color inkDim: Qt.rgba(1, 1, 1, 0.52)
    readonly property bool needed: wheel.shown || hud.shown

    onNeededChanged: {
        if (needed) { hideTimer.stop(); win.visible = true }
        else hideTimer.restart()
    }
    Timer { id: hideTimer; interval: 420; onTriggered: if (!win.needed) win.visible = false }

    Connections {
        target: orbit
        function onPlaced(x, y, w, h) {
            if (win.x !== x || win.y !== y || win.width !== w || win.height !== h) {
                win.x = x; win.y = y; win.width = w; win.height = h
            }
        }
        function onWheelOpened(items, index) { hud.dismiss(); wheel.open(items, index) }
        function onWheelMoved(index, dir) { wheel.move(index, dir) }
        function onWheelCommitted(index) { wheel.commit(index) }
        function onWheelCancelled() { wheel.cancel() }
        function onHudShown(glyph, title, detail, progress, dir) {
            if (!wheel.shown) hud.show(glyph, title, detail, progress, dir)
        }
    }

    // ================================================================ WHEEL
    Item {
        id: wheel
        property bool shown: false
        property var items: []
        property int index: 0
        property int n: Math.max(items.length, 1)
        readonly property real step: 360 / n
        property real selTarget: 0        // cumulative degrees, so wrap-around animates forward
        property real selAngle: selTarget
        property real openT: 0            // 0..1 drives the staggered entry

        readonly property real dia: 340 * win.s
        readonly property real rad: 116 * win.s
        width: dia; height: dia
        anchors.centerIn: parent
        opacity: 0
        scale: 0.86

        Behavior on selAngle { SpringAnimation { spring: 5.2; damping: 0.36; epsilon: 0.02 } }

        function open(list, idx) {
            closeAnim.stop(); commitAnim.stop()
            items = list
            index = idx
            selTarget = idx * step
            shown = true
            openAnim.restart()
            centre.swap(0)
        }

        function move(idx, dir) {
            var d = ((idx - index) % n + n) % n           // forward distance
            if (dir < 0 && d !== 0) d = d - n
            index = idx
            selTarget += d * step
            centre.swap(dir)
        }

        function commit(idx) {
            if (!shown) return
            index = idx
            shown = false
            openAnim.stop()
            commitAnim.restart()
        }

        function cancel() {
            if (!shown) return
            shown = false
            openAnim.stop()
            closeAnim.restart()
        }

        ParallelAnimation {
            id: openAnim
            NumberAnimation { target: wheel; property: "opacity"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic }
            SpringAnimation { target: wheel; property: "scale"; from: 0.86; to: 1; spring: 6; damping: 0.42; epsilon: 0.002 }
            NumberAnimation { target: wheel; property: "rotation"; from: -12; to: 0; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 1.2 }
            NumberAnimation { target: wheel; property: "openT"; from: 0; to: 1; duration: 420; easing.type: Easing.OutCubic }
        }
        SequentialAnimation {
            id: commitAnim
            NumberAnimation { target: puck; property: "pulse"; from: 1; to: 1.35; duration: 90; easing.type: Easing.OutQuad }
            ParallelAnimation {
                NumberAnimation { target: puck; property: "pulse"; to: 1; duration: 160; easing.type: Easing.OutQuad }
                NumberAnimation { target: wheel; property: "scale"; to: 1.08; duration: 220; easing.type: Easing.OutCubic }
                NumberAnimation { target: wheel; property: "opacity"; to: 0; duration: 220; easing.type: Easing.OutCubic }
            }
        }
        ParallelAnimation {
            id: closeAnim
            NumberAnimation { target: wheel; property: "scale"; to: 0.9; duration: 170; easing.type: Easing.InCubic }
            NumberAnimation { target: wheel; property: "opacity"; to: 0; duration: 170; easing.type: Easing.InCubic }
        }

        function px(angleDeg, r) { return dia / 2 + r * Math.sin(angleDeg * Math.PI / 180) }
        function py(angleDeg, r) { return dia / 2 - r * Math.cos(angleDeg * Math.PI / 180) }

        // ---- glass disc with soft shadow
        Rectangle {
            id: disc
            anchors.fill: parent
            radius: width / 2
            color: Qt.rgba(0.075, 0.08, 0.10, 0.985)
            border.color: Qt.rgba(1, 1, 1, 0.08)
            border.width: 1
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: "#B0000000"
                shadowBlur: 1.0
                shadowVerticalOffset: 10 * win.s
            }
        }
        // inner highlight for depth
        Rectangle {
            anchors.centerIn: parent
            width: wheel.dia - 2; height: width; radius: width / 2
            color: "transparent"
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.045) }
                GradientStop { position: 0.5; color: "transparent" }
            }
        }

        // ---- track + tick marks
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Qt.rgba(1, 1, 1, 0.07); strokeWidth: 1; fillColor: "transparent"
                PathAngleArc { centerX: wheel.dia / 2; centerY: wheel.dia / 2; radiusX: wheel.dia / 2 - 14 * win.s; radiusY: radiusX; startAngle: 0; sweepAngle: 360 }
            }
        }
        Repeater {
            model: wheel.n
            Rectangle {
                readonly property real a: index * wheel.step
                width: 2 * win.s; height: 6 * win.s; radius: 1
                color: Qt.rgba(1, 1, 1, index === wheel.index ? 0 : 0.18)
                x: wheel.px(a, wheel.dia / 2 - 14 * win.s) - width / 2
                y: wheel.py(a, wheel.dia / 2 - 14 * win.s) - height / 2
                rotation: a
            }
        }

        // ---- selection arc on the rim (glow + core), rides the spring
        Shape {
            id: selArc
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            readonly property real sweep: Math.min(wheel.step * 0.62, 70)
            ShapePath {
                strokeColor: Qt.rgba(win.accent.r, win.accent.g, win.accent.b, 0.22)
                strokeWidth: 12 * win.s; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: wheel.dia / 2; centerY: wheel.dia / 2; radiusX: wheel.dia / 2 - 14 * win.s; radiusY: radiusX
                               startAngle: wheel.selAngle - 90 - selArc.sweep / 2; sweepAngle: selArc.sweep }
            }
            ShapePath {
                strokeColor: win.accent
                strokeWidth: 3.5 * win.s; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: wheel.dia / 2; centerY: wheel.dia / 2; radiusX: wheel.dia / 2 - 14 * win.s; radiusY: radiusX
                               startAngle: wheel.selAngle - 90 - selArc.sweep / 2; sweepAngle: selArc.sweep }
            }
        }

        // ---- puck behind the highlighted icon
        Rectangle {
            id: puck
            property real pulse: 1
            width: 56 * win.s; height: width; radius: width / 2
            x: wheel.px(wheel.selAngle, wheel.rad) - width / 2
            y: wheel.py(wheel.selAngle, wheel.rad) - height / 2
            scale: pulse
            color: Qt.rgba(win.accent.r, win.accent.g, win.accent.b, 0.20)
            border.color: Qt.rgba(win.accent.r, win.accent.g, win.accent.b, 0.55)
            border.width: 1
        }

        // ---- items
        Repeater {
            model: wheel.items
            Item {
                id: it
                readonly property bool sel: index === wheel.index
                readonly property real a: index * wheel.step
                // staggered entry: each item slides out from the centre a little after the previous
                readonly property real t: Math.max(0, Math.min(1, wheel.openT * 1.6 - index * 0.06))
                readonly property real r: wheel.rad * (0.72 + 0.28 * t)
                width: 56 * win.s; height: width
                x: wheel.px(a, r) - width / 2
                y: wheel.py(a, r) - height / 2
                opacity: t * (sel ? 1 : 0.62)
                scale: sel ? 1.16 : 1
                Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutBack; easing.overshoot: 2 } }
                Behavior on opacity { NumberAnimation { duration: 120 } }

                Text {
                    anchors.centerIn: parent
                    text: modelData.glyph
                    font.family: orbit.iconFont
                    font.pixelSize: 21 * win.s
                    color: it.sel ? win.ink : win.inkDim
                    Behavior on color { ColorAnimation { duration: 140 } }
                }
                Rectangle {   // one-shot marker
                    visible: !modelData.sticky
                    width: 4 * win.s; height: width; radius: width / 2
                    color: win.accent
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 6 * win.s
                }
            }
        }

        // ---- centre: big glyph + label, slides in the turn direction
        Item {
            id: centre
            anchors.centerIn: parent
            width: wheel.rad * 1.3; height: width
            property real shift: 0
            property var cur: wheel.items.length ? wheel.items[wheel.index] : ({ glyph: "", label: "", sticky: true })

            function swap(dir) {
                swapAnim.stop()
                shift = dir * 14 * win.s
                content.opacity = dir === 0 ? 1 : 0.25
                swapAnim.start()
            }
            ParallelAnimation {
                id: swapAnim
                SpringAnimation { target: centre; property: "shift"; to: 0; spring: 7; damping: 0.5; epsilon: 0.05 }
                NumberAnimation { target: content; property: "opacity"; to: 1; duration: 140; easing.type: Easing.OutCubic }
            }

            Column {
                id: content
                anchors.centerIn: parent
                anchors.horizontalCenterOffset: centre.shift
                spacing: 6 * win.s
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: centre.cur.glyph
                    font.family: orbit.iconFont
                    font.pixelSize: 36 * win.s
                    color: win.accent
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: centre.cur.label
                    font.pixelSize: 17 * win.s
                    font.weight: Font.DemiBold
                    color: win.ink
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: centre.cur.sticky ? "press to use" : "press to run"
                    font.pixelSize: 11 * win.s
                    font.letterSpacing: 0.4
                    color: Qt.rgba(1, 1, 1, 0.38)
                }
            }
        }
    }

    // ================================================================ HUD
    Item {
        id: hud
        property bool shown: false
        property string glyph: ""
        property string title: ""
        property string detail: ""
        property real progress: -1
        property real nudge: 0
        property real lift: 18 * win.s

        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height - 150 * win.s + lift
        width: pill.width; height: pill.height
        opacity: 0

        function show(g, t, d, p, dir) {
            var wasShown = shown
            glyph = g; title = t; detail = d; progress = p
            shown = true
            outAnim.stop()
            if (!wasShown) inAnim.restart()
            else { opacity = 1; lift = 0 }
            if (dir !== 0) { nudgeAnim.stop(); nudge = dir * 16; nudgeAnim.start() }
            hudTimer.restart()
        }
        function dismiss() { if (shown) { shown = false; hudTimer.stop(); outAnim.restart() } }

        Timer { id: hudTimer; interval: orbit.hudMs; onTriggered: hud.dismiss() }
        ParallelAnimation {
            id: inAnim
            NumberAnimation { target: hud; property: "opacity"; from: 0; to: 1; duration: 150; easing.type: Easing.OutCubic }
            SpringAnimation { target: hud; property: "lift"; from: 18 * win.s; to: 0; spring: 6; damping: 0.45; epsilon: 0.05 }
        }
        ParallelAnimation {
            id: outAnim
            NumberAnimation { target: hud; property: "opacity"; to: 0; duration: 260; easing.type: Easing.InCubic }
            NumberAnimation { target: hud; property: "lift"; to: 10 * win.s; duration: 260; easing.type: Easing.InCubic }
        }
        SpringAnimation { id: nudgeAnim; target: hud; property: "nudge"; to: 0; spring: 9; damping: 0.32; epsilon: 0.1 }

        Rectangle {
            id: pill
            width: row.implicitWidth + 30 * win.s
            height: 58 * win.s
            radius: height / 2
            color: Qt.rgba(0.075, 0.08, 0.10, 0.985)
            border.color: Qt.rgba(1, 1, 1, 0.08)
            Behavior on width { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
            layer.enabled: true
            layer.effect: MultiEffect { shadowEnabled: true; shadowColor: "#90000000"; shadowBlur: 0.8; shadowVerticalOffset: 6 * win.s }

            Row {
                id: row
                anchors.verticalCenter: parent.verticalCenter
                x: 12 * win.s
                spacing: 12 * win.s
                Rectangle {
                    width: 36 * win.s; height: width; radius: width / 2
                    anchors.verticalCenter: parent.verticalCenter
                    color: Qt.rgba(win.accent.r, win.accent.g, win.accent.b, 0.18)
                    Text {
                        anchors.centerIn: parent
                        text: hud.glyph
                        font.family: orbit.iconFont
                        font.pixelSize: 17 * win.s
                        color: win.accent
                        rotation: hud.nudge
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 5 * win.s
                    Row {
                        spacing: 8 * win.s
                        Text { text: hud.title; color: win.ink; font.pixelSize: 15 * win.s; font.weight: Font.DemiBold }
                        Text { text: hud.detail; color: win.inkDim; font.pixelSize: 15 * win.s; visible: hud.detail.length > 0 }
                    }
                    Rectangle {
                        visible: hud.progress >= 0
                        width: 150 * win.s; height: 4 * win.s; radius: height / 2
                        color: Qt.rgba(1, 1, 1, 0.10)
                        Rectangle {
                            height: parent.height; radius: parent.radius
                            color: win.accent
                            width: parent.width * Math.max(0, hud.progress)
                            Behavior on width { SpringAnimation { spring: 7; damping: 0.5; epsilon: 0.2 } }
                        }
                    }
                }
                Item { width: 4 * win.s; height: 1 }
            }
        }
    }
}
