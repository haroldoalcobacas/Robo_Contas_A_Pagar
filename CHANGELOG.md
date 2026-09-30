# Changelog

Mudanças relevantes para quem usa o robô. Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- Antes de escanear, o robô verifica se a planilha está aberta no Excel. No painel e no ícone, pergunta se deve **salvar e fechar** a planilha (suas alterações são mantidas) ou se você prefere fechá-la. Na execução agendada, não fecha nada: registra no log e não processa.
- Testes automáticos (`python -m pytest`) que garantem o gabarito dos 3 níveis, a idempotência e as regras principais.
- `CLAUDE.md` e skills do Claude Code em `.claude/skills/` (testar, gerar instalador, atualizar ilustrações).
- `pyproject.toml` com metadados, dependências e configuração de testes.

### Alterado
- Versão num único lugar (`robo/__init__.py`), exibida no título do painel. O instalador sai com nome automático, com versão, data e hora (`Setup_RoboContas_1.0.0_20260930-1510.exe`), e o `Instalar.bat` abre sempre o mais recente.
- Um único ponto de entrada: `main.py`. O painel foi para `robo/painel.py` e a execução sem tela para `robo/cli.py`.
  `python executar.py` passa a ser `python main.py --executar` (com `--sem-relatorio` para só varrer).
- Guia de uso movido para `docs/COMO_USAR.md`.
- A versão do Nível 1 fica em `historico/`.

### Corrigido
- `dados/gerar_dados.py` gravava num caminho fixo de outro computador; agora grava ao lado do script.

## [1.0.0] - 2026-09-30

### Adicionado
- Leitura de NF-e em XML, faturas em PDF e cobranças no corpo do e-mail.
- Duplicidade por tipo de cobrança, status (vencida, vence em 7 dias, em dia, paga), aba de exceções e log.
- Planilha com painel de resumo, abas Resumo, Exceções e Log; coluna "Pago em".
- Leitura da caixa real via IMAP (somente leitura); anexos em `anexos/<fornecedor>/<ano-mês>/`; validação de CNPJ.
- Relatório diário, semanal ou mensal por e-mail e WhatsApp (CallMeBot).
- Painel com 4 abas, ícone na bandeja, início com o Windows e varredura pelo Agendador de Tarefas.
- Senhas no Gerenciador de Credenciais do Windows.
- Instalador para Windows sem administrador (`Setup_RoboContas_1.0.0.exe`).
