# 3 · Tareas

Cada tarea cita los requisitos que cubre y el test que la verifica.

| # | Tarea | Requisitos | Verificación | Estado |
|---|---|---|---|---|
| T1 | Configuración central `config.yaml` | todos | carga en tests | ✅ |
| T2 | Indicadores semanales | R-F1 | `test_stages.py` | ✅ |
| T3 | Clasificador de fases | R-F2, R-F3 | `test_stages.py` | ✅ |
| T4 | Zonas de resistencia y mínimos de corrección | R-R1…R-R3 | `test_resistance.py` | ✅ |
| T5 | Filtro de entrada y tamaño | R-E1…R-E6 | `test_strategy.py` | ✅ |
| T6 | Gestión de posición: stops, reducciones, salida | R-S1, R-S3, R-S4, R-D1…R-D5 | `test_strategy.py` | ✅ |
| T7 | Cliente Alpaca + bróker simulado | R-X3 | `test_executor.py` | ✅ (simulado) |
| T8 | Ejecutor semanal | R-E7, R-E8, R-S2, R-D6, R-X1, R-X2, R-X4 | `test_executor.py` | ✅ |
| T9 | Guardián diario | R-S5 | `test_executor.py` | ✅ |
| T10 | Universo y datos | R-U1…R-U4 | `test_data.py` (agregación) | ✅ parcial: la descarga real se prueba en la primera ejecución |
| T11 | Informe: rentabilidad y alfa | R-W1, R-W2 | `test_report.py` | ✅ |
| T12 | Panel web | R-W3…R-W6 | revisión visual con datos de ejemplo | ✅ |
| T13 | Workflows de GitHub Actions | R-X, R-W6 | primera ejecución manual | ⏳ pendiente del usuario |
| T14 | Prueba de extremo a extremo contra Alpaca paper | todos | `--dry-run` y luego ejecución real | ⏳ pendiente del usuario |
| T15 | Completar `universe/stoxx600.csv` | R-U3 | — | ⏳ lista semilla incluida |

## Siguiente iteración (no incluida)

- Backtest de las reglas sobre histórico antes de pasar a dinero real.
- Filtro sectorial (fase del sector, como recomienda Weinstein).
- Ejecución en Europa con un bróker que la permita.
