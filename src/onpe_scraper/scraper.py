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


@dataclass(slots=True)
class AgrupacionData:
    partido_id: str
    nombre: str


@dataclass(slots=True)
class VotoData:
    codigo_mesa: str
    partido_id: str
    votos: int


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
        return codigo_mesa.zfill(6)

    @staticmethod
    def _build_session() -> curl_requests.Session:
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
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = self._build_session()
            self._thread_local.session = session
        return session

    def _fetch_mesa_requests(self, codigo_mesa: str) -> dict[str, Any] | None:
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
        codigo_mesa = self.normalize_mesa_code(codigo_mesa)
        return self._fetch_mesa_requests(codigo_mesa)

    def extract_acta(self, payload: dict[str, Any] | None) -> dict[str, Any] | None:
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
    def _int_value(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _text_value(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def build_mesa_data(self, acta: dict[str, Any]) -> MesaData:
        detalle = acta.get("detalle") if isinstance(acta.get("detalle"), list) else []

        blancos = next((self._int_value(item.get("adVotos")) for item in detalle if item.get("adCodigo") == "80"), 0)
        nulos = next((self._int_value(item.get("adVotos")) for item in detalle if item.get("adCodigo") == "81"), 0)
        impugnados = next((self._int_value(item.get("adVotos")) for item in detalle if item.get("adCodigo") == "82"), 0)

        return MesaData(
            codigo_mesa=self.normalize_mesa_code(self._text_value(acta.get("codigoMesa"))),
            id_ubigeo=self._text_value(acta.get("idUbigeo")),
            local_votacion=self._text_value(acta.get("nombreLocalVotacion")),
            electores_habiles=self._int_value(acta.get("totalElectoresHabiles")),
            votos_emitidos=self._int_value(acta.get("totalVotosEmitidos")),
            votos_validos=self._int_value(acta.get("totalVotosValidos")),
            blancos=blancos,
            nulos=nulos,
            impugnados=impugnados,
            estado_acta=self._text_value(acta.get("descripcionEstadoActa")),
        )

    def build_agrupaciones(self, acta: dict[str, Any]) -> list[AgrupacionData]:
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
        return [items[index : index + size] for index in range(0, len(items), size)]

    def _process_mesa(self, index: int, codigo_mesa: str) -> MesaResult:
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
    def _write_tsv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(headers)
            writer.writerows(rows)

    @staticmethod
    def _append_tsv(path: Path, rows: list[list[str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerows(rows)

    @staticmethod
    def _load_agrupaciones_tsv(path: Path) -> OrderedDict[str, AgrupacionData]:
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
        if primary.exists():
            return primary
        if legacy.exists():
            return legacy
        return primary

    def run(self, mesas_csv: Path, output_dir: Path, append: bool = False) -> dict[str, int]:
        mesas = self.load_mesas(mesas_csv)
        indexed_mesas = list(enumerate(mesas))
        batches = self._chunked(indexed_mesas, self.batch_size)
        total_mesas = len(indexed_mesas)

        agrupaciones_path = output_dir / "agrupaciones.txt"
        mesas_data_path = output_dir / "mesas_data.txt"
        votos_path = output_dir / "votos.txt"

        # Compatibilidad con salidas antiguas .tsv cuando se corre en modo append.
        agrupaciones_read_path = self._prefer_existing_path(agrupaciones_path, output_dir / "agrupaciones.tsv")
        mesas_data_read_path = self._prefer_existing_path(mesas_data_path, output_dir / "mesas_data.tsv")
        votos_read_path = self._prefer_existing_path(votos_path, output_dir / "votos.tsv")

        agrupaciones_unicas: OrderedDict[str, AgrupacionData] = (
            self._load_agrupaciones_tsv(agrupaciones_read_path) if append else OrderedDict()
        )
        mesas_rows: list[list[str]] = []
        votos_rows: list[list[str]] = []
        mesas_actualizadas: set[str] = set()

        mesas_procesadas = 0
        mesas_sin_data = 0

        for batch_number, lote in enumerate(batches, start=1):
            print(
                f"Lote {batch_number}/{len(batches)}: iniciando {len(lote)} mesas",
                flush=True,
            )
            resultados: list[MesaResult] = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futuros = [
                    executor.submit(self._process_mesa, index, codigo_mesa)
                    for index, codigo_mesa in lote
                ]
                for futuro in as_completed(futuros):
                    resultados.append(futuro.result())

            resultados.sort(key=lambda item: item.index)

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
            print(
                (
                    f"Lote {batch_number}/{len(batches)}: completado "
                    f"procesadas={mesas_procesadas} sin_data={mesas_sin_data} "
                    f"avance={completadas}/{total_mesas} ({porcentaje:.1f}%)"
                ),
                flush=True,
            )

        self._write_tsv(
            agrupaciones_path,
            ["partido_id", "nombre"],
            [[item.partido_id, item.nombre] for item in agrupaciones_unicas.values()],
        )
        if append:
            existentes = self._load_mesas_data_tsv(mesas_data_read_path)
            for row in mesas_rows:
                codigo_mesa = self.normalize_mesa_code(self._text_value(row[0]))
                if codigo_mesa:
                    existentes[codigo_mesa] = row
            mesas_rows = list(existentes.values())

            votos_existentes = self._load_votos_tsv(votos_read_path)
            votos_filtrados = [
                row for row in votos_existentes if self.normalize_mesa_code(self._text_value(row[0])) not in mesas_actualizadas
            ]
            votos_rows = votos_filtrados + votos_rows

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
            mesas_rows,
        )
        self._write_tsv(
            votos_path,
            ["codigo_mesa", "partido_id", "votos"],
            votos_rows,
        )

        mesas_faltantes = self._write_mesas_faltantes(mesas_csv, mesas_rows)

        return {
            "mesas_en_listado": len(mesas),
            "mesas_procesadas": mesas_procesadas,
            "mesas_sin_data": mesas_sin_data,
            "agrupaciones_unicas": len(agrupaciones_unicas),
            "votos_registrados": len(votos_rows),
            "mesas_faltantes": mesas_faltantes,
        }
