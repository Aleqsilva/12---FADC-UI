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

from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from enum import Enum
from typing import Any, List, Optional
from matplotlib.pylab import rint
import itertools
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════════════════

@dataclass
class Destino:
    """Um destino de encaminhamento (socket -> IP), independente de rede."""
    socket_id: int          # INT_ID_DEST resolvido (0..15)
    rede: int                # 1 ou 2 (NW1/NW2)
    ip: tuple[int, int, int, int]
    entradas: list[Entrada] = field(default_factory=list)  # header + 4 bytes, p/ mutação


@dataclass
class RegraEncaminhamento:
    """Uma regra que referencia um socket (ACD ou DIAG)."""
    tipo: str                # "ACD" ou "DIAG"
    socket_id: int           # aponta pro Destino.socket_id
    can_tx_id: Optional[int] # só para ACD
    entradas: list[Entrada] = field(default_factory=list)

class EncaminhamentoCOM:

    RANGE_NW1 = (32, 47)
    RANGE_NW2 = (48, 63)

    def __init__(self, config: ADCConfig):
        self.config = config
        self.destinos: list[Destino] = []
        self.regras: list[RegraEncaminhamento] = []
        self.carregar()

    def carregar(self) -> None:
        self.destinos.clear()
        self.regras.clear()
        print("Carregando encaminhamento...")
        for grupo in self.agrupar_blocos_config(self.config.entradas):
            self._classificar(grupo)

    def _classificar(self, grupo: list[Entrada]) -> None:
        header = grupo[0]
        if header.identificator == "CFG_INT_ID_DEST_NW1":
            base = self.RANGE_NW1[0]
            rede = 1
            try:
                socket_abs = int(header.valor)
            except Exception:
                return
            socket_id = socket_abs - base
            # coletar 4 bytes de IP (filhos do grupo)
            ip_bytes = []
            for filho in grupo[1:]:
                try:
                    ip_bytes.append(int(filho.valor))
                except Exception:
                    ip_bytes.append(0)
            if len(ip_bytes) >= 4:
                ip = tuple(ip_bytes[:4])
            else:
                ip = tuple((ip_bytes + [0, 0, 0, 0])[:4])
            destino = Destino(socket_id=socket_id, rede=rede, ip=ip, entradas=list(grupo))
            self.destinos.append(destino)
        elif header.identificator == "CFG_INT_ID_DEST_NW2":
            base = self.RANGE_NW2[0]
            rede = 2
            try:
                socket_abs = int(header.valor)
            except Exception:
                return
            socket_id = socket_abs - base
            ip_bytes = []
            for filho in grupo[1:]:
                try:
                    ip_bytes.append(int(filho.valor))
                except Exception:
                    ip_bytes.append(0)
            if len(ip_bytes) >= 4:
                ip = tuple(ip_bytes[:4])
            else:
                ip = tuple((ip_bytes + [0, 0, 0, 0])[:4])
            destino = Destino(socket_id=socket_id, rede=rede, ip=ip, entradas=list(grupo))
            self.destinos.append(destino)
        elif header.identificator == "CFG_FWRD_ACD":
            # procurar INT_ID_DEST e CAN_TX_ID nos filhos
            socket_id = None
            can_tx_id = None
            for filho in grupo[1:]:
                if filho.identificator == "INT_ID_DEST":
                    try:
                        socket_id = int(filho.valor)
                    except Exception:
                        socket_id = None
                elif filho.identificator == "CAN_TX_ID":
                    try:
                        can_tx_id = int(filho.valor)
                    except Exception:
                        can_tx_id = None
            regra = RegraEncaminhamento(tipo="ACD", socket_id=socket_id if socket_id is not None else -1, can_tx_id=can_tx_id, entradas=list(grupo))
            self.regras.append(regra)
        elif header.identificator == "CFG_FWRD_DIAG":
            socket_id = None
            for filho in grupo[1:]:
                if filho.identificator == "INT_ID_DEST":
                    try:
                        socket_id = int(filho.valor)
                    except Exception:
                        socket_id = None
            regra = RegraEncaminhamento(tipo="DIAG", socket_id=socket_id if socket_id is not None else -1, can_tx_id=None, entradas=list(grupo))
            self.regras.append(regra)
        print(self.regras[-1] if self.regras else "Nenhuma regra encontrada.")

    def adicionar_destino(self, rede: int, ip: tuple[int, int, int, int]) -> Destino:
        base, topo = self.RANGE_NW1 if rede == 1 else self.RANGE_NW2
        ocupados = {d.socket_id for d in self.destinos if d.rede == rede}
        livre = next((s for s in range(0, topo - base + 1) if s not in ocupados), None)
        if livre is None:
            raise ValueError(f"Não há sockets livres na rede {rede}.")

        prefixo = f"DEST_IP_INT_ID_NW{rede}"
        header = Entrada(self.config, "CONFIG", True, f"CFG_INT_ID_DEST_NW{rede}",
                          str(base + livre), 8, config_name=f"CFG_INT_ID_DEST_NW{rede}")
        filhos = [
            Entrada(self.config, "CONFIG", False, f"{prefixo}_B{i+1}", str(byte), 8,
                     config_name=f"CFG_INT_ID_DEST_NW{rede}")
            for i, byte in enumerate(ip)
        ]
        self._inserir_no_config([header, *filhos])
        destino = Destino(socket_id=livre, rede=rede, ip=ip, entradas=[header, *filhos])
        self.destinos.append(destino)
        return destino

    def remover_destino(self, socket_id: int, rede: int) -> None:
        if any(r.socket_id == socket_id for r in self.regras):
            raise ValueError("Socket ainda referenciado por regras de encaminhamento; remova-as primeiro.")
        destino = next((d for d in self.destinos if d.socket_id == socket_id and d.rede == rede),None)
        if destino is None:
            raise ValueError(f"Destino com socket {socket_id} na rede {rede} não encontrado.")
        for e in destino.entradas:
            self.config.entradas.remove(e)
        self.destinos.remove(destino)

    def adicionar_regra(self, tipo: str, socket_id: int, can_tx_id: Optional[int] = None) -> RegraEncaminhamento:
        if not any(d.socket_id == socket_id for d in self.destinos):
            raise ValueError(f"Socket {socket_id} não configurado em CFG_INT_ID_DEST_NW1/NW2.")

        if can_tx_id is None:
            raise ValueError("can_tx_id deve ser fornecido para regras do tipo ACD.")

        if tipo == "ACD":
            header = Entrada(self.config, "CONFIG", True, "CFG_FWRD_ACD", "9", 8, config_name="CFG_FWRD_ACD")
            filhos = [
                Entrada(self.config, "CONFIG", False, "INT_ID_DEST", str(socket_id), 4, config_name="CFG_FWRD_ACD"),
                Entrada(self.config, "CONFIG", False, "CAN_TX_ID", str(can_tx_id), 12, config_name="CFG_FWRD_ACD"),
            ]
        elif tipo == "DIAG":
            header = Entrada(self.config, "CONFIG", True, "CFG_FWRD_DIAG", "11", 8, config_name="CFG_FWRD_DIAG")
            filhos = [
                Entrada(self.config, "CONFIG", False, "RESERVED", "0", 4, reserved=True, config_name="CFG_FWRD_DIAG"),
                Entrada(self.config, "CONFIG", False, "INT_ID_DEST", str(socket_id), 4, config_name="CFG_FWRD_DIAG"),
            ]
        else:
            raise ValueError(f"Tipo de regra desconhecido: {tipo}")

        self._inserir_no_config([header, *filhos])
        regra = RegraEncaminhamento(tipo=tipo, socket_id=socket_id, can_tx_id=can_tx_id, entradas=[header, *filhos])
        self.regras.append(regra)
        return regra

    def remover_regra(self, regra: RegraEncaminhamento) -> None:
        for e in regra.entradas:
            self.config.entradas.remove(e)
        self.regras.remove(regra)

    def agrupar_blocos_config(self, entradas: list[Entrada]) -> list[list[Entrada]]:
        """Agrupa entradas do bloco CONFIG em [header, filho1, filho2, ...]."""
        grupos, atual = [], []
        for e in entradas:
            if e.is_comment or e.block != "CONFIG":
                continue
            if e.cfg:
                if atual:
                    grupos.append(atual)
                atual = [e]
            elif atual:
                atual.append(e)
        if atual:
            grupos.append(atual)
        return grupos

    def _inserir_no_config(self, entradas: list[Entrada]) -> None:
        """Insere um grupo de entradas (header CFG_ + filhos) no config,
        logo antes do bloco [PROTECTION], e mantém configs_dict sincronizado."""
        idx = next(
            (i for i, e in enumerate(self.config.entradas) if e.block == "PROTECTION"),
            len(self.config.entradas),
        )
        for offset, entrada in enumerate(entradas):
            self.config.entradas.insert(idx + offset, entrada)
            if not entrada.is_comment and entrada.block == "CONFIG":
                self.config.preenche_config_dict(self.config, entrada)

    def remover_bloco(self, config: ADCConfig, grupo: list[Entrada]) -> None:
        for e in grupo:
            config.entradas.remove(e)

class SessionConfig:
    def __init__(self):
        self._configs = {}
        self._ativo = None

    def adicionar_config(self, config: ADCConfig) -> None:
        chave = config.id
        if chave in self._configs:
            raise ValueError(f"Config {chave} já carregada nesta sessão.")
        self._configs[chave] = config
        self._ativo = chave

    def clear(self) -> None:
        self._configs.clear()
        self._ativo = None

    def remover_config(self, id: str) -> None:
        self._configs.pop(id, None)
        if self._ativo == id:
            self._ativo = next(iter(self._configs), None)

    def selecionar(self, id: str) -> ADCConfig:
        chave = id
        if chave not in self._configs:
            raise KeyError(f"Config {chave} não está na sessão.")
        self._ativo = chave
        return self._configs[chave]

    @property
    def ativo(self) -> Optional[ADCConfig]:
        return self._configs.get(self._ativo)

    def listar(self) -> list[ADCConfig]:
        return list(self._configs.values())

    def esta_vazia(self) -> bool:
        return not self._configs

    def __repr__(self) -> str:
        return f"SessionConfig(ativo={self._ativo}, configs={list(self._configs.keys())})"

class BancoDadosConfig:
    def __init__(self):
        self.bd_data = {}

        try:
            arquivo_json = "bd_config.json"
            with open(arquivo_json, 'r', encoding='utf-8') as file:
                self.bd_data = json.load(file)
        except:
            raise RuntimeError(f"Erro ao carregar o arquivo {arquivo_json}.")

    def obter_valores(self, cfg_name) -> Optional[dict]:
        try:
            return self.bd_data[str(cfg_name)]
        except KeyError:
            raise ValueError(f"Configuração '{cfg_name}' não encontrada no banco de dados.")

class TipoADC(Enum):
    AEB = "2"
    COM = "108"


class Entrada:
    def __init__(self, config, block: str, cfg: bool, identificator: str, valor: Any, num_bits: str, reserved: bool = False, comentario: Optional[str] = None, is_comment: bool = False, config_name: Optional[str] = ""):
        self.config = config
        self.block = block
        self.cfg = cfg
        self.identificator = identificator
        self.num_bits = num_bits
        self.valor = valor
        self.reserved = reserved
        self.comentario = comentario
        self.is_comment = is_comment
        self.config_name = config_name

    def validar(self) -> bool:
        return Validador.valida_entrada(self, self.config)

    def __repr__(self) -> str:
        return f"Entrada(block={self.block!r}, cfg={self.cfg!r}, identificator={self.identificator!r}, valor={self.valor!r}, num_bits={self.num_bits!r}, reserved={self.reserved!r}, comentario={self.comentario!r}, is_comment={self.is_comment!r})"
    
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
            "COMPONENT": ("108" if tipo == TipoADC.COM else "2"),
            "VERSION": "",
        }

    def adicionar_entrada(self, entrada: Entrada) -> None:
        self.entradas.append(entrada)

    def preenche_config_dict(self, config: ADCConfig, entrada: Entrada) -> None:
        if entrada.cfg:
            chave = f"{config.tipo.name}:{entrada.identificator}"
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
                "nome": entrada.identificator,
                "num_bit": entrada.num_bits,
                "range": entrada.valor,
                "id": f"{entrada.num_bits}:{entrada.valor}",
                "origem": config.tipo.name,
                "entradas": [],
            }

    def __repr__(self) -> str:
        return f"ADCConfig(id={self.id['id']!r}, tipo={self.tipo}, entradas={self.entradas})"


class Validador:
    bd = BancoDadosConfig()

    def validar_config(self, config: ADCConfig) -> bool:
        for entrada in config.entradas:
            if not Validador.valida_entrada(entrada, config):
                return False
        return True

    @staticmethod
    def valida_entrada(entrada: Entrada, config: ADCConfig) -> bool:
        tipo_config = config.tipo.name.lower() if config.tipo == TipoADC.COM else config.tipo.name
        if entrada.is_comment:
            return True

        identificator = entrada.identificator
        numero_bits = entrada.num_bits
        valor = entrada.valor
        bloco = entrada.block
        config_name = entrada.config_name

        # TESTE EM 3 CAMADAS: ID, CONFIG, PROTECTION
        # TESTE PARA IDENTIFICATION
        if bloco == "IDENTIFICATION":
            if identificator == "ID":
                if numero_bits != 12:
                    raise ValueError(f"ID deve ter 12 bits, mas tem {numero_bits}.")
                if valor != config.id:
                    raise ValueError(f"ID do arquivo ({valor}) nao corresponde ao ID da configuracao ({config.id}).")
            elif identificator == "CHANNEL":
                if numero_bits != 4:
                    raise ValueError(f"CHANNEL deve ter 4 bits, mas tem {numero_bits}.")
                if valor != "0":
                    raise ValueError(f"CHANNEL deve ser 0, mas tem {valor}.")
            else:
                raise ValueError(f"Identificador desconhecido no bloco IDENTIFICATION: {identificator}")
            
        # TESTE PARA CONFIG
        elif bloco == "CONFIG":
            dict_referencia = Validador.bd.obter_valores(f"{tipo_config}:{(config_name if config_name else identificator)}")
            if entrada.cfg:
                conta_reserved = 0
                if identificator != dict_referencia["nome"]:
                    raise ValueError(f"Nome da entrada ({identificator}) nao corresponde ao nome de referencia ({dict_referencia['nome']}).")

                if numero_bits != dict_referencia["num_bit"]:
                    raise ValueError(f"Num bits ({numero_bits}) da entrada {identificator} nao corresponde ao num bits de referencia ({dict_referencia['num_bit']}).")

                if dict_referencia["range"] and isinstance(dict_referencia["range"], dict):
                    if dict_referencia["range"]["tipo"] == "range":
                        if int(valor) < dict_referencia["range"]["min"] or int(valor) > dict_referencia["range"]["max"]:
                            raise ValueError(f"Valor ({valor}) da entrada {identificator} esta fora do range de referencia ({dict_referencia['range']}).")
                    elif dict_referencia["range"]["tipo"] == "enum":
                        if int(valor) not in dict_referencia["range"]["valores"]:
                            raise ValueError(f"Valor ({valor}) da entrada {identificator} esta fora do range de referencia ({dict_referencia['range']}).")    
                else:
                    if int(valor) != dict_referencia["range"]:
                        raise ValueError(f"Valor da entrada ({valor}) nao corresponde ao valor de referencia ({dict_referencia['range']}).")

                if dict_referencia["origem"] != tipo_config:
                    raise ValueError(f"Origem da entrada ({tipo_config}) nao corresponde a origem de referencia ({dict_referencia['origem']}).")
            else:
                if entrada.reserved:
                    candidatos = (e for e in dict_referencia["entradas"] if e["nome"] == identificator)
                    if candidatos:
                        entrada_referencia = next(itertools.islice(candidatos, conta_reserved, None), None)
                        conta_reserved += 1
                else:
                    entrada_referencia = next((e for e in dict_referencia["entradas"] if e["nome"] == identificator), None)

                if entrada_referencia is None:
                    raise ValueError(f"Entrada {identificator} nao encontrada na lista de referencias.")

                if entrada_referencia["num_bit"] != numero_bits:
                    raise ValueError(f"Num bits ({numero_bits}) da entrada {identificator} nao corresponde ao num bits de referencia ({entrada_referencia['num_bit']}).")

                if entrada_referencia["valor_range"] and isinstance(entrada_referencia["valor_range"], dict):
                    if entrada_referencia["valor_range"]["tipo"] == "range":
                        if int(valor) < entrada_referencia["valor_range"]["min"] or int(valor) > entrada_referencia["valor_range"]["max"]:
                            raise ValueError(f"Valor ({valor}) da entrada {identificator} esta fora do range de referencia ({entrada_referencia['valor_range']}).")
                    elif entrada_referencia["valor_range"]["tipo"] == "enum":
                        if int(valor) not in entrada_referencia["valor_range"]["valores"]:
                            raise ValueError(f"Valor ({valor}) da entrada {identificator} esta fora do range de referencia ({entrada_referencia['valor_range']}).")

                elif entrada_referencia["valor_range"]:
                    if int(valor) != int(entrada_referencia["valor_range"]):
                        raise ValueError(f"Valor da entrada ({valor}) nao corresponde ao valor de referencia ({entrada_referencia['valor_range']}).")

                elif not entrada_referencia["valor_range"]:
                    if int(valor) > 2**int(entrada_referencia["num_bit"]) - 1:
                        raise ValueError(f"Valor ({valor}) da entrada {identificator} esta fora do range de referencia (0 a {2**int(entrada_referencia['num_bit']) - 1}).")

                else:
                    raise ValueError(f"Valor de referencia nao definido para a entrada {identificator}.")
                
        #TESTE PARA PROTECTION
        elif bloco == "PROTECTION":
            if identificator not in config.protection:
                raise ValueError(f"Identificador desconhecido no bloco PROTECTION: {identificator}")

            if identificator == "COMPONENT":
                if numero_bits != 8:
                    raise ValueError(f"Num bits da entrada ({numero_bits}) nao corresponde ao num bits de referencia (8).")
                if valor not in TipoADC._value2member_map_:
                    raise ValueError(f"Valor da entrada ({valor}) esta fora do range de referencia.")

            elif identificator == "VERSION":
                if numero_bits != 48:
                    raise ValueError(f"Num bits da entrada ({numero_bits}) nao corresponde ao num bits de referencia (48).")
                if not valor.startswith("0x"):
                    raise ValueError(f"Valor da entrada ({valor}) deve estar no formato hexadecimal (ex: 0x1A).")
                date = datetime.strptime(f"{valor.split('0x')[1]}", "%Y%m%d%H%M")
                if date > datetime.now():
                    raise ValueError(f"Valor de VERSION ({valor}) nao pode ser maior que a data atual.")
        else:
            raise ValueError(f"Bloco desconhecido: {bloco}")


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

        if int(config_id) < 1 or int(config_id) > 4095:
            raise ValueError("ID deve estar entre 1 e 4095.")

        if config_tipo not in TipoADC:
            raise ValueError(f"Tipo ADC desconhecido: {config_tipo}")

        config = ADCConfig(config_tipo, id=config_id)       

        esta_salvando = False
        cfg_name = None

        for linha in linhas:
            if linha.startswith("//"):
                comentario = linha.split("//", 1)[1].strip()
                config.adicionar_entrada(Entrada(config, block="", cfg=False, identificator="", valor=linha, num_bits="0", reserved=False, is_comment = True, comentario=comentario))

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

                identificator, num_bits, valor = self.obtem_valores_linha(linha)
                if identificator and num_bits and valor:

                    if linha.startswith("CFG_") and "CFG_GTWY_IP_B" not in identificator:
                        cfg_name = identificator
                    elif linha.startswith("PROTECTION"):
                        cfg_name = None
                    #                                                              |           ÚNICA EXCEÇÃO            | 
                    entrada = Entrada(config, block=block, cfg = linha.startswith("CFG_") and "CFG_GTWY_IP_B" not in identificator, identificator=identificator, valor=valor, num_bits=int(num_bits), reserved=True if linha.startswith("RESERVED") else False, is_comment=False, comentario=comentario if "//" in linha else None, config_name=cfg_name if not linha.startswith("CFG_") or "CFG_GTWY_IP_B" in identificator else None)
                    config.adicionar_entrada(entrada)
                    if not entrada.is_comment and entrada.block == "CONFIG":
                        config.preenche_config_dict(config, entrada)
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
        """Extrai os valores de uma linha do arquivo ADC e retorna como uma tupla (identificator, num_bits, valor)."""
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
    def criar_config(tipo: TipoADC, id: str) -> ADCConfig:
        return ADCConfig(tipo=tipo, id=id)


# ═══════════════════════════════════════════════════════════
# CONTROLLER
# ═══════════════════════════════════════════════════════════

class ADCController:
    def __init__(self) -> None:
        self._config:   Optional[ADCConfig] = None
        self._parser    = ADCParser()
        self._validador = Validador()
        self._bd = BancoDadosConfig()
        self._sessao = SessionConfig()
        self._encaminhamento: Optional[EncaminhamentoCOM] = None

    @property
    def sessao(self) -> Optional[SessionConfig]:
        return self._sessao

    @property
    def config(self) -> Optional[ADCConfig]:
        return self._config

    def _garantir_sessao(self) -> SessionConfig:
        if self._sessao is None:
            self._sessao = SessionConfig()
        return self._sessao

    def encerrar_sessao(self) -> None:
        self._sessao = None
        self._config = None

    def criar_config(self, tipo: TipoADC, id) -> None:
        config = ADCFactory.criar_config(tipo, id)
        sessao = self._garantir_sessao()
        sessao.adicionar_config(config) 
        self._config = config
        self._encaminhamento = EncaminhamentoCOM(config) if config.tipo == TipoADC.COM else None #None, futuramente, será EncaminhamentoAEB

    def carregar_arquivo(self, path: str) -> None:
        config = self._parser.parse(path)
        self._validador.validar_config(config)
        sessao = self._garantir_sessao()
        sessao.adicionar_config(config)
        self._config = config
        self._encaminhamento = EncaminhamentoCOM(config) if config.tipo == TipoADC.COM else None #None, futuramente, será EncaminhamentoAEB

    def trocar_config(self, id: str) -> None:
        if self._sessao is None:
            raise RuntimeError("Nenhuma sessão ativa.")
        self._config = self._sessao.selecionar(id)
        self._encaminhamento = EncaminhamentoCOM(self._config) if self._config and self._config.tipo == TipoADC.COM else None #None, futuramente, será EncaminhamentoAEB

    def remover_config(self, id: str) -> None:
        if self._sessao is None:
            return
        self._sessao.remover_config(id)
        self._config = self._sessao.ativo
        if self._sessao.esta_vazia():
            self._sessao = None
        if self._config is None:
            self._encaminhamento = None
        
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
        self._entrada_por_item: dict[str, Entrada] = {}

    def renderizar_campos(self, config: ADCConfig, comment_state: bool) -> None:
        for widget in self.winfo_children():
            widget.destroy()
        self._vars.clear()
        self._entrada_por_item.clear()

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
                    item_id = treeview.insert("", "end", values=("","","", entrada.comentario), tags=("comment",))
                    self._entrada_por_item[item_id] = entrada
            else:
                if entrada.block == "IDENTIFICATION":

                    if not title_id:
                        treeview.insert("", "end", values=("IDENTIFICATION",) + ("",) * (len_columns - 1), tags=("title",))
                        title_id = True

                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    item_id = treeview.insert("", "end", values=values)
                    self._entrada_por_item[item_id] = entrada

                elif entrada.block == "CONFIG":

                    if not title_config:
                        treeview.insert("", "end", values=("CONFIG",) + ("",) * (len_columns - 1), tags=("title",))
                        title_config = True

                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    true_grey_false_white = not true_grey_false_white if entrada.cfg else true_grey_false_white

                    if entrada.cfg:
                        item_id = treeview.insert("", "end", values=values, tags=("style_cfg_bold",) if true_grey_false_white else ("style_cfg_bold_white",))
                    else:
                        item_id = treeview.insert("", "end", values=values, tags=("grey/white",) if true_grey_false_white else ())
                    self._entrada_por_item[item_id] = entrada

                elif entrada.block == "PROTECTION":
                    if not title_protection:
                        treeview.insert("", "end", values=(" PROTECTION",) + ("",) * (len_columns - 1), tags=("title",))
                        title_protection = True

                    values = (entrada.identificator, entrada.num_bits, entrada.valor) + ((entrada.comentario,) if comment_state and entrada.comentario else ())
                    item_id = treeview.insert("", "end", values=values)
                    self._entrada_por_item[item_id] = entrada
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

        entrada = self._entrada_por_item.get(rowid)
        if entrada is None:
            return

        self.entryPopup = EntryPopup(self, treeview, rowid, int(column[1:])-1, text, entrada)
        self.entryPopup.place(x=x, y=y + pady, width=width, height=height, anchor="w")


    def coletar_dados(self) -> dict[str, str]:
        #for identificator, value in self._vars.items():
        #    print(f"Coletando dados: {identificator} = {value}")
        return {identificator: value for identificator, num_bit, value in self._vars.items()}

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
    COLUNA_PARA_ATRIBUTO = {
        0: "identificator",
        1: "num_bits",
        2: "valor",
        3: "comentario",
    }

    def __init__(self, parent, treeview, iid, column, text, entrada, **kw):
        super().__init__(parent, **kw)
        self.tv = treeview
        self.iid = iid
        self.column = column
        self.entrada = entrada

        self.insert(0, text)
        self['exportselection'] = False

        self.focus_force()
        self.select_all()
        self.bind("<Return>", self.on_return)
        self.bind("<Escape>", lambda e: self.destroy())

    def on_return(self, event):
        self.salvar()

    def select_all(self, *ignore):
        self.selection_range(0, tk.END)
        return 'break'

    def salvar(self, event=None):
        novo_valor = self.get()
        atributo = self.COLUNA_PARA_ATRIBUTO.get(self.column)

        if atributo is None:
            self.destroy()
            return

        valor_anterior = getattr(self.entrada, atributo)
        setattr(self.entrada, atributo, novo_valor)

        try:
            self.entrada.validar()
        except Exception as exc:
            setattr(self.entrada, atributo, valor_anterior)
            messagebox.showerror("Valor inválido", str(exc))
            self.destroy()
            return

        self.tv.set(self.iid, self.column, novo_valor)
        self.destroy()

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
        sidebar = tk.Frame(self._root, bg="#dde3ec", padx=8, pady=8)
        sidebar.pack(fill="y", side="left")

        self.lista = tk.Listbox(sidebar, height=5, bg="#f0f0f0", font=("Segoe UI", 9))
        tk.Label(sidebar, text="Configurações", bg="#dde3ec", font=("Segoe UI", 9, "bold")).pack(anchor="w")

        tk.Label(
            self._root, textvariable=self._status_var,
            anchor="w", bg="#dde3ec", fg="#333",
            font=("Segoe UI", 8), relief="sunken",
        ).pack(fill="x", side="bottom")

        self.atualiza_sessoes()

        toolbar = tk.Frame(self._root, bg="#dde3ec", pady=4)
        toolbar.pack(fill="x")

        for label, cmd in [
            ("Nova config",     self._on_nova_config),
            ("Nova sessão", self._on_nova_sessao),
            ("Abrir config",   self._on_abrir),
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

        lbf = tk.LabelFrame(central, text="Endereçamento", bg="#f0f0f0", font=("Segoe UI", 9, "bold"))
        lbf.pack(fill="both", expand=True, padx=10, pady=10)

        self._campos_enderecamento: dict[str, tk.StringVar] = {}

        campos = [
            ("IP1", "ip1"),
            ("IP2", "ip2"),
            ("MÁSCARA", "mascara"),
            ("DEFAULT GW", "gateway"),
        ]

        for linha, (texto, chave) in enumerate(campos):
            ttk.Label(lbf, text=texto).grid(row=linha, column=0, sticky="w", padx=4)
            var = tk.StringVar(value="—")
            ttk.Entry(lbf, width=20, state="disabled", textvariable=var).grid(
                row=linha, column=1, sticky="ew", padx=4
            )
            self._campos_enderecamento[chave] = var
            
        self._frame_tabela = ttk.Frame(lbf, relief="solid", borderwidth=1)
        self._frame_tabela.grid(row=len(campos), column=0, columnspan=2, sticky="nsew", padx=10, pady=15)

        ttk.Label(
            self._frame_tabela,
            text="FDS",
            width=10,
            anchor="center"
        ).grid(row=0, column=0, sticky="nsew")


        ttk.Label(
            self._frame_tabela,
            text="IPs dos FDS' que receberão\ninformação da placa COM",
            relief="groove",
            anchor="center"
        ).grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        ttk.Label(
            self._frame_tabela,
            text="FADC",
            width=10,
            anchor="center"
        ).grid(row=1, column=0, sticky="nsew")

        ttk.Label(
            self._frame_tabela,
            text="IDs das AEBs que receberão\ndados de contagem relacionados\naos IPs de FADC",
            relief="groove",
            anchor="center"
        ).grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

        self._frame_destino = ttk.Frame(lbf, relief="solid", borderwidth=1)
        self._frame_destino.grid(row=len(campos), column=0, columnspan=2, sticky="nsew", padx=10, pady=15)

        # Ajuste de expansão
        lbf.columnconfigure(1, weight=1)
        self._frame_tabela.columnconfigure(1, weight=1)

        self.atualiza_campos_enderecamento()
        self.atualiza_dados_encaminhamento()

    def atualiza_campos_enderecamento(self) -> None:
        if not hasattr(self, "_campos_enderecamento"):
            return

        config = self._controller.config
        if config is None or config.tipo != TipoADC.COM:
            for var in self._campos_enderecamento.values():
                var.set("—")
            return

        self._campos_enderecamento["ip1"].set(self._obter_ip_str(config, "MY_IP_NW1"))
        self._campos_enderecamento["ip2"].set(self._obter_ip_str(config, "MY_IP_NW2"))
        self._campos_enderecamento["gateway"].set(self._obter_ip_str(config, "DFLT_GTWY_IP"))

        mask1 = config.obter_entrada("MY_MASK_NW1")
        mask2 = config.obter_entrada("MY_MASK_NW2")
        partes = []
        if mask1 is not None:
            partes.append(f"NW1: /{mask1.valor}")
        if mask2 is not None and str(mask2.valor) != "0":
            partes.append(f"NW2: /{mask2.valor}")
        self._campos_enderecamento["mascara"].set(" | ".join(partes) if partes else "—")

    def _obter_ip_str(self, config: ADCConfig, prefixo: str) -> str:
        """Monta 'a.b.c.d' a partir das 4 entradas <prefixo>_B1..B4. '—' se nenhuma existir."""
        entradas = [config.obter_entrada(f"{prefixo}_B{i}") for i in range(1, 5)]
        if all(e is None for e in entradas):
            return "—"
        return ".".join(str(e.valor) if e is not None else "0" for e in entradas)

    def atualiza_dados_encaminhamento(self) -> None:
        # atualiza visualização de destinos/regra de encaminhamento na UI
        if not hasattr(self, "_frame_tabela") or self._frame_tabela is None:
            return
        
        for w in self._frame_tabela.winfo_children():
            w.destroy()

        enc = getattr(self._controller, '_encaminhamento', None)
        if enc is None:
            ttk.Label(self._frame_tabela, text="Nenhum encaminhamento (não é configuração COM)").grid(row=0, column=0, sticky="w", padx=6, pady=6)
            return

        # Cabeçalhos
        ttk.Label(self._frame_tabela, text="Socket", width=10, anchor="w").grid(row=0, column=0, sticky="w", padx=6)
        ttk.Label(self._frame_tabela, text="Rede", width=6, anchor="w").grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(self._frame_tabela, text="IP", anchor="w").grid(row=0, column=2, sticky="w", padx=6)

        for i, destino in enumerate(enc.destinos, start=1):
            ip_str = '.'.join(str(b) for b in destino.ip)
            ttk.Label(self._frame_tabela, text=str(destino.socket_id)).grid(row=i, column=0, sticky="w", padx=6)
            ttk.Label(self._frame_tabela, text=str(destino.rede)).grid(row=i, column=1, sticky="w", padx=6)
            ttk.Label(self._frame_tabela, text=ip_str).grid(row=i, column=2, sticky="w", padx=6)

    def atualiza_sessoes(self) -> None:
        self.lista.delete(0, tk.END)
        sessoes = self._controller.sessao._configs if self._controller._sessao else {}

        for _, configs in [("Sessão atual", sessoes)]:
            if configs:
                for session_id in configs:
                    self.lista.insert(tk.END, session_id)
            else:
                self.lista.insert(tk.END, "—")

        self.lista.pack(fill="both", expand=True, pady=(8, 0))
        self.atualiza_dados_encaminhamento()
        self.atualiza_campos_enderecamento()

    def on_double_click_sessao(self, event) -> None:
        selection = self.lista.curselection()
        if not selection:
            return
        index = selection[0]
        session_id = self.lista.get(index)
        if session_id == "—":
            return
        try:
            self._controller.trocar_config(session_id)
            self.mostrar_config()
            self._status(f"Sessão ativa: {session_id}")
        except Exception as exc:
            self._erro(exc)

    def toggle_comentarios(self) -> None:
        if self._form is None or self._controller.config is None:
            return
        self._form.renderizar_campos(self._controller.config, self.toggle_var.get())

    def bind_eventos(self) -> None:
        self._root.bind("<Control-o>", lambda _e: self._on_abrir())
        self._root.bind("<Control-s>", lambda _e: self._on_salvar())
        self.lista.bind("<Double-Button-1>", self.on_double_click_sessao)

    def mostrar_config(self) -> None:
        config = self._controller.config
        if config is None:
            return
        self._id_var.set(config.id or "—")
        self._tipo_var.set(config.tipo.name)
        self._form.renderizar_campos(config, self.toggle_var.get())
        self.atualiza_campos_enderecamento()

    def _on_nova_sessao(self) -> None:
        response = messagebox.askyesno("Confirmação", "Sua sessão atual será encerrada. Deseja continuar?")
        if not response:
            return
        self._controller.encerrar_sessao()
        self.mostrar_config()
        self.atualiza_sessoes()
        self._status("Nova sessão criada.")

    def _on_nova_config(self) -> None:
        dialog = _DialogNovaConfig(self._root)
        tipo = dialog.resultado
        if tipo is None:
            return
        id = dialog.id
        if id is None or not id.isdigit() or int(id) < 1 or int(id) > 4095:
            messagebox.showerror("Erro", "ID inválido. Deve ser um número entre 1 e 4095.")
            return
        try:
            self._controller.criar_config(tipo, id)
            self.mostrar_config()
            self.atualiza_sessoes()
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
            self.atualiza_sessoes()
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
            self._status("Nenhuma configuracao carregada para aplicar.")
            return
        self.atualiza_sessoes()
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
            
        tk.Label(self, text="Digite um ID:", padx=16, pady=12).pack()
        self._id_var = tk.StringVar()
        tk.Entry(self, textvariable=self._id_var).pack(pady=(0, 12), padx=16, fill="x")

        tk.Button(self, text="Criar", command=self._confirmar,
                  bg="#4a6fa5", fg="white", padx=10, pady=4).pack(pady=12)

        
        self.wait_window()

    def _confirmar(self) -> None:
        self.resultado = TipoADC[self._var.get()]
        self.id = self._id_var.get()
        self.destroy()


# ═══════════════════════════════════════════════════════════
# Ponto de entrada
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    MainView().iniciar()