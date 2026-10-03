import QtQuick

// Row status, as a silhouette first and a colour second:
//   1 hollow ring   under-constrained
//   2 triangle + !  redundant constraints
//   3 disc + !      conflicting, malformed, or failed to recompute
//
// Not an x on the disc: a round mark with an x is the shape of a close
// button, and without the red - to anyone who cannot see it - that is
// what it looked like. The error and the warning share the bang and
// differ in outline, disc against triangle.
Item {
    id: mark

    //  0 none, 1 under-constrained, 2 warning, 3 error
    property int level: 0
    property bool active: false
    property int size: theme.markSize

    signal clicked()
    // With Ctrl held: the row opens the Property Inspector instead.
    signal ctrlClicked()

    visible: level > 0
    implicitWidth: size
    implicitHeight: size

    onLevelChanged: canvas.requestPaint()

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: true
        opacity: (hover.hovered || mark.active) ? 1.0 : 0.85

        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            if (mark.level <= 0)
                return;

            var c = width / 2;
            var r = width * 0.40;

            if (mark.level === 1) {
                // Hollow, and in the body text colour rather than a warning
                // one: degrees of freedom are a state, not a fault, and a
                // sketch is under-constrained for most of its life.
                ctx.strokeStyle = theme.textDim;
                ctx.lineWidth = Math.max(1.4, width * 0.13);
                ctx.beginPath();
                ctx.arc(c, c, r * 0.86, 0, 2 * Math.PI);
                ctx.stroke();
                return;
            }

            var ink = mark.level >= 3 ? theme.danger : theme.warning;
            ctx.fillStyle = ink;
            ctx.strokeStyle = ink;

            if (mark.level >= 3) {
                ctx.beginPath();
                ctx.arc(c, c, r, 0, 2 * Math.PI);
                ctx.fill();

                // A bang, cut through the disc in the canvas colour: the
                // same stroke as the warning's, sized to the disc.
                ctx.strokeStyle = theme.markInk;
                ctx.lineWidth = Math.max(1.4, width * 0.13);
                ctx.lineCap = "round";
                ctx.beginPath();
                ctx.moveTo(c, c - r * 0.55);
                ctx.lineTo(c, c + r * 0.12);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(c, c + r * 0.50);
                ctx.lineTo(c, c + r * 0.53);
                ctx.stroke();
            } else {
                // A triangle sitting on its base, nudged down so its visual
                // centre lands on the row's centre rather than its bounding
                // box doing so.
                var h = r * 1.95;
                var w = r * 2.15;
                var top = c - h / 2 + r * 0.12;
                ctx.beginPath();
                ctx.moveTo(c, top);
                ctx.lineTo(c + w / 2, c + h / 2);
                ctx.lineTo(c - w / 2, c + h / 2);
                ctx.closePath();
                ctx.lineJoin = "round";
                ctx.lineWidth = width * 0.12;
                ctx.fill();
                ctx.stroke();

                // A bang, cut through the triangle in the canvas colour.
                ctx.strokeStyle = theme.markInk;
                ctx.lineWidth = Math.max(1.3, width * 0.12);
                ctx.lineCap = "round";
                ctx.beginPath();
                ctx.moveTo(c, top + h * 0.34);
                ctx.lineTo(c, top + h * 0.66);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(c, top + h * 0.82);
                ctx.lineTo(c, top + h * 0.84);
                ctx.stroke();
            }
        }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        onTapped: {
            if (point.modifiers & Qt.ControlModifier)
                mark.ctrlClicked();
            else
                mark.clicked();
        }
    }
}
