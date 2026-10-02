import QtQuick

// Expand/collapse affordance.
//
// The shape is the theme's own branch indicator - a dart, which is a
// triangle with a concave notch in its back edge - rather than the plain
// triangle this used to draw, so the panel's disclosure reads as part of
// the same UI as the stock tree's.
//
// Redrawn from the SVG's proportions instead of loading the file: one shape
// covers both states, because the open branch icon is the closed one rotated
// a quarter turn, and a Canvas is resolution-independent where a 21px asset
// would be resampled at every other row height and scale factor. The colour
// is a property, so it can follow the host palette or be pinned to the
// theme's own value - see `ink` below for which it currently does.
Item {
    id: root

    property bool expanded: false
    property bool shown: true

    // The dart's widest extent, in pixels. Below about 8 the notch in its
    // back edge stops resolving and the glyph reads as a plain triangle,
    // which is the thing this shape exists not to be.
    property real span: theme.fontAside

    // Picked by the theme to stand out from what is behind the arrow: the
    // panel when docked, the 3D view in an overlay.
    property color ink: theme.branchInk

    // Repaints are driven from the owning item rather than from
    // mirrored copies of its properties: a child property with the
    // same name as its parent's shadows it inside this scope, which
    // is how a plain pass-through binding turns into a loop.
    onInkChanged: arrow.requestPaint()
    onSpanChanged: arrow.requestPaint()

    signal toggled()

    implicitWidth: theme.markSize
    implicitHeight: implicitWidth

    Canvas {
        id: arrow
        anchors.fill: parent
        antialiasing: true
        visible: root.shown
        opacity: hover.hovered ? 1.0 : 0.8
        rotation: root.expanded ? 90 : 0

        Behavior on rotation { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }


        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();

            // Measured off the theme's branch_closed.svg. In its 21-unit
            // box the dart runs 4 units from centre to tip, 4 back to the
            // trailing corners, 5 across to each of them, with the notch
            // 1.93 from centre, drawn with a 1-unit round-joined stroke -
            // 11 units across in total, including the stroke.
            var c = width / 2;
            var unit = Math.max(0.4, root.span / 11);
            var along = 4 * unit;
            var across = 5 * unit;
            var notch = 1.93 * unit;

            ctx.beginPath();
            ctx.moveTo(c + along, c);
            ctx.lineTo(c - along, c + across);
            ctx.lineTo(c - notch, c);
            ctx.lineTo(c - along, c - across);
            ctx.closePath();

            ctx.fillStyle = root.ink;
            ctx.strokeStyle = root.ink;
            ctx.lineWidth = unit;
            ctx.lineJoin = "round";
            ctx.lineCap = "round";
            ctx.fill();
            ctx.stroke();
        }
    }

    HoverHandler { id: hover; enabled: root.shown; cursorShape: Qt.PointingHandCursor }
    TapHandler { enabled: root.shown; onTapped: root.toggled() }
}
