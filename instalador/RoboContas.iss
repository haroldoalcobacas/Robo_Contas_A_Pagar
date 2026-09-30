; Instalador do Robô de Contas a Pagar (Inno Setup 6)
; Compilar:  instalador\build.ps1   (ou ISCC.exe instalador\RoboContas.iss)
;
; Instala só para o usuário atual: não pede senha de administrador.

#define Nome "Robô de Contas a Pagar"
#define Versao "1.0.0"
#define Exe "RoboContas.exe"

[Setup]
AppId={{5B7E3C1A-9D2F-4E8B-A6C4-2F1D8E0B7C93}
AppName={#Nome}
AppVersion={#Versao}
AppPublisher=Haroldo Alcobaças
DefaultDirName={localappdata}\Programs\RoboContas
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=saida
OutputBaseFilename=Setup_RoboContas_{#Versao}
SetupIconFile=robo.ico
UninstallDisplayIcon={app}\{#Exe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na área de trabalho"
Name: "iniciar"; Description: "Mostrar o ícone do robô ao iniciar o Windows"
Name: "agendar"; Description: "Escanear sozinho ao ligar o PC e todo dia às 08:00"

[Files]
Source: "dist\RoboContas\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Nome}"; Filename: "{app}\{#Exe}"
Name: "{autoprograms}\{#Nome} - Painel"; Filename: "{app}\{#Exe}"; Parameters: "--config"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\{#Exe}"; Tasks: atalho

[Run]
; O próprio programa cria o registro de início e a tarefa agendada,
; do mesmo jeito que a aba "Automação" do painel.
Filename: "{app}\{#Exe}"; Parameters: "--inicio sim"; Tasks: iniciar; Flags: runhidden waituntilterminated
Filename: "{app}\{#Exe}"; Parameters: "--agendar 08:00"; Tasks: agendar; Flags: runhidden waituntilterminated
Filename: "{app}\{#Exe}"; Parameters: "--config"; Description: "Abrir o painel para configurar agora"; Flags: postinstall nowait skipifsilent
Filename: "{app}\{#Exe}"; Description: "Iniciar o ícone do robô"; Flags: postinstall nowait skipifsilent unchecked

[UninstallRun]
; 1º fecha o ícone da bandeja, que prende os arquivos
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#Exe} /F"; Flags: runhidden waituntilterminated; RunOnceId: "fechar"
Filename: "{app}\{#Exe}"; Parameters: "--desagendar"; Flags: runhidden waituntilterminated; RunOnceId: "desagendar"
Filename: "{app}\{#Exe}"; Parameters: "--inicio nao"; Flags: runhidden waituntilterminated; RunOnceId: "inicio"

; Configuração (%APPDATA%\RoboContasAPagar) e planilhas (Documentos) são
; dados do usuário e ficam no computador após a desinstalação.
