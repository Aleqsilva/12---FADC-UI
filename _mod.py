import os
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# Try to import from the main application
try:
    from trackplan_api import TrackplanAPI as TrackplanService
    from trackplan_api import TrackplanXMLData, TrackplanLoadedState, TrackplanAssetBundle
    TRACKPLAN_AVAILABLE = True
except ImportError:
    TRACKPLAN_AVAILABLE = False
    TrackplanService = None
    TrackplanXMLData = None
    TrackplanLoadedState = None
    TrackplanAssetBundle = None

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    ImageTk = None
    ImageDraw = None
    ImageFont = None

# Module state
_loaded_data = None  # TrackplanLoadedState
_element_images = None  # TrackplanAssetBundle


def open_fds_recovery(zip_path: str) -> Dict[str, Any]:
    global _loaded_data, _element_images

    try:
        if not os.path.exists(zip_path):
            return {'success': False, 'error': f'File not found: {zip_path}'}

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            xml_files = [f for f in zip_ref.namelist() if f.endswith('.xml')]

            trackplan_content = None
            fds_config_content = None

            for xml_name in xml_files:
                with zip_ref.open(xml_name) as f:
                    content = f.read()
                    if 'Trackplan' in xml_name:
                        trackplan_content = content
                    elif 'FdsConfig' in xml_name:
                        fds_config_content = content


            if trackplan_content is None:
                return {'success': False, 'error': 'Trackplan.xml not found in zip'}

            try:
                trackplan_root = ET.fromstring(trackplan_content)
                print(type(trackplan_root))
                xml_data = TrackplanService.parse_trackplan_xml(trackplan_root, 'Trackplan.xml')
                _loaded_data = TrackplanService.populate_loaded_trackplan(xml_data)
            except Exception as e:
                return {'success': False, 'error': f'Error parsing Trackplan.xml: {str(e)}'}

            try:
                _element_images = TrackplanService.load_element_images()
                if not PIL_AVAILABLE:
                    return {
                        'success': True,
                        'trackplan_data': _loaded_data,
                        'error': 'PIL/Pillow not available - images will not render'
                    }
            except Exception as e:
                _element_images = TrackplanAssetBundle()

            return {
                'success': True,
                'trackplan_data': _loaded_data,
                'fds_config_data': fds_config_content,
                'element_images': _element_images,
                'error': None
            }

    except zipfile.BadZipFile:
        return {'success': False, 'error': 'Invalid ZIP file'}
    except Exception as e:
        return {'success': False, 'error': f'Unexpected error: {str(e)}'}


def get_trackplan_elements() -> Optional[List[Dict[str, Any]]]:
    global _loaded_data
    if _loaded_data is None:
        return None
    return _loaded_data.elements


def get_trackplan_metadata() -> Dict[str, Any]:
    global _loaded_data
    if _loaded_data is None:
        return {}
    return {
        'grid_width': _loaded_data.grid_width,
        'grid_height': _loaded_data.grid_height,
        'next_element_id': _loaded_data.next_element_id,
        'element_count': len(_loaded_data.elements) if _loaded_data.elements else 0,
        'rails': len(_loaded_data.trackplan_data.get('rails', {})) if _loaded_data.trackplan_data else 0,
        'sensors': len(_loaded_data.trackplan_data.get('sensors', {})) if _loaded_data.trackplan_data else 0,
        'fmas': len(_loaded_data.trackplan_data.get('fmas', {})) if _loaded_data.trackplan_data else 0,
        'links': len(_loaded_data.trackplan_data.get('links', {})) if _loaded_data.trackplan_data else 0,
        'crossings': len(_loaded_data.trackplan_data.get('crossing_dict', {})) if _loaded_data.trackplan_data else 0,
    }


def has_images() -> bool:
    global _element_images
    return _element_images is not None and len(_element_images.normal_images) > 0


def get_image(key: str, image_size: int = 30) -> Optional[Any]:
    global _element_images
    if _element_images is None:
        return None

    if key in _element_images.normal_images:
        return _element_images.normal_images[key]

    if key in _element_images.blue_images:
        return _element_images.blue_images[key]

    for k, v in _element_images.fma_preview_images.items():
        if k.endswith(key) or key in k:
            return v

    return None


def get_element_image(element_type: str, angle: int, mirror: int = 0,
                     image_size: int = 30) -> Optional[Any]:
    key_map = {
        'rail': f'rail_{angle}_{mirror}',
        'switch': f'switch_{angle}_{mirror}',
        'link': f'link_{angle}',
        'crossing': f'crossing_{angle}',
        'sensor': f'sensor_{angle}',
        'fma': None,
    }

    key = key_map.get(element_type)
    if key is None:
        return None

    return get_image(key, image_size)
