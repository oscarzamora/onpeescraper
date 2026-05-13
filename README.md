# ONPE Scraper

Extractor en Python para ONPE Perú basado en la lista de mesas faltantes.

## Qué resuelve este proyecto

Este proyecto convierte la publicación operativa de ONPE a un formato de datos simple, reutilizable y transparente para análisis. En lugar de depender de consultas manuales mesa por mesa en la web o de revisiones repetitivas para detectar cambios de estado, el scraper descarga, normaliza y deja la información lista para consumo analítico.

Con este flujo se logra:

- simplificar la extracción de resultados publicados por ONPE;
- mantener una lista viva de mesas pendientes por procesar;
- reemplazar automáticamente la información de mesas que cambian de estado;
- exponer con transparencia lo que ONPE publica respecto a conteos de votos, estado del acta y detalle por agrupación;
- dejar la salida en archivos tabulares fáciles de abrir y modelar en Excel, Power BI u otras herramientas.

En términos prácticos, este repositorio reduce el trabajo manual de seguimiento, evita reprocesar todo desde cero en cada corrida y deja un snapshot auditable de lo que ONPE tiene publicado en un momento dado.

## Estado operativo

- Última actualización del README: `2026-05-12 22:37:35 -04:00`.
- Snapshot actual del universo ONPE: `86,696` mesas procesadas y `6,070` mesas pendientes sobre `92,766` mesas totales publicadas.
- Avance actual del snapshot: `93.46%` (`mesas procesadas / total de mesas publicadas`).
- Al momento de esta actualización quedan `6,070` mesas en `source_data/MesasFaltantes.txt`.
- El usuario puede volver a correr el script para descargar las mesas restantes que sigan pendientes en esa lista.
- Los archivos de `output` pueden consumirse directamente desde Excel, Power BI u otras herramientas de análisis de datos.
- Respecto al registro documentado anterior, hubo una variación neta de `+5,853` mesas pendientes en `MesasFaltantes.txt`.

## Estado del Excel analítico

- Archivo preparado: `analytics/onpe_analytics.xlsx`.
- Estado: contiene importaciones listas y apuntando a las fuentes publicadas en GitHub.
- Para explotar la data solo faltan los pasos de modelado y análisis descritos en `README_EXCEL_ANALYTICS.md` (relaciones, medidas DAX, pivots, mapas y refresco).

## Estado actual

- El extractor trabaja contra `/actas/buscar/mesa` porque no se usa un endpoint público de UBIGEO.
- La entrada base es `source_data/MesasFaltantes.txt`.
- `source_data/todas_las_mesas.txt` contiene el universo completo de mesas publicadas por ONPE.
- Las mesas sin `data` o sin acta presidencial se omiten.
- La salida genera tres archivos TXT delimitados por tabulaciones: `agrupaciones.txt`, `mesas_data.txt` y `votos.txt`.

## Modelo de datos de output

Los archivos de `output` están delimitados por tabulaciones y se relacionan por IDs con match exacto (sin transformaciones adicionales al momento de cruzar).

### Columnas e interpretación de salida

#### `output/agrupaciones.txt`

Dimensión de partidos o agrupaciones detectadas en la extracción.

- `partido_id`: identificador único de la agrupación o partido (llave de la tabla).
- `nombre`: nombre textual de la agrupación o partido.

#### `output/mesas_data.txt`

Tabla principal a nivel de mesa. Una fila representa una mesa consultada en ONPE.

- `codigo_mesa`: identificador único de la mesa (llave de la tabla).
- `ubigeo`: código ubigeo asociado a la mesa.
- `local_votacion`: local de votación asociado a la mesa.
- `electores_habiles`: total de electores habilitados.
- `votos_emitidos`: total de votos emitidos.
- `votos_validos`: total de votos válidos.
- `blancos`: total de votos en blanco.
- `nulos`: total de votos nulos.
- `impugnados`: total de votos impugnados.
- `estado_acta`: estado publicado por ONPE; define si la mesa sale de `MesasFaltantes.txt`.

#### `output/votos.txt`

Tabla de detalle por mesa y agrupación. Una mesa puede tener muchas filas, una por partido o agrupación.

- `codigo_mesa`: mesa a la que pertenece la fila de detalle.
- `partido_id`: agrupación o partido al que se atribuyen los votos.
- `votos`: cantidad de votos obtenidos por la agrupación en esa mesa.

### Llaves por dataset

- `mesas_data.txt`: llave `codigo_mesa`.
- `agrupaciones.txt`: llave `partido_id`.
- `votos.txt`: llave compuesta `codigo_mesa + partido_id`.

### Relaciones y cardinalidad

- `mesas_data` (1) -> `votos` (N): por `codigo_mesa` con match exacto.
- `agrupaciones` (1) -> `votos` (N): por `partido_id` con match exacto.

`votos` es el único dataset de detalle (many) porque almacena múltiples filas por mesa, una por agrupación/candidato. Por eso su llave es compuesta (`codigo_mesa`, `partido_id`).

## ERD de referencia

Modelo lógico resumido para análisis:

- `mesas_data` (1) -> `votos` (N) por `codigo_mesa`.
- `agrupaciones` (1) -> `votos` (N) por `partido_id`.
- `candidato` es una dimensión opcional manual (`source_data/candidato.txt`) para enriquecer por persona.
- `ubigeo` es una dimensión externa (`source_data/geodir-ubigeo-reniec.xlsx`) para análisis territorial.

Nota: el scraper vigente genera solo los archivos tabulados descritos en este README; las demás dimensiones son de enriquecimiento analítico.

## Archivos de entrada

- `source_data/todas_las_mesas.txt`: listado maestro de mesas ONPE (referencia completa).
- `source_data/MesasFaltantes.txt`: listado operativo que usa el scraper en cada corrida.
- `source_data/candidato.txt`: catálogo de candidatos por partido cargado manualmente.
- `source_data/geodir-ubigeo-reniec.xlsx`: catálogo geográfico por ubigeo (RENIEC).

Nota: al finalizar una corrida, el script actualiza `MesasFaltantes.txt` con las mesas cuyo `estado_acta` siga siendo distinto de `Contabilizada`.
Nota: `candidato.txt` no se genera automáticamente; su mantenimiento es manual.

## Guía para Excel analítico

Si quieres construir un Excel analítico conectado a estos datos, revisa la guía dedicada: [README_EXCEL_ANALYTICS.md](README_EXCEL_ANALYTICS.md).

La guía explica cómo consumir los archivos desde GitHub RAW, modelarlos en Power Query y construir relaciones, medidas DAX, drill-down y mapas.

### Columnas e interpretación de entrada

#### `source_data/MesasFaltantes.txt`

Archivo operativo de una sola columna lógica. En el archivo actual no hay encabezado: cada línea representa una mesa pendiente.

- `codigo_mesa`: mesa pendiente por consultar o reconsultar en ONPE.
- Si la mesa sigue con estado distinto de `Contabilizada`, permanece en esta lista al final de la corrida.

#### `source_data/todas_las_mesas.txt`

Archivo maestro del universo publicado por ONPE. Sí contiene encabezado.

- `codigo_mesa`: identificador único de mesa usado para medir cobertura del snapshot.

#### `source_data/candidato.txt`

Catálogo manual para enriquecer o validar la lectura de agrupaciones/candidaturas.

- `partido_id`: identificador del partido/agrupación alineado con la salida ONPE.
- `Candidato`: nombre del candidato asociado (puede estar vacío).

#### `source_data/geodir-ubigeo-reniec.xlsx`

Catálogo geográfico complementario. Debe tratarse como tabla de referencia externa. Las columnas observadas en el archivo actual son:

- `Ubigeo`: llave territorial para relacionar mesa con geografía.
- `Distrito`, `Provincia`, `Departamento`: niveles administrativos.
- `Poblacion`, `Superficie`: métricas de referencia territorial.
- `Y`, `X`: latitud y longitud.

### Origen de `geodir-ubigeo-reniec.xlsx`

- Origen de referencia publicado en Geodir: https://account.geodir.co/resources/file/recursos/geodir-ubigeo-reniec.xlsx
- Copia usada en el proyecto: `source_data/geodir-ubigeo-reniec.xlsx`
- Advertencia: este archivo puede no estar actualizado respecto a la última versión oficial disponible.

Ejemplo de registros:

```text
Ubigeo	Distrito	Provincia	Departamento	Poblacion	Superficie	Y	X
010101	Chachapoyas	Chachapoyas	Amazonas	29,171	153.78	-6.2294	-77.8714
010102	Asuncion	Chachapoyas	Amazonas	288	25.71	-6.0317	-77.7122
010103	Balsas	Chachapoyas	Amazonas	1,644	357.09	-6.8375	-78.0214
010104	Cheto	Chachapoyas	Amazonas	591	56.97	-6.2558	-77.7003
010105	Chiliquin	Chachapoyas	Amazonas	687	143.43	-6.0778	-77.7392
```

## Requisitos

- Python 3.11 o superior
- `curl_cffi` para simular un navegador Chrome y obtener el JSON real de ONPE

## Instalación

```bash
pip install -r requirements.txt
```


## Uso

```bash
python main.py --input source_data/MesasFaltantes.txt --output-dir output
```

Durante la ejecución se imprime avance por lote en consola. Por defecto el lote es de 50 mesas y el tamaño se puede ajustar con `--batch-size`.

También puedes ejecutar el paquete como módulo después de instalarlo en editable:

```bash
pip install -e .
python -m onpe_scraper --input source_data/MesasFaltantes.txt --output-dir output
```

## Estructura

- `main.py`: punto de entrada rápido.
- `src/onpe_scraper/`: lógica del scraper.
- `.github/copilot-instructions.md`: instrucciones del workspace.

## Supuesto técnico

El flujo asume que el servicio devuelve una estructura JSON con `data` como lista de actas y que la acta presidencial se identifica con `idEleccion = 10`. Las mesas cortas se normalizan con padding a 6 dígitos antes de consultar el servicio. Si el servicio cambia, este supuesto debe revisarse antes de ampliar el extractor.

## Qué hace el script Python

El proyecto tiene un flujo simple en la superficie, pero internamente aplica varias reglas para que la extracción sea repetible, incremental y consistente con lo que publica ONPE.

### Archivos Python involucrados

| Archivo | Qué hace |
| --- | --- |
| `main.py` | Punto de entrada. Agrega `src` al `sys.path` y ejecuta el CLI del proyecto. |
| `src/onpe_scraper/cli.py` | Define los argumentos de línea de comandos, resuelve la ruta de entrada y crea la instancia del extractor. |
| `src/onpe_scraper/scraper.py` | Implementa toda la lógica de lectura, consulta HTTP, filtrado de acta presidencial, construcción de tablas y actualización de archivos. |

### Lógica detallada del proceso

| Paso | Qué hace el script | Detalle operativo |
| --- | --- | --- |
| 1 | Lee argumentos | `cli.py` recibe `--input`, `--output-dir`, `--base-url`, `--id-eleccion`, `--timeout`, `--pause-seconds`, `--max-workers`, `--batch-size` y `--append`. |
| 2 | Resuelve archivo de entrada | Si el usuario pasa un `.txt` que no existe, intenta usar el `.csv` equivalente como compatibilidad con versiones anteriores. |
| 3 | Crea el extractor | `OnpeExtractor` guarda configuración base, limita `max_workers` a un máximo interno de `5` y prepara almacenamiento thread-local para sesiones HTTP. |
| 4 | Carga la lista de mesas | `load_mesas()` lee la primera columna del archivo de entrada, ignora filas vacías, ignora valores no numéricos, elimina duplicados y normaliza cada mesa a 6 dígitos con `zfill(6)`. |
| 5 | Divide en lotes | `_chunked()` reparte las mesas en grupos del tamaño indicado por `--batch-size` para procesarlas por bloques. |
| 6 | Prepara rutas de salida | Define `output/agrupaciones.txt`, `output/mesas_data.txt` y `output/votos.txt`. En modo `--append` también puede leer versiones antiguas `.tsv` si existen. |
| 7 | Inicializa catálogos existentes | En modo incremental carga `agrupaciones`, `mesas_data` y `votos` previos para hacer upsert en vez de reconstrucción total. |
| 8 | Ejecuta procesamiento paralelo | Para cada lote usa `ThreadPoolExecutor` con hasta `5` workers. Cada worker consulta una mesa en paralelo. |
| 9 | Reutiliza sesiones HTTP por hilo | `_get_session()` crea una sesión `curl_cffi` por hilo y la reutiliza, evitando recrear conexiones en cada mesa. |
| 10 | Consulta el endpoint de ONPE | `_fetch_mesa_requests()` llama a `/actas/buscar/mesa` con `codigoMesa=<mesa>`, encabezados tipo navegador y `impersonate='chrome124'` para obtener el JSON real del backend. |
| 11 | Maneja errores de red o JSON | Si la respuesta falla, no devuelve JSON válido o produce excepción, el resultado de esa mesa se trata como sin data. |
| 12 | Filtra la elección correcta | `extract_acta()` revisa `payload['data']` y selecciona solo la acta cuyo `idEleccion` coincide con la configuración actual, por defecto `10`. |
| 13 | Omite mesas no útiles | Si la respuesta no trae `data` o no contiene acta presidencial, la mesa no genera filas de salida y se contabiliza como `mesas_sin_data`. |
| 14 | Construye la fila de mesa | `build_mesa_data()` toma campos del acta y produce una fila única por mesa con ubigeo, local, electores, totales de votos y `estado_acta`. |
| 15 | Calcula blancos, nulos e impugnados | Dentro de `detalle`, busca los códigos `80`, `81` y `82` para mapearlos a `blancos`, `nulos` e `impugnados`. |
| 16 | Construye el catálogo de agrupaciones | `build_agrupaciones()` recorre `detalle`, toma `adAgrupacionPolitica` y `adDescripcion`, y arma el catálogo de partidos sin duplicados. |
| 17 | Construye el detalle de votos | `build_votos()` genera filas por `codigo_mesa`, `partido_id` y `votos` a partir de cada item del detalle del acta. |
| 18 | Mantiene el orden original | Aunque el procesamiento es paralelo, al final de cada lote los resultados se ordenan por el índice original de la mesa antes de consolidarlos. |
| 19 | Reporta avance por lote | Después de cada lote imprime en consola cuántas mesas fueron procesadas, cuántas quedaron sin data y el porcentaje de avance acumulado. |
| 20 | Escribe agrupaciones | Siempre reescribe `agrupaciones.txt` con el conjunto único consolidado de agrupaciones detectadas. |
| 21 | Hace upsert de mesas en modo append | Si `--append` está activo, carga `mesas_data` existente y reemplaza solo las mesas recién actualizadas por sus nuevas filas. |
| 22 | Hace upsert de votos en modo append | Si `--append` está activo, elimina del histórico los votos de mesas actualizadas y luego agrega las nuevas filas obtenidas para esas mesas. |
| 23 | Deduplica votos | Antes de escribir `votos.txt`, conserva una sola fila por llave compuesta `codigo_mesa + partido_id` para evitar acumulación histórica de duplicados. |
| 24 | Reescribe los TXT finales | `_write_tsv()` guarda `mesas_data.txt` y `votos.txt` como archivos de texto delimitados por tabulaciones, con encabezado. |
| 25 | Regenera `MesasFaltantes.txt` | `_write_mesas_faltantes()` revisa todas las filas finales de `mesas_data` y reescribe la lista solo con mesas cuyo `estado_acta` sea distinto de `Contabilizada`. |
| 26 | Devuelve un resumen final | El método `run()` retorna contadores: mesas en listado, procesadas, sin data, agrupaciones únicas, votos registrados y mesas faltantes actualizadas. |

### Resumen funcional del script

| Componente | Responsabilidad |
| --- | --- |
| Lectura de entrada | Tomar la lista operativa de mesas y normalizarla. |
| Consulta ONPE | Pedir el JSON de cada mesa al backend oficial de resultados. |
| Selección de acta | Elegir solo la acta presidencial (`idEleccion = 10`). |
| Transformación | Separar la respuesta en tres datasets: mesa, agrupación y votos. |
| Consolidación | Mezclar resultados nuevos con archivos previos cuando se usa `--append`. |
| Control operativo | Detectar qué mesas siguen pendientes según `estado_acta`. |
| Salida analítica | Dejar TXT tabulados listos para Excel, Power BI u otro consumidor. |
