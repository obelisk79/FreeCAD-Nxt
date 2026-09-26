import QtQuick
import QtQuick.Controls.Basic

// The tree's context menu: Qt Quick Controls' Menu, in its own window.
//
// `popupType: Popup.Window` (Qt 6.8+) gives the menu a popup window of its
// own, as QMenu has, so it reaches past the dock, closes on a click anywhere
// else or on Escape, opens More on hover as a cascading submenu, and is
// walked with the arrow keys - all Qt's, none of it ours. The Basic style
// is imported by name so FreeCAD's widget style cannot reach in; every
// visible part is drawn here, in the panel's theme.
//
// What goes in it is decided in Python from the TOML definition files and
// arrives as plain data (menus/present.py). `load()` builds the items from
// it; one menu is made per opening and destroyed when it closes.
Menu {
    // Not `menu`: every MenuItem has a `menu` property of its own, which
    // would shadow it inside the rows.
    id: contextMenu

    popupType: Popup.Window
    // Submenus open beside the menu on hover, as a desktop menu's do; the
    // default depends on the platform.
    cascade: true
    // Opens at its anchor's corner, not overlapping it: the anchor is a
    // point (see NxtTree.qml).
    overlap: 0
    padding: 4
    // Wide enough for the icon bar, and for the longest row.
    implicitWidth: Math.max(236, contentWidth + leftPadding + rightPadding)


    signal chosen(string command)

    background: Rectangle {
        implicitWidth: 236
        radius: 5
        color: theme.background
        border.width: 1
        border.color: theme.border
    }

    // The item that stands for More in this menu is made from this.
    delegate: Row_ {}

    onClosed: Qt.callLater(contextMenu.destroy)

    // ------------------------------------------------------------ building

    // One entry: a row, or a submenu when it has items of its own.
    function addEntry(target, spec, style) {
        if (spec.items && spec.items.length) {
            var inner = submenu.createObject(null, {title: spec.label});
            for (var i = 0; i < spec.items.length; ++i)
                addEntry(inner, spec.items[i], "plain");
            target.addMenu(inner);
        } else {
            target.addItem(entry.createObject(null, {spec: spec,
                                                     style: style}));
        }
    }

    function load(spec) {
        addItem(header.createObject(null, {title: spec.title || "",
                                           subtitle: spec.subtitle || ""}));
        if ((spec.bar || []).length)
            addItem(bar.createObject(null, {buttons: spec.bar}));
        if (spec.lead)
            addItem(entry.createObject(null, {spec: spec.lead,
                                              style: "lead"}));
        for (var s = 0; s < (spec.state || []).length; ++s)
            addItem(entry.createObject(null, {spec: spec.state[s],
                                              style: "state"}));
        var sections = spec.sections || [];
        for (var i = 0; i < sections.length; ++i) {
            addItem(label.createObject(null, {text: sections[i].name}));
            for (var j = 0; j < sections[i].items.length; ++j)
                addEntry(contextMenu, sections[i].items[j], "plain");
        }
        addItem(separator.createObject(null));
        if (spec.delete)
            addItem(entry.createObject(null, {spec: spec.delete,
                                              style: "danger"}));
        var groups = spec.more || [];
        if (groups.length) {
            var more = submenu.createObject(null, {title: qsTr("More")});
            for (var g = 0; g < groups.length; ++g) {
                if (g > 0)
                    more.addItem(separator.createObject(null));
                if (groups[g].name)
                    more.addItem(label.createObject(null,
                                                    {text: groups[g].name}));
                for (var k = 0; k < groups[g].items.length; ++k)
                    addEntry(more, groups[g].items[k], "plain");
            }
            addMenu(more);
        }
    }

    function choose(command) {
        contextMenu.chosen(command);
    }

    // ------------------------------------------------------------- parts

    component Row_: MenuItem {
        id: row
        property var spec: ({})
        property string style: "plain"
        property string shortcutText: spec.shortcut || ""

        // The row standing for More is made by the Menu itself, with no
        // spec: it takes its label from the submenu.
        text: subMenu ? subMenu.title : (spec.label || "")
        enabled: subMenu !== null || spec.enabled === true
        implicitHeight: theme.rowHeight
        // Hover highlights a row and opens More; not left to the platform.
        hoverEnabled: true
        leftPadding: 10
        rightPadding: 10
        font.pixelSize: theme.fontSmall
        font.bold: style === "lead"

        contentItem: Item {
            implicitWidth: rowLabel.implicitWidth
                           + (row.shortcutText
                              ? rowShortcut.implicitWidth + 24 : 0)
                           + (row.subMenu ? 16 : 0)
            implicitHeight: rowLabel.implicitHeight

            Text {
                id: rowLabel
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - (row.shortcutText
                                       ? rowShortcut.width + 12 : 0)
                elide: Text.ElideRight
                text: row.text
                font: row.font
                color: !row.enabled ? theme.textDim
                     : row.style === "danger" ? theme.danger
                     : theme.text
                opacity: row.enabled ? 1.0 : 0.6
            }
            Text {
                id: rowShortcut
                anchors.verticalCenter: parent.verticalCenter
                anchors.right: parent.right
                visible: row.shortcutText.length > 0
                text: row.shortcutText
                font.pixelSize: theme.fontAside
                color: theme.textDim
            }
        }

        arrow: Text {
            x: row.width - width - 8
            anchors.verticalCenter: parent.verticalCenter
            visible: row.subMenu !== null
            text: "›"
            font.pixelSize: theme.fontSmall
            color: theme.textDim
        }

        background: Rectangle {
            radius: 3
            color: row.highlighted && row.enabled ? theme.hover
                 : row.style === "state"
                   ? Qt.rgba(theme.warning.r, theme.warning.g,
                             theme.warning.b, 0.22)
                   : "transparent"
        }
    }

    Component {
        id: entry
        Row_ {
            onTriggered: contextMenu.choose(spec.command)
        }
    }

    Component {
        id: submenu

        Menu {
            id: sub
            popupType: Popup.Window
            padding: 4
            implicitWidth: Math.max(180, contentWidth + leftPadding
                                         + rightPadding)
            delegate: Row_ {}
            background: Rectangle {
                implicitWidth: 180
                radius: 5
                color: theme.background
                border.width: 1
                border.color: theme.border
            }
        }
    }

    Component {
        id: label

        Item {
            property alias text: caption.text
            implicitWidth: caption.implicitWidth + 20
            implicitHeight: theme.rowHeight - 4

            Text {
                id: caption
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 2
                x: 10
                font.pixelSize: theme.fontAside - 1
                font.letterSpacing: 0.6
                font.bold: true
                font.capitalization: Font.AllUppercase
                color: theme.textDim
            }
        }
    }

    Component {
        id: separator

        MenuSeparator {
            topPadding: 4
            bottomPadding: 4
            contentItem: Rectangle {
                implicitHeight: 1
                color: theme.border
            }
        }
    }

    // What the menu is for.
    Component {
        id: header

        Item {
            property string title
            property string subtitle
            implicitWidth: titleRow.implicitWidth + 20
            implicitHeight: theme.rowHeight

            Row {
                id: titleRow
                x: 6
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.parent.title
                    font.pixelSize: theme.fontSmall
                    font.bold: true
                    color: theme.text
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.parent.subtitle
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }
            }
        }
    }

    // The icon bar: the same five for every object; one that does not
    // apply is dimmed where it stands.
    //
    // A MenuItem, so the keyboard can stop on it like any row: Down from
    // the top reaches it, Left and Right move between its buttons, Enter
    // runs the one marked.
    Component {
        id: bar

        MenuItem {
            id: barItem
            property var buttons: []
            property int current: 0

            // The bar's width is shared out among its buttons.
            readonly property real buttonWidth:
                (width - 4 - 2 * Math.max(0, buttons.length - 1))
                / Math.max(1, buttons.length)

            function step(by) {
                var n = buttons.length;
                for (var k = 1; k <= n; ++k) {
                    var next = (current + by * k + n * k) % n;
                    if (buttons[next].enabled) {
                        current = next;
                        return;
                    }
                }
            }

            implicitWidth: 228
            implicitHeight: 44
            padding: 0
            hoverEnabled: false
            Keys.onLeftPressed: step(-1)
            Keys.onRightPressed: step(1)
            onTriggered: {
                var spec = buttons[current];
                if (spec && spec.enabled)
                    contextMenu.choose(spec.command);
            }
            Component.onCompleted: if (buttons.length && !buttons[0].enabled)
                                       step(1)

            background: Item {}

            contentItem: Row {
                spacing: 2
                bottomPadding: 4
                leftPadding: 2

                Repeater {
                    model: barItem.buttons

                    Rectangle {
                        id: button
                        required property var modelData
                        required property int index
                        readonly property bool usable: modelData.enabled
                        // Marked for the keyboard only while the bar has
                        // it, so a mouse user never sees two highlights.
                        readonly property bool marked:
                            barItem.highlighted && barItem.current === index

                        width: barItem.buttonWidth
                        height: 40
                        radius: 4
                        color: (buttonMouse.containsMouse || marked) && usable
                               ? theme.hover : theme.surface
                        border.width: marked ? 1 : 0
                        border.color: theme.accent
                        opacity: usable ? 1.0 : 0.4

                        Column {
                            anchors.centerIn: parent
                            spacing: 2

                            Image {
                                anchors.horizontalCenter:
                                    parent.horizontalCenter
                                width: 16
                                height: 16
                                sourceSize.width: 32
                                sourceSize.height: 32
                                source: button.modelData.icon
                                    ? "image://nxticon/@cmd/"
                                      + button.modelData.icon
                                    : ""
                            }
                            Text {
                                anchors.horizontalCenter:
                                    parent.horizontalCenter
                                text: button.modelData.short
                                      || button.modelData.label
                                font.pixelSize: theme.fontAside
                                color: theme.textDim
                            }
                        }

                        MouseArea {
                            id: buttonMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: button.usable
                                ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: {
                                if (!button.usable)
                                    return;
                                contextMenu.choose(button.modelData.command);
                                contextMenu.dismiss();
                            }
                        }

                        Accessible.role: Accessible.Button
                        Accessible.name: button.modelData.label
                    }
                }
            }
        }
    }
}
