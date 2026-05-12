# ONPE Scraper

Extractor en Python para ONPE Perú basado en la lista de mesas faltantes.

## Estado actual

- El extractor trabaja contra `/actas/buscar/mesa` porque no se usa un endpoint público de UBIGEO.
- La entrada base es `source_data/MesasFaltantes.txt`.
- `source_data/todas_las_mesas.txt` contiene el universo completo de mesas publicadas por ONPE.
- Las mesas sin `data` o sin acta presidencial se omiten.
- La salida genera tres archivos TXT delimitados por tabulaciones: `agrupaciones.txt`, `mesas_data.txt` y `votos.txt`.

## Archivos de entrada

- `source_data/todas_las_mesas.txt`: listado maestro de mesas ONPE (referencia completa).
- `source_data/MesasFaltantes.txt`: listado operativo que usa el scraper en cada corrida.
- `source_data/candidato.txt`: catálogo de candidatos por partido cargado manualmente.

Nota: al finalizar una corrida, el script actualiza `MesasFaltantes.txt` con las mesas cuyo `estado_acta` siga siendo distinto de `Contabilizada`.
Nota: `candidato.txt` no se genera automáticamente; su mantenimiento es manual.

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
