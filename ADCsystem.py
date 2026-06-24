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
    AEB = "AEB"
    COM = "COM"


class Entrada:
    def __init__(self, nome: str, valor: Any, tipo: int, obrigatoria: bool = True):
        self.nome: str         = nome
        self.valor: Any        = valor
        self.tipo: int    = tipo
        self.obrigatoria: bool = obrigatoria

    def validar(self) -> bool:
        tipo_map = {
            0:    int,
        }
        esperado = tipo_map[self.tipo]
        if self.obrigatoria and self.valor is None:
            raise ValueError(f"Entrada '{self.nome}' e obrigatoria e esta vazia.")
        if self.valor is not None and not isinstance(self.valor, esperado):
            raise TypeError(
                f"Entrada '{self.nome}': esperado {esperado.__name__}, "
                f"recebido {type(self.valor).__name__}."
            )
        return True

    def __repr__(self) -> str:
        return f"Entrada(nome={self.nome!r}, valor={self.valor!r}, tipo={self.tipo})"


class ADCConfig:
    def __init__(self, tipo: TipoADC, id: str = ""):
        self.id: str                 = id
        self.tipo: TipoADC           = tipo
        self.entradas: List[Entrada] = []

    def adicionar_entrada(self, entrada: Entrada) -> None:
        self.entradas.append(entrada)

    def obter_entrada(self, nome: str) -> Optional[Entrada]:
        return next((e for e in self.entradas if e.nome == nome), None)

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
        
        config_id = (re.search(r"12:(\d+)", linha_ID)).group(1) # Obtem o id do arquivo
        
        print(f"ID extraido: {config_id}")

        config = ADCConfig(tipo=TipoADC["AEB"], id=config_id)
        conversores = {
            0:    int,
        }        

        esta_salvando = False

        for linha in linhas[linhas.index(linha_ID)+1:]:
            if "[CONFIG]" in linha:
                esta_salvando = True
                continue
            
            if not linha:
                esta_salvando = False
                continue

            if esta_salvando:
                if linha.startswith("CFG_"):
                    print(f"Salvando linha: {linha}")




        nome, valor_raw, tipo_raw, obrig_raw = linha.split(",")
        td  = int(tipo_raw)
        val = conversores[td](valor_raw)
        config.adicionar_entrada(Entrada(nome, val, td, obrig_raw.lower() == "true"))
        return config

    def gerar(self, config: ADCConfig, arquivo: str) -> None:
        with open(arquivo, "w", encoding="utf-8") as f:
            f.write(f"{config.id},{config.tipo.name}\n")
            for e in config.entradas:
                f.write(f"{e.nome},{e.valor},{e.tipo.name},{e.obrigatoria}\n")



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

    def editar_entrada(self, nome: str, valor: Any) -> None:
        self._garantir_config()
        entrada = self._config.obter_entrada(nome)
        if entrada is None:
            raise KeyError(f"Entrada '{nome}' nao encontrada.")
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

    def renderizar_campos(self, config: ADCConfig) -> None:
        for widget in self.winfo_children():
            widget.destroy()
        self._vars.clear()

        for col, txt in enumerate(("Nome", "Valor", "Tipo", "Obrigatoria")):
            tk.Label(self, text=txt, font=("Segoe UI", 9, "bold")).grid(
                row=0, column=col, padx=6, pady=(0, 4), sticky="w"
            )

        for row, entrada in enumerate(config.entradas, start=1):
            tk.Label(self, text=entrada.nome).grid(row=row, column=0, padx=6, sticky="w")
            var = tk.StringVar(value=str(entrada.valor))
            self._vars[entrada.nome] = var
            tk.Entry(self, textvariable=var, width=20).grid(row=row, column=1, padx=6)
            tk.Label(self, text=entrada.tipo.name).grid(row=row, column=2, padx=6)
            tk.Label(self, text="Sim" if entrada.obrigatoria else "Nao").grid(row=row, column=3, padx=6)

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
        self._root.resizable(False, False)
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

        self._form = FormularioADC(central, self._controller, bg="#f0f0f0")
        self._form.pack(fill="both", expand=True)

        tk.Label(
            self._root, textvariable=self._status_var,
            anchor="w", bg="#dde3ec", fg="#333",
            font=("Segoe UI", 8), relief="sunken",
        ).pack(fill="x", side="bottom")

    def bind_eventos(self) -> None:
        self._root.bind("<Control-o>", lambda _e: self._on_abrir())
        self._root.bind("<Control-s>", lambda _e: self._on_salvar())

    def mostrar_config(self) -> None:
        config = self._controller.config
        if config is None:
            return
        self._id_var.set(config.id or "—")
        self._tipo_var.set(config.tipo.name)
        self._form.renderizar_campos(config)

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
            self._status(f"Carregado: {path}")
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
                conversores = {
                    TipoDado.INT:    int,
                    TipoDado.FLOAT:  float,
                    TipoDado.STRING: str,
                    TipoDado.BOOL:   lambda v: v.lower() in ("true", "1", "sim"),
                }
                valor = conversores[entrada.tipo](val_str)
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