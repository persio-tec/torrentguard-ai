import os
import subprocess

class TorrentFirewall:
    def __init__(self):
        self.enabled = False

    def enable(self):
        try:
            # Bloqueio básico via iptables se disponível (userland)
            cmds = [
                ["iptables", "-N", "TORRENTGUARD"],
                ["iptables", "-I", "INPUT", "-j", "TORRENTGUARD"],
                ["iptables", "-I", "OUTPUT", "-j", "TORRENTGUARD"],
            ]
            for c in cmds:
                subprocess.run(c, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.enabled = True
            return True
        except Exception as e:
            return False

    def disable(self):
        try:
            subprocess.run(["iptables", "-F", "TORRENTGUARD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["iptables", "-X", "TORRENTGUARD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.enabled = False
            return True
        except:
            return False

    def status(self):
        return "ATIVO" if self.enabled else "INATIVO"
