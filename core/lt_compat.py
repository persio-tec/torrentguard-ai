"""Camada de compatibilidade entre as APIs do libtorrent 1.x e 2.x.

O libtorrent 2.x removeu varios metodos usados pelo app:

============  ==================================  ==========================
API antiga    libtorrent 1.x                       libtorrent 2.x
============  ==================================  ==========================
metadados     ``handle.has_metadata()``            ``handle.status().has_metadata``
info hash     ``handle.get_torrent_info()``        ``handle.torrent_file()``
nome          ``handle.name()``                    ``handle.status().name``
arquivos      ``info.file_at(i)``                  ``info.files().file_path(i)``
============  ==================================  ==========================

Como o app precisa funcionar nas duas versoes, toda a traducao fica
centralizada aqui.
"""

import warnings

__all__ = ["has_metadata", "torrent_info_of", "torrent_name", "list_files"]


def has_metadata(handle):
    """True quando o torrent ja tem os metadados (lista de arquivos)."""
    if handle is None:
        return False
    getter = getattr(handle, "has_metadata", None)
    if callable(getter):
        try:
            return bool(getter())
        except Exception:
            return False
    try:
        return bool(handle.status().has_metadata)
    except Exception:
        return False


def torrent_info_of(handle):
    """Devolve o ``torrent_info`` do handle (None se ainda nao houver)."""
    if handle is None:
        return None
    for name in ("get_torrent_info", "torrent_file"):
        getter = getattr(handle, name, None)
        if not callable(getter):
            continue
        try:
            info = getter()
        except Exception:
            info = None
        if info is not None:
            return info
    return None


def torrent_name(handle, info=None):
    """Nome do torrent (cai para o hash quando ainda nao ha metadados)."""
    if info is None:
        info = torrent_info_of(handle)
    if info is not None:
        try:
            name = info.name()
            if name:
                return name
        except Exception:
            pass
    try:
        name = getattr(handle.status(), "name", "")
        if name:
            return name
    except Exception:
        pass
    try:
        return str(handle.info_hash())
    except Exception:
        return "(sem nome)"


def list_files(info):
    """Lista de ``(caminho, tamanho)`` dos arquivos do torrent."""
    files = []
    if info is None:
        return files

    # libtorrent 1.x: torrent_info.file_at(i)
    file_at = getattr(info, "file_at", None)
    if callable(file_at):
        try:
            for i in range(info.num_files()):
                entry = file_at(i)
                files.append((entry.path, entry.size))
            return files
        except Exception:
            files = []

    # libtorrent 2.x: torrent_info.files() -> file_storage
    storage = _file_storage(info)
    if storage is not None:
        try:
            total = storage.num_files()
        except Exception:
            total = 0
        for i in range(total):
            try:
                files.append((storage.file_path(i), storage.file_size(i)))
            except Exception:
                continue
        return files

    return files


def _file_storage(info):
    """Obtem o ``file_storage`` do ``torrent_info`` em qualquer versao."""
    files_attr = getattr(info, "files", None)
    if files_attr is None:
        return None
    if callable(files_attr):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                return files_attr()
            except Exception:
                return None
    # libtorrent 1.x: ja e um file_storage
    if hasattr(files_attr, "num_files"):
        return files_attr
    return None
