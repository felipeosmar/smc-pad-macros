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
- **Captura de atalho** — clique em "Gravar" e aperte a combinação; ela é gravada por nome (ex.: `ctrl+shift+t`)
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

- **`key`** — atalho de teclado. `keys` aceita `"ctrl+c"` ou uma lista
  `["ctrl+c","enter"]` (a lista é disparada em sequência).

  Os nomes são traduzidos pelo daemon para os keycodes do Linux, porque o
  `ydotool` 1.x só aceita pares `<keycode>:<pressionado>` — e ignora em silêncio
  o que não entende. Nomes reconhecidos (tabela `KEYCODES` em `midi-macros.py`):

  | Grupo | Nomes |
  |---|---|
  | Modificadores | `ctrl`, `shift`, `alt`, `super`/`meta`/`win`, `altgr`, e as variantes `left…`/`right…` |
  | Letras e dígitos | `a`–`z`, `0`–`9` |
  | Função | `f1`–`f24` |
  | Edição/navegação | `enter`/`return`, `esc`, `backspace`, `tab`, `space`, `delete`, `insert`, `home`, `end`, `pageup`, `pagedown`, `up`, `down`, `left`, `right` |
  | Travas e especiais | `print`/`printscreen`, `capslock`, `numlock`, `scrolllock`, `menu` |
  | Pontuação (layout US) | `minus`, `equal`/`plus`, `leftbrace`, `rightbrace`, `semicolon`, `apostrophe`, `grave`, `backslash`, `comma`, `dot`/`period`, `slash` |
  | Mídia | `volumeup`, `volumedown`, `mute`, `playpause`, `nextsong`, `previoussong`, `stopcd` |

  Maiúsculas/minúsculas e espaços são ignorados (`CTRL + C` = `ctrl+c`). As teclas
  são pressionadas na ordem escrita e soltas na ordem inversa. Um nome desconhecido
  **não** é executado: vira erro no log do serviço e falha visível no botão
  "Testar agora" da GUI.

  A sintaxe crua do `ydotool` também é aceita e repassada intacta, para casos que
  a tabela não cobre:

  ```json
  { "type": "key", "keys": "29:1 46:1 46:0 29:0", "label": "Copiar (keycodes)" }
  ```

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

### 1. Permissão do `/dev/uinput` e o daemon `ydotoold`

O `ydotool` precisa escrever em `/dev/uinput`. O pacote do Debian/Ubuntu já
instala a regra udev que libera isso para o grupo `input`
(`/usr/lib/udev/rules.d/80-uinput.rules`) — **não é preciso criar regra à mão**.
Falta apenas entrar no grupo:

```bash
sudo usermod -aG input "$USER"     # relogue depois disto
```

O `ydotool` não age sozinho: ele conversa com o daemon `ydotoold`, que o pacote
entrega como serviço de usuário. Ative:

```bash
systemctl --user enable --now ydotool.service
systemctl --user status ydotool.service
```

Sem o `ydotoold` rodando, os pads `key` e `type` falham silenciosamente — os
pads `exec` continuam funcionando, porque não passam pelo `ydotool`.

### 2. Arquivos do projeto

O daemon e a GUI resolvem tudo a partir de `~/.config/midi-macros/`. Clone ali:

```bash
git clone https://github.com/felipeosmar/smc-pad-macros.git ~/.config/midi-macros
```

Se preferir manter o repositório no seu diretório de trabalho, use um symlink:

```bash
ln -s ~/work/smc-pad-macros ~/.config/midi-macros
```

### 3. Serviço systemd (usuário)

`~/.config/systemd/user/midi-macros.service`:

```ini
[Unit]
Description=MIDI Macros — SMC-PAD Pocket controla macros do sistema
After=graphical-session.target ydotool.service
Wants=ydotool.service
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/.config/midi-macros/midi-macros.py
Restart=always
RestartSec=3
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-0

[Install]
WantedBy=graphical-session.target
```

`DISPLAY` deve casar com a sua sessão — confira com
`systemctl --user show-environment | grep -E 'DISPLAY|WAYLAND'`.

Ative:

```bash
systemctl --user daemon-reload
systemctl --user enable --now midi-macros.service
systemctl --user status midi-macros.service
```

### 4. Lançador da GUI e ícone no menu

`~/.local/bin/midi-macros-gui`:

```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/midi-macros-gui <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 "$HOME/.config/midi-macros/gui/server.py" "$@"
EOF
chmod +x ~/.local/bin/midi-macros-gui
```

Para o ícone **MIDI Macros** aparecer no menu de aplicativos:

```bash
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
install -m 644 ~/.config/midi-macros/gui/static/icon.svg \
  ~/.local/share/icons/hicolor/scalable/apps/midi-macros.svg

cat > ~/.local/share/applications/midi-macros.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=MIDI Macros
GenericName=Configurador de macros MIDI
Comment=Configura as macros dos pads do controlador MIDI
Exec=midi-macros-gui
Icon=midi-macros
Terminal=false
Categories=Utility;
Keywords=midi;macro;pad;smc-pad;launchpad;atalho;
StartupNotify=false
EOF

update-desktop-database ~/.local/share/applications
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor
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
| Pad `key` não faz nada | Veja o log (`journalctl --user -u midi-macros -n 20`): nome de tecla desconhecido é recusado e registrado. Se não houver log, `ydotoold` está parado (`systemctl --user status ydotool`) ou você está fora do grupo `input` (`id -nG \| grep input`) — refaça o passo 1 e **relogue**. |
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
