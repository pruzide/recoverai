Write-Host "=== RecoverAI pitch demo ===" -ForegroundColor Cyan

$suffix = Get-Random -Maximum 99999

$merchant = (docker compose exec db psql -U postgres -d recoverai -Atc "SELECT id FROM merchants WHERE name='Demo Merchant';").Trim()
Write-Host "Merchant: $merchant"

Write-Host "`n[1/2] Sending payment.failed webhook..." -ForegroundColor Yellow
python scripts/send_local_webhook.py $merchant payment.failed pay_pitch_$suffix evt_fail_$suffix expired_instrument

Start-Sleep -Seconds 4

Read-Host "`nPress ENTER to send payment.captured"

$case    = (docker compose exec db psql -U postgres -d recoverai -Atc "SELECT id FROM recovery_cases WHERE status='WAITING' ORDER BY created_at DESC LIMIT 1;").Trim()
$origPay = (docker compose exec db psql -U postgres -d recoverai -Atc "SELECT p.provider_payment_id FROM recovery_cases rc JOIN payments p ON p.id = rc.payment_id WHERE rc.status='WAITING' ORDER BY rc.created_at DESC LIMIT 1;").Trim()
Write-Host "Case: $case"

Write-Host "`n[2/2] Sending payment.captured webhook..." -ForegroundColor Yellow
python scripts/send_recovery_success_webhook.py $merchant $case 7999 evt_cap_$suffix $origPay

Write-Host "`nDone. Refresh dashboard: case should be RECOVERED." -ForegroundColor Green