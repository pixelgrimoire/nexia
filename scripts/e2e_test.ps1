# E2E smoke test for local stack (PowerShell)
# - Posts a sample webhook into webhook-receiver (in-container HTTP call)
# - Checks Redis stream `nf:sent` before and after
# Run from repo root: .\scripts\e2e_test.ps1

Write-Host "Counting nf:sent (before)..."
$beforeRaw = & docker compose exec redis redis-cli XLEN nf:sent 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to query redis (before). Make sure docker compose is running."; exit 2
}
$before = 0
if ($beforeRaw -match '\d+') { $before = [int]$Matches[0] }
Write-Host "nf:sent before: $before"

# Base64 payload used to avoid shell quoting issues; adjust if needed
$b64 = 'eyJvYmplY3QiOiJ3aGF0c2FwcF9idXNpbmVzc19hY2NvdW50IiwiZW50cnkiOlt7ImlkIjoiZXRlX2lkIiwgImNoYW5nZXMiOlt7InZhbHVlIjp7Im1lc3NhZ2VzIjpbeyJmcm9tIjoiOTg3NiIsInRleHQiOnsicmVhbCI6IkVOREVfVEVTVCJ9fX1dfV19'

Write-Host "Posting test webhook into webhook-receiver (in-container)..."
$resp = & docker compose exec webhook-receiver python -c "import http.client,base64,hmac,hashlib; b64='$b64'; body=base64.b64decode(b64); secret=b'dev_secret'; sig='sha256='+hmac.new(secret, body, hashlib.sha256).hexdigest(); conn=http.client.HTTPConnection('127.0.0.1',8000); conn.request('POST','/api/webhooks/whatsapp',body,{'X-Hub-Signature-256':sig,'Content-Type':'application/json'}); r=conn.getresponse(); print(r.status); print(r.read().decode())"
Write-Host $resp

Start-Sleep -Seconds 1

Write-Host "Counting nf:sent (after)..."
$afterRaw = & docker compose exec redis redis-cli XLEN nf:sent 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to query redis (after)."; exit 3
}
$after = 0
if ($afterRaw -match '\d+') { $after = [int]$Matches[0] }
Write-Host "nf:sent after: $after"

if ($after -gt $before) {
    Write-Host "E2E PASS: nf:sent increased ($before -> $after)"
    exit 0
} else {
    Write-Host "E2E FAIL: nf:sent did not increase ($before -> $after)"
    exit 4
}
