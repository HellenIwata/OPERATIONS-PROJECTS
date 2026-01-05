$vaultName = "my-vault"
$certName = "cert1"
$interval = 300

Write-Host " === Monitorando status do certificado $certName  do KV '$vaultName' a cada $interval segundos === "

while ($true) {
  try {
    $statusInfo = az keyvault certificate pending show `
    --vault-name $vaultName `
    --name $certName `
    --output json | ConvertFrom-Json

    $status = $statusInfo.status
    $cancel = $statusInfo.cancellationRequested

    $time = Get-Date -Format "HH:mm:ss"
    Write-Host "[$time] - Status: $status - Cancelamento solicitado: $cancel"

    if ($status -ne "inProgress") {
      Write-Information " Operação finalizada. Status atual: $status"
      break
    }
  }
  catch {
    Write-Information " Não foi possível obter o status ( pode ja estar finalizado)"
    break
  }
  Start-Sleep -s $interval
}
