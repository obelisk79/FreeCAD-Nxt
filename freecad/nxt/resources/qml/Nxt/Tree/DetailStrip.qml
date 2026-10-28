import QtQuick
import Nxt.Controls

// Expanded row details: the finding in words, constraint state, references
// and dependents.
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
    readonly property bool hasUses: strip.refs && strip.refs.length > 0
    readonly property bool hasUsers: strip.consumers
                                     && strip.consumers.length > 0
    readonly property bool hasValues: strip.keyProps
                                      && strip.keyProps.length > 0
    readonly property bool hasContent: hasFindings || hasUses || hasUsers
                                    || strip.isProfile || strip.isLifted
                                    || hasValues || strip.propertyCount > 0


    //: Variables (a VarSet's): two columns, each name over its value.
    readonly property bool stackedValues: strip.hasValues
                                          && !!strip.keyProps[0].stacked

    Grid {
        visible: strip.stackedValues
        width: parent.width
        columns: 2
        columnSpacing: 10
        rowSpacing: 4

        Repeater {
            model: strip.stackedValues ? strip.keyProps.length : 0

            KeyValue {
                required property int index
                spec: strip.keyProps[index]
                owner: strip.owner
                cellWidth: Math.max(60, (strip.width - 10) / 2)
                onEdited: function (value) {
                    strip.keyEdited(spec.name, value);
                }
            }
        }
    }

    Flow {
        visible: (strip.hasValues && !strip.stackedValues)
                 || strip.propertyCount > 0
        width: parent.width
        spacing: 10

        // Counted, not the list: a new list would recreate delegates and drop focus.
        Repeater {
            model: strip.keyProps && !strip.stackedValues
                   ? strip.keyProps.length : 0

            KeyValue {
                required property int index
                spec: strip.keyProps[index]
                owner: strip.owner
                onEdited: function (value) {
                    strip.keyEdited(spec.name, value);
                }
            }
        }

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


    // Unknown is shown, not hidden: a silent solver must not look like "fine".
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


    Flow {
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
        // Only for something lifted; on a plain feature it is the normal state.
        visible: strip.isLifted && !strip.hasUsers
        text: qsTr("nothing uses this yet")
        font.pixelSize: strip.lineSize
        font.italic: true
        color: theme.textDim
    }
}
