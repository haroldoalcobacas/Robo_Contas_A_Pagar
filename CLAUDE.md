# CLAUDE.md

Robô de Contas a Pagar (Desafio RPA #01): lê e-mails de cobrança (NF-e XML, fatura PDF, corpo do e-mail), gera `contas_a_pagar.xlsx` e envia resumo por e-mail/WhatsApp. Python puro, Windows, sem n8n. O enunciado do desafio está em `CONTEXT.md` (local, fora do Git).

## Comandos

```bash
python -m pytest                       # 36 testes; SEMPRE rodar após mudar robo/
python main.py --executar --sem-relatorio   # varredura sem tela (base de exemplo)
python main.py --config                # painel (tkinter)
python main.py                         # ícone na bandeja
powershell -ExecutionPolicy Bypass -File instalador\build.ps1   # .exe + Setup
python docs/gerar_ilustracoes.py       # recaptura imagens da documentação
```

Resultado esperado com a base de exemplo (data 20/09/2026): **9 contas, R$ 8.631,75, 1 duplicidade, 1 exceção, 3 ignorados**. Os testes em `tests/test_gabarito.py` garantem isso; não mude o gabarito para fazer teste passar.

## Arquitetura

- `main.py`: único ponto de entrada (vira `RoboContas.exe`); só trata argumentos.
- `robo/servico.py` → `rodar()`: o motor chamado por painel, bandeja e agendador. Cuida de trava, log em arquivo e `estado.json`.
- `robo/processador.py` → `processar()`: as regras (duplicidade, status, exceções, anexos). Recebe e-mails de `robo/fontes.py` (pasta ou IMAP).
- `robo/extratores.py`: todo extrator devolve **o mesmo dicionário** (`_conta()`). Um extrator novo só precisa respeitar esse contrato.
- `robo/planilha.py`: a planilha é a **memória** do robô (idempotência). A tabela começa abaixo de um painel de resumo; `ler_contas()` acha a linha de títulos por `"Status"` + `"Chave"`.
- `robo/config.py`: caminhos por modo (código-fonte = pasta do projeto; `.exe` = `%APPDATA%` e Documentos), `.env` e cofre de senhas (`keyring`).
- `robo/painel.py` (tkinter), `robo/bandeja.py` (pystray), `robo/sistema.py` (registro Run + Agendador de Tarefas), `robo/cli.py` (execução sem tela).

## Regras do projeto

- Código, nomes e mensagens em **português**; linhas até 79 colunas.
- Chave de duplicidade: NF-e = CNPJ + número; boleto = linha digitável; corpo = remetente + nº da fatura. Corpo do e-mail só é lido se não houver anexo de cobrança.
- `NaoECobranca` → log `IGNORADO`; `ErroExtracao` → aba **Exceções**. Nunca deixar um e-mail derrubar a execução.
- Senhas (`IMAP_SENHA`, `SMTP_SENHA`, `WHATSAPP_APIKEY`) vão para o cofre do Windows, nunca para o `.env` nem para o código.
- Dependências: manter `requirements.txt` (usado pelos `.bat` e pelo build) em sincronia com `pyproject.toml`.
- Ao mudar código que vai para o usuário, gerar o instalador de novo antes de distribuir e registrar no `CHANGELOG.md`.
- Versão: **só** em `robo/__init__.py` (`__version__`). O `pyproject.toml` lê de lá, o `build.ps1` passa para o `.iss` (`/DVersao`, `/DBuild`) e o painel mostra no título. O instalador sai como `Setup_RoboContas_<versão>_<AAAAMMDD-HHMM>.exe`.

## Armadilhas conhecidas

- **Testes e scripts nunca podem tocar dados reais**: defina `ROBO_DADOS` (pasta isolada) *antes* de importar `robo`, e troque `config.SERVICO_COFRE` para um nome de teste; `config.salvar()` apaga do cofre as senhas vazias. Veja `tests/conftest.py`.
- `.env` pode vir com BOM (Bloco de Notas): ler sempre com `utf-8-sig`.
- `instalador/RoboContas.iss` precisa ser **UTF-8 com BOM**, senão o Inno Setup estraga os acentos.
- `.bat` em ASCII e CRLF (garantido pelo `.gitattributes`).
- Planilha aberta no Excel bloqueia a gravação. `robo/excel.py` detecta isso **antes** de escanear: painel e ícone perguntam se podem salvar e fechar (via COM/PowerShell, achando a janela do Excel pela acessibilidade, porque `GetActiveObject` falha logo após o Excel abrir); o agendador nunca fecha a planilha do usuário, só registra e sai com `PlanilhaBloqueada`.
- No PowerShell 5.1, passe mensagens de commit por arquivo (`git commit -F`), não por here-string.
- Pelo código-fonte a data de referência fica fixa em 2026-09-20 (reprodutível); instalado, o padrão é "hoje".
