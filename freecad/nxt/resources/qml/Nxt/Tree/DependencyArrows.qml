import QtQuick

// The selection's dependencies as arrows in a gutter at the tree's right edge
// (links.py). Drawn over the list; never takes the mouse.
Canvas {
    id: arrows

    property ListView list
    property var arrowData: nxt.linkArrows
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

    // Row middle in this canvas, or -1 above / +1 below when not built.
    function rowY(row) {
        var item = list.itemAtIndex(row);
        if (!item)
            return row < list.indexAt(10, list.contentY) ? -1 : 1e9;
        return item.y - list.contentY + list.anchors.topMargin
               + theme.rowHeight / 2;
    }

    function rowRight(row) {
        var item = list.itemAtIndex(row);
        return item ? Math.min(item.pillRight + 4, gutterX - 2) : -1;
    }

    // Docked: the list's right edge. Overlay: past the widest pill spanned,
    // and the room the hints need before it.
    property real gutterX: width - gutter + 2
    function placeGutter(hintRoom) {
        if (!theme.overlay) {
            gutterX = width - gutter + 2;
            return;
        }
        var d = arrows.arrowData;
        var lo = d.source, hi = d.source;
        for (var k = 0; k < d.links.length; ++k) {
            lo = Math.min(lo, d.links[k].row);
            hi = Math.max(hi, d.links[k].row);
        }
        var widest = 0;
        var first = list.indexAt(10, list.contentY);
        var last = list.indexAt(10, list.contentY + list.height);
        if (last < 0)
            last = list.count - 1;
        first = Math.max(Math.max(0, first), lo);
        last = Math.min(last, hi);
        for (var i = first; i <= last; ++i) {
            var item = list.itemAtIndex(i);
            if (item)
                widest = Math.max(widest, item.pillRight);
        }
        gutterX = Math.min(width - gutter + 2, widest + 10 + hintRoom);
    }

    //: Arrowhead length and half-width.
    readonly property real headLength: 8
    readonly property real headHalfWidth: 3

    //: Gap between a hint and the arrow it ends at.
    readonly property real hintGap: 4

    // The link from the row's side, of the selection; two words at most.
    function phrase(link) {
        var uses = link.dir === "in";
        switch (link.kind) {
        case "attachment":
            return uses ? qsTr("attached from") : qsTr("attached to");
        case "expression":
            return uses ? qsTr("referenced by") : qsTr("references");
        case "link":
            return uses ? qsTr("linked by") : qsTr("links to");
        default:
            return uses ? qsTr("shape for") : qsTr("built on");
        }
    }

    // Words for a link whose kind the user has not learned yet
    // (tree/hints.py); one per row, the first link drawn to it.
    function hintFor(link, index) {
        var d = arrows.arrowData;
        if (d.learned && d.learned.indexOf(link.kind) >= 0)
            return "";
        for (var j = 0; j < index; ++j)
            if (d.links[j].row === link.row)
                return "";
        return phrase(link);
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
        ctx.font = theme.fontAside + "px sans-serif";
        var room = 0;
        for (var h = 0; h < d.links.length; ++h) {
            var said = hintFor(d.links[h], h);
            if (said)
                room = Math.max(room, ctx.measureText(said).width + hintGap * 2);
        }
        placeGutter(room);
        var x0 = gutterX;
        // Scrolled out of sight, the selection's arrows start at the
        // edge it went past, as a link's out of sight end there.
        var src = rowY(d.source);
        var srcAbove = src < 0;
        var srcOff = srcAbove || src > height;
        if (srcOff)
            src = srcAbove ? 3 : height - 3;
        var rows = srcOff ? [] : [d.source];

        for (var i = 0; i < d.links.length; ++i) {
            var link = d.links[i];
            var colour = link.dir === "in" ? theme.arrowIn : theme.arrowOut;
            var y = rowY(link.row);
            var off = y < 0 || y > height;
            if (srcOff && off && (y < 0) === srcAbove)
                continue;   // both ends past the same edge
            var yEnd = off ? (y < 0 ? 3 : height - 3) : y;
            if (!off)
                rows.push(link.row);
            var bulge = 10 + (i % 5) * 7;
            var ya = link.dir === "in" ? yEnd : src;
            var yb = link.dir === "in" ? src : yEnd;
            ya += link.dir === "in" ? 0 : 3;
            yb += link.dir === "in" ? -3 : 0;

            ctx.strokeStyle = colour;
            ctx.fillStyle = colour;
            ctx.lineWidth = 1.6;
            ctx.setLineDash(dash(link.kind));
            // The last control point lies on the head's axis, so the head continues the line.
            var tipX = x0 + 3, tipY = yb;
            var dx = Math.cos(Math.PI / 6);
            var dy = (ya < yb ? -1 : 1) * Math.sin(Math.PI / 6);
            var baseX = tipX + headLength * dx, baseY = tipY + headLength * dy;
            var reach = Math.max(4, bulge * 0.7);
            var c2x = baseX + reach * dx, c2y = baseY + reach * dy;
            ctx.beginPath();
            ctx.moveTo(x0, ya);
            ctx.bezierCurveTo(x0 + bulge, ya, c2x, c2y, baseX, baseY);
            ctx.stroke();
            ctx.setLineDash([]);

            if (!(off && link.dir === "out")) {
                var tilt = Math.atan2(c2y - tipY, c2x - tipX);
                ctx.save();
                ctx.translate(tipX, tipY);
                ctx.rotate(tilt);
                ctx.beginPath();
                ctx.moveTo(0, 0);
                ctx.lineTo(headLength, -headHalfWidth);
                ctx.lineTo(headLength, headHalfWidth);
                ctx.closePath();
                ctx.fill();
                ctx.restore();
            }
            if (off) {
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

        if (srcOff) {
            var edge = srcAbove ? 0 : height;
            var away = srcAbove ? 1 : -1;
            ctx.fillStyle = theme.textDim;
            ctx.beginPath();
            ctx.moveTo(x0, edge);
            ctx.lineTo(x0 - headHalfWidth * 2, edge + away * headLength);
            ctx.lineTo(x0 + headHalfWidth * 2, edge + away * headLength);
            ctx.closePath();
            ctx.fill();
        }

        // Hints end where their arrow starts: the pattern is the arrow's.
        // One that does not fit between the name and the chips is left out.
        var hinted = {};
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";
        for (var t = 0; t < d.links.length; ++t) {
            var hl = d.links[t];
            var words = hintFor(hl, t);
            var hy = rowY(hl.row);
            var item = list.itemAtIndex(hl.row);
            if (!words || !item || hy < 0 || hy > height)
                continue;
            // Overlay: past the pill, over the 3D view. Docked: within
            // the row, between the name and the chips.
            var right = (theme.overlay ? x0 : Math.min(x0, item.chipsStart))
                        - hintGap;
            var floor = theme.overlay ? item.pillRight : item.labelEnd;
            var wordsWidth = ctx.measureText(words).width;
            if (right - wordsWidth < floor + hintGap * 2)
                continue;
            ctx.fillStyle = hl.dir === "in" ? theme.arrowIn : theme.arrowOut;
            ctx.fillText(words, right, hy);
            hinted[hl.row] = right - wordsWidth - hintGap;
        }

        ctx.strokeStyle = theme.textDim;
        ctx.globalAlpha = 0.6;
        ctx.lineWidth = 1;
        ctx.setLineDash([1, 3]);
        for (var r = 0; r < rows.length; ++r) {
            var ly = rowY(rows[r]);
            var lx = rowRight(rows[r]);
            var lend = hinted[rows[r]] !== undefined ? hinted[rows[r]] : x0;
            if (lx < 0 || lx >= lend)
                continue;
            ctx.beginPath();
            ctx.moveTo(lx, ly);
            ctx.lineTo(lend, ly);
            ctx.stroke();
        }
        ctx.setLineDash([]);
        ctx.globalAlpha = 1.0;
    }
}
