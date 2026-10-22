import libtorrent as lt

class TorrentEngine:
    def __init__(self):
        self.ses = lt.session()
        try:
            if hasattr(self.ses, 'listen_on'):
                self.ses.listen_on(6881, 6891)
            elif hasattr(self.ses, 'start_lsd'):
                pass
        except Exception:
            pass
        self.torrents = {}

    def add_magnet(self, magnet, save_path, paused=True):
        params = lt.parse_magnet_uri(magnet)
        params.save_path = save_path
        h = self.ses.add_torrent(params)
        if paused:
            h.pause()
        ih = str(h.info_hash())
        self.torrents[ih] = h
        return ih, h

    def add_torrent_file(self, torrent_path, save_path, paused=True):
        info = lt.torrent_info(torrent_path)
        params = lt.add_torrent_params()
        params.ti = info
        params.save_path = save_path
        h = self.ses.add_torrent(params)
        if paused:
            h.pause()
        ih = str(h.info_hash())
        self.torrents[ih] = h
        return ih, h, info

    def resume(self, ih):
        h = self.torrents.get(ih)
        if h: h.resume(); return True
        return False

    def pause(self, ih):
        h = self.torrents.get(ih)
        if h: h.pause(); return True
        return False

    def remove(self, ih):
        h = self.torrents.get(ih)
        if h: 
            self.ses.remove_torrent(h)
            self.torrents.pop(ih,None)
            return True
        return False
