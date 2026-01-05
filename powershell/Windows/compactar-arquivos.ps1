$dirOrigem = "caminho/origem"
$dirSaida = "caminho/saida"

$nomeBase = "nomeBase"
$logFile = "caminho/log.log"

function Registrar-Log {
  param (
    [string]$mensagem
  )
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $logEntry = "$timestamp - $mensagem"
  Add-Content -Path $logFile -Value $logEntry -Append
}

if (-not (Test-Path $dirSaida){
  New-Item -Path $dirSaida -ItemType Directory -Force
  Registrar-Log "Diretório de saída criado: $dirSaida"
})else {
  Registrar-Log "Diretório de saída já existe: $dirSaida"
}

$dataCorte = (Get-Date).AddDays(-60).Date

$oldFiles = Get-ChildItem -Path $dirOrigem -Recurse -File |
            Where-Object {$_.LastWriteTime.Date -lt $dataCorte}

if ($oldFiles.Count -gt 0) {
  Registrar-Log " Iniciar a compactação de $($oldFiles.Count) arquivo"

  foreach ($file in $oldFiles) {
    $nome_zip_individual = "$($file.Name)_$nomeBase-$timestamp.zip"
    $caminho_zip = Join-Path -Path $dirSaida -ChildName $nome_zip_individual
    
    try{
      Compress-Archive -Path $file.FullName -DestinationPath $caminho_zip -Force
      Registrar-Log "Arquivo '$($file.Name)' compactado com sucesso"
    } catch {
      Registrar-Log " Erro ao processar o arquivo '$($file.Name)': $_"
    }
  }
  Registrar-Log "Processamento de todos os arquivos antigos concluído"
} else{
  Registrar-Log "Nenhum arquivo com mais de 60 dias foi encontrado"
}