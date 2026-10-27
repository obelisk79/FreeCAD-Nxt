import QtQuick

// Find, not filter: hits list under the field, and choosing one reveals
// and selects it in the untouched tree.
Item {
    id: box

    property var results: []
    property string placeholder: qsTr("search")
    property int current: 0
    property bool open: false
    //: The hits list's width, and where it starts, from the field's left.
    property real listWidth: width
    property real listX: 0

    signal queryChanged(string text)
    signal chosen(string name)

    implicitHeight: field.implicitHeight

    function choose(index) {
        if (index < 0 || index >= box.results.length)
            return;
        var target = box.results[index].name;
        box.open = false;

        // Deferred: clearing destroys the delegate whose handler is running (qFatal).
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
        clearable: true

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
                box.open = false;
            } else {
                field.text = "";
                field.input.focus = false;
            }
        }
    }

    // Lags so a click on a result lands before the list closes.
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
        width: Math.max(box.width, box.listWidth)
        x: box.listX
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

                HoverHandler { id: rowHover }
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
