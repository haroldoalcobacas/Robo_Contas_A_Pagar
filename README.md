# Robô de Contas a Pagar

**Da caixa de entrada à planilha, sem ninguém abrir anexo.**

Robô em Python que lê uma caixa de e-mails, identifica as notas fiscais, extrai os dados, descarta duplicidades e gera uma planilha de contas a pagar.

> Projeto do Desafio RPA #01. Status: **Nível 1 concluído** (NF-e em XML).

## O problema

Toda semana alguém abre a caixa de entrada, procura o que é cobrança no meio de newsletters e conversas, baixa o XML da nota, copia fornecedor, CNPJ, valor e vencimento para uma planilha e confere se a nota já não foi lançada. É repetitivo, baseado em regras e sujeito a erro: exatamente o tipo de tarefa que RPA resolve.

## O que o robô faz

1. Lê todos os e-mails `.eml` da pasta de entrada.
2. Procura anexos de **NF-e em XML**.
3. Extrai fornecedor, CNPJ, número da nota, data de emissão, valor total e vencimento.
4. Descarta notas já lançadas (reenvios, "RE:").
5. Gera `contas_a_pagar.xlsx`, ordenada por vencimento e com linha de total.
6. Registra no terminal o destino de **cada** e-mail:

```
[OK]        01_NF_e_1000_Nuvem_Hosting_Ltda.eml: NF 1000 - Nuvem Hosting Ltda - R$ 489.90
[DUPLICADA] 07_RE_NF_e_1037_Papelaria_Central_ME.eml: NF 1037 de Papelaria Central ME já lançada
[IGNORADO]  12_Almoo_sexta.eml: sem NF-e em XML
[ERRO]      14_NF_e_1111_Contabilidade_Silva_Filhos.eml / NFe_1111.xml: XML inválido/corrompido

6 contas lançadas | Total a pagar: R$ 6.340,57
```

## Como rodar

Requisitos: Python 3.10 ou mais recente.

```bash
pip install openpyxl
cp .env.example .env        # no Windows: copy .env.example .env
python robo_nivel1.py
```

A planilha `contas_a_pagar.xlsx` é gerada na raiz do projeto. Se ela estiver aberta no Excel, feche antes de rodar.

## Configuração

Tudo que pode mudar fica no arquivo `.env`, que não vai para o Git. O modelo está em [`.env.example`](.env.example).

| Variável | Padrão | Para que serve |
|---|---|---|
| `PASTA_EMAILS` | `dados/caixa_de_entrada` | Pasta com os `.eml` |
| `ARQUIVO_SAIDA` | `contas_a_pagar.xlsx` | Planilha gerada |
| `DATA_REFERENCIA` | `2026-09-20` | Data fixa para os alertas, para o resultado ser reprodutível |
| `IMAP_*`, `TELEGRAM_*` | vazio | Reservadas para o Nível 3 |

## Dados de exemplo

A pasta [`dados/caixa_de_entrada/`](dados/caixa_de_entrada/) tem 14 e-mails simulando setembro/2026: NF-e em XML, faturas em PDF, cobrança só no corpo do e-mail, e-mails que não são cobrança e algumas armadilhas. O script [`dados/gerar_dados.py`](dados/gerar_dados.py) regenera os arquivos.

## Decisões tomadas

**Chave de duplicidade = CNPJ do emissor + número da nota.**
Número de nota só é único dentro do mesmo emissor: nos dados há duas "NF-e 1111" de empresas diferentes. Valor também não serve: a Nuvem Hosting enviou duas notas de R$ 489,90, uma para cada mês.

**Tolerância a `&` sem escape.**
Um fornecedor enviou o XML com `Silva & Filhos`, o que é XML inválido. Em vez de rejeitar a nota (R$ 1.850,00 a menos no total), o robô escapa esse `&` antes de ler o arquivo. Os `&` que já estavam corretos ficam como estão.

**Um arquivo com problema não derruba o robô.**
Cada e-mail é processado dentro de um `try/except`. Um XML corrompido vira uma linha de `[ERRO]` no log e o robô segue para o próximo.

**Nenhum e-mail some sem explicação.**
Todo e-mail termina como `OK`, `DUPLICADA`, `IGNORADO` ou `ERRO`.

**Tipos corretos na planilha.**
Valores são gravados como número e datas como data, com formatação `R$` e `DD/MM/AAAA`. O total é uma fórmula `=SUM`, então continua certo se alguém editar um valor.

**Data de referência fixa.**
Usar a data de hoje faria o resultado mudar a cada dia e impediria conferir com o gabarito.

**Por que Python?**
O coração do problema é extrair dados e aplicar regras, e em Python isso é código testável e versionável. O n8n entra no Nível 3, na orquestração: gatilho de e-mail, agendamento e envio do resumo.

## Roteiro

- [x] **Nível 1:** NF-e em XML, planilha, ignorar o que não é cobrança
- [ ] **Nível 2:** faturas em PDF, aba de exceções, status (`VENCIDA`, `VENCE EM ATÉ 7 DIAS`, `EM DIA`), idempotência
- [ ] **Nível 3:** cobrança no corpo do e-mail, caixa real via IMAP, resumo no Telegram, agendamento, anexos organizados, validação de CNPJ

## Estrutura

```
.
├── robo_nivel1.py           # o robô
├── .env.example             # modelo de configuração
├── dados/
│   ├── gerar_dados.py       # gera os e-mails de exemplo
│   └── caixa_de_entrada/    # 14 e-mails .eml
└── contas_a_pagar.xlsx      # saída (gerada, fora do Git)
```
