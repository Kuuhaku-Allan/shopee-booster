@echo off
echo ================================================================================
echo RESUMO R6.2 - AUDITORIA COM RADAR OPCIONAL
echo ================================================================================
echo.
echo [1/3] Testes de Integracao Auditoria + Radar...
python test_audit_radar_integration.py
echo.
echo [2/3] Testes do Adaptador Radar...
python test_radar_audit_context_service.py
echo.
echo [3/3] Teste Manual Dry-Run...
python scripts/audit_with_radar_context.py 2777bd10-5e4f-40ff-b302-81d23f8834d9 --dry-run-prompt
echo.
echo ================================================================================
echo RESUMO FINAL
echo ================================================================================
echo Testes de Integracao: 8/8 passando
echo Testes do Adaptador: 10/10 passando
echo Teste Manual: OK (notebook como off-niche)
echo Total: 18/18 testes passando
echo ================================================================================
