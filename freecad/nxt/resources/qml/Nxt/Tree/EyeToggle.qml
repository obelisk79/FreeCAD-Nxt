import QtQuick

// Visibility toggle, drawn on a Canvas so it stays crisp at ~14px at any
// scale and follows `ink`.
Item {
    id: root

    property bool open: true
    property color ink: theme.textDim

    // Canvas does not repaint on property changes, so nudge it by hand.
    onOpenChanged: canvas.item && canvas.item.requestPaint()
    onInkChanged: canvas.item && canvas.item.requestPaint()

    signal toggled()

    implicitWidth: theme.iconSize
    implicitHeight: implicitWidth

    // Painted only while shown: most rows never show the eye.
    Loader {
        id: canvas
        anchors.fill: parent
        active: root.opacity > 0
        sourceComponent: Component {
            Canvas {
                anchors.fill: parent
                antialiasing: true
                scale: eyeTap.pressed ? 0.85 : 1.0
                opacity: eyeTap.pressed ? 0.7 : 1.0
                Behavior on scale { NumberAnimation { duration: 70 } }


                onPaint: {
                    var ctx = getContext("2d");
                    ctx.reset();

                    var cx = width / 2;
                    var cy = height / 2;
                    var ew = width * 0.90;          // lid span
                    var eh = ew * 0.62;             // lid rise
                    var stroke = Math.max(1.0, width * 0.075);

                    ctx.lineWidth = stroke;
                    ctx.lineCap = "round";
                    ctx.lineJoin = "round";
                    ctx.strokeStyle = root.ink;
                    ctx.fillStyle = root.ink;

                    if (root.open) {
                        ctx.beginPath();
                        ctx.moveTo(cx - ew / 2, cy);
                        ctx.quadraticCurveTo(cx, cy - eh, cx + ew / 2, cy);
                        ctx.quadraticCurveTo(cx, cy + eh, cx - ew / 2, cy);
                        ctx.closePath();
                        ctx.stroke();

                        ctx.beginPath();
                        ctx.arc(cx, cy, eh * 0.30, 0, 2 * Math.PI);
                        ctx.fill();
                    } else {
                        ctx.beginPath();
                        ctx.moveTo(cx - ew / 2, cy - eh * 0.10);
                        ctx.quadraticCurveTo(cx, cy + eh * 0.85, cx + ew / 2, cy - eh * 0.10);
                        ctx.stroke();

                        var lash = eh * 0.34;
                        ctx.beginPath();
                        ctx.moveTo(cx, cy + eh * 0.44);
                        ctx.lineTo(cx, cy + eh * 0.44 + lash);
                        ctx.moveTo(cx - ew * 0.32, cy + eh * 0.30);
                        ctx.lineTo(cx - ew * 0.40, cy + eh * 0.30 + lash * 0.8);
                        ctx.moveTo(cx + ew * 0.32, cy + eh * 0.30);
                        ctx.lineTo(cx + ew * 0.40, cy + eh * 0.30 + lash * 0.8);
                        ctx.stroke();
                    }
                }
            }
        }
    }

    TapHandler { id: eyeTap; onTapped: root.toggled() }
}
