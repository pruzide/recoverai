Write-Host "=== RecoverAI pitch demo ===" -ForegroundColor Cyan

$suffix = Get-Random -Maximum 99999

$merchant = (docker compose exec db psql -U postgres -d recoverai -Atc "SELECT id FROM merchants WHERE name='Demo Merchant';").Trim()
Write-Host "Merchant: $merchant"

Write-Host "`n[1/2] Sending payment.failed webhook..." -ForegroundColor Yellow
python scripts/send_local_webhook.py $merchant payment.failed pay_pitch_$suffix evt_pitch_$suffix expired_instrument

Start-Sleep -Seconds 4

Read-Host "`nPress ENTER to send payment.captured"

$case = (docker compose exec db psql -U postgres -d recoverai -Atc "SELECT id FROM recovery_cases ORDER BY created_at DESC LIMIT 1;").Trim()
Write-Host "Case: $case"

Write-Host "`n[2/2] Sending payment.captured webhook..." -ForegroundColor Yellow
python scripts/send_recovery_success_webhook.py $merchant $case 7999 evt_pitch_$suffix pay_pitch_$suffix

Write-Host "`nDone. Refresh dashboard: case should be RECOVERED." -ForegroundColor Green