import QtQuick

// Dotted connector lines from a container to its children, as a classic
// tree view draws them (the "TreeLines" preference): down from the parent,
// across to the row, and straight through past the rows of deeper levels.
//
// What to draw in each column is worked out by the model (branch_lines in
// tree/models.py); this only draws it. Lines that belong to the active
// Body, Part or assembly - the ones to its children, and everything
// inside it - are drawn in the accent colour.
Item {
    id: lines

    //: Per column: 0 nothing, 1 straight through, 2 a tee, 3 the last.
    property var branches: []
    //: The column the accent colour starts at, or -1.
    property int activeFrom: -1
    //: Where column 0 is, the distance between columns, and where the
    //: row's own content begins (the arm stops short of it).
    property real firstX: 0
    property real step: 16
    property real armEnd: 0
    //: The row's first line: the arm is drawn at its middle.
    property real headHeight: height
    //: The row's y in the list, so dots line up from one row to the next.
    property real offset: 0
    property color ink: theme.border

    readonly property int period: 3
    readonly property int phase: (period - (Math.round(offset) % period))
                                 % period

    component Dots: Item {
        id: run
        property bool vertical: true
        property color ink
        property int phase: 0
        // Its own copy: an inline component cannot see the file's ids.
        property int period: 3
        readonly property real extent: vertical ? height : width
        Repeater {
            model: Math.max(0, Math.ceil((run.extent - run.phase)
                                         / run.period))
            Rectangle {
                required property int index
                x: run.vertical ? 0 : run.phase + index * run.period
                y: run.vertical ? run.phase + index * run.period : 0
                width: 1
                height: 1
                color: run.ink
            }
        }
    }

    Repeater {
        model: lines.branches
        Item {
            id: column
            required property int index
            required property int modelData
            readonly property color ink:
                lines.activeFrom >= 0 && index >= lines.activeFrom
                    ? theme.accent : lines.ink
            readonly property real middle: Math.round(lines.headHeight / 2)
            x: Math.round(lines.firstX + index * lines.step)
            height: lines.height

            // Down: the whole row, or only as far as the arm on the last
            // child.
            Dots {
                visible: column.modelData > 0
                width: 1
                // No height, no dots: nothing is made for a gap.
                height: column.modelData === 0 ? 0
                      : column.modelData === 3 ? column.middle + 1
                      : lines.height
                phase: lines.phase
                ink: column.ink
            }
            // Across, to the row.
            Dots {
                visible: column.modelData >= 2
                vertical: false
                x: 1
                y: column.middle
                height: 1
                width: column.modelData >= 2
                       ? Math.max(0, lines.armEnd - column.x - 1) : 0
                phase: 1
                ink: column.ink
            }
        }
    }
}
