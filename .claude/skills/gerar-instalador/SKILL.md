---
name: gerar-instalador
description: Gera o RoboContas.exe (PyInstaller) e o Setup_RoboContas_x.y.z.exe (Inno Setup) com o código atual, após testar. Use quando o usuário quiser distribuir, instalar ou atualizar o instalador.
---

# Gerar o instalador

1. Rode a skill `testar` primeiro. Não gere instalador com teste falhando.
2. Se houve mudança relevante para o usuário desde a última versão:
   - aumente `__version__` em `robo/__init__.py`, o **único** lugar da versão (pyproject, instalador e painel leem de lá);
   - registre a mudança no topo do `CHANGELOG.md`.
   - Não edite a versão no `.iss`: o `build.ps1` a passa por `/DVersao`. O `.iss` precisa continuar **UTF-8 com BOM**.
3. Gere:
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File instalador\build.ps1
   ```
   Se o Inno Setup faltar: `winget install JRSoftware.InnoSetup --scope user`.
4. Valide o executável sem instalar e sem tocar dados reais, usando uma pasta isolada:
   - defina `ROBO_DADOS` para uma pasta temporária com um `.env` contendo `PASTA_SAIDA=<pasta temporária>\saida` e `DATA_REFERENCIA=2026-09-20`;
   - rode `instalador\dist\RoboContas\RoboContas.exe --executar` e confira em `<pasta>\logs\robo.log`: 9 contas, R$ 8.631,75.
5. Informe ao usuário o caminho do instalador. O nome sai automático, `instalador\saida\Setup_RoboContas_<versão>_<AAAAMMDD-HHMM>.exe`, e o `build.ps1` imprime o caminho no final. Informe também o tamanho e a versão.
