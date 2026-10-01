import QtQuick

// A drop target for the document's top level (bridge.dropOnRoot): the
// header's document name, and empty space below the rows when docked.
// `accepting` is true while a drag it would take is over it, for whoever
// draws the highlight.
DropArea {
    id: area

    //: The panel's drag ghost, which carries the names being dragged.
    property Item ghost
    property bool accepting: false
    //: Optional: (x, y) -> bool, where in the area a drop is the top
    //: level's. Below the rows, for the tree's empty space: a row that
    //: refuses a drop must not hand it on to the document instead.
    property var allowAt: null

    function wanted(x, y) {
        return (allowAt === null || allowAt(x, y))
               && nxt.canDropOnRoot(names());
    }

    // A reorder within a Body slides a row up and down its column; it is
    // never a move out of the Body.
    function names() {
        return ghost && !ghost.sliding ? ghost.names : [];
    }

    onEntered: function (drag) {
        accepting = wanted(drag.x, drag.y);
    }
    onPositionChanged: function (drag) {
        accepting = wanted(drag.x, drag.y);
    }
    onExited: accepting = false
    onDropped: function (drop) {
        if (accepting && wanted(drop.x, drop.y))
            nxt.dropOnRoot(names());
        accepting = false;
    }
}
