import QtQuick

// One choice of a few, all in view: a row of joined buttons, the chosen one
// filled. For a setting with two to four values, where a drop-down would
// hide the alternatives behind a click.
//
// `options` is a list of {value, label}; `value` is the chosen one. Picking
// emits `picked(value)` and leaves `value` to whoever owns the setting, so
// the control always shows what is stored rather than what was clicked.
// Left and Right move the choice when it has focus.
FocusScope {
    id: control

    property var options: []
    property var value
    signal picked(var value)

    implicitWidth: 200
    implicitHeight: Math.round(theme.rowHeight * 0.95)
    activeFocusOnTab: true

    function indexOf(v) {
        for (var i = 0; i < options.length; ++i)
            if (options[i].value === v)
                return i;
        return -1;
    }

    function step(by) {
        var next = indexOf(value) + by;
        if (next >= 0 && next < options.length)
            picked(options[next].value);
    }

    Keys.onLeftPressed: step(-1)
    Keys.onRightPressed: step(1)

    Accessible.role: Accessible.PageTabList

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: 4
        color: theme.chip
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? theme.accent : theme.border
    }

    Row {
        anchors.fill: parent
        anchors.margins: 2
        spacing: 2

        Repeater {
            model: control.options

            Rectangle {
                id: option
                required property var modelData
                required property int index
                readonly property bool chosen: modelData.value === control.value

                width: (parent.width - parent.spacing
                        * (control.options.length - 1))
                       / Math.max(1, control.options.length)
                height: parent.height
                radius: 3
                color: chosen ? theme.accent
                     : optionMouse.containsMouse ? theme.hover
                     : "transparent"

                Text {
                    anchors.centerIn: parent
                    width: parent.width - 6
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    text: option.modelData.label
                    font.pixelSize: theme.fontSmall
                    color: option.chosen ? theme.accentText : theme.text
                }

                MouseArea {
                    id: optionMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        control.forceActiveFocus();
                        control.picked(option.modelData.value);
                    }
                }

                Accessible.role: Accessible.PageTab
                Accessible.name: option.modelData.label
                Accessible.checked: option.chosen
            }
        }
    }
}
