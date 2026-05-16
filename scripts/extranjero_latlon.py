from __future__ import annotations

# Flujo principal:
# 1. Leer ubigeo_extranjero.txt                  → ubigeo → (pais, ciudad)
# 2. Leer mesas_data.txt                         → ubigeo → local_votacion (primera por ubigeo)
# 3. Armar lista deduplicada de queries (primario: local+ciudad+pais, fallback: ciudad+pais)
# 4. Ejecutar todas las queries contra Nominatim (1 request por query única)
# 5. Mapear resultados a ubigeos y escribir ubigeo_extranjero_lat_lon.txt

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


COUNTRY_ALIASES: dict[str, str] = {
    "ANTILLAS HOLANDESAS": "ARUBA",
    "GRAN BRETAÑA": "REINO UNIDO",
}

CITY_ALIASES: dict[str, str] = {
    "LONDRES": "LONDON",
}

# Última capa de seguridad para casos conocidos difíciles de geocodificar.
UBIGEO_COORD_OVERRIDES: dict[str, tuple[str, str]] = {
    "920101": ("12.5013629", "-69.9618475"),
    "941204": ("51.5074456", "-0.1277653"),
}


class GeocodingError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Geocoder
# ---------------------------------------------------------------------------

class NominatimGeocoder:
    def __init__(self, delay_seconds: float = 1.1, timeout: int = 30) -> None:
        self.delay_seconds = max(0.0, delay_seconds)
        self.timeout = timeout
        # cache: query_string → (lat, lon) | None
        self._cache: dict[str, tuple[str, str] | None] = {}

    def geocode(self, query: str) -> tuple[str, str] | None:
        """Geocodifica un texto libre. Devuelve (lat, lon) o None si no encuentra."""
        key = query.upper().strip()
        if key in self._cache:
            return self._cache[key]

        url = (
            "https://nominatim.openstreetmap.org/search"
            f"?format=jsonv2&limit=1&addressdetails=0&q={quote(query)}"
        )
        headers = {
            "User-Agent": "onpescraper-extranjero-latlon/2.0 (+local-script)",
            "Accept": "application/json",
        }
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise GeocodingError(f"Error HTTP al geocodificar '{query}': {exc}") from exc

        try:
            results = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GeocodingError(f"Respuesta no JSON para '{query}'.") from exc

        if not isinstance(results, list) or len(results) == 0:
            self._cache[key] = None
            self._sleep()
            return None

        first = results[0]
        lat = str(first.get("lat", "")).strip()
        lon = str(first.get("lon", "")).strip()
        result = (lat, lon) if lat and lon else None
        self._cache[key] = result
        self._sleep()
        return result

    def prewarm(self, queries: list[str]) -> None:
        """Ejecuta todas las queries únicas (no cacheadas) contra la API en orden."""
        pending = [q for q in queries if q.upper().strip() not in self._cache]
        unique_pending = list(dict.fromkeys(pending))  # mantener orden, sin duplicados
        total = len(unique_pending)
        print(f"Queries a resolver: {total}", flush=True)
        for i, q in enumerate(unique_pending, 1):
            result = self.geocode(q)
            status = f"{result[0]}, {result[1]}" if result else "no encontrado"
            print(f"  [{i}/{total}] {q!r} → {status}", flush=True)

    def _sleep(self) -> None:
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)


# ---------------------------------------------------------------------------
# Carga de archivos
# ---------------------------------------------------------------------------

def load_extranjero(path: Path) -> dict[str, dict[str, str]]:
    """ubigeo → {pais, ciudad, continente}"""
    result: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        header = [h.strip() for h in header]
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            row = {header[i]: parts[i].strip() for i in range(min(len(header), len(parts)))}
            ubigeo = row.get("ubigeo", "").strip()
            if ubigeo:
                result[ubigeo] = row
    return result


def load_local_votacion(path: Path, ubigeos: set[str]) -> dict[str, str]:
    """ubigeo → local_votacion (primera aparición por ubigeo)."""
    result: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        header = [h.strip() for h in header]
        try:
            idx_ubigeo = header.index("ubigeo")
            idx_local = header.index("local_votacion")
        except ValueError as exc:
            raise GeocodingError(f"Columna no encontrada en mesas_data: {exc}") from exc

        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= max(idx_ubigeo, idx_local):
                continue
            ubigeo = parts[idx_ubigeo].strip()
            if ubigeo not in ubigeos or ubigeo in result:
                continue
            local = parts[idx_local].strip()
            if local:
                result[ubigeo] = local
    return result


def normalize_place(pais: str, ciudad: str) -> tuple[str, str]:
    normalized_country = COUNTRY_ALIASES.get(pais, pais)
    normalized_city = CITY_ALIASES.get(ciudad, ciudad)
    return normalized_country, normalized_city


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def build_queries(
    extranjero: dict[str, dict[str, str]],
    local_votacion: dict[str, str],
) -> dict[str, list[str]]:
    """
    Para cada ubigeo devuelve una lista ordenada de queries:
    1) local_votacion, ciudad, pais
    2) pais, ciudad
    3) ciudad, pais
    """
    queries: dict[str, list[str]] = {}
    for ubigeo, info in extranjero.items():
        pais_raw = info.get("pais", "").strip()
        ciudad_raw = info.get("ciudad", "").strip()
        pais, ciudad = normalize_place(pais_raw, ciudad_raw)
        local = local_votacion.get(ubigeo, "").strip()
        fallback_pc = f"{pais}, {ciudad}"
        fallback_cp = f"{ciudad}, {pais}"
        fallback_pc_raw = f"{pais_raw}, {ciudad_raw}"
        fallback_cp_raw = f"{ciudad_raw}, {pais_raw}"

        candidates: list[str] = []
        if local:
            candidates.append(f"{local}, {ciudad}, {pais}")
        candidates.append(fallback_pc)
        candidates.append(fallback_cp)
        candidates.append(fallback_pc_raw)
        candidates.append(fallback_cp_raw)

        # dedupe manteniendo orden
        queries[ubigeo] = list(dict.fromkeys(candidates))
    return queries


def resolve_coords(
    queries: dict[str, list[str]],
    geocoder: NominatimGeocoder,
) -> dict[str, tuple[str, str]]:
    """ubigeo → (lat, lon). Prueba candidatos en orden hasta encontrar match."""
    # 1. Prewarm con todas las queries únicas
    all_queries: list[str] = []
    for candidates in queries.values():
        all_queries.extend(candidates)
    geocoder.prewarm(all_queries)

    # 2. Mapear resultados
    coords: dict[str, tuple[str, str]] = {}
    for ubigeo, candidates in queries.items():
        result: tuple[str, str] | None = None
        for query in candidates:
            result = geocoder.geocode(query)
            if result:
                break
        if result is None and ubigeo in UBIGEO_COORD_OVERRIDES:
            result = UBIGEO_COORD_OVERRIDES[ubigeo]
        if result:
            coords[ubigeo] = result
    return coords


def write_output(
    extranjero: dict[str, dict[str, str]],
    coords: dict[str, tuple[str, str]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("ubigeo\tlat\tlon\n")
        for ubigeo in extranjero:
            if ubigeo in coords:
                lat, lon = coords[ubigeo]
                fh.write(f"{ubigeo}\t{lat}\t{lon}\n")
            else:
                fh.write(f"{ubigeo}\t\t\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera ubigeo_extranjero_lat_lon.txt enriqueciendo cada ubigeo extranjero "
            "con coordenadas obtenidas de Nominatim (local+ciudad+pais, fallback pais+ciudad)."
        )
    )
    parser.add_argument(
        "--extranjero",
        type=Path,
        default=Path("output/ubigeo_extranjero.txt"),
        help="Archivo TSV con ubigeo, Continente, pais, ciudad.",
    )
    parser.add_argument(
        "--mesas",
        type=Path,
        default=Path("output/mesas_data.txt"),
        help="Archivo TSV con codigo_mesa, ubigeo, local_votacion, ...",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/ubigeo_extranjero_lat_lon.txt"),
        help="Archivo TSV de salida con ubigeo, lat, lon.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.1,
        help="Segundos de espera entre requests a Nominatim (default: 1.1 — límite ToS).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout por request HTTP en segundos (default: 30).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    geocoder = NominatimGeocoder(
        delay_seconds=max(1.0, args.delay),  # respetar ToS de Nominatim: ≥1 s entre requests
        timeout=max(1, args.timeout),
    )

    print(f"Cargando {args.extranjero} ...", flush=True)
    extranjero = load_extranjero(args.extranjero)
    print(f"  {len(extranjero)} ubigeos extranjeros", flush=True)

    print(f"Cargando {args.mesas} ...", flush=True)
    local_votacion = load_local_votacion(args.mesas, set(extranjero.keys()))
    print(f"  {len(local_votacion)} ubigeos con local_votacion encontrado", flush=True)

    queries = build_queries(extranjero, local_votacion)
    coords = resolve_coords(queries, geocoder)

    con_coords = sum(1 for v in coords.values() if v)
    sin_coords = len(extranjero) - con_coords
    print(f"\nResultados: {con_coords} con coords, {sin_coords} sin coords", flush=True)

    write_output(extranjero, coords, args.output)
    print(f"Archivo escrito: {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())