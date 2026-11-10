import QtQuick
import Nxt.Controls

// The welcome on Nxt's first run (app/welcome.py): what Nxt adds, and
// recommended addons not yet installed, each installable from here.
Rectangle {
    id: root

    readonly property int pad: 20
    readonly property int gap: 14

    implicitWidth: 460
    implicitHeight: body.implicitHeight + 2 * pad
    color: theme.background

    Keys.onEscapePressed: welcome.close()

    Column {
        id: body
        x: root.pad
        y: root.pad
        width: root.width - 2 * root.pad
        spacing: root.gap

        Row {
            spacing: 12

            Image {
                width: 56
                height: 56
                sourceSize.width: 112
                sourceSize.height: 112
                source: welcome.logo
                fillMode: Image.PreserveAspectFit
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2

                Text {
                    text: qsTr("Welcome to Nxt")
                    font.pixelSize: Math.round(theme.fontRow * 1.6)
                    font.bold: true
                    color: theme.text
                }
                Text {
                    text: qsTr("A faster, clearer interface for FreeCAD.")
                    font.pixelSize: theme.fontSmall
                    color: theme.textDim
                }
            }
        }

        Column {
            width: parent.width
            spacing: 5

            Repeater {
                model: [
                    qsTr("Model tree with a rollback bar, problem marks and drag-and-drop"),
                    qsTr("Property Inspector laid out for each feature"),
                    qsTr("Part Design task panels built for speed and the keyboard"),
                    qsTr("Nxt Fillet and Chamfer, with handles in the 3D view"),
                    qsTr("Section view, and values to type or scroll in the 3D view")
                ]

                Row {
                    required property string modelData
                    spacing: 8
                    width: parent.width

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 6
                        height: 6
                        radius: 3
                        color: theme.accent
                    }
                    Text {
                        width: parent.width - 14
                        wrapMode: Text.Wrap
                        text: parent.modelData
                        font.pixelSize: theme.fontSmall
                        color: theme.text
                    }
                }
            }

            Text {
                topPadding: 2
                text: qsTr("Settings: Edit > Preferences > FreeCAD-Nxt")
                font.pixelSize: theme.fontAside
                color: theme.textDim
            }
        }

        Column {
            visible: welcome.addons.length > 0
            width: parent.width
            spacing: 6

            Text {
                text: qsTr("Recommended")
                font.pixelSize: theme.fontSmall
                font.bold: true
                color: theme.text
            }

            Repeater {
                model: welcome.addons

                Rectangle {
                    id: card
                    required property var modelData
                    readonly property string installState: modelData.state

                    width: parent.width
                    height: cardBody.implicitHeight + 16
                    radius: 4
                    color: theme.chip
                    border.width: 1
                    border.color: theme.border

                    Column {
                        id: cardBody
                        x: 10
                        y: 8
                        width: parent.width - 20 - action.width - 10
                        spacing: 2

                        Text {
                            text: card.modelData.name
                            font.pixelSize: theme.fontSmall
                            font.bold: true
                            color: theme.text
                        }
                        Text {
                            width: parent.width
                            wrapMode: Text.Wrap
                            text: card.modelData.blurb
                            font.pixelSize: theme.fontSmall
                            color: theme.textDim
                        }
                        Text {
                            visible: card.installState === "failed"
                            width: parent.width
                            wrapMode: Text.Wrap
                            text: qsTr("Not installed: %1").arg(card.modelData.error)
                            font.pixelSize: theme.fontAside
                            color: theme.danger
                        }
                    }

                    Item {
                        id: action
                        anchors.right: parent.right
                        anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.max(installButton.implicitWidth,
                                        progress.implicitWidth)
                        height: theme.fieldHeight

                        TextButton {
                            id: installButton
                            anchors.right: parent.right
                            visible: card.installState === "missing"
                                     || card.installState === "failed"
                            text: card.installState === "failed" ? qsTr("Retry")
                                                           : qsTr("Install")
                            primary: true
                            onClicked: welcome.install(card.modelData.name)
                        }
                        Text {
                            id: progress
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !installButton.visible
                            text: card.installState === "installing"
                                  ? qsTr("Installing…") : qsTr("Installed")
                            font.pixelSize: theme.fontSmall
                            color: theme.textDim
                        }
                    }
                }
            }
        }

        Item {
            width: parent.width
            height: theme.fieldHeight

            Text {
                visible: welcome.restartNeeded
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - buttons.width - 8
                elide: Text.ElideRight
                text: qsTr("Restart FreeCAD to use what was installed.")
                font.pixelSize: theme.fontSmall
                color: theme.textDim
            }
            Row {
                id: buttons
                anchors.right: parent.right
                spacing: 4

                TextButton {
                    visible: welcome.restartNeeded
                    text: qsTr("Restart now")
                    onClicked: welcome.restart()
                }
                TextButton {
                    text: qsTr("Get started")
                    primary: true
                    onClicked: welcome.close()
                }
            }
        }
    }
}
