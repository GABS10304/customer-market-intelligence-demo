"""Demo-Modus: fiktive Produkt- und Cluster-Namen (keine RIWA-Bezeichner)."""

from __future__ import annotations

from config import DEMO_MODE

GIS_BEREICH = "geoSuiteData" if DEMO_MODE else "riwaGisData"
TERA_WIN_BEREICH = "erpSuiteData" if DEMO_MODE else "teraWinData"
BUILD_BEREICH = "buildSuiteData" if DEMO_MODE else "otsBauData"

GIS_PLATFORM_LABEL = "GeoSuite" if DEMO_MODE else "RIWA GIS"
TERA_PLATFORM_LABEL = "ERP Suite Demo" if DEMO_MODE else "TERA"
CLIENT_LABEL = "GeoClient" if DEMO_MODE else "RGZ Client"
MAP_APP_LABEL = "MapApp Demo" if DEMO_MODE else "KartenApp"
