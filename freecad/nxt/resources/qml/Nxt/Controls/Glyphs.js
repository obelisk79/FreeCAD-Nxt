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

// A rounded stroke, a tenth of the icon wide.
function pen(ctx, w, ink) {
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.2, w * 0.1);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
}

// Edit: a pencil, point down-left, its cap marked off.
function pencil(ctx, w, h, ink) {
    pen(ctx, w, ink);
    ctx.moveTo(w * 0.16, h * 0.84);
    ctx.lineTo(w * 0.22, h * 0.6);
    ctx.lineTo(w * 0.64, h * 0.18);
    ctx.lineTo(w * 0.82, h * 0.36);
    ctx.lineTo(w * 0.4, h * 0.78);
    ctx.closePath();
    ctx.moveTo(w * 0.54, h * 0.28);
    ctx.lineTo(w * 0.72, h * 0.46);
    ctx.stroke();
}

// A padlock, shut: a body and its shackle.
function lock(ctx, w, h, ink) {
    padlock(ctx, w, h, ink, 0);
}

// A padlock, open: the shackle lifted off to one side.
function unlock(ctx, w, h, ink) {
    padlock(ctx, w, h, ink, w * 0.22);
}

function padlock(ctx, w, h, ink, lift) {
    pen(ctx, w, ink);
    ctx.rect(w * 0.2, h * 0.46, w * 0.6, h * 0.42);
    ctx.moveTo(w * 0.32 + lift, h * 0.46 - (lift ? h * 0.08 : 0));
    ctx.lineTo(w * 0.32 + lift, h * 0.3);
    ctx.arc(w * 0.5 + lift, h * 0.3, w * 0.18, Math.PI, 0);
    ctx.lineTo(w * 0.68 + lift, lift ? h * 0.36 : h * 0.46);
    ctx.stroke();
}

// A constraint's Deactivate: a circle struck through.
function deactivate(ctx, w, h, ink) {
    pen(ctx, w, ink);
    ctx.arc(w / 2, h / 2, w * 0.4, 0, 2 * Math.PI);
    ctx.moveTo(w * 0.22, h * 0.78);
    ctx.lineTo(w * 0.78, h * 0.22);
    ctx.stroke();
}

// Activate: the circle whole.
function activate(ctx, w, h, ink) {
    pen(ctx, w, ink);
    ctx.arc(w / 2, h / 2, w * 0.4, 0, 2 * Math.PI);
    ctx.stroke();
}

// Make reference: brackets, as a driven value is shown.
function reference(ctx, w, h, ink) {
    pen(ctx, w, ink);
    ctx.moveTo(w * 0.3, h * 0.15);
    ctx.lineTo(w * 0.12, h * 0.15);
    ctx.lineTo(w * 0.12, h * 0.85);
    ctx.lineTo(w * 0.3, h * 0.85);
    ctx.moveTo(w * 0.7, h * 0.15);
    ctx.lineTo(w * 0.88, h * 0.15);
    ctx.lineTo(w * 0.88, h * 0.85);
    ctx.lineTo(w * 0.7, h * 0.85);
    ctx.stroke();
}

// Delete: a bin.
function remove(ctx, w, h, ink) {
    pen(ctx, w, ink);
    ctx.moveTo(w * 0.12, h * 0.26);
    ctx.lineTo(w * 0.88, h * 0.26);
    ctx.moveTo(w * 0.38, h * 0.26);
    ctx.lineTo(w * 0.38, h * 0.1);
    ctx.lineTo(w * 0.62, h * 0.1);
    ctx.lineTo(w * 0.62, h * 0.26);
    ctx.moveTo(w * 0.24, h * 0.26);
    ctx.lineTo(w * 0.3, h * 0.9);
    ctx.lineTo(w * 0.7, h * 0.9);
    ctx.lineTo(w * 0.76, h * 0.26);
    ctx.stroke();
}
