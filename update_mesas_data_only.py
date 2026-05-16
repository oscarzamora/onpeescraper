from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onpe_scraper.scraper import OnpeExtractor


HEADERS = [
    "codigo_mesa",
    "ubigeo",
    "local_votacion",
    "electores_habiles",
    "votos_emitidos",
    "votos_validos",
    "blancos",
    "nulos",
    "impugnados",
    "estado_acta",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Actualiza solo output/mesas_data.txt para mesas no contabilizadas"
    )
    parser.add_argument("--mesas-data", default="output/mesas_data.txt")
    parser.add_argument(
        "--base-url",
        default="https://resultadoelectoral.onpe.gob.pe/presentacion-backend",
    )
    parser.add_argument("--id-eleccion", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--pause-seconds", type=float, default=0.0)
    parser.add_argument("--max-workers", type=int, default=5)
    return parser


def row_from_mesa_data(mesa_data: object) -> list[str]:
    return [
        str(getattr(mesa_data, "codigo_mesa")),
        str(getattr(mesa_data, "id_ubigeo")),
        str(getattr(mesa_data, "local_votacion")),
        str(getattr(mesa_data, "electores_habiles")),
        str(getattr(mesa_data, "votos_emitidos")),
        str(getattr(mesa_data, "votos_validos")),
        str(getattr(mesa_data, "blancos")),
        str(getattr(mesa_data, "nulos")),
        str(getattr(mesa_data, "impugnados")),
        str(getattr(mesa_data, "estado_acta")),
    ]


def main() -> int:
    args = build_parser().parse_args()
    mesas_data_path = Path(args.mesas_data)

    if not mesas_data_path.exists():
        print(f"No existe el archivo: {mesas_data_path}")
        return 1

    extractor = OnpeExtractor(
        base_url=args.base_url,
        id_eleccion=args.id_eleccion,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        max_workers=args.max_workers,
    )

    ordered_codes: list[str] = []
    rows_by_code: dict[str, list[str]] = {}
    pending_codes: list[str] = []

    with mesas_data_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            codigo = extractor.normalize_mesa_code(str(row.get("codigo_mesa", "")).strip())
            if not codigo:
                continue

            current_row = [
                codigo,
                str(row.get("ubigeo", "")).strip(),
                str(row.get("local_votacion", "")).strip(),
                str(row.get("electores_habiles", "")).strip(),
                str(row.get("votos_emitidos", "")).strip(),
                str(row.get("votos_validos", "")).strip(),
                str(row.get("blancos", "")).strip(),
                str(row.get("nulos", "")).strip(),
                str(row.get("impugnados", "")).strip(),
                str(row.get("estado_acta", "")).strip(),
            ]

            if codigo not in rows_by_code:
                ordered_codes.append(codigo)
            rows_by_code[codigo] = current_row

            estado = current_row[9].strip().casefold()
            if estado != "contabilizada":
                pending_codes.append(codigo)

    if not pending_codes:
        print("No hay mesas no contabilizadas para actualizar.")
        return 0

    print(f"Mesas no contabilizadas detectadas: {len(pending_codes)}")

    updated = 0
    without_data = 0

    with ThreadPoolExecutor(max_workers=max(1, min(args.max_workers, 5))) as executor:
        futures = {
            executor.submit(extractor.fetch_mesa, code): code for code in pending_codes
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                payload = future.result()
                acta = extractor.extract_acta(payload)
                if not acta:
                    without_data += 1
                    continue
                mesa_data = extractor.build_mesa_data(acta)
                rows_by_code[code] = row_from_mesa_data(mesa_data)
                updated += 1
            except Exception:
                without_data += 1

    final_rows = [rows_by_code[c] for c in ordered_codes if c in rows_by_code]
    with mesas_data_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(HEADERS)
        writer.writerows(final_rows)

    print(f"Mesas actualizadas: {updated}")
    print(f"Mesas sin data/actualizacion: {without_data}")
    print(f"Archivo actualizado: {mesas_data_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
