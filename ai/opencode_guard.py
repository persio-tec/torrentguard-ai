"""Analise de torrents com o OpenCode CLI."""

import os
import subprocess

#: candidatos para o executavel do OpenCode CLI
CLI_CANDIDATES = (
    "/usr/lib/opencode-desktop/opencode-cli",
    "/usr/local/bin/opencode",
    os.path.expanduser("~/.local/bin/opencode"),
)


class OpenCodeGuard:
    def __init__(self, model="opencode/big-pickle", timeout=240):
        self.model = self._normalize_model(model)
        self.timeout = timeout
        self.cli = self._find_cli()

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_model(model):
        """Aceita 'big-pickle' ou 'opencode/big-pickle'."""
        model = (model or "big-pickle").strip()
        if "/" not in model:
            return "opencode/" + model
        return model

    # ------------------------------------------------------------------
    @staticmethod
    def _find_cli():
        """Localiza o executavel do OpenCode CLI."""
        for path in CLI_CANDIDATES:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        found = None
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(directory, "opencode-cli")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return found

    # ------------------------------------------------------------------
    def analyze_torrent(self, name, files, report=None):
        """Pede ao OpenCode um parecer de seguranca sobre o torrent.

        ``report`` e opcional: quando informado (dicionario do
        ``PreDownloadScanner``) o parecer ja considera o risco calculado
        localmente.
        """
        if not files:
            return "Nenhum arquivo para analisar."

        lines = []
        total = 0
        for entry in files[:40]:
            path = entry.get("path", "?") if isinstance(entry, dict) else str(entry)
            size = entry.get("size", 0) if isinstance(entry, dict) else 0
            try:
                size = int(size)
            except (TypeError, ValueError):
                size = 0
            total += size
            lines.append("- %s (%.2f MB)" % (path, size / 1024 / 1024))

        extra = ""
        if report:
            extra = (
                "\nAnalise local previa (scanner): risco={risk}, score={score}\n"
                "Motivos: {reasons}\n"
            ).format(
                risk=report.get("risk", "?"),
                score=report.get("score", "?"),
                reasons="; ".join(report.get("reasons") or []) or "nenhum",
            )

        prompt = (
            "Voce e um analisador de seguranca para torrents.\n"
            "Avalie este torrent ANTES do download.\n\n"
            "Nome: {name}\n"
            "Total de arquivos: {count} ({size:.2f} MB)\n"
            "{extra}\n"
            "Arquivos:\n{files}\n\n"
            "Responda em PORTUGUES com:\n"
            "1. CLASSIFICACAO: SEGURO | SUSPEITO | PERIGOSO\n"
            "2. MOTIVO: explicacao objetiva\n"
            "3. RISCOS: lista\n"
            "4. RECOMENDACAO: BAIXAR COM CAUTELA | NAO RECOMENDADO | PARECER SEGURO\n"
            "5. DICAS: o que observar"
        ).format(name=name, count=len(files), size=total / 1024 / 1024,
                 extra=extra, files="\n".join(lines))

        cli = self.cli or self._find_cli()
        if not cli:
            return ("OpenCode CLI nao encontrado.\n"
                    "Procurei em: %s" % ", ".join(CLI_CANDIDATES))

        env = os.environ.copy()
        env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + env.get("PATH", "")
        try:
            proc = subprocess.run(
                [cli, "run", "--model", self.model, prompt],
                capture_output=True, text=True, timeout=self.timeout, env=env)
        except FileNotFoundError:
            return "OpenCode CLI nao encontrado em %s" % cli
        except subprocess.TimeoutExpired:
            return "Tempo esgotado (%ss) na analise com OpenCode." % self.timeout
        except Exception as exc:
            return "Erro ao executar o OpenCode: %s" % exc

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()

        if proc.returncode != 0:
            return ("OpenCode retornou erro (codigo %s).\n%s"
                    % (proc.returncode, err or out or "sem detalhes"))

        if out:
            # remove o cabecalho de "build · modelo" que o CLI imprime
            cleaned = "\n".join(
                line for line in out.splitlines()
                if not line.strip().startswith(">")
            ).strip()
            return cleaned or out
        if err:
            return err
        return "Sem resposta do OpenCode."
