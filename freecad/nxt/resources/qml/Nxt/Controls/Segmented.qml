import QtQuick

// One choice of a few, as joined buttons. Emits `picked(value)` and leaves
// `value` to the owner, so it shows what is stored.
//
// A click shows its choice at once; `picked` follows a frame later, so the
// choice is drawn before whatever it sets off. Once `value` changes the
// control shows it; if it never does, it goes back.
FocusScope {
    id: control

    property var options: []
    property var value
    signal picked(var value)

    //: A choice made but not yet stored.
    property var pending: undefined
    readonly property var shown: pending !== undefined ? pending : value

    implicitWidth: 200
    implicitHeight: Math.round(theme.rowHeight * 0.95)
    activeFocusOnTab: true

    onValueChanged: {
        settle.stop();
        pending = undefined;
    }

    function indexOf(v) {
        for (var i = 0; i < options.length; ++i)
            if (options[i].value === v)
                return i;
        return -1;
    }

    function choose(v) {
        if (v === control.shown)
            return;
        control.pending = v;
        announce.chosen = v;
        announce.restart();
        settle.restart();
    }

    function step(by) {
        var next = indexOf(shown) + by;
        if (next >= 0 && next < options.length)
            choose(options[next].value);
    }

    Timer {
        id: announce
        property var chosen
        interval: 30
        onTriggered: control.picked(announce.chosen)
    }
    Timer {
        id: settle
        interval: 2500
        onTriggered: control.pending = undefined
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
        opacity: control.enabled ? 1.0 : 0.45
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
                readonly property bool chosen: modelData.value === control.shown

                width: (parent.width - parent.spacing
                        * (control.options.length - 1))
                       / Math.max(1, control.options.length)
                height: parent.height
                radius: 3
                color: chosen ? (optionMouse.pressed
                                 ? Qt.darker(theme.accent, 1.15) : theme.accent)
                     : optionMouse.pressed ? theme.pressed
                     : optionMouse.containsMouse ? theme.hover
                     : "transparent"

                Behavior on color { ColorAnimation { duration: 70 } }

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
                    enabled: control.enabled
                    hoverEnabled: true
                    onClicked: {
                        control.forceActiveFocus();
                        control.choose(option.modelData.value);
                    }
                }

                Accessible.role: Accessible.PageTab
                Accessible.name: option.modelData.label
                Accessible.checked: option.chosen
            }
        }
    }
}
