#! /bin/bash

# ==============================================================================
# Author:         Hellen IWata
# Create date:    2025-10-31
# Version:        1.0.0
# Description:    Este script agrupa usuários de um servidor AWS Transfer Family
#                 pelo seu IAM Role. Para cada role, ele lista os usuários
#                 associados, seus mapeamentos de diretório e as políticas IAM
#                 anexadas à role.
#
# Dependencies:   - aws-cli (configurado com as credenciais apropriadas)
#                 - jq
#
# IAM Permissions: As credenciais da AWS precisam das seguintes permissões:
#                  - transfer:ListUsers
#                  - transfer:DescribeUser
#                  - iam:ListAttachedRolePolicies
#
# Configuration:  Defina o 'server_id' na seção de configuração ou passe-o
#                 como um argumento de linha de comando.
#
# Usage:          ./get-users-role-grouped.sh [server-id]
#                 Exemplo: ./get-users-role-grouped.sh s-1234567890abcdef0
# ==============================================================================

# --- CONFIG ---
# ID do servidor Transfer Family. Pode ser substituído pelo argumento da linha de comando.
server_id="s-xxxxxxxxxxxxxxxxx"
output_file="transfer_roles_grouped.json"
# --- FIM DA CONFIG ---

# Sobrescreve o server_id se um argumento for fornecido
if [ -n "$1" ]; then
    server_id=$1
fi

log(){
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] - $1"
}

# --- VERIFICAÇÃO DE DEPENDÊNCIAS ---
if ! command -v aws &> /dev/null; then
    log "ERRO: O utilitário 'aws-cli' é necessário, mas não foi encontrado."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    log "ERRO: O utilitário 'jq' é necessário, mas não foi encontrado."
    exit 1
fi

if [[ "$server_id" == "s-xxxxxxxxxxxxxxxxx" ]]; then
    log "ERRO: Por favor, edite o script para definir o 'server_id' ou passe-o como argumento."
    exit 1
fi

log "Iniciando agrupamento de usuários por role para o servidor: $server_id"

log "Buscando todos os usuários..."
users_json=$(aws transfer list-users --server-id "$server_id" --output json)
if [ $? -ne 0 ]; then
    log "ERRO: Falha ao listar usuários para o servidor '$server_id'. Verifique o ID e as permissões."
    exit 1
fi

user_details="[]"
log "Buscando detalhes para cada usuário..."
for username in $(echo "$users_json" | jq -r '.Users[].UserName'); do
    log "Processando usuário: $username"
    detail=$(aws transfer describe-user --server-id "$server_id" --user-name "$username" --query 'User' --output json)
    user_details=$(echo "$user_details" | jq --argjson detail "$detail" '. + [$detail]')
done

log "Agrupando usuários por role e buscando políticas IAM..."
echo "$user_details" | jq '
  # 1. Agrupa todos os usuários pela Role ARN
  group_by(.Role) |
  # 2. Mapeia sobre cada grupo (cada role)
  map({
    # Extrai o nome da role a partir da ARN
    "ROLE_NAME": (.[0].Role | split("/") | .[-1]),
    # Para cada role, busca as políticas IAM anexadas (executa um comando shell)
    "POLICIES": (
      "aws iam list-attached-role-policies --role-name \(.[0].Role | split("/") | .[-1]) --query '\''AttachedPolicies[*].PolicyName'\'' --output json" |
      (shell | fromjson)
    ),
    # Mapeia os usuários dentro do grupo para um formato mais limpo
    "USERS_IN_ROLE": map({
      "USERNAME": .UserName,
      # Lida com o caso de não haver mapeamento de diretório
      "HOME_DIRECTORY_MAPPING": (.HomeDirectoryMappings[0].Target // "N/A")
    })
  })
' > "$output_file"

if [ $? -eq 0 ]; then
    log "Agrupamento concluído com sucesso."
    log "Arquivo de saída salvo em: $output_file"
else
    log "ERRO: Falha ao processar os dados com jq."
fi