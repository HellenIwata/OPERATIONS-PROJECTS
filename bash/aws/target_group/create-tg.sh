#! /bin/bash

# ==============================================================================
# Author:         Hellen Iwata
# Create date:    2025-06-18
# Version:        1.0.0
# Description:    Este script automatiza a criação de múltiplos Target Groups (TGs)
#                 da AWS para um intervalo de portas especificado. Para cada porta,
#                 ele cria um TG do tipo TCP, registra uma instância EC2 nele e
#                 configura as verificações de saúde.
#
# Dependencies:   - aws-cli (configurado com as credenciais apropriadas)
#
# Configuration:  Antes de executar, preencha as variáveis na seção 'CONFIG'
#                 abaixo com os IDs corretos da sua VPC e instância EC2.
#
# Usage:          ./create-tg.sh
# ==============================================================================

# --- CONFIG ---
# PREENCHA ESTAS VARIÁVEIS ANTES DE EXECUTAR
vpc_id="vpc-xxxxxxxxxxxxxxxxx" # ID da sua VPC
ec2_id="i-xxxxxxxxxxxxxxxxx"  # ID da instância EC2 a ser registrada

# Início e fim do intervalo de portas
start_port=1035
end_port=1040
# --- FIM DA CONFIG ---

for port in $(seq $start_port $end_port); do
	tg_name="tg-${port}-${ec2_id}"
	echo "Creating target group '$tg_name' in port '$port'"

	aws elbv2 create-target-group \
		--name "$tg_name" \
		--port "$port" \
		--protocol TCP \
		--vpc-id $vpc_id \
		--target-type instance \
		--health-check-protocol TCP \
		--health-check-port 21 \
		--health-check-enabled \
		--health-check-interval-seconds 15 \
		--health-check-timeout-seconds 5 \
		--health-check-threshold-count 2 \
		--unhealthy-threshold-count 2

	echo "Target group '$tg_name' created"

	tg_arn=$(aws elbv2 describe-target-groups \
		--names "$tg_name" \
		--query 'TargetGroups[0].TargetGroupArn' \
		--output text)

	echo "Recording EC2 Instance '$ec2_id' in target group '$tg_name'"

	aws elbv2 register-targets \
		--target-group-arn "$tg_arn" \
		--targets Id="$ec2_id"

	echo "EC2 Instance registered in '$tg_name' at port '$port'"
	echo "-----------------------------------------------------"
done
