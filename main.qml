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

    readonly property color bgDark: "#141414"
    readonly property color bgCard: "#1e1e1e"
    readonly property color bgPanel: "#181818"
    readonly property color borderDark: "#2a2a2a"
    readonly property color textMain: "#ffffff"
    readonly property color textMuted: "#7a7a7a"
    readonly property color accentColor: "#bb86fc"

    // App state tracking parameter
    property bool renderModeActive: false
    property string renamingAbsPath: ""

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

                background: Rectangle { color: bgCard; border.color: borderDark; radius: 6 }
                
                Column {
                    spacing: 12; width: 300
                    Text { text: "⚠️ PERMANENT DISK WIPE?"; color: "#ff5555"; font.bold: true; font.pixelSize: 15 }
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
                    Button { id: createBtn; text: "+ New Vessel"; onClicked: newVesselPopup.open() }
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
                                Button { id: openVesselBtn; text: "Open Vessel"; onClicked: vesselManager.openVessel(modelData.path) }
                                Button { id: deleteVesselBtn; text: "❌"; width: 35; onClicked: { deleteConfirmationDialog.vesselPathToDelete = modelData.path; deleteConfirmationDialog.vesselNameToDelete = modelData.name; deleteConfirmationDialog.open() } }
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

                background: Rectangle { color: bgCard; border.color: borderDark; radius: 6 }

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
                MenuItem { text: "📁 New Folder"; onClicked: vesselManager.createNewAsset("", true) }
                MenuItem { text: "📝 New Droplet"; onClicked: vesselManager.createNewAsset("", false) }
            }

            Menu {
                id: itemContextMenu
                property string targetedPath: ""
                property string targetedRelPath: ""
                property string targetedName: ""
                property bool targetIsDir: false

                MenuItem { text: "📝 New Droplet Here"; visible: itemContextMenu.targetIsDir; onClicked: vesselManager.createNewAsset(itemContextMenu.targetedRelPath, false) }
                MenuItem { text: "📁 New Folder Here"; visible: itemContextMenu.targetIsDir; onClicked: vesselManager.createNewAsset(itemContextMenu.targetedRelPath, true) }
                
                MenuItem { 
                    text: "✏️ Rename Asset"
                    onClicked: {
                        renameModalDialog.targetAbsPath = itemContextMenu.targetedPath
                        renameInputBox.text = itemContextMenu.targetedName
                        renameModalDialog.open()
                    }
                }

                MenuItem { text: "🗑️ Delete Asset"; onClicked: vesselManager.removeAsset(itemContextMenu.targetedPath) }
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
                            Text { text: "🛸 " + vesselManager.currentVesselName; color: textMain; font.pixelSize: 15; font.bold: true; elide: Text.ElideRight; width: 180; anchors.verticalCenter: parent.verticalCenter }
                            Button { id: closeWorkspaceBtn; text: "Exit"; onClicked: vesselManager.closeWorkspace() }
                        }

                        TabBar {
                            id: sidebarTabBar; Layout.fillWidth: true; Layout.preferredHeight: 40; currentIndex: 2
                            background: Rectangle { color: "transparent" }
                            TabButton { id: t1; width: 85; height: 40; contentItem: Text { text: "🤖"; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: sidebarTabBar.currentIndex === 0 ? accentColor : textMuted } }
                            TabButton { id: t2; width: 85; height: 40; contentItem: Text { text: "📦"; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: sidebarTabBar.currentIndex === 1 ? accentColor : textMuted } }
                            TabButton { id: t3; width: 85; height: 40; contentItem: Text { text: "💧"; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: sidebarTabBar.currentIndex === 2 ? accentColor : textMuted } }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: borderDark }

                        StackLayout {
                            id: sidebarStackLayout
                            Layout.fillWidth: true; Layout.fillHeight: true; currentIndex: sidebarTabBar.currentIndex

                            // [Index 0]: AI Subsystem Gemini-Style Sidebar Menu
                            Item {
                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 14

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "✦ Gemini Workspace Core"; color: textMain; font.bold: true; font.pixelSize: 13 }
                                        Item { Layout.fillWidth: true }
                                        Button { text: "New 💬"; onClicked: vesselManager.selectConversation("") }
                                    }

                                    Text { text: "Recent Chats"; color: textMuted; font.pixelSize: 11; font.bold: true; Layout.topMargin: 5 }
                                    ScrollView {
                                        Layout.fillWidth: true; Layout.preferredHeight: parent.height * 0.35; clip: true
                                        ListView {
                                            id: recentChatsList; width: parent.width; spacing: 2
                                            model: vesselManager.aiConversations
                                            delegate: ItemDelegate {
                                                width: recentChatsList.width; height: 28
                                                background: Rectangle { color: (vesselManager.activeChatId === modelData.id) ? "#2a2a2a" : (hovered ? "#222222" : "transparent"); radius: 4 }
                                                contentItem: Text { text: "💬  " + modelData.title; color: textMain; font.pixelSize: 12; elide: Text.ElideRight }
                                                onClicked: vesselManager.selectConversation(modelData.id)
                                            }
                                        }
                                    }

                                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: borderDark }

                                    Text { text: "Generated Code & Droplets"; color: textMuted; font.pixelSize: 11; font.bold: true }
                                    ScrollView {
                                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                        ListView {
                                            id: generatedFilesList; width: parent.width; spacing: 2
                                            model: vesselManager.aiGeneratedFiles
                                            delegate: ItemDelegate {
                                                width: generatedFilesList.width; height: 28
                                                background: Rectangle { color: hovered ? "#222222" : "transparent"; radius: 4 }
                                                contentItem: Text { text: "✨  " + modelData.name; color: "#a87ffb"; font.pixelSize: 12; elide: Text.ElideRight }
                                                onClicked: print("Clicked artifact row map target: " + modelData.name)
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
                                        Button { text: "+ Upload"; onClicked: fileUploadDialog.open() }
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
                                                contentItem: Text { text: "📦 " + modelData; color: textMain; font.pixelSize: 12; elide: Text.ElideMiddle }
                                                background: Rectangle { color: hovered ? "#222222" : "transparent"; radius: 4 }
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
                                        Button { text: "+ 📄"; onClicked: vesselManager.createNewAsset("", false) }
                                        Button { text: "+ 📁"; onClicked: vesselManager.createNewAsset("", true) }
                                    }

                                    ScrollView {
                                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                        ListView {
                                            id: dropletsListView; width: parent.width; spacing: 2
                                            model: vesselManager.dropletsTree
                                            
                                            delegate: ItemDelegate {
                                                id: dropletDelegate
                                                width: dropletsListView.width; height: 30
                                                background: Rectangle { color: hovered ? "#222222" : "transparent"; radius: 4 }
                                                
                                                contentItem: Text {
                                                    text: (modelData.isFile ? "📄  " : "📁  ") + modelData.name
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
                    width: parent.width - fileSidebar.width; height: parent.height; color: bgDark

                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 25; spacing: 15

                        // Editor Utility Toolbar
                        RowLayout {
                            Layout.fillWidth: true; Layout.preferredHeight: 35
                            
                            Rectangle {
                                width: 220; height: 32; color: bgPanel; radius: 4; border.color: borderDark
                                Text { 
                                    text: sidebarTabBar.currentIndex === 0 ? "🤖 Gemini Agent Shell Console" : (vesselManager.activeFileName ? vesselManager.activeFileName : "No File Open")
                                    color: textMain; anchors.centerIn: parent; font.pixelSize: 12; font.bold: true; elide: Text.ElideMiddle; width: parent.width - 20 
                                }
                            }
                            Item { Layout.fillWidth: true }

                            Button {
                                action: toggleRenderAction
                                text: window.renderModeActive ? "✏️ Edit Source" : "👁️ View Rendered"
                                visible: sidebarTabBar.currentIndex === 0 ? false : !canvasContainer.isPdfActive
                                
                                ToolTip.visible: hovered
                                ToolTip.text: "Toggle Render Mode (Ctrl + M)"
                                ToolTip.delay: 400
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
                                            text: pdfEngineDoc.status === PdfDocument.Loading ? "⏳ Loading PDF Engine..." : "⚠️ Built-in PDF Engine Failed to Render"
                                            color: pdfEngineDoc.status === PdfDocument.Loading ? textMain : "#ff5555"
                                            font.bold: true; font.pixelSize: 15; horizontalAlignment: Text.AlignHCenter
                                        }
                                        Text {
                                            text: "Engine Status Code: " + pdfEngineDoc.status + "\nTarget: " + vesselManager.activeFileUrl
                                            color: textMuted; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter
                                            visible: pdfEngineDoc.status !== PdfDocument.Loading
                                        }
                                        Button {
                                            text: "↗️ Open in System PDF Viewer"
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            visible: pdfEngineDoc.status !== PdfDocument.Loading
                                            onClicked: Qt.openUrlExternally(vesselManager.activeFileUrl)
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
                                                    color: modelData.sender === "user" ? "#303030" : "#4b2b7a"
                                                    Layout.alignment: Qt.AlignTop
                                                    Text { text: modelData.sender === "user" ? "U" : "✦"; color: textMain; font.bold: true; font.pixelSize: 12; anchors.centerIn: parent }
                                                }

                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    Text { text: modelData.sender === "user" ? "You" : "Gemini Core"; color: textMuted; font.bold: true; font.pixelSize: 11 }
                                                    Text { text: modelData.text; color: textMain; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.MarkdownText }
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
                                                placeholderText: "Ask Gemini anything about your notes, write scripts, or inspect assets..."
                                                placeholderTextColor: textMuted; background: Rectangle { color: "transparent" }
                                                
                                                onAccepted: {
                                                    if (aiConsoleInputBox.text.trim() !== "") {
                                                        vesselManager.submitUserMessage(aiConsoleInputBox.text)
                                                        aiConsoleInputBox.text = ""
                                                    }
                                                }
                                            }

                                            Button {
                                                text: "➔"; Layout.preferredWidth: 36; Layout.preferredHeight: 36
                                                enabled: aiConsoleInputBox.text.trim() !== ""
                                                background: Rectangle { color: parent.enabled ? accentColor : "#252525"; radius: 18 }
                                                onClicked: {
                                                    vesselManager.submitUserMessage(aiConsoleInputBox.text)
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
                } // End SplitView Layout Workspace Area
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
                    Button { id: browseBtn; text: "Browse"; onClicked: folderPickerDialog.open() }
                }
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter; spacing: 15
                Button { text: "Cancel"; onClicked: newVesselPopup.close() }
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
                }
            }
        }
    }
}
