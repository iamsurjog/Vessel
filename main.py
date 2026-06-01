from mimetypes import init
import sys
import os
import json
import shutil
import urllib.parse
from pathlib import Path
from PySide6.QtCore import QObject, Slot, Signal, Property, QUrl
from PySide6.QtGui import QGuiApplication, QDesktopServices
from PySide6.QtQml import QQmlApplicationEngine

from modules import updateEmbeds, answerTo, initVessel

def get_storage_directory() -> Path:
    home = Path.home()
    if os.name == "nt":
        appdata = os.environ.get("LOCALAPPDATA")
        base_dir = Path(appdata) if appdata else home / "AppData" / "Local"
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base_dir = Path(xdg_config) if xdg_config else home / ".config"
    config_dir = base_dir / "vessel"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir

STORAGE_FILE = get_storage_directory() / "vessels_history.json"

class VesselManager(QObject):
    vesselsChanged = Signal()
    currentVesselChanged = Signal()
    materialsChanged = Signal()
    dropletsChanged = Signal()
    activeContentChanged = Signal()

    def __init__(self):
        super().__init__()
        self._vessels = []
        self._current_vessel_name = ""
        self._current_vessel_path = ""
        self._materials_files = []
        self._droplets_tree = []
        self._active_file_text = ""
        self._active_file_name = ""
        self._active_file_path = ""
        self.load_history()
        # TODO: DELETE THESE
        self._ai_conversations = [
            {"id": "c1", "title": "Data Indexing Optimization"},
            {"id": "c2", "title": "RAG Pipeline Debugging"},
            {"id": "c3", "title": "Arch Config Shell Script"}
        ]
        self._ai_generated_files = [
            {"name": "index_vessel.py", "type": "Python"},
            {"name": "summary_notes.md", "type": "Markdown"},
            {"name": "schema_v2.json", "type": "JSON"}
        ]
        self._active_chat_history = [
            {"sender": "user", "text": "Can you review my vector retrieval loop?"},
            {"sender": "model", "text": "I can help with that! For optimal RAG lookups, make sure you scale your embeddings and use a normalized dot-product distance index rather than brute-force cosine distance."}
        ]
        self._active_chat_id = "c1"

    def load_history(self):
        if STORAGE_FILE.exists():
            try:
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    self._vessels = json.load(f)
            except Exception:
                self._vessels = []

    def save_history(self):
        try:
            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._vessels, f, indent=4)
        except Exception:
            pass

    # Core Global Properties
    @Property(list, notify=vesselsChanged)
    def vesselsList(self): return self._vessels

    @Property(str, notify=currentVesselChanged)
    def currentVesselName(self): return self._current_vessel_name

    @Property(str, notify=currentVesselChanged)
    def currentVesselPath(self): return self._current_vessel_path

    @Property(list, notify=materialsChanged)
    def materialsFiles(self): return self._materials_files

    @Property(list, notify=dropletsChanged)
    def dropletsTree(self): return self._droplets_tree

    @Property(str, notify=activeContentChanged)
    def activeFileText(self): return self._active_file_text

    @Property(str, notify=activeContentChanged)
    def activeFileName(self): return self._active_file_name

    @Property(str, notify=activeContentChanged)
    def activeFilePath(self): return self._active_file_path


    aiConversationsChanged = Signal()
    aiGeneratedFilesChanged = Signal()
    activeChatChanged = Signal()

    @Property(list, notify=aiConversationsChanged)
    def aiConversations(self): return self._ai_conversations

    @Property(list, notify=aiGeneratedFilesChanged)
    def aiGeneratedFiles(self): return self._ai_generated_files

    @Property(list, notify=activeChatChanged)
    def activeChatHistory(self): return self._active_chat_history

    @Property(str, notify=activeChatChanged)
    def activeChatId(self): return self._active_chat_id

    @Slot(str)
    def selectConversation(self, chat_id):
        """Switches the current conversation context view."""
        self._active_chat_id = chat_id
        # Mock switching content based on target selection
        if chat_id == "c1":
            self._active_chat_history = [
                {"sender": "user", "text": "Can you review my vector retrieval loop?"},
                {"sender": "model", "text": "I can help with that! For optimal RAG lookups, make sure you scale your embeddings and use a normalized dot-product distance index rather than brute-force cosine distance."}
            ]
        elif chat_id == "c2":
            self._active_chat_history = [
                {"sender": "user", "text": "Why is my RAG getting context hallucinations?"},
                {"sender": "model", "text": "Usually, that means your chunk size is too narrow or your top-k retrieval is pulling irrelevant documents. Try adding a reranking step."}
            ]
        else:
            self._active_chat_history = []
        self.activeChatChanged.emit()

    @Slot(str)
    @Slot(str)
    def submitUserMessage(self, message):
        """Appends user input and streams live backend calculations to the workspace timeline."""
        if not message.strip(): 
            return
            
        # A. Append your message directly to the visual timeline grid array map
        self._active_chat_history.append({"sender": "user", "text": message.strip()})
        self.activeChatChanged.emit()
        
        # B. Route directly to your LLM endpoint passing the active contextual channel identity key
        try:
            # Passes current conversation identity string parameter (e.g., "c1")
            ai_response = answerTo(self._active_chat_id, message.strip())
            
            # Fallback error guard check if backend module outputs a null response block
            if not ai_response:
                ai_response = "✦ *Gemini Core error: Empty inference buffer returned from background pipeline host.*"
        except Exception as e:
            ai_response = f"⚠️ *Failed to communicate with local RAG execution thread:* \n\n```\n{str(e)}\n ```"

        # C. Stream the processing results straight back to your QML interface canvas frame
        self._active_chat_history.append({"sender": "model", "text": ai_response})
        self.activeChatChanged.emit()

    @Property(QUrl, notify=activeContentChanged)
    def activeFileUrl(self): 
        if not self._active_file_path: 
            return QUrl() # Returns an empty valid URL object
        # Sends a native Qt URL directly to the QML engine
        return QUrl.fromLocalFile(self._active_file_path)

    # --- Disk Infrastructure Routines ---
    @Slot(str, str, result=bool)
    def createVessel(self, name: str, target_path: str):
        base_dir = Path(target_path.strip())
        vessel_dir = base_dir / name.strip()
        absolute_path = str(vessel_dir.resolve())
        try:
            (vessel_dir / "Droplets").mkdir(parents=True, exist_ok=True)
            (vessel_dir / "Materials").mkdir(parents=True, exist_ok=True)
            (vessel_dir / "AI").mkdir(parents=True, exist_ok=True)
            (vessel_dir / ".vessel").mkdir(parents=True, exist_ok=True)
            _ = initVessel(vessel_dir)

            
            _ = (vessel_dir / "Droplets" / "Welcome.md").write_text("# Welcome to your Vessel\nThis note is a **Droplet**! You can write *Markdown* text here.", encoding="utf-8")
            
            entry = {"name": name.strip(), "path": absolute_path}
            if entry not in self._vessels:
                self._vessels.append(entry)
                self.save_history()
                self.vesselsChanged.emit()
            self.openVessel(absolute_path)
            return True
        except Exception:
            return False

    @Slot(str)
    def openVessel(self, path):
        target = Path(path)
        if target.exists():
            self._current_vessel_path = str(target.resolve())
            self._current_vessel_name = target.name
            self.refresh_files()
            self.currentVesselChanged.emit()

    @Slot(str)
    def deleteVessel(self, path_to_remove):
        target_dir = Path(path_to_remove)
        if target_dir.exists() and target_dir.is_dir():
            try: shutil.rmtree(target_dir)
            except Exception: pass
        self._vessels = [v for v in self._vessels if v["path"] != path_to_remove]
        self.save_history()
        self.vesselsChanged.emit()

    def refresh_files(self):
        target = Path(self._current_vessel_path)
        # Materials Scanning
        try:
            self._materials_files = [f.name for f in os.scandir(target / "Materials") if not f.name.startswith('.')]
            self.materialsChanged.emit()
        except Exception:
            self._materials_files = []

        # Droplets Recursive Scan
        try:
            self._droplets_tree = self._build_tree(target / "Droplets")
            self.dropletsChanged.emit()
        except Exception:
            self._droplets_tree = []

    def _build_tree(self, root_path: Path):
        """Recursively builds a layout map of folders and Droplets with nesting depths."""
        items = []
        if not root_path.exists(): return items
        
        # Sort so folders appear above files, alphabetically
        entries = sorted(list(os.scandir(root_path)), key=lambda e: (e.is_file(), e.name.lower()))
        
        for entry in entries:
            if entry.name.startswith('.'): continue
            
            # Calculate the nesting depth by counting path separators
            relative_to_droplets = os.path.relpath(entry.path, Path(self._current_vessel_path) / "Droplets")
            # If at the root of Droplets, depth is 0. If inside a folder, depth is 1, etc.
            depth = 0 if relative_to_droplets == "." else len(Path(relative_to_droplets).parts) - 1
            
            relative_to_vessel = os.path.relpath(entry.path, self._current_vessel_path)
            
            if entry.is_dir():
                items.append({
                    "name": entry.name,
                    "isFile": False,
                    "relPath": relative_to_vessel,
                    "absPath": entry.path,
                    "depth": depth  # <-- PASS DEPTH TO QML
                })
                # Recursively add subdirectories
                items.extend(self._build_tree(Path(entry.path)))
            else:
                items.append({
                    "name": entry.name,
                    "isFile": True,
                    "relPath": relative_to_vessel,
                    "absPath": entry.path,
                    "depth": depth  # <-- PASS DEPTH TO QML
                })
        return items

    # --- Droplet Workspace Control Slots ---
    @Slot(str)
    def loadDropletContent(self, abs_path):
        """Reads note file text data into memory."""
        p = Path(abs_path)
        if p.exists() and p.is_file():
            try:
                self._active_file_text = p.read_text(encoding="utf-8")
                self._active_file_name = p.name
                self._active_file_path = str(p.resolve())
                self.activeContentChanged.emit()
            except Exception:
                pass

    @Slot(str, str)
    def saveActiveDroplet(self, abs_path, text):
        """Saves current string updates live back down to storage."""
        if abs_path:
            try:
                Path(abs_path).write_text(text, encoding="utf-8")
                self._active_file_text = text
            except Exception:
                pass

    @Slot(str, bool)
    def createNewAsset(self, parent_rel_path, is_folder):
        """Creates an asset inside the Droplets tree subdirectories."""
        base_vessel = Path(self._current_vessel_path)
        
        if parent_rel_path == "" or parent_rel_path == "Droplets":
            target_parent = base_vessel / "Droplets"
        else:
            anchor = base_vessel / parent_rel_path
            target_parent = anchor if anchor.is_dir() else anchor.parent

        if is_folder:
            new_path = target_parent / "New_Folder"
            count = 1
            while new_path.exists():
                new_path = target_parent / f"New_Folder_{count}"
                count += 1
            new_path.mkdir(exist_ok=True)
        else:
            new_path = target_parent / "Untitled.md"
            count = 1
            while new_path.exists():
                new_path = target_parent / f"Untitled_{count}.md"
                count += 1
            new_path.write_text("# Untitled\n", encoding="utf-8")
            
        self.refresh_files()

    @Slot(str, str, result=bool)
    @Slot(str, str, result=bool)
    def renameAsset(self, abs_path, new_name):
        """Renames a file or directory on disk."""
        old_path = Path(abs_path)
        if not old_path.exists() or not new_name.strip():
            return False
            
        validated_name = new_name.strip()
        
        # --- NEW: Allow HTML and TXT formats ---
        if old_path.is_file():
            allowed_extensions = ('.md', '.html', '.txt')
            if not any(validated_name.lower().endswith(ext) for ext in allowed_extensions):
                validated_name += '.md'

        new_path = old_path.parent / validated_name
        
        if new_path.exists() and new_path != old_path:
            return False
        try:
            old_path.rename(new_path)
            if str(old_path.resolve()) == self._active_file_path:
                self._active_file_name = new_path.name
                self._active_file_path = str(new_path.resolve())
                self.activeContentChanged.emit()
            self.refresh_files()
            success = True
        except Exception:
            success = False
        success = True # representation of your internal operation flag
        
        if success:
            try:
                updateEmbeds()
                print("Vector Index: Regenerated layout map hashes after asset renaming.")
            except Exception as e:
                print(f"Backend Error running updateEmbeds on rename: {e}")
        return success

    @Slot(str)
    def handleMaterialClick(self, filename):
        """Smart router: handles PDFs, Text/HTML inside the app, pushes others to OS."""
        target_path = Path(self._current_vessel_path) / "Materials" / filename
        if not target_path.exists(): return
        
        ext = filename.lower()
        
        # 1. Handle PDFs internally
        if ext.endswith('.pdf'):
            self._active_file_name = filename
            self._active_file_path = str(target_path.resolve())
            self._active_file_text = "" 
            self.activeContentChanged.emit()
            
        # 2. Handle HTML, Markdown, and Text internally
        elif ext.endswith(('.html', '.md', '.txt', '.csv', '.json')):
            try:
                self._active_file_text = target_path.read_text(encoding="utf-8")
                self._active_file_name = filename
                self._active_file_path = str(target_path.resolve())
                self.activeContentChanged.emit()
            except Exception as e:
                print(f"Python Error reading material text: {e}")
                
        # 3. Fallback: Open Word, PPT, Images, etc., in the OS default apps
        else:
            file_url = QUrl.fromLocalFile(str(target_path.resolve()))
            QDesktopServices.openUrl(file_url)

    @Slot(str)
    def autoSaveDroplet(self, text):
        """Saves current string text modifications instantly to disk as the user types."""
        # Only attempt to write if there is a file actively loaded in the viewport
        if self._active_file_path:
            try:
                with open(self._active_file_path, "w", encoding="utf-8") as f:
                    f.write(text)
                # Keep our inner data copy matched up with the visual text canvas
                self._active_file_text = text
            except Exception as e:
                print(f"Python Error during auto-save: {e}")

    @Slot(str)
    def removeAsset(self, abs_path):
        """Deletes a folder or file completely from the local workspace."""
        p = Path(abs_path)
        if p.exists():
            try:
                if p.is_dir(): shutil.rmtree(p)
                else: p.unlink()
                
                # Reset viewport state if active file was dropped
                if str(p.resolve()) == self._active_file_path:
                    self._active_file_text = ""
                    self._active_file_name = ""
                    self._active_file_path = ""
                    self.activeContentChanged.emit()
                    
                self.refresh_files()
            except Exception:
                pass

    @Slot(str, result=bool)
    def uploadMaterialFile(self, raw_source_path):
        clean_path = raw_source_path.strip()
        clean_path = urllib.parse.unquote(clean_path)
        if clean_path.startswith("file://"):
            clean_path = clean_path.replace("file:///", "") if os.name == "nt" else clean_path.replace("file://", "")
            if os.name == "nt": clean_path = clean_path.replace("/", "\\")
        source = Path(clean_path)
        if not source.exists(): return False
        try:
            shutil.copy2(source, Path(self._current_vessel_path) / "Materials" / source.name)
            try:
                updateEmbeds()
                print("Vector Index: Successfully synchronized embeddings for new asset upload.")
            except Exception as e:
                print(f"Backend Error running updateEmbeds on upload: {e}")
            self.refresh_files()
            return True
        except Exception: return False
            

    @Slot()
    def closeWorkspace(self):
        self._current_vessel_name = ""
        self._current_vessel_path = ""
        self._materials_files = []
        self._droplets_tree = []
        self._active_file_text = ""
        self._active_file_name = ""
        self._active_file_path = ""
        self.currentVesselChanged.emit()
        self.activeContentChanged.emit()

if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    
    vessel_manager = VesselManager()
    engine.rootContext().setContextProperty("vesselManager", vessel_manager)
    engine.load(Path(__file__).parent / "main.qml")
    
    # Check if the QML engine loaded the file successfully before executing
    if not engine.rootObjects():
        sys.exit(-1)

    try:
        # Start the Qt event loop
        exit_code = app.exec()
        sys.exit(exit_code)
        
    except Exception as e:
        print(f"🔥 Critical Application Crash Intercepted: {e}")
        sys.exit(1)
        
    finally:
        # ----------------------------------------------------
        # THE SAFE EXCLUSION CLEANUP PASS
        # ----------------------------------------------------
        # This code block is GUARANTEED to execute on window close or crash!
        print("\n🔒 Shutting down Vessel Engine safely... Executing single-pass batch save.")
        
        if vessel_manager._active_file_path and vessel_manager._active_file_text:
            # Save the text data left in memory
            with open(vessel_manager._active_file_path, "w", encoding="utf-8") as f:
                f.write(vessel_manager._active_file_text)
            print(f"💾 Successfully saved uncommitted modifications to: {vessel_manager._active_file_name}")
            updateEmbeds()
            # Update embeddings exactly once before termination
                    
