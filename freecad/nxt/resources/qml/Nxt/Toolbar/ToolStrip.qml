import QtQuick
import Qt.labs.qmlmodels
import Nxt.Toolbar

// Nxt's tool strip: every command of FreeCAD's shown toolbars in one row,
// wrapping when the window is narrow. Context: `strip` (toolbars/bridge.py)
// and `theme`. Rows carry kind, text, tip, enabled, checkable, checked,
// icon, dropdown, choices and current.
Item {
    id: root

    readonly property int gap: Math.max(1, Math.round(theme.rowHeight * 0.08))
    readonly property int padding: Math.max(2, Math.round(strip.iconSize * 0.2))
    readonly property int itemSize: strip.iconSize + 2 * padding

    implicitHeight: flow.implicitHeight + 2 * gap

    Flow {
        id: flow
        x: root.gap
        y: root.gap
        width: Math.max(0, root.width - 2 * root.gap)
        spacing: root.gap

        Repeater {
            model: strip.model

            delegate: DelegateChooser {
                role: "kind"

                DelegateChoice {
                    roleValue: "separator"
                    StripSeparator { height: root.itemSize }
                }

                DelegateChoice {
                    roleValue: "choice"
                    ChoiceBar {
                        required property int index
                        required property var model
                        size: root.itemSize
                        iconSize: strip.iconSize
                        choices: model.choices
                        current: model.current
                        enabled: model.enabled
                        onChosen: (choice) => strip.choose(index, choice)
                    }
                }

                DelegateChoice {
                    ToolItem {
                        required property int index
                        required property var model
                        size: root.itemSize
                        iconSize: strip.iconSize
                        icon: model.icon
                        text: model.kind === "button" || model.icon === ""
                              ? model.text : ""
                        tip: model.tip || model.text
                        enabled: model.enabled
                        checked: model.checked
                        dropdown: model.dropdown
                        onActivated: {
                            const at = mapToItem(null, 0, height);
                            strip.activate(index, at.x, at.y);
                        }
                        onMenuRequested: (at) => strip.openMenu(index, at.x, at.y)
                    }
                }
            }
        }
    }
}
