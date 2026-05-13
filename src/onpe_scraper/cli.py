from __future__ import annotations

import argparse
from pathlib import Path

from .scraper import OnpeExtractor


def build_parser() -> argparse.ArgumentParser:
    # Expone los parámetros operativos del scraper para correrlo desde consola.
    parser = argparse.ArgumentParser(description="Extractor ONPE 2026 basado en mesas faltantes")
    parser.add_argument(
        "--input",
        default="source_data/MesasFaltantes.txt",
        help="Ruta del TXT con las mesas faltantes",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directorio donde se escribirán los TXT generados",
    )
    parser.add_argument("--base-url", default="https://resultadoelectoral.onpe.gob.pe/presentacion-backend", help="Base URL del servicio de mesa")
    parser.add_argument("--id-eleccion", type=int, default=10, help="Identificador de elección a procesar")
    parser.add_argument("--timeout", type=int, default=30, help="Tiempo de espera por petición en segundos")
    parser.add_argument("--pause-seconds", type=float, default=0.0, help="Pausa entre peticiones para reducir carga")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Cantidad máxima de mesas a procesar en paralelo (tope interno: 5)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Cantidad de mesas por lote antes de concatenar resultados",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        default=True,
        help="Actualizar (upsert) resultados en los TXT existentes en lugar de reconstruirlos desde cero",
    )
    return parser


def main() -> int:
    # Lee argumentos y resuelve compatibilidad con rutas antiguas de entrada.
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists() and input_path.suffix.lower() == ".txt":
        legacy_csv = input_path.with_suffix(".csv")
        if legacy_csv.exists():
            input_path = legacy_csv
    output_dir = Path(args.output_dir)

    # Construye el extractor con la configuración elegida por el usuario.
    extractor = OnpeExtractor(
        base_url=args.base_url,
        id_eleccion=args.id_eleccion,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        max_workers=args.max_workers,
        batch_size=args.batch_size,
    )

    # Ejecuta la extracción completa y resume el resultado al final.
    summary = extractor.run(input_path, output_dir, append=args.append)

    print("Extracción completada")
    print(f"Mesas en listado: {summary['mesas_en_listado']}")
    print(f"Mesas procesadas: {summary['mesas_procesadas']}")
    print(f"Mesas sin data: {summary['mesas_sin_data']}")
    print(f"Agrupaciones únicas: {summary['agrupaciones_unicas']}")
    print(f"Votos registrados: {summary['votos_registrados']}")
    print(f"Mesas faltantes actualizadas: {summary['mesas_faltantes']}")
    return 0
