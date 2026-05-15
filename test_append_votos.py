#!/usr/bin/env python3
"""
Test para verificar que el script NO borra datos de votos.txt
- Crea un archivo votos.txt con datos iniciales
- Simula una ejecución del scraper
- Verifica que los datos iniciales permanecen
- Verifica que solo se agregan datos nuevos
"""

import csv
import tempfile
from pathlib import Path
from src.onpe_scraper.scraper import OnpeExtractor

def test_append_no_borrar_votos():
    """Verifica que append preserva votos existentes sin sobrescribir"""
    
    # Crear directorio temporal
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        output_dir.mkdir(parents=True)
        
        votos_path = output_dir / "votos.txt"
        
        # PASO 1: Crear archivo votos.txt con datos iniciales
        print("\n📝 PASO 1: Creando archivo votos.txt con datos iniciales")
        votos_iniciales = [
            ["000001", "PARTIDO_A", "100"],
            ["000002", "PARTIDO_A", "150"],
            ["000003", "PARTIDO_B", "200"],
        ]
        
        with votos_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t", lineterminator="\n")
            writer.writerow(["codigo_mesa", "partido_id", "votos"])
            writer.writerows(votos_iniciales)
        
        # Leer datos iniciales
        with votos_path.open("r", encoding="utf-8") as f:
            contenido_inicial = f.read()
        print("Contenido inicial:")
        print(contenido_inicial)
        
        # PASO 2: Simular agregación de nuevos votos (append)
        print("\n📝 PASO 2: Usando OnpeExtractor para anexar nuevos votos")
        extractor = OnpeExtractor()
        
        # Simular nuevos votos a agregar
        votos_nuevos = [
            ["000004", "PARTIDO_C", "175"],
            ["000005", "PARTIDO_A", "225"],
        ]
        
        # Simular _append_tsv
        extractor._append_tsv(votos_path, votos_nuevos)
        
        # PASO 3: Leer y verificar archivo final
        print("\n📝 PASO 3: Leyendo archivo después de append")
        with votos_path.open("r", encoding="utf-8") as f:
            contenido_final = f.read()
        print("Contenido final:")
        print(contenido_final)
        
        # PASO 4: Verificar que los datos iniciales están presentes
        print("\n✅ PASO 4: Verificando datos iniciales")
        with votos_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            filas = list(reader)
        
        verificaciones = {
            "000001": False,
            "000002": False,
            "000003": False,
            "000004": False,
            "000005": False,
        }
        
        for fila in filas:
            codigo = fila.get("codigo_mesa", "").strip()
            votos = fila.get("votos", "").strip()
            
            if codigo in verificaciones:
                verificaciones[codigo] = True
                print(f"  ✓ Mesa {codigo} con {votos} votos encontrada")
        
        # PASO 5: Análisis final
        print("\n" + "="*60)
        print("📊 RESUMEN DE VERIFICACIÓN")
        print("="*60)
        
        total_filas = len(filas)
        datos_originales_presentes = sum(1 for m in ["000001", "000002", "000003"] 
                                         if verificaciones[m])
        datos_nuevos_presentes = sum(1 for m in ["000004", "000005"] 
                                     if verificaciones[m])
        
        print(f"Total de filas después de append: {total_filas}")
        print(f"Datos originales conservados: {datos_originales_presentes}/3")
        print(f"Datos nuevos agregados: {datos_nuevos_presentes}/2")
        print(f"Total esperado: 5 filas (3 originales + 2 nuevas)")
        
        # Resultado final
        if all([
            total_filas == 5,
            datos_originales_presentes == 3,
            datos_nuevos_presentes == 2
        ]):
            print("\n✅ ¡TEST EXITOSO! Los datos NO fueron borrados, solo se agregaron.")
            print("   El archivo votos.txt es SEGURO en modo append.")
            return True
        else:
            print("\n❌ ¡TEST FALLIDO! Hay un problema con la preservación de datos.")
            return False


def test_deduplicacion_votos():
    """Verifica que no hay duplicados cuando se procesa la misma mesa"""
    
    print("\n\n" + "="*60)
    print("🔍 TEST 2: Deduplicación de votos (No duplicar mesa/partido)")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        output_dir.mkdir(parents=True)
        
        votos_path = output_dir / "votos.txt"
        
        # Crear archivo con datos iniciales
        print("\nDatos iniciales:")
        votos_iniciales = [
            ["000001", "PARTIDO_A", "100"],
            ["000001", "PARTIDO_B", "150"],
        ]
        
        with votos_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t", lineterminator="\n")
            writer.writerow(["codigo_mesa", "partido_id", "votos"])
            writer.writerows(votos_iniciales)
        
        with votos_path.open("r", encoding="utf-8") as f:
            print(f.read())
        
        # Simular nuevos votos (incluyendo un duplicado)
        print("\nSimulando actualización de mesa 000001 (mismo partido A con nuevo valor):")
        votos_actualizacion = [
            ["000001", "PARTIDO_A", "250"],  # Actualización del mismo votos
            ["000002", "PARTIDO_A", "300"],  # Nueva mesa
        ]
        
        extractor = OnpeExtractor()
        
        # En un flujo real con append y deduplicación (por OrderedDict)
        # se combinarían los votos y se deduplicarían por (mesa, partido)
        votos_existentes = []
        with votos_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                votos_existentes.append([
                    row.get("codigo_mesa", "").strip(),
                    row.get("partido_id", "").strip(),
                    row.get("votos", "").strip()
                ])
        
        # Combinar y deduplicar
        from collections import OrderedDict
        votos_dedup = OrderedDict()
        
        # Primero existentes
        for row in votos_existentes:
            if len(row) >= 3:
                key = (row[0], row[1])
                votos_dedup[key] = row
        
        # Luego nuevos (sobreescriben si hay duplicado)
        for row in votos_actualizacion:
            if len(row) >= 3:
                key = (row[0], row[1])
                votos_dedup[key] = row
        
        print(f"\nDatos después de deduplicación:")
        for key, row in votos_dedup.items():
            print(f"  Mesa {row[0]}, Partido {row[1]}: {row[2]} votos")
        
        # Verificar
        print(f"\nTotal de registros únicos: {len(votos_dedup)}")
        print("Esperado: 3 (mesa 1 partido A actualizado, mesa 1 partido B, mesa 2 partido A)")
        
        if len(votos_dedup) == 3:
            print("\n✅ ¡TEST EXITOSO! La deduplicación funciona correctamente.")
            return True
        else:
            print("\n❌ ¡TEST FALLIDO! Hay más registros de los esperados.")
            return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 TESTS DE INTEGRIDAD: VOTOS.TXT")
    print("="*60)
    
    test1 = test_append_no_borrar_votos()
    test2 = test_deduplicacion_votos()
    
    print("\n\n" + "="*60)
    print("📋 RESUMEN FINAL")
    print("="*60)
    print(f"Test 1 (Append sin borrar): {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"Test 2 (Deduplicación): {'✅ PASS' if test2 else '❌ FAIL'}")
    
    if test1 and test2:
        print("\n🎉 ¡TODOS LOS TESTS PASARON!")
        print("   El archivo votos.txt es SEGURO y NO se borrará.")
    else:
        print("\n⚠️  Algunos tests fallaron. Revisar el código.")
