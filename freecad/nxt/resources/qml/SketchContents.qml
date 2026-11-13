import QtQuick
import Nxt.Controls
import Nxt.Tree

// Experimental: the sketch's elements and constraints in one card, in
// place of FreeCAD's two lists (sketch_contents_model.py). Closed, it is
// one row of counts; open, a tab for each, a search, filter chips and a
// recycled list, so a sketch of thousands costs only the rows on screen.
// A row selects what it names (Ctrl adds to the selection); the one thing
// selected opens a strip under its row.
Rectangle {
    id: card

    readonly property var contents: sketch.contents
    readonly property var counts: contents.counts
    //: Rows shown before the list scrolls.
    readonly property int rowsShown: 14
    readonly property int gap: 6

    implicitHeight: column.implicitHeight + 2 * gap
    radius: 6
    color: theme.surface
    border.width: 1
    border.color: theme.border

    function filterLabel(name) {
        return name === "free" ? qsTr("Free")
             : name === "construction" ? qsTr("Construction")
             : name === "external" ? qsTr("External")
             : name === "flagged" ? qsTr("Problems")
             : name === "reference" ? qsTr("Reference")
             : name === "inactive" ? qsTr("Inactive") : name;
    }
    readonly property var tabFilters: contents.tab === "elements"
                                      ? ["free", "construction", "external"]
                                      : ["flagged", "reference", "inactive"]

    function choose(name, add, selected) {
        if (add)
            sketch.toggle(name, !selected);
        else
            sketch.pick(name);
    }

    Column {
        id: column
        x: card.gap
        y: card.gap
        width: card.width - 2 * card.gap
        spacing: card.gap

        // -- the card's head: open or close it --
        Item {
            id: head
            width: parent.width
            height: theme.rowHeight
            activeFocusOnTab: true
            Keys.onSpacePressed: contents.setOpen(!contents.open)
            Keys.onReturnPressed: contents.setOpen(!contents.open)
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Contents")

            Rectangle {
                anchors.fill: parent
                radius: 4
                color: headPress.pressed ? theme.pressed : theme.hover
                visible: headHover.hovered || headPress.pressed
            }
            Rectangle {
                anchors.fill: parent
                radius: 4
                color: "transparent"
                border.width: 2
                border.color: theme.accent
                visible: head.activeFocus
            }
            Disclosure {
                id: dart
                anchors.verticalCenter: parent.verticalCenter
                x: 4
                expanded: contents.open
                onToggled: contents.setOpen(!contents.open)
            }
            Text {
                id: headTitle
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: dart.right
                anchors.leftMargin: 6
                text: qsTr("Contents")
                font.pixelSize: theme.fontSmall
                font.bold: true
                color: theme.text
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: headTitle.right
                anchors.leftMargin: 8
                anchors.right: parent.right
                elide: Text.ElideRight
                text: qsTr("%1 elements · %2 constraints")
                      .arg(sketch.counts.elements || 0)
                      .arg(sketch.counts.constraints || 0)
                font.pixelSize: theme.fontSmall
                color: theme.textDim
            }
            HoverHandler { id: headHover }
            MouseArea {
                id: headPress
                anchors.fill: parent
                onClicked: contents.setOpen(!contents.open)
            }
        }

        // -- tab, search and filters --
        Segmented {
            visible: contents.open
            width: parent.width
            value: contents.tab
            options: [
                {value: "elements",
                 label: qsTr("Elements %1").arg(card.counts.elements || 0)},
                {value: "constraints",
                 label: qsTr("Constraints %1")
                        .arg(card.counts.constraints || 0)}]
            onPicked: function (value) { contents.setTab(value); }
        }
        TextField {
            id: search
            visible: contents.open
            width: parent.width
            height: theme.fieldHeight
            placeholder: qsTr("Search")
            clearable: true
            onEdited: function (value) { contents.setQuery(value); }
            onDismissed: {
                text = "";
                contents.setQuery("");
            }
        }
        Flow {
            visible: contents.open
            width: parent.width
            spacing: 4
            Repeater {
                model: card.tabFilters.length
                Chip {
                    required property int index
                    readonly property string filter: card.tabFilters[index]
                    readonly property int count: card.counts[filter] || 0
                    visible: count > 0 || active
                    text: card.filterLabel(filter) + "  " + count
                    active: contents.filters.indexOf(filter) >= 0
                    severity: filter === "flagged" ? 1 : 0
                    onClicked: contents.toggleFilter(filter)
                }
            }
        }

        // -- the rows --
        Item {
            visible: contents.open
            width: parent.width
            height: Math.min(list.contentHeight,
                             card.rowsShown * theme.rowHeight)

            ListView {
                id: list
                anchors.fill: parent
                anchors.rightMargin: bar.visible ? bar.width + 2 : 0
                clip: true
                reuseItems: true
                boundsBehavior: Flickable.StopAtBounds
                model: contents
                delegate: rowDelegate
            }
            NxtScrollBar {
                id: bar
                anchors.right: parent.right
                height: parent.height
                target: list
            }
            Text {
                anchors.centerIn: parent
                visible: list.count === 0
                text: qsTr("Nothing matches")
                font.pixelSize: theme.fontSmall
                color: theme.textDim
            }
        }
    }

    Connections {
        target: card.contents
        function onReveal(row) {
            list.positionViewAtIndex(row, ListView.Contain);
        }
    }

    // One delegate for every kind of row, recycled as the list scrolls:
    // its parts show by `kind`.
    Component {
        id: rowDelegate

        Item {
            id: line

            required property string key
            required property string kind
            required property string title
            required property string detail
            required property int number
            required property int mark
            required property bool dashed
            required property bool selected
            required property bool folded
            required property int count
            required property int ref
            required property string name
            required property bool editable
            required property bool driving
            required property bool active
            required property var chips
            required property int more
            required property bool fixes
            required property string value

            readonly property bool isRow: kind === "element"
                                          || kind === "constraint"
            readonly property bool isStrip: kind === "elementStrip"
                                            || kind === "constraintStrip"

            width: ListView.view ? ListView.view.width : 0
            height: isStrip ? strip.implicitHeight + 8
                  : kind === "summary" ? summary.implicitHeight + 8
                  : theme.rowHeight

            // -- a group heading: fold or open it --
            Item {
                visible: line.kind === "group"
                anchors.fill: parent

                Disclosure {
                    id: groupDart
                    anchors.verticalCenter: parent.verticalCenter
                    x: 2
                    expanded: !line.folded
                    onToggled: contents.setFolded(line.key, !line.folded)
                }
                SeverityMark {
                    id: groupMark
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: groupDart.right
                    anchors.leftMargin: 4
                    level: line.mark > 1 ? line.mark : 0
                    size: theme.markSizeSmall
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: groupMark.visible ? groupMark.right
                                                    : groupDart.right
                    anchors.leftMargin: 6
                    text: line.title + "  " + line.count
                    font.pixelSize: theme.fontAside
                    font.capitalization: Font.AllUppercase
                    color: theme.textDim
                }
                MouseArea {
                    anchors.fill: parent
                    z: -1
                    onClicked: contents.setFolded(line.key, !line.folded)
                }
            }

            // -- an element or a constraint --
            Rectangle {
                visible: line.isRow
                anchors.fill: parent
                radius: 4
                color: line.selected ? Qt.rgba(theme.accent.r, theme.accent.g,
                                               theme.accent.b, 0.28)
                     : rowMouse.containsMouse ? theme.hover : "transparent"
                opacity: line.kind === "constraint" && !line.active ? 0.55
                                                                    : 1.0

                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: function (mouse) {
                        card.choose(line.name,
                                    mouse.modifiers & Qt.ControlModifier,
                                    line.selected);
                    }
                }
                SeverityMark {
                    id: rowMark
                    anchors.verticalCenter: parent.verticalCenter
                    x: 4
                    level: line.mark
                    size: theme.markSizeSmall
                }
                Text {
                    id: rowNumber
                    visible: line.kind === "constraint"
                    anchors.verticalCenter: parent.verticalCenter
                    x: rowMark.x + theme.markSizeSmall + 4
                    width: visible ? Math.round(theme.fontSmall * 2.2) : 0
                    horizontalAlignment: Text.AlignRight
                    text: line.number
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
                Text {
                    id: rowTitle
                    anchors.verticalCenter: parent.verticalCenter
                    x: rowNumber.visible ? rowNumber.x + rowNumber.width + 8
                                         : rowMark.x + theme.markSizeSmall + 6
                    width: Math.min(implicitWidth,
                                    rowEnd.x - x - 6)
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                    text: line.title
                    font.pixelSize: theme.fontSmall
                    font.italic: line.dashed
                    color: theme.text
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: rowTitle.right
                    anchors.leftMargin: 8
                    anchors.right: rowEnd.left
                    anchors.rightMargin: 6
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                    text: line.detail
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }

                Row {
                    id: rowEnd
                    anchors.right: parent.right
                    anchors.rightMargin: 2
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: line.kind === "constraint"
                                 && !line.editable && line.value.length > 0
                        text: "(" + line.value + ")"
                        font.pixelSize: theme.fontSmall
                        color: theme.textDim
                    }
                    TextField {
                        id: valueField

                        property bool typed: false

                        function revert() {
                            text = line.value;
                            typed = false;
                        }
                        function apply() {
                            if (typed && text !== line.value)
                                sketch.setValue(line.ref, text);
                            typed = false;
                        }

                        visible: line.kind === "constraint" && line.editable
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.round(theme.fontSmall * 7)
                        height: Math.round(theme.rowHeight * 0.85)
                        // As the 3D handles step: fine, coarse with Shift.
                        stepFor: function (modifiers) {
                            return modifiers & Qt.ShiftModifier ? 10 : 1;
                        }
                        onEdited: if (input.activeFocus) typed = true
                        onAccepted: apply()
                        onStepped: {
                            typed = true;
                            apply();
                        }
                        onDismissed: {
                            revert();
                            input.focus = false;
                        }
                        input.onActiveFocusChanged: {
                            if (!input.activeFocus)
                                apply();
                        }
                        Connections {
                            target: line
                            function onValueChanged() {
                                if (!valueField.typed)
                                    valueField.revert();
                            }
                        }
                        Component.onCompleted: revert()
                    }
                    IconButton {
                        visible: line.fixes && line.kind === "constraint"
                                 && line.editable
                        paint: Glyphs.reference
                        tip: qsTr("Make reference")
                        onClicked: sketch.setDriving(line.ref, false)
                    }
                    IconButton {
                        visible: line.fixes
                        paint: Glyphs.deactivate
                        tip: qsTr("Deactivate")
                        onClicked: sketch.setActive(line.ref, false)
                    }
                    IconButton {
                        visible: line.fixes
                        paint: Glyphs.remove
                        tip: qsTr("Delete")
                        onClicked: sketch.remove(line.ref)
                    }
                }
            }

            // -- the strip under the one selected row --
            Column {
                id: strip
                visible: line.isStrip
                x: Math.round(theme.markSizeSmall + 10)
                y: 4
                width: parent.width - x - 4
                spacing: 4

                Text {
                    visible: line.kind === "elementStrip"
                             && line.detail.length > 0
                    text: line.detail
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }
                NxtSwitch {
                    visible: line.kind === "elementStrip"
                    width: parent.width
                    text: qsTr("Construction")
                    stored: line.dashed
                    onChangedTo: function (on) {
                        sketch.setConstruction(line.ref, on);
                    }
                }
                NxtSwitch {
                    visible: line.kind === "constraintStrip" && line.editable
                    width: parent.width
                    text: qsTr("Driving")
                    stored: line.driving
                    onChangedTo: function (on) {
                        sketch.setDriving(line.ref, on);
                    }
                }
                NxtSwitch {
                    visible: line.kind === "constraintStrip"
                    width: parent.width
                    text: qsTr("Active")
                    stored: line.active
                    onChangedTo: function (on) {
                        sketch.setActive(line.ref, on);
                    }
                }
                Flow {
                    width: parent.width
                    spacing: 4
                    // By count: a new list would rebuild the chip under
                    // its click.
                    Repeater {
                        model: line.isStrip ? line.chips.length : 0
                        Chip {
                            required property int index
                            readonly property var item: line.chips[index]
                                                        || ({})
                            text: item.title || ""
                            onClicked: sketch.pick(item.name)
                        }
                    }
                    Chip {
                        visible: line.more > 0
                        text: "+" + line.more
                        tip: qsTr("Every constraint on it")
                        onClicked: contents.showConstraintsOn(line.ref)
                    }
                }
            }

            // -- several things selected --
            Column {
                id: summary
                visible: line.kind === "summary"
                x: 4
                y: 4
                width: parent.width - 8
                spacing: 2

                Text {
                    text: qsTr("%1 selected").arg(line.count)
                    font.pixelSize: theme.fontSmall
                    font.bold: true
                    color: theme.text
                }
                Flow {
                    width: parent.width
                    spacing: 2
                    TextButton {
                        visible: line.number > 0
                        text: qsTr("Construction")
                        onClicked: sketch.constructSelected()
                    }
                    TextButton {
                        visible: line.number > 0
                        text: qsTr("Select constraints")
                        onClicked: sketch.selectConstraints()
                    }
                    TextButton {
                        text: qsTr("Delete")
                        danger: true
                        onClicked: sketch.deleteSelected()
                    }
                }
            }
        }
    }
}
