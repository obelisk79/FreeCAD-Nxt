import QtQuick

// Where a Part Design feature's eye would be (TreeRow). Features have no
// visibility of their own - the tip bar decides what the Body shows - so
// this stands in the eye's place: a small node on a line, the timeline's
// own shape, saying "a step" rather than "a thing you can hide".
//
// Drawn, like EyeToggle, so it follows `ink` at any size.
Item {
    id: root

    property color ink: theme.textDim
    onInkChanged: canvas.requestPaint()

    implicitWidth: theme.iconSize
    implicitHeight: implicitWidth

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: true

        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            var cx = width / 2, cy = height / 2;
            var stroke = Math.max(1.0, width * 0.075);
            var r = width * 0.17;
            ctx.lineWidth = stroke;
            ctx.lineCap = "round";
            ctx.strokeStyle = root.ink;
            // the line through, broken where the node sits
            ctx.beginPath();
            ctx.moveTo(cx, height * 0.08);
            ctx.lineTo(cx, cy - r);
            ctx.moveTo(cx, cy + r);
            ctx.lineTo(cx, height * 0.92);
            ctx.stroke();
            // the node
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, 2 * Math.PI);
            ctx.stroke();
        }
    }
}
