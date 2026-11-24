
import QtQuick
import Nxt.Controls
import Nxt.Tree
import Nxt.Inspector
Rectangle {
    id: host
    width: 120; height: 200
    Component { id: popupComponent; TreeSettings {} }
    function open() {
        var popup = popupComponent.createObject(host);
        popup.x = 10; popup.y = 10;
        popup.open();
        return popup;
    }
}
