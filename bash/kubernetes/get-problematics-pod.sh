#! /bin/bash

# ==============================================================================
# Author:         Hellen Iwata
# Create date:    2025-09-30
# Version:        1.0.1
# Description:    Este script varre todos os namespaces de um cluster Kubernetes
#                 em busca de pods com status problemáticos (como Crash, Evicted,
#                 Error, ContainerCreating). As informações de namespace e nome
#                 dos pods encontrados são salvas em um arquivo de saída no
#                 formato JSON.
#
# Dependencies:   - kubectl (configurado e com acesso ao cluster)
#
# Output Format:  O script gera um arquivo JSON contendo uma lista de objetos,
#                 cada um com o namespace e o nome do pod problemático.
#
# Usage:          ./get-problematics-pod.sh
# ==============================================================================

# VARIABLES
timestamp=$(date +%Y-%m-%d_%H-%M-%S)
output_file="problematic_pods_$timestamp.json"

log "INFO" "Buscando pods com status problemáticos em todos os namespaces..."

kubectl get pods --all-namespaces -o json | jq -r '
  .items[] | 
  select(.status.phase | test("Failed|Unknown")) or 
  (.status.containerStatuses[]? | select(.state.waiting.reason == "CrashLoopBackOff" or .state.terminated.reason == "Error")) |
  {namespace: .metadata.namespace, pod_name: .metadata.name}
' | jq -s '.' > "$output_file"

log "SUCCESS" "Verificação concluída. Arquivo de saída gerado."
log "INFO" "ARQUIVO DE SAÍDA: '$output_file'"