import os
import json
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet
from core.config import CONFIG_DIR

KEY_FILE = CONFIG_DIR / "security.key"
VAULT_FILE = CONFIG_DIR / "vault.enc"
VIRUS_DB = CONFIG_DIR / "virus_db.json"

class SecurityManager:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.key = self._load_key()
        self.fernet = Fernet(self.key)
        self._init_virus_db()

    def _load_key(self):
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes()
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        os.chmod(KEY_FILE, 0o600)
        return key

    def encrypt(self, data: str) -> str:
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, data: str) -> str:
        return self.fernet.decrypt(data.encode()).decode()

    def sha256(self, path):
        h = hashlib.sha256()
        try:
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except:
            return None

    def _init_virus_db(self):
        if VIRUS_DB.exists(): return
        db = {
            "signatures": [
                {"hash": "e99a18c428cb38d5f260853678922e03", "name": "Teste-Signature"},
            ],
            "names": ["crack.exe","keygen.exe","patch.exe","loader.exe","activator.exe"],
            "ext_block": [".exe",".msi",".bat",".cmd",".ps1",".vbs",".scr"]
        }
        VIRUS_DB.write_text(json.dumps(db, indent=2), encoding='utf-8')

    def scan_file(self, path):
        db = json.loads(VIRUS_DB.read_text()) if VIRUS_DB.exists() else {"signatures":[],"names":[]}
        res = {"safe": True, "hits": []}
        try:
            name = os.path.basename(path).lower()
            if name in [x.lower() for x in db.get("names",[])]:
                res["safe"] = False
                res["hits"].append(f"Nome suspeito: {name}")
            h = self.sha256(path)
            for s in db.get("signatures",[]):
                if s.get("hash") == h:
                    res["safe"] = False
                    res["hits"].append(f"Assinatura conhecida: {s.get('name')}")
        except Exception as e:
            res["hits"].append(str(e))
        return res
