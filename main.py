import sys
import os
import json
import shutil
import uuid
import datetime
import urllib.parse
import threading
from pathlib import Path
from PySide6.QtCore import QObject, Slot, Signal, Property, QUrl
from PySide6.QtGui import QGuiApplication, QDesktopServices
from PySide6.QtQml import QQmlApplicationEngine

from modules import updateEmbeds, answerTo, initVessel, bm25_search, tag_search


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
PROVIDER_CONFIG_FILE = get_storage_directory() / "provider_config.json"


def _default_provider_config() -> dict:
    return {
        "provider": "ollama",
        "ollama_model": "tinyllama:1.1b",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "anthropic_api_key": "",
        "anthropic_model": "claude-3-haiku-20240307",
        "google_api_key": "",
        "google_model": "gemini-2.0-flash",
    }


def _load_provider_config() -> dict:
    cfg = _default_provider_config()
    if PROVIDER_CONFIG_FILE.exists():
        try:
            data = json.loads(PROVIDER_CONFIG_FILE.read_text(encoding="utf-8"))
            cfg.update(data)
        except Exception:
            pass
    return cfg


def _save_provider_config(cfg: dict):
    PROVIDER_CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


class VesselManager(QObject):
    vesselsChanged = Signal()
    currentVesselChanged = Signal()
    materialsChanged = Signal()
    dropletsChanged = Signal()
    activeContentChanged = Signal()
    conversationsChanged = Signal()
    chatHistoryChanged = Signal()
    webSearchEnabledChanged = Signal()
    aiProcessingChanged = Signal()
    aiResponseReceived = Signal(str)  # emitted from worker thread with final answer
    providerConfigChanged = Signal()

    def __init__(self):
        super().__init__()
        self._vessels = []
        self._current_vessel_name = ""
        self._current_vessel_path = ""      # also used as the chat namespace
        self._materials_files = []
        self._droplets_tree = []
        self._active_file_text = ""
        self._active_file_name = ""
        self._active_file_path = ""
        self._web_search_enabled = False

        # Chat persistence — loaded from disk
        self._conversations: list[dict] = []   # [{id, title, created_at, updated_at}, …]
        self._active_chat_id = ""
        self._active_chat_history: list[dict] = []   # [{sender, text}, …]

        # Provider configuration (persisted)
        self._provider_config = _load_provider_config()

        # Processing state for loading indicator
        self._ai_processing = False

        # Connect response signal to main thread handler
        self.aiResponseReceived.connect(self._on_ai_response)

        self.load_history()

    # ------------------------------------------------------------------
    # Chat persistence helpers
    # ------------------------------------------------------------------
    def _chats_dir(self) -> Path | None:
        if not self._current_vessel_path:
            return None
        d = Path(self._current_vessel_path) / "AI" / ".sys" / "chats"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _conv_path(self, conv_id: str) -> Path | None:
        base = self._chats_dir()
        if base is None:
            return None
        return base / f"{conv_id}.json"

    def _load_conversations_from_disk(self):
        """Scan the chats directory and rebuild the conversation list (latest first)."""
        base = self._chats_dir()
        if base is None:
            self._conversations = []
            self.conversationsChanged.emit()
            return
        convs = []
        if base.exists():
            for f in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if f.suffix == ".json":
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        convs.append({
                            "id": data.get("id", f.stem),
                            "title": data.get("title", "Untitled"),
                            "created_at": data.get("created_at", ""),
                            "updated_at": data.get("updated_at", ""),
                        })
                    except Exception:
                        pass
        self._conversations = convs
        self.conversationsChanged.emit()

    def _load_chat_history(self, conv_id: str) -> list[dict]:
        """Load all messages for a conversation from its JSON file."""
        path = self._conv_path(conv_id)
        if path is None or not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("messages", [])
        except Exception:
            return []

    def _save_message(self, conv_id: str, sender: str, text: str):
        """Append a message to a conversation file, creating it if needed."""
        path = self._conv_path(conv_id)
        now = _now_iso()
        if path is None:
            return

        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {
                "id": conv_id,
                "title": "New Chat",
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }

        data["messages"].append({
            "sender": sender,
            "text": text,
            "created_at": now,
        })
        data["updated_at"] = now

        # Auto-title: use the first user message as the title
        if data["title"] == "New Chat" and sender == "user":
            title = text.strip()[:60]
            if len(text.strip()) > 60:
                title += "…"
            data["title"] = title

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Refresh the conversation list so the new title shows up
        self._load_conversations_from_disk()

    def _create_conversation(self) -> str:
        """Create a blank conversation file and return its id."""
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        path = self._conv_path(conv_id)
        if path is None:
            return ""
        now = _now_iso()
        data = {
            "id": conv_id,
            "title": "New Chat",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self._load_conversations_from_disk()
        return conv_id

    # ------------------------------------------------------------------
    # Vessel load/save for the vessel registry
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Core Global Properties
    # ------------------------------------------------------------------
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

    @Property(bool, notify=webSearchEnabledChanged)
    def webSearchEnabled(self): return self._web_search_enabled

    @webSearchEnabled.setter
    def webSearchEnabled(self, enabled):
        if self._web_search_enabled != enabled:
            self._web_search_enabled = enabled
            self.webSearchEnabledChanged.emit()

    # ------------------------------------------------------------------
    # Provider configuration properties
    # ------------------------------------------------------------------
    @Property(str, notify=providerConfigChanged)
    def providerName(self):
        return self._provider_config.get("provider", "ollama")

    @Property(str, notify=providerConfigChanged)
    def ollamaModel(self):
        return self._provider_config.get("ollama_model", "tinyllama:1.1b")

    @Property(str, notify=providerConfigChanged)
    def openaiApiKey(self):
        return self._provider_config.get("openai_api_key", "")

    @Property(str, notify=providerConfigChanged)
    def anthropicApiKey(self):
        return self._provider_config.get("anthropic_api_key", "")

    @Property(str, notify=providerConfigChanged)
    def googleApiKey(self):
        return self._provider_config.get("google_api_key", "")

    @Slot(str)
    def setProviderName(self, name):
        if self._provider_config.get("provider") != name:
            self._provider_config["provider"] = name
            _save_provider_config(self._provider_config)
            self.providerConfigChanged.emit()

    @Slot(str)
    def setOllamaModel(self, model):
        if self._provider_config.get("ollama_model") != model:
            self._provider_config["ollama_model"] = model
            _save_provider_config(self._provider_config)
            self.providerConfigChanged.emit()

    @Slot(str)
    def setOpenaiApiKey(self, key):
        self._provider_config["openai_api_key"] = key
        _save_provider_config(self._provider_config)
        self.providerConfigChanged.emit()

    @Slot(str)
    def setAnthropicApiKey(self, key):
        self._provider_config["anthropic_api_key"] = key
        _save_provider_config(self._provider_config)
        self.providerConfigChanged.emit()

    @Slot(str)
    def setGoogleApiKey(self, key):
        self._provider_config["google_api_key"] = key
        _save_provider_config(self._provider_config)
        self.providerConfigChanged.emit()

    @Property(bool, notify=aiProcessingChanged)
    def aiProcessing(self):
        return self._ai_processing

    # ------------------------------------------------------------------
    # Chat properties & slots
    # ------------------------------------------------------------------
    @Property(list, notify=conversationsChanged)
    def aiConversations(self): return self._conversations

    @Property(list, notify=chatHistoryChanged)
    def activeChatHistory(self): return self._active_chat_history

    @Property(str, notify=chatHistoryChanged)
    def activeChatId(self): return self._active_chat_id

    @Slot()
    def newConversation(self):
        """Create a new empty conversation and switch to it."""
        conv_id = self._create_conversation()
        if conv_id:
            self._active_chat_id = conv_id
            self._active_chat_history = []
            self.chatHistoryChanged.emit()

    @Slot(str)
    def selectConversation(self, chat_id):
        """Load a conversation and display its history."""
        self._active_chat_id = chat_id
        self._active_chat_history = self._load_chat_history(chat_id)
        self.chatHistoryChanged.emit()

    @Slot(str, bool)
    def submitUserMessage(self, message, web_search_enabled=False):
        """Send a message, save it, get an AI response in a background thread."""
        if not message.strip():
            return

        # Auto-create a conversation if none is active
        if not self._active_chat_id:
            conv_id = self._create_conversation()
            if not conv_id:
                return
            self._active_chat_id = conv_id
            self._active_chat_history = []

        msg_text = message.strip()
        vessel_path = self._current_vessel_path
        provider_config = dict(self._provider_config)

        # Save user message immediately
        self._save_message(self._active_chat_id, "user", msg_text)
        self._active_chat_history.append({"sender": "user", "text": msg_text})
        self.chatHistoryChanged.emit()

        # Show loading state
        self._ai_processing = True
        self.aiProcessingChanged.emit()

        # Extract previous messages for conversational context
        # Exclude the current user message — it's already embedded in the prompt
        chat_history = list(self._active_chat_history[:-1])

        # Spawn background thread so the UI stays responsive
        thread = threading.Thread(
            target=self._process_ai_response,
            args=(vessel_path, msg_text, web_search_enabled, chat_history, provider_config),
            daemon=True,
        )
        thread.start()

    def _process_ai_response(self, vessel_path, msg_text, web_search_enabled, chat_history, provider_config):
        """Run answerTo in a background thread, emit result on main thread."""
        try:
            if vessel_path:
                ai_response = answerTo(
                    vessel_path, msg_text, web_search_enabled,
                    chat_history=chat_history,
                    provider_config=provider_config,
                )
            else:
                ai_response = "*No vessel is currently open. Please create or open a vessel first.*"

            if not ai_response:
                ai_response = "✦ *AI Core error: Empty inference buffer returned from background pipeline host.*"
        except Exception as e:
            ai_response = f"⚠️ *Failed to communicate with local RAG execution thread:* \n\n```\n{str(e)}\n ```"

        # Emit signal — the handler runs on the main thread via Qt's signal-slot mechanism
        self.aiResponseReceived.emit(ai_response)

    def _on_ai_response(self, ai_response):
        """Handle the AI response on the main thread (connected via signal)."""
        self._ai_processing = False
        self.aiProcessingChanged.emit()

        self._save_message(self._active_chat_id, "model", ai_response)
        self._active_chat_history.append({"sender": "model", "text": ai_response})
        self.chatHistoryChanged.emit()

    @Property(QUrl, notify=activeContentChanged)
    def activeFileUrl(self):
        if not self._active_file_path:
            return QUrl()
        return QUrl.fromLocalFile(self._active_file_path)

    # ------------------------------------------------------------------
    # Disk Infrastructure Routines
    # ------------------------------------------------------------------
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

            _ = (vessel_dir / "Droplets" / "Welcome.md").write_text(
                "# Welcome to your Vessel\nThis note is a **Droplet**! You can write *Markdown* text here.",
                encoding="utf-8",
            )

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
            # Load chats for this vessel
            self._load_conversations_from_disk()
            if self._conversations:
                self.selectConversation(self._conversations[0]["id"])
            else:
                self.newConversation()

    @Slot(str)
    def deleteVessel(self, path_to_remove):
        target_dir = Path(path_to_remove)
        if target_dir.exists() and target_dir.is_dir():
            try:
                shutil.rmtree(target_dir)
            except Exception:
                pass
        self._vessels = [v for v in self._vessels if v["path"] != path_to_remove]
        self.save_history()
        self.vesselsChanged.emit()

    def refresh_files(self):
        target = Path(self._current_vessel_path)
        try:
            self._materials_files = [
                f.name
                for f in os.scandir(target / "Materials")
                if not f.name.startswith(".")
            ]
            self.materialsChanged.emit()
        except Exception:
            self._materials_files = []

        try:
            self._droplets_tree = self._build_tree(target / "Droplets")
            self.dropletsChanged.emit()
        except Exception:
            self._droplets_tree = []

    def _build_tree(self, root_path: Path):
        items = []
        if not root_path.exists():
            return items

        entries = sorted(
            list(os.scandir(root_path)),
            key=lambda e: (e.is_file(), e.name.lower()),
        )

        for entry in entries:
            if entry.name.startswith("."):
                continue

            relative_to_droplets = os.path.relpath(
                entry.path, Path(self._current_vessel_path) / "Droplets"
            )
            depth = (
                0
                if relative_to_droplets == "."
                else len(Path(relative_to_droplets).parts) - 1
            )

            relative_to_vessel = os.path.relpath(entry.path, self._current_vessel_path)

            if entry.is_dir():
                items.append({
                    "name": entry.name,
                    "isFile": False,
                    "relPath": relative_to_vessel,
                    "absPath": entry.path,
                    "depth": depth,
                })
                items.extend(self._build_tree(Path(entry.path)))
            else:
                items.append({
                    "name": entry.name,
                    "isFile": True,
                    "relPath": relative_to_vessel,
                    "absPath": entry.path,
                    "depth": depth,
                })
        return items

    # ------------------------------------------------------------------
    # Droplet Workspace Control Slots
    # ------------------------------------------------------------------
    @Slot(str)
    def loadDropletContent(self, abs_path):
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
        if abs_path:
            try:
                Path(abs_path).write_text(text, encoding="utf-8")
                self._active_file_text = text
            except Exception:
                pass

    @Slot(str, bool)
    def createNewAsset(self, parent_rel_path, is_folder):
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
        old_path = Path(abs_path)
        if not old_path.exists() or not new_name.strip():
            return False

        validated_name = new_name.strip()

        if old_path.is_file():
            allowed_extensions = (".md", ".html", ".txt")
            if not any(
                validated_name.lower().endswith(ext) for ext in allowed_extensions
            ):
                validated_name += ".md"

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
        success = True

        if success:
            try:
                from modules import bm25_search as _
                from pathlib import Path as _P
                import sqlite3

                db_file = (
                    _P(self._current_vessel_path) / "AI" / ".sys" / "vessel_rag.db"
                )
                if db_file.exists():
                    conn = sqlite3.connect(str(db_file))
                    conn.execute("PRAGMA foreign_keys = ON;")
                    conn.execute(
                        "UPDATE documents SET title = ? WHERE title = ?",
                        (new_path.name, old_path.name),
                    )
                    conn.commit()
                    conn.close()
                    print(
                        f"📝 Updated document title: {old_path.name} → {new_path.name}"
                    )
            except Exception as e:
                print(f"Info: Could not update document title on rename ({e})")
        return success

    @Slot(str)
    def handleMaterialClick(self, filename):
        target_path = Path(self._current_vessel_path) / "Materials" / filename
        if not target_path.exists():
            return

        ext = filename.lower()

        if ext.endswith(".pdf"):
            self._active_file_name = filename
            self._active_file_path = str(target_path.resolve())
            self._active_file_text = ""
            self.activeContentChanged.emit()

        elif ext.endswith((".html", ".md", ".txt", ".csv", ".json")):
            try:
                self._active_file_text = target_path.read_text(encoding="utf-8")
                self._active_file_name = filename
                self._active_file_path = str(target_path.resolve())
                self.activeContentChanged.emit()
            except Exception as e:
                print(f"Python Error reading material text: {e}")

        else:
            file_url = QUrl.fromLocalFile(str(target_path.resolve()))
            QDesktopServices.openUrl(file_url)

    @Slot(str)
    def autoSaveDroplet(self, text):
        if self._active_file_path:
            try:
                with open(self._active_file_path, "w", encoding="utf-8") as f:
                    f.write(text)
                self._active_file_text = text
            except Exception as e:
                print(f"Python Error during auto-save: {e}")

    @Slot(str)
    def removeAsset(self, abs_path):
        p = Path(abs_path)
        if p.exists():
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()

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
            clean_path = (
                clean_path.replace("file:///", "")
                if os.name == "nt"
                else clean_path.replace("file://", "")
            )
            if os.name == "nt":
                clean_path = clean_path.replace("/", "\\")
        source = Path(clean_path)
        if not source.exists():
            return False
        try:
            dest = Path(self._current_vessel_path) / "Materials" / source.name
            shutil.copy2(source, dest)
            try:
                updateEmbeds(str(dest.resolve()))
                print("Vector Index: Successfully synchronized embeddings for new asset upload.")
            except Exception as e:
                print(f"Backend Error running updateEmbeds on upload: {e}")
            self.refresh_files()
            return True
        except Exception:
            return False

    @Slot()
    def closeWorkspace(self):
        self._current_vessel_name = ""
        self._current_vessel_path = ""
        self._materials_files = []
        self._droplets_tree = []
        self._active_file_text = ""
        self._active_file_name = ""
        self._active_file_path = ""
        self._conversations = []
        self._active_chat_id = ""
        self._active_chat_history = []
        self.currentVesselChanged.emit()
        self.activeContentChanged.emit()
        self.conversationsChanged.emit()
        self.chatHistoryChanged.emit()

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
                    
