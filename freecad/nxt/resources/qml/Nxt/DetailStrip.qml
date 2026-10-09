import QtQuick

// What the gutter mark could not say: the finding in words, the
// constraint state, what this reads and what reads it.
Column {
    id: strip

    property int level: 0
    property var notes: []
    property int dof: -1
    property int constrained: -1        // -1 unknown, 0 no, 1 yes
    property var consumers: []
    property var refs: []
    property bool isProfile: false
    property bool isLifted: false
    property var keyProps: []           // see properties.describe
    property string owner: ""           // the row's object, for expressions
    property int propertyCount: 0

    // Chips in here behave exactly as chips on a row do: click to go
    // there, double-click to open it. They did not, for no reason anyone
    // decided - a sketch reached through this strip simply could not be
    // opened, while the same sketch reached from the row could.
    signal consumerClicked(string name)
    signal referenceClicked(string name)
    signal chipActivated(string name)
    signal chipHovered(string name, bool hovered)
    signal keyEdited(string prop, var value)
    signal allPropertiesRequested()

    spacing: 2
    topPadding: 2
    bottomPadding: 5

    readonly property real lineSize: theme.fontSmall

    readonly property bool hasFindings: strip.notes && strip.notes.length > 0
    // Every reference, not just the crowded case. The row now chips only
    // what is broken, so for most rows this strip is the only place the
    // references are named at all.
    readonly property bool hasUses: strip.refs && strip.refs.length > 0
    readonly property bool hasUsers: strip.consumers
                                     && strip.consumers.length > 0
    readonly property bool hasValues: strip.keyProps
                                      && strip.keyProps.length > 0
    readonly property bool hasContent: hasFindings || hasUses || hasUsers
                                    || strip.isProfile || strip.isLifted
                                    || hasValues || strip.propertyCount > 0

    // --- what it is made of ----------------------------------------------- #

    // First, because it is what most people open a strip to change. The
    // rest of the object's properties are one click away in the property
    // inspector - FreeCAD's own editor, borrowed - rather than listed here,
    // where a long list would push the whole tree down.
    Flow {
        visible: strip.hasValues || strip.propertyCount > 0
        width: parent.width
        spacing: 10

        // Counted, not handed the list: every rebuild brings a fresh list,
        // and a Repeater given a new list destroys and recreates its
        // delegates - taking the field being typed in, and its focus, with
        // it. By index, a delegate lives as long as the count holds.
        Repeater {
            model: strip.keyProps ? strip.keyProps.length : 0

            KeyValue {
                required property int index
                spec: strip.keyProps[index]
                owner: strip.owner
                onEdited: function (value) {
                    strip.keyEdited(spec.name, value);
                }
            }
        }

        // Words, not an icon: the count says how much is behind it and the
        // ellipsis that it opens somewhere else.
        Text {
            height: theme.fieldHeight
            verticalAlignment: Text.AlignVCenter
            visible: strip.propertyCount > 0
            text: qsTr("All properties · %1…").arg(strip.propertyCount)
            font.pixelSize: theme.fontSmall
            font.underline: allHover.hovered
            color: theme.link
            Accessible.role: Accessible.Link
            Accessible.name: qsTr("All properties")

            HoverHandler {
                id: allHover
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler { onTapped: strip.allPropertiesRequested() }
        }
    }

    // --- the finding, in words ------------------------------------------ #

    Repeater {
        model: strip.notes ? strip.notes : []

        Row {
            required property var modelData
            spacing: 5

            SeverityMark {
                anchors.verticalCenter: parent.verticalCenter
                level: strip.level >= 3 ? 3 : 2
                size: theme.fontRow
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: modelData
                font.pixelSize: strip.lineSize
                color: strip.level >= 3 ? theme.danger : theme.warning
                wrapMode: Text.WordWrap
            }
        }
    }

    // --- how constrained it is ------------------------------------------ #

    // Stated in words rather than as a bare number, and only for profiles:
    // "14" beside a sketch is a quantity of nothing in particular. The
    // unknown case is shown rather than hidden, because a build whose
    // solver does not answer must not be drawn as though every sketch
    // were fine.
    Text {
        visible: strip.isProfile
        text: strip.constrained === 1 ? qsTr("fully constrained")
            : strip.dof === 1 ? qsTr("1 degree of freedom left")
            : strip.dof > 1 ? qsTr("%1 degrees of freedom left").arg(strip.dof)
            : strip.constrained === 0 ? qsTr("not fully constrained")
            : qsTr("constraint state unknown in this build")
        font.pixelSize: strip.lineSize
        color: theme.textDim
    }

    // --- what it reads --------------------------------------------------- #

    // Where the names go when the row could not afford them. A row with
    // several references shows them as icons, which says how many and what
    // kind but not which - this says which, and which part of which.
    Flow {
        visible: strip.hasUses
        width: parent.width
        spacing: 3

        Text {
            text: qsTr("uses")
            font.pixelSize: strip.lineSize
            color: theme.textDim
            rightPadding: 3
        }

        Repeater {
            model: strip.refs ? strip.refs : []

            Chip {
                required property var modelData
                text: modelData.sub.length > 0
                    ? modelData.label + ":" + modelData.sub
                    : modelData.label
                sub: modelData.sub
                severity: modelData.severity
                onClicked: strip.referenceClicked(modelData.name)
                onDoubleClicked: strip.chipActivated(modelData.name)
                onHoveredChanged: function (h) {
                    strip.chipHovered(modelData.name, h);
                }
            }
        }
    }

    // --- who depends on it ---------------------------------------------- #

    // The reuse information the shelf existed to carry. It lives here
    // rather than as row chips because a sketch used by six features would
    // grow a row six chips wide, and the timeline would stop being
    // scannable - which is the whole reason the sketches came back into it.
    //
    // Shown for anything lifted, not only sketches: a Boolean's tool and a
    // datum a feature is attached to were lifted for the same reason and
    // the same question is worth asking of them.
    Flow {
        // Anything with dependents says so, lifted or not. A pocket that
        // a fillet is built on is exactly as worth knowing about as a
        // sketch that two pads share.
        visible: strip.hasUsers
        width: parent.width
        spacing: 3

        Text {
            text: qsTr("used by")
            font.pixelSize: strip.lineSize
            color: theme.textDim
            rightPadding: 3
        }

        Repeater {
            model: strip.consumers ? strip.consumers : []

            Chip {
                required property var modelData
                text: modelData.label
                onClicked: strip.consumerClicked(modelData.name)
                onDoubleClicked: strip.chipActivated(modelData.name)
                onHoveredChanged: function (h) {
                    strip.chipHovered(modelData.name, h);
                }
            }
        }
    }

    Text {
        // Only for something lifted: "nothing uses this yet" is a remark
        // about a sketch or a tool that is waiting to be used. On a solid
        // feature at the end of a history it is simply the normal state.
        visible: strip.isLifted && !strip.hasUsers
        text: qsTr("nothing uses this yet")
        font.pixelSize: strip.lineSize
        font.italic: true
        color: theme.textDim
    }
}
