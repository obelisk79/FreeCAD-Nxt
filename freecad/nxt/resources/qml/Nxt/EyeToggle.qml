import QtQuick

// Visibility control.
//
// Drawn rather than glyphed or shipped as an asset: this sits at roughly
// 14 logical pixels, where a font glyph is at the mercy of hinting and a
// bitmap is at the mercy of the display's scale factor. A Canvas redraws at
// whatever size and colour it is handed, which also means it follows the
// host stylesheet through `ink` without a second asset for light and dark.
//
// Open reads as an outlined almond with a pupil; closed drops the pupil and
// replaces the upper lid with lashes, so the two states differ in silhouette
// rather than only in detail - the part that survives at this size.
Item {
    id: root

    property bool open: true
    property color ink: theme.textDim

    // Canvas repaints itself on resize but not when a value its onPaint
    // reads changes, so both are nudged by hand - from here, so that no
    // child property shadows one of these.
    onOpenChanged: canvas.requestPaint()
    onInkChanged: canvas.requestPaint()

    signal toggled()

    implicitWidth: theme.iconSize
    implicitHeight: implicitWidth

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: true


        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();

            var cx = width / 2;
            var cy = height / 2;
            // Proportions tuned by rendering the shape at its real 15px
            // size. A shorter almond or a larger pupil fills the outline and
            // the open state collapses into a blob.
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
                // the closed lid, sitting a little lower than the open one
                ctx.beginPath();
                ctx.moveTo(cx - ew / 2, cy - eh * 0.10);
                ctx.quadraticCurveTo(cx, cy + eh * 0.85, cx + ew / 2, cy - eh * 0.10);
                ctx.stroke();

                // three short lashes. Individually illegible at this size,
                // which is fine - collectively they read as "shut".
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

    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: root.toggled() }
}
