.pragma library

// Icons drawn on a Canvas, as IconButton's `paint` takes them:
// (context, width, height, ink).

// A settings gear: eight teeth around a hole.
function gear(ctx, w, h, ink) {
    var c = w / 2, outer = w / 2, inner = outer * 0.72;
    var teeth = 8;
    ctx.fillStyle = ink;
    ctx.beginPath();
    for (var i = 0; i < teeth * 2; ++i) {
        var r = i % 2 === 0 ? outer : inner;
        var a0 = (i - 0.5) * Math.PI / teeth;
        var a1 = (i + 0.5) * Math.PI / teeth;
        ctx.lineTo(c + r * Math.cos(a0), c + r * Math.sin(a0));
        ctx.lineTo(c + r * Math.cos(a1), c + r * Math.sin(a1));
    }
    ctx.closePath();
    ctx.moveTo(c + outer * 0.32, c);
    ctx.arc(c, c, outer * 0.32, 0, 2 * Math.PI, true);
    ctx.fill("evenodd");
}
