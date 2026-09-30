# Robô de Contas a Pagar

**Da caixa de entrada à planilha, sem ninguém abrir anexo.**

Robô em Python que lê uma caixa de e-mails, identifica as cobranças (NF-e em XML e faturas em PDF), extrai os dados, descarta duplicidades, marca o que está vencido e gera uma planilha de contas a pagar.

> Projeto do Desafio RPA #01. Status: **Nível 2 concluído**. 100% Python, sem n8n.

## O problema

Toda semana alguém abre a caixa de entrada, procura o que é cobrança no meio de newsletters e conversas, baixa o XML ou o PDF, copia fornecedor, CNPJ, valor e vencimento para uma planilha e confere se a nota já não foi lançada. É repetitivo, baseado em regras e sujeito a erro: exatamente o tipo de tarefa que RPA resolve.

## O que o robô faz

1. Lê todos os e-mails `.eml` da pasta de entrada.
2. Extrai os dados das **NF-e em XML** e das **faturas/boletos em PDF**.
3. Descarta **duplicidades** (reenvios, "RE:").
4. Calcula o **status** de cada conta: `VENCIDA`, `VENCE EM ATÉ 7 DIAS` ou `EM DIA`.
5. Grava a planilha com as abas **Resumo**, **Contas a Pagar**, **Exceções** e **Log**.
6. Registra o destino de **cada** e-mail: `OK`, `JÁ LANÇADA`, `DUPLICADA`, `IGNORADO` ou `EXCEÇÃO`.

```
[OK        ] 08_Sua_fatura_chegou_vencimento_19_09.eml: Energia Paulista S.A. - Ref. 09/2026 - R$ 742,18
[DUPLICADA ] 07_RE_NF_e_1037_Papelaria_Central_ME.eml: Papelaria Central ME - NF-e 1037 - R$ 213,47 (reenvio da mesma cobrança)
[IGNORADO  ] 13_Poltica_de_frias_atualizada.eml: politica_ferias.pdf: PDF sem valor e vencimento
[EXCEÇÃO   ] 14_NF_e_1111_Contabilidade_Silva_Filhos.eml: XML inválido/corrompido

8 contas na planilha | Total a pagar: R$ 8.282,75
Novas: 8 | Já lançadas: 0 | Duplicidades: 1 | Exceções: 1 | Ignorados: 4
  VENCIDA: 3 (R$ 3.082,08)
  VENCE EM ATÉ 7 DIAS: 2 (R$ 1.413,47)
  EM DIA: 3 (R$ 3.787,20)
```

## Como rodar

Requisitos: Python 3.10 ou mais recente.

```bash
pip install -r requirements.txt
```

**Com tela (recomendado):**

```bash
python app.py
```

Para testar com os e-mails de exemplo, basta clicar em **Executar robô**. Nenhuma configuração é necessária: por padrão o robô lê a pasta `dados/caixa_de_entrada` e os relatórios ficam desligados.

**Sem tela** (terminal ou Agendador de Tarefas), usando o que estiver no `.env`:

```bash
python executar.py
```

A planilha é gerada em `saida/contas_a_pagar.xlsx`. Se ela estiver aberta no Excel, feche antes de rodar.

## A tela

| Aba | O que tem |
|---|---|
| **Executar** | Pasta dos e-mails, pasta de saída, nome da planilha, data de referência (fixa ou "hoje"), botão de execução, log ao vivo e resumo |
| **Leitura de e-mail** | Origem (pasta local ou caixa IMAP), servidor, porta, usuário, senha e botão **Testar conexão** |
| **Relatório** | Envio por e-mail e/ou WhatsApp, frequência (diário, semanal ou mensal), dados SMTP com **Testar conexão** e dados do WhatsApp (CallMeBot) |

Os campos de e-mail e WhatsApp só ficam ativos, e só são exigidos, quando a opção correspondente é marcada. **Salvar configurações** grava tudo no `.env`, que não vai para o Git.

## Configuração

O modelo com todas as chaves está em [`.env.example`](.env.example).

| Variável | Padrão | Para que serve |
|---|---|---|
| `PASTA_EMAILS` | `dados/caixa_de_entrada` | Pasta com os `.eml` |
| `PASTA_SAIDA` | `saida` | Onde a planilha é gravada |
| `NOME_PLANILHA` | `contas_a_pagar.xlsx` | Nome da planilha |
| `DATA_REFERENCIA` | `2026-09-20` | Data dos alertas. Vazio = hoje |
| `ORIGEM_EMAILS` | `pasta` | `pasta` ou `imap` |
| `IMAP_*` | Gmail | Caixa real (Nível 3) |
| `RELATORIO_EMAIL`, `RELATORIO_WHATSAPP` | `nao` | Canais do relatório |
| `RELATORIO_FREQUENCIA` | `diario` | `diario`, `semanal` ou `mensal` |
| `SMTP_*`, `EMAIL_DESTINATARIOS` | Gmail | Envio por e-mail |
| `WHATSAPP_NUMERO`, `WHATSAPP_APIKEY` | vazio | Envio pelo CallMeBot |

No Gmail, use uma **senha de app** (Conta Google > Segurança > Senhas de app), nunca a senha normal da conta.

## Decisões tomadas

**Chave de duplicidade depende do tipo de cobrança.**
- NF-e: **CNPJ do emissor + número da nota**. Número de nota só é único dentro do mesmo emissor: nos dados há duas "NF-e 1111" de empresas diferentes. Valor também não serve: a Nuvem Hosting enviou duas notas de R$ 489,90, uma para cada mês.
- Boleto em PDF: a **linha digitável**, que é única por boleto. Sem ela, CNPJ + vencimento + valor.

**Idempotência: a planilha é a memória do robô.**
Antes de processar, o robô lê as chaves já gravadas na aba *Contas a Pagar*. Contas que já estão lá aparecem como `JÁ LANÇADA` e não são repetidas. Rodar duas vezes seguidas dá a mesma planilha. O status é recalculado para todas as contas a cada execução, porque uma conta "em dia" hoje pode estar vencida amanhã.

**Dois tipos de "não deu", tratados de forma diferente.**
- *Não é cobrança* (PDF da política de férias, newsletter): vai para o log como `IGNORADO`.
- *Parece cobrança, mas não deu para ler* (XML corrompido, PDF sem vencimento): vai para a aba **Exceções**, porque alguém precisa olhar.

**Um arquivo com problema não derruba o robô.**
Cada e-mail é processado dentro de um `try/except`, com uma rede de segurança final para erros inesperados.

**Tolerância a `&` sem escape.**
Um fornecedor enviou o XML com `Silva & Filhos`, o que é XML inválido. Em vez de rejeitar a nota (R$ 1.850,00 a menos), o robô escapa esse `&` antes de ler o arquivo.

**PDF é lido por padrões de texto.**
XML tem tags fixas; PDF é texto posicionado para humanos. O robô extrai o texto com `pypdf` e busca "Vencimento:", "Valor do documento: R$", "Linha digitável:" e "CNPJ:" com expressões regulares, convertendo o valor do formato brasileiro (`1.200,00`). Como PDFs simples costumam perder acentos, o nome do fornecedor usa a grafia do remetente do e-mail quando os dois batem.

**Tipos corretos na planilha.**
Valores são gravados como número e datas como data. O total é uma fórmula `=SUM`, e o status tem cor (vermelho, amarelo, verde).

**Credenciais fora do código.**
Tudo fica no `.env`, ignorado pelo Git. A tela lê e grava esse arquivo.

## Gabarito

| Nível | Contas | Total | Resultado do robô |
|---|---|---|---|
| 1 (só XML) | 6 | R$ 6.340,57 | ✅ |
| 2 (XML + PDF) | 8 | R$ 8.282,75 | ✅ 1 duplicidade, 1 exceção |

## Roteiro

- [x] **Nível 1:** NF-e em XML, planilha, ignorar o que não é cobrança
- [x] **Nível 2:** faturas em PDF, duplicidade, exceções, status, idempotência
- [x] Tela de configurações com teste de conexão IMAP e SMTP
- [ ] **Nível 3:** cobrança no corpo do e-mail, leitura da caixa real via IMAP, relatório consolidado por e-mail/WhatsApp, agendamento, anexos em `anexos/<fornecedor>/<ano-mes>/`, validação de CNPJ

## Estrutura

```
.
├── app.py                   # tela de abertura e configurações
├── executar.py              # execução sem tela (terminal/agendador)
├── robo/
│   ├── config.py            # leitura e gravação do .env
│   ├── extratores.py        # NF-e (XML) e fatura (PDF)
│   ├── processador.py       # regras: duplicidade, status, exceções, log
│   ├── planilha.py          # leitura (memória) e gravação do .xlsx
│   └── conexoes.py          # testes de login IMAP e SMTP
├── robo_nivel1.py           # versão do Nível 1, mantida como referência
├── requirements.txt
├── .env.example             # modelo de configuração
├── dados/
│   ├── gerar_dados.py       # gera os e-mails de exemplo
│   └── caixa_de_entrada/    # 14 e-mails .eml
└── saida/                   # planilha gerada (fora do Git)
```
