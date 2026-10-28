import QtQuick
import Nxt.Controls

// One defining value in the detail strip: name and editor (ValueEditor),
// side by side, or the name over the editor when stacked (VarSet variables).
Grid {
    id: entry

    //: Width for the editor when stacked; the column's.
    property real cellWidth: 120
    readonly property bool stacked: !!entry.spec.stacked

    property var spec: ({})             // one entry from properties.describe
    property string owner: ""           // the object, for expressions
    signal edited(var value)

    columns: stacked ? 1 : 2
    columnSpacing: 6
    rowSpacing: 1

    Text {
        height: entry.stacked ? implicitHeight : theme.fieldHeight
        width: entry.stacked ? entry.cellWidth : implicitWidth
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
        text: entry.spec.name || ""
        font.pixelSize: theme.fontSmall
        color: theme.textDim
    }

    ValueEditor {
        spec: entry.spec
        owner: entry.owner
        width: entry.stacked ? entry.cellWidth
               : entry.spec.kind === "quantity" || entry.spec.kind === "number"
               ? Math.max(64, Math.min(160, valueMetrics.advanceWidth + 30))
               : implicitWidth
        onEdited: function (value) { entry.edited(value); }
    }

    TextMetrics {
        id: valueMetrics
        font.pixelSize: theme.fontSmall
        text: entry.spec.expression ? "= " + entry.spec.expression
                                    : (entry.spec.text || "")
    }
}
