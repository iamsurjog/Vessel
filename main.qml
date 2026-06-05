import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Pdf

ApplicationWindow {
    id: window
    visible: true
    width: 1100
    height: 750
    visibility: Window.FullScreen
    title: vesselManager.currentVesselName ? vesselManager.currentVesselName + " - Vessel Workspace" : "Vessel Launcher"

    readonly property color bgDark: vesselManager.themeBgDark
    readonly property color bgCard: vesselManager.themeBgCard
    readonly property color bgPanel: vesselManager.themeBgPanel
    readonly property color borderDark: vesselManager.themeBorderColor
    readonly property color textMain: vesselManager.themeTextPrimary
    readonly property color textMuted: vesselManager.themeTextSecondary
    readonly property color accentColor: vesselManager.themeAccent
    readonly property color dangerColor: vesselManager.themeDanger

    // Derived theme colors (auto-computed)
    readonly property color hoverBg: Qt.lighter(bgCard, 1.08)
    readonly property color buttonHoverBg: Qt.lighter(bgCard, 1.25)
    readonly property color activeBg: Qt.lighter(bgPanel, 1.2)
    readonly property color textOnAccent: "#000000"
    readonly property color successColor: "#50fa7b"
    readonly property color disabledBg: Qt.darker(bgDark, 1.15)

    // App state tracking parameter
    property bool renderModeActive: false
    property string renamingAbsPath: ""
    property bool showUpcomingPanel: false

    background: Rectangle { color: bgDark }

    Shortcut {
        sequence: "F11"
        onActivated: window.visibility = (window.visibility === Window.FullScreen) ? Window.Windowed : Window.FullScreen
    }

    StackView {
        id: rootStack
        anchors.fill: parent
        initialItem: launcherComponent

        Connections {
            target: vesselManager
            function onCurrentVesselPathChanged() {
                if (vesselManager.currentVesselPath !== "") {
                    if (rootStack.currentItem && rootStack.currentItem.id !== "workspaceView") {
                        rootStack.replace(workspaceComponent)
                    }
                } else {
                    rootStack.replace(launcherComponent)
                }
            }
        }
    }

    // ── Toast Notifications ──
    property var _toastQueue: []

    function showToast(msg, color) {
        _toastQueue.push({ text: msg, color: color || accentColor })
        if (!toastShowTimer.running && !toastHideAnim.running) {
            _dequeueToast()
        }
    }

    function _dequeueToast() {
        if (_toastQueue.length === 0) return
        var item = _toastQueue[0]
        toastInner.color = item.color === "error" ? dangerColor
                          : item.color === "success" ? successColor
                          : item.color
        toastText.color = (item.color === "error" || item.color === "success" || item.color === "#50fa7b" || item.color === "#ff5555") ? textOnAccent : textMain
        toastRect.visible = true
        toastShowAnim.start()
        toastShowTimer.start()
    }

    Rectangle {
        id: toastRect
        visible: false
        z: 9999
        anchors.horizontalCenter: parent.horizontalCenter
        y: 20
        height: toastText.implicitHeight + 20
        width: toastText.implicitWidth + 40
        radius: 8

        Rectangle {
            id: toastInner
            anchors.fill: parent; radius: 8; color: accentColor
            opacity: 0
            Behavior on opacity { NumberAnimation { duration: 250 } }
        }

        Text {
            id: toastText
            anchors.centerIn: parent
            color: textMain; font.pixelSize: 12; font.bold: true
        }

        NumberAnimation {
            id: toastShowAnim; target: toastInner; property: "opacity"; to: 1.0; duration: 250
        }
        NumberAnimation {
            id: toastHideAnim; target: toastInner; property: "opacity"; to: 0.0; duration: 250
            onStopped: {
                toastRect.visible = false
                _toastQueue.shift()
                _dequeueToast()
            }
        }

        Timer {
            id: toastShowTimer; interval: 2500
            onTriggered: toastHideAnim.start()
        }
    }

    Connections {
        target: vesselManager
        function onNotificationEmitted(message, color) {
            showToast(message, color)
        }
    }

    // =========================================================================
    // VIEW MODULE 1: LAUNCHER SCREEN
    // =========================================================================
    Component {
        id: launcherComponent
        Item {
            id: launcherView
            property string vesselPathToDelete: ""
            property string vesselNameToDelete: ""

            Dialog {
                id: deleteConfirmationDialog
                title: "Destroy Vessel Record"
                anchors.centerIn: parent
                modal: true
                standardButtons: Dialog.Yes | Dialog.No

                property string vesselPathToDelete: ""
                property string vesselNameToDelete: ""

                background: Rectangle { color: bgCard; border.color: borderDark; radius: 8 }
                
                Column {
                    spacing: 12; width: 300
                    Text { text: "PERMANENT DISK WIPE?"; color: dangerColor; font.bold: true; font.pixelSize: 15 }
                    Text { 
                        text: "Confirm deletion of '" + deleteConfirmationDialog.vesselNameToDelete + "'?\n\nThis completely erases all notes and assets from your computer disk storage framework permanently."
                        color: textMain; font.pixelSize: 12; width: parent.width; wrapMode: Text.WordWrap 
                    }
                }
                
                onAccepted: {
                    vesselManager.deleteVessel(deleteConfirmationDialog.vesselPathToDelete)
                    deleteConfirmationDialog.vesselPathToDelete = ""
                    deleteConfirmationDialog.vesselNameToDelete = ""
                }
            }

            Column {
                anchors.fill: parent; anchors.margins: 50; spacing: 24
                Row {
                    width: parent.width
                    Column {
                        width: parent.width - createBtn.width; spacing: 4
                        Text { text: "Vessels Engine Launcher"; color: textMain; font.pixelSize: 24; font.bold: true }
                        Text { text: "Open workspace notes environment containers or spawn localized text vaults."; color: textMuted; font.pixelSize: 12 }
                    }
                    Button {
                        id: createBtn; text: "+ New Vessel"
                        onClicked: newVesselPopup.open()
                        background: Rectangle { color: accentColor; radius: 6; implicitWidth: 110; implicitHeight: 34 }
                        contentItem: Text { text: "+ New Vessel"; color: textOnAccent; font.pixelSize: 13; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                }

                ScrollView {
                    width: parent.width; height: parent.height - 100; clip: true
                    ListView {
                        id: vesselsListView; width: parent.width; spacing: 10
                        model: vesselManager.vesselsList
                        delegate: Rectangle {
                            width: vesselsListView.width; height: 60; color: bgCard; border.color: borderDark; radius: 6
                            Row {
                                anchors.fill: parent; anchors.margins: 14; spacing: 15
                                Column {
                                    width: parent.width - openVesselBtn.width - deleteVesselBtn.width - 30; anchors.verticalCenter: parent.verticalCenter
                                    Text { text: modelData.name; color: textMain; font.bold: true; font.pixelSize: 14 }
                                    Text { text: modelData.path; color: textMuted; font.pixelSize: 11; elide: Text.ElideMiddle; width: parent.width }
                                }
                                Button {
                                    id: openVesselBtn; text: "Open Vessel"
                                    onClicked: vesselManager.openVessel(modelData.path)
                                    background: Rectangle { color: openVesselBtn.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 90; implicitHeight: 30 }
                                    contentItem: Text { text: "Open Vessel"; color: textMain; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                }
                                Button {
                                    id: deleteVesselBtn; text: "✕"; font.pixelSize: 14; width: 35
                                    onClicked: { deleteConfirmationDialog.vesselPathToDelete = modelData.path; deleteConfirmationDialog.vesselNameToDelete = modelData.name; deleteConfirmationDialog.open() }
                                    contentItem: Text { text: parent.text; color: textMuted; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                    background: Rectangle { color: deleteVesselBtn.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1 }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // =========================================================================
    // VIEW MODULE 2: THE APPLICATION WORKSPACE VIEW
    // =========================================================================
    Component {
        id: workspaceComponent
        Item {
            id: workspaceView
            property bool isLoadingContent: false

            Dialog {
                id: renameModalDialog
                title: "Rename Asset"
                anchors.centerIn: parent
                modal: true
                standardButtons: Dialog.Ok | Dialog.Cancel

                property string targetAbsPath: ""

                background: Rectangle { color: bgCard; border.color: borderDark; radius: 8 }

                Column {
                    spacing: 12
                    width: 280

                    Text { text: "Enter New Name:"; color: textMain; font.bold: true; font.pixelSize: 14 }
                    
                    TextField {
                        id: renameInputBox
                        width: parent.width
                        color: textMain
                        selectByMouse: true
                        background: Rectangle { color: bgDark; border.color: borderDark; radius: 4 }
                    }
                }

                onOpened: {
                    renameInputBox.forceActiveFocus()
                    renameInputBox.selectAll()
                }

                onAccepted: {
                    vesselManager.renameAsset(targetAbsPath, renameInputBox.text)
                    renameInputBox.text = ""
                    targetAbsPath = ""
                }
                onRejected: {
                    renameInputBox.text = ""
                    targetAbsPath = ""
                }
            }

            Menu {
                id: globalSidebarContextMenu
                MenuItem { text: "New Folder"; onClicked: vesselManager.createNewAsset("", true) }
                MenuItem { text: "New Droplet"; onClicked: vesselManager.createNewAsset("", false) }
            }

            Menu {
                id: itemContextMenu
                property string targetedPath: ""
                property string targetedRelPath: ""
                property string targetedName: ""
                property bool targetIsDir: false

                MenuItem { text: "New Droplet Here"; visible: itemContextMenu.targetIsDir; onClicked: vesselManager.createNewAsset(itemContextMenu.targetedRelPath, false) }
                MenuItem { text: "New Folder Here"; visible: itemContextMenu.targetIsDir; onClicked: vesselManager.createNewAsset(itemContextMenu.targetedRelPath, true) }
                
                MenuItem { 
                    text: "Rename Asset"
                    onClicked: {
                        renameModalDialog.targetAbsPath = itemContextMenu.targetedPath
                        renameInputBox.text = itemContextMenu.targetedName
                        renameModalDialog.open()
                    }
                }

                MenuItem { text: "Delete Asset"; onClicked: vesselManager.removeAsset(itemContextMenu.targetedPath) }
            }

            // Keyboard shortcut binding mechanism for content scaling conversions
            Action {
                id: toggleRenderAction
                shortcut: "Ctrl+M"
                enabled: vesselManager.activeFileName !== "" && sidebarTabBar.currentIndex !== 0
                onTriggered: window.renderModeActive = !window.renderModeActive
            }

            Row {
                anchors.fill: parent

                // ==========================================
                // SIDEBAR INTERFACE REGION
                // ==========================================
                Rectangle {
                    id: fileSidebar; width: 280; height: parent.height; color: bgPanel; border.color: borderDark

                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.RightButton
                        onClicked: (mouse) => { if(mouse.button === Qt.RightButton) globalSidebarContextMenu.popup() }
                    }

                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 12; spacing: 12

                        Row {
                            Layout.fillWidth: true; Layout.preferredHeight: 30
                            Text { text: vesselManager.currentVesselName; color: textMain; font.pixelSize: 15; font.bold: true; elide: Text.ElideRight; width: 170; anchors.verticalCenter: parent.verticalCenter }
                            Button {
                                id: closeWorkspaceBtn; text: "Exit"
                                onClicked: vesselManager.closeWorkspace()
                                background: Rectangle { color: closeWorkspaceBtn.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 50; implicitHeight: 28 }
                                contentItem: Text { text: "Exit"; color: textMain; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            }
                        }

                        TabBar {
                            id: sidebarTabBar; Layout.fillWidth: true; Layout.preferredHeight: 40; currentIndex: 2
                            background: Rectangle { color: "transparent" }
                            TabButton { id: t1; width: 85; height: 40; text: "AI"; font.pixelSize: 14; contentItem: Text { text: "AI"; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: sidebarTabBar.currentIndex === 0 ? accentColor : textMuted } }
                            TabButton { id: t2; width: 85; height: 40; text: "Files"; font.pixelSize: 14; contentItem: Text { text: "Files"; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: sidebarTabBar.currentIndex === 1 ? accentColor : textMuted } }
                            TabButton { id: t3; width: 85; height: 40; text: "Notes"; font.pixelSize: 14; contentItem: Text { text: "Notes"; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: sidebarTabBar.currentIndex === 2 ? accentColor : textMuted } }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: borderDark }

                        StackLayout {
                            id: sidebarStackLayout
                            Layout.fillWidth: true; Layout.fillHeight: true; currentIndex: sidebarTabBar.currentIndex

                            // [Index 0]: AI Chat Sidebar
                            Item {
                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 14

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "AI Chat"; color: textMain; font.bold: true; font.pixelSize: 13 }
                                        Item { Layout.fillWidth: true }
                                        Button {
                                            text: "New"
                                            onClicked: vesselManager.newConversation()
                                            background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 60; implicitHeight: 26 }
                                            contentItem: Text { text: "New"; color: textMain; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                        }
                                    }

                                    Text { text: "Recent Chats"; color: textMuted; font.pixelSize: 11; font.bold: true; Layout.topMargin: 5 }
                                    ScrollView {
                                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                        ListView {
                                            id: recentChatsList; width: parent.width; spacing: 2
                                            model: vesselManager.aiConversations
                                            delegate: ItemDelegate {
                                                width: recentChatsList.width; height: 28
                                                background: Rectangle { color: (vesselManager.activeChatId === modelData.id) ? activeBg : (hovered ? hoverBg : "transparent"); radius: 4 }
                                                contentItem: Text { text: modelData.title; color: textMain; font.pixelSize: 12; elide: Text.ElideRight }
                                                onClicked: vesselManager.selectConversation(modelData.id)
                                            }
                                        }
                                    }
                                }
                            }

                            // [Index 1]: Materials Subsystem File Panel View
                            Item {
                                id: materialsTabItem
                                
                                DropArea {
                                    id: fileDropArea
                                    anchors.fill: parent
                                    keys: ["text/uri-list"]
                                    onEntered: (drag) => { if (drag.hasUrls) drag.acceptProposedAction() }
                                    onDropped: (drop) => { if (drop.hasUrls) vesselManager.uploadMaterialFile(drop.urls[0].toString()) }
                                }
                                
                                Rectangle { 
                                    anchors.fill: parent
                                    color: accentColor
                                    opacity: fileDropArea.containsDrag ? 0.12 : 0.0
                                    border.color: accentColor
                                    border.width: fileDropArea.containsDrag ? 2 : 0
                                    visible: fileDropArea.containsDrag
                                    z: 10
                                    Text { text: "Drop Asset to Store"; color: textMain; font.bold: true; anchors.centerIn: parent } 
                                }

                                ColumnLayout {
                                    anchors.fill: parent; spacing: 10

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "Materials Vault"; color: textMain; font.bold: true; font.pixelSize: 13 }
                                        Item { Layout.fillWidth: true }
                                        Button {
                                            text: "+ Upload"
                                            onClicked: fileUploadDialog.open()
                                            background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 70; implicitHeight: 26 }
                                            contentItem: Text { text: "+ Upload"; color: textMain; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                        }
                                    }

                                    ScrollView { 
                                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                        ListView { 
                                            id: materialsListView; width: parent.width; spacing: 4
                                            model: vesselManager.materialsFiles
                                            
                                            Text {
                                                text: "No material assets imported yet.\nClick + Upload or drag files here."
                                                color: textMuted; font.pixelSize: 11; font.italic: true; horizontalAlignment: Text.AlignHCenter
                                                visible: parent.count === 0; anchors.centerIn: parent
                                            }

                                            delegate: ItemDelegate { 
                                                width: parent.width; height: 28
                                                contentItem: Text { text: modelData; color: textMain; font.pixelSize: 12; elide: Text.ElideMiddle }
                                                background: Rectangle { color: hovered ? hoverBg : "transparent"; radius: 4 }
                                                onClicked: vesselManager.handleMaterialClick(modelData)
                                            }
                                        }
                                    }
                                }
                            }

                            // [Index 2]: Droplets Note Architecture Panel View
                            Item {
                                ColumnLayout {
                                    anchors.fill: parent; spacing: 8

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "Droplets (Notes)"; color: textMain; font.bold: true; font.pixelSize: 13 }
                                        Item { Layout.fillWidth: true }
                                        Button {
                                            text: "+"; font.pixelSize: 14
                                            onClicked: vesselManager.createNewAsset("", false)
                                            contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                            background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 44; implicitHeight: 26 }
                                        }
                                        Button {
                                            text: "+"; font.pixelSize: 14
                                            onClicked: vesselManager.createNewAsset("", true)
                                            contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                            background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 44; implicitHeight: 26 }
                                        }
                                    }

                                    ScrollView {
                                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                        ListView {
                                            id: dropletsListView; width: parent.width; spacing: 2
                                            model: vesselManager.dropletsTree
                                            
                                            delegate: ItemDelegate {
                                                id: dropletDelegate
                                                width: dropletsListView.width; height: 30
                                                background: Rectangle { color: hovered ? hoverBg : "transparent"; radius: 4 }

                                                contentItem: Text {
                                                    text: modelData.name
                                                    color: (vesselManager.activeFileName === modelData.name) ? accentColor : textMain
                                                    font.pixelSize: modelData.isFile ? 12 : 13
                                                    font.bold: !modelData.isFile
                                                    verticalAlignment: Text.AlignVCenter
                                                    leftPadding: 6 + (modelData.depth * 20)
                                                }

                                                onClicked: { if (modelData.isFile) vesselManager.loadDropletContent(modelData.absPath) }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    acceptedButtons: Qt.RightButton
                                                    onClicked: (mouse) => {
                                                        if (mouse.button === Qt.RightButton) {
                                                            itemContextMenu.targetedPath = modelData.absPath
                                                            itemContextMenu.targetedRelPath = modelData.relPath
                                                            itemContextMenu.targetedName = modelData.name
                                                            itemContextMenu.targetIsDir = !modelData.isFile
                                                            itemContextMenu.popup()
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        } // End Sidebar StackLayout
                    } // End Sidebar ColumnLayout
                } // End Sidebar Rectangle

                // ==========================================
                // EDITOR CANVAS & RENDER ENGINE REGION
                // ==========================================
                Rectangle {
                    width: parent.width - fileSidebar.width - (window.showUpcomingPanel ? 220 : 0); height: parent.height; color: bgDark

                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 25; spacing: 15

                        // Editor Utility Toolbar
                        RowLayout {
                            Layout.fillWidth: true; Layout.preferredHeight: 35
                            
                            Rectangle {
                                width: 220; height: 32; color: bgPanel; radius: 6; border.color: borderDark
                                Text {
                                    text: sidebarTabBar.currentIndex === 0 ? "AI Assistant" : (vesselManager.activeFileName ? vesselManager.activeFileName : "No File Open")
                                    color: textMain; anchors.centerIn: parent; font.pixelSize: 12; font.bold: true; elide: Text.ElideMiddle; width: parent.width - 20 
                                }
                            }
                            Item { Layout.fillWidth: true }

                            Button {
                                id: upcomingToggle
                                text: "☰"; font.pixelSize: 14; width: 34; height: 32
                                onClicked: window.showUpcomingPanel = !window.showUpcomingPanel
                                ToolTip.visible: hovered
                                ToolTip.text: window.showUpcomingPanel ? "Hide Upcoming Events" : "Show Upcoming Events"
                                ToolTip.delay: 400
                                contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle {
                                    color: window.showUpcomingPanel ? buttonHoverBg : (upcomingToggle.hovered ? activeBg : "transparent")
                                    radius: 6; border.color: window.showUpcomingPanel ? accentColor : borderDark; border.width: 1
                                }
                            }

                            Button {
                                id: calendarButton
                                text: "📅"; font.pixelSize: 14; width: 34; height: 32
                                onClicked: openCalendar()
                                ToolTip.visible: hovered
                                ToolTip.text: "Calendar"
                                ToolTip.delay: 400
                                contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle {
                                    color: calendarButton.hovered ? activeBg : "transparent"
                                    radius: 6; border.color: borderDark; border.width: 1
                                }
                            }

                            Button {
                                id: settingsButton
                                text: "⚙"; font.pixelSize: 14; width: 34; height: 32
                                onClicked: settingsPopup.open()
                                ToolTip.visible: hovered
                                ToolTip.text: "Settings"
                                ToolTip.delay: 400
                                contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle {
                                    color: settingsButton.hovered ? activeBg : "transparent"
                                    radius: 6; border.color: borderDark; border.width: 1
                                }
                            }

                            Button {
                                action: toggleRenderAction
                                text: window.renderModeActive ? "Edit Source" : "View Rendered"
                                visible: sidebarTabBar.currentIndex === 0 ? false : !canvasContainer.isPdfActive
                                
                                ToolTip.visible: hovered
                                ToolTip.text: "Toggle Render Mode (Ctrl + M)"
                                ToolTip.delay: 400
                                background: Rectangle {
                                    color: parent.hovered ? activeBg : "transparent"
                                    radius: 6; border.color: borderDark; border.width: 1
                                }
                            }
                        }

                        // Display Switch Board Master Container
                        StackLayout {
                            id: workspaceStackLayout
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            currentIndex: sidebarTabBar.currentIndex === 0 ? 1 : 0 

                            // ----------------------------------------------------
                            // GRID CANVAS A: BASE FILE & EXPLO WORKSPACE (Tabs 1 & 2)
                            // ----------------------------------------------------
                            Rectangle {
                                id: canvasContainer
                                color: bgPanel; border.color: borderDark; radius: 6
                                property bool isPdfActive: vesselManager.activeFileName ? vesselManager.activeFileName.toLowerCase().endsWith(".pdf") : false
                                property bool isHtmlActive: vesselManager.activeFileName ? vesselManager.activeFileName.toLowerCase().endsWith(".html") : false

                                ScrollView {
                                    anchors.fill: parent; anchors.margins: 20; clip: true
                                    visible: !canvasContainer.isPdfActive
                                    
                                    TextArea {
                                        id: textEditArea
                                        visible: !window.renderModeActive
                                        text: vesselManager.activeFileText
                                        color: textMain; font.family: ["Courier New", "Courier", "monospace"]; font.pixelSize: 14
                                        wrapMode: TextArea.Wrap; selectByMouse: true
                                        placeholderText: "Open a Droplet note asset or type contents inside this canvas frame..."
                                        placeholderTextColor: textMuted
                                        background: Rectangle { color: "transparent" }
                                        onTextChanged: { if (!workspaceView.isLoadingContent && vesselManager.activeFileName !== "") vesselManager.autoSaveDroplet(textEditArea.text) }

                                        Connections {
                                            target: vesselManager
                                            function onActiveContentChanged() {
                                                workspaceView.isLoadingContent = true
                                                textEditArea.text = vesselManager.activeFileText
                                                workspaceView.isLoadingContent = false
                                            }
                                        }
                                    }

                                    Text {
                                        id: markdownRenderArea
                                        visible: window.renderModeActive
                                        text: textEditArea.text
                                        textFormat: canvasContainer.isHtmlActive ? Text.RichText : Text.MarkdownText
                                        color: textMain; font.pixelSize: 14; wrapMode: Text.Wrap; width: parent.width - 20
                                        onLinkActivated: (link) => Qt.openUrlExternally(link)
                                    }
                                }

                                Item {
                                    anchors.fill: parent; visible: canvasContainer.isPdfActive
                                    
                                    PdfDocument { 
                                        id: pdfEngineDoc
                                        source: canvasContainer.isPdfActive ? vesselManager.activeFileUrl : "" 
                                    }
                                    
                                    PdfMultiPageView { 
                                        anchors.fill: parent; anchors.margins: 4; document: pdfEngineDoc; 
                                        visible: canvasContainer.isPdfActive && (pdfEngineDoc.status === PdfDocument.Ready) 
                                    }

                                    Column {
                                        anchors.centerIn: parent; spacing: 15
                                        visible: canvasContainer.isPdfActive && (pdfEngineDoc.status !== PdfDocument.Ready)

                                        Text {
                                            text: pdfEngineDoc.status === PdfDocument.Loading ? "Loading PDF Engine..." : "Built-in PDF Engine Failed to Render"
                                            color: pdfEngineDoc.status === PdfDocument.Loading ? textMain : dangerColor
                                            font.bold: true; font.pixelSize: 15; horizontalAlignment: Text.AlignHCenter
                                        }
                                        Text {
                                            text: "Engine Status Code: " + pdfEngineDoc.status + "\nTarget: " + vesselManager.activeFileUrl
                                            color: textMuted; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter
                                            visible: pdfEngineDoc.status !== PdfDocument.Loading
                                        }
                                        Button {
                                            text: "Open in System PDF Viewer"
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            visible: pdfEngineDoc.status !== PdfDocument.Ready
                                            onClicked: Qt.openUrlExternally(vesselManager.activeFileUrl)
                                            background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitHeight: 32 }
                                            contentItem: Text { text: "Open in System PDF Viewer"; color: textMain; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                        }
                                    }
                                }
                            }

                            // ----------------------------------------------------
                            // GRID CANVAS B: GEMINI CHAT PIPELINE CONSOLE (Tab 0)
                            // ----------------------------------------------------
                            Rectangle {
                                color: bgPanel; border.color: borderDark; radius: 6

                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: 20; spacing: 15

                                    ScrollView {
                                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                        
                                        ListView {
                                            id: chatThreadView; width: parent.width; spacing: 18
                                            model: vesselManager.activeChatHistory
                                            
                                            delegate: RowLayout {
                                                width: chatThreadView.width; spacing: 12
                                                
                                                Rectangle {
                                                    width: 32; height: 32; radius: 16
                                                    color: modelData.sender === "user" ? Qt.darker(bgCard, 1.25) : Qt.darker(accentColor, 1.4)
                                                    Layout.alignment: Qt.AlignTop
                                                    Text { text: modelData.sender === "user" ? "U" : "AI"; color: textMain; font.bold: true; font.pixelSize: 12; anchors.centerIn: parent }
                                                }

                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    Text { text: modelData.sender === "user" ? "You" : "AI"; color: textMuted; font.bold: true; font.pixelSize: 11 }
                                                    Text { text: modelData.text; color: textMain; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.MarkdownText }
                                                }
                                            }

                                            // Auto-scroll to bottom when new messages arrive
                                            onCountChanged: {
                                                var idx = count - 1
                                                if (idx >= 0) {
                                                    currentIndex = idx
                                                    positionViewAtIndex(idx, ListView.End)
                                                }
                                            }
                                        }

                                        // Loading indicator with animated dots + status text
                                        Rectangle {
                                            visible: vesselManager.aiProcessing
                                            anchors.bottom: parent.bottom
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            height: 48
                                            color: "transparent"

                                            RowLayout {
                                                id: dotRow
                                                anchors.left: parent.left; anchors.leftMargin: 28
                                                anchors.verticalCenter: parent.verticalCenter; spacing: 6

                                                Repeater {
                                                    model: 3
                                                    Rectangle {
                                                        width: 8; height: 8; radius: 4
                                                        color: accentColor; opacity: 0.3
                                                        SequentialAnimation on opacity {
                                                            loops: Animation.Infinite
                                                            running: vesselManager.aiProcessing
                                                            PauseAnimation { duration: index * 300 }
                                                            NumberAnimation {
                                                                to: 1.0; duration: 400; easing: Easing.InOutQuad
                                                            }
                                                            NumberAnimation {
                                                                to: 0.3; duration: 400; easing: Easing.InOutQuad
                                                            }
                                                        }
                                                    }
                                                }

                                                Text {
                                                    text: vesselManager.aiStatus
                                                    color: textMuted; font.pixelSize: 11; font.italic: true
                                                    visible: vesselManager.aiStatus !== ""
                                                    leftPadding: 8
                                                }
                                            }
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true; Layout.preferredHeight: 52; color: bgDark; border.color: borderDark; radius: 26 
                                        
                                        RowLayout {
                                            anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 10
                                            
                                            TextField {
                                                id: aiConsoleInputBox; Layout.fillWidth: true; color: textMain; font.pixelSize: 13
                                                placeholderText: "Ask AI about your notes, write scripts, or inspect assets..."
                                                placeholderTextColor: textMuted; background: Rectangle { color: "transparent" }
                                                
                                                onAccepted: {
                                                    if (aiConsoleInputBox.text.trim() !== "") {
                                                        vesselManager.submitUserMessage(aiConsoleInputBox.text, vesselManager.webSearchEnabled)
                                                        aiConsoleInputBox.text = ""
                                                    }
                                                }
                                            }

                                            Switch {
                                                id: webSearchSwitch
                                                checked: vesselManager.webSearchEnabled
                                                onCheckedChanged: vesselManager.webSearchEnabled = checked
                                                ToolTip.visible: hovered
                                                ToolTip.text: checked ? "Web search enabled (DuckDuckGo)" : "Web search disabled"
                                            }

                                            Button {
                                                text: "▶"; font.pixelSize: 14; Layout.preferredWidth: 36; Layout.preferredHeight: 36
                                                enabled: aiConsoleInputBox.text.trim() !== ""
                                                contentItem: Text { text: parent.text; color: textOnAccent; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                                background: Rectangle {
                                                    color: parent.enabled ? accentColor : disabledBg
                                                    radius: 18
                                                    border.color: parent.enabled ? accentColor : "transparent"
                                                    border.width: 1
                                                }
                                                onClicked: {
                                                    vesselManager.submitUserMessage(aiConsoleInputBox.text, vesselManager.webSearchEnabled)
                                                    aiConsoleInputBox.text = ""
                                                }
                                            }
                                        }
                                    } // End Capsule Bar
                                } // End ColumnLayout
                            } // End Chat View Subpanel
                        } // End Master StackLayout
                        Text { text: "Storage Location Node: " + vesselManager.currentVesselPath; color: textMuted; font.pixelSize: 10 }
                    } // End Right Panel Layout Column
                } // End SplitView Layout Workspace Area (Editor Canvas)

                // ==========================================
                // UPCOMING EVENTS / DEADLINES PANEL
                // ==========================================
                Rectangle {
                    id: upcomingPanel
                    width: 220; height: parent.height
                    visible: window.showUpcomingPanel
                    color: bgPanel; border.color: borderDark

                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 12; spacing: 8

                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: "Upcoming"; color: textMain; font.bold: true; font.pixelSize: 13 }
                            Item { Layout.fillWidth: true }
                        Text {
                            text: "✕"; color: textMuted; font.pixelSize: 12
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: window.showUpcomingPanel = false }
                        }

                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: borderDark }

                        Text {
                            text: "Loading..."
                            color: textMuted; font.pixelSize: 11; font.italic: true
                            visible: upcomingEventList.count === 0
                        }

                        ScrollView {
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true

                            ListView {
                                id: upcomingEventList; width: parent.width; spacing: 3
                                model: []

                                delegate: ItemDelegate {
                                    width: parent.width; height: 50; hoverEnabled: true
                                    background: Rectangle { color: parent.hovered ? hoverBg : "transparent"; radius: 4 }

                                    ColumnLayout {
                                        anchors.fill: parent; anchors.margins: 6; spacing: 2

                                        Text {
                                            text: modelData.title
                                            color: {
                                                // Tomorrow → red
                                                var tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1)
                                                var y = tomorrow.getFullYear(), m = ("0"+(tomorrow.getMonth()+1)).slice(-2), d = ("0"+tomorrow.getDate()).slice(-2)
                                                var tomorrowStr = y + "-" + m + "-" + d
                                                modelData.date === tomorrowStr ? dangerColor : textMain
                                            }
                                            font.pixelSize: 12; font.bold: true
                                            elide: Text.ElideRight; Layout.fillWidth: true
                                        }
                                        Text {
                                            text: modelData.date
                                            color: textMuted; font.pixelSize: 10
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Reload when shown or when events change
                    function reload() {
                        var data = vesselManager.getUpcomingEventsJson()
                        upcomingEventList.model = JSON.parse(data || "[]")
                    }

                    onVisibleChanged: { if (visible) reload() }
                }

                Connections {
                    target: vesselManager
                    function onEventsChanged() {
                        if (upcomingPanel.visible) upcomingPanel.reload()
                    }
                }
            } // End WorkspaceView Root Item Component
        } // End WorkspaceComponent Declared ID
    } // End Launcher Screen Component

    // =========================================================================
    // GLOBAL REGISTRATION SYSTEM FILE UTILS
    // =========================================================================
    function cleanUrlToPath(rawUrl) {
        let urlStr = rawUrl.toString();
        let cleanPath = "";
        if (Qt.platform.os === "windows") {
            cleanPath = urlStr.replace("file:///", "").replace(/\//g, "\\");
        } else {
            cleanPath = urlStr.replace("file://", "");
        }
        return decodeURIComponent(cleanPath);
    }

    FileDialog {
        id: fileUploadDialog
        title: "Import Asset File"
        onAccepted: {
            vesselManager.uploadMaterialFile(cleanUrlToPath(fileUploadDialog.selectedFile))
        }
    }

    FolderDialog {
        id: folderPickerDialog
        title: "Select Root Location"
        onAccepted: {
            locationTextField.text = cleanUrlToPath(folderPickerDialog.selectedFolder)
        }
    }

    Popup {
        id: newVesselPopup
        anchors.centerIn: parent
        width: 450; height: 340; modal: true; focus: true
        closePolicy: Popup.CloseOnEscape

        background: Rectangle { color: bgCard; border.color: borderDark; radius: 6 }

        Column {
            anchors.fill: parent; anchors.margins: 25; spacing: 20

            Text { text: "Create a new Vessel"; color: textMain; font.pixelSize: 20; font.bold: true }

            Column {
                width: parent.width; spacing: 6
                Text { text: "Vessel Name"; color: textMuted; font.pixelSize: 12 }
                TextField { id: nameTextField; width: parent.width; placeholderText: "Research Vault"; color: textMain; background: Rectangle { color: bgDark; border.color: borderDark; radius: 4 } }
            }

            Column {
                width: parent.width; spacing: 6
                Text { text: "Location Path"; color: textMuted; font.pixelSize: 12 }
                Row {
                    width: parent.width; spacing: 10
                    TextField { id: locationTextField; width: parent.width - browseBtn.width - 10; placeholderText: "Type path or browse..."; color: textMain; selectByMouse: true; background: Rectangle { color: bgDark; border.color: borderDark; radius: 4 } }
                    Button {
                        id: browseBtn; text: "Browse"
                        onClicked: folderPickerDialog.open()
                                background: Rectangle { color: browseBtn.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitHeight: 30 }
                                contentItem: Text { text: "Browse"; color: textMain; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            }
                        }
                    }

                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter; spacing: 15
                        Button {
                            text: "Cancel"
                            onClicked: newVesselPopup.close()
                            background: Rectangle { color: parent.hovered ? activeBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 80; implicitHeight: 34 }
                    contentItem: Text { text: "Cancel"; color: textMain; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
                Button {
                    text: "Create"
                    enabled: nameTextField.text.trim().length > 0 && locationTextField.text.trim().length > 0
                    onClicked: {
                        let success = vesselManager.createVessel(nameTextField.text, locationTextField.text)
                        if (success) {
                            nameTextField.text = ""
                            locationTextField.text = ""
                            newVesselPopup.close()
                        }
                    }
                    background: Rectangle {
                        color: parent.enabled ? accentColor : disabledBg
                        radius: 6; implicitWidth: 80; implicitHeight: 34
                    }
                    contentItem: Text { text: "Create"; color: parent.enabled ? textOnAccent : textMuted; font.pixelSize: 13; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }
        }
    }

    // =========================================================================
    // CALENDAR POPUP — month grid with event management
    // =========================================================================
    Popup {
        id: calendarPopup
        anchors.centerIn: parent
        width: 540; height: 580; modal: true; focus: true
        closePolicy: Popup.CloseOnEscape

        readonly property var today: new Date()
        property var displayMonth: new Date()
        property var selectedDate: new Date()
        property var allEvents: []

        function fmtDate(d) {
            var y = d.getFullYear()
            var m = ("0" + (d.getMonth()+1)).slice(-2)
            var day = ("0" + d.getDate()).slice(-2)
            return y + "-" + m + "-" + day
        }
        function monthLabel(d) {
            var names = ["January","February","March","April","May","June","July","August","September","October","November","December"]
            return names[d.getMonth()] + " " + d.getFullYear()
        }
        function daysInMonth(d) { return new Date(d.getFullYear(), d.getMonth()+1, 0).getDate() }
        function startDow(d)  { return new Date(d.getFullYear(), d.getMonth(), 1).getDay() }

        property var dayCells: []
        function buildGrid() {
            var cells = []
            var y = displayMonth.getFullYear(), m = displayMonth.getMonth()
            var dim = daysInMonth(displayMonth), sd = startDow(displayMonth)
            var todayStr = fmtDate(new Date()), selStr = fmtDate(selectedDate)
            for (var i = 0; i < 42; i++) {
                var dn = i - sd + 1, valid = dn >= 1 && dn <= dim, dStr = ""
                if (valid) { var dt = new Date(y, m, dn); dStr = fmtDate(dt) }
                var ev = valid ? allEvents.filter(function(e){ return e.date === dStr }) : []
                cells.push({ dayNum: dn, valid: valid, dateStr: dStr,
                    isToday: dStr === todayStr, isSelected: dStr === selStr,
                    hasEvent: ev.length > 0 })
            }
            dayCells = cells
        }

        property var eventsForDate: []
        function updateEventsForDate() {
            var sel = fmtDate(selectedDate)
            eventsForDate = allEvents.filter(function(e){ return e.date === sel })
        }

        function loadEvents() {
            var data = vesselManager.getEventsJson()
            allEvents = JSON.parse(data || "[]")
            buildGrid(); updateEventsForDate()
        }

        function selectDate(year, month, day) {
            selectedDate = new Date(year, month, day)
            buildGrid(); updateEventsForDate()
        }
        function prevMonth() {
            displayMonth = new Date(displayMonth.getFullYear(), displayMonth.getMonth()-1, 1)
            buildGrid()
        }
        function nextMonth() {
            displayMonth = new Date(displayMonth.getFullYear(), displayMonth.getMonth()+1, 1)
            buildGrid()
        }
        function goToday() {
            displayMonth = new Date(); selectedDate = new Date()
            buildGrid(); updateEventsForDate()
        }

        onOpened: loadEvents()

        background: Rectangle { color: bgCard; border.color: borderDark; radius: 8 }

        ColumnLayout {
            anchors.fill: parent; anchors.margins: 20; spacing: 10

            // Header
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Calendar"; color: textMain; font.bold: true; font.pixelSize: 16 }
                Item { Layout.fillWidth: true }
                Button {
                    text: "Today"
                    onClicked: calendarPopup.goToday()
                    ToolTip.visible: hovered; ToolTip.text: "Jump to today"
                    background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitHeight: 26 }
                    contentItem: Text { text: "Today"; color: accentColor; font.pixelSize: 11; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; leftPadding: 8; rightPadding: 8 }
                }
                Button {
                    text: "✕"; font.pixelSize: 14; onClicked: calendarPopup.close()
                    contentItem: Text { text: parent.text; color: textMuted; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { color: "transparent"; implicitWidth: 28; implicitHeight: 28 }
                }
            }

            // Add event form
            RowLayout {
                Layout.fillWidth: true; spacing: 6
                TextField {
                    id: calEventTitle
                    Layout.fillWidth: true
                    placeholderText: "Event title..."
                    color: textMain; font.pixelSize: 12
                    background: Rectangle { color: bgDark; border.color: borderDark; radius: 4; implicitHeight: 28 }
                }
                TextField {
                    id: calEventDate
                    width: 110
                    text: calendarPopup.fmtDate(calendarPopup.selectedDate)
                    color: textMain; font.pixelSize: 12
                    background: Rectangle { color: bgDark; border.color: borderDark; radius: 4; implicitHeight: 28 }
                }
                Button {
                    text: "+"; font.pixelSize: 14
                    onClicked: {
                        if (calEventTitle.text.trim() && calEventDate.text.trim()) {
                            vesselManager.createCalendarEvent(calEventTitle.text, calEventDate.text)
                            calEventTitle.text = ""
                            calendarPopup.loadEvents()
                        }
                    }
                    ToolTip.visible: hovered; ToolTip.text: "Add event"
                    contentItem: Text { text: parent.text; color: textOnAccent; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { color: accentColor; radius: 6; implicitWidth: 30; implicitHeight: 28 }
                }
            }

            // Month navigation
            RowLayout {
                Layout.fillWidth: true; Layout.topMargin: 4
                Button {
                    text: "◀"; font.pixelSize: 14; onClicked: calendarPopup.prevMonth()
                    contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 4; implicitWidth: 28; implicitHeight: 26 }
                }
                Item { Layout.fillWidth: true }
                Text { text: calendarPopup.monthLabel(calendarPopup.displayMonth); color: textMain; font.bold: true; font.pixelSize: 15 }
                Item { Layout.fillWidth: true }
                Button {
                    text: "▶"; font.pixelSize: 14; onClicked: calendarPopup.nextMonth()
                    contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 4; implicitWidth: 28; implicitHeight: 26 }
                }
            }

            // Day-of-week headers
            GridLayout {
                Layout.fillWidth: true; columns: 7; columnSpacing: 2; rowSpacing: 2
                Repeater {
                    model: ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
                    delegate: Text {
                        text: modelData; color: textMuted; font.pixelSize: 10; font.bold: true
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        Layout.fillWidth: true; Layout.preferredHeight: 22
                    }
                }
            }

            // Day grid (42 cells)
            GridLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                columns: 7; columnSpacing: 2; rowSpacing: 2

                Repeater {
                    model: calendarPopup.dayCells

                    delegate: Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Layout.preferredHeight: 40
                        visible: modelData.valid
                        radius: 6
                        color: modelData.isSelected ? accentColor
                             : modelData.isToday ? buttonHoverBg
                             : "transparent"
                        border.color: modelData.isToday && !modelData.isSelected ? accentColor : "transparent"
                        border.width: modelData.isToday && !modelData.isSelected ? 1 : 0

                        MouseArea {
                            anchors.fill: parent
                            onClicked: calendarPopup.selectDate(calendarPopup.displayMonth.getFullYear(), calendarPopup.displayMonth.getMonth(), modelData.dayNum)
                            cursorShape: Qt.PointingHandCursor
                        }

                        ColumnLayout {
                            anchors.fill: parent; spacing: 2
                            Text {
                                text: modelData.dayNum
                                color: modelData.isSelected ? textOnAccent : textMain
                                font.pixelSize: 12; font.bold: modelData.isToday
                                horizontalAlignment: Text.AlignHCenter
                                Layout.fillWidth: true; Layout.topMargin: 3
                            }
                            Rectangle {
                                width: 4; height: 4; radius: 2; color: accentColor
                                visible: modelData.hasEvent
                                Layout.alignment: Qt.AlignHCenter
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }
            }

            // Events for selected date
            Rectangle { Layout.fillWidth: true; height: 1; color: borderDark }

            Text {
                text: "Events on " + calendarPopup.fmtDate(calendarPopup.selectedDate)
                color: textMuted; font.bold: true; font.pixelSize: 11
            }

            ScrollView {
                Layout.fillWidth: true; Layout.preferredHeight: 80; clip: true

                ListView {
                    id: calEventList; width: parent.width; spacing: 4
                    model: calendarPopup.eventsForDate

                    Text {
                        text: "No events on this date"
                        color: textMuted; font.pixelSize: 11; font.italic: true
                        visible: parent.count === 0; anchors.centerIn: parent
                    }

                    delegate: ItemDelegate {
                        width: parent.width; height: 34; hoverEnabled: true
                        background: Rectangle { color: parent.hovered ? activeBg : "transparent"; radius: 4 }
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 4; spacing: 8
                            Rectangle { width: 3; height: 20; radius: 2; color: accentColor }
                            Text {
                                text: modelData.title
                                color: textMain; font.pixelSize: 11
                                elide: Text.ElideRight; Layout.fillWidth: true
                            }
                            Button {
                                text: "✕"; font.pixelSize: 14; width: 18; height: 18
onClicked: {
                                        vesselManager.deleteCalendarEvent(modelData.id)
                                        calendarPopup.loadEvents()
                                    }
                                    contentItem: Text { text: parent.text; color: textMuted; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                    background: Rectangle { color: "transparent"; radius: 2 }
                            }
                        }
                    }
                }
            }
        }
    }

    function openCalendar() {
        calendarPopup.loadEvents()
        calendarPopup.open()
    }

    // =========================================================================
    // SETTINGS MODAL — provider selection & API key management
    // =========================================================================
    Popup {
        id: settingsPopup
        anchors.centerIn: parent
        width: 480; height: 640; modal: true; focus: true
        closePolicy: Popup.CloseOnEscape

        background: Rectangle { color: bgCard; border.color: borderDark; radius: 8 }

        property var providerKeys: ["ollama", "google", "openai", "anthropic"]

        function syncFromManager() {
            var p = vesselManager.providerName
            for (var i = 0; i < settingsPopup.providerKeys.length; i++) {
                if (settingsPopup.providerKeys[i] === p) {
                    providerCombo.currentIndex = i
                    break
                }
            }
            ollamaModelField.text = vesselManager.ollamaModel
            geminiKeyField.text = vesselManager.googleApiKey
            chatgptKeyField.text = vesselManager.openaiApiKey
            claudeKeyField.text = vesselManager.anthropicApiKey
        }

        function syncThemeFields() {
            themeBgDarkField.text = vesselManager.themeBgDark
            themeBgCardField.text = vesselManager.themeBgCard
            themeBgPanelField.text = vesselManager.themeBgPanel
            themeBorderField.text = vesselManager.themeBorderColor
            themeTextPrimaryField.text = vesselManager.themeTextPrimary
            themeTextSecondaryField.text = vesselManager.themeTextSecondary
            themeAccentField.text = vesselManager.themeAccent
            themeDangerField.text = vesselManager.themeDanger
        }

        function saveSettings() {
            var idx = providerCombo.currentIndex
            var provider = settingsPopup.providerKeys[idx]
            vesselManager.setProviderName(provider)
            vesselManager.setOllamaModel(ollamaModelField.text.trim() || "tinyllama:1.1b")
            vesselManager.setGoogleApiKey(geminiKeyField.text)
            vesselManager.setOpenaiApiKey(chatgptKeyField.text)
            vesselManager.setAnthropicApiKey(claudeKeyField.text)
            settingsPopup.close()
        }

        function resetThemeDefaults() {
            vesselManager.setThemeColor("bgDark", "#141414")
            vesselManager.setThemeColor("bgCard", "#1e1e1e")
            vesselManager.setThemeColor("bgPanel", "#181818")
            vesselManager.setThemeColor("borderColor", "#2a2a2a")
            vesselManager.setThemeColor("textPrimary", "#ffffff")
            vesselManager.setThemeColor("textSecondary", "#7a7a7a")
            vesselManager.setThemeColor("accent", "#bb86fc")
            vesselManager.setThemeColor("danger", "#ff5555")
            syncThemeFields()
        }

        onOpened: {
            syncFromManager()
            syncThemeFields()
        }

        Column {
            anchors.fill: parent; anchors.margins: 25; spacing: 18

            Text { text: "Settings"; color: textMain; font.pixelSize: 20; font.bold: true }
            Text { text: "Configure AI provider and API credentials."; color: textMuted; font.pixelSize: 12 }

            Rectangle { width: parent.width; height: 1; color: borderDark }

            // Provider selector
            Column { width: parent.width; spacing: 6
                Text { text: "AI Provider"; color: textMuted; font.pixelSize: 12; font.bold: true }
                ComboBox {
                    id: providerCombo
                    width: parent.width; height: 36
                    model: ["Local Ollama", "Gemini (Google)", "ChatGPT (OpenAI)", "Claude (Anthropic)"]
                    currentIndex: 0

                    background: Rectangle { color: bgDark; border.color: borderDark; radius: 6; implicitHeight: 36 }
                    contentItem: Text { text: providerCombo.displayText; color: textMain; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; leftPadding: 10 }
                    indicator: Text { text: "▼"; color: textMuted; font.pixelSize: 10; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter }
                }
            }

            // ── Ollama: model name ──
            Column { width: parent.width; spacing: 6
                visible: providerCombo.currentIndex === 0
                Text { text: "Model Name"; color: textMuted; font.pixelSize: 12; font.bold: true }
                TextField {
                    id: ollamaModelField
                    width: parent.width; height: 36
                    placeholderText: "tinyllama:1.1b"
                    color: textMain; font.pixelSize: 13
                    leftPadding: 10
                    background: Rectangle { color: bgDark; border.color: borderDark; radius: 6 }
                }
                Text { text: "Requires Ollama installed and 'ollama serve' running."; color: textMuted; font.pixelSize: 10; wrapMode: Text.WordWrap }
            }

            // ── Gemini: API key ──
            Column { width: parent.width; spacing: 6
                visible: providerCombo.currentIndex === 1
                Text { text: "Gemini API Key"; color: textMuted; font.pixelSize: 12; font.bold: true }
                Row { width: parent.width; spacing: 8
                    TextField {
                        id: geminiKeyField
                        width: parent.width - toggleGeminiBtn.width - 8; height: 36
                        placeholderText: "Enter your Google AI API key"
                        color: textMain; font.pixelSize: 13; leftPadding: 10
                        echoMode: TextInput.Password
                        background: Rectangle { color: bgDark; border.color: borderDark; radius: 6 }
                    }
                    Button {
                        id: toggleGeminiBtn
                        text: geminiKeyField.echoMode === TextInput.Password ? "◉" : "◯"; font.pixelSize: 14
                        width: 36; height: 36
                        onClicked: geminiKeyField.echoMode = geminiKeyField.echoMode === TextInput.Password ? TextInput.Normal : TextInput.Password
                        contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { color: toggleGeminiBtn.hovered ? activeBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1 }
                    }
                }
            }

            // ── ChatGPT: API key ──
            Column { width: parent.width; spacing: 6
                visible: providerCombo.currentIndex === 2
                Text { text: "OpenAI API Key"; color: textMuted; font.pixelSize: 12; font.bold: true }
                Row { width: parent.width; spacing: 8
                    TextField {
                        id: chatgptKeyField
                        width: parent.width - toggleGptBtn.width - 8; height: 36
                        placeholderText: "sk-..."
                        color: textMain; font.pixelSize: 13; leftPadding: 10
                        echoMode: TextInput.Password
                        background: Rectangle { color: bgDark; border.color: borderDark; radius: 6 }
                    }
                    Button {
                        id: toggleGptBtn
                        text: chatgptKeyField.echoMode === TextInput.Password ? "◉" : "◯"; font.pixelSize: 14
                        width: 36; height: 36
                        onClicked: chatgptKeyField.echoMode = chatgptKeyField.echoMode === TextInput.Password ? TextInput.Normal : TextInput.Password
                        contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { color: toggleGptBtn.hovered ? activeBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1 }
                    }
                }
            }

            // ── Claude: API key ──
            Column { width: parent.width; spacing: 6
                visible: providerCombo.currentIndex === 3
                Text { text: "Anthropic API Key"; color: textMuted; font.pixelSize: 12; font.bold: true }
                Row { width: parent.width; spacing: 8
                    TextField {
                        id: claudeKeyField
                        width: parent.width - toggleClaudeBtn.width - 8; height: 36
                        placeholderText: "sk-ant-..."
                        color: textMain; font.pixelSize: 13; leftPadding: 10
                        echoMode: TextInput.Password
                        background: Rectangle { color: bgDark; border.color: borderDark; radius: 6 }
                    }
                    Button {
                        id: toggleClaudeBtn
                        text: claudeKeyField.echoMode === TextInput.Password ? "◉" : "◯"; font.pixelSize: 14
                        width: 36; height: 36
                        onClicked: claudeKeyField.echoMode = claudeKeyField.echoMode === TextInput.Password ? TextInput.Normal : TextInput.Password
                        contentItem: Text { text: parent.text; color: textMain; font.pixelSize: parent.font.pixelSize; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { color: toggleClaudeBtn.hovered ? activeBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1 }
                    }
                }
            }

            // ── Theme Colors ──
            Rectangle { width: parent.width; height: 1; color: borderDark }

            Text { text: "Theme Colors"; color: textMain; font.pixelSize: 16; font.bold: true; Layout.topMargin: 4 }

            Column { width: parent.width; spacing: 5

                Row { width: parent.width; spacing: 8
                    Text { text: "Bg Dark"; color: textMuted; font.pixelSize: 12; width: 100; anchors.verticalCenter: parent.verticalCenter }
                    TextField {
                        id: themeBgDarkField; text: "#141414"; width: parent.width - 130; height: 26
                        color: textMain; font.pixelSize: 12; leftPadding: 6; placeholderText: "#RRGGBB"
                        validator: RegularExpressionValidator {
                            regularExpression: /^#[0-9a-fA-F]{6}$/
                        }
                        background: Rectangle {
                            color: bgDark; border.color: borderDark; radius: 4
                        }
                        onTextEdited: {
                            if (text.length === 7 && text[0] === "#")
                                vesselManager.setThemeColor("bgDark", text)
                        }
                    }
                    Rectangle { width: 20; height: 20; radius: 3; border.color: borderDark; border.width: 1; color: themeBgDarkField.text }
                }
                Row { width: parent.width; spacing: 8
                    Text { text: "Bg Card"; color: textMuted; font.pixelSize: 12; width: 100; anchors.verticalCenter: parent.verticalCenter }
                    TextField {
                        id: themeBgCardField; text: "#1e1e1e"; width: parent.width - 130; height: 26
                        color: textMain; font.pixelSize: 12; leftPadding: 6; placeholderText: "#RRGGBB"
                        validator: RegularExpressionValidator {
                            regularExpression: /^#[0-9a-fA-F]{6}$/
                        }
                        background: Rectangle {
                            color: bgDark; border.color: borderDark; radius: 4
                        }
                        onTextEdited: {
                            if (text.length === 7 && text[0] === "#")
                                vesselManager.setThemeColor("bgCard", text)
                        }
                    }
                    Rectangle { width: 20; height: 20; radius: 3; border.color: borderDark; border.width: 1; color: themeBgCardField.text }
                }
                Row { width: parent.width; spacing: 8
                    Text { text: "Bg Panel"; color: textMuted; font.pixelSize: 12; width: 100; anchors.verticalCenter: parent.verticalCenter }
                    TextField {
                        id: themeBgPanelField; text: "#181818"; width: parent.width - 130; height: 26
                        color: textMain; font.pixelSize: 12; leftPadding: 6; placeholderText: "#RRGGBB"
                        validator: RegularExpressionValidator {
                            regularExpression: /^#[0-9a-fA-F]{6}$/
                        }
                        background: Rectangle {
                            color: bgDark; border.color: borderDark; radius: 4
                        }
                        onTextEdited: {
                            if (text.length === 7 && text[0] === "#")
                                vesselManager.setThemeColor("bgPanel", text)
                        }
                    }
                    Rectangle { width: 20; height: 20; radius: 3; border.color: borderDark; border.width: 1; color: themeBgPanelField.text }
                }
                Row { width: parent.width; spacing: 8
                    Text { text: "Border"; color: textMuted; font.pixelSize: 12; width: 100; anchors.verticalCenter: parent.verticalCenter }
                    TextField {
                        id: themeBorderField; text: "#2a2a2a"; width: parent.width - 130; height: 26
                        color: textMain; font.pixelSize: 12; leftPadding: 6; placeholderText: "#RRGGBB"
                        validator: RegularExpressionValidator {
                            regularExpression: /^#[0-9a-fA-F]{6}$/
                        }
                        background: Rectangle {
                            color: bgDark; border.color: borderDark; radius: 4
                        }
                        onTextEdited: {
                            if (text.length === 7 && text[0] === "#")
                                vesselManager.setThemeColor("borderColor", text)
                        }
                    }
                    Rectangle { width: 20; height: 20; radius: 3; border.color: borderDark; border.width: 1; color: themeBorderField.text }
                }
                Row { width: parent.width; spacing: 8
                    Text { text: "Text Primary"; color: textMuted; font.pixelSize: 12; width: 100; anchors.verticalCenter: parent.verticalCenter }
                    TextField {
                        id: themeTextPrimaryField; text: "#ffffff"; width: parent.width - 130; height: 26
                        color: textMain; font.pixelSize: 12; leftPadding: 6; placeholderText: "#RRGGBB"
                        validator: RegularExpressionValidator {
                            regularExpression: /^#[0-9a-fA-F]{6}$/
                        }
                        background: Rectangle {
                            color: bgDark; border.color: borderDark; radius: 4
                        }
                        onTextEdited: {
                            if (text.length === 7 && text[0] === "#")
                                vesselManager.setThemeColor("textPrimary", text)
                        }
                    }
                    Rectangle { width: 20; height: 20; radius: 3; border.color: borderDark; border.width: 1; color: themeTextPrimaryField.text }
                }
                Row { width: parent.width; spacing: 8
                    Text { text: "Text Secondary"; color: textMuted; font.pixelSize: 12; width: 100; anchors.verticalCenter: parent.verticalCenter }
                    TextField {
                        id: themeTextSecondaryField; text: "#7a7a7a"; width: parent.width - 130; height: 26
                        color: textMain; font.pixelSize: 12; leftPadding: 6; placeholderText: "#RRGGBB"
                        validator: RegularExpressionValidator {
                            regularExpression: /^#[0-9a-fA-F]{6}$/
                        }
                        background: Rectangle {
                            color: bgDark; border.color: borderDark; radius: 4
                        }
                        onTextEdited: {
                            if (text.length === 7 && text[0] === "#")
                                vesselManager.setThemeColor("textSecondary", text)
                        }
                    }
                    Rectangle { width: 20; height: 20; radius: 3; border.color: borderDark; border.width: 1; color: themeTextSecondaryField.text }
                }
                Row { width: parent.width; spacing: 8
                    Text { text: "Accent"; color: textMuted; font.pixelSize: 12; width: 100; anchors.verticalCenter: parent.verticalCenter }
                    TextField {
                        id: themeAccentField; text: "#bb86fc"; width: parent.width - 130; height: 26
                        color: textMain; font.pixelSize: 12; leftPadding: 6; placeholderText: "#RRGGBB"
                        validator: RegularExpressionValidator {
                            regularExpression: /^#[0-9a-fA-F]{6}$/
                        }
                        background: Rectangle {
                            color: bgDark; border.color: borderDark; radius: 4
                        }
                        onTextEdited: {
                            if (text.length === 7 && text[0] === "#")
                                vesselManager.setThemeColor("accent", text)
                        }
                    }
                    Rectangle { width: 20; height: 20; radius: 3; border.color: borderDark; border.width: 1; color: themeAccentField.text }
                }
                Row { width: parent.width; spacing: 8
                    Text { text: "Danger"; color: textMuted; font.pixelSize: 12; width: 100; anchors.verticalCenter: parent.verticalCenter }
                    TextField {
                        id: themeDangerField; text: "#ff5555"; width: parent.width - 130; height: 26
                        color: textMain; font.pixelSize: 12; leftPadding: 6; placeholderText: "#RRGGBB"
                        validator: RegularExpressionValidator {
                            regularExpression: /^#[0-9a-fA-F]{6}$/
                        }
                        background: Rectangle {
                            color: bgDark; border.color: borderDark; radius: 4
                        }
                        onTextEdited: {
                            if (text.length === 7 && text[0] === "#")
                                vesselManager.setThemeColor("danger", text)
                        }
                    }
                    Rectangle { width: 20; height: 20; radius: 3; border.color: borderDark; border.width: 1; color: themeDangerField.text }
                }
            }

            Row {
                Button {
                    text: "Reset to Defaults"
                    onClicked: settingsPopup.resetThemeDefaults()
                    background: Rectangle { color: parent.hovered ? buttonHoverBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 120; implicitHeight: 28 }
                    contentItem: Text { text: "Reset to Defaults"; color: textMain; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }

            Item { Layout.fillHeight: true }

            // Action buttons
            Row {
                anchors.horizontalCenter: parent.horizontalCenter; spacing: 15
                Button {
                    text: "Cancel"
                    onClicked: settingsPopup.close()
                    background: Rectangle { color: parent.hovered ? activeBg : "transparent"; radius: 6; border.color: borderDark; border.width: 1; implicitWidth: 80; implicitHeight: 34 }
                    contentItem: Text { text: "Cancel"; color: textMain; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
                Button {
                    text: "Save"
                    onClicked: settingsPopup.saveSettings()
                    background: Rectangle { color: accentColor; radius: 6; implicitWidth: 80; implicitHeight: 34 }
                    contentItem: Text { text: "Save"; color: textOnAccent; font.pixelSize: 13; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }
        }
    }
}
