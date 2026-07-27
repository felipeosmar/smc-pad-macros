# MIDI Macros GUI — Design (aprovado 2026-07-27)

Interface gráfica para configurar o `midi-macros` (SMC-PAD Pocket → macros do SO).

## Decisões
- **Forma:** app web local, sem dependências (Python stdlib + HTML/CSS/JS puro), bind em 127.0.0.1.
- **Vibe:** dark neon / Launchpad.
- **Ao vivo:** não (edição estática do `config.json`; o daemon relê a cada toque, salvar vale na hora).
- **Execução:** sob demanda — comando/ícone sobe servidor + abre navegador; heartbeat encerra o servidor quando a aba fecha.
- **Recursos:** controle do serviço systemd, botão "Testar" por pad, captura de atalho de teclado, lançador no menu de apps.

## Estrutura
```
~/.config/midi-macros/gui/
  server.py          # http.server; importa run_action/build_env do midi-macros.py
  static/index.html
  static/style.css
  static/app.js
~/.local/bin/midi-macros-gui
~/.local/share/applications/midi-macros-gui.desktop
```

## API (localhost)
- `GET /api/config` / `PUT /api/config` — ler / salvar (valida JSON antes de gravar).
- `POST /api/test {note}` — dispara a ação do pad (reusa `run_action`).
- `GET /api/service` / `POST /api/service {action}` — status e start/stop/restart do serviço.
- `POST /api/heartbeat` + `POST /api/quit` — encerra o servidor ao fechar a aba (timeout ~15s).

## UI
- Grid 4×4 na ordem física (topo 48-51 … base 36-39); cor por tipo (tecla=ciano, comando=magenta, texto=verde-lima, mídia/volume=laranja, vazio=cinza); glow + animação de pressão.
- Editor lateral: tipo, campo conforme tipo, rótulo, botões Testar/Salvar. Captura de atalho no tipo tecla.
- Barra superior: status do serviço (indicador + start/stop/restart), "Salvar tudo".

## Notas
- Testar ação de tecla injeta no foco atual (o navegador) — avisar na UI.
- Não controla o LED RGB físico (firmware proprietário).
- Sem repositório git; design registrado localmente, sem commit.
