# ONPE Scraper

Scraper en Python para extraer resultados por mesa desde ONPE Peru y mantener una lista operativa de mesas pendientes.

## Estado de cobertura ONPE

La data de este repositorio esta completa al 100% respecto a lo publicado por ONPE para este corte.

- Total de mesas publicadas por ONPE: 92,766
- Mesas pendientes: 0
- Cobertura: 100%

Nota: cuando ONPE publique nuevas mesas o actualizaciones, el proceso incremental vuelve a detectar y registrar cambios.

## Objetivo

Este repositorio se enfoca solo en extraccion y publicacion de datos base.

- consulta mesas en el backend de ONPE;
- normaliza codigos de mesa;
- guarda salidas tabulares en TXT (delimitado por tab);
- actualiza `source_data/MesasFaltantes.txt` segun el estado del acta.

Nota: esta data puede usarse para analiticas (Excel, Power BI u otras herramientas), pero el modelado analitico queda fuera de este proyecto.

## ERD (Modelo de datos)

```mermaid
erDiagram
	MESAS_DATA ||--o{ VOTOS : codigo_mesa
	AGRUPACIONES ||--o{ VOTOS : partido_id
	UBIGEO_RENIEC ||--o{ MESAS_DATA : ubigeo

	MESAS_DATA {
		string codigo_mesa PK
		string ubigeo
		string local_votacion
		int electores_habiles
		int votos_emitidos
		int votos_validos
		int blancos
		int nulos
		int impugnados
		string estado_acta
	}

	AGRUPACIONES {
		string partido_id PK
		string nombre
	}

	VOTOS {
		string codigo_mesa FK
		string partido_id FK
		int votos
	}

	UBIGEO_RENIEC {
		string Ubigeo PK
		string Distrito
		string Provincia
		string Departamento
		number Poblacion
		number Superficie
		number Y
		number X
	}
```

Llaves y relaciones:

- MESAS_DATA: PK codigo_mesa
- AGRUPACIONES: PK partido_id
- VOTOS: PK logica compuesta codigo_mesa + partido_id
- UBIGEO_RENIEC: PK Ubigeo
- MESAS_DATA (1) -> VOTOS (N) por codigo_mesa
- AGRUPACIONES (1) -> VOTOS (N) por partido_id
- UBIGEO_RENIEC (1) -> MESAS_DATA (N) por ubigeo

## Entradas

- `source_data/MesasFaltantes.txt`: lista operativa de mesas a consultar.
- `source_data/todas_las_mesas.txt`: universo de referencia de mesas publicadas.
- `source_data/candidato.txt`: catalogo manual opcional para enriquecimiento.
- `source_data/geodir-ubigeo-reniec.xlsx`: dimension geografica por ubigeo para analisis territorial.

Origen de ubigeo:

- Fuente: Geodir (dataset RENIEC de ubigeos)
- URL de referencia: https://account.geodir.co/resources/file/recursos/geodir-ubigeo-reniec.xlsx
- En este repositorio se mantiene una copia local para cruces analiticos.

## Salidas

- `output/mesas_data.txt`: cabecera por mesa.
- `output/votos.txt`: detalle por mesa y agrupacion.
- `output/agrupaciones.txt`: catalogo de agrupaciones detectadas.

Los archivos en `output/` estan listos para uso analitico directo en Excel, Power BI, SQL o notebooks, sin transformaciones complejas adicionales.

## Requisitos

- Python 3.11+
- Dependencias en `requirements.txt`

## Instalacion

```bash
pip install -r requirements.txt
```

## Ejecucion

### Desde script principal

```bash
python main.py --input source_data/MesasFaltantes.txt --output-dir output --append
```

### Desde modulo

```bash
pip install -e .
python -m onpe_scraper --input source_data/MesasFaltantes.txt --output-dir output --append
```

## Comportamiento de actualizacion

- Se trabaja en modo incremental (`--append`).
- No se sobreescribe el historico de `output/votos.txt`.
- No se duplican filas historicas ya existentes por clave (`codigo_mesa`, `partido_id`).
- `source_data/MesasFaltantes.txt` se regenera al final con mesas cuyo `estado_acta` sea distinto de `Contabilizada`.

## Supuesto tecnico vigente

El scraper consulta `/actas/buscar/mesa` y selecciona la acta presidencial con `idEleccion = 10`.
Si ONPE cambia estructura o endpoint, este supuesto debe validarse y documentarse.

## Estructura de este repositorio

```text
onpescraper/
|-- main.py
|-- pyproject.toml
|-- requirements.txt
|-- README.md
|-- output/
|   |-- agrupaciones.txt
|   |-- mesas_data.txt
|   \-- votos.txt
|-- source_data/
|   |-- MesasFaltantes.txt
|   |-- todas_las_mesas.txt
|   |-- candidato.txt
|   \-- geodir-ubigeo-reniec.xlsx
\-- src/
	\-- onpe_scraper/
		|-- __init__.py
		|-- __main__.py
		|-- cli.py
		\-- scraper.py
```
