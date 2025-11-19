#! /bin/bash

# ==============================================================================
# Author:         Hellen Iwata
# Create date:    2025-09-30
# Version:		    1.0.0
# Description:    Este script coleta logs de uma lista de pods do Kubernetes
#                 especificados em um arquivo JSON. Ele itera sobre cada pod
#                 no JSON, extrai os logs usando 'kubectl' e os salva em um
#                 único arquivo de saída.
#
# Dependencies:   - kubectl (configurado e com acesso ao cluster)
#                 - jq
#
# JSON format:    O script espera um arquivo JSON com uma lista de objetos,
#                 onde cada objeto contém 'namespace' e 'pod_name'.
#                 Exemplo:
#                 [
#                   { "namespace": "default", "pod_name": "meu-pod-1" },
#                   { "namespace": "dev", "pod_name": "meu-pod-2" }
#                 ]
#
# Usage:          ./get-logs-problematics-pod.sh <caminho-para-o-arquivo.json>
# ==============================================================================

# Verificar parametro inicial para executar o script
if [ -z "$1" ]; then
	echo "USE: $0 <json-file>"
	exit 1
fi


# Definir a variaveis do script
json_file=$1
timestamp=$(date +%Y-%m-%d_%H-%M-%S)
output_file=$"logs_problematic_pods_$timestamp.log"

if [ ! -f "$json_file" ]; then
	echo "File not found: '$json_file'"
	exit 1
fi

# Verificar o utilitario 'jq'

if ! command -v jq >/dev/null; then
	echo "The 'jq' is required to process JSON"
	exit 1
fi

# Executar o script

echo "====== List of pods used for log collection ======"
cat "$json_file" >> "$output_file"
echo -e "\n\n" >> "$output_file"

# Processar cada entrada do JSON
jq -c '.[]' "$json_file" | while read -r pod_info; do $
	namespace=$(jq -r '.namespace' <<< "$pod_info")
	pod_name=$(jq -r '.pod_name' <<< "$pod_info")

	echo "==== POD LOGS: '$pod_name' in '$namespace' ====" >> "$output_file"$
	kubectl -n "$namespace" logs "$pod_name" >> "$output_file" 2>&1
	echo -e "\n\n" >> "$output_file"
done

echo "OUTPUT FILE: '$output_file'"