"""
Utilitários para XML do Trackplan/FDS.

Funções aqui ajudam a manter consistência entre diferentes geradores.
"""
from typing import Optional
import xml.etree.ElementTree as ET

def normalize_trackplan_order(root: ET.Element) -> None:
    """Reordena nós do Trackplan para uma ordem consistente.

    - Dentro de <Track>: Rail → Sensor → Fma (ordem estável intra-grupo)
    - No nível raiz: Fds → Stations → Track → Supervisors → Cubicles (outros ao final)
    """
    try:
        # Ordenar filhos de <Track>
        track_elem = root.find("Track")
        if track_elem is not None:
            order_map = {"Rail": 0, "Sensor": 1, "Fma": 2}
            children = list(track_elem)
            children.sort(key=lambda el: order_map.get(el.tag, 99))
            track_elem[:] = children

        # Ordenar filhos do <Trackplan>
        root_order = {"Fds": 0, "Stations": 1, "Track": 2, "Supervisors": 3, "Cubicles": 4}
        root_children = list(root)
        root_children.sort(key=lambda el: root_order.get(el.tag, 99))
        root[:] = root_children
    except Exception:
        # Não interromper fluxo em caso de falhas de ordenação
        pass
