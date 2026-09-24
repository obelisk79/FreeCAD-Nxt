import QtQuick

// Find, not filter.
//
// Filtering a tree to show a match throws away the context that makes the
// match meaningful, and leaves the user to undo the search before they can
// carry on working. This searches instead: the tree is never touched, the
// hits appear in a list under the field, and choosing one opens the path to
// it, selects it and scrolls it into view.
//
// Results cover every object in the document, profiles included, and land
// in the one list the panel now has - so a hit is always somewhere the user
// can be taken to.
Item {
    id: box

    property var results: []
    property string placeholder: qsTr("search")
    property int current: 0
    property bool open: false

    signal queryChanged(string text)
    signal chosen(string name)

    implicitHeight: field.implicitHeight

    function choose(index) {
        if (index < 0 || index >= box.results.length)
            return;
        var target = box.results[index].name;
        box.open = false;

        // Deferred, because this is reached from a result delegate's tap
        // handler and clearing the query empties the Repeater's model -
        // destroying that very delegate. Destroying an object while one of
        // its signal handlers is on the stack calls qFatal in QML, which
        // aborts the process rather than merely warning.
        Qt.callLater(function () {
            field.text = "";
            box.chosen(target);
        });
    }

    function step(delta) {
        if (box.results.length === 0)
            return;
        box.current = Math.max(
            0, Math.min(box.results.length - 1, box.current + delta));
        list.positionViewAtIndex(box.current, ListView.Contain);
    }

    TextField {
        id: field
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        placeholder: box.placeholder

        onEdited: function (value) {
            box.queryChanged(value);
            box.current = 0;
            box.open = value.length > 0;
        }
        onDownPressed: box.step(1)
        onUpPressed: box.step(-1)
        onAccepted: box.choose(box.current)
        onDismissed: {
            if (box.open) {
                box.open = false;       // first Escape closes the results
            } else {
                field.text = "";
                field.input.focus = false;
            }
        }
    }

    // Closing on focus loss has to lag slightly, or clicking a result
    // dismisses the list before the tap is delivered to it.
    Timer {
        id: closer
        interval: 150
        onTriggered: box.open = false
    }

    Connections {
        target: field.input
        function onActiveFocusChanged() {
            if (field.input.activeFocus)
                closer.stop();
            else
                closer.start();
        }
    }

    Rectangle {
        id: popup
        visible: box.open && box.results.length > 0
        z: 10
        y: field.y + field.height + 4
        width: parent.width
        height: Math.min(6, box.results.length) * rowHeight + 8
        color: theme.background
        border.width: 1
        border.color: theme.border
        radius: 4

        readonly property int rowHeight: Math.round(theme.rowHeight * 1.5)

        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 4
            clip: true
            model: box.results
            boundsBehavior: Flickable.StopAtBounds

            delegate: Item {
                required property int index
                required property var modelData

                width: list.width
                height: popup.rowHeight

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: 3
                    color: theme.accent
                    opacity: index === box.current ? 1.0
                           : rowHover.hovered ? 0.35 : 0.0
                    Behavior on opacity { NumberAnimation { duration: 70 } }
                }

                Image {
                    id: hitIcon
                    x: 6
                    anchors.verticalCenter: parent.verticalCenter
                    width: theme.iconSize
                    height: width
                    sourceSize.width: width * 2
                    sourceSize.height: width * 2
                    source: modelData.iconUrl
                }

                Column {
                    x: hitIcon.x + hitIcon.width + 7
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - x - 8
                    spacing: 0

                    Text {
                        width: parent.width
                        text: modelData.label
                        elide: Text.ElideMiddle
                        font.pixelSize: theme.fontRow
                        color: index === box.current ? theme.accentText : theme.text
                    }

                    Text {
                        width: parent.width
                        visible: text.length > 0
                        // A hoisted sketch has no path in the tree, so say
                        // which half it is in rather than showing nothing.
                        text: modelData.isProfile
                              ? (modelData.context.length > 0
                                 ? qsTr("profile in %1").arg(modelData.context)
                                 : qsTr("profile"))
                              : modelData.context
                        elide: Text.ElideMiddle
                        font.pixelSize: theme.fontAside
                        color: index === box.current ? theme.accentText : theme.textDim
                        opacity: 0.85
                    }
                }

                HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    onTapped: {
                        box.current = index;
                        box.choose(index);
                    }
                }
            }
        }
    }
}
