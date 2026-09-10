#!/usr/bin/env python3
"""
API reutilizavel para Trackplan.xml.

Este modulo concentra a logica que pode ser consumida por outros projetos:
- leitura e parse de Trackplan.xml
- geracao de Trackplan.xml
- populacao de estado carregado para canvas/modelo
- carregamento de imagens de ativos
- geracao de imagens de FMA e helpers de animacao
"""

from __future__ import annotations

import math
import os
import xml.dom.minidom
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple, Union

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageTk = None

try:
    from .xml_utils import normalize_trackplan_order
except Exception:
    from xml_utils import normalize_trackplan_order


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _value_from_field(field: Any, default_value: Any) -> Any:
    if field is None:
        return default_value
    if hasattr(field, "get"):
        try:
            value = field.get()
            return value if value not in (None, "") else default_value
        except Exception:
            return default_value
    return field if field not in (None, "") else default_value


def _photoimage_from_pil(
    pil_image: Any,
    name_prefix: str = "image",
    photoimage_factory: Optional[Callable[[Any, str], Any]] = None,
) -> Any:
    if pil_image is None:
        return None

    if photoimage_factory is not None:
        return photoimage_factory(pil_image, name_prefix)

    if PIL_AVAILABLE and ImageTk is not None:
        return ImageTk.PhotoImage(pil_image)

    return pil_image


def _app_base_dir() -> Path:
    return Path(getattr(__import__("sys"), "_MEIPASS", Path(__file__).resolve().parent))


def resource_path(*parts: str) -> str:
    return str(_app_base_dir().joinpath(*parts))


@dataclass
class TrackplanElementData:
    xml_element: ET.Element
    x: int = field(init=False)
    y: int = field(init=False)
    angle: int = field(init=False)

    def __post_init__(self) -> None:
        self.x = _safe_int(self.xml_element.get("x", 0))
        self.y = _safe_int(self.xml_element.get("y", 0))
        self.angle = _safe_int(self.xml_element.get("angle", 0))


@dataclass
class RailData(TrackplanElementData):
    rail_id: Optional[str] = field(init=False)
    mirror: int = field(init=False)
    rail_type: str = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.rail_id = self.xml_element.get("id")
        self.mirror = _safe_int(self.xml_element.get("mirror", 0))
        self.rail_type = self.xml_element.get("type", "RAIL")


@dataclass
class LinkData(TrackplanElementData):
    link_id: Optional[str] = field(init=False)
    url: Optional[str] = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.link_id = self.xml_element.get("id")
        self.url = self.xml_element.get("url")


@dataclass
class SensorData(TrackplanElementData):
    sensor_id: Optional[str] = field(init=False)
    name: str = field(init=False)
    ref_id: Optional[str] = field(init=False)
    fma0: Optional[str] = field(init=False)
    fma1: Optional[str] = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.sensor_id = self.xml_element.get("id")
        self.name = self.xml_element.get("name", f"S{self.sensor_id}")
        self.ref_id = self.xml_element.get("refId", self.sensor_id)
        self.fma0 = self.xml_element.get("fma0")
        self.fma1 = self.xml_element.get("fma1")


@dataclass
class CrossingData(TrackplanElementData):
    crossing_id: Optional[str] = field(init=False)
    paths: list[dict[str, Optional[str]]] = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.crossing_id = self.xml_element.get("id")
        self.paths = []
        for path in self.xml_element.findall(".//Path"):
            self.paths.append({"from": path.get("from"), "to": path.get("to")})


@dataclass
class FMAData(TrackplanElementData):
    fma_id: Optional[str] = field(init=False)
    name: str = field(init=False)
    ref_id: str = field(init=False)
    associated_sensors: list[dict[str, str]] = field(init=False)
    associated_rails: list[dict[str, str]] = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.fma_id = self.xml_element.get("id")
        self.name = self.xml_element.get("name", f"FMA{self.fma_id}")
        self.ref_id = self.xml_element.get("refId", "")
        self.associated_sensors = []
        self.associated_rails = []

        for rail_ref in self.xml_element.findall(".//Rails/Ref"):
            rail_id = rail_ref.get("refId")
            if not rail_id:
                continue

            item: dict[str, str] = {"refId": str(rail_id).strip()}

            from_attr = rail_ref.get("from")
            to_attr = rail_ref.get("to")
            if from_attr is not None and str(from_attr).strip() != "":
                item["from"] = str(from_attr).strip()
            if to_attr is not None and str(to_attr).strip() != "":
                item["to"] = str(to_attr).strip()
            if "from" in item or "to" in item:
                item["type"] = "crossing"

            self.associated_rails.append(item)

        sensor_nodes: list[ET.Element] = []
        sensor_nodes.extend(self.xml_element.findall(".//Sensors/Ref"))
        sensor_nodes.extend(self.xml_element.findall(".//Sensors/Sensor"))

        for sref in sensor_nodes:
            sid = sref.get("refId") or sref.get("id")
            if not sid:
                continue

            pos = (sref.get("fmaPosition") or sref.get("position") or "").strip().lower()
            if pos not in ("left", "right"):
                pos = "right"

            self.associated_sensors.append({"refId": str(sid), "fmaPosition": pos})


@dataclass
class TrackplanXMLData:
    root: ET.Element
    filename: str
    rails: list[RailData] = field(init=False)
    links: list[LinkData] = field(init=False)
    sensors: list[SensorData] = field(init=False)
    fmas: list[FMAData] = field(init=False)
    crossings: list[CrossingData] = field(init=False)
    rails_dict: dict[str, ET.Element] = field(init=False)
    links_dict: dict[str, ET.Element] = field(init=False)
    sensors_dict: dict[str, ET.Element] = field(init=False)
    fmas_dict: dict[str, ET.Element] = field(init=False)
    crossing_dict: dict[str, ET.Element] = field(init=False)

    def __post_init__(self) -> None:
        self.rails = [RailData(rail) for rail in self.root.findall(".//Rail")]
        self.links = [LinkData(link) for link in self.root.findall(".//Link")]
        self.sensors = [SensorData(sensor) for sensor in self.root.findall(".//Sensor")]
        self.fmas = [FMAData(fma) for fma in self.root.findall(".//Fma")]
        self.crossings = [CrossingData(crossing) for crossing in self.root.findall(".//Crossing")]

        self.rails_dict = {rail.rail_id: rail.xml_element for rail in self.rails if rail.rail_id}
        self.links_dict = {link.link_id: link.xml_element for link in self.links if link.link_id}
        self.sensors_dict = {sensor.sensor_id: sensor.xml_element for sensor in self.sensors if sensor.sensor_id}
        self.fmas_dict = {fma.fma_id: fma.xml_element for fma in self.fmas if fma.fma_id}
        self.crossing_dict = {crossing.crossing_id: crossing.xml_element for crossing in self.crossings if crossing.crossing_id}


@dataclass
class TrackplanLoadedState:
    elements: list[dict[str, Any]]
    grid_width: int
    grid_height: int
    next_element_id: int
    trackplan_data: dict[str, Any]


@dataclass
class TrackplanAssetBundle:
    normal_images: dict[str, Any] = field(default_factory=dict)
    blue_images: dict[str, Any] = field(default_factory=dict)
    fma_preview_images: dict[str, Any] = field(default_factory=dict)
    missing_images: list[str] = field(default_factory=list)
    missing_blue_images: list[str] = field(default_factory=list)


class TrackplanAPI:
    """API reutilizavel para parsing, geracao e assets de Trackplan."""

    @staticmethod
    def parse_trackplan_xml(source: Union[str, bytes, ET.ElementTree, Any], filename: Optional[str] = None) -> TrackplanXMLData:
        if isinstance(source, (ET.ElementTree, ET.Element)):
            root = source.getroot() if isinstance(source, ET.ElementTree) else source
            return TrackplanXMLData(root, filename or "from_element")   # <-- adicionar
        if isinstance(source, bytes):
            root = ET.fromstring(source)
            return TrackplanXMLData(root, filename or "from_bytes")
        if isinstance(source, str):
            tree = ET.parse(source)
            return TrackplanXMLData(tree.getroot(), filename or source)
        tree = ET.parse(source)
        return TrackplanXMLData(tree.getroot(), filename or getattr(source, "name", "from_file"))

    @staticmethod
    def populate_loaded_trackplan(xml_data: TrackplanXMLData) -> TrackplanLoadedState:
        elements: list[dict[str, Any]] = []

        for rail in xml_data.rails:
            element = {
                "type": "switch" if rail.rail_type == "SWITCH" else "rail",
                "id": _safe_int(rail.rail_id, rail.rail_id),
                "xml_id": rail.rail_id,
                "x": rail.x,
                "y": rail.y,
                "angle": rail.angle,
                "mirror": rail.mirror,
                "rail_type": rail.rail_type,
                "auto_rail": False,
            }
            elements.append(element)

        for crossing in xml_data.crossings:
            elements.append({
                "type": "crossing",
                "id": _safe_int(crossing.crossing_id, crossing.crossing_id),
                "xml_id": crossing.crossing_id,
                "x": crossing.x,
                "y": crossing.y,
                "angle": crossing.angle,
            })

        for link in xml_data.links:
            elements.append({
                "type": "link",
                "id": _safe_int(link.link_id, link.link_id),
                "xml_id": link.link_id,
                "x": link.x,
                "y": link.y,
                "angle": link.angle,
                "url": link.url,
            })

        for sensor in xml_data.sensors:
            element = {
                "type": "sensor",
                "id": _safe_int(sensor.sensor_id, sensor.sensor_id),
                "xml_id": sensor.sensor_id,
                "x": sensor.x,
                "y": sensor.y,
                "angle": sensor.angle,
                "name": sensor.name,
                "ref_id": sensor.ref_id,
            }
            if sensor.fma0:
                element["fma0"] = str(sensor.fma0)
            if sensor.fma1:
                element["fma1"] = str(sensor.fma1)
            elements.append(element)

        for fma in xml_data.fmas:
            element = {
                "type": "fma",
                "id": _safe_int(fma.fma_id, fma.fma_id),
                "xml_id": fma.fma_id,
                "x": fma.x,
                "y": fma.y,
                "angle": fma.angle,
                "name": fma.name,
                "ref_id": fma.ref_id,
                "associated_sensors": fma.associated_sensors,
                "associated_rails": fma.associated_rails,
            }
            elements.append(element)

        grid_width, grid_height = TrackplanAPI._infer_grid_dimensions(xml_data)
        next_element_id = TrackplanAPI.update_next_element_id(elements)
        trackplan_data = {
            "root": xml_data.root,
            "filename": xml_data.filename,
            "fmas": xml_data.fmas_dict,
            "sensors": xml_data.sensors_dict,
            "rails": xml_data.rails_dict,
            "links": xml_data.links_dict,
        }

        return TrackplanLoadedState(
            elements=elements,
            grid_width=grid_width,
            grid_height=grid_height,
            next_element_id=next_element_id,
            trackplan_data=trackplan_data,
        )

    @staticmethod
    def update_next_element_id(elements: Iterable[Mapping[str, Any]]) -> int:
        max_base = 0
        for element in elements:
            raw_id = element.get("id")
            if raw_id is None:
                continue
            text = str(raw_id)
            if len(text) > 1 and text[0] in ("2", "3", "4") and text[1:].isdigit():
                base = int(text[1:])
            else:
                digits = "".join(ch for ch in text if ch.isdigit())
                if not digits:
                    continue
                try:
                    base = int(digits)
                except Exception:
                    continue
            max_base = max(max_base, base)
        return max_base + 1 if max_base > 0 else 7000

    @staticmethod
    def load_element_images(
        images_dir: Optional[Union[str, Path]] = None,
        blue_images_dir: Optional[Union[str, Path]] = None,
        grid_size: int = 30,
        fds_model: str = "FDS101",
        photoimage_factory: Optional[Callable[[Any, str], Any]] = None,
    ) -> TrackplanAssetBundle:
        bundle = TrackplanAssetBundle()

        if not PIL_AVAILABLE:
            return bundle

        images_dir = Path(images_dir or resource_path("images"))
        blue_images_dir = Path(blue_images_dir or images_dir / "blue")

        if not images_dir.exists():
            images_dir.mkdir(parents=True, exist_ok=True)
        if not blue_images_dir.exists():
            blue_images_dir.mkdir(parents=True, exist_ok=True)

        image_size = grid_size
        image_files: dict[str, str] = {}

        for angle in [0, 45, 90, 180, 225, 270, 315]:
            for mirror in [0, 1]:
                image_files[f"rail_{angle}_{mirror}"] = f"rail_{angle}_{mirror}.png"

        for angle in [0, 90, 180, 270]:
            image_files[f"link_{angle}"] = f"link_{angle}.png"

        for angle in [0, 90, 270]:
            image_files[f"crossing_{angle}"] = f"crossing_{angle}.png"

        for angle in [0, 45, 90, 180, 225]:
            for mirror in [0, 1]:
                image_files[f"switch_{angle}_{mirror}"] = f"switch_{angle}_{mirror}.png"

        for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
            image_files[f"sensor_{angle}"] = f"sensor_{angle}.png"

        for key, filename in image_files.items():
            image_path = images_dir / filename
            if not image_path.exists():
                bundle.missing_images.append(filename)
                continue
            try:
                img = Image.open(image_path)
                img = img.resize((image_size, image_size), Image.Resampling.LANCZOS)
                bundle.normal_images[key] = _photoimage_from_pil(img, f"element_{key}", photoimage_factory)
            except Exception:
                bundle.missing_images.append(filename)

        for key, filename in image_files.items():
            blue_path = blue_images_dir / filename
            if not blue_path.exists():
                bundle.missing_blue_images.append(filename)
                continue
            try:
                img = Image.open(blue_path)
                img = img.resize((image_size, image_size), Image.Resampling.LANCZOS)
                bundle.blue_images[key] = _photoimage_from_pil(img, f"blue_{key}", photoimage_factory)
            except Exception:
                bundle.missing_blue_images.append(filename)

        for angle in ([0, 90, 180, 270] if fds_model == "FDS101" else [0, 45, 90, 135, 180, 225, 270, 315]):
            preview = TrackplanAPI.create_fma_image_with_integrated_text(angle, "FMA", photoimage_factory)
            if preview is not None:
                bundle.fma_preview_images[f"fma_{angle}_PREV"] = preview

        return bundle

    @staticmethod
    def animate_fma_highlight(
        canvas: Any,
        scheduler: Any,
        element: Mapping[str, Any],
        blue_image: Any,
        restore_image_fn: Optional[Callable[[Mapping[str, Any]], None]] = None,
        duration_ms: int = 3000,
    ) -> bool:
        canvas_id = element.get("canvas_id")
        if not canvas_id:
            return False

        canvas.itemconfig(canvas_id, image=blue_image)

        if duration_ms > 0 and restore_image_fn is not None and scheduler is not None and hasattr(scheduler, "after"):
            scheduler.after(duration_ms, lambda: restore_image_fn(element))

        return True

    @staticmethod
    def create_fma_image_with_integrated_text(
        angle: int,
        text: str,
        photoimage_factory: Optional[Callable[[Any, str], Any]] = None,
    ) -> Any:
        if not PIL_AVAILABLE:
            return None

        try:
            img = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            if angle in (0, 180):
                for y in range(13, 17):
                    draw.line([(1, y), (29, y)], fill=(0, 0, 0, 255), width=1)
            elif angle in (90, 270):
                for x in range(13, 17):
                    draw.line([(x, 1), (x, 29)], fill=(0, 0, 0, 255), width=1)
            elif angle in (45, 225):
                draw.line([(1, 29), (29, 1)], fill=(0, 0, 0, 255), width=4)
            elif angle in (135, 315):
                draw.line([(1, 1), (29, 29)], fill=(0, 0, 0, 255), width=4)

            box_config = {
                0: {"type": "rect", "x1": 2, "y1": 18, "x2": 29, "y2": 28, "text_rot": 0},
                90: {"type": "rect", "x1": 18, "y1": 2, "x2": 28, "y2": 29, "text_rot": 90},
                180: {"type": "rect", "x1": 2, "y1": 3, "x2": 29, "y2": 13, "text_rot": 0},
                270: {"type": "rect", "x1": 3, "y1": 2, "x2": 13, "y2": 29, "text_rot": -90},
                45: {"type": "poly", "cx": 16, "cy": 14, "w": 13, "h": 6, "text_rot": 45},
                135: {"type": "poly", "cx": 20, "cy": 20, "w": 13, "h": 6, "text_rot": 135},
                225: {"type": "poly", "cx": 14, "cy": 16, "w": 13, "h": 6, "text_rot": 45},
                315: {"type": "poly", "cx": 10, "cy": 10, "w": 13, "h": 6, "text_rot": 135},
            }

            cfg = box_config.get(angle, box_config[0])

            def diagonal_box(cx: float, cy: float, angle_deg: float, length: float = 10, thickness: float = 4) -> list[tuple[float, float]]:
                import math

                radians = math.radians(angle_deg)
                dx = math.cos(radians)
                dy = math.sin(radians)
                px = -dy
                py = dx
                half_length = length / 2
                half_thickness = thickness / 2
                return [
                    (cx - dx * half_length - px * half_thickness, cy - dy * half_length - py * half_thickness),
                    (cx + dx * half_length - px * half_thickness, cy + dy * half_length - py * half_thickness),
                    (cx + dx * half_length + px * half_thickness, cy + dy * half_length + py * half_thickness),
                    (cx - dx * half_length + px * half_thickness, cy - dy * half_length + py * half_thickness),
                ]

            if cfg["type"] == "rect":
                draw.rectangle([(cfg["x1"], cfg["y1"]), (cfg["x2"], cfg["y2"])], outline=(0, 0, 0), fill=(255, 255, 255))
                text_cx = (cfg["x1"] + cfg["x2"]) // 2
                text_cy = (cfg["y1"] + cfg["y2"]) // 2
            else:
                pts = diagonal_box(cfg["cx"], cfg["cy"], angle, length=12, thickness=4)
                draw.polygon(pts, outline=(0, 0, 0), fill=(255, 255, 255))
                text_cx, text_cy = cfg["cx"], cfg["cy"]

            try:
                font = ImageFont.truetype("arial.ttf", 8)
            except Exception:
                font = ImageFont.load_default()

            if cfg["text_rot"] == 0:
                draw.text((text_cx, text_cy), text, fill=(0, 0, 0), font=font, anchor="mm")
            else:
                temp_img = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.text((25, 25), text, fill=(0, 0, 0), font=font, anchor="mm")
                temp_img = temp_img.rotate(-angle, expand=True)
                width, height = temp_img.size
                img.paste(temp_img, (int(text_cx - width / 2), int(text_cy - height / 2)), temp_img)

            return _photoimage_from_pil(img, f"fma_{angle}_{text}", photoimage_factory)
        except Exception:
            return None

    @staticmethod
    def create_fma_blue_image_with_integrated_text(
        angle: int,
        text: str,
        photoimage_factory: Optional[Callable[[Any, str], Any]] = None,
    ) -> Any:
        if not PIL_AVAILABLE:
            return None

        try:
            img = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            text_areas = {
                0: {"x1": 2, "y1": 18, "x2": 29, "y2": 28},
                45: {"x1": 2, "y1": 18, "x2": 13, "y2": 28},
                90: {"x1": 18, "y1": 2, "x2": 28, "y2": 29},
                135: {"x1": 17, "y1": 18, "x2": 28, "y2": 28},
                180: {"x1": 2, "y1": 3, "x2": 29, "y2": 13},
                225: {"x1": 17, "y1": 2, "x2": 28, "y2": 13},
                270: {"x1": 3, "y1": 2, "x2": 13, "y2": 29},
                315: {"x1": 2, "y1": 2, "x2": 13, "y2": 13},
            }

            if angle not in text_areas:
                angle = 0

            area = text_areas[angle]

            if angle in (0, 180):
                for y in range(13, 17):
                    draw.line([(1, y), (29, y)], fill=(0, 0, 0, 255), width=1)
            elif angle in (90, 270):
                for x in range(13, 17):
                    draw.line([(x, 1), (x, 29)], fill=(0, 0, 0, 255), width=1)
            elif angle in (45, 225):
                draw.line([(1, 29), (29, 1)], fill=(0, 0, 0, 255), width=4)
            elif angle in (135, 315):
                draw.line([(1, 1), (29, 29)], fill=(0, 0, 0, 255), width=4)

            if angle in (45, 135, 225, 315):
                rotated_boxes = {
                    45: {"cx": 20, "cy": 10, "w": 14, "h": 7, "angle": 45},
                    135: {"cx": 20, "cy": 20, "w": 14, "h": 7, "angle": 135},
                    225: {"cx": 10, "cy": 20, "w": 14, "h": 7, "angle": 45},
                    315: {"cx": 10, "cy": 10, "w": 14, "h": 7, "angle": 135},
                }
                box = rotated_boxes[angle]
                TrackplanAPI._draw_rotated_rect(
                    draw,
                    cx=box["cx"],
                    cy=box["cy"],
                    width=box["w"],
                    height=box["h"],
                    angle_deg=box["angle"],
                    outline=(0, 0, 0, 255),
                    fill=(255, 255, 255, 255),
                )
            else:
                draw.rectangle([(area["x1"], area["y1"]), (area["x2"], area["y2"])], outline=(0, 0, 0, 255), width=1, fill=(255, 255, 255, 255))

            try:
                font = ImageFont.truetype("arial.ttf", 4)
            except Exception:
                font = ImageFont.load_default()

            text_center_x = (area["x1"] + area["x2"]) // 2
            text_center_y = (area["y1"] + area["y2"]) // 2

            if angle == 90:
                temp_img = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.text((25, 25), text, fill=(0, 0, 0, 255), font=font, anchor="mm")
                temp_img = temp_img.rotate(-90, expand=False)
                img.paste(temp_img, (text_center_x - 25, text_center_y - 25), temp_img)
            elif angle == 270:
                temp_img = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.text((25, 25), text, fill=(0, 0, 0, 255), font=font, anchor="mm")
                temp_img = temp_img.rotate(90, expand=False)
                img.paste(temp_img, (text_center_x - 25, text_center_y - 25), temp_img)
            else:
                draw.text((text_center_x, text_center_y), text, fill=(0, 0, 0, 255), font=font, anchor="mm")

            return _photoimage_from_pil(img, f"fma_blue_{angle}_{text}", photoimage_factory)
        except Exception:
            return None

    @staticmethod
    def get_auto_rail_config(element_type: str, element_angle: Any) -> Tuple[int, int]:
        config = {
            "sensor": {
                0: (0, 0), 45: (270, 0), 90: (180, 0), 135: (270, 1),
                180: (0, 0), 225: (270, 0), 270: (180, 0), 315: (270, 1),
            },
            "fma": {
                0: (0, 0), 45: (270, 0), 90: (180, 0), 135: (270, 1),
                180: (0, 0), 225: (270, 0), 270: (180, 0), 315: (270, 1),
            },
        }
        try:
            angle_int = int(element_angle)
            return config.get(element_type, {}).get(angle_int, (angle_int, 0))
        except Exception:
            return (0, 0)

    @staticmethod
    def _infer_grid_dimensions(xml_data: TrackplanXMLData) -> tuple[int, int]:
        track_elem = xml_data.root.find(".//Track")
        width_val = None
        height_val = None

        if track_elem is not None:
            try:
                if str(track_elem.get("width", "")).strip():
                    width_val = int(str(track_elem.get("width")).strip())
            except Exception:
                width_val = None
            try:
                if str(track_elem.get("height", "")).strip():
                    height_val = int(str(track_elem.get("height")).strip())
            except Exception:
                height_val = None

        if width_val is None or height_val is None:
            max_x = -1
            max_y = -1
            try:
                if xml_data.rails:
                    max_x = max(max_x, max(rail.x for rail in xml_data.rails))
                    max_y = max(max_y, max(rail.y for rail in xml_data.rails))
                if xml_data.sensors:
                    max_x = max(max_x, max(sensor.x for sensor in xml_data.sensors))
                    max_y = max(max_y, max(sensor.y for sensor in xml_data.sensors))
                if xml_data.fmas:
                    max_x = max(max_x, max(fma.x for fma in xml_data.fmas))
                    max_y = max(max_y, max(fma.y for fma in xml_data.fmas))
            except Exception:
                pass

            if width_val is None:
                width_val = max_x if max_x >= 0 else 71
            if height_val is None:
                height_val = max_y if max_y >= 0 else 16

        return width_val if width_val is not None else 71, height_val if height_val is not None else 16

    @staticmethod
    def _find_real_rail_at_position(elements: Iterable[Mapping[str, Any]], position: Tuple[Any, Any]) -> Optional[Mapping[str, Any]]:
        if not position or len(position) != 2:
            return None
        x, y = position
        for element in elements:
            if element.get("x") == x and element.get("y") == y:
                return element
        return None

    @staticmethod
    def _get_rail_config_for_sensor(sensor_angle: Any) -> Tuple[int, int]:
        return TrackplanAPI.get_auto_rail_config("sensor", sensor_angle)

    @staticmethod
    def _get_rail_config_for_fma(fma_angle: Any) -> Tuple[int, int]:
        return TrackplanAPI.get_auto_rail_config("fma", fma_angle)

    @staticmethod
    def _draw_rotated_rect(draw: Any, cx: float, cy: float, width: float, height: float, angle_deg: float, outline: Any, fill: Any, line_width: int = 1) -> None:
        import math

        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        hw, hh = width / 2, height / 2

        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        rotated = [(cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a) for x, y in corners]
        draw.polygon(rotated, outline=outline, fill=fill)

    @staticmethod
    def _prettify_xml(element: ET.Element) -> str:
        rough_string = ET.tostring(element, encoding="unicode")
        reparsed = xml.dom.minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="\t", encoding=None)

    # ========== CANVAS =========

class TrackplanDesignerView():

    def __init__(self, root):
        self.root = root
        self.image_registry = {}
        self.fds_model = "FDS101"
        
    def create_trackplan_canvas(self):
        """Cria a aba do designer de Trackplan minimalista com foco na grade"""
        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True)

        # === TOOLBAR COMPACTA NO TOPO ===
        toolbar = ttk.Frame(frame, padding="3")
        toolbar.pack(fill=tk.X)
        
        # NOME DO FDS NO TOPO DO CANVAS
        fds_name_frame = ttk.Frame(frame, style="Section.TLabelframe")
        fds_name_frame.pack(fill=tk.X, padx=5, pady=(2, 0))
        
        # Configurar o grid do frame para expansão
        fds_name_frame.grid_columnconfigure(1, weight=1)

        # Variável para o nome do FDS
        self.trackplan_fds_name_var = tk.StringVar()

        # Label que mostra o nome do FDS
        self.fds_name_label = ttk.Label(fds_name_frame, 
                                    textvariable=self.trackplan_fds_name_var,
                                    font=("Segoe UI", 11, "bold"), 
                                    foreground="#1e3a5f",
                                    background="#f0f0f0",
                                    anchor="e")
        self.fds_name_label.grid(row=0, column=1, padx=5, pady=5, sticky="")

        # Atualizar nome inicial
        #self.update_trackplan_fds_name()  necessário reescrever função

        # === ÁREA DA GRADE (TELA CHEIA) ===
        canvas_frame = ttk.Frame(frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Canvas principal ocupando toda a área restante
        self.trackplan_canvas = tk.Canvas(canvas_frame, bg="white", scrollregion=(0, 0, 2400, 800))
        
        # Scrollbars
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.trackplan_canvas.xview)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.trackplan_canvas.yview)
        
        self.trackplan_canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)
        
        # Layout em grade
        self.trackplan_canvas.grid(row=0, column=0, sticky="nsew")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # === CONFIGURAR EVENTOS ===
        self.trackplan_canvas.bind("<Button-1>", self.on_canvas_click_with_focus)
        
        # === INICIALIZAR SISTEMA ===
        self.initialize_trackplan_system()
        
        # Variáveis adicionais para grade (ANTES de apply_grid)
        self.width_var = tk.StringVar(value="30")
        self.height_var = tk.StringVar(value="10")
 
        # Forçar atualização da interface antes de aplicar a grade
        self.root.update_idletasks()
        
        # Aplicar grade e atualizar preview com delay
        self.root.after(100, self.apply_grid_delayed)


    def _apply_trackplan_dimensions(self, xml_data):
        """Aplica as dimensões do trackplan à grade"""
        track_elem = xml_data.root.find(".//Track")

        width_val = None
        height_val = None

        if track_elem is not None:
            w_attr = track_elem.get("width")
            h_attr = track_elem.get("height")
            # Tentar converter atributos para int
            try:
                if w_attr is not None and str(w_attr).strip() != "":
                    width_val = int(str(w_attr).strip())
            except Exception:
                width_val = None
            try:
                if h_attr is not None and str(h_attr).strip() != "":
                    height_val = int(str(h_attr).strip())
            except Exception:
                height_val = None

            # Fallback: calcular a partir dos elementos, se necessário
            if width_val is None or height_val is None:
                max_x = -1
                max_y = -1
                try:
                    if xml_data.rails:
                        max_x = max(max_x, max(r.x for r in xml_data.rails))
                        max_y = max(max_y, max(r.y for r in xml_data.rails))
                    if xml_data.sensors:
                        max_x = max(max_x, max(s.x for s in xml_data.sensors))
                        max_y = max(max_y, max(s.y for s in xml_data.sensors))
                    if xml_data.fmas:
                        max_x = max(max_x, max(f.x for f in xml_data.fmas))
                        max_y = max(max_y, max(f.y for f in xml_data.fmas))
                except Exception as e:
                    print(f"Falha ao calcular dimensões pelo conteúdo: {e}")

                if width_val is None and max_x >= 0:
                    width_val = max_x
                if height_val is None and max_y >= 0:
                    height_val = max_y

            # Defaults finais se ainda não definidos
            if width_val is None:
                width_val = 71
            if height_val is None:
                height_val = 16

            self.width_var.set(str(width_val))
            self.height_var.set(str(height_val))
            self.apply_grid()
        else:
            print("Elemento Track não encontrado, usando dimensões padrão 71x16")
            self.width_var.set("71")
            self.height_var.set("16")
            self.apply_grid()

    def apply_grid(self):
        """Aplica a grade com números clicáveis nas margens"""
        try:
            # Valores inseridos pelo usuário são as coordenadas máximas desejadas
            max_col = int(self.width_var.get())
            max_row = int(self.height_var.get())
        except ValueError:
            messagebox.showerror("Erro", "Coluna e linha máximas devem ser números inteiros")
            return
        
        # Limpar canvas (grade, números e highlights)
        self.trackplan_canvas.delete("grid")
        self.trackplan_canvas.delete("grid_numbers")
        self.trackplan_canvas.delete("row_highlight")
        self.trackplan_canvas.delete("column_highlight")
        
        # Calcular dimensões reais
        actual_width = max_col + 1
        actual_height = max_row + 1
        
        # Configurar região de scroll
        total_width = (actual_width + 1) * self.grid_size + 100
        total_height = (actual_height + 1) * self.grid_size + 100
        self.trackplan_canvas.configure(scrollregion=(0, 0, total_width, total_height))
        
        # Desenhar linhas apenas se visível
        if getattr(self, 'grid_visible', True):
            for x in range(actual_width + 1):
                x_pos = (x + 1) * self.grid_size
                self.trackplan_canvas.create_line(
                    x_pos, self.grid_size, x_pos, (actual_height + 1) * self.grid_size,
                    fill="gray", tags="grid"
                )
            
            for y in range(actual_height + 1):
                y_pos = (y + 1) * self.grid_size
                self.trackplan_canvas.create_line(
                    self.grid_size, y_pos, (actual_width + 1) * self.grid_size, y_pos,
                    fill="gray", tags="grid"
                )
    
        # Números das colunas
        for x in range(actual_width):
            x_pos = (x + 1) * self.grid_size + self.grid_size // 2
            rect_id = self.trackplan_canvas.create_rectangle(
                (x + 1) * self.grid_size, 0, (x + 2) * self.grid_size, self.grid_size,
                fill="lightgray", outline="black", tags="grid_numbers"
            )
            text_id = self.trackplan_canvas.create_text(
                x_pos, self.grid_size // 2, text=str(x),
                font=("Arial", 8, "bold"), tags="grid_numbers"
            )
        
        # Números das linhas
        for y in range(actual_height):
            y_pos = (y + 1) * self.grid_size + self.grid_size // 2
            rect_id = self.trackplan_canvas.create_rectangle(
                0, (y + 1) * self.grid_size, self.grid_size, (y + 2) * self.grid_size,
                fill="lightgray", outline="black", tags="grid_numbers"
            )
            text_id = self.trackplan_canvas.create_text(
                self.grid_size // 2, y_pos, text=str(y),
                font=("Arial", 8, "bold"), tags="grid_numbers"
            )
        
        # Canto superior esquerdo
        corner_id = self.trackplan_canvas.create_rectangle(
            0, 0, self.grid_size, self.grid_size,
            fill="darkgray", outline="black", tags="grid_numbers"
        )
        
        grid_status = "LIGADA" if getattr(self, 'grid_visible', True) else "DESLIGADA"


    def apply_grid_delayed(self):
        """Aplica grade com delay para garantir que o canvas esteja pronto"""
        try:
            self.apply_grid()
        except Exception as e:
            print(f"Erro ao aplicar grade com delay: {e}")
            # Tentar novamente após mais tempo
            print("Tentando aplicar grade novamente em 500ms...")
            self.root.after(500, self.apply_grid)
        

    def initialize_trackplan_system(self):
        """Inicializa o sistema do trackplan"""
        try:
            # Variáveis de controle do sistema
            self.trackplan_elements = []  # Lista para armazenar elementos
            
            # Variáveis da grade
            self.grid_width = 30
            self.grid_height = 10
            self.cell_size = 20
            self.grid_size = 30  # Tamanho das células na visualização
            self.grid_visible = True 
            
            # Mapeamento de elementos por posição para busca rápida
            self.element_position_map = {}
            
            #Animação seleção cubicle
            self._overlay_anim = {}  # tag -> {'base': (x1,y1,x2,y2), 'step': 0, 'job': None}

            # Configuração de ângulos e mirrors automáticos de rail para sensores e FMAs
            self.auto_rail_config = {
                # Configuração para sensores: ângulo_sensor -> (ângulo_rail, mirror_rail)
                'sensor': {
                    0: (0, 0),       # Sensor 0° → Rail 0° mirror 0
                    45: (270, 0),     # Sensor 45° → Rail 270° mirror 0
                    90: (180, 0),     # Sensor 90° → Rail 180° mirror 0
                    135: (270, 1),   # Sensor 135° → Rail 270° mirror 1
                    180: (0, 0),   # Sensor 180° → Rail 0° mirror 0
                    225: (270, 0),   # Sensor 225° → Rail 270° mirror 0
                    270: (180, 0),   # Sensor 270° → Rail 180° mirror 0
                    315: (270, 1)    # Sensor 315° → Rail 270° mirror 1
                },
                # Configuração para FMAs: ângulo_fma -> (ângulo_rail, mirror_rail)
                'fma': {
                    0: (0, 0),       # FMA 0° → Rail 0° mirror 0
                    90: (180, 0),     # FMA 90° → Rail 180° mirror 0
                    180: (0, 0),   # FMA 180° → Rail 0° mirror 0
                    270: (180, 0),   # FMA 270° → Rail 180° mirror 0
                }
            }
            
            # Carregar imagens dos elementos
            self.load_element_images()            
        except Exception as e:
            print(f"Erro ao inicializar sistema trackplan: {e}")


    def load_element_images(self):
        """Carrega imagens dos elementos se disponíveis"""
        self.element_images = {}
        self.blue_element_images = {}  # Imagens azuis para destacamento
        try:
            # Diretório de imagens (criar pasta 'images' no mesmo diretório do script)
            images_dir = os.path.join(os.path.dirname(__file__), "images")
            blue_images_dir = os.path.join(images_dir, "blue")  # Pasta para imagens azuis
            
            if os.path.exists(images_dir):
                # Usar o tamanho completo do grid para pixel art fidedigna
                image_size = self.grid_size  # 30x30 pixels completos
                
                # Lista completa de imagens a carregar
                image_files = {}
                
                # RAILS - Combinações corretas de ângulo e mirror
                rail_angles = [0, 45, 90, 180, 225, 270, 315]
                for angle in rail_angles:
                        for mirror in [0, 1]:
                            key = f"rail_{angle}_{mirror}"
                            filename = f"rail_{angle}_{mirror}.png"
                            image_files[key] = filename
                # LINKS
                link_angles = [0, 90, 180, 270]
                for angle in link_angles:
                    key = f"link_{angle}"
                    filename = f"link_{angle}.png"
                    image_files[key] = filename

                # CROSSING Ângulos 0/90/270 
                for angle in [0, 90, 270]:
                    key = f"crossing_{angle}"
                    filename = f"crossing_{angle}.png"
                    image_files[key] = filename

                # SWITCHES - Todas as combinações de ângulo e mirror
                switch_angles = [0, 45, 90, 180, 225]
                for angle in switch_angles:
                    for mirror in [0, 1]:
                        key = f"switch_{angle}_{mirror}"
                        filename = f"switch_{angle}_{mirror}.png"
                        image_files[key] = filename
                
                # SENSORES - Ângulos padrão (sem direção para imagens normais)
                sensor_angles = [0, 45, 90, 135, 180, 225, 270, 315]
                for angle in sensor_angles:
                    key = f"sensor_{angle}"
                    filename = f"sensor_{angle}.png"
                    image_files[key] = filename
                
                # Carregar todas as imagens NORMAIS
                loaded_count = 0
                for key, filename in image_files.items():
                    image_path = os.path.join(images_dir, filename)
                    if os.path.exists(image_path):
                        try:
                            # Carregar e redimensionar imagem
                            img = Image.open(image_path)
                            img = img.resize((image_size, image_size), Image.Resampling.LANCZOS)
                            # Criar PhotoImage com correção de bug Python 3.13
                            self.element_images[key] = self.create_safe_photo_image(img, f"element_{key}")
                            if self.element_images[key]:  # Só contar se criou com sucesso
                                loaded_count += 1
                        except Exception as e:
                            print(f"Erro ao carregar imagem {filename}: {e}")
                
                # Carregar todas as imagens AZUIS (da pasta images/blue/)
                blue_loaded_count = 0
                if os.path.exists(blue_images_dir):
                    # Para rails, switches e FMAs - usar mesma estrutura das imagens normais
                    for key, filename in image_files.items():
                        # Buscar imagem azul correspondente
                        blue_image_path = os.path.join(blue_images_dir, filename)
                        if os.path.exists(blue_image_path):
                            try:
                                # Carregar e redimensionar imagem azul
                                img = Image.open(blue_image_path)
                                img = img.resize((image_size, image_size), Image.Resampling.LANCZOS)
                                # Criar PhotoImage com correção de bug Python 3.13
                                self.blue_element_images[key] = self.create_safe_photo_image(img, f"blue_element_{key}")
                                if self.blue_element_images[key]:  # Só contar se criou com sucesso
                                    blue_loaded_count += 1
                            except Exception as e:
                                print(f"Erro ao carregar imagem azul {filename}: {e}")
                    
                # Para SENSORES AZUIS - usar sistema left/right
                sensor_blue_expected = 0
                for angle in sensor_angles:
                    for direction in ['left', 'right']:
                        blue_key = f"sensor_{angle}_{direction}"
                        blue_filename = f"sensor_{angle}_{direction}.png"
                        blue_image_path = os.path.join(blue_images_dir, blue_filename)
                        sensor_blue_expected += 1
                        if os.path.exists(blue_image_path):
                            try:
                                # Carregar e redimensionar imagem azul do sensor
                                img = Image.open(blue_image_path)
                                img = img.resize((image_size, image_size), Image.Resampling.LANCZOS)
                                # Criar PhotoImage com correção de bug Python 3.13
                                self.blue_element_images[blue_key] = self.create_safe_photo_image(img, f"blue_sensor_{blue_key}")
                                if self.blue_element_images[blue_key]:  # Só contar se criou com sucesso
                                    blue_loaded_count += 1
                            except Exception as e:
                                print(f"Erro ao carregar imagem azul de sensor {blue_filename}: {e}")
                        else:
                            print("Pasta de imagens azuis não encontrada. Criando...")
                            os.makedirs(blue_images_dir, exist_ok=True)
                    sensor_blue_expected = len(sensor_angles) * 2  # left/right para cada ângulo
                
                # GERAR IMAGENS FMA DINAMICAMENTE PARA PREVIEW
                fma_preview_count = 0
                fma_angles = [0, 90, 180, 270] if self.fds_model == "FDS101" else [0, 45, 90, 135, 180, 225, 270, 315]
                for angle in fma_angles:
                    preview_key = f"fma_{angle}_PREV"
                    try:
                        dynamic_image = self.create_fma_image_with_integrated_text(angle, "FMA")
                        if dynamic_image:
                            self.element_images[preview_key] = dynamic_image
                            fma_preview_count += 1
                        else:
                            print(f"Falha ao criar: {preview_key}")
                    except Exception as e:
                        print(f"Erro ao criar {preview_key}: {e}")
                
                # Listar imagens faltantes para facilitar a criação
                missing_images = []
                missing_blue_images = []
                
                # Verificar imagens normais faltantes
                for key, filename in image_files.items():
                    image_path = os.path.join(images_dir, filename)
                    if not os.path.exists(image_path):
                        missing_images.append(filename)
                
                # Verificar imagens azuis faltantes (rails, switches, FMAs)
                for key, filename in image_files.items():
                    blue_image_path = os.path.join(blue_images_dir, filename)
                    if not os.path.exists(blue_image_path):
                        missing_blue_images.append(filename)
                
                # Verificar imagens azuis de sensores faltantes (sistema left/right)
                for angle in sensor_angles:
                    for direction in ['left', 'right']:
                        blue_sensor_filename = f"sensor_{angle}_{direction}.png"
                        blue_sensor_path = os.path.join(blue_images_dir, blue_sensor_filename)
                        if not os.path.exists(blue_sensor_path):
                            missing_blue_images.append(blue_sensor_filename)
                        
            else:
                print(f"Diretorio de imagens nao encontrado: {images_dir}")
                print("Criando estrutura de pastas...")
                os.makedirs(images_dir, exist_ok=True)
                os.makedirs(blue_images_dir, exist_ok=True)
                
        except ImportError:
            print("PIL nao encontrado. Execute: pip install Pillow")
            print("Usando desenho por linhas...")
        except Exception as e:
            print(f"Erro ao carregar imagens: {e}")


    def on_canvas_click_with_focus(self, event):
        """Evento de clique no canvas com foco automático"""
        self.trackplan_canvas.focus_set()
        return self.on_canvas_click(event)

    def on_canvas_click(self, event):
        """Evento de clique no canvas"""
        x = self.trackplan_canvas.canvasx(event.x)
        y = self.trackplan_canvas.canvasy(event.y)
        
        # Converter para coordenadas da grade (ajustar para espaço reservado das coordenadas)
        grid_x = int((x - self.grid_size) // self.grid_size)
        grid_y = int((y - self.grid_size) // self.grid_size)
        
        # Verificar se está dentro da grade válida (0 até width, 0 até height)
        try:
            width = int(self.width_var.get())
            height = int(self.height_var.get())
        except ValueError:
            width, height = 71, 16
        
        if grid_x < 0 or grid_y < 0 or grid_x > width or grid_y > height:
            return
        
        self.handle_selection_click(grid_x, grid_y, event)
        
        self.refresh_fma_test_window()


    def create_safe_photo_image(self, pil_image, name_prefix="image"):
        """Cria PhotoImage de forma segura com correção para Python 3.13 e registry"""
        try:
            from PIL import ImageTk
            
            # Criar PhotoImage
            photo_image = ImageTk.PhotoImage(pil_image)
            
            # Correção preventiva para o bug do Python 3.13
            unique_name = f"{name_prefix}_{id(photo_image)}"
            if not hasattr(photo_image, 'name'):
                photo_image.name = unique_name
            
            # Manter referência forte no registry para prevenir garbage collection
            self.image_registry[unique_name] = photo_image
            
            return photo_image
        except Exception as e:
            print(f"Erro ao criar PhotoImage seguro: {e}")
            return None
    
    def create_fma_image_with_integrated_text(self, angle, text):
        try:
            import math
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new('RGBA', (30, 30), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # --- Linha principal ---
            if angle in (0, 180):
                for y in range(13, 17):
                    draw.line([(1, y), (29, y)], fill=(0, 0, 0, 255), width=1)

            elif angle in (90, 270):
                for x in range(13, 17):
                    draw.line([(x, 1), (x, 29)], fill=(0, 0, 0, 255), width=1)

            elif angle in (45, 225):
                draw.line([(1, 29), (29, 1)], fill=(0, 0, 0, 255), width=4)

            elif angle in (135, 315):
                draw.line([(1, 1), (29, 29)], fill=(0, 0, 0, 255), width=4)

            # --- Configuração das caixas ---
            box_config = {
                0:   {'type': 'rect', 'x1': 2,  'y1': 18, 'x2': 29, 'y2': 28, 'text_rot': 0},
                90:  {'type': 'rect', 'x1': 18, 'y1': 2,  'x2': 28, 'y2': 29, 'text_rot': 90},
                180: {'type': 'rect', 'x1': 2,  'y1': 3,  'x2': 29, 'y2': 13, 'text_rot': 0},
                270: {'type': 'rect', 'x1': 3,  'y1': 2,  'x2': 13, 'y2': 29, 'text_rot': -90},

                45:  {'type': 'poly', 'cx': 16, 'cy': 14, 'w': 13, 'h': 6, 'text_rot': 45},
                135: {'type': 'poly', 'cx': 20, 'cy': 20, 'w': 13, 'h': 6, 'text_rot': 135},
                225: {'type': 'poly', 'cx': 14, 'cy': 16, 'w': 13, 'h': 6, 'text_rot': 45},
                315: {'type': 'poly', 'cx': 10, 'cy': 10, 'w': 13, 'h': 6, 'text_rot': 135},
            }

            cfg = box_config.get(angle, box_config[0])
        
            def diagonal_box(cx, cy, angle_deg, length=10, thickness=4):
                angle = math.radians(angle_deg)

                # vetor da linha
                dx = math.cos(angle)
                dy = math.sin(angle)

                # vetor perpendicular
                px = -dy
                py = dx

                # metade
                hl = length / 2
                ht = thickness / 2

                return [
                    (cx - dx*hl - px*ht, cy - dy*hl - py*ht),
                    (cx + dx*hl - px*ht, cy + dy*hl - py*ht),
                    (cx + dx*hl + px*ht, cy + dy*hl + py*ht),
                    (cx - dx*hl + px*ht, cy - dy*hl + py*ht),
                ]


            # --- Desenhar caixa ---
            if cfg['type'] == 'rect':
                draw.rectangle(
                    [(cfg['x1'], cfg['y1']), (cfg['x2'], cfg['y2'])],
                    outline=(0, 0, 0), fill=(255, 255, 255)
                )
                text_cx = (cfg['x1'] + cfg['x2']) // 2
                text_cy = (cfg['y1'] + cfg['y2']) // 2
            else:
                pts = diagonal_box(cfg['cx'], cfg['cy'], angle, length=12, thickness=4)
                draw.polygon(pts, outline=(0, 0, 0), fill=(255, 255, 255))
                text_cx, text_cy = cfg['cx'], cfg['cy']

            # --- Fonte --- 
            try:
                font = ImageFont.truetype("arial.ttf", 8)
            except:
                font = ImageFont.load_default()

            # --- Texto ---
            if cfg['text_rot'] == 0:
                draw.text((text_cx, text_cy), text, fill=(0, 0, 0), font=font, anchor="mm")
            else:
                temp_img = Image.new('RGBA', (50, 50), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)

                temp_draw.text((25, 25), text, fill=(0, 0, 0), font=font, anchor="mm")

                temp_img = temp_img.rotate(-angle, expand=True)
                
                w, h = temp_img.size
                img.paste(temp_img, (int(text_cx - w/2), int(text_cy - h/2)), temp_img)

            return self.create_safe_photo_image(img, f"fma_{angle}_{text}")

        except Exception as e:
            print(f"Erro ao criar imagem FMA com texto '{text}' (ângulo {angle}°): {e}")
            return None

    def carregar_elementos(self, elements: list[dict]) -> None:
        """Recebe a lista vinda de get_trackplan_elements() e desenha no canvas."""
        self.trackplan_elements = elements
        self.element_position_map = {(e["x"], e["y"]): e for e in elements}
        self._desenhar_elementos()

    def _desenhar_elementos(self) -> None:
        self.trackplan_canvas.delete("element")

        for el in self.trackplan_elements:
            x, y = el["x"], el["y"]
            # +1 porque a linha/coluna 0 é reservada para os números (igual ao apply_grid)
            cx = (x + 1) * self.grid_size + self.grid_size // 2
            cy = (y + 1) * self.grid_size + self.grid_size // 2

            key = self._chave_imagem(el)
            img = self.element_images.get(key)
            if img is None:
                print(f"Imagem não encontrada para elemento {el.get('type')} (key={key})")
                continue

            self.trackplan_canvas.create_image(
                cx, cy, image=img, tags=("element", f"el_{el.get('id')}")
            )

    def _chave_imagem(self, el: dict) -> str:
        tipo = el.get("type")
        angle = el.get("angle", 0)
        mirror = el.get("mirror", 0)

        if tipo in ("rail", "switch"):
            return f"{tipo}_{angle}_{mirror}"
        if tipo == "sensor":
            return f"sensor_{angle}"
        if tipo == "link":
            return f"link_{angle}"
        if tipo == "crossing":
            return f"crossing_{angle}"
        if tipo == "fma":
            return f"fma_{angle}_PREV"
        return ""

    def draw_rotated_rect(self, draw, cx, cy, width, height, angle_deg, outline, fill, line_width=1):
        print(f"Desenhando retângulo rotacionado: centro=({cx},{cy}), tamanho=({width}x{height}), ângulo={angle_deg}°")
        """Desenha um retângulo rotacionado dado centro, tamanho e ângulo."""
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        hw, hh = width / 2, height / 2

        # 4 cantos relativos ao centro
        corners = [
            (-hw, -hh),
            ( hw, -hh),
            ( hw,  hh),
            (-hw,  hh),
        ]

        # Rotacionar e transladar
        rotated = [
            (cx + x * cos_a - y * sin_a,
            cy + x * sin_a + y * cos_a)
            for x, y in corners
        ]

        draw.polygon(rotated, outline=outline, fill=fill)

    def create_fma_blue_image_with_integrated_text(self, angle, text):
        """
        Cria uma imagem FMA AZUL personalizada com texto integrado (para highlighting)
        
        Args:
            angle: Ângulo da FMA (0, 90, 180, 270)  
            text: Texto a ser integrado na imagem (ex: "2DAT", "1AT", etc)
            
        Returns:
            ImageTk.PhotoImage azul pronto para uso no canvas ou None se erro
        """
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            
            # Criar imagem 30x30 com fundo transparente
            img = Image.new('RGBA', (30, 30), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Definir posições dos quadrados de texto por ângulo - AJUSTADO 1 pixel para cima
            text_areas = {
                0:   {'x1': 2,  'y1': 18, 'x2': 29, 'y2': 28, 'rotation': 0},    # Abaixo da horizontal
                45:  {'x1': 2,  'y1': 18, 'x2': 13, 'y2': 28, 'rotation': 45},   # Canto inferior-esquerdo
                90:  {'x1': 18, 'y1': 2,  'x2': 28, 'y2': 29, 'rotation': 90},   # À direita da vertical
                135: {'x1': 17, 'y1': 18, 'x2': 28, 'y2': 28, 'rotation': 135},  # Canto inferior-direito
                180: {'x1': 2,  'y1': 3,  'x2': 29, 'y2': 13, 'rotation': 180},  # Acima da horizontal
                225: {'x1': 17, 'y1': 2,  'x2': 28, 'y2': 13, 'rotation': 225},  # Canto superior-direito
                270: {'x1': 3,  'y1': 2,  'x2': 13, 'y2': 29, 'rotation': 270},  # À esquerda da vertical
                315: {'x1': 2,  'y1': 2,  'x2': 13, 'y2': 13, 'rotation': 315},  # Canto superior-esquerdo
            }
            
            if angle not in text_areas:
                angle = 0  # Fallback para ângulo 0
            
            area = text_areas[angle]
            
            # CORES AZUIS para highlighting
            blue_line_color = (48, 48, 227, 255)      # Azul para linhas
            blue_outline_color = (48, 48, 227, 255)   # Azul para contorno
            blue_fill_color = (255, 255, 255, 255)    # Fundo BRANCO para a caixa de texto (igual às FMAs normais)
            blue_text_color = (0, 0, 0, 255)          # Texto PRETO para legibilidade no fundo branco
            
            # Desenhar linha principal baseada no ângulo - AJUSTADO 1 pixel para cima
            if angle == 0:
                # Linha horizontal: x=1,y=13 até x=29,y=17
                for y in range(13, 17):
                    draw.line([(1, y), (29, y)], fill=(0, 0, 0, 255), width=1)
            elif angle == 45:
                # Linha diagonal com espessura equivalente
                draw.line([(1, 29), (29, 1)], fill=(0, 0, 0, 255), width=4)
            elif angle == 90:
                # Linha vertical: x=13,y=0 até x=17,y=29
                for x in range(13, 17):
                    draw.line([(x, 1), (x, 29)], fill=(0, 0, 0, 255), width=1)
            elif angle == 135:
                # Linha diagonal invertida com espessura equivalente
                draw.line([(1, 1), (29, 29)], fill=(0, 0, 0, 255), width=4)
            elif angle == 180:
                # Linha horizontal invertida: x=1,y=13 até x=29,y=17
                for y in range(13, 17):
                    draw.line([(1, y), (29, y)], fill=(0, 0, 0, 255), width=1)
            elif angle == 225:
                # Linha diagonal com espessura equivalente
                draw.line([(1, 29), (29, 1)], fill=(0, 0, 0, 255), width=4)
            elif angle == 270:
                # Linha vertical invertida: x=13,y=1 até x=17,y=29
                for x in range(13, 17):
                    draw.line([(x, 1), (x, 29)], fill=(0, 0, 0, 255), width=1)
            elif angle == 315:
                # Linha diagonal com espessura equivalente
                draw.line([(1, 1), (29, 29)], fill=(0, 0, 0, 255), width=4)

            # Desenhar quadrado de texto (EM AZUL)
            # Parâmetros da caixa rotacionada por ângulo
            rotated_boxes = {
                45:  {'cx': 20, 'cy': 10, 'w': 14, 'h': 7, 'angle': 45},
                135: {'cx': 20, 'cy': 20, 'w': 14, 'h': 7, 'angle': 135},
                225: {'cx': 10, 'cy': 20, 'w': 14, 'h': 7, 'angle': 45},
                315: {'cx': 10, 'cy': 10, 'w': 14, 'h': 7, 'angle': 135},
            }

            if angle in rotated_boxes:
                b = rotated_boxes[angle]
                self.draw_rotated_rect(
                    draw,
                    cx=b['cx'], cy=b['cy'],
                    width=b['w'], height=b['h'],
                    angle_deg=b['angle'],
                    outline=(0, 0, 0, 255),
                    fill=(255, 255, 255, 255)
                )
            else:
                # Ângulos normais continuam usando draw.rectangle
                draw.rectangle([
                    (area['x1'], area['y1']),
                    (area['x2'], area['y2'])
                ], outline=(0, 0, 0, 255), width=1, fill=(255, 255, 255, 255))

            # Adicionar texto no quadrado (EM AZUL ESCURO)
            try:
                font = ImageFont.truetype("arial.ttf", 4, bold=True)  # Fonte menor para FMAs
            except:
                font = ImageFont.load_default()
            
            # Calcular centro do quadrado de texto (toda FMA já foi ajustada 1 pixel para cima)
            text_center_x = (area['x1'] + area['x2']) // 2
            text_center_y = (area['y1'] + area['y2']) // 2  # Centro normal, pois toda FMA subiu
            
            # Para ângulos 90° e 270°, criar texto rotacionado
            if angle == 90:
                # Criar imagem temporária para rotacionar o texto
                temp_img = Image.new('RGBA', (50, 50), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.text((25, 25), text, fill=blue_text_color, font=font, anchor="mm")
                temp_img = temp_img.rotate(-90, expand=False)  # Rotacionar 90° horário
                # Colar texto rotacionado na posição correta
                img.paste(temp_img, (text_center_x - 25, text_center_y - 25), temp_img)
            elif angle == 270:
                # Criar imagem temporária para rotacionar o texto
                temp_img = Image.new('RGBA', (50, 50), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.text((25, 25), text, fill=blue_text_color, font=font, anchor="mm")
                temp_img = temp_img.rotate(90, expand=False)  # Rotacionar 90° anti-horário
                # Colar texto rotacionado na posição correta
                img.paste(temp_img, (text_center_x - 25, text_center_y - 25), temp_img)
            else:
                # Texto normal (0° e 180°)
                draw.text((text_center_x, text_center_y), text, fill=blue_text_color, font=font, anchor="mm")
            
            # Converter para ImageTk.PhotoImage com correção de bug Python 3.13
            return self.create_safe_photo_image(img, f"fma_blue_{angle}_{text}")
            
        except Exception as e:
            print(f"Erro ao criar imagem FMA AZUL com texto '{text}' (ângulo {angle}°): {e}")
            return None

    def parse_cubicle_from_xml(self, cubicle_elem) -> Optional[Dict[str, Any]]:
            """Parse um elemento <Cubicle> do XML e retorna dicionário com os dados.

            Args:
                cubicle_elem: Elemento XML <Cubicle> a ser parseado

            Returns:
                Dicionário com os dados do cubicle ou None se inválido
            """
            try:
                cubicle_data = {
                    'id': cubicle_elem.get('id', ''),
                    'name': cubicle_elem.get('name', ''),
                    'height': _safe_int(cubicle_elem.get('height', '1')),
                    'x': _safe_int(cubicle_elem.get('x', '0')),
                    'y': _safe_int(cubicle_elem.get('y', '0')),
                    'angle': _safe_int(cubicle_elem.get('angle', '0')),
                }
                # Retorna apenas se tiver dados mínimos válidos
                if not cubicle_data['id'] and not cubicle_data['name']:
                    return None
                return cubicle_data
            except Exception:
                return None

    def load_cubicles_from_xml(self, trackplan_root):
        """Carrega cubicles de um arquivo Trackplan.xml"""
        cubicles_data = []
        try:
            root = trackplan_root.getroot() if isinstance(trackplan_root, ET.ElementTree) else trackplan_root
            print(f"root {root}")
            # Procurar seção de Cubicles
            if root.tag == 'Cubicles':
                cubicles_section = root
            elif root.tag == 'Trackplan':
                cubicles_section = root.find("Cubicles")
            else:
                cubicles_section = root.find('.//Cubicles')

            if cubicles_section is None:
                messagebox.showwarning("Aviso", "Arquivo XML não contém seção de Cubículos.")
                return

            
            for cubicle_elem in cubicles_section.findall("Cubicle"):
                cubicle_data = self.parse_cubicle_from_xml(cubicle_elem)
                if cubicle_data:
                    cubicles_data.append(cubicle_data)

            return cubicles_data

        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar XML: {str(e)}")


__all__ = [
    "PIL_AVAILABLE",
    "TrackplanAPI",
    "TrackplanDesignerView",
    "TrackplanAssetBundle",
    "TrackplanElementData",
    "TrackplanLoadedState",
    "TrackplanXMLData",
    "RailData",
    "LinkData",
    "SensorData",
    "CrossingData",
    "FMAData",
    "normalize_trackplan_order",
    "resource_path",
]