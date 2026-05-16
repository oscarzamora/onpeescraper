from __future__ import annotations

import csv
import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from curl_cffi import requests as curl_requests


# Representa el resultado consolidado de una mesa a nivel cabecera.
@dataclass(slots=True)
class MesaData:
    codigo_mesa: str
    id_ubigeo: str
    local_votacion: str
    electores_habiles: int
    votos_emitidos: int
    votos_validos: int
    blancos: int
    nulos: int
    impugnados: int
    estado_acta: str


# Representa una agrupación política detectada en el detalle del acta.
@dataclass(slots=True)
class AgrupacionData:
    partido_id: str
    nombre: str


# Representa el detalle de votos por mesa y agrupación.
@dataclass(slots=True)
class VotoData:
    codigo_mesa: str
    partido_id: str
    votos: int


# Agrupa todo lo extraído para una mesa durante el procesamiento paralelo.
@dataclass(slots=True)
class MesaResult:
    index: int
    codigo_mesa: str
    mesa_data: MesaData | None
    agrupaciones: list[AgrupacionData]
    votos: list[VotoData]


class OnpeExtractor:
    def __init__(
        self,
        base_url: str = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend",
        id_eleccion: int = 10,
        timeout: int = 30,
        pause_seconds: float = 0.0,
        max_workers: int = 5,
        batch_size: int = 50,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.id_eleccion = id_eleccion
        self.timeout = timeout
        self.pause_seconds = pause_seconds
        self.max_workers = max(1, min(max_workers, 5))
        self.batch_size = max(1, batch_size)
        self._thread_local = threading.local()

    @staticmethod
    def normalize_mesa_code(codigo_mesa: str) -> str:
        # Normaliza los códigos a 6 dígitos para que todas las consultas usen el mismo formato.
        return codigo_mesa.zfill(6)

    @staticmethod
    def _build_session() -> curl_requests.Session:
        # Crea una sesión HTTP con headers de navegador para obtener el JSON real de ONPE.
        session = curl_requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            }
        )
        return session

    def _get_session(self) -> curl_requests.Session:
        # Reutiliza una sesión por hilo para no recrear conexiones en cada petición.
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = self._build_session()
            self._thread_local.session = session
        return session

    def _fetch_mesa_requests(self, codigo_mesa: str) -> dict[str, Any] | None:
        # Consulta el backend de ONPE por código de mesa y devuelve el payload JSON si es válido.
        url = f"{self.base_url}/actas/buscar/mesa"
        try:
            response = self._get_session().get(
                url,
                params={"codigoMesa": codigo_mesa},
                timeout=self.timeout,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://resultadoelectoral.onpe.gob.pe/",
                },
                impersonate="chrome124",
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except (requests.RequestException, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def load_mesas(csv_path: Path) -> list[str]:
        # Lee el listado operativo, elimina duplicados y conserva solo códigos numéricos válidos.
        mesas: list[str] = []
        seen: set[str] = set()

        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if not row:
                    continue
                value = row[0].strip()
                if not value or not value.isdigit() or value in seen:
                    continue
                normalized = OnpeExtractor.normalize_mesa_code(value)
                seen.add(normalized)
                mesas.append(normalized)

        return mesas

    def fetch_mesa(self, codigo_mesa: str) -> dict[str, Any] | None:
        # Punto de acceso público para consultar una mesa ya normalizada.
        codigo_mesa = self.normalize_mesa_code(codigo_mesa)
        return self._fetch_mesa_requests(codigo_mesa)

    def extract_acta(self, payload: dict[str, Any] | None) -> dict[str, Any] | None:
        # Selecciona únicamente la acta correspondiente a la elección configurada.
        if not payload:
            return None

        data = payload.get("data")
        if not isinstance(data, list):
            return None

        for acta in data:
            if isinstance(acta, dict) and acta.get("idEleccion") == self.id_eleccion:
                return acta

        return None

    @staticmethod
    def _int_value(value: Any) -> str:
        # Convierte valores numéricos a string preservando vacíos, nunca devuelve 0 para datos faltantes.
        try:
            if value is None or value == "":
                return ""
            return str(int(value))
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def _text_value(value: Any) -> str:
        # Normaliza cualquier valor textual a string sin espacios sobrantes.
        if value is None:
            return ""
        return str(value).strip()

    def build_mesa_data(self, acta: dict[str, Any]) -> MesaData:
        # Construye la fila principal de la mesa y extrae blancos, nulos e impugnados desde el detalle.
        detalle = acta.get("detalle") if isinstance(acta.get("detalle"), list) else []

        blancos_val = next((self._int_value(item.get("adVotos")) for item in detalle if item.get("adCodigo") == "80"), "")
        nulos_val = next((self._int_value(item.get("adVotos")) for item in detalle if item.get("adCodigo") == "81"), "")
        impugnados_val = next((self._int_value(item.get("adVotos")) for item in detalle if item.get("adCodigo") == "82"), "")

        return MesaData(
            codigo_mesa=self.normalize_mesa_code(self._text_value(acta.get("codigoMesa"))),
            id_ubigeo=self._text_value(acta.get("idUbigeo")),
            local_votacion=self._text_value(acta.get("nombreLocalVotacion")),
            electores_habiles=int(self._int_value(acta.get("totalElectoresHabiles")) or 0),
            votos_emitidos=int(self._int_value(acta.get("totalVotosEmitidos")) or 0),
            votos_validos=int(self._int_value(acta.get("totalVotosValidos")) or 0),
            blancos=int(blancos_val or 0),
            nulos=int(nulos_val or 0),
            impugnados=int(impugnados_val or 0),
            estado_acta=self._text_value(acta.get("descripcionEstadoActa")),
        )

    def build_agrupaciones(self, acta: dict[str, Any]) -> list[AgrupacionData]:
        # Construye el catálogo de agrupaciones a partir del detalle publicado por ONPE.
        detalle = acta.get("detalle") if isinstance(acta.get("detalle"), list) else []
        agrupaciones: list[AgrupacionData] = []

        for item in detalle:
            if not isinstance(item, dict):
                continue
            partido_id = self._text_value(item.get("adAgrupacionPolitica"))
            nombre = self._text_value(item.get("adDescripcion"))
            if not partido_id and not nombre:
                continue
            agrupaciones.append(
                AgrupacionData(
                    partido_id=partido_id,
                    nombre=nombre,
                )
            )

        return agrupaciones

    def build_votos(self, codigo_mesa: str, acta: dict[str, Any]) -> list[VotoData]:
        # Genera el detalle de votos por agrupación para una mesa específica.
        detalle = acta.get("detalle") if isinstance(acta.get("detalle"), list) else []
        votos: list[VotoData] = []

        for item in detalle:
            if not isinstance(item, dict):
                continue
            partido_id = self._text_value(item.get("adAgrupacionPolitica"))
            votos.append(
                VotoData(
                    codigo_mesa=codigo_mesa,
                    partido_id=partido_id,
                    votos=self._int_value(item.get("adVotos")),
                )
            )

        return votos

    @staticmethod
    def _chunked(items: list[tuple[int, str]], size: int) -> list[list[tuple[int, str]]]:
        # Divide las mesas en lotes para controlar memoria, avance y paralelismo.
        return [items[index : index + size] for index in range(0, len(items), size)]

    def _process_mesa(self, index: int, codigo_mesa: str) -> MesaResult:
        # Ejecuta el ciclo completo de una mesa: consulta, filtro de acta y transformación a datasets.
        payload = self._fetch_mesa_requests(codigo_mesa)
        acta = self.extract_acta(payload)

        if acta is None:
            if self.pause_seconds > 0:
                time.sleep(self.pause_seconds)
            return MesaResult(
                index=index,
                codigo_mesa=codigo_mesa,
                mesa_data=None,
                agrupaciones=[],
                votos=[],
            )

        mesa_data = self.build_mesa_data(acta)
        agrupaciones = self.build_agrupaciones(acta)
        votos = self.build_votos(codigo_mesa, acta)

        if self.pause_seconds > 0:
            time.sleep(self.pause_seconds)

        return MesaResult(
            index=index,
            codigo_mesa=codigo_mesa,
            mesa_data=mesa_data,
            agrupaciones=agrupaciones,
            votos=votos,
        )

    @staticmethod
    def _write_tsv_headers(path: Path, headers: list[str]) -> None:
        # Crea el archivo con encabezados solo si no existe.
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(headers)

    @staticmethod
    def _write_tsv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
        # Escribe un TXT tabulado completo (solo para inicialización, use _write_tsv_headers + _append_tsv).
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(headers)
            writer.writerows(rows)

    @staticmethod
    def _append_tsv(path: Path, rows: list[list[str]]) -> None:
        # Mantiene una utilidad de append tabulado para escenarios auxiliares o extensiones futuras.
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerows(rows)

    @staticmethod
    def _load_agrupaciones_tsv(path: Path) -> OrderedDict[str, AgrupacionData]:
        # Carga agrupaciones previas para poder hacer merge incremental sin perder catálogo histórico.
        result: OrderedDict[str, AgrupacionData] = OrderedDict()
        if not path.exists():
            return result
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    partido_id, nombre = row[0], row[1]
                    key = partido_id or nombre
                    if key and key not in result:
                        result[key] = AgrupacionData(partido_id=partido_id, nombre=nombre)
        return result

    def _load_mesas_data_tsv(self, path: Path) -> OrderedDict[str, list[str]]:
        # Carga mesas previas y tolera nombres de columnas antiguos para compatibilidad hacia atrás.
        result: OrderedDict[str, list[str]] = OrderedDict()
        if not path.exists():
            return result

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                codigo_mesa_raw = row.get("codigo_mesa") or row.get("mesa") or ""
                codigo_mesa = self.normalize_mesa_code(self._text_value(codigo_mesa_raw))
                if not codigo_mesa:
                    continue

                local_votacion = row.get("local_votacion")
                if local_votacion is None:
                    local_votacion = row.get("local", "")

                electores_habiles = row.get("electores_habiles")
                if electores_habiles is None:
                    electores_habiles = row.get("habiles", "0")

                votos_emitidos = row.get("votos_emitidos")
                if votos_emitidos is None:
                    votos_emitidos = row.get("emitidos", "0")

                votos_validos = row.get("votos_validos")
                if votos_validos is None:
                    votos_validos = row.get("validos", "0")

                estado_acta = row.get("estado_acta")
                if estado_acta is None:
                    estado_acta = row.get("estado", "")

                result[codigo_mesa] = [
                    codigo_mesa,
                    self._text_value(row.get("ubigeo")),
                    self._text_value(local_votacion),
                    self._text_value(electores_habiles),
                    self._text_value(votos_emitidos),
                    self._text_value(votos_validos),
                    self._text_value(row.get("blancos")),
                    self._text_value(row.get("nulos")),
                    self._text_value(row.get("impugnados")),
                    self._text_value(estado_acta),
                ]

        return result

    def _load_votos_tsv(self, path: Path) -> list[list[str]]:
        # Carga votos previos para reemplazar solo las mesas actualizadas en modo append.
        result: list[list[str]] = []
        if not path.exists():
            return result

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                codigo_mesa_raw = row.get("codigo_mesa") or row.get("mesa") or ""
                codigo_mesa = self.normalize_mesa_code(self._text_value(codigo_mesa_raw))
                if not codigo_mesa:
                    continue
                result.append(
                    [
                        codigo_mesa,
                        self._text_value(row.get("partido_id")),
                        self._text_value(row.get("votos")),
                    ]
                )

        return result

    def _write_mesas_faltantes(self, path: Path, mesas_rows: list[list[str]]) -> int:
        # Reconstruye el listado operativo con las mesas cuyo estado todavía no es Contabilizada.
        pendientes: list[str] = []
        seen: set[str] = set()

        for row in mesas_rows:
            if len(row) < 10:
                continue
            codigo_mesa = self.normalize_mesa_code(self._text_value(row[0]))
            estado_acta = self._text_value(row[9]).casefold()
            if not codigo_mesa or estado_acta == "contabilizada":
                continue
            if codigo_mesa in seen:
                continue
            seen.add(codigo_mesa)
            pendientes.append(codigo_mesa)

        path.parent.mkdir(parents=True, exist_ok=True)
        contenido = "\n".join(pendientes)
        if contenido:
            contenido += "\n"
        path.write_text(contenido, encoding="utf-8")
        return len(pendientes)

    @staticmethod
    def _prefer_existing_path(primary: Path, legacy: Path) -> Path:
        # Prefiere el nombre actual del archivo, pero admite rutas antiguas para migraciones suaves.
        if primary.exists():
            return primary
        if legacy.exists():
            return legacy
        return primary

    def _flush_partial_data(
        self,
        agrupaciones_path: Path,
        mesas_data_path: Path,
        votos_path: Path,
        agrupaciones_unicas: OrderedDict[str, AgrupacionData],
        mesas_rows: list[list[str]],
        votos_rows: list[list[str]],
        append: bool,
        mesas_data_read_path: Path,
        votos_read_path: Path,
        mesas_actualizadas: set[str],
    ) -> None:
        # Escribe los datos acumulados hasta el punto de error de conexión.
        print("⚠ Perdida de conexión detectada. Guardando datos acumulados...", flush=True)

        agrupaciones_rows = [[item.partido_id, item.nombre] for item in agrupaciones_unicas.values()]
        mesas_rows_final = mesas_rows
        votos_rows_final = votos_rows

        if append:
            agrupaciones_existentes = self._load_agrupaciones_tsv(agrupaciones_path)
            agrupaciones_existentes_keys = set(agrupaciones_existentes.keys())
            agrupaciones_rows = [
                [item.partido_id, item.nombre]
                for key, item in agrupaciones_unicas.items()
                if key not in agrupaciones_existentes_keys
            ]

            mesas_existentes = self._load_mesas_data_tsv(mesas_data_read_path)
            mesas_existentes_keys = set(mesas_existentes.keys())
            mesas_rows_final = [
                row
                for row in mesas_rows
                if self.normalize_mesa_code(self._text_value(row[0])) not in mesas_existentes_keys
            ]

            votos_existentes = self._load_votos_tsv(votos_read_path)
            votos_existentes_keys = {
                (
                    self.normalize_mesa_code(self._text_value(row[0])),
                    self._text_value(row[1]),
                )
                for row in votos_existentes
                if len(row) >= 2
            }
            votos_rows_final = [
                row
                for row in votos_rows
                if len(row) >= 2
                and (
                    self.normalize_mesa_code(self._text_value(row[0])),
                    self._text_value(row[1]),
                )
                not in votos_existentes_keys
            ]

        # Anexa agrupaciones nuevas
        self._append_tsv(
            agrupaciones_path,
            agrupaciones_rows,
        )

        # mesas_data se guarda por upsert para reflejar cambios de estado/conteo de mesas ya existentes.
        mesas_rows_consolidadas = mesas_rows_final
        if append:
            mesas_consolidadas_map = OrderedDict(self._load_mesas_data_tsv(mesas_data_read_path))
            for row in mesas_rows:
                codigo_mesa = self.normalize_mesa_code(self._text_value(row[0]))
                if codigo_mesa:
                    mesas_consolidadas_map[codigo_mesa] = row
            mesas_rows_consolidadas = list(mesas_consolidadas_map.values())

        self._write_tsv(
            mesas_data_path,
            [
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
            ],
            mesas_rows_consolidadas,
        )

        # Anexa votos con deduplicación por mesa/partido
        votos_unicos: OrderedDict[tuple[str, str], list[str]] = OrderedDict()
        for row in votos_rows_final:
            if len(row) < 3:
                continue
            codigo_mesa = self.normalize_mesa_code(self._text_value(row[0]))
            partido_id = self._text_value(row[1])
            if not codigo_mesa:
                continue
            votos_unicos[(codigo_mesa, partido_id)] = [codigo_mesa, partido_id, self._text_value(row[2])]
        votos_rows_final = list(votos_unicos.values())
        
        self._append_tsv(
            votos_path,
            votos_rows_final,
        )
        
        print("✓ Datos guardados exitosamente", flush=True)

    def run(self, mesas_csv: Path, output_dir: Path, append: bool = False) -> dict[str, int]:
        # Orquesta toda la extracción: lee entrada, procesa lotes, consolida resultados y reescribe salidas.
        mesas = self.load_mesas(mesas_csv)
        indexed_mesas = list(enumerate(mesas))
        batches = self._chunked(indexed_mesas, self.batch_size)
        total_mesas = len(indexed_mesas)

        agrupaciones_path = output_dir / "agrupaciones.txt"
        mesas_data_path = output_dir / "mesas_data.txt"
        votos_path = output_dir / "votos.txt"

        # Crear encabezados si archivos no existen
        self._write_tsv_headers(agrupaciones_path, ["partido_id", "nombre"])
        self._write_tsv_headers(mesas_data_path, [
            "codigo_mesa", "ubigeo", "local_votacion", "electores_habiles",
            "votos_emitidos", "votos_validos", "blancos", "nulos", "impugnados", "estado_acta"
        ])
        self._write_tsv_headers(votos_path, ["codigo_mesa", "partido_id", "votos"])

        # Compatibilidad con salidas antiguas .tsv cuando se corre en modo append.
        agrupaciones_read_path = self._prefer_existing_path(agrupaciones_path, output_dir / "agrupaciones.tsv")
        mesas_data_read_path = self._prefer_existing_path(mesas_data_path, output_dir / "mesas_data.tsv")
        votos_read_path = self._prefer_existing_path(votos_path, output_dir / "votos.tsv")

        agrupaciones_existentes = self._load_agrupaciones_tsv(agrupaciones_read_path) if append else OrderedDict()
        mesas_existentes = self._load_mesas_data_tsv(mesas_data_read_path) if append else OrderedDict()
        votos_existentes_rows = self._load_votos_tsv(votos_read_path) if append else []
        agrupaciones_existentes_keys = set(agrupaciones_existentes.keys())
        mesas_existentes_keys = set(mesas_existentes.keys())
        votos_existentes_keys = {
            (
                self.normalize_mesa_code(self._text_value(row[0])),
                self._text_value(row[1]),
            )
            for row in votos_existentes_rows
            if len(row) >= 2
        }

        agrupaciones_unicas: OrderedDict[str, AgrupacionData] = (
            agrupaciones_existentes if append else OrderedDict()
        )
        mesas_rows: list[list[str]] = []
        votos_rows: list[list[str]] = []
        mesas_actualizadas: set[str] = set()

        mesas_procesadas = 0
        mesas_sin_data = 0

        try:
            for batch_number, lote in enumerate(batches, start=1):
                # Reporta el inicio del lote para seguimiento operativo en corridas largas.
                print(
                    f"Lote {batch_number}/{len(batches)}: iniciando {len(lote)} mesas",
                    flush=True,
                )
                resultados: list[MesaResult] = []
                # Procesa cada mesa del lote en paralelo y junta los resultados terminados.
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futuros = [
                        executor.submit(self._process_mesa, index, codigo_mesa)
                        for index, codigo_mesa in lote
                    ]
                    for futuro in as_completed(futuros):
                        try:
                            resultado = futuro.result()
                            resultados.append(resultado)
                        except Exception as e:
                            # Si hay error de conexión en un hilo, lo propagamos al nivel superior
                            if isinstance(e, (requests.ConnectionError, requests.Timeout, requests.ConnectTimeout)):
                                raise
                            # Otros errores se ignoran para continuar con el siguiente futuro
                            continue

                resultados.sort(key=lambda item: item.index)

                # Consolida el lote en las tres salidas lógicas: mesas, agrupaciones y votos.
                for resultado in resultados:
                    if resultado.mesa_data is None:
                        mesas_sin_data += 1
                        continue

                    mesas_procesadas += 1

                    mesa_data = resultado.mesa_data
                    mesas_rows.append(
                        [
                            mesa_data.codigo_mesa,
                            mesa_data.id_ubigeo,
                            mesa_data.local_votacion,
                            str(mesa_data.electores_habiles),
                            str(mesa_data.votos_emitidos),
                            str(mesa_data.votos_validos),
                            str(mesa_data.blancos),
                            str(mesa_data.nulos),
                            str(mesa_data.impugnados),
                            mesa_data.estado_acta,
                        ]
                    )
                    mesas_actualizadas.add(mesa_data.codigo_mesa)

                    for agrupacion in resultado.agrupaciones:
                        key = agrupacion.partido_id or agrupacion.nombre
                        if key and key not in agrupaciones_unicas:
                            agrupaciones_unicas[key] = agrupacion

                    for voto in resultado.votos:
                        votos_rows.append(
                            [
                                voto.codigo_mesa,
                                voto.partido_id,
                                str(voto.votos),
                            ]
                        )

                completadas = mesas_procesadas + mesas_sin_data
                porcentaje = (completadas / total_mesas * 100) if total_mesas else 100.0
                # Reporta avance acumulado para saber cuánto falta de la corrida completa.
                print(
                    (
                        f"Lote {batch_number}/{len(batches)}: completado "
                        f"procesadas={mesas_procesadas} sin_data={mesas_sin_data} "
                        f"avance={completadas}/{total_mesas} ({porcentaje:.1f}%)"
                    ),
                    flush=True,
                )
        except (requests.ConnectionError, requests.Timeout, requests.ConnectTimeout) as e:
            # Si pierde conexión, genera flush parcial de datos acumulados y termina
            print(f"✗ Error de conexión: {e}", flush=True)
            self._flush_partial_data(
                agrupaciones_path,
                mesas_data_path,
                votos_path,
                agrupaciones_unicas,
                mesas_rows,
                votos_rows,
                append,
                mesas_data_read_path,
                votos_read_path,
                mesas_actualizadas,
            )
            raise SystemExit(1)

        # Evita acumulación histórica de duplicados por mesa/partido.
        votos_unicos: OrderedDict[tuple[str, str], list[str]] = OrderedDict()
        for row in votos_rows:
            if len(row) < 3:
                continue
            codigo_mesa = self.normalize_mesa_code(self._text_value(row[0]))
            partido_id = self._text_value(row[1])
            if not codigo_mesa:
                continue
            votos_unicos[(codigo_mesa, partido_id)] = [codigo_mesa, partido_id, self._text_value(row[2])]
        votos_rows = list(votos_unicos.values())

        agrupaciones_rows = [[item.partido_id, item.nombre] for item in agrupaciones_unicas.values()]
        if append:
            agrupaciones_rows = [
                [item.partido_id, item.nombre]
                for key, item in agrupaciones_unicas.items()
                if key not in agrupaciones_existentes_keys
            ]

        # mesas_data va por upsert: si la mesa existe, se actualiza; si no existe, se inserta.
        mesas_rows_consolidadas = mesas_rows
        if append:
            mesas_consolidadas_map = OrderedDict(mesas_existentes)
            for row in mesas_rows:
                codigo_mesa = self.normalize_mesa_code(self._text_value(row[0]))
                if codigo_mesa:
                    mesas_consolidadas_map[codigo_mesa] = row
            mesas_rows_consolidadas = list(mesas_consolidadas_map.values())

        votos_rows_to_append = votos_rows
        if append:
            votos_rows_to_append = [
                row
                for row in votos_rows
                if (
                    self.normalize_mesa_code(self._text_value(row[0])),
                    self._text_value(row[1]),
                )
                not in votos_existentes_keys
            ]

        # Siempre usar append: solo agregar datos nuevos, nunca sobrescribir
        self._append_tsv(
            agrupaciones_path,
            agrupaciones_rows,
        )
        self._write_tsv(
            mesas_data_path,
            [
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
            ],
            mesas_rows_consolidadas,
        )
        self._append_tsv(
            votos_path,
            votos_rows_to_append,
        )

        # Actualiza el archivo de pendientes a partir del estado final de las mesas consolidadas.
        mesas_faltantes = self._write_mesas_faltantes(mesas_csv, mesas_rows_consolidadas)

        # Devuelve métricas resumidas de la corrida para imprimirlas en CLI.
        return {
            "mesas_en_listado": len(mesas),
            "mesas_procesadas": mesas_procesadas,
            "mesas_sin_data": mesas_sin_data,
            "agrupaciones_unicas": len(agrupaciones_unicas),
            "votos_registrados": len(votos_rows_to_append),
            "mesas_faltantes": mesas_faltantes,
        }
