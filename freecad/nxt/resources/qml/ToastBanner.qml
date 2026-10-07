import QtQuick
import Nxt

// The undo toast in the 3D view (toast.py). Sized to its content; the
// Python side centres it at the top of the view, and hides it once it
// has faded.
UndoToast {
    id: banner

    // Null-safe: the banner can outlive `toasts` by an event at teardown.
    actions: toasts ? toasts.labels : []
    sticky: toasts ? toasts.sticky : false
    // Not visible until first shown, which is not a toast going away.
    property bool ready: false

    Component.onCompleted: {
        ready = true;
        show(toasts.message);
    }
    onActionRequested: (index) => toasts.act(index)
    onVisibleChanged: if (ready && !visible) toasts.dismissed()

    Connections {
        target: toasts
        function onShown() { banner.show(toasts.message); }
        function onCleared() { banner.dismiss(); }
    }
}
