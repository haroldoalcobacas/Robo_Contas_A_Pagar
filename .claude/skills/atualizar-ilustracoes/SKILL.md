---
name: atualizar-ilustracoes
description: Recaptura as imagens da documentação (painel, planilha, e-mail do relatório, ícones) rodando o robô com a base de exemplo. Use quando a interface, a planilha ou o relatório mudarem.
---

# Atualizar as ilustrações

1. Rode:
   ```
   python docs/gerar_ilustracoes.py
   ```
   O script usa uma pasta isolada (`C:\Users\Public\RoboContas_docs`) e um cofre de senhas separado: não mexe em `.env`, planilha, log nem senhas reais, e as imagens não mostram o nome de usuário.
2. Precisa de Excel (planilha) e Microsoft Edge (e-mail do relatório). Se faltar algum, o script avisa e pula aquela imagem.
3. Abra 2 ou 3 imagens de `docs/img/` para conferir o resultado antes de concluir.
4. Se textos ou valores mudaram, atualize também os trechos correspondentes em `README.md` e `docs/COMO_USAR.md` (o exemplo de WhatsApp está em `docs/exemplos/relatorio_whatsapp.txt`).
