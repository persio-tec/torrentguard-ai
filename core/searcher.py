"""Fontes de busca de torrents usadas dentro do app.

Cada fonte devolve dicionarios com as mesmas chaves::

    {'name', 'link', 'seeds', 'leeches', 'size', 'source'}

O campo ``link`` e um magnet pronto sempre que possivel, para que o
resultado possa ser adicionado ao TorrentGuard sem etapas extras.

Fontes:

* ``apibay``   - API oficial do The Pirate Bay (funciona)
* ``nyaa``     - feed RSS (magnet montado a partir do info hash)
* ``1337x``    - HTML (protegido por Cloudflare, avisa quando falha)
* ``tgx``      - HTML (dominio principal fora do ar, usa mirrors)
"""

import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

#: trackers usados nos magnet links montados pelo app
TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://open.stealth.si:80/announce",
    "udp://exodus.desync.com:6969/announce",
)

#: mirrors do TorrentGalaxy (o dominio principal saiu do ar)
TGX_MIRRORS = (
    "https://torrentgalaxy.to",
    "https://torrentgalaxy.click",
    "https://torrentgalaxy.pm",
)

#: categorias da API do The Pirate Bay
TPB_CATEGORIES = {
    "video": 200,
    "audio": 100,
    "aplicativos": 300,
    "jogos": 400,
}


def human_size(num):
    try:
        num = int(num)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if num < 1024.0:
                return f"{num:.2f} {unit}"
            num /= 1024.0
        return f"{num:.2f} PB"
    except (TypeError, ValueError):
        return '-'


def info_hash_of(link):
    """Extrai o info hash de um magnet link (ou '' se nao houver)."""
    if not link:
        return ""
    match = re.search(r'urn:btih:([0-9a-fA-F]{40})', link)
    return match.group(1).lower() if match else ""


def build_magnet(info_hash, name):
    """Monta um magnet link completo a partir do info hash."""
    trackers = "".join("&tr=" + quote_plus(t) for t in TRACKERS)
    return (f"magnet:?xt=urn:btih:{info_hash}"
            f"&dn={quote_plus(name or '')}{trackers}")


class TorrentSearcher:
    def __init__(self, timeout=20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        #: mensagens de erro das fontes consultadas (ultima busca)
        self.last_errors = []

    # ------------------------------------------------------------------
    # utilitarios
    # ------------------------------------------------------------------
    def _reset_errors(self):
        self.last_errors = []

    def _error(self, source, message):
        self.last_errors.append(f"{source}: {message}")
        return []

    def _add(self, results, item):
        """Adiciona o resultado ignorando info hashes repetidos."""
        info_hash = info_hash_of(item.get('link', ''))
        if info_hash:
            for existing in results:
                if info_hash_of(existing.get('link', '')) == info_hash:
                    return results
        results.append(item)
        return results

    def _get(self, url, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        return self.session.get(url, **kwargs)

    # ------------------------------------------------------------------
    # fontes
    # ------------------------------------------------------------------
    def search_1337x(self, query):
        """Busca no 1337x (protegido por Cloudflare - pode falhar)."""
        results = []
        try:
            url = f"https://1337x.to/search/{quote_plus(query)}/1/"
            r = self._get(url)
            if r.status_code != 200:
                return self._error("1337x", f"HTTP {r.status_code} (bloqueado pelo site)")
            soup = BeautifulSoup(r.text, 'html.parser')
            for row in soup.select('table.table-list tbody tr')[:25]:
                cells = row.find_all('td')
                if len(cells) < 6:
                    continue
                a = row.select_one('td.name a:nth-of-type(2)') or row.select_one('td.name a')
                if not a or not a.get('href'):
                    continue
                name = a.text.strip()
                link = a['href']
                if link.startswith('/'):
                    link = 'https://1337x.to' + link
                seeds = cells[1].text.strip()
                leech = cells[2].text.strip()
                size = cells[4].text.strip()
                self._add(results, {'name': name, 'link': link, 'seeds': seeds,
                                    'leeches': leech, 'size': size, 'source': '1337x'})
        except Exception as exc:
            return self._error("1337x", str(exc))
        return results

    def search_nyaa(self, query):
        """Busca no nyaa.si usando o feed RSS (magnet pelo info hash)."""
        results = []
        try:
            url = f"https://nyaa.si/?page=rss&q={quote_plus(query)}&c=0_0"
            r = self._get(url)
            if r.status_code != 200:
                return self._error("nyaa", f"HTTP {r.status_code}")
            soup = BeautifulSoup(r.text, 'xml')
            items = soup.find_all('item')
            if not items:
                return self._error("nyaa", "nenhum resultado")
            for item in items[:40]:
                name = item.title.text.strip() if item.title else ""
                if not name:
                    continue
                info_hash = ""
                node = item.find('nyaa:infoHash')
                if node and node.text:
                    info_hash = node.text.strip()
                seeds = item.find('nyaa:seeders')
                leech = item.find('nyaa:leechers')
                size = item.find('nyaa:size')
                if not info_hash:
                    # sem info hash: usa a pagina de detalhe para pegar o magnet
                    link_node = item.link
                    detail = link_node.text.strip() if link_node else ''
                    magnet = self.get_magnet(detail)
                    if not magnet:
                        continue
                    link = magnet
                else:
                    link = build_magnet(info_hash, name)
                self._add(results, {
                    'name': name,
                    'link': link,
                    'seeds': seeds.text.strip() if seeds else '0',
                    'leeches': leech.text.strip() if leech else '0',
                    'size': size.text.strip() if size else '-',
                    'source': 'nyaa.si',
                })
        except Exception as exc:
            return self._error("nyaa", str(exc))
        return results

    def search_tgx(self, query):
        """Busca no TorrentGalaxy (usa mirrors, o dominio principal morreu)."""
        results = []
        last = None
        for base in TGX_MIRRORS:
            try:
                url = (f"{base}/torrents.php?search={quote_plus(query)}"
                       f"&lang=0&nox=2&sort=seeders&order=desc")
                r = self._get(url)
                if r.status_code != 200:
                    last = f"{base} respondeu HTTP {r.status_code}"
                    continue
                soup = BeautifulSoup(r.text, 'html.parser')
                rows = soup.select('div.tgxtable tbody tr.tgxtablerow')
                if not rows:
                    last = f"{base} sem tabela de resultados"
                    continue
                for row in rows[:25]:
                    a = row.select_one('a.txlight')
                    if not a or not a.get('href'):
                        continue
                    name = a.text.strip()
                    link = a['href']
                    if link.startswith('/'):
                        link = base + link
                    tds = row.find_all('td')
                    seeds = tds[11].text.strip() if len(tds) > 11 else '0'
                    leech = tds[12].text.strip() if len(tds) > 12 else '0'
                    size = tds[7].text.strip() if len(tds) > 7 else '-'
                    self._add(results, {'name': name, 'link': link, 'seeds': seeds,
                                        'leeches': leech, 'size': size, 'source': 'tgx'})
                if results:
                    return results
            except Exception as exc:
                last = f"{base}: {exc}"
        return self._error("tgx", last or "fonte indisponivel")

    def _apibay(self, query, category=0, source='apibay', limit=40):
        """Consulta a API do The Pirate Bay (apibay.org)."""
        results = []
        try:
            url = f"https://apibay.org/q.php?q={quote_plus(query)}&cat={category}"
            r = self._get(url)
            if r.status_code != 200:
                return self._error(source, f"HTTP {r.status_code}")
            data = r.json()
            if not isinstance(data, list):
                return self._error(source, "resposta inesperada da API")
            for item in data:
                if not isinstance(item, dict):
                    continue
                if item.get('id') == '0':
                    continue
                info_hash = (item.get('info_hash') or '').strip()
                name = (item.get('name') or '').strip()
                if not info_hash or not name:
                    continue
                self._add(results, {
                    'name': name,
                    'link': build_magnet(info_hash, name),
                    'seeds': str(item.get('seeders') or '0'),
                    'leeches': str(item.get('leechers') or '0'),
                    'size': human_size(item.get('size') or 0),
                    'source': source,
                })
                if len(results) >= limit:
                    break
        except Exception as exc:
            return self._error(source, str(exc))
        return results

    def search_apibay(self, query):
        """Busca na API do The Pirate Bay (todas as categorias)."""
        return self._apibay(query, category=0, source='apibay')

    def search_piratebay(self, query):
        """Busca complementaria por categoria (video, audio, apps, jogos)."""
        results = []
        for label, category in TPB_CATEGORIES.items():
            found = self._apibay(query, category=category,
                                 source=f'tpb/{label}', limit=20)
            for item in found:
                self._add(results, item)
        return results

    # ------------------------------------------------------------------
    # combinacoes
    # ------------------------------------------------------------------
    def search_general(self, query):
        """Busca ampla: The Pirate Bay + nyaa + 1337x + TorrentGalaxy."""
        self._reset_errors()
        results = []
        for finder in (self.search_apibay, self.search_nyaa,
                       self.search_1337x, self.search_tgx):
            for item in finder(query):
                self._add(results, item)
        return results

    def search_files(self, query):
        """Busca por arquivo: The Pirate Bay (geral + categorias)."""
        self._reset_errors()
        results = []
        for finder in (self.search_apibay, self.search_piratebay):
            for item in finder(query):
                self._add(results, item)
        return results

    # ------------------------------------------------------------------
    def get_magnet(self, url):
        """Tenta obter o magnet link de uma pagina HTML."""
        try:
            if url and url.startswith('magnet:'):
                return url
            r = self._get(url)
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('magnet:?'):
                    return href
        except Exception:
            pass
        return None
