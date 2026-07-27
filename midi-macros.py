#!/usr/bin/env python3
"""
midi-macros — transforma o controlador MIDI SMC-PAD Pocket em um teclado de macros.

Lê os eventos MIDI (Note on) da porta ALSA do dispositivo via `aseqdump` e, para
cada pad (nota), executa a ação definida em config.json.

Tipos de ação suportados (campo "type" em cada pad):
  - "key":  atalho de teclado via ydotool. Campo "keys" = "ctrl+c" ou ["ctrl+c","enter"].
  - "type": digita texto literal via ydotool. Campo "text" = "texto".
  - "exec": roda um comando de shell. Campo "cmd" = "firefox" / "playerctl next" / etc.

A config é relida a cada toque, então dá para editar sem reiniciar o serviço.
"""
import json
import os
import re
import subprocess
import sys
import time
import signal

CONFIG = os.path.expanduser("~/.config/midi-macros/config.json")

# Ex.: "128:0   Note on                 9, note 36, velocity 93"
NOTE_RE = re.compile(r"Note on\s+\d+,\s*note\s+(\d+),\s*velocity\s+(\d+)")

DEVNULL = subprocess.DEVNULL


def log(*a):
    print("[midi-macros]", *a, file=sys.stderr, flush=True)


def build_env():
    """Ambiente para lançar apps GUI / ydotool a partir do serviço systemd --user."""
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":1")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{os.getuid()}/bus"
    return env


_last_good_cfg = {}


def load_config():
    global _last_good_cfg
    try:
        with open(CONFIG) as f:
            _last_good_cfg = json.load(f)
    except Exception as e:
        log("config.json inválido, usando última versão válida:", e)
    return _last_good_cfg


def run_action(action, env):
    typ = action.get("type")
    if typ == "key":
        keys = action.get("keys")
        seq = keys if isinstance(keys, list) else [keys]
        args = ["ydotool", "key"] + seq
        p = subprocess.Popen(args, env=env, stdout=DEVNULL, stderr=subprocess.PIPE, text=True)
        _, err = p.communicate()
        if p.returncode != 0 and err:
            log(f"ydotool key falhou ({keys}): {err.strip()}")
    elif typ == "type":
        subprocess.Popen(["ydotool", "type", action.get("text", "")],
                         env=env, stdout=DEVNULL, stderr=DEVNULL)
    elif typ == "exec":
        subprocess.Popen(action.get("cmd", ""), shell=True, env=env,
                         stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)
    else:
        log(f"tipo de ação desconhecido: {typ!r}")


def main():
    env = build_env()
    load_config()
    device = _last_good_cfg.get("device", "SMC-PAD Pocket")

    stop = {"flag": False}

    def _term(*_):
        stop["flag"] = True
    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    log(f"iniciando — device MIDI: {device!r}")
    while not stop["flag"]:
        proc = subprocess.Popen(["aseqdump", "-p", device],
                                stdout=subprocess.PIPE, stderr=DEVNULL, text=True)
        log(f"escutando {device}")
        try:
            for line in proc.stdout:
                if stop["flag"]:
                    break
                m = NOTE_RE.search(line)
                if not m:
                    continue
                note, vel = int(m.group(1)), int(m.group(2))
                if vel == 0:           # note-off disfarçado
                    continue
                cfg = load_config()
                action = cfg.get("pads", {}).get(str(note))
                if not action:
                    log(f"pad nota {note}: sem mapeamento (adicione em config.json)")
                    continue
                log(f"pad nota {note} -> {action.get('label', action.get('type'))}")
                try:
                    run_action(action, env)
                except Exception as e:
                    log("erro ao executar ação:", e)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
        if stop["flag"]:
            break
        log("porta MIDI encerrada (dispositivo desconectou?). Retentando em 3s...")
        time.sleep(3)
    log("encerrado.")


if __name__ == "__main__":
    main()
