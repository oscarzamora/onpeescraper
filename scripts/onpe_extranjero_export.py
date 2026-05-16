from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://resultadoelectoral.onpe.gob.pe/main/presidenciales",
}


@dataclass(frozen=True)
class UbigeoItem:
    ubigeo: str
    nombre: str


class OnpeApiError(RuntimeError):
    pass


class OnpeClient:
    def __init__(self, base_url: str = BASE_URL, retries: int = 3, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.timeout = timeout

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = urlencode(params or {})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                request = Request(url, headers=DEFAULT_HEADERS)
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8", errors="replace").strip()

                lowered = body[:120].lower()
                if lowered.startswith("<!doctype html") or lowered.startswith("<html"):
                    raise OnpeApiError(
                        "La API devolvio HTML en lugar de JSON. "
                        "Reintenta en unos minutos o valida acceso a ONPE desde tu red."
                    )

                payload = json.loads(body)
                if payload.get("success") is False:
                    raise OnpeApiError(
                        f"ONPE reporto error en {path}: {payload.get('message', 'sin detalle')}"
                    )
                return payload
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OnpeApiError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(1.2 * attempt)
                    continue
                raise OnpeApiError(f"No se pudo consultar {url}: {exc}") from exc

        raise OnpeApiError(f"No se pudo consultar {url}: {last_error}")

    def get_active_election_id(self) -> int:
        payload = self._get_json("/proceso/proceso-electoral-activo")
        data = payload.get("data") or {}
        election_id = data.get("idEleccionPrincipal")
        if not isinstance(election_id, int):
            raise OnpeApiError("No se encontro idEleccionPrincipal en el proceso activo.")
        return election_id

    def list_level1_foreign(self, election_id: int) -> list[UbigeoItem]:
        payload = self._get_json(
            "/ubigeos/departamentos",
            {"idEleccion": election_id, "idAmbitoGeografico": 2},
        )
        return [UbigeoItem(item["ubigeo"], item["nombre"]) for item in payload.get("data", [])]

    def list_countries(self, election_id: int, continent_code: str) -> list[UbigeoItem]:
        payload = self._get_json(
            "/ubigeos/provincias",
            {
                "idEleccion": election_id,
                "idAmbitoGeografico": 2,
                "idUbigeoDepartamento": continent_code,
            },
        )
        return [UbigeoItem(item["ubigeo"], item["nombre"]) for item in payload.get("data", [])]

    def list_cities(self, election_id: int, country_code: str) -> list[UbigeoItem]:
        payload = self._get_json(
            "/ubigeos/distritos",
            {
                "idEleccion": election_id,
                "idAmbitoGeografico": 2,
                "idUbigeoProvincia": country_code,
            },
        )
        return [UbigeoItem(item["ubigeo"], item["nombre"]) for item in payload.get("data", [])]


def build_rows(client: OnpeClient, election_id: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    continents = client.list_level1_foreign(election_id)

    for continent in continents:
        countries = client.list_countries(election_id, continent.ubigeo)
        for country in countries:
            cities = client.list_cities(election_id, country.ubigeo)
            for city in cities:
                rows.append(
                    {
                        "ubigeo": city.ubigeo,
                        "Continente": continent.nombre,
                        "pais": country.nombre,
                        "ciudad": city.nombre,
                    }
                )

    rows.sort(key=lambda row: (row["Continente"], row["pais"], row["ciudad"]))
    return rows


def write_tsv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ubigeo", "Continente", "pais", "ciudad"]

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exporta EXTRANJERO de ONPE en formato ubigeo,Continente,pais,ciudad"
        )
    )
    parser.add_argument(
        "--election-id",
        type=int,
        default=None,
        help="ID de eleccion ONPE (si no se especifica, usa el proceso activo).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/extranjero-ubigeo-continente-pais-ciudad.txt"),
        help="Ruta del TXT (TSV) de salida.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Ruta opcional para guardar tambien en JSON.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Numero de reintentos por request (default: 3).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = OnpeClient(retries=max(1, args.retries))
    election_id = args.election_id or client.get_active_election_id()

    rows = build_rows(client, election_id)

    write_tsv(rows, args.output)

    if args.json_output is not None:
        write_json(rows, args.json_output)

    countries_count = len({(row["Continente"], row["pais"]) for row in rows})
    print(f"idEleccion={election_id}")
    print(f"paises={countries_count}")
    print(f"ciudades={len(rows)}")
    print(f"txt={args.output.as_posix()}")
    if args.json_output is not None:
        print(f"json={args.json_output.as_posix()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
