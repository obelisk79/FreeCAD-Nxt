import QtQuick

// Dotted tree connector lines (the "TreeLines" preference); the model
// (branch_lines in tree/models.py) decides what each column draws.
Canvas {
    id: lines

    //: Per column: 0 nothing, 1 through, 2 tee, 3 last.
    property var branches: []
    //: Column the accent starts at, or -1.
    property int activeFrom: -1
    property real firstX: 0
    property real step: 16
    property real armEnd: 0
    property real headHeight: height
    //: Row y in the list, so dots line up across rows.
    property real offset: 0
    property color ink: theme.border

    readonly property int period: 3
    readonly property int phase: (period - (Math.round(offset) % period))
                                 % period

    readonly property color accent: theme.accent

    onBranchesChanged: requestPaint()
    onActiveFromChanged: requestPaint()
    onFirstXChanged: requestPaint()
    onStepChanged: requestPaint()
    onArmEndChanged: requestPaint()
    onHeadHeightChanged: requestPaint()
    onPhaseChanged: requestPaint()
    onInkChanged: requestPaint()
    onHeightChanged: requestPaint()
    onAccentChanged: requestPaint()

    function dots(ctx: var, x: real, y: real, length: real, vertical: bool,
                  start: int): void {
        for (let at = start; at < length; at += period)
            ctx.fillRect(vertical ? x : x + at, vertical ? y + at : y, 1, 1)
    }

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const middle = Math.round(headHeight / 2)
        for (let index = 0; index < branches.length; ++index) {
            const kind = branches[index]
            if (kind === 0)
                continue
            const x = Math.round(firstX + index * step)
            ctx.fillStyle = activeFrom >= 0 && index >= activeFrom ? accent : ink
            dots(ctx, x, 0, kind === 3 ? middle + 1 : height, true, phase)
            if (kind >= 2)
                dots(ctx, x + 1, middle, Math.max(0, armEnd - x - 1), false, 1)
        }
    }
}
