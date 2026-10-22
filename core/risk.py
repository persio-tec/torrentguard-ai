"""Classificacao de risco dos torrents (scanner local + parecer do OpenCode).

Niveis usados na interface:

* ``LOW``    - sem indicio de risco
* ``MEDIUM`` - risco moderado (exige confirmacao antes de baixar)
* ``HIGH``   - risco alto (exige confirmacao explicita antes de baixar)
"""

import re

#: niveis na ordem crescente de gravidade
LEVELS = ("LOW", "MEDIUM", "HIGH")

#: rotulos exibidos na interface
LEVEL_LABELS = {
    "LOW": "OK",
    "MEDIUM": "MEDIO",
    "HIGH": "ALTO",
}

#: cores dos rotulos na tabela
LEVEL_COLORS = {
    "LOW": "#2e7d32",
    "MEDIUM": "#e08b00",
    "HIGH": "#c62828",
}

#: classificacoes do OpenCode -> nivel de risco
OPENCODE_LEVELS = {
    "PERIGOSO": "HIGH",
    "PERIGOSA": "HIGH",
    "SUSPEITO": "MEDIUM",
    "SUSPEITOS": "MEDIUM",
    "SEGURO": "LOW",
    "SEGURA": "LOW",
}


def worst(level_a, level_b):
    """Devolve o nivel mais grave entre dois."""
    for level in reversed(LEVELS):
        if level in (level_a, level_b):
            return level
    return "LOW"


def parse_verdict(text):
    """Extrai ``(nivel, recomendacao)`` do parecer do OpenCode.

    O modelo responde em texto livre (markdown), entao a leitura e feita
    por expressoes regulares tolerantes a acentuacao e formatacao.
    """
    if not text:
        return None, None
    upper = text.upper()

    level = None
    match = re.search(
        r"CLASSIFIC\w{0,8}\s*[:\-*]{0,3}\s*\**\s*(PERIGOS[OA]|SUSPEIT[OA]|SEGUR[OA])",
        upper)
    if match:
        level = OPENCODE_LEVELS.get(match.group(1))

    recommendation = None
    match = re.search(
        r"RECOMEND\w{0,8}\s*[:\-*]{0,3}\s*\**\s*"
        r"(BAIXAR COM CAUTELA|N[ÃA]O RECOMENDADO|PARECER SEGURO)",
        upper)
    if match:
        recommendation = match.group(1)

    return level, recommendation


def summary_of(report):
    """Resumo curto do relatorio local, para a janela de aviso."""
    if not report:
        return ""
    reasons = report.get("reasons") or []
    blocked = report.get("blocked_ext") or []
    parts = []
    if reasons:
        parts.append("\n".join(f"- {r}" for r in reasons[:8]))
    if blocked:
        parts.append("Executáveis encontrados: " + ", ".join(blocked[:8]))
    return "\n".join(parts)
