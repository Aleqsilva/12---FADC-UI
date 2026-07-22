"""
ADC System — MVC com Tkinter
Diagrama: ADCConfig, Entrada, TipoDado, TipoADC, ADCParser, Validador,
          ADCFactory, ADCController, MainView, FormularioADC
"""

from __future__ import annotations

import tkinter.font as tkfont
import tkinter as tk
import re
import json

from tkinter import filedialog, messagebox, ttk
from enum import Enum
from typing import Any, List, Optional
from matplotlib.pylab import rint

# ═══════════════════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════════════════

class BancoDadosConfig:
    def __init__(self):
        try:
            arquivo_json = "bd_config.json"
            with open(arquivo_json, 'r', encoding='utf-8') as file:
                self.bd_data = json.load(file)
        except:
            raise RuntimeError(f"Erro ao carregar o arquivo {arquivo_json}.")

class TipoADC(Enum):
    AEB = "2"
    COM = "108"


class Entrada:
    def __init__(self, block: str, cfg: bool, keyword: str, identificator: str, valor: Any, num_bits: str, reserved: bool = False, comentario: Optional[str] = None, is_comment: bool = False, config_name: Optional[str] = ""):
        self.block = block
        self.cfg = cfg
        self.keyword = keyword
        self.identificator = identificator
        self.num_bits = num_bits
        self.valor = valor
        self.reserved = reserved
        self.comentario = comentario
        self.is_comment = is_comment
        self.config_name = config_name

    def validar(self) -> bool:
        if self.reserved and self.valor != "0":
            raise ValueError(f"Entrada '{self.identificator}' é reservada e não é 0.")
        if self.valor is not None and not isinstance(self.valor, str):
            raise TypeError(f"Entrada '{self.identificator}' deve ser do tipo str, mas recebeu {type(self.valor).__name__}.")
        return True

    def __repr__(self) -> str:
        return f"{self.identificator!r}            {self.num_bits}:{self.valor!r}"
    
    def to_dict(self) -> dict:
        return {
            "nome": self.identificator,
            "num_bit": self.num_bits,
            "valor_range": self.valor,
        }

class ADCConfig:
    def __init__(self, tipo: TipoADC, id: str = ""):
        self.id = id
        self.tipo: TipoADC           = tipo
        self.configs_dict = {}
        self.entradas: List[Entrada] = []
        self.protection = {
            "COMPONENT": "",
            "VERSION": "",
        }

    def adicionar_entrada(self, entrada: Entrada) -> None:
        self.entradas.append(entrada)

    def preenche_config_dict(self, config: ADCConfig, entrada: Entrada) -> None:
        if entrada.cfg:
            chave = f"{config.tipo.name}:{entrada.keyword}"
            if chave not in self.configs_dict:
                self.configs_dict[chave] = []

            self.configs_dict[chave].append(config.config_to_dict(entrada, config))
        else:
            chave = f"{config.tipo.name}:{entrada.config_name}"
            self.configs_dict[chave][-1]["entradas"].append(entrada.to_dict())

    def obter_entrada(self, identificator: str) -> Optional[Entrada]:
        return next((e for e in self.entradas if e.identificator == identificator), None)

    def config_to_dict(self, entrada, config) -> dict:
        return{
                "nome": entrada.keyword,
                "num_bit": entrada.num_bits,
                "range": entrada.valor,
                "id": f"{entrada.num_bits}:{entrada.valor}",
                "origem": config.tipo.name,
                "entradas": [],
            }

    def __repr__(self) -> str:
        return f"ADCConfig(id={self.id['id']!r}, tipo={self.tipo}, entradas={self.entradas})"


class Validador:
    def __init__(self):
        self.bd = BancoDadosConfig()

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
        cfg_name = None

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

                    if linha.startswith("CFG_"):
                        cfg_name = keyword
                    elif linha.startswith("PROTECTION"):
                        cfg_name = None

                    entrada = Entrada(block=block, cfg=True if linha.startswith("CFG_") else False, keyword=keyword, identificator=keyword, valor=valor, num_bits=int(num_bits), reserved=True if linha.startswith("RESERVED") else False, is_comment=False, comentario=comentario if "//" in linha else None, config_name=cfg_name if not linha.startswith("CFG_") else None)
                    config.adicionar_entrada(entrada)
                    if not entrada.is_comment and entrada.block == "CONFIG":
                        config.preenche_config_dict(config, entrada)

        print(json.dumps(config.configs_dict, indent=2))

        return config

    def gerar(self, config: ADCConfig, arquivo: str) -> None:
        id_title = False
        protection_title = False
        with open(arquivo, "w", encoding="utf-8") as f:
            
            width = max(len(e.identificator) for e in config.entradas) + 4

            for e in config.entradas:
                if e.is_comment:
                    f.write(f"{e.valor}\n")
                elif e.block == "IDENTIFICATION":
                    comment = f"    //{e.comentario}" if e.comentario else ""
                    if not id_title:
                        f.write("[IDENTIFICATION]\n")
                    f.write(f"{e.identificator:<{width}}{e.num_bits}:{e.valor}{comment}\n")
                    id_title = True
                elif e.block == "CONFIG":
                    comment = f"    //{e.comentario}" if e.comentario else ""
                    if e.cfg:
                        f.write("\n[CONFIG]\n")
                        f.write(f"{e.identificator:<{width}}{e.num_bits}:{e.valor}{comment}\n")
                    else:
                        f.write(f"{e.identificator:<{width}}{e.num_bits}:{e.valor}{comment}\n")
                elif e.block == "PROTECTION":
                    comment = f"    //{e.comentario}" if e.comentario else ""
                    if not protection_title:
                        f.write("\n[PROTECTION]\n")

                        protection_title = True
                    f.write(f"{e.identificator:<{width}}{e.num_bits}:{e.valor}{comment}\n")
        
    def obtem_valores_linha(self, linha) -> tuple[str, str, str]:
        """Extrai os valores de uma linha do arquivo ADC e retorna como uma tupla (keyword, num_bits, valor)."""
        if linha.startswith("//"):
            return ["", "", ""]
        
        partes = linha.split()

        if len(partes) < 2:
            raise ValueError(f"Linha mal formatada: {linha}")
        
        nome = partes[0]
        num_bits, valor = partes[1].split(":")

        return [str(nome), str(num_bits), str(valor)]    

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
        self._vars = {}

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
                        treeview.insert("", "end", values=("IDENTIFICATION",) + ("",) * (len_columns - 1), tags=("title",))
                        title_id = True

                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    treeview.insert("", "end", values=values)

                elif entrada.block == "CONFIG":

                    if not title_config:
                        treeview.insert("", "end", values=("CONFIG",) + ("",) * (len_columns - 1), tags=("title",))
                        title_config = True

                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    true_grey_false_white = not true_grey_false_white if entrada.cfg else true_grey_false_white

                    if entrada.cfg:
                        treeview.insert("", "end", values=values, tags=("style_cfg_bold",) if true_grey_false_white else ("style_cfg_bold_white",))
                    else:
                        treeview.insert("", "end", values=values, tags=("grey/white",) if true_grey_false_white else ())

                elif entrada.block == "PROTECTION":
                    if not title_protection:
                        treeview.insert("", "end", values=(" PROTECTION",) + ("",) * (len_columns - 1), tags=("title",))
                        title_protection = True

                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    treeview.insert("", "end", values=values)
                else:
                    raise ValueError(f"Bloco desconhecido: {entrada.block}")

        treeview.grid(row=0, column=0, columnspan=len_columns, sticky="nsew")
        treeview.tag_configure("title", font=("Segoe UI", 10, "bold"), background="#1F1D1D", foreground="#ffffff")
        treeview.tag_configure("grey/white", font=("Segoe UI", 9), background="#a5a2a2")
        treeview.tag_configure("style_cfg_bold", font=("Segoe UI", 9, "bold"), background="#a5a2a2")
        treeview.tag_configure("style_cfg_bold_white", font=("Segoe UI", 9, "bold"), background="#ffffff")
        treeview.tag_configure("comment", font=("Segoe UI", 9), foreground="#6A9955")


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

        if not rowid or not column or column == "#2" or (column == "#4" and not comment_state):
            return
        
        x, y, width, height = treeview.bbox(rowid, column)

        pady = height // 2

        if any(word in item for item in treeview.item(rowid, "values") for word in ["IDENTIFICATION", "CONFIG", "PROTECTION", "RESERVED", "CFG_"]):
            return

        text = treeview.item(rowid, "values")[int(column[1:]) - 1] if int(column[1:]) - 1 < len(treeview.item(rowid, "values")) else ""

        self.entryPopup = EntryPopup(self, treeview, rowid, int(column[1:])-1, text)
        self.entryPopup.place(x=x, y=y + pady, width=width, height=height, anchor="w")


    def coletar_dados(self) -> dict[str, str]:
        #for keyword, value in self._vars.items():
        #    print(f"Coletando dados: {keyword} = {value}")
        return {keyword: value for keyword, num_bit, value in self._vars.items()}

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
        if len(vals) <= self.column:
            vals.extend([""] * (self.column - len(vals) + 1))
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
            print("Nenhuma configuracao carregada para aplicar.")
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