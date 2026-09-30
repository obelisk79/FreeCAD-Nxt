import QtQuick
import Nxt

// The isolate notice in the 3D view (isolate_notice.py). Sized to its
// content; the Python side centres it at the top of the view.
IsolationNotice {
    text: isolation.notice
    onExitRequested: isolation.leave()
}
