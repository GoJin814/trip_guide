from pathlib import Path

import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
MAP_COMPONENT = components.declare_component(
    "trip_map", path=str(ROOT / "map_component")
)
