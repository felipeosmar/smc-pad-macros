# 🎛️ midi-macros

Transforme um controlador MIDI de pads em um **teclado de macros** para o Linux.
Cada pad dispara uma ação do sistema — atalho de teclado, comando de shell ou
digitação de texto — e tudo é configurável por uma **interface gráfica dark-neon**
estilo Launchpad.

Feito para o **M-VAVE SMC-PAD Pocket** (16 pads, BLE-MIDI), mas funciona com
qualquer dispositivo que apareça como porta ALSA sequencer.

![Feito para GNOME/Wayland](https://img.shields.io/badge/GNOME-Wayland-22d3ee)
![Python stdlib](https://img.shields.io/badge/Python-stdlib%20only-a3e635)
![Sem dependências externas](https://img.shields.io/badge/deps-0-f04dc4)

---

## Como funciona

```
┌──────────────┐   BLE-MIDI   ┌─────────┐   Note on    ┌──────────────┐
│ SMC-PAD      │ ───────────► │  BlueZ  │ ───────────► │  aseqdump    │
│ Pocket       │   (Bluetooth)│  (ALSA) │  (porta seq) │  (parser)    │
└──────────────┘              └─────────┘              └──────┬───────┘
                                                              │ nota → ação
                                                              ▼
                          ┌───────────────────────────────────────────┐
                          │  midi-macros.py (daemon systemd --user)     │
                          │   key  → ydotool key   ctrl+c               │
                          │   type → ydotool type  "texto"             │
                          │   exec → sh -c         "playerctl next"    │
                          └───────────────────────────────────────────┘
```

O daemon lê os eventos `Note on` da porta ALSA do controlador via `aseqdump` e,
para cada pad (nota MIDI **36–51**), executa a ação definida em `config.json`.
A config é **relida a cada toque**, então você edita sem reiniciar nada.

Injeção de teclado/texto usa **`ydotool`** (via `/dev/uinput`), que funciona no
Wayland nativo do GNOME — onde o `xdotool` não alcança.

---

## Componentes

| Caminho | O que é |
|---|---|
| `midi-macros.py` | O daemon. Escuta o MIDI e dispara as ações. |
| `config.json` | Mapa `nota → ação`. Editável à mão ou pela GUI. |
| `gui/` | Interface web local de configuração (Python stdlib puro). |
| `scripts/` | Scripts de exemplo chamados por pads do tipo `exec`. |
| `DESIGN.md` | Registro das decisões de design da GUI. |

---

## Interface gráfica

Uma **web app local** (sem dependências, só a stdlib do Python) com estética
dark-neon "Launchpad": grid de 16 pads onde cada um brilha com a cor da sua
categoria de ação.

**Recursos:**

- Grade de 16 pads na mesma disposição física do controlador
- Editor lateral com 4 tipos de ação: **Tecla**, **Comando**, **Texto** e **Vazio**
- **Captura de atalho** — clique em "Gravar" e aperte a combinação; ela vira a sintaxe do `ydotool`
- **Testar agora** dispara a ação sem tocar no controlador
- **Controle do serviço** (Ligar / Desligar / Reiniciar) com LED de estado ao vivo
- **Salvar tudo** grava no mesmo `config.json` que o daemon lê

**Ciclo de vida inteligente:** o servidor sobe sob demanda em `127.0.0.1:8765`,
abre o navegador sozinho e **se encerra quando você fecha a aba** — nada fica
rodando em segundo plano à toa.

Abra com:

```bash
midi-macros-gui
```

…ou pelo ícone **MIDI Macros** no menu de aplicativos.

### Cores das categorias

| Cor | Categoria | Tipo de ação |
|---|---|---|
| 🟦 Ciano | Tecla | `key` |
| 🟪 Magenta | Comando | `exec` |
| 🟨 Âmbar | Mídia/Volume | `exec` com `playerctl`/`wpctl`/… |
| 🟩 Lima | Texto | `type` |
| ⬜ Cinza | Vazio | sem ação |

---

## Formato do `config.json`

```json
{
  "device": "SMC-PAD Pocket",
  "pads": {
    "42": { "type": "key",  "keys": "ctrl+c",             "label": "Copiar" },
    "48": { "type": "exec", "cmd": "firefox",             "label": "Abrir Firefox" },
    "36": { "type": "exec", "cmd": "playerctl play-pause","label": "Play/Pause" },
    "51": { "type": "type", "text": "meu@email.com",      "label": "Digitar email" }
  }
}
```

- **`key`** — atalho de teclado. `keys` aceita `"ctrl+c"` ou uma lista `["ctrl+c","enter"]`.
- **`type`** — digita `text` literalmente onde o cursor estiver.
- **`exec`** — roda `cmd` como comando de shell no seu ambiente gráfico.

As chaves são as **notas MIDI** dos pads (36–51 no SMC-PAD Pocket). Descubra a
nota de cada pad monitorando o dispositivo:

```bash
aseqdump -p "SMC-PAD Pocket"
```

---

## Instalação

### Dependências

```bash
sudo apt install ydotool playerctl alsa-utils   # aseqdump vem em alsa-utils
# wpctl vem com o PipeWire (wireplumber)
```

### 1. Permissão do `/dev/uinput` (para o ydotool)

O `ydotool` precisa escrever em `/dev/uinput`. Crie a regra udev:

```bash
sudo tee /etc/udev/rules.d/99-uinput-perm.rules <<'EOF'
KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG input "$USER"     # relogue depois disto
```

### 2. Arquivos do projeto

Coloque o projeto em `~/.config/midi-macros/`:

```bash
git clone https://github.com/felipeosmar/smc-pad-macros.git ~/.config/midi-macros
```

### 3. Serviço systemd (usuário)

`~/.config/systemd/user/midi-macros.service`:

```ini
[Unit]
Description=MIDI Macros — SMC-PAD Pocket controla macros do sistema
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/.config/midi-macros/midi-macros.py
Restart=always
RestartSec=3
Environment=DISPLAY=:1
Environment=WAYLAND_DISPLAY=wayland-0

[Install]
WantedBy=graphical-session.target
```

Ative:

```bash
systemctl --user daemon-reload
systemctl --user enable --now midi-macros.service
systemctl --user status midi-macros.service
```

### 4. Lançador da GUI (opcional)

`~/.local/bin/midi-macros-gui`:

```bash
#!/usr/bin/env bash
exec /usr/bin/python3 "$HOME/.config/midi-macros/gui/server.py"
```

```bash
chmod +x ~/.local/bin/midi-macros-gui
```

---

## Conectando o controlador (BLE-MIDI)

O SMC-PAD Pocket é um dispositivo **MIDI over Bluetooth Low Energy**. O plugin MIDI
do BlueZ o expõe automaticamente como uma porta ALSA sequencer ao parear:

```bash
bluetoothctl
# scan on → encontre o "SMC-PAD Pocket" → pair <MAC> → connect <MAC> → trust <MAC>
```

Depois de conectado, confirme a porta:

```bash
aconnect -l          # deve listar "SMC-PAD Pocket"
aseqdump -p "SMC-PAD Pocket"   # aperte os pads e veja os "Note on"
```

---

## Solução de problemas

| Sintoma | Causa provável |
|---|---|
| Pads não fazem nada | Serviço parado (`systemctl --user status midi-macros`) ou dispositivo desconectado (`aconnect -l`). |
| `ydotool` falha silenciosamente | Sem permissão em `/dev/uinput` — refaça o passo 1 e **relogue**. |
| Atalho não chega no app certo | O `key` digita na janela em foco; a GUI avisa disso no botão de teste. |
| GUI abre sem estilo | Verifique se `gui/static/` está completo (`index.html`, `style.css`, `app.js`). |

---

## Requisitos

- Linux com **PipeWire** (para `wpctl`) e **BlueZ** com plugin MIDI
- **Python 3** (só a biblioteca padrão — zero pacotes pip)
- `ydotool`, `playerctl`, `alsa-utils`
- Testado no **Ubuntu / GNOME sobre Wayland**

---

## Licença

MIT — use, modifique e compartilhe à vontade.
