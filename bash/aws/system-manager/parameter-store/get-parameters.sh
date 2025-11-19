#! /bin/bash

# ==============================================================================
# Author:         Hellen Iwata
# Create date:    2025-06-06
# Description:    Este script busca e lista parâmetros do AWS SSM Parameter Store
#                 que correspondem a uma chave de busca e um ambiente.
#                 Ele inclui um mecanismo de retentativa para lidar com
#                 problemas de API transitórios.
#
# Dependencies:   - aws-cli (configurado com as credenciais apropriadas)
#
# IAM Permissions: As credenciais da AWS precisam da seguinte permissão:
#                  - ssm:DescribeParameters
#
# Usage:          ./get-parameters.sh <chave-de-busca> <ambiente>
#                 Exemplo: ./get-parameters.sh my-app-db-pass dev
# ==============================================================================

if [ $# -ne 2 ]; then
	echo -e "\033[0;31mERRO: Número inválido de argumentos.\033[0m"
	echo "USO: $0 <chave-de-busca> <ambiente>"
	exit 1
fi

name_parameter=$1
env=$2

timestamp=$(date +%Y-%m-%d_%H-%M-%S)
output_file="get_ssm_parameter_store_log-$env-$timestamp.log"

max_retries=4
retry_delay=5
retry_count=0


log(){
	local LEVEL=$1
	shift
	local MESSAGE="$@"
	local log_line="${timestamp} [${LEVEL}] ${MESSAGE}"
	
	case "$LEVEL" in
		INFO) COLOR="\033[0;32m";;
		WARN) COLOR="\033[0;33m";;
		ERROR) COLOR="\033[0;31m";;
		*) COLOR="\033[0m";;
	esac

	echo -e "$COLOR$log_line\033[0m"
	echo "$log_line" >> "$output_file"
}

if ! command -v aws &> /dev/null; then
    log "ERROR" "O utilitário 'aws-cli' é necessário, mas não foi encontrado."
    exit 1
fi

get_parameter(){
	
	while [ $retry_count -lt $max_retries ]; do
		
		log "INFO" "Retry get: '$retry_count'"
		params=$(aws ssm describe-parameters \
			--query "Parameters[?contains(Name,\"$name_parameter\")].Name" \
			--output text
		)

		if [ -n "$params" ]; then	
			log "INFO" "Parameters found in attemp: '$retry_count'"
			return 0 # Sucesso, sair da função
		fi

		log "WARN" "No parameter found. Trying again after $retry_delay seconds"
		sleep $retry_delay
		retry_count=$((retry_count + 1))
	done

	log "ERROR" "No parameters containing '$name_parameter' found after $max_retries attempts"
	return 1
}


show_parameters(){
	log "INFO" "Showing parameters"
	echo "$params" | sed 's/^/ - /' | tee -a "$output_file"
}

log "INFO" "Iniciando a busca por parâmetros contendo '$name_parameter' no ambiente '$env'"

get_parameter
show_parameters

log "INFO" "Busca finalizada. LOG: '$output_file'"
