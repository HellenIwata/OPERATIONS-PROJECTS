#! /bin/bash

# ==============================================================================
# Author:         Hellen Iwata
# Create date:    2025-09-30
# Version:        1.0.0
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

echo "[" > "$output_file"

namespace=$(kubectl get ns --no-headers -o custom-columns=":metadata.name")
firsts_entry=true

for ns in $namespace; do
	pods=$(kubectl get pods -n "$ns" --no-headers | grep -Ei "Crash|Evicted|Error|ContainerCreating" | awk  '{print $1}')
	for pod in $pods; do
		if [ "$firsts_entry" == true ]; then
			firsts_entry=false
		else
			echo "," >> "$output_file"
		fi
		echo "{\"namespace\": \"$ns\", \"pod_name\": \"$pod\"}" >> "$output_file"
	done
done

echo "]" >> "$output_file"

echo "OUTPUT FILE: '$output_file'"