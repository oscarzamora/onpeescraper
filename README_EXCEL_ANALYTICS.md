# Excel Analytics Model (ONPE / Elecciones)

Guía para construir un Excel analítico conectado en vivo a archivos alojados en GitHub, con modelo de datos, relaciones, drill-down, mapas y refresco automático.

Link al documento principal del proyecto: [README principal](README.md)

## Objetivo

El objetivo es armar un Excel que consuma los archivos del proyecto desde GitHub RAW y permita analizar resultados electorales con:

- modelo de datos tipo star schema;
- relaciones entre mesas, votos, candidatos, partidos y ubigeo;
- medidas DAX;
- tablas dinámicas con drill-down;
- gráficos tipo Power BI;
- mapa interactivo con mouse-over;
- refresco automático desde GitHub RAW.

## Estado actual del archivo Excel

- Archivo detectado: `analytics/onpe_analytics.xlsx`.
- El workbook ya tiene las importaciones preparadas y apuntando a fuentes en GitHub.
- Para terminar la explotación analítica faltan estos pasos:
  - validar tipos de datos y formato de columnas clave (`codigo_mesa`, `partido_id`, `ubigeo`);
  - crear/ajustar relaciones del modelo de datos;
  - crear medidas DAX base;
  - construir pivots, gráficos y mapa;
  - dejar configurado el refresco con `Actualizar todo`.

## 1. Archivos fuente en GitHub RAW

El Excel se alimenta directamente desde estos archivos publicados en GitHub.

Directorio completo:

- [https://github.com/oscarzamora/onpeescraper/tree/main/source_data](https://github.com/oscarzamora/onpeescraper/tree/main/source_data)
- [https://github.com/oscarzamora/onpeescraper/tree/main/output](https://github.com/oscarzamora/onpeescraper/tree/main/output)

Archivos disponibles en `source_data`:

- [MesasFaltantes.txt](https://github.com/oscarzamora/onpeescraper/blob/main/source_data/MesasFaltantes.txt): lista operativa de mesas pendientes.
- [candidato.txt](https://github.com/oscarzamora/onpeescraper/blob/main/source_data/candidato.txt): candidatos y su partido.
- [geodir-ubigeo-reniec.xlsx](https://github.com/oscarzamora/onpeescraper/blob/main/source_data/geodir-ubigeo-reniec.xlsx): ubigeo oficial con territorio y coordenadas.
- [.gitkeep](https://github.com/oscarzamora/onpeescraper/blob/main/source_data/.gitkeep): archivo marcador del directorio.
- [todas_las_mesas.txt](https://github.com/oscarzamora/onpeescraper/blob/main/source_data/todas_las_mesas.txt): universo completo de mesas publicadas por ONPE.

Archivos de salida que el Excel también puede consumir desde GitHub RAW:

- [agrupaciones.txt](https://github.com/oscarzamora/onpeescraper/blob/main/output/agrupaciones.txt): partidos o agrupaciones detectadas.
- [mesas_data.txt](https://github.com/oscarzamora/onpeescraper/blob/main/output/mesas_data.txt): información principal por mesa.
- [votos.txt](https://github.com/oscarzamora/onpeescraper/blob/main/output/votos.txt): votos por mesa y agrupación.

Cada archivo se debe consumir desde su URL RAW. Ejemplo:

```text
https://raw.githubusercontent.com/<usuario>/<repo>/main/mesas_data.txt
```

## 2. Carga de datos en Excel con Power Query

Para cada archivo:

1. Abrir Excel.
2. Ir a Datos.
3. Elegir Obtener datos > Desde otras fuentes > Desde Web.
4. Pegar la URL RAW.
5. En Power Query, transformar el archivo.
6. Para TXT, usar delimitador tabulación.
7. Cerrar y cargar > Solo conexión + Agregar al Modelo de datos.

Repetir para:

- `mesas_data`
- `votos`
- `agrupaciones`
- `candidato`
- `ubigeo.xlsx`

Si quieres pegar las URLs directamente desde este proyecto, usa esta base:

```text
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/
```

Y concatena el nombre del archivo, por ejemplo:

```text
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/output/mesas_data.txt
```

Si prefieres copiar las URLs directas del proyecto sin armar nada a mano, aquí van:

```text
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/output/agrupaciones.txt
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/output/mesas_data.txt
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/output/votos.txt
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/source_data/MesasFaltantes.txt
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/source_data/candidato.txt
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/source_data/geodir-ubigeo-reniec.xlsx
https://raw.githubusercontent.com/oscarzamora/onpeescraper/main/source_data/todas_las_mesas.txt
```

## 3. Modelo de datos y relaciones

Crear estas relaciones:

- `mesas_data[codigo_mesa]` -> `votos[codigo_mesa]`
- `candidato[candidato_id]` -> `votos[candidato_id]`
- `agrupaciones[partido_id]` -> `candidato[partido_id]`
- `ubigeo[Ubigeo]` -> `mesas_data[ubigeo]`

Notas:

- `mesas_data` es la tabla central.
- `ubigeo` permite construir la jerarquía territorial oficial.
- `localidad` se usa como nivel adicional dentro del distrito.

## 4. Medidas DAX

Crear estas medidas en el modelo de datos:

```DAX
Total Votos := SUM(votos[votos])
```

```DAX
Total Votos Nacional := CALCULATE(SUM(votos[votos]), ALL(candidato))
```

```DAX
% Candidato := DIVIDE([Total Votos], [Total Votos Nacional])
```

```DAX
Total Votos Mesa := SUM(votos[votos])
```

## 5. Tab: Candidatos

Crear una tabla dinámica usando el Modelo de datos.

Configuración:

- Filas: `candidato[nombre_candidato]`
- Valores: `Total Votos`
- Valores: `% Candidato`
- Ordenar de mayor a menor
- Insertar gráfico de barras horizontales

Este tab permite:

- ranking de candidatos;
- porcentaje nacional;
- drill-through por candidato.

## 6. Tab: Territorio

Crear una tabla dinámica con jerarquía territorial:

Filas, en este orden:

- `ubigeo[Departamento]`
- `ubigeo[Provincia]`
- `ubigeo[Distrito]`
- `mesas_data[localidad]`
- `mesas_data[codigo_mesa]`

Columnas:

- `candidato[nombre_candidato]`

Valores:

- `Total Votos`

Esto permite drill-down tipo Power BI:

```text
Departamento
  Provincia
    Distrito
      Localidad
        Mesa
          Candidato A   Candidato B   ...
```

## 7. Tab: Mapa

Requisitos:

- `ubigeo.xlsx` debe tener latitud y longitud.
- `Total Votos Mesa` debe estar disponible.

Pasos:

1. Crear una tabla con latitud, longitud, mesa, localidad, territorio y votos.
2. Insertar un mapa o 3D Map.
3. Configurar tamaño o color por `Total Votos Mesa`.
4. Configurar tooltip con mesa, localidad, votos y territorio.

## 8. Refresco automático

Cada vez que se actualicen los archivos en GitHub:

1. Excel > Datos.
2. Actualizar todo.

Excel recargará:

- `mesas_data`
- `votos`
- `agrupaciones`
- `candidato`
- `ubigeo`

Y actualizará:

- tablas dinámicas;
- gráficos;
- mapa;
- drill-through.

## 9. Relación con el proyecto principal

Esta guía complementa el modelo de datos y el snapshot operativo descritos en el [README principal](README.md).

Si cambian los nombres de columnas o se agregan nuevas salidas, primero actualiza el README principal y luego ajusta esta guía para que ambos documentos sigan alineados.
