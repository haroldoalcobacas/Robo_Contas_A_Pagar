---
name: testar
description: Roda os testes automáticos e a varredura da base de exemplo e confere o gabarito do desafio (9 contas, R$ 8.631,75). Use após qualquer mudança em robo/ ou quando o usuário pedir para testar o robô.
---

# Testar o robô

1. Rode os testes:
   ```
   python -m pytest
   ```
   Todos devem passar. Se algum falhar, investigue a causa no código; não altere o teste nem o gabarito para fazê-lo passar.

2. Rode uma varredura real da base de exemplo, sem enviar relatório:
   ```
   python main.py --executar --sem-relatorio
   ```
   Confira no resumo final: **9 contas em aberto, Total a pagar: R$ 8.631,75, Duplicidades: 1, Exceções: 1, Ignorados: 3**.
   Se aparecer "feche a planilha no Excel", peça ao usuário para fechar `saida/contas_a_pagar.xlsx`.

3. Relate ao usuário: quantos testes passaram, o resumo da varredura e qualquer diferença em relação ao esperado, com o trecho do log (`logs/robo.log`).
