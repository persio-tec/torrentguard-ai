"""Sessao do libtorrent usada pelo TorrentGuard AI."""

import os
import shutil

import libtorrent as lt

from core.lt_compat import list_files, torrent_info_of


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
        #: pasta de download de cada torrent (para apagar os arquivos)
        self.paths = {}

    # ------------------------------------------------------------------
    def add_magnet(self, magnet, save_path, paused=True):
        params = lt.parse_magnet_uri(magnet)
        params.save_path = save_path
        h = self.ses.add_torrent(params)
        if paused:
            h.pause()
        ih = str(h.info_hash())
        self.torrents[ih] = h
        self.paths[ih] = save_path
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
        self.paths[ih] = save_path
        return ih, h, info

    # ------------------------------------------------------------------
    def resume(self, ih):
        h = self.torrents.get(ih)
        if h:
            h.resume()
            return True
        return False

    def pause(self, ih):
        h = self.torrents.get(ih)
        if h:
            h.pause()
            return True
        return False

    def remove(self, ih, delete_files=False):
        """Remove o torrent da sessao (opcionalmente apagando os arquivos)."""
        h = self.torrents.get(ih)
        if not h:
            return False
        if delete_files:
            self.delete_data(ih)
        try:
            self.ses.remove_torrent(h)
        except Exception:
            try:
                self.ses.remove_torrent(ih)
            except Exception:
                pass
        self.torrents.pop(ih, None)
        self.paths.pop(ih, None)
        return True

    # ------------------------------------------------------------------
    def delete_data(self, ih):
        """Apaga os arquivos baixados do torrent. Devolve a lista apagada."""
        removed = []
        h = self.torrents.get(ih)
        if h is None:
            return removed
        info = torrent_info_of(h)
        if info is None:
            return removed
        base = self.paths.get(ih) or ""
        base_real = os.path.realpath(base) if base else None
        for path, _size in list_files(info):
            # evita path traversal em nomes de arquivo maliciosos
            if os.path.isabs(path) or ".." in path.split(os.sep):
                continue
            full = os.path.join(base, path) if base else path
            if base_real is not None:
                try:
                    if os.path.commonpath([base_real, os.path.realpath(full)]) != base_real:
                        continue
                except (ValueError, OSError):
                    continue
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
                    removed.append(full)
                elif os.path.isfile(full):
                    os.remove(full)
                    removed.append(full)
            except OSError:
                continue
        # remove as pastas que ficaram vazias
        if base:
            self._prune_empty_dirs(base)
        return removed

    @staticmethod
    def _prune_empty_dirs(base, keep_base=True):
        try:
            for root, dirs, files in os.walk(base, topdown=False):
                if not dirs and not files and root != base:
                    os.rmdir(root)
        except OSError:
            pass
