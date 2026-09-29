import QtQuick

// The selection's dependencies, drawn as arrows in a gutter at the tree's
// right edge (links.py works out which). Blue arrows come in from what the
// selection reads; purple arrows go out to what reads it. The line says
// the kind of link: solid geometry, dotted attachment, dashed expression,
// dash-dot link or clone. A faint dotted leader joins each row involved to
// the gutter, and a count marks an arrow that stands for several rows (a
// collapsed branch). A target scrolled out of sight gets a small arrowhead
// at the top or bottom edge, pointing the way.
//
// Drawn over the list, never taking the mouse: it is a picture of the
// rows, not a control.
Canvas {
    id: arrows

    property ListView list
    property var arrowData: nxt.linkArrows
    //: Width of the gutter the arrows loop through.
    readonly property int gutter: Math.round(theme.rowHeight * 1.9)

    antialiasing: true
    enabled: false

    onArrowDataChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Connections {
        target: arrows.list
        function onContentYChanged() { arrows.requestPaint(); }
        function onContentHeightChanged() { arrows.requestPaint(); }
    }
    Connections {
        target: theme
        function onChanged() { arrows.requestPaint(); }
    }

    // Where a row's middle is, in this canvas, or null when it is not
    // built (scrolled well out of sight): then -1 above, +1 below.
    function rowY(row) {
        var item = list.itemAtIndex(row);
        if (!item)
            return row < list.indexAt(10, list.contentY) ? -1 : 1e9;
        return item.y - list.contentY + list.anchors.topMargin
               + theme.rowHeight / 2;
    }

    function rowRight(row) {
        var item = list.itemAtIndex(row);
        return item ? Math.min(item.pillRight + 4, width - gutter) : -1;
    }

    function dash(kind) {
        if (kind === "attachment") return [1.5, 3];
        if (kind === "expression") return [5, 3];
        if (kind === "link") return [7, 2, 1.5, 2];
        return [];
    }

    onPaint: {
        var ctx = getContext("2d");
        ctx.reset();
        var d = arrows.arrowData;
        if (!d || d.source < 0 || !d.links || d.links.length === 0)
            return;
        var x0 = width - gutter + 2;
        var src = rowY(d.source);
        if (src < 0 || src > height)
            return;         // the selection itself is out of sight
        var rows = [d.source];

        for (var i = 0; i < d.links.length; ++i) {
            var link = d.links[i];
            var colour = link.dir === "in" ? theme.arrowIn : theme.arrowOut;
            var y = rowY(link.row);
            var off = y < 0 || y > height;
            var yEnd = off ? (y < 0 ? 3 : height - 3) : y;
            if (!off)
                rows.push(link.row);
            // Nested lanes: short spans hug the rows, long ones go wide.
            var bulge = 10 + (i % 5) * 7;
            // Data flows from what is read to what reads it.
            var ya = link.dir === "in" ? yEnd : src;
            var yb = link.dir === "in" ? src : yEnd;
            ya += link.dir === "in" ? 0 : 3;
            yb += link.dir === "in" ? -3 : 0;

            ctx.strokeStyle = colour;
            ctx.fillStyle = colour;
            ctx.lineWidth = 1.6;
            ctx.setLineDash(dash(link.kind));
            ctx.beginPath();
            ctx.moveTo(x0, ya);
            ctx.bezierCurveTo(x0 + bulge, ya, x0 + bulge, yb, x0 + 3, yb);
            ctx.stroke();
            ctx.setLineDash([]);

            // The arrowhead, at the reading end, pointing left into the row.
            if (!(off && link.dir === "out")) {
                ctx.beginPath();
                ctx.moveTo(x0 + 1, yb);
                ctx.lineTo(x0 + 7, yb - 3.5);
                ctx.lineTo(x0 + 7, yb + 3.5);
                ctx.closePath();
                ctx.fill();
            }
            if (off) {
                // Out of sight: a head at the edge, pointing the way.
                var tip = y < 0 ? 0 : height;
                var sign = y < 0 ? 1 : -1;
                ctx.beginPath();
                ctx.moveTo(x0 + bulge, tip);
                ctx.lineTo(x0 + bulge - 4, tip + sign * 6);
                ctx.lineTo(x0 + bulge + 4, tip + sign * 6);
                ctx.closePath();
                ctx.fill();
            }
            if (link.count > 1) {
                var by = (ya + yb) / 2;
                ctx.beginPath();
                ctx.arc(x0 + bulge, by, 7, 0, 2 * Math.PI);
                ctx.fill();
                ctx.fillStyle = theme.background;
                ctx.font = "bold " + Math.max(8, theme.fontAside - 2)
                           + "px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(String(link.count), x0 + bulge, by + 0.5);
            }
        }

        // Leaders: row to gutter, so the eye can follow across.
        ctx.strokeStyle = theme.textDim;
        ctx.globalAlpha = 0.6;
        ctx.lineWidth = 1;
        ctx.setLineDash([1, 3]);
        for (var r = 0; r < rows.length; ++r) {
            var ly = rowY(rows[r]);
            var lx = rowRight(rows[r]);
            if (lx < 0 || lx >= x0)
                continue;
            ctx.beginPath();
            ctx.moveTo(lx, ly);
            ctx.lineTo(x0, ly);
            ctx.stroke();
        }
        ctx.setLineDash([]);
        ctx.globalAlpha = 1.0;
    }
}
