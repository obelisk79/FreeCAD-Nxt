import QtQuick

// A single-line text field, drawn rather than styled.
//
// QtQuick.Controls would give us one, but it would arrive wearing whatever
// Qt style the host has set, and the host here is FreeCAD with a stylesheet
// we do not control. A TextInput plus a rectangle is less code than
// convincing a styled control to match the rest of the panel.
//
// Keys are surfaced as signals rather than handled here, because the thing
// that owns the field is the thing that knows what up, down and return mean
// in context - stepping a result list, in the only case that currently
// exists.
Item {
    id: field

    property alias text: input.text
    property alias input: input
    property string placeholder: ""
    //: The object whose property this edits, "Document#Name" or "Name":
    //: given one, "=" opens expression help (ExpressionAssist).
    property string owner: ""

    signal edited(string value)
    signal accepted()
    signal dismissed()
    signal upPressed()
    signal downPressed()

    implicitHeight: theme.fieldHeight

    // A field has to read as a field in both modes. The first overlay pass
    // faded this rectangle out entirely, which took the border with it and
    // left the placeholder floating in the header with nothing to say it
    // was a target. In overlay the fill steps down to the chip colour
    // instead - enough separation from the header pill behind it - and the
    // border stays at full strength either way.
    Rectangle {
        anchors.fill: parent
        radius: 3
        color: theme.overlay ? theme.chip : theme.background
        border.width: 1
        border.color: input.activeFocus ? theme.accent
                    : theme.overlay ? theme.pillBorder
                    : theme.border
    }

    Text {
        anchors.verticalCenter: parent.verticalCenter
        x: 6
        visible: input.text.length === 0
        text: field.placeholder
        font.pixelSize: theme.fontSmall
        color: theme.textDim
        opacity: 0.8
    }

    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: 6
        anchors.rightMargin: clearButton.visible ? 20 : 6
        verticalAlignment: TextInput.AlignVCenter
        font.pixelSize: theme.fontSmall
        color: theme.text
        selectionColor: theme.accent
        selectedTextColor: theme.accentText
        selectByMouse: true
        clip: true

        onTextChanged: field.edited(text)

        // The expression list, while one is being typed, has first say on
        // the keys it uses (ExpressionAssist.handleKey); what it leaves is
        // the field's. Asked in each key's own handler: Qt calls those
        // before Keys.onPressed, which would never see them.
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

    // A way out that does not require knowing about Escape.
    Item {
        id: clearButton
        visible: input.text.length > 0
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

        HoverHandler { id: clearHover; cursorShape: Qt.PointingHandCursor }
        TapHandler {
            onTapped: {
                input.text = "";
                field.dismissed();
            }
        }
    }
}
