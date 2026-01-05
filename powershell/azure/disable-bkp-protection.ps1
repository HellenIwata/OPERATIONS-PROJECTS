$vaultName = "my-vault"
$workloadType = "SQLDataBase"
$bkpMgmType = "AzureWorkload"
$tenantId = "tenant-id"
$subscriptionId = "subscription-id"
$resourcesIdsPath = "resources\ids\path.json"
$logFile = "Disable-backup-vault.log"

Write-Host "="*50
Write-Host "= INICIANDO O SCRIPT PARA DESABILITAR A PROTECAO DE BACKUP DO RECOVERY SERVICES VAULT: $vaultName ="
Write-Host "="*50

try {
  Write-Host "Tentando conectar a conta do Azure... " -ForegroundColor Yellow
  Connect-AzAccount -TenantId $tenantId -SubscriptionId $subscriptionId -ErrorAction Stop
  Write-Host "Conexao com o Azure estabelecida com sucesso" -ForegroundColor Green
}
catch {
  Write-Error " Erro ao conecta a conta do Azure: $($_.Exception.Message)"
  Registrar_Logs " Erro critico: Falha ao conectar à conta do Azure. Mensagem: $($_.Exception.Message)"
  Exit 1
}

function Registrar_Logs {
  param (
    [string]$mensagem,
    [string]$tipo = "INFO"
  )
  $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  "$timestamp - $($tipo.ToUpper()) : $mensagem" | Out-File -Append -FilePath $logFile

  if($tipo -eq "ERROR){
    Write-Host "$timestamp - ERROR - $mensagem" -ForegroundColor Red
  } elseif ($tipo -eq "WARN"){
    Write-Host "$timestamp - WARN - $mensagem" -ForegroundColor Yellow
  } else {
    Write-Host "$timestamp - INFO - $mensagem" -ForegroundColor Cyan
  }
}

$resourcesIds = @()
try {
  Write-Host "Lendo IDs dos recursos do arquivo: $resourcesIdsPath" -ForegroundColor Yellow
  if (Test-Path $resourcesIdsPath) {
    $resourcesIds = Get-Content -Path $resourcesIdsPath | ConvertFrom-Json -ErrorAction Stop
    if($resourcesIds.Count -eq 0){
      Resgistrar_Logs "Nenhum ID de recurso encontrado no arquivo '$resourcesIdsPath'. Verifique o conteúdo" -tipo "WARN"
      Exit 0
    }
    Write-Host "IDs dos recursos carregados com sucesso. Total: $resourcesIds.Count" -ForegroundColor Green
  } else {
    throw "O arquivo especificado não foi encontrado: $resourcesIdsPath"
  }
} catch {
  Write-Error "Erro ao ler ou processar o arquivo de IDs dos recursos: $($_.Exception.Message)" -ForegroundColor Red
  Registrar_logs "ERRO CRÍTICO: Falha ao ler o arquivo de IDs dos recursos. Mensagem: $($_.Exception.Message)" -tipo "ERROR"
  Exit 1
}


Write-Host "INICIANDO O PROCESSO DE DESABILITAR A PROTECAO DE BACKUP PARA OS RECURSOS LISTADOS..." -ForegroundColor Yellow

$totalResources = $resourcesIds.Count
$processedResources = 0

foreach ($resourceId in $resourceIds) {
  $processedResources++
  $remainingResources = $totalResources - $processedResources

  Write-Host " `nProcessando recurso ($processedResources de $totalResources) com o ID: $resourceId. Recursos restantes: $remainingResources" -ForegroundColor Yellow

  try{
    az backup protection disable --backup-management -type $bkpMgmType `
    --resource-id $resourceId `
    --workload-type $workloadType `
    --delete-backup-data true `
    --yes `
    --only-show-errors

    Registrar_Logs "Protecao de backup desabilitada com sucesso para: $resourceId" -tipo "INFO"
    Write-Host "Recursos restantes para processar: $remainingResources" -ForegroundColor Yellow

  } catch {
    $errorMessage = $_.Exception.Message
    Registrar_Logs "Erro ao desabilitar a protecao de backup para o item com ID '$resourceId': $($errorMessage)" -tipo "ERROR"
  }
}

Write-Host "="*50
Write-Host " SCRIPT CONCLUIDO" -ForegroundColor Green
Write-Host "="*50

Registrar_Logs "O Script foi concluido." -tipo "INFO"
