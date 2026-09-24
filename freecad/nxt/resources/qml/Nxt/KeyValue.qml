import QtQuick

// One of an object's defining values in the detail strip: its name, and
// the editor for its kind (see ValueEditor).
Row {
    id: entry

    property var spec: ({})             // one entry from properties.describe
    signal edited(var value)

    spacing: 6

    Text {
        height: theme.fieldHeight
        verticalAlignment: Text.AlignVCenter
        text: entry.spec.name || ""
        font.pixelSize: theme.fontSmall
        color: theme.textDim
    }

    ValueEditor {
        spec: entry.spec
        width: entry.spec.kind === "quantity" || entry.spec.kind === "number"
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
