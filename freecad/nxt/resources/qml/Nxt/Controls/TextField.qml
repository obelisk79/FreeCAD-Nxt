import QtQuick

// A single-line text field, drawn by hand so the host's QtQuick.Controls
// style cannot reach it. Keys are surfaced as signals for the owner.
Item {
    id: field

    property alias text: input.text
    property alias input: input
    property string placeholder: ""
    //: Enables "=" expression help.
    property string owner: ""
    //: A clear (x) button while there is text: for searches and filters.
    property bool clearable: false
    //: Shown after the text inside the field, not editable (a unit).
    property string suffix: ""
    //: Room kept at the start for something drawn over the field.
    property real leading: 0
    //: The wheel's step on the number, given its modifiers; null: none.
    property var stepFor: null
    //: The wheel can step: once focused, or the pointer has rested on
    //: it, so scrolling a card past the field leaves it alone.
    property bool wheelReady: false
    property real wheelPending: 0

    signal edited(string value)
    signal accepted()
    signal dismissed()
    signal upPressed()
    signal downPressed()
    //: The wheel changed the number and came to rest.
    signal stepped()

    readonly property var numberAtStart:
        /^(\s*)([-+]?(?:\d+[.,]?\d*|[.,]\d+)(?:[eE][-+]?\d+)?)/

    function decimalsOf(text) {
        var match = /[.,](\d+)/.exec(text);
        return match ? match[1].length : 0;
    }

    //: The number at the start of the text moved by `delta`.
    function step(delta) {
        var match = field.numberAtStart.exec(input.text);
        if (!match)
            return false;
        var comma = match[2].indexOf(",") >= 0;
        var value = parseFloat(match[2].replace(",", ".")) + delta;
        var places = Math.max(field.decimalsOf(match[2]),
                              field.decimalsOf(String(Math.abs(delta))));
        var shown = value.toFixed(Math.min(places, 6));
        if (comma)
            shown = shown.replace(".", ",");
        input.text = match[1] + shown + input.text.slice(match[0].length);
        return true;
    }

    implicitHeight: theme.fieldHeight

    Rectangle {
        anchors.fill: parent
        radius: 3
        color: theme.overlay ? theme.chip : theme.background
        border.width: 1
        border.color: input.activeFocus ? theme.accent
                    : fieldHover.hovered ? theme.textDim
                    : theme.overlay ? theme.pillBorder
                    : theme.border
    }

    HoverHandler {
        id: fieldHover
        cursorShape: Qt.IBeamCursor
        onHoveredChanged: {
            if (hovered) {
                wheelDwell.restart();
            } else {
                wheelDwell.stop();
                field.wheelReady = false;
            }
        }
    }

    Timer {
        id: wheelDwell
        interval: 300
        onTriggered: field.wheelReady = true
    }

    // Only the text changes while the wheel turns; the value is set once
    // it rests, so a spin is one recompute and one undo step.
    Timer {
        id: wheelRest
        interval: 400
        onTriggered: field.stepped()
    }

    WheelHandler {
        enabled: field.stepFor !== null
                 && (field.wheelReady || input.activeFocus)
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function (event) {
            field.wheelPending += event.angleDelta.y / 120;
            var notches = field.wheelPending > 0
                          ? Math.floor(field.wheelPending)
                          : Math.ceil(field.wheelPending);
            if (notches === 0)
                return;
            field.wheelPending -= notches;
            if (!input.activeFocus)
                input.forceActiveFocus();
            if (field.step(notches * field.stepFor(event.modifiers)))
                wheelRest.restart();
            input.selectAll();
        }
    }

    Text {
        anchors.verticalCenter: parent.verticalCenter
        x: 6 + field.leading
        visible: input.text.length === 0
        text: field.placeholder
        font.pixelSize: theme.fontSmall
        color: theme.textDim
        opacity: 0.8
    }

    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: 6 + field.leading
        anchors.rightMargin: (clearButton.visible ? 20 : 6)
                             + (suffixLabel.visible ? suffixLabel.width + 4
                                                    : 0)
        verticalAlignment: TextInput.AlignVCenter
        font.pixelSize: theme.fontSmall
        color: theme.text
        selectionColor: theme.accent
        selectedTextColor: theme.accentText
        selectByMouse: true
        clip: true

        onTextChanged: field.edited(text)

        // Assist asked in each key handler too: Qt runs those before
        // Keys.onPressed, which would never see these keys.
        Keys.onPressed: function (event) {
            if (assist.handleKey(event))
                event.accepted = true;
        }
        Keys.onReturnPressed: function (event) {
            if (!assist.handleKey(event)) field.accepted();
        }
        Keys.onEnterPressed: function (event) {
            if (!assist.handleKey(event)) field.accepted();
        }
        Keys.onEscapePressed: function (event) {
            if (!assist.handleKey(event)) field.dismissed();
        }
        Keys.onUpPressed: function (event) {
            if (!assist.handleKey(event)) field.upPressed();
        }
        Keys.onDownPressed: function (event) {
            if (!assist.handleKey(event)) field.downPressed();
        }
    }

    ExpressionAssist {
        id: assist
        input: input
        owner: field.owner
    }

    Text {
        id: suffixLabel
        visible: field.suffix.length > 0
        anchors.right: parent.right
        anchors.rightMargin: clearButton.visible ? 20 : 6
        anchors.verticalCenter: parent.verticalCenter
        text: field.suffix
        font.pixelSize: theme.fontSmall
        color: theme.textDim
    }

    Item {
        id: clearButton
        visible: field.clearable && input.text.length > 0
        width: 16
        height: 16
        anchors.right: parent.right
        anchors.rightMargin: 3
        anchors.verticalCenter: parent.verticalCenter

        Canvas {
            anchors.fill: parent
            antialiasing: true
            opacity: clearHover.hovered ? 1.0 : 0.55

            onPaint: {
                var ctx = getContext("2d");
                ctx.reset();
                var c = width / 2;
                var a = width * 0.22;
                ctx.strokeStyle = theme.textDim;
                ctx.lineWidth = 1.6;
                ctx.lineCap = "round";
                ctx.beginPath();
                ctx.moveTo(c - a, c - a);
                ctx.lineTo(c + a, c + a);
                ctx.moveTo(c + a, c - a);
                ctx.lineTo(c - a, c + a);
                ctx.stroke();
            }
        }

        HoverHandler { id: clearHover }
        TapHandler {
            onTapped: {
                input.text = "";
                field.dismissed();
            }
        }
    }
}
