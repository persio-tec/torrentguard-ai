import json
from pathlib import Path

APP_NAME = "TorrentGuard AI"
CONFIG_DIR = Path.home() / ".config" / "torrentguard-ai"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
DOWNLOADS_DIR = Path.home() / "Downloads" / "TorrentGuard"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT = {
    "general": {"download_dir": str(DOWNLOADS_DIR), "start_paused": True, "ask_before_start": True},
    "security": {"enable_pre_scan": True, "use_opencode_ai": True},
    "opencode": {"model": "big-pickle", "enabled": True},
    "ui": {"theme": "dark"}
}

class Config:
    def __init__(self):
        self.data = self.load()
    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE,'r',encoding='utf-8') as f:
                    d=json.load(f)
                c=json.loads(json.dumps(DEFAULT))
                def m(a,b):
                    for k,v in b.items():
                        if isinstance(v,dict) and k in a and isinstance(a[k],dict): m(a[k],v)
                        else: a[k]=v
                m(c,d); return c
            except (OSError, json.JSONDecodeError): return json.loads(json.dumps(DEFAULT))
        self.save(DEFAULT); return json.loads(json.dumps(DEFAULT))
    def save(self,c=None):
        if c is None: c=self.data
        with open(CONFIG_FILE,'w',encoding='utf-8') as f: json.dump(c,f,indent=4,ensure_ascii=False)
        return True

    def get(self, section, key, default=None):
        """Le um valor do arquivo de configuracao."""
        try:
            return self.data.get(section, {}).get(key, default)
        except Exception:
            return default

cfg = Config()
