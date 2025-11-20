#! /bin/bash

# ==============================================================================
# Author:         Hellen Iwata
# Create date:    2025-06-06
# Description:    Este script deleta de forma segura parâmetros do AWS SSM
#                 Parameter Store que correspondem a uma chave de busca.
#                 Ele inclui retentativas, backup automático, confirmação manual
#                 e um modo de simulação (dry-run).
#
# Dependencies:   - aws-cli (configurado com as credenciais apropriadas)
#                 - jq
#
# IAM Permissions: As credenciais da AWS precisam das seguintes permissões:
#                  - ssm:DescribeParameters
#                  - ssm:GetParameter
#                  - ssm:DeleteParameter
#
# Usage:          ./delete-parameters.sh <chave-de-busca> <ambiente> [--dry-run]
#                 Exemplo: ./delete-parameters.sh my-app-db-pass dev
#                 Exemplo (simulação): ./delete-parameters.sh my-app-db-pass prod --dry-run
# ==============================================================================

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
	echo -e "\033[0;31mERRO: Número inválido de argumentos.\033[0m"
	echo "USO: $0 <chave-de-busca> <ambiente> [--dry-run]"
	exit 1
fi

name_parameter=$1
env=$2

timestamp=$(date +%Y-%m-%d_%H-%M-%S)
output_file="delete_ssm_parameter_store_log-$env-$timestamp.log"
output_backup_file="parameters-backup-$name_parameter-$env-$timestamp.json"

max_retries=4
retry_delay=5
retry_count=0

dry_run=false

log(){
	local LEVEL=$1
	shift
	local MESSAGE="$@"
	local log_line="${timestamp} [${LEVEL}] ${MESSAGE}"
	
	case "$LEVEL" in
		INFO) COLOR="\033[0;32m";;
		WARN) COLOR="\033[0;33m";;
		ERROR) COLOR="\033[0;31m";;
		SUCCESS) COLOR="\033[0;34m";;
		*) COLOR="\033[0m";;
	esac

	echo -e "$COLOR$log_line\033[0m"
	echo "$log_line" >> "$output_file"
}

if  [ "$3" == "--dry-run" ]; then
	dry_run=true
fi

# --- VERIFICAÇÃO DE DEPENDÊNCIAS ---
if ! command -v aws &> /dev/null; then
    log "ERROR" "O utilitário 'aws-cli' é necessário, mas não foi encontrado."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    log "ERROR" "O utilitário 'jq' é necessário, mas não foi encontrado."
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

create_backup(){
	log "INFO" "Creating backup parameter '$name_parameter' in '$env' environment"
	params_json="[]"
	
	echo "$params" | while read -r name; do
		param=$(aws ssm get-parameter \
			--name "$name" \
			--with-decryption
		)
		params_json=$(echo "$params_json $param" | jq -s '.[0] +[.[1]]')
	done

	echo "$params_json" | jq '.' > "$output_backup_file"
	log "INFO" "Backup created in '$output_backup_file'"
}

verify_delete(){
	if [ "$dry_run" == true ]; then
		log "INFO" "ACTIVE MODE: Dry-run. Skip config delete"
		return 0
	fi

	log "WARN" "Do you wish PERMANENTLY DELETE the listed parameters? (y/n)"
	read -r confirm
	if [[  "$confirm" != 'y' && "$confirm" != 'Y' ]]; then
		echo "Operation cancelled" | tee -a "$output_file"
		exit 1
	fi
}

delete_parameter(){
	log "INFO" "Deleting parameters '$name_parameter' in '$env' environment"

	echo "$params" | while read -r name; do
		if [ "$dry_run" == true ]; then
			log "INFO" "[DRY-RUN] Simulação de exclusão do parâmetro: '$name'"
		else
			echo -n "> Parameter delete: '$name'" | tee -a "$output_file"
			if aws ssm delete-parameter --name "$name" > /dev/null 2>&1; then
				log "SUCCESS" "DELETED"
			else
				log "ERROR" "FAILED"
			fi
		fi
	done
	
	if [ "$dry_run" == true ]; then
		log "WARN" "DEACTIVE MODE: Dry-run. No changes will be made"
	else
		log "INFO" "Parameters deleted"
	fi	
}

# --- EXECUÇÃO PRINCIPAL ---
log "INFO" "Starting the delete for parameters containing '$name_parameter' int the '$env' environment"
if [ "$dry_run" == true ]; then
	log "WARN" "MODO ATIVO: [DRY-RUN]. No changes will be made"
fi

get_parameter
show_parameters
create_backup
verify_delete
delete_parameter

log "INFO" "Finished. LOG FILE: '$output_file'"
