import QtQuick

// One row of the panel.
//
// Indentation is drawn, not structural: the model hands us a depth and we
// offset. That is what lets a sketch be lifted out of the feature that
// claims it and placed beside that feature instead - the row does not know
// it was ever nested, it only knows its depth.
//
// A row is two parts stacked: the line itself, which is always exactly one
// row high, and a detail strip below it that is closed almost always. The
// line has to stay a fixed height for the timeline bar to be able to land
// between two of them; the strip is allowed to make the delegate taller,
// which is why the bar asks the list where a row is rather than
// multiplying an index by a row height.
Item {
    id: row

    required property int index
    required property string name
    required property string label
    required property int depth
    required property bool hasChildren
    required property bool expanded
    required property bool objectVisible
    required property bool selected
    required property string iconUrl
    required property var refs
    required property bool isContainer
    required property bool inError
    required property bool highlighted
    required property bool isFeature
    required property bool afterTip
    required property bool isProfile
    required property bool isLifted
    required property bool isActive
    required property int severity
    required property var notes
    required property int dof
    required property int constrained
    required property bool detailOpen
    required property string bodyName
    required property var consumers
    required property var keyProps
    required property int propertyCount

    // The feature that made the face just picked in the 3D view, when that
    // is not the selected object - the tip, for a face on a Body's solid.
    // Outlined in the accent colour, over a hover-coloured fill, until the
    // selection changes: marked, not selected, because the selection is
    // FreeCAD's and is the face.
    readonly property bool pickOrigin: nxt.pickOrigins.indexOf(row.name) >= 0

    property Item dragGhost
    property bool dropTarget: false
    property bool renaming: false

    // Opens the Property Inspector level with this row, beside the dock's
    // border (-1 says so) in both modes. Beside the pill in overlay mode
    // put the inspector over the panel, which draws above it there.
    function openInspector() {
        var corner = row.mapToGlobal(0, 0);
        nxt.openPropertyInspector(row.name, -1, corner.y);
    }
    //: Widest the detail strip may grow, shared with the panel header.
    property real detailCap: width

    // A click on the label of a row that is already the selection starts a
    // rename - the file-manager gesture, and the one thing a single click
    // can mean on a row that is already selected. It cannot fire on the
    // click that *made* the selection, or a row could never be selected by
    // its name without going into an edit box.
    //
    // Deferred by the platform's double-click interval, because a double
    // click opens the object and its first half looks exactly like this.
    // Whichever arrives first wins, and a drag cancels it outright.
    Timer {
        id: renameDelay
        interval: Application.styleHints.mouseDoubleClickInterval + 20
        onTriggered: if (row.selected && !row.renaming) row.beginRename()
    }

    function armRename() { renameDelay.restart(); }
    function disarmRename() { renameDelay.stop(); }

    // Hit-tested against the label's *glyphs* rather than its box, which
    // runs most of the width of the row. Clicking the empty space beside a
    // short name is not clicking the name.
    function overGlyphs(x, y) {
        var local = title.mapFromItem(head, x, y);
        var glyphs = Math.min(title.width, title.contentWidth);
        return local.x >= 0 && local.x <= glyphs
            && local.y >= 0 && local.y <= title.height;
    }

    // Losing the selection cancels a pending rename: it was armed because
    // this row was the selection, and it no longer is.
    onSelectedChanged: if (!row.selected) row.disarmRename()

    // Rename edits Label, never Name: Name is the immutable identifier every
    // link in the document is written against.
    function beginRename() {
        renameInput.text = row.label;
        row.renaming = true;
        renameInput.forceActiveFocus();
        renameInput.selectAll();
    }

    function commitRename() {
        if (!row.renaming)
            return;
        row.renaming = false;
        nxt.rename(row.name, renameInput.text);
    }

    function cancelRename() {
        // Clears the flag first, so the focus loss that follows finds
        // nothing left to commit.
        row.renaming = false;
    }

    width: ListView.view ? ListView.view.width : 280
    implicitHeight: head.height + (showDetail ? detail.height : 0) + gap

    // Where this row's overlay pill ends, for anything that has to line up
    // with it from outside the list - the timeline bar, which is not a row
    // and so cannot anchor to one.
    readonly property real pillRight: theme.overlay
                                    ? tail.x + tail.width + 5
                                    : head.width

    // ------------------------------------------------------------- the gap

    // While something is being dragged, the row it would land under opens a
    // little. A drop target outline says *which* row; the gap says where the
    // thing in your hand is going to end up, which is the question actually
    // being asked mid-drag. Animated, because an instant jump reads as the
    // list twitching rather than as a space being made.
    readonly property bool gapBelow: ListView.view
                                     && ListView.view.gapAfterRow === row.index
    // A reorder within a Body opens a whole row's height: the dragged row
    // itself is on its way into that space. Any other drop only hints.
    readonly property int dragGapHeight:
        ListView.view && ListView.view.reorderDrag
            ? theme.rowHeight : Math.round(theme.rowHeight * 0.55)
    // This row is the one in your hand: it stays where it was, faded, as a
    // reminder of where it came from, while its image follows the pointer.
    readonly property bool dragSource: ListView.view
                                       && ListView.view.dragSource === row.name
    property real gap: 0
    onGapBelowChanged: gap = gapBelow ? row.dragGapHeight : 0

    Behavior on gap {
        NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
    }

    // What the gutter mark says. Four states, four silhouettes - see
    // SeverityMark. A sketch that is merely under-constrained gets the
    // quietest of them, because that is the state most sketches are in
    // most of the time and it is not a fault.
    readonly property int markLevel: {
        if (row.severity >= 2) return 3;
        if (row.severity >= 1) return 2;
        if (row.isProfile && row.constrained !== 1
                && theme.showUnderConstrained) return 1;
        return 0;
    }

    // A clean sketch has nothing to flag, but it still has a detail strip
    // worth opening - it is where the list of features using it lives. So
    // the mark's slot stays clickable and shows a faint ring on hover.
    //
    // Asked of the strip rather than worked out again here. Duplicating the
    // condition is what put a mark on a row whose strip then opened empty:
    // the mark said "this row has consumers", the strip said "only lifted
    // rows list consumers", and a feature is never lifted.
    readonly property bool hasDetail: content.hasContent
    readonly property bool showDetail: row.detailOpen && row.hasDetail

    // Does this row's failure belong to one of its profiles? If so the chip
    // carries the red and the label stays normal - reddening the feature's
    // own name blames it for something it did not do.
    readonly property bool blamedOnProfile: {
        if (!row.inError || !row.refs)
            return false;
        for (var i = 0; i < row.refs.length; ++i)
            if (row.refs[i].severity >= 2)
                return true;
        return false;
    }

    readonly property int leftPad: theme.rowPad + depth * theme.indent
    // The detail strip lines up with the row's pill, so it reads as part of
    // it. Past two levels deep it stops following the indent - a narrow
    // dock cannot spare the width - and a tick under the pill keeps the
    // two joined.
    readonly property int detailIndentCap: 2
    readonly property real pillLeft: icon.x - 5
    readonly property real detailLeft:
        Math.max(2, pillLeft - Math.max(0, depth - detailIndentCap)
                               * theme.indent)
    readonly property int guideOffset: Math.round(theme.rowHeight * 0.3)

    readonly property var shownRefs: {
        // Which ones is a preference (theme.chipMode): only those with a
        // problem, as it was designed; every one; or none, leaving the
        // detail strip to name them.
        var out = [];
        if (!row.refs || theme.chipMode === "none")
            return out;
        var all = theme.chipMode === "all";
        for (var i = 0; i < row.refs.length; ++i)
            if (all || row.refs[i].severity > 0 || row.refs[i].pinned)
                out.push(row.refs[i]);
        return out;
    }

    function chipText(ref) {
        return ref.sub.length > 0 ? ref.label + ":" + ref.sub : ref.label;
    }

    //: Beyond this many characters a name stops being shown and the chip
    //: falls back to its icon. Whole name or clean icon, never a fragment:
    //: an elided name costs the width *and* still makes you hover.
    readonly property int chipTextLimit: 16
    //: Below this the row has no width to spare whatever the name is.
    readonly property int chipTextFloor: 240

    readonly property bool compactChips: {
        if (row.shownRefs.length > 1)
            return true;
        if (row.shownRefs.length === 1)
            return row.width < row.chipTextFloor
                || row.chipText(row.shownRefs[0]).length > row.chipTextLimit;
        return false;
    }
    readonly property int chipLimit: row.compactChips ? 6 : 1

    // ================================================================= line

    Item {
        id: head
        width: parent.width
        height: theme.rowHeight
        opacity: row.dragSource ? 0.3 : 1.0

        // Never animate a colour to or from "transparent". That value is
        // transparent *black*, so ColorAnimation interpolates through
        // semi-opaque black and the row flashes a grey bar on its way in
        // and out - visible on two rows at once while one fades in and the
        // other fades out. Keep the fill colour solid and animate opacity.
        //
        // Docked, this is the row's selection/hover wash and spans the
        // width. In overlay mode it is the row's *backdrop* and wraps only
        // the content, which is what keeps a floating panel readable over
        // an arbitrary model: the scrim exists where the text is and
        // nowhere else, so the disclosure arrows sit on bare transparency
        // and the whole thing reads as labels rather than a translucent
        // sheet.
        Rectangle {
            id: fill
            y: 1
            height: parent.height - 2
            x: theme.overlay ? icon.x - 5 : 2
            width: theme.overlay
                 ? Math.max(0, tail.x + tail.width + 5 - x)
                 : Math.max(0, parent.width - 4)
            radius: 4

            color: row.selected ? theme.accent
                 : row.pickOrigin ? theme.hover
                 : !theme.overlay ? theme.hover
                 : hover.hovered ? theme.pillHover
                 : theme.pill
            opacity: theme.overlay ? 1.0
                   : (row.selected || hover.hovered || row.dropTarget
                      || row.pickOrigin) ? 1.0
                   : row.highlighted ? 0.5
                   : row.isActive ? 0.28
                   : 0.0
            border.width: row.pickOrigin && !row.selected ? 2
                        : theme.overlay && !row.selected ? 1 : 0
            border.color: row.pickOrigin ? theme.accent : theme.pillBorder

            Behavior on opacity { NumberAnimation { duration: 70 } }
            Behavior on color { ColorAnimation { duration: 70 } }
        }

        // A brief glow over the row when it was just picked in the 3D view
        // and scrolled into sight: says "here it is" after the list moved.
        // Over the fill rather than a change to it, so the selection colour
        // underneath is never animated.
        Rectangle {
            id: flash
            x: fill.x
            y: fill.y
            width: fill.width
            height: fill.height
            radius: fill.radius
            color: "transparent"
            border.width: 2
            border.color: theme.accent
            opacity: 0

            SequentialAnimation {
                id: flashAnimation
                NumberAnimation {
                    target: flash; property: "opacity"
                    to: 1; duration: 120; easing.type: Easing.OutQuad
                }
                PauseAnimation { duration: 450 }
                NumberAnimation {
                    target: flash; property: "opacity"
                    to: 0; duration: 500; easing.type: Easing.InQuad
                }
            }

            Connections {
                target: nxt
                function onFlashRows(names) {
                    if (names.indexOf(row.name) >= 0)
                        flashAnimation.restart();
                }
            }
        }

        // Drop feedback rides on its own outline so it stays visible while
        // the fill is faded out - during a drag the pointer is grabbed by
        // the source row, so this row is a drop target without being
        // hovered.
        Rectangle {
            anchors.fill: fill
            radius: fill.radius
            color: "transparent"
            border.width: row.dropTarget ? 2 : row.highlighted ? 1 : 0
            border.color: theme.accent
        }

        // A hairline guide per ancestor level, so deep nesting stays
        // readable. Suppressed in overlay mode - a rule drawn across the 3D
        // view reads as part of the model, not as part of the panel.
        Repeater {
            model: theme.overlay ? 0 : row.depth
            Rectangle {
                required property int index
                x: theme.rowPad + index * theme.indent + theme.tipGutter
                   + guideOffset
                width: 1
                height: head.height
                color: theme.border
                opacity: 0.5
            }
        }

        // ------------------------------------------------- the active mark

        Rectangle {
            objectName: "activeMark"
            visible: row.isActive
            // Outside the row's own indent when docked, so it tracks a Body
            // nested in a Part instead of floating at the panel edge. In
            // overlay mode it moves just inside the pill, for the reason
            // the spine does: a rule drawn on bare transparency over the
            // 3D view reads as part of the model.
            x: theme.overlay ? icon.x - 3 : Math.max(1, row.leftPad - 4)
            y: 2
            width: 3
            height: head.height - 4
            radius: 1.5
            color: theme.accent
        }

        // ------------------------------------------------------- the spine

        // The Body's history, drawn as a line down its children: solid
        // where the model is built, dashed past the rollback bar. This is
        // the non-colour half of the rolled-back state. Dimming alone is a
        // brightness difference, which is the cue that survives worst -
        // a dashed line and a solid line are different shapes, and stay
        // different in a greyscale screenshot or at a glance.
        Item {
            id: spine
            // Docked, the spine runs down the panel's own gutter and reads
            // as one continuous line through the Body. In overlay mode
            // there is no continuity to draw - the rows are separate pills
            // over the 3D view, and a line in the gutter would float on
            // bare transparency and read as part of the model. So it moves
            // inside the pill's left edge and appears only where it is
            // saying something: on the rows past the bar. Losing the
            // rolled-back cue entirely in overlay mode would leave that
            // state carried by dimming alone, which is the one cue this
            // panel does not rely on by itself.
            visible: row.bodyName !== "" && (!theme.overlay || row.afterTip)
            x: theme.overlay ? icon.x - 3
                             : row.leftPad + Math.round(theme.tipGutter * 0.45)
            width: 2
            height: head.height

            Rectangle {
                visible: !row.afterTip
                anchors.fill: parent
                color: theme.textDim
                opacity: 0.45
            }

            // Dashes, drawn as segments rather than with a dash pattern so
            // this costs one Repeater and no Canvas per row.
            Repeater {
                model: row.afterTip ? 3 : 0
                Rectangle {
                    required property int index
                    width: parent.width
                    height: Math.max(2, Math.round(head.height / 7))
                    y: Math.round(index * head.height / 3)
                       + Math.round(head.height / 12)
                    color: theme.textDim
                    opacity: 0.45
                }
            }
        }

        Disclosure {
            id: expander
            x: row.leftPad + theme.tipGutter
            anchors.verticalCenter: parent.verticalCenter
            shown: row.hasChildren
            expanded: row.expanded
            onToggled: nxt.toggleExpanded(row.name)
        }

        Image {
            id: icon
            x: expander.x + expander.width + 2
            anchors.verticalCenter: parent.verticalCenter
            width: theme.iconSize
            height: width
            sourceSize.width: width * 2
            sourceSize.height: width * 2
            source: row.iconUrl
            // Inside a Body, every feature but the tip is hidden by
            // definition, so Visibility says nothing useful - what matters
            // is which side of the rollback bar it is on. A sketch drawn
            // after the bar is in the same position: it had not been drawn
            // yet at the moment the bar is showing.
            opacity: row.afterTip ? 0.32
                   : row.isFeature ? 1.0
                   : row.objectVisible ? 1.0 : 0.38
            Behavior on opacity { NumberAnimation { duration: 110 } }
        }

        TextMetrics {
            id: labelMetrics
            font: title.font
            text: row.label
        }

        Text {
            id: title
            visible: !row.renaming
            anchors.verticalCenter: parent.verticalCenter
            x: icon.x + icon.width + 6
            // Never reads `tail.x` (which depends on this width in overlay
            // mode) nor its own `implicitWidth` (which an elided Text
            // re-emits on every width change). Both loop on a mode switch.
            width: theme.overlay
                 ? Math.min(labelMetrics.advanceWidth,
                            Math.max(40, head.width - x - 110))
                 : Math.max(0, head.width - x - tail.width - 16)
            text: row.label
            elide: Text.ElideMiddle
            font.pixelSize: theme.fontRow
            font.bold: row.isContainer
            font.italic: !row.objectVisible && !row.isFeature && !row.isProfile
            color: row.selected ? theme.accentText
                 : (row.inError && !row.blamedOnProfile) ? theme.danger
                 : row.afterTip ? theme.textDim
                 : row.isFeature ? theme.text
                 : row.objectVisible ? theme.text
                 : theme.textDim
        }

        Rectangle {
            visible: row.renaming
            x: renameInput.x - 4
            y: renameInput.y - 2
            width: renameInput.width + 8
            height: renameInput.height + 4
            radius: 3
            color: theme.background
            border.width: 1
            border.color: theme.accent
        }

        TextInput {
            id: renameInput
            visible: row.renaming
            anchors.verticalCenter: parent.verticalCenter
            x: title.x
            width: Math.max(60, head.width - x - 10)
            font: title.font
            color: theme.text
            selectionColor: theme.accent
            selectedTextColor: theme.accentText
            selectByMouse: true
            clip: true

            onEditingFinished: row.commitRename()
            Keys.onEscapePressed: row.cancelRename()
        }

        // ---------------------------------------------- chips and gutter

        // The right-hand group, positioned as a whole. `x` is assigned
        // rather than anchored, so switching modes moves it instead of
        // rebuilding its anchor graph - and nothing inside is ever
        // re-anchored.
        Item {
            id: tail
            y: 0
            height: parent.height
            width: chips.width + (state.width > 0 ? 6 + state.width : 0)
            x: theme.overlay ? title.x + title.width + 6
                             : Math.max(0, head.width - width - 8)

            Row {
                id: chips
                visible: !row.renaming
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                spacing: 3

                // The references carrying a problem - see `shownRefs`.
                // Kept on the operation and deliberately not mirrored onto
                // the thing read: a sketch used by six features would grow
                // a row six chips wide, and a timeline you cannot scan is
                // worse than one that states a relationship only once. The
                // other side of it lives in the read object's detail strip.
                //
                // One is named, if the name fits. Several, or one too long
                // for the row, become icons. The names are one click away
                // in the detail strip either way.
                Repeater {
                    model: row.shownRefs.slice(0, row.chipLimit)
                    Chip {
                        required property var modelData
                        compact: row.compactChips
                        text: row.chipText(modelData)
                        sub: modelData.sub
                        iconUrl: modelData.iconUrl
                        severity: modelData.severity
                        onClicked: nxt.revealObjectRow(modelData.name)
                        // Straight into the referenced object's editor.
                        onDoubleClicked: nxt.activate(modelData.name)
                        onHoveredChanged: function (h) {
                            if (h) nxt.highlightRelated(modelData.name);
                            else nxt.highlightRelated(row.name);
                        }
                    }
                }

                Chip {
                    visible: row.shownRefs.length > row.chipLimit
                    interactive: false
                    text: "+" + (row.shownRefs.length - row.chipLimit)
                }
            }

            // ----------------------------------------------- state marks

            Row {
                id: state
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: chips.right
                anchors.leftMargin: 6
                spacing: 5

                // Visibility, for everything the bar does not already
                // govern. A Body's solid features are controlled by the
                // rollback bar, and giving them an eye as well would offer
                // two controls for one piece of state that disagree the
                // moment either is used. Kept in the layout rather than
                // removed, so the gutter mark to its right sits at the
                // same x on every row and a glance down the edge of the
                // panel finds the marks in a column.
                EyeToggle {
                    anchors.verticalCenter: parent.verticalCenter
                    open: row.objectVisible
                    enabled: !row.isFeature
                    ink: row.selected ? theme.accentText : theme.textDim
                    opacity: (row.isFeature || !hover.hovered) ? 0.0 : 1.0
                    onToggled: nxt.toggleVisibility(row.name)

                    Behavior on opacity { NumberAnimation { duration: 90 } }
                }

                // The gutter. Always the last thing in the row, so it is
                // always at the same distance from the edge.
                Item {
                    anchors.verticalCenter: parent.verticalCenter
                    width: theme.markSize
                    height: width

                    SeverityMark {
                        id: mark
                        anchors.centerIn: parent
                        size: parent.width
                        level: row.markLevel > 0 ? row.markLevel
                             : (row.hasDetail && hover.hovered) ? 1 : 0
                        // A ring that only appeared because the pointer is
                        // here must not read the same as one that is
                        // telling you something.
                        opacity: row.markLevel > 0 ? 1.0 : 0.45
                        active: row.detailOpen
                        onClicked: nxt.toggleDetail(row.name)
                    }
                }
            }
        }

        HoverHandler {
            id: hover
            onHoveredChanged: hovered ? nxt.highlightRelated(row.name)
                                      : nxt.clearHighlightFor(row.name)
        }

        // ---------------------------------------------------- interaction

        DropArea {
            anchors.fill: parent
            // A reorder within a Body finds its slot from where the dragged
            // row is, not from the row under the pointer; see the drag
            // ghost in NxtTree.qml.
            enabled: !(row.ListView.view && row.ListView.view.reorderDrag)

            function setGap(open) {
                if (row.ListView.view)
                    row.ListView.view.dropGap = open ? row.index : -1;
            }

            onEntered: function (drag) {
                row.dropTarget = nxt.canDropOn(
                    row.dragGhost ? row.dragGhost.names : [], row.name);
                if (!row.dropTarget) drag.accepted = false;
                // A reparent puts the dragged object *inside* the target,
                // which is to say on the rows below it - so the space opens
                // under the target rather than above it.
                setGap(row.dropTarget);
            }
            onExited: {
                row.dropTarget = false;
                setGap(false);
            }
            onDropped: function (drop) {
                if (row.dropTarget)
                    nxt.dropOn(row.dragGhost ? row.dragGhost.names : [],
                               row.name);
                row.dropTarget = false;
                setGap(false);
            }
        }

        // z below everything else on purpose. A MouseArea that accepts a
        // press takes an exclusive grab, and delivery runs topmost-first -
        // declared last at the default z it would sit above the expander,
        // the reference chips and the gutter mark, and none of their
        // TapHandlers would ever see an event. Plain Rectangles and Text do
        // not accept mouse events, so pushing this underneath costs nothing
        // and revives the controls.
        MouseArea {
            anchors.fill: parent
            z: -1
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            property point origin
            property bool armed: false

            onPressed: function (mouse) {
                if (mouse.button === Qt.RightButton) {
                    // Opens where the row was clicked, once the selection
                    // has settled; the point is in the panel's scene.
                    var at = mapToItem(null, mouse.x, mouse.y);
                    if (row.ListView.view)
                        row.ListView.view.forceActiveFocus();
                    nxt.requestContextMenu(row.name, at.x, at.y);
                    return;
                }
                origin = Qt.point(mouse.x, mouse.y);
                armed = true;
                var wasSelected = row.selected;
                if (row.ListView.view) {
                    row.ListView.view.currentIndex = row.index;
                    row.ListView.view.forceActiveFocus();
                }
                var additive = (mouse.modifiers & Qt.ControlModifier) !== 0;
                var range = (mouse.modifiers & Qt.ShiftModifier) !== 0;
                if (range)
                    nxt.selectRange(row.name);
                else
                    nxt.select(row.name, additive);
                if (wasSelected && !additive && !row.renaming
                        && row.overGlyphs(mouse.x, mouse.y))
                    row.armRename();
            }

            onPositionChanged: function (mouse) {
                if (!armed || !row.dragGhost) return;
                var here = mapToItem(row.dragGhost.parent, mouse.x, mouse.y);
                if (!row.dragGhost.Drag.active) {
                    if (Math.abs(mouse.x - origin.x)
                            + Math.abs(mouse.y - origin.y) < 8)
                        return;
                    // Moving the object is not asking to rename it.
                    row.disarmRename();
                    // Within a Body, a drag reorders: the row itself slides
                    // up and down its column, held where it was grabbed.
                    // Anything else can go anywhere, so a label follows the
                    // pointer instead.
                    var sliding = row.bodyName !== "";
                    row.dragGhost.begin([row.name], row.label, row.iconUrl,
                                        sliding ? origin : null);
                    if (sliding) {
                        head.grabToImage(function (result) {
                            row.dragGhost.picture(result.url, head.width,
                                                  head.height);
                        });
                        var corner = row.mapToItem(row.dragGhost.parent, 0, 0);
                        row.dragGhost.x = corner.x;
                    }
                }
                if (row.dragGhost.sliding) {
                    row.dragGhost.y = here.y - origin.y;
                } else {
                    row.dragGhost.x = here.x + 10;
                    row.dragGhost.y = here.y + 6;
                }
            }

            onReleased: {
                armed = false;
                if (row.dragGhost && row.dragGhost.Drag.active)
                    row.dragGhost.finish();
            }

            // Anywhere on the row, including the label: opening the
            // object is what a double click means everywhere else in
            // FreeCAD, and splitting the row into two zones that did
            // different things on the same gesture was a rule nobody could
            // see. Renaming is the single click on an already-selected
            // name, which this cancels - the first half of a double click
            // is indistinguishable from it until the second half arrives.
            onDoubleClicked: function (mouse) {
                row.disarmRename();
                nxt.activate(row.name);
            }
        }
    }

    // =============================================================== detail

    Item {
        id: detail
        objectName: "detail"
        anchors.top: head.bottom
        width: Math.min(parent.width, row.detailCap)
        height: row.showDetail ? content.implicitHeight : 0
        visible: row.showDetail
        clip: true

        Rectangle {
            anchors.fill: parent
            anchors.leftMargin: row.detailLeft
            anchors.rightMargin: 8
            anchors.bottomMargin: 3
            radius: 4
            color: theme.chip
            opacity: theme.overlay ? 0.0 : 0.55
        }

        Rectangle {
            visible: theme.overlay
            anchors.fill: parent
            anchors.leftMargin: row.detailLeft
            anchors.rightMargin: 8
            anchors.bottomMargin: 3
            radius: 4
            color: theme.pill
            border.width: 1
            border.color: theme.pillBorder
        }

        // Only when the strip has stopped short of the pill: a tick on its
        // top edge, under the pill's start, says whose strip it is.
        Rectangle {
            visible: row.detailLeft < row.pillLeft - 1
            x: row.pillLeft
            y: 0
            width: 14
            height: 2
            radius: 1
            color: theme.accent
        }

        // Close. The strip's own button, so a strip opened from the gutter
        // mark or the menu can be closed where it is; Escape does the same.
        Item {
            id: closeButton
            z: 2
            anchors.right: parent.right
            anchors.rightMargin: 10
            y: 2
            width: 18
            height: 18

            Rectangle {
                anchors.fill: parent
                radius: 3
                color: theme.hover
                visible: closeMouse.containsMouse
            }
            Text {
                anchors.centerIn: parent
                text: "\u00d7"
                font.pixelSize: theme.fontRow
                color: closeMouse.containsMouse ? theme.text : theme.textDim
            }
            MouseArea {
                id: closeMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: nxt.toggleDetail(row.name)
            }
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Close details")
        }

        DetailStrip {
            id: content
            x: row.detailLeft + 8
            width: Math.max(40, parent.width - x - 14 - closeButton.width)
            level: row.markLevel
            notes: row.notes
            dof: row.dof
            constrained: row.constrained
            consumers: row.consumers
            refs: row.refs
            isProfile: row.isProfile
            isLifted: row.isLifted
            keyProps: row.keyProps
            propertyCount: row.propertyCount
            onKeyEdited: function (prop, value) {
                nxt.setKeyProperty(row.name, prop, value);
            }
            onAllPropertiesRequested: row.openInspector()
            onConsumerClicked: function (name) { nxt.revealObjectRow(name); }
            onReferenceClicked: function (name) { nxt.revealObjectRow(name); }
            onChipActivated: function (name) { nxt.activate(name); }
            onChipHovered: function (name, hovered) {
                if (hovered) nxt.highlightRelated(name);
                else nxt.highlightRelated(row.name);
            }
        }
    }
}
