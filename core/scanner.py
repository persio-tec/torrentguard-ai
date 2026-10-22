import os

from core.lt_compat import list_files

class PreDownloadScanner:
    def __init__(self):
        self.suspicious_ext = ['.exe','.msi','.bat','.cmd','.sh','.ps1','.vbs','.js','.jar','.scr','.pif','.com']
        self.piracy_keywords = ['crack','keygen','patch','activator','loader','serial','license','nulled','warez']

    def analyze_info(self, info):
        files = [{'path': path, 'size': size}
                 for path, size in list_files(info)]
        name = ""
        try:
            name = info.name()
        except Exception:
            pass
        return self.analyze_files(files, name)

    def analyze_files(self, files, name=""):
        report = {'risk': 'LOW', 'score': 0, 'reasons': [], 'files': files, 'blocked_ext': []}
        text = name.lower()
        for k in self.piracy_keywords:
            if k in text:
                report['score'] += 15
                report['reasons'].append(f"Nome contém termo suspeito: {k}")
        for f in files:
            p = f['path'].lower()
            ext = os.path.splitext(p)[1]
            if ext in self.suspicious_ext:
                report['blocked_ext'].append(f['path'])
                report['score'] += 12
                report['reasons'].append(f"Arquivo executável detectado: {f['path']}")
            for k in self.piracy_keywords:
                if k in p:
                    report['score'] += 10
                    report['reasons'].append(f"Nome suspeito: {f['path']}")
        if report['score'] >= 40: report['risk'] = 'HIGH'
        elif report['score'] >= 20: report['risk'] = 'MEDIUM'
        else: report['risk'] = 'LOW'
        return report
