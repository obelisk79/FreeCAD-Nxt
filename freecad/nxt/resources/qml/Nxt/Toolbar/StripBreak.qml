import QtQuick

// The end of a row in a strip's Flow: it takes the rest of the line after
// the items before it, so what follows starts the next. Sized from what
// those items take up, never from positions, which the Flow sets from
// sizes and animates as items move.
// At least a pixel: a Flow skips items of no size. In edit mode it is a
// bar on a line of its own, a drop zone that starts a new row.
Item {
    id: lineEnd

    property bool across: true
    property bool editing: false
    property bool targeted: false
    property int size: 24
    //: The Flow it ends a line of, and what its line's items take up.
    property Item line: null
    property real used: 0
    readonly property int least: 1
    readonly property real rest: !line ? 0
        : (across ? line.width : line.height) - used

    //: In edit mode a bar across the whole strip, on a line of its own:
    //: all of it starts a new row.
    readonly property int bar: Math.round(size / 2)

    width: across ? (editing && line ? line.width : Math.max(least, rest))
                  : (editing ? bar : least)
    height: across ? (editing ? bar : least)
                   : (editing && line ? line.height : Math.max(least, rest))

    Rectangle {
        anchors.fill: parent
        visible: lineEnd.editing
        radius: 4
        color: lineEnd.targeted ? theme.pressed : "transparent"
        border.color: lineEnd.targeted ? theme.accent : theme.border
        border.width: 1
        opacity: lineEnd.targeted ? 1 : 0.6
    }
}
