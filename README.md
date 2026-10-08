<img src="freecad/nxt/resources/icons/FreeCAD-Nxt.svg" alt="" width="64" align="right">

# Nxt

A modern, fluid UI/UX replacement for FreeCAD built on QtQuick/QML.
======
[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/K4H827QS0N)

> [!WARNING]
> **Experimental: Nxt is under heavy development.** Expect bugs, rough
> edges, and features that change or disappear between updates without
> notice. Some of it changes your documents for you (for example, the
> automatic repair of sketches whose profile will not close), so keep
> backups of models you care about, and report problems on the
> [issue tracker](https://github.com/obelisk79/FreeCAD-Nxt/issues).



**FreeCAD-Nxt** transforms how you navigate and interact with your 3D CAD models. By replacing legacy desktop trees and property lists with intuitive visual overlays, direct viewport gizmos, and proactive geometry diagnostics, FreeCAD-Nxt delivers a refined, modern CAD user experience without sacrificing FreeCAD’s underlying parametric power.

---

## Key Highlights & Intent

* **Visual Design Clarity**: Replaces deeply nested trees with clean, collapsible model structures
* **Proactive Geometry Diagnostics**: Automatically catches common "Wire not closed" errors and auto-applies fixes before feature generation fails.
* **Direct Viewport Interaction**: Edit feature properties, and modify values with input fields directly in 3D space
* **Modernized Feature Hierarchy**: Adds new methods for displaying feature hierarchy and relationships visually within the tree view
* **Improved error indicators**: Adds error 'chips' to tree objects which can be interacted with to initiate corrective edits

---


## Features

### Smart Geometry & Auto-Repair
* **"Wire Not Closed" Auto-Repair**: Heuristics automatically detect open endpoints or tiny gaps in a sketch when creating 3D features (Pads, Pockets, Revolves) and offers transparent repair options.
* **Improved Attachment Handling**: Streamlined `PartDesign_Sketch` attachment workflows for cleaner face-reattachment and positioning.
* **Feedback & Undo**: Non-destructive actions display interactive toast notifications with single-click **Undo** capabilities.

### Modern Model Panel & Tree Hierarchy
* **Intuitive Feature Flow**: Displays model elements in their chronological creation order while maintaining clear logical grouping.
* **Dependency Mapping**: Visualizes consumed geometry (such as a Sketch consumed by a Pad) so you can track parametric relationships at a glance.
* **Overlay Mode**: Toggle floating model panel labels directly over the viewport to keep your focal point on the geometry.
* **In-Line Renaming & Reordering**: Reorder features via visual drag handles and rename elements cleanly without losing panel focus.

### Interactive Property Inspector & Viewport Gizmos
* **Context-Aware Inspector**: Automatically formats and groups properties for selected features, faces, or bodies.
* **On-Canvas Controls**: Double-click faces or features in 3D space to summon float-input fields, directional gizmos, and step settings without digging through menus.
* **Enhanced 3D Picking**: Select 3D geometry and instantly trace back to the specific parametric feature that created it.

---

## Getting Started

### Installation

#### Option 1: FreeCAD Addon Manager *(Custom Repository)*

FreeCAD-Nxt is currently available as a custom addon source in the standard FreeCAD Addon Manager.

1. Open **FreeCAD**.
2. Navigate to **Tools** ➔ **Addon Manager**.
2. Navigate to the Edit menu >  **Preferences** and find the section for the addon manager on the left side.
4. Under the **Custom Repositories** section, click **Add**.
5. Enter the repository details:
   * **URL**: `https://github.com/obelisk79/FreeCAD-Nxt`
   * **Branch**: `main`
6. Click **Save** / **OK** and close the preferences dialog.
7. Search for **FreeCAD-Nxt** in the Addon Manager list and click **Install**.
8. Restart FreeCAD.

---

#### Option 2: Manual Installation

Clone or copy the repository directory directly into your local FreeCAD `Mod` directory:

* **Linux**: `~/.local/share/FreeCAD/Mod/FreeCAD-Nxt`
* **macOS**: `~/Library/Application Support/FreeCAD/Mod/FreeCAD-Nxt`
* **Windows**: `%APPDATA%\FreeCAD\Mod\FreeCAD-Nxt`

```bash
git clone [https://github.com/obelisk79/FreeCAD-Nxt.git](https://github.com/obelisk79/FreeCAD-Nxt.git) ~/.local/share/FreeCAD/Mod/FreeCAD-Nxt
