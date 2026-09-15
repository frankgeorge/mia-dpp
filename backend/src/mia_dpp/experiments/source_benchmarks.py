"""Shared source pages used by normalization experiments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkPage:
    name: str
    label: str
    url: str
    relationships: tuple[tuple[str, str], ...] = ()


BENCHMARK_PAGES = (
    BenchmarkPage(
        name="afriso",
        label="AFRISO TankControl 25",
        url=(
            "https://www.afriso.com/products/domestic-technology/"
            "level-indicators-and-level-controllers/tankcontrol-20-25/"
            "52161-fuellstandmessgeraet-tankcontrol-25"
        ),
        relationships=(
            ("Operating temperature range", "Medium"),
            ("Operating temperature range", "Ambient"),
            ("Operating temperature range", "Storage"),
            ("Submersible probe", "IP68"),
            ("Housing", "IP54"),
        ),
    ),
    BenchmarkPage(
        name="apple-macbook-air",
        label="Apple MacBook Air specifications",
        url="https://www.apple.com/macbook-air/specs/",
    ),
    BenchmarkPage(
        name="raspberry-pi-5",
        label="Raspberry Pi 5",
        url="https://www.raspberrypi.com/products/raspberry-pi-5/",
    ),
    BenchmarkPage(
        name="framework-laptop-13",
        label="Framework Laptop 13",
        url="https://frame.work/products/laptop13-diy-intel-ultra-1",
    ),
    BenchmarkPage(
        name="cisco-catalyst-9200",
        label="Cisco Catalyst 9200 Series data sheet",
        url=(
            "https://www.cisco.com/c/en/us/products/collateral/switches/"
            "catalyst-9200-series-switches/nb-06-cat9200-ser-data-sheet-cte-en.html"
        ),
    ),
)
