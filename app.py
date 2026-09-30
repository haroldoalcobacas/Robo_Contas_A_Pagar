"""
Tela de abertura do Robô de Contas a Pagar.

Três abas:
- Executar: pastas de entrada/saída, data de referência e botão de execução.
- Leitura de e-mail: origem (pasta ou IMAP) e credenciais da caixa.
- Relatório: envio por e-mail e/ou WhatsApp, e a frequência.

Tudo é salvo no .env (fora do Git).

Uso:
    python app.py
"""

import os
import queue
import threading
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from robo import config
from robo.conexoes import testar_imap, testar_smtp
from robo.planilha import PlanilhaBloqueada
from robo.processador import brl, processar

FORMATO_DATA = "%d/%m/%Y"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Robô de Contas a Pagar")
        self.geometry("900x680")
        self.minsize(780, 580)

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

        # Comunicação entre a thread do robô e a tela
        self.fila: queue.Queue = queue.Queue()
        self.executando = False

        self._estilos()
        self._montar()
        self.after(100, self._ler_fila)

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
                initialdir=atual if atual.exists() else config.RAIZ)
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
        self.btn_executar = ttk.Button(botoes, text="▶  Executar robô",
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
        for texto, valor in [("Pasta local com arquivos .eml", "pasta"),
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
        ttk.Button(f, text="Testar conexão",
                   command=self.testar_imap).grid(row=5, column=1,
                                                  sticky="w", pady=(8, 0))

        ttk.Label(aba, style="Dica.TLabel", justify="left", text=(
            "Gmail: ative a verificação em duas etapas e gere uma "
            "\"senha de app\" (Conta Google > Segurança > Senhas de app).\n"
            "Use essa senha de 16 letras aqui, nunca a senha normal da "
            "conta.\n\nA leitura direta da caixa entra no Nível 3. Até lá, "
            "o robô usa a pasta local e este teste só confere o login."
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

        ttk.Label(aba, style="Dica.TLabel", justify="left", text=(
            "CallMeBot é gratuito e envia mensagens para o seu próprio "
            "WhatsApp. A API key é obtida em callmebot.com.\n"
            "O envio automático do relatório entra no Nível 3."
        )).pack(anchor="w", pady=(8, 0))
        self._alternar_canais()
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
        """Guarda caminhos dentro do projeto como relativos (portáveis)."""
        try:
            return pasta.resolve().relative_to(config.RAIZ).as_posix()
        except ValueError:
            return str(pasta)

    def _cfg_da_tela(self) -> dict[str, str]:
        cfg = {k: var.get().strip() for k, var in self.v.items()}
        # Senhas não levam strip: espaço pode fazer parte delas
        for k in ("IMAP_SENHA", "SMTP_SENHA"):
            cfg[k] = self.v[k].get()
        cfg["RELATORIO_EMAIL"] = "sim" if self.var_rel_email.get() else "nao"
        cfg["RELATORIO_WHATSAPP"] = "sim" if self.var_rel_whats.get() else "nao"
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

    def _validar(self, cfg: dict[str, str]) -> list[str]:
        erros = []
        if cfg["DATA_REFERENCIA"] == "invalida":
            erros.append("Data de referência inválida (use DD/MM/AAAA).")
        for chave, nome in [("IMAP_PORTA", "IMAP"), ("SMTP_PORTA", "SMTP")]:
            if cfg[chave] and not cfg[chave].isdigit():
                erros.append(f"Porta {nome} deve ser um número.")
        if not cfg["NOME_PLANILHA"].lower().endswith(".xlsx"):
            erros.append("O nome da planilha deve terminar em .xlsx.")
        if cfg["RELATORIO_EMAIL"] == "sim" and not cfg["EMAIL_DESTINATARIOS"]:
            erros.append("Informe ao menos um destinatário do relatório.")
        if cfg["RELATORIO_WHATSAPP"] == "sim" and not (
                cfg["WHATSAPP_NUMERO"].isdigit() and cfg["WHATSAPP_APIKEY"]):
            erros.append("WhatsApp: informe o número (só dígitos, com DDI) "
                         "e a API key.")
        return erros

    def salvar(self) -> bool:
        cfg = self._cfg_da_tela()
        erros = self._validar(cfg)
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
        if self.executando:
            return
        cfg = self._cfg_da_tela()
        erros = [e for e in self._validar(cfg)
                 if "relatório" not in e and "WhatsApp" not in e]
        if erros:
            messagebox.showwarning("Não é possível executar", "\n".join(erros))
            return
        pasta = config.caminho(cfg, "PASTA_EMAILS")
        if not pasta.is_dir():
            messagebox.showerror("Pasta não encontrada", str(pasta))
            return
        saida = config.caminho(cfg, "PASTA_SAIDA") / cfg["NOME_PLANILHA"]
        data_ref = config.data_referencia(cfg)

        self._limpar_log()
        if cfg["ORIGEM_EMAILS"] == "imap":
            self._escrever("[AVISO] Leitura via IMAP chega no Nível 3. "
                           "Usando a pasta local.\n")
        self.executando = True
        self.btn_executar.state(["disabled"])
        self.lbl_resumo.config(text="Executando...")

        def tarefa():
            try:
                res = processar(pasta, saida, data_ref,
                                log=lambda s: self.fila.put(("log", s)))
                self.fila.put(("fim", res))
            except PlanilhaBloqueada:
                self.fila.put(("erro", f"Não foi possível gravar "
                               f"{saida.name}.\nFeche a planilha no Excel "
                               "e rode de novo."))
            except Exception as erro:
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

    def _fim_execucao(self, res) -> None:
        self.executando = False
        self.btn_executar.state(["!disabled"])
        if res is None:
            return
        vencidas = res.por_status("VENCIDA")
        self.lbl_resumo.config(text=(
            f"{len(res.contas)} contas  |  Total {brl(res.total)}  |  "
            f"{len(vencidas)} vencidas  |  {len(res.novas)} novas  |  "
            f"{len(res.excecoes)} exceções"))

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
        cfg = self._cfg_da_tela()
        arquivo = config.caminho(cfg, "PASTA_SAIDA") / cfg["NOME_PLANILHA"]
        if arquivo.exists():
            os.startfile(arquivo)
        else:
            messagebox.showinfo("Planilha", "A planilha ainda não foi "
                                "gerada. Clique em Executar robô.")

    def abrir_pasta_saida(self) -> None:
        pasta = config.caminho(self._cfg_da_tela(), "PASTA_SAIDA")
        pasta.mkdir(parents=True, exist_ok=True)
        os.startfile(pasta)

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
