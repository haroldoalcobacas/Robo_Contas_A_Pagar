"""
Painel do Robô de Contas a Pagar.

Quatro abas:
- Executar: pastas de entrada/saída, data de referência e botão de execução.
- Leitura de e-mail: origem (pasta ou IMAP) e credenciais da caixa.
- Relatório: envio por e-mail e/ou WhatsApp, frequência e envio imediato.
- Automação: ícone ao iniciar o Windows e varredura agendada.

Configurações vão para o .env; senhas, para o Gerenciador de Credenciais.

Uso:
    python app.py       (ou main.py --config)
"""

import os
import queue
import threading
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from robo import config, servico, sistema
from robo.conexoes import testar_imap, testar_smtp
from robo.planilha import PlanilhaBloqueada
from robo.processador import brl

FORMATO_DATA = "%d/%m/%Y"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Robô de Contas a Pagar")
        self.geometry("920x700")
        self.minsize(800, 600)
        self._icone_janela()

        cfg = config.carregar()
        # Uma variável de tela para cada chave do .env
        self.v = {k: tk.StringVar(value=cfg.get(k, ""))
                  for k in config.PADROES}

        data_iso = cfg.get("DATA_REFERENCIA", "").strip()
        self.var_hoje = tk.BooleanVar(value=not data_iso)
        self.var_data = tk.StringVar(
            value=(date.fromisoformat(data_iso).strftime(FORMATO_DATA)
                   if data_iso else date.today().strftime(FORMATO_DATA)))
        self.var_rel_email = tk.BooleanVar(
            value=cfg["RELATORIO_EMAIL"] == "sim")
        self.var_rel_whats = tk.BooleanVar(
            value=cfg["RELATORIO_WHATSAPP"] == "sim")
        self.var_anexos = tk.BooleanVar(value=cfg["SALVAR_ANEXOS"] == "sim")
        self.var_inicio = tk.BooleanVar(
            value=sistema.inicio_automatico_ativo())
        self.var_agenda = tk.BooleanVar(value=sistema.agendamento_ativo())

        # Comunicação entre as threads de trabalho e a tela
        self.fila: queue.Queue = queue.Queue()
        self.executando = False

        self._estilos()
        self._montar()
        self.after(100, self._ler_fila)

    def _icone_janela(self) -> None:
        try:
            from PIL import ImageTk
            from robo.bandeja import desenhar_icone
            self._img_icone = ImageTk.PhotoImage(desenhar_icone("verde", 64))
            self.iconphoto(True, self._img_icone)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Montagem da tela
    # ------------------------------------------------------------------
    def _estilos(self) -> None:
        estilo = ttk.Style(self)
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 16, "bold"))
        estilo.configure("Sub.TLabel", foreground="#555")
        estilo.configure("Dica.TLabel", foreground="#666",
                         font=("Segoe UI", 8))
        estilo.configure("Destaque.TButton", font=("Segoe UI", 10, "bold"))
        estilo.configure("Resumo.TLabel", font=("Segoe UI", 10, "bold"))

    def _montar(self) -> None:
        topo = ttk.Frame(self, padding=(16, 12, 16, 4))
        topo.pack(fill="x")
        ttk.Label(topo, text="Robô de Contas a Pagar",
                  style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(topo, style="Sub.TLabel",
                  text="Da caixa de entrada à planilha, sem abrir anexo."
                  ).pack(anchor="w")

        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, padx=16, pady=8)
        abas.add(self._aba_executar(abas), text="  Executar  ")
        abas.add(self._aba_leitura(abas), text="  Leitura de e-mail  ")
        abas.add(self._aba_relatorio(abas), text="  Relatório  ")
        abas.add(self._aba_automacao(abas), text="  Automação  ")

        rodape = ttk.Frame(self, padding=(16, 0, 16, 12))
        rodape.pack(fill="x")
        self.lbl_status = ttk.Label(rodape, style="Sub.TLabel",
                                    text=f"Configuração: {config.ARQUIVO_ENV}")
        self.lbl_status.pack(side="left")
        ttk.Button(rodape, text="Salvar configurações",
                   command=self.salvar).pack(side="right")

    def _campo(self, pai, linha, rotulo, chave=None, var=None,
               largura=42, senha=False, dica=None):
        """Rótulo + caixa de texto numa linha do grid. Devolve a Entry."""
        ttk.Label(pai, text=rotulo).grid(row=linha, column=0, sticky="w",
                                         padx=(0, 8), pady=3)
        entrada = ttk.Entry(pai, textvariable=var or self.v[chave],
                            width=largura, show="•" if senha else "")
        entrada.grid(row=linha, column=1, sticky="we", pady=3)
        if dica:
            ttk.Label(pai, text=dica, style="Dica.TLabel").grid(
                row=linha, column=2, sticky="w", padx=8)
        return entrada

    def _botao_pasta(self, pai, linha, chave) -> None:
        def escolher():
            atual = config.caminho(self._cfg_da_tela(), chave)
            pasta = filedialog.askdirectory(
                initialdir=atual if atual.exists() else config.DADOS_APP)
            if pasta:
                self.v[chave].set(self._relativo(Path(pasta)))
        ttk.Button(pai, text="Procurar...", command=escolher).grid(
            row=linha, column=2, padx=8)

    # --- Aba 1: Executar ----------------------------------------------
    def _aba_executar(self, pai) -> ttk.Frame:
        aba = ttk.Frame(pai, padding=12)

        arquivos = ttk.LabelFrame(aba, text="Arquivos", padding=10)
        arquivos.pack(fill="x")
        arquivos.columnconfigure(1, weight=1)
        self._campo(arquivos, 0, "Pasta dos e-mails (.eml)", "PASTA_EMAILS")
        self._botao_pasta(arquivos, 0, "PASTA_EMAILS")
        self._campo(arquivos, 1, "Pasta de saída", "PASTA_SAIDA")
        self._botao_pasta(arquivos, 1, "PASTA_SAIDA")
        self._campo(arquivos, 2, "Nome da planilha", "NOME_PLANILHA")
        ttk.Checkbutton(
            arquivos, variable=self.var_anexos,
            text="Guardar os anexos em <saída>/anexos/<fornecedor>/<ano-mês>"
        ).grid(row=3, column=1, sticky="w", pady=(4, 0))

        data = ttk.LabelFrame(aba, text="Data de referência para os alertas",
                              padding=10)
        data.pack(fill="x", pady=8)
        self.ent_data = ttk.Entry(data, textvariable=self.var_data, width=12)
        self.ent_data.pack(side="left")
        ttk.Label(data, text="DD/MM/AAAA", style="Dica.TLabel").pack(
            side="left", padx=(6, 16))
        ttk.Checkbutton(data, text="Usar a data de hoje",
                        variable=self.var_hoje,
                        command=self._alternar_data).pack(side="left")
        self._alternar_data()

        botoes = ttk.Frame(aba)
        botoes.pack(fill="x", pady=(0, 8))
        self.btn_executar = ttk.Button(botoes, text="▶  Escanear agora",
                                       style="Destaque.TButton",
                                       command=self.executar)
        self.btn_executar.pack(side="left", ipadx=10, ipady=3)
        ttk.Button(botoes, text="Abrir planilha",
                   command=self.abrir_planilha).pack(side="left", padx=8)
        ttk.Button(botoes, text="Abrir pasta de saída",
                   command=self.abrir_pasta_saida).pack(side="left")

        self.lbl_resumo = ttk.Label(aba, text="", style="Resumo.TLabel")
        self.lbl_resumo.pack(anchor="w", pady=(0, 4))

        self.txt_log = scrolledtext.ScrolledText(
            aba, height=14, font=("Consolas", 9), state="disabled",
            wrap="none")
        self.txt_log.pack(fill="both", expand=True)
        return aba

    # --- Aba 2: Leitura de e-mail -------------------------------------
    def _aba_leitura(self, pai) -> ttk.Frame:
        aba = ttk.Frame(pai, padding=12)

        origem = ttk.LabelFrame(aba, text="De onde ler os e-mails",
                                padding=10)
        origem.pack(fill="x")
        for texto, valor in [("Pasta local com arquivos .eml (testes)",
                              "pasta"),
                             ("Caixa de e-mail real (IMAP)", "imap")]:
            ttk.Radiobutton(origem, text=texto, value=valor,
                            variable=self.v["ORIGEM_EMAILS"],
                            command=self._alternar_imap).pack(anchor="w")

        self.frm_imap = ttk.LabelFrame(aba, text="Servidor IMAP", padding=10)
        self.frm_imap.pack(fill="x", pady=8)
        self.frm_imap.columnconfigure(1, weight=1)
        f = self.frm_imap
        self._campo(f, 0, "Servidor", "IMAP_HOST",
                    dica="Gmail: imap.gmail.com")
        self._campo(f, 1, "Porta", "IMAP_PORTA", largura=8, dica="993 (SSL)")
        self._campo(f, 2, "Usuário (e-mail)", "IMAP_USUARIO")
        ent_senha = self._campo(f, 3, "Senha", "IMAP_SENHA", senha=True)
        self._mostrar_senha(f, 3, ent_senha)
        self._campo(f, 4, "Pasta da caixa", "IMAP_PASTA", largura=20,
                    dica="INBOX = caixa de entrada")
        self._campo(f, 5, "Ler os últimos", "IMAP_DIAS", largura=6,
                    dica="dias")
        ttk.Button(f, text="Testar conexão",
                   command=self.testar_imap).grid(row=6, column=1,
                                                  sticky="w", pady=(8, 0))

        ttk.Label(aba, style="Dica.TLabel", justify="left", text=(
            "Gmail: ative a verificação em duas etapas e gere uma "
            "\"senha de app\" (Conta Google > Segurança > Senhas de app).\n"
            "Use essa senha de 16 letras aqui, nunca a senha normal da "
            "conta.\n\nA caixa é lida em modo somente leitura: nada é "
            "apagado, movido ou marcado como lido."
        )).pack(anchor="w")
        self._alternar_imap()
        return aba

    # --- Aba 3: Relatório ---------------------------------------------
    def _aba_relatorio(self, pai) -> ttk.Frame:
        aba = ttk.Frame(pai, padding=12)

        linha = ttk.Frame(aba)
        linha.pack(fill="x")
        canal = ttk.LabelFrame(linha, text="Enviar relatório por",
                               padding=10)
        canal.pack(side="left", fill="both", expand=True)
        ttk.Checkbutton(canal, text="E-mail", variable=self.var_rel_email,
                        command=self._alternar_canais).pack(anchor="w")
        ttk.Checkbutton(canal, text="WhatsApp", variable=self.var_rel_whats,
                        command=self._alternar_canais).pack(anchor="w")

        freq = ttk.LabelFrame(linha, text="Frequência do consolidado",
                              padding=10)
        freq.pack(side="left", fill="both", expand=True, padx=(8, 0))
        for texto, valor in [("Diário", "diario"), ("Semanal", "semanal"),
                             ("Mensal", "mensal")]:
            ttk.Radiobutton(freq, text=texto, value=valor,
                            variable=self.v["RELATORIO_FREQUENCIA"]
                            ).pack(side="left", padx=(0, 12))

        self.frm_smtp = ttk.LabelFrame(aba, text="E-mail (SMTP)", padding=10)
        self.frm_smtp.pack(fill="x", pady=8)
        self.frm_smtp.columnconfigure(1, weight=1)
        f = self.frm_smtp
        self._campo(f, 0, "Servidor", "SMTP_HOST",
                    dica="Gmail: smtp.gmail.com")
        self._campo(f, 1, "Porta", "SMTP_PORTA", largura=8,
                    dica="587 (STARTTLS) ou 465 (SSL)")
        self._campo(f, 2, "Usuário (e-mail)", "SMTP_USUARIO")
        ent_senha = self._campo(f, 3, "Senha", "SMTP_SENHA", senha=True)
        self._mostrar_senha(f, 3, ent_senha)
        self._campo(f, 4, "Destinatários", "EMAIL_DESTINATARIOS",
                    dica="separados por vírgula")
        ttk.Button(f, text="Testar conexão",
                   command=self.testar_smtp).grid(row=5, column=1,
                                                  sticky="w", pady=(8, 0))

        self.frm_whats = ttk.LabelFrame(aba, text="WhatsApp (CallMeBot)",
                                        padding=10)
        self.frm_whats.pack(fill="x")
        self.frm_whats.columnconfigure(1, weight=1)
        f = self.frm_whats
        self._campo(f, 0, "Número com DDI", "WHATSAPP_NUMERO", largura=20,
                    dica="ex.: 5511999998888")
        ent_key = self._campo(f, 1, "API key", "WHATSAPP_APIKEY",
                              largura=20, senha=True)
        self._mostrar_senha(f, 1, ent_key)

        rodape = ttk.Frame(aba)
        rodape.pack(fill="x", pady=(8, 0))
        ttk.Label(rodape, style="Dica.TLabel", justify="left", text=(
            "CallMeBot é gratuito e envia mensagens para o seu próprio "
            "WhatsApp.\nA API key é obtida em callmebot.com. "
            "No envio automático, o relatório sai uma vez por dia/semana/mês."
        )).pack(side="left", anchor="w")
        self.btn_relatorio = ttk.Button(
            rodape, text="Gerar e enviar relatório agora",
            command=self.enviar_relatorio)
        self.btn_relatorio.pack(side="right")
        self._alternar_canais()
        return aba

    # --- Aba 4: Automação ---------------------------------------------
    def _aba_automacao(self, pai) -> ttk.Frame:
        aba = ttk.Frame(pai, padding=12)

        frm = ttk.LabelFrame(aba, text="Rodar sozinho", padding=10)
        frm.pack(fill="x")
        ttk.Checkbutton(
            frm, variable=self.var_inicio,
            text="Mostrar o ícone do robô ao lado do relógio quando o "
                 "Windows iniciar").grid(row=0, column=0, columnspan=3,
                                         sticky="w", pady=3)
        ttk.Checkbutton(
            frm, variable=self.var_agenda,
            text="Escanear sozinho ao ligar o computador e todo dia às"
        ).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=self.v["AGENDA_HORA"], width=6).grid(
            row=1, column=1, sticky="w", padx=4)
        ttk.Label(frm, text="HH:MM", style="Dica.TLabel").grid(
            row=1, column=2, sticky="w")
        ttk.Button(frm, text="Aplicar", command=self.aplicar_automacao).grid(
            row=2, column=0, sticky="w", pady=(10, 0))

        ttk.Label(aba, style="Dica.TLabel", justify="left", text=(
            "A varredura agendada usa o Agendador de Tarefas do Windows: "
            "funciona mesmo com este painel e o ícone fechados.\n"
            "Se o computador estiver desligado no horário, ela roda assim "
            "que ele ligar. O relatório é enviado quando estiver devido "
            "(conforme a frequência).\n\n"
            f"Log das execuções: {config.PASTA_LOGS / 'robo.log'}"
        )).pack(anchor="w", pady=8)
        return aba

    def _mostrar_senha(self, pai, linha, entrada) -> None:
        var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            pai, text="Mostrar", variable=var,
            command=lambda: entrada.config(show="" if var.get() else "•")
        ).grid(row=linha, column=2, sticky="w", padx=8)

    # ------------------------------------------------------------------
    # Habilitar / desabilitar campos
    # ------------------------------------------------------------------
    @staticmethod
    def _habilitar(frame, ligado: bool) -> None:
        for filho in frame.winfo_children():
            try:
                filho.state(["!disabled"] if ligado else ["disabled"])
            except (AttributeError, tk.TclError):
                pass

    def _alternar_data(self) -> None:
        if self.var_hoje.get():
            self.var_data.set(date.today().strftime(FORMATO_DATA))
            self.ent_data.state(["disabled"])
        else:
            self.ent_data.state(["!disabled"])

    def _alternar_imap(self) -> None:
        self._habilitar(self.frm_imap, self.v["ORIGEM_EMAILS"].get() == "imap")

    def _alternar_canais(self) -> None:
        self._habilitar(self.frm_smtp, self.var_rel_email.get())
        self._habilitar(self.frm_whats, self.var_rel_whats.get())

    # ------------------------------------------------------------------
    # Configuração
    # ------------------------------------------------------------------
    @staticmethod
    def _relativo(pasta: Path) -> str:
        """Guarda caminhos dentro da pasta de dados como relativos."""
        try:
            return pasta.resolve().relative_to(config.DADOS_APP).as_posix()
        except ValueError:
            return str(pasta)

    def _cfg_da_tela(self) -> dict[str, str]:
        cfg = {k: var.get().strip() for k, var in self.v.items()}
        # Senhas não levam strip: espaço pode fazer parte delas
        for k in config.SEGREDOS:
            cfg[k] = self.v[k].get()
        cfg["RELATORIO_EMAIL"] = "sim" if self.var_rel_email.get() else "nao"
        cfg["RELATORIO_WHATSAPP"] = "sim" if self.var_rel_whats.get() else "nao"
        cfg["SALVAR_ANEXOS"] = "sim" if self.var_anexos.get() else "nao"
        if self.var_hoje.get():
            cfg["DATA_REFERENCIA"] = ""
        else:
            try:
                cfg["DATA_REFERENCIA"] = datetime.strptime(
                    self.var_data.get().strip(), FORMATO_DATA
                ).date().isoformat()
            except ValueError:
                cfg["DATA_REFERENCIA"] = "invalida"
        return cfg

    def _erros_execucao(self, cfg: dict[str, str]) -> list[str]:
        erros = []
        if cfg["DATA_REFERENCIA"] == "invalida":
            erros.append("Data de referência inválida (use DD/MM/AAAA).")
        if not cfg["NOME_PLANILHA"].lower().endswith(".xlsx"):
            erros.append("O nome da planilha deve terminar em .xlsx.")
        for chave, nome in [("IMAP_PORTA", "Porta IMAP"),
                            ("IMAP_DIAS", "Dias de leitura")]:
            if cfg[chave] and not cfg[chave].isdigit():
                erros.append(f"{nome} deve ser um número.")
        if cfg["ORIGEM_EMAILS"] == "imap" and not (
                cfg["IMAP_HOST"] and cfg["IMAP_USUARIO"]
                and cfg["IMAP_SENHA"]):
            erros.append("Caixa IMAP: informe servidor, usuário e senha.")
        return erros

    def _erros_relatorio(self, cfg: dict[str, str]) -> list[str]:
        erros = []
        if cfg["SMTP_PORTA"] and not cfg["SMTP_PORTA"].isdigit():
            erros.append("Porta SMTP deve ser um número.")
        if cfg["RELATORIO_EMAIL"] == "sim" and not (
                cfg["SMTP_USUARIO"] and cfg["SMTP_SENHA"]
                and cfg["EMAIL_DESTINATARIOS"]):
            erros.append("E-mail: informe usuário, senha e destinatários.")
        if cfg["RELATORIO_WHATSAPP"] == "sim" and not (
                cfg["WHATSAPP_NUMERO"].isdigit() and cfg["WHATSAPP_APIKEY"]):
            erros.append("WhatsApp: informe o número (só dígitos, com DDI) "
                         "e a API key.")
        return erros

    def _hora_valida(self, hora: str) -> bool:
        try:
            datetime.strptime(hora, "%H:%M")
            return True
        except ValueError:
            return False

    def salvar(self) -> bool:
        cfg = self._cfg_da_tela()
        erros = self._erros_execucao(cfg) + self._erros_relatorio(cfg)
        if not self._hora_valida(cfg["AGENDA_HORA"]):
            erros.append("Horário da automação inválido (use HH:MM).")
        if erros:
            messagebox.showwarning("Verifique as configurações",
                                   "\n".join(erros))
            return False
        config.salvar(cfg)
        agora = datetime.now().strftime("%H:%M:%S")
        self.lbl_status.config(text=f"Configurações salvas às {agora}.")
        return True

    # ------------------------------------------------------------------
    # Execução do robô (em thread, para a tela não congelar)
    # ------------------------------------------------------------------
    def executar(self) -> None:
        cfg = self._cfg_da_tela()
        erros = self._erros_execucao(cfg)
        if erros:
            messagebox.showwarning("Não é possível executar", "\n".join(erros))
            return
        self._rodar(cfg, "Escaneando...", relatorio_modo="nao")

    def enviar_relatorio(self) -> None:
        cfg = self._cfg_da_tela()
        erros = self._erros_execucao(cfg) + self._erros_relatorio(cfg)
        if not (self.var_rel_email.get() or self.var_rel_whats.get()):
            erros.append("Marque e-mail e/ou WhatsApp.")
        if erros:
            messagebox.showwarning("Não é possível enviar", "\n".join(erros))
            return
        self._rodar(cfg, "Escaneando e enviando relatório...",
                    relatorio_modo="forcar",
                    frequencia=cfg["RELATORIO_FREQUENCIA"])

    def _rodar(self, cfg: dict, aviso: str, **kwargs) -> None:
        if self.executando:
            return
        self._limpar_log()
        self.executando = True
        self.btn_executar.state(["disabled"])
        self.btn_relatorio.state(["disabled"])
        self.lbl_resumo.config(text=aviso)

        def tarefa():
            try:
                execucao = servico.rodar(
                    cfg, log=lambda s: self.fila.put(("log", s)), **kwargs)
                self.fila.put(("fim", execucao))
            except servico.RoboOcupado:
                self.fila.put(("erro", "O robô já está em execução (pelo "
                               "ícone ou pelo agendador). Tente em "
                               "instantes."))
            except PlanilhaBloqueada:
                self.fila.put(("erro", "Não foi possível gravar a "
                               "planilha.\nFeche-a no Excel e rode de "
                               "novo."))
            except Exception as erro:
                servico.logger().exception("erro no painel")
                self.fila.put(("erro", f"{type(erro).__name__}: {erro}"))

        threading.Thread(target=tarefa, daemon=True).start()

    def _ler_fila(self) -> None:
        try:
            while True:
                tipo, *dados = self.fila.get_nowait()
                if tipo == "log":
                    self._escrever(dados[0])
                elif tipo == "fim":
                    self._fim_execucao(dados[0])
                elif tipo == "erro":
                    self._fim_execucao(None)
                    self.lbl_resumo.config(text="Execução interrompida.")
                    messagebox.showerror("Erro", dados[0])
                elif tipo == "teste":
                    titulo, ok, texto = dados
                    self.lbl_status.config(
                        text=f"{titulo}: {'ok' if ok else 'falhou'}.")
                    (messagebox.showinfo if ok else messagebox.showerror)(
                        titulo, texto)
        except queue.Empty:
            pass
        self.after(100, self._ler_fila)

    def _fim_execucao(self, execucao) -> None:
        self.executando = False
        self.btn_executar.state(["!disabled"])
        self.btn_relatorio.state(["!disabled"])
        if execucao is None:
            return
        res = execucao.resultado
        self.lbl_resumo.config(text=(
            f"{len(res.abertas)} em aberto  |  A pagar {brl(res.total)}  |  "
            f"{len(res.por_status('VENCIDA'))} vencidas  |  "
            f"{len(res.novas)} novas  |  {len(res.excecoes)} exceções"))
        if execucao.envios:
            titulo = ("Relatório com problemas" if execucao.houve_erro_envio
                      else "Relatório enviado")
            (messagebox.showwarning if execucao.houve_erro_envio
             else messagebox.showinfo)(titulo, "\n".join(execucao.envios))

    def _escrever(self, texto: str) -> None:
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", texto + "\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def _limpar_log(self) -> None:
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.config(state="disabled")

    def abrir_planilha(self) -> None:
        arquivo = config.arquivo_planilha(self._cfg_da_tela())
        if arquivo.exists():
            os.startfile(arquivo)
        else:
            messagebox.showinfo("Planilha", "A planilha ainda não foi "
                                "gerada. Clique em Escanear agora.")

    def abrir_pasta_saida(self) -> None:
        pasta = config.caminho(self._cfg_da_tela(), "PASTA_SAIDA")
        pasta.mkdir(parents=True, exist_ok=True)
        os.startfile(pasta)

    # ------------------------------------------------------------------
    # Automação (registro do Windows + Agendador de Tarefas)
    # ------------------------------------------------------------------
    def aplicar_automacao(self) -> None:
        hora = self.v["AGENDA_HORA"].get().strip()
        if self.var_agenda.get() and not self._hora_valida(hora):
            messagebox.showwarning("Automação", "Horário inválido "
                                   "(use HH:MM).")
            return
        try:
            sistema.definir_inicio_automatico(self.var_inicio.get())
            if self.var_agenda.get():
                sistema.agendar(hora)
            else:
                sistema.desagendar()
        except Exception as erro:
            messagebox.showerror("Automação", f"Não foi possível aplicar:"
                                 f"\n{erro}")
            return
        self.salvar()
        partes = [
            "Ícone ao iniciar o Windows: "
            + ("ligado" if sistema.inicio_automatico_ativo() else
               "desligado"),
            "Varredura agendada: "
            + (f"todo dia às {hora} e ao ligar o PC"
               if sistema.agendamento_ativo() else "desligada"),
        ]
        messagebox.showinfo("Automação", "\n".join(partes))

    # ------------------------------------------------------------------
    # Testes de conexão (em thread: podem demorar até o timeout)
    # ------------------------------------------------------------------
    def _testar(self, titulo: str, funcao, *args) -> None:
        self.lbl_status.config(text=f"{titulo}: testando...")

        def tarefa():
            try:
                self.fila.put(("teste", titulo, True, funcao(*args)))
            except Exception as erro:
                self.fila.put(("teste", titulo, False,
                               f"Falha na conexão:\n{erro}"))

        threading.Thread(target=tarefa, daemon=True).start()

    def testar_imap(self) -> None:
        c = self._cfg_da_tela()
        if not (c["IMAP_USUARIO"] and c["IMAP_SENHA"]
                and c["IMAP_PORTA"].isdigit()):
            messagebox.showwarning("IMAP", "Preencha servidor, porta, "
                                   "usuário e senha.")
            return
        self._testar("Teste IMAP", testar_imap, c["IMAP_HOST"],
                     int(c["IMAP_PORTA"]), c["IMAP_USUARIO"],
                     c["IMAP_SENHA"], c["IMAP_PASTA"] or "INBOX")

    def testar_smtp(self) -> None:
        c = self._cfg_da_tela()
        if not (c["SMTP_USUARIO"] and c["SMTP_SENHA"]
                and c["SMTP_PORTA"].isdigit()):
            messagebox.showwarning("SMTP", "Preencha servidor, porta, "
                                   "usuário e senha.")
            return
        self._testar("Teste SMTP", testar_smtp, c["SMTP_HOST"],
                     int(c["SMTP_PORTA"]), c["SMTP_USUARIO"],
                     c["SMTP_SENHA"])


if __name__ == "__main__":
    App().mainloop()
