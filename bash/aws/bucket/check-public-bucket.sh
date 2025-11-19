#! /bin/bash

# ==============================================================================
# Author:         Hellen Iwata
# Create date:    2025-11-06
# Version:        1.0.0
# Description:    Este script verifica todos os buckets S3 em uma conta da AWS
#                 para identificar aqueles que podem estar acessíveis publicamente.
#                 Ele se baseia principalmente na configuração do Public Access Block.
#                 Um bucket é sinalizado se:
#                 1. Não possui uma configuração de Public Access Block definida.
#                 2. Todas as suas configurações de Public Access Block estão
#                    definidas como 'false'.
#
# Dependencies:   - aws-cli (configurado com as credenciais apropriadas)
#                 - jq
#
# Output:         Gera um arquivo 'public-bucket.txt' com a lista de buckets
#                 sinalizados como potencialmente públicos.
# ==============================================================================

output_file="public-bucket.txt"

buckets=$(aws s3api list-buckets --query "Buckets[].Name" --output text)

echo "Public Buckets Found: "  >> $output_file
echo "----------------------" >> $output_file

for bucket in $buckets; do
	echo "Check this bucket: '$bucket'"

	config=$(aws s3api get-public-access-block \
		--bucket "$bucket" \
		--query "PublicAccessBlockConfiguration" \
		--output json 2>/dev/null)

	if [ $? -ne 0 ]; then
		echo "$bucket" | tee -a $output_file
		continue
	fi

	BLOCK_ACLS=$(echo "$config" | jq -r '.BlockPublicAcls')
	IGNORE_ACLS=$(echo "$config" | jq -r '.IgnorePublicAcls')
	BLOCK_POLICY=$(echo "$config" | jq -r '.BlockPublicPolicy')
	RESTRICT_BUCKET=$(echo "$config" | jq -r '.RestrictPublicBuckets')


	if [ "$BLOCK_ACLS" == "false" ] || \
		[ "$IGNORE_ACLS" == "false" ] || \
		[ "$BLOCK_POLICY" == "false" ] || \
		[ "$RESTRICT_BUCKET" == "false" ]; then
		echo "$bucket" | tee -a $output_file
	fi
done

echo "Output file: '$output_file'"