"""
ADC System — MVC com Tkinter
Diagrama: ADCConfig, Entrada, TipoDado, TipoADC, ADCParser, Validador,
          ADCFactory, ADCController, MainView, FormularioADC
"""

from __future__ import annotations

import tkinter.font as tkfont
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from enum import Enum
from typing import Any, List, Optional
import re

from matplotlib.pylab import rint

# ═══════════════════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════════════════

class TipoADC(Enum):
    AEB = "2"
    COM = "108"


class Entrada:
    def __init__(self, block: str, cfg: bool, keyword: str, identificator: str, valor: Any, num_bits: str, reserved: bool = False, comentario: Optional[str] = None, is_comment: bool = False):
        self.block = block
        self.cfg = cfg
        self.keyword = keyword
        self.identificator = identificator
        self.num_bits = num_bits
        self.valor = valor
        self.reserved = reserved
        self.comentario = comentario
        self.is_comment = is_comment

    def validar(self) -> bool:
        if self.reserved and self.valor != "0":
            raise ValueError(f"Entrada '{self.identificator}' é reservada e não é 0.")
        if self.valor is not None and not isinstance(self.valor, str):
            raise TypeError(f"Entrada '{self.identificator}' deve ser do tipo str, mas recebeu {type(self.valor).__name__}.")
        return True

    def __repr__(self) -> str:
        return f"{self.identificator!r}            {self.num_bits}:{self.valor!r}"


class ADCConfig:
    def __init__(self, tipo: TipoADC, id: str = ""):
        self.id: str                 = id
        self.tipo: TipoADC           = tipo
        self.entradas: List[Entrada] = []

    def adicionar_entrada(self, entrada: Entrada) -> None:
        self.entradas.append(entrada)

    def obter_entrada(self, identificator: str) -> Optional[Entrada]:
        return next((e for e in self.entradas if e.identificator == identificator), None)

    def __repr__(self) -> str:
        return f"ADCConfig(id={self.id!r}, tipo={self.tipo}, entradas={self.entradas})"


class Validador:
    def validar_config(self, config: ADCConfig) -> bool:
        for entrada in config.entradas:
            entrada.validar()
        return True


class ADCParser:
    def parse(self, arquivo: str) -> ADCConfig:
        with open(arquivo, "r", encoding="utf-8") as f:
            linhas = [l.strip() for l in f if l.strip()]

        if not linhas:
            raise ValueError("Arquivo vazio.")

        linha_ID = next((l for l in linhas if l.startswith("ID")), None)
        
        if not linha_ID:
            raise ValueError("Arquivo sem identificador de configuracao.")
        
        _,_,config_id = self.obtem_valores_linha(linha_ID) # Obtem o id do arquivo
        config_tipo = self.obtem_tipo_adc(linhas) # Obtem o tipo do ADC do arquivo

        if not config_id or not config_tipo:
            raise ValueError("Arquivo sem ID ou tipo ADC.")

        config = ADCConfig(config_tipo, id=config_id)       

        esta_salvando = False

        for linha in linhas:
            if linha.startswith("//"):
                comentario = linha.split("//", 1)[1].strip()
                config.adicionar_entrada(Entrada(block="", cfg=False, keyword="", identificator="", valor=linha, num_bits="0", reserved=False, is_comment = True, comentario=comentario))
                
            if any(tag in linha for tag in ["[IDENTIFICATION]","[CONFIG]","[PROTECTION]"]):
                block = re.search(r"\[(.*?)\]", linha).group(1)
                esta_salvando = True
                continue
            
            if not linha:
                esta_salvando = False
                continue

            if esta_salvando:
                if "//" in linha:
                    comentario = linha.split("//", 1)[1].strip()

                keyword, num_bits, valor = self.obtem_valores_linha(linha)
                if keyword and num_bits and valor:
                    config.adicionar_entrada(Entrada(block=block, cfg=True if linha.startswith("CFG_") else False, keyword=keyword, identificator=keyword, valor=valor, num_bits=int(num_bits), reserved=True if linha.startswith("RESERVED") else False, is_comment=False, comentario=comentario if "//" in linha else None))
        return config

    def gerar(self, config: ADCConfig, arquivo: str) -> None:
        id_title = False
        protection_title = False
        with open(arquivo, "w", encoding="utf-8") as f:
            
            width = max(len(e.identificator) for e in config.entradas) + 4

            for e in config.entradas:
                if e.block == "IDENTIFICATION":
                    if not id_title:
                        f.write("[IDENTIFICATION]\n")

                    f.write(f"{e.identificator:<{width}}{e.num_bits}:{e.valor}\n")
                    id_title = True
                elif e.block == "CONFIG":
                    if e.cfg:
                        f.write("\n[CONFIG]\n")
                        f.write(f"{e.identificator:<{width}}{e.num_bits}:{e.valor}\n")
                    else:
                        f.write(f"{e.identificator:<{width}}{e.num_bits}:{e.valor}\n")
                elif e.block == "PROTECTION":
                    if not protection_title:
                        f.write("\n[PROTECTION]\n")

                        protection_title = True
                    f.write(f"{e.identificator:<{width}}{e.num_bits}:{e.valor}\n")
        
    def obtem_valores_linha(self, linha: str) -> tuple[str, str, str]:
        """Extrai os valores de uma linha do arquivo ADC e retorna como uma tupla (keyword, num_bits, valor)."""
        if linha.startswith("//"):
            return ["", "", ""]
        
        partes = linha.split()
        bits, valor = partes[1].split(":")
        return [str(partes[0]), str(bits), str(valor)]

    def obtem_tipo_adc(self, linhas: list[str]) -> TipoADC:
        for linha in linhas:
            if "COMPONENT" in linha:
                _,_,valor = self.obtem_valores_linha(linha)
                return TipoADC(str(valor)) if str(valor) in TipoADC._value2member_map_ else None

        raise ValueError("Tipo ADC nao encontrado no arquivo.")

class ADCFactory:
    @staticmethod
    def criar_config(tipo: TipoADC) -> ADCConfig:
        return ADCConfig(tipo=tipo)


# ═══════════════════════════════════════════════════════════
# CONTROLLER
# ═══════════════════════════════════════════════════════════

class ADCController:
    def __init__(self) -> None:
        self._config:   Optional[ADCConfig] = None
        self._parser    = ADCParser()
        self._validador = Validador()

    @property
    def config(self) -> Optional[ADCConfig]:
        return self._config

    def criar_config(self, tipo: TipoADC) -> None:
        self._config = ADCFactory.criar_config(tipo)

    def carregar_arquivo(self, path: str) -> None:
        self._config = self._parser.parse(path)
        self._validador.validar_config(self._config)

    def editar_entrada(self, identificator: str, valor: Any) -> None:
        self._garantir_config()
        entrada = self._config.obter_entrada(identificator)
        if entrada is None:
            raise KeyError(f"Entrada '{identificator}' nao encontrada.")
        entrada.valor = valor
        entrada.validar()

    def adicionar_entrada(self, entrada: Entrada) -> None:
        self._garantir_config()
        self._config.adicionar_entrada(entrada)

    def exportar(self, path: str) -> None:
        self._garantir_config()
        self._validador.validar_config(self._config)
        self._parser.gerar(self._config, path)

    def _garantir_config(self) -> None:
        if self._config is None:
            raise RuntimeError("Nenhuma configuracao carregada.")


# ═══════════════════════════════════════════════════════════
# VIEW — FormularioADC
# ═══════════════════════════════════════════════════════════

class FormularioADC(tk.LabelFrame):
    def __init__(self, parent: tk.Widget, controller: ADCController, **kw):
        super().__init__(parent, text="Entradas", padx=8, pady=8, **kw)
        self._controller = controller
        self._vars: dict[str, tk.StringVar] = {}

    def renderizar_campos(self, config: ADCConfig, comment_state: bool) -> None:
        for widget in self.winfo_children():
            widget.destroy()
        self._vars.clear()

        columns = ("Nome", "Num Bits", "Valor") + (("Comentário",) if comment_state else ())
        len_columns = len(columns)

        treeview = ttk.Treeview(self, columns=columns, show="headings")
        size_columns = [150, 100, 100] + ([200] if comment_state else [])
        for col, width in zip(columns, size_columns):
            treeview.heading(col, text=col)
            treeview.column(col, width=width, anchor="w")
        treeview.bind("<Double-1>", lambda event: self.on_double_click(event, treeview, comment_state))


        hsb = ttk.Scrollbar(self, orient="horizontal", command=treeview.xview)
        vsb = ttk.Scrollbar(self, orient="vertical", command=treeview.yview)

        treeview.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)

        title_id = False
        title_config = False
        title_protection = False
        true_grey_false_white = True

        for entrada in config.entradas:
            if entrada.is_comment:
                if comment_state:
                    treeview.insert("", "end", values=("","","", entrada.comentario), tags=("comment",))
            else:
                if entrada.block == "IDENTIFICATION":
                    if not title_id:
                        treeview.insert("", "end", values=("--- IDENTIFICATION ----------",) + ("------------------------",) * (len_columns - 1), tags=("title",))
                        title_id = True
                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    treeview.insert("", "end", values=values)
                elif entrada.block == "CONFIG":
                    if not title_config:
                        treeview.insert("", "end", values=("--- CONFIG ----------",) + ("------------------------",) * (len_columns - 1), tags=("title",))
                        title_config = True
                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    true_grey_false_white = not true_grey_false_white if entrada.cfg else true_grey_false_white
                    if entrada.cfg:
                        treeview.insert("", "end", values=("", "", "", ""))
                    treeview.insert("", "end", values=values, tags=("color1",) if true_grey_false_white else ())
                elif entrada.block == "PROTECTION":
                    if not title_protection:
                        treeview.insert("", "end", values=("--- PROTECTION ----------",) + ("------------------------",) * (len_columns - 1), tags=("title",))
                        title_protection = True
                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    treeview.insert("", "end", values=values)
                else:
                    raise ValueError(f"Bloco desconhecido: {entrada.block}")

        treeview.grid(row=0, column=0, columnspan=len_columns, sticky="nsew")
        treeview.tag_configure("title", font=("Segoe UI", 10, "bold"), background="#aaaaaa")
        treeview.tag_configure("color1", font=("Segoe UI", 9), background="#a5a2a2")

        if comment_state:
            self.auto_fit_columns(treeview)

        hsb.grid(row=1, column=0, columnspan=len_columns, sticky="ew")
        vsb.grid(row=0, column=len_columns, sticky="ns")


    def on_double_click(self, event: tk.Event, treeview: ttk.Treeview, comment_state: bool) -> None:
        try:
            self.entryPopup.destroy()
        except AttributeError:
            pass
        rowid = treeview.identify_row(event.y)
        column = treeview.identify_column(event.x)

        if not rowid or not column:
            return
        
        x, y, width, height = treeview.bbox(rowid, column)

        pady = height // 2

        text = treeview.item(rowid, "values")[int(column[1:]) - 1]
        self.entryPopup = EntryPopup(self, treeview, rowid, int(column[1:])-1, text)
        self.entryPopup.place(x=x, y=y + pady, width=width, height=height, anchor="w")


    def coletar_dados(self) -> dict[str, str]:
        return {nome: var.get() for nome, var in self._vars.items()}

    def auto_fit_columns(self, treeview: ttk.Treeview) -> None:
        font = tkfont.nametofont("TkDefaultFont")

        max_width = font.measure("Comentário")  # cabeçalho

        for item in treeview.get_children():
            valor = treeview.item(item, "values")
            has_comment = len(valor) > 3
            if has_comment:  # índice da coluna Comentário
                max_width = max(max_width, font.measure(str(valor[3])))

        treeview.column("Comentário", width=max_width + 20)

class EntryPopup(tk.Entry):
    def __init__(self, parent, treeview, iid, column, text, **kw):
        super().__init__(parent, **kw)
        self.tv = treeview
        self.iid = iid
        self.column = column

        self.insert(0, text)
        self['exportselection'] = False

        self.focus_force()
        self.select_all()
        self.bind("<Return>", self.on_return)
        self.bind("<Escape>", lambda e: self.destroy())

    def on_return(self, event):
        vals = list(self.tv.item(self.iid, "values"))
        vals[self.column] = self.get()
        self.tv.item(self.iid, values=vals)
        self.destroy()

    def select_all(self, *ignore):
        self.selection_range(0, tk.END)
        return 'break'

# ═══════════════════════════════════════════════════════════
# VIEW — MainView
# ═══════════════════════════════════════════════════════════

class MainView:
    def __init__(self) -> None:
        self._controller = ADCController()
        self._root       = tk.Tk()
        self._form:  Optional[FormularioADC] = None
        self._status_var = tk.StringVar(value="Pronto.")

    def iniciar(self) -> None:
        self._root.title("ADC System")
        self._root.resizable(False, True)
        self._root.configure(bg="#f0f0f0")
        self._construir_ui()
        self.bind_eventos()
        self._root.mainloop()

    def _construir_ui(self) -> None:
        toolbar = tk.Frame(self._root, bg="#dde3ec", pady=4)
        toolbar.pack(fill="x")

        for label, cmd in [
            ("Nova config",     self._on_nova_config),
            ("Abrir arquivo",   self._on_abrir),
            ("Salvar",          self._on_salvar),
            ("Aplicar edicoes", self._on_aplicar),
        ]:
            tk.Button(
                toolbar, text=label, command=cmd,
                relief="flat", bg="#4a6fa5", fg="white",
                activebackground="#3a5a8a", padx=10, pady=4,
                font=("Segoe UI", 9),
            ).pack(side="left", padx=4)

        central = tk.Frame(self._root, bg="#f0f0f0", padx=12, pady=12)
        central.pack(fill="both", expand=True)

        self._tipo_var = tk.StringVar(value="—")
        self._id_var   = tk.StringVar(value="")
        tipo_frame = tk.Frame(central, bg="#f0f0f0")
        tipo_frame.pack(fill="x", pady=(0, 8))
        tk.Label(tipo_frame, text="ID:", bg="#f0f0f0",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(tipo_frame, textvariable=self._id_var, bg="#f0f0f0",
                 fg="#4a6fa5", font=("Segoe UI", 9)).pack(side="left", padx=(4, 16))
        tk.Label(tipo_frame, text="Tipo ADC:", bg="#f0f0f0",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(tipo_frame, textvariable=self._tipo_var, bg="#f0f0f0",
                 fg="#4a6fa5", font=("Segoe UI", 9)).pack(side="left", padx=6)
        
        self.toggle_var = tk.BooleanVar()
        self.toggle_var.trace_add("write", lambda *_: self.toggle_comentarios())

        toggle = tk.Checkbutton(tipo_frame, text="Mostrar comentários", variable=self.toggle_var, bg="#f0f0f0", font=("Segoe UI", 9))
        toggle.pack(side="right", padx=6)

        self._form = FormularioADC(central, self._controller, bg="#f0f0f0")
        self._form.pack(fill="both", expand=True)

        tk.Label(
            self._root, textvariable=self._status_var,
            anchor="w", bg="#dde3ec", fg="#333",
            font=("Segoe UI", 8), relief="sunken",
        ).pack(fill="x", side="bottom")

    def toggle_comentarios(self) -> None:
        if self._form is None or self._controller.config is None:
            return
        self._form.renderizar_campos(self._controller.config, self.toggle_var.get())

    def bind_eventos(self) -> None:
        self._root.bind("<Control-o>", lambda _e: self._on_abrir())
        self._root.bind("<Control-s>", lambda _e: self._on_salvar())

    def mostrar_config(self) -> None:
        config = self._controller.config
        if config is None:
            return
        self._id_var.set(config.id or "—")
        self._tipo_var.set(config.tipo.name)
        self._form.renderizar_campos(config, self.toggle_var.get())

    def _on_nova_config(self) -> None:
        dialog = _DialogNovaConfig(self._root)
        tipo = dialog.resultado
        if tipo is None:
            return
        try:
            self._controller.criar_config(tipo)
            self.mostrar_config()
            self._status("Nova configuracao criada.")
        except Exception as exc:
            self._erro(exc)

    def _on_abrir(self) -> None:
        path = filedialog.askopenfilename(
            title="Abrir configuracao ADC",
            filetypes=[("Arquivos ADC", "*.txt *.adc"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            self._controller.carregar_arquivo(path)
            self.mostrar_config()
            self._status(f"Carregado: {path.split('/')[-1]}")
        except Exception as exc:
            self._erro(exc)

    def _on_salvar(self) -> None:
        if self._controller.config is None:
            messagebox.showwarning("Aviso", "Nenhuma configuracao para salvar.")
            return
        path = filedialog.asksaveasfilename(
            title="Salvar configuracao ADC",
            defaultextension=".txt",
            filetypes=[("Arquivos ADC", "*.txt *.adc")],
        )
        if not path:
            return
        try:
            self._controller.exportar(path)
            self._status(f"Salvo em: {path}")
        except Exception as exc:
            self._erro(exc)

    def _on_aplicar(self) -> None:
        if self._form is None or self._controller.config is None:
            return
        dados = self._form.coletar_dados()
        erros = []
        for nome, val_str in dados.items():
            entrada = self._controller.config.obter_entrada(nome)
            if entrada is None:
                continue
            try:
                valor = val_str
                self._controller.editar_entrada(nome, valor)
            except Exception as exc:
                erros.append(f"{nome}: {exc}")

        if erros:
            messagebox.showerror("Erros de validacao", "\n".join(erros))
        else:
            self._status("Edicoes aplicadas com sucesso.")

    def _status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _erro(self, exc: Exception) -> None:
        messagebox.showerror("Erro", str(exc))
        self._status(f"Erro: {exc}")


# ═══════════════════════════════════════════════════════════
# Dialog auxiliar
# ═══════════════════════════════════════════════════════════

class _DialogNovaConfig(tk.Toplevel):
    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("Nova Configuracao")
        self.resizable(False, False)
        self.grab_set()
        self.resultado: Optional[TipoADC] = None

        tk.Label(self, text="Selecione o tipo ADC:", padx=16, pady=12).pack()
        self._var = tk.StringVar(value=TipoADC.AEB.name)
        for membro in TipoADC:
            tk.Radiobutton(self, text=membro.name, variable=self._var,
                           value=membro.name).pack(anchor="w", padx=24)
        tk.Button(self, text="Criar", command=self._confirmar,
                  bg="#4a6fa5", fg="white", padx=10, pady=4).pack(pady=12)
        self.wait_window()

    def _confirmar(self) -> None:
        self.resultado = TipoADC[self._var.get()]
        self.destroy()


# ═══════════════════════════════════════════════════════════
# Ponto de entrada
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    MainView().iniciar()