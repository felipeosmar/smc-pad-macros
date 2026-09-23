#!/usr/bin/env python3
"""
midi-macros — transforma o controlador MIDI SMC-PAD Pocket em um teclado de macros.

Lê os eventos MIDI (Note on) da porta ALSA do dispositivo via `aseqdump` e, para
cada pad (nota), executa a ação definida em config.json.

Tipos de ação suportados (campo "type" em cada pad):
  - "key":  atalho de teclado via ydotool. Campo "keys" = "ctrl+c" ou ["ctrl+c","enter"].
            Os nomes são traduzidos para keycodes (ver KEYCODES); a sintaxe crua do
            ydotool ("29:1 46:1 46:0 29:0") também é aceita e repassada sem alteração.
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
import threading

CONFIG = os.path.expanduser("~/.config/midi-macros/config.json")

# Ex.: "128:0   Note on                 9, note 36, velocity 93"
NOTE_RE = re.compile(r"Note on\s+\d+,\s*note\s+(\d+),\s*velocity\s+(\d+)")

DEVNULL = subprocess.DEVNULL


def log(*a):
    print("[midi-macros]", *a, file=sys.stderr, flush=True)


def build_env():
    """Ambiente para lançar apps GUI / ydotool a partir do serviço systemd --user."""
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":0")
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


# O ydotool 1.x abandonou os nomes de tecla: o subcomando `key` aceita apenas pares
# "<keycode>:<pressionado>" e — pior — ignora em silêncio (exit 0) qualquer valor que
# não entenda, o que fazia todo pad "key" falhar sem deixar rastro. Traduzimos nomes
# para keycodes aqui e validamos antes de invocar o ydotool.
# Valores conforme /usr/include/linux/input-event-codes.h (KEY_*).
KEYCODES = {
    # modificadores
    "ctrl": 29, "leftctrl": 29, "rightctrl": 97, "shift": 42, "leftshift": 42,
    "rightshift": 54, "alt": 56, "leftalt": 56, "rightalt": 100, "altgr": 100,
    "super": 125, "meta": 125, "win": 125, "leftmeta": 125, "rightmeta": 126,
    # letras
    "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34, "h": 35, "i": 23,
    "j": 36, "k": 37, "l": 38, "m": 50, "n": 49, "o": 24, "p": 25, "q": 16, "r": 19,
    "s": 31, "t": 20, "u": 22, "v": 47, "w": 17, "x": 45, "y": 21, "z": 44,
    # dígitos
    "0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10,
    # teclas de função
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66,
    "f9": 67, "f10": 68, "f11": 87, "f12": 88, "f13": 183, "f14": 184, "f15": 185,
    "f16": 186, "f17": 187, "f18": 188, "f19": 189, "f20": 190, "f21": 191, "f22": 192,
    "f23": 193, "f24": 194,
    # edição e navegação
    "enter": 28, "return": 28, "esc": 1, "escape": 1, "backspace": 14, "tab": 15,
    "space": 57, "delete": 111, "insert": 110, "home": 102, "end": 107, "pageup": 104,
    "pagedown": 109, "up": 103, "down": 108, "left": 105, "right": 106,
    # travas e teclas especiais
    "printscreen": 99, "print": 99, "sysrq": 99, "capslock": 58, "numlock": 69,
    "scrolllock": 70, "menu": 127, "compose": 127,
    # pontuação (layout US)
    "minus": 12, "equal": 13, "plus": 13, "leftbrace": 26, "rightbrace": 27,
    "semicolon": 39, "apostrophe": 40, "grave": 41, "backslash": 43, "comma": 51,
    "dot": 52, "period": 52, "slash": 53,
    # mídia
    "volumeup": 115, "volumedown": 114, "mute": 113, "playpause": 164, "nextsong": 163,
    "previoussong": 165, "stopcd": 166,
}

# Sintaxe crua do ydotool, ex.: "29:1" (keycode 29 pressionado).
RAW_EVENT_RE = re.compile(r"^\d+:[01]$")


def key_events(combo):
    """Traduz um atalho em eventos do ydotool.

    "ctrl+c" -> ["29:1", "46:1", "46:0", "29:0"] — pressiona na ordem escrita e
    solta na ordem inversa. Uma string já no formato cru do ydotool é repassada
    intacta. Levanta ValueError se algum nome for desconhecido, para que o erro
    apareça no log em vez de virar um no-op silencioso.
    """
    tokens = combo.split()
    if tokens and all(RAW_EVENT_RE.match(t) for t in tokens):
        return tokens

    nomes = [n for n in combo.lower().replace(" ", "").split("+") if n]
    if not nomes:
        raise ValueError(f"atalho vazio: {combo!r}")
    codigos = []
    for n in nomes:
        if n not in KEYCODES:
            raise ValueError(f"tecla desconhecida {n!r} em {combo!r}")
        codigos.append(KEYCODES[n])
    return [f"{c}:1" for c in codigos] + [f"{c}:0" for c in reversed(codigos)]


def run_action(action, env):
    """Executa a ação de um pad.

    Devolve None em caso de sucesso ou uma mensagem de erro, para que a GUI possa
    mostrar ao usuário o motivo real em vez de um sucesso falso.
    """
    def fail(msg):
        log("ação não executada —", msg)
        return msg

    typ = action.get("type")
    if typ == "key":
        keys = action.get("keys")
        seq = keys if isinstance(keys, list) else [keys]
        eventos = []
        for combo in seq:
            if not isinstance(combo, str):
                return fail(f"'keys' inválido: {combo!r}")
            try:
                eventos += key_events(combo)
            except ValueError as e:
                return fail(str(e))
        p = subprocess.Popen(["ydotool", "key", *eventos], env=env,
                             stdout=DEVNULL, stderr=subprocess.PIPE, text=True)
        _, err = p.communicate()
        if p.returncode != 0:
            return fail(f"ydotool saiu com rc={p.returncode}: {err.strip()}")
    elif typ == "type":
        subprocess.Popen(["ydotool", "type", action.get("text", "")],
                         env=env, stdout=DEVNULL, stderr=DEVNULL)
    elif typ == "exec":
        subprocess.Popen(action.get("cmd", ""), shell=True, env=env,
                         stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)
    else:
        return fail(f"tipo de ação desconhecido: {typ!r}")


def client_alsa(device):
    """Número do client ALSA do dispositivo, ou None se ele não estiver conectado."""
    try:
        with open("/proc/asound/seq/clients", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r'\s*Client\s+(\d+)\s+:\s+"([^"]*)"', line)
                if m and device in m.group(2):
                    return int(m.group(1))
    except OSError:
        pass
    return None


def esperar_porta(device, stop, intervalo=3):
    """Espera o dispositivo aparecer no ALSA antes de abrir o aseqdump.

    Sem isso, com o pad desligado o laço externo reabriria o aseqdump a cada 3s e
    encheria o journal de "porta MIDI encerrada".
    """
    avisou = False
    while not stop["flag"]:
        cid = client_alsa(device)
        if cid is not None:
            return cid
        if not avisou:
            log(f"{device} não está conectado; aguardando o dispositivo...")
            avisou = True
        time.sleep(intervalo)
    return None


def vigiar_porta(device, proc, stop, client_inicial, intervalo=5):
    """Derruba o aseqdump quando o client ALSA do dispositivo muda.

    O pad é Bluetooth e dorme por inatividade. Ao reconectar, o ALSA cria um client
    NOVO; o aseqdump inscrito no anterior continua vivo, porém surdo, e não fecha o
    stdout — então o laço de leitura nunca percebe e o retry existente jamais dispara.
    Matar o processo faz o laço externo reconectar na porta nova.
    """
    while not stop["flag"] and proc.poll() is None:
        time.sleep(intervalo)
        atual = client_alsa(device)
        if atual != client_inicial:
            log(f"porta MIDI mudou (client {client_inicial} -> {atual}); reconectando")
            try:
                proc.terminate()
            except Exception:
                pass
            return


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
        client = esperar_porta(device, stop)
        if stop["flag"]:
            break
        proc = subprocess.Popen(["aseqdump", "-p", device],
                                stdout=subprocess.PIPE, stderr=DEVNULL, text=True)
        log(f"escutando {device} (client ALSA {client})")
        threading.Thread(target=vigiar_porta, args=(device, proc, stop, client),
                         daemon=True).start()
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
