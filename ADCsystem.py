"""
ADC System — MVC com Tkinter
Diagrama: ADCConfig, Entrada, TipoDado, TipoADC, ADCParser, Validador,
          ADCFactory, ADCController, MainView, FormularioADC
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from enum import Enum
from typing import Any, List, Optional
import re

# ═══════════════════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════════════════

class TipoADC(Enum):
    AEB = "2"
    COM = "108"


class Entrada:
    def __init__(self, block: str, cfg: bool, keyword: str, identificator: str, valor: Any, num_bits: str, reserved: bool = False):
        self.block = block
        self.cfg = cfg
        self.keyword = keyword
        self.identificator = identificator
        self.num_bits = num_bits
        self.valor = valor
        self.reserved = reserved

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
            if any(tag in linha for tag in ["[IDENTIFICATION]","[CONFIG]","[PROTECTION]"]):
                block = re.search(r"\[(.*?)\]", linha).group(1)
                esta_salvando = True
                continue
            
            if not linha:
                esta_salvando = False
                continue

            if esta_salvando:
                    keyword, num_bits, valor = self.obtem_valores_linha(linha)
                    if keyword and num_bits and valor:
                        if linha.startswith("CFG_"):
                            config.adicionar_entrada(Entrada(block=block, cfg=True, keyword=keyword, identificator=keyword, valor=valor, num_bits=int(num_bits), reserved=False))
                        elif linha.startswith("RESERVED"):
                            config.adicionar_entrada(Entrada(block=block, cfg=False, keyword=keyword, identificator=keyword, valor=valor, num_bits=int(num_bits), reserved=True))
                        else:
                            config.adicionar_entrada(Entrada(block=block, cfg=False, keyword=keyword, identificator=keyword, valor=valor, num_bits=int(num_bits), reserved=False))
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
            line = linha.split('//', 1)[1]
            print(f"Linha de comentario salva: {line}")
            return ["", "", ""]
        elif "//" in linha:
            line = linha.split('//', 1)[1]
            print(f"Linha de comentario salva: {line}")
        
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
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = tk.Frame(self.canvas, background="#f0f0f0")

        self.window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.content.bind("<Configure>", self._on_frame_configure)

        self._controller = controller
        self._vars: dict[str, tk.StringVar] = {}

    def _on_frame_configure(self, event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self.content.winfo_reqwidth() != self.canvas.winfo_width():
            self.canvas.configure(width=self.content.winfo_reqwidth())

    def renderizar_campos(self, config: ADCConfig, comment_state: bool) -> None:
        for widget in self.content.winfo_children():
            widget.destroy()
        self._vars.clear()

        columns = ("Nome", "Num Bits", "Valor") + ("Comentário",) if comment_state else ()

        for col, txt in enumerate(columns):
            tk.Label(self.content, text=txt, font=("Segoe UI", 9, "bold")).grid(
                row=0, column=col, padx=6, pady=(0, 4), sticky="nsew"
            )

        row = 1
        title_id = False
        title_config = False
        title_protection = False
        for entrada in config.entradas:
            if entrada.block == "IDENTIFICATION":
                if not title_id:
                    ttk.Separator(self.content, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=(2, 4)); row += 1
                    tk.Label(self.content, text="IDENTIFICATION", background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 2)); row += 1
                    title_id = True
                tk.Label(self.content, text=entrada.identificator, background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=0, padx=6, sticky="w")
                tk.Label(self.content, text=entrada.num_bits, background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=1, padx=6, sticky="w")
                tk.Label(self.content, text=entrada.valor, background="#f0f0f0", width=20, font="Helvetica 10 bold").grid(row=row, column=2, padx=6); row += 1
            elif entrada.block == "CONFIG":
                if not title_config:
                    ttk.Separator(self.content, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=(2, 4)); row += 1
                    tk.Label(self.content, text="CONFIG", background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 2)); row += 1
                    title_config = True
                if entrada.cfg:
                    ttk.Separator(self.content, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=(2, 4)); row += 1
                    tk.Label(self.content, text=entrada.identificator, background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=0, padx=6, sticky="w")
                    tk.Label(self.content, text=entrada.num_bits, background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=1, padx=6, sticky="w")
                    tk.Label(self.content, text=entrada.valor, background="#f0f0f0", width=20, font="Helvetica 10 bold").grid(row=row, column=2, padx=6); row += 1
                elif entrada.reserved:
                    tk.Label(self.content, text=entrada.identificator, background="#f0f0f0").grid(row=row, column=0, padx=6, sticky="w")
                    tk.Label(self.content, text=entrada.num_bits, background="#f0f0f0").grid(row=row, column=1, padx=6, sticky="w")
                    tk.Label(self.content, text=entrada.valor, background="#f0f0f0", width=20).grid(row=row, column=2, padx=6); row += 1
                else:
                    tk.Label(self.content, text=entrada.identificator).grid(row=row, column=0, padx=6, sticky="w")
                    var = tk.StringVar(value=str(entrada.valor))
                    self._vars[entrada.identificator] = var
                    tk.Label(self.content, text=entrada.num_bits).grid(row=row, column=1, padx=6, sticky="w")
                    tk.Entry(self.content, textvariable=var, width=20).grid(row=row, column=2, padx=6); row += 1
            elif entrada.block == "PROTECTION":
                if not title_protection:
                    ttk.Separator(self.content, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=(2, 4)); row += 1
                    tk.Label(self.content, text="PROTECTION", background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 2)); row += 1
                    title_protection = True
                tk.Label(self.content, text=entrada.identificator, background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=0, padx=6, sticky="w")
                tk.Label(self.content, text=entrada.num_bits, background="#f0f0f0", font="Helvetica 10 bold").grid(row=row, column=1, padx=6, sticky="w")
                tk.Label(self.content, text=entrada.valor, background="#f0f0f0", width=20, font="Helvetica 10 bold").grid(row=row, column=2, padx=6); row += 1
            else:
                raise ValueError(f"Bloco desconhecido: {entrada.block}")

    def coletar_dados(self) -> dict[str, str]:
        return {nome: var.get() for nome, var in self._vars.items()}


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