import boto3
import pandas as pd
from botocore.exceptions import ClientError

# ---| CONFIGURACAO |---
OUTPUTFILE = "Relatorio_AWS_Arquitetura_v2.xlsx"

# ---| FUNCOES AUXILIARES |---
def get_active_regions():
    """Descobre todas as regiões ativas na conta AWS."""
    print("--- [0/4] Descobrindo regiões ativas... ---")
    try:
        ec2 = boto3.client('ec2', region_name='us-east-1')
        regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]
        print(f"    -> Encontradas {len(regions)} regiões ativas.")
        return regions
    except ClientError:
        print("    [!] Erro ao listar regiões. Usando fallback 'us-east-1'.")
        return ['us-east-1'] # Fallback

def get_tag_value(tags, key):
    if not tags: return None
    for tag in tags:
        if tag['Key'] == key: return tag['Value']
    return None

def analyze_vpc_architecture(region_name, vpc_id, all_lambdas):
    """
    Analisa a arquitetura de rede de uma VPC especifica.
    """
    ec2_resource = boto3.resource('ec2', region_name=region_name)
    vpc = ec2_resource.Vpc(vpc_id)
    vpc_name = get_tag_value(vpc.tags, 'Name') or ""

    snet_details = []
    compute_details = []
    lambda_details = []
    vpc_details = []

    # 1. Mapeamento das tabelas de rotas para sub-redes (Pública vs Privada)
    snet_to_rtb = {}
    
    # Itera sobre todas as Route Tables da VPC para classificar
    for rtb in vpc.route_tables.all():
        is_public = False
        # Se tiver rota para IGW, é pública
        for route in rtb.routes:
            if route.gateway_id and route.gateway_id.startswith('igw-'):
                is_public = True
                break
        
        # Mapeia as subnets associadas explicitamente
        for association in rtb.associations:
            if association.subnet_id:
                snet_to_rtb[association.subnet_id] = "Public" if is_public else "Private"

    # 2. Iterar sobre as VPCs
    for net in vpc.vpcs.all():
      vpc_name = vpc_name or get_tag_value(net.tags, 'Name') or ""
      vpcn_id = net.id
      vpc_cidr = net.cidr_block
      # Armazena detalhes da VPC
      vpc_details.append({
          'Region': region_name,
          'VPC ID': vpcn_id,
          'VPC Name': vpc_name,
          'CIDR Block': vpc_cidr
      })

    # 3. Iterar sobre as sub-redes
    for snet in vpc.subnets.all():
        # Define se é Publica/Privada (Default: Private se usar a Main Route Table implícita)
        snet_type = snet_to_rtb.get(snet.id, "Private (Implicit/Main)")
        
        snet_details.append({
            'Region': region_name,
            'VPC ID': vpc_id,
            'VPC Name': vpc_name,
            'Subnet ID': snet.id,
            'CIDR Block': snet.cidr_block,
            'Availability Zone': snet.availability_zone,
            'Subnet Type': snet_type
        })

        # 4. Listar EC2s na sub-rede
        # O filtro acontece no lado da AWS, muito eficiente
        for ec2 in snet.instances.all():
            ebs_volumes = [m['Ebs']['VolumeId'] for m in ec2.block_device_mappings if 'Ebs' in m]
            
            compute_details.append({
                'Region': region_name,
                'VPC ID': vpc_id,
                'Subnet ID': snet.id,
                'EC2 Instance ID': ec2.id,
                'Instance Type': ec2.instance_type,
                'EBS Volumes': ", ".join(ebs_volumes) if ebs_volumes else "-"
            })
        
        # 5. Obter Lambdas associadas a ESTA Subnet especifica
        # Iteramos sobre a lista pré-carregada (em memória)
        for function in all_lambdas:
            # Verifica se a função tem config de VPC
            if 'VpcConfig' in function and function['VpcConfig'].get('VpcId') == vpc_id:
                # CORREÇÃO CRÍTICA: Verifica se a Lambda está nesta Subnet específica
                if snet.id in function['VpcConfig'].get('SubnetIds', []):
                    lambda_details.append({
                        'Region': region_name,
                        'VPC ID': vpc_id,
                        'Subnet ID': snet.id,
                        'Lambda Function Name': function['FunctionName'],
                        'Lambda Function ARN': function['FunctionArn']
                    })

    return snet_details, compute_details, lambda_details

def scan_regional_resources(region):
    print(f"   -> Varrendo região: {region}...")
    
    ec2_resource = boto3.resource('ec2', region_name=region)
    lambda_client = boto3.client('lambda', region_name=region)
    
    # 2. OTIMIZAÇÃO: Busca Lambdas UMA vez por região
    region_lambdas = []
    try:
        paginator = lambda_client.get_paginator('list_functions')
        for page in paginator.paginate():
            region_lambdas.extend(page['Functions'])
    except ClientError:
        print(f"      [!] Erro ao listar Lambdas na região {region}. Pulando...")
    
    vpc_data = []
    comp_data = []
    lmb_data = []

    # 3. Iterar sobre VPCs passando a lista de Lambdas
    try:
        for vpc in ec2_resource.vpcs.all():
            # CORREÇÃO: Passando region_lambdas como argumento
            v, c, l = analyze_vpc_architecture(region, vpc.id, region_lambdas)
            vpc_data.extend(v)
            comp_data.extend(c)
            lmb_data.extend(l)
    except ClientError as e:
        print(f"      [!] Erro ao acessar VPCs: {e}")

    return vpc_data, comp_data, lmb_data

# --- GLOBAIS ---
def scan_global_resources():
    print("\n--- [3/4] Varrendo Recursos GLOBAIS ---")
    data = []
    
    def add(cat, svc, name, loc, det):
        data.append({'Region': loc, 'Category': cat, 'Service': svc, 'Name/ID': name, 'Details': det})

    # IAM
    try:
        iam = boto3.client('iam')
        for user in iam.list_users()['Users']:
            add('Security', 'IAM User', user['UserName'], 'Global', f"ID: {user['UserId']}")
    except Exception as e: print(f"   [Erro IAM]: {e}")

    # S3
    try:
        s3 = boto3.client('s3')
        for bucket in s3.list_buckets().get('Buckets', []):
            add('Storage', 'S3 Bucket', bucket['Name'], 'Global', f"Created: {bucket['CreationDate']}")
    except Exception as e: print(f"   [Erro S3]: {e}")

    # CloudFront
    try:
        cf = boto3.client('cloudfront')
        dists = cf.list_distributions().get('DistributionList', {})
        for item in dists.get('Items', []):
            add('CDN', 'CloudFront', item['Id'], 'Global', f"Domain: {item['DomainName']}")
    except Exception as e: print(f"   [Erro CloudFront]: {e}")

    # Route53
    try:
        r53 = boto3.client('route53')
        for zone in r53.list_hosted_zones()['HostedZones']:
            add('DNS', 'Hosted Zone', zone['Name'], 'Global', f"Private: {zone['Config']['PrivateZone']}")
    except Exception as e: print(f"   [Erro Route53]: {e}")

    return pd.DataFrame(data)

# --- EXECUÇÃO ---
if __name__ == "__main__":
    print("Iniciando Scan v2.1 (Architecture Audit)...")
    
    regions = get_active_regions()
    
    all_vpc_data = []
    all_ec2_data = []
    all_lmb_data = []
    
    # Global
    df_global = scan_global_resources()

    print("\n--- [2/3] Varrendo Regiões ---")
    for region in regions:
        # CORREÇÃO: Removido argumento inválido vpc_name=None
        v, c, l = scan_regional_resources(region)
        all_vpc_data.extend(v)
        all_ec2_data.extend(c)
        all_lmb_data.extend(l)

    print("\n--- [3/3] Gerando Excel ---")
    try:
        with pd.ExcelWriter(OUTPUTFILE, engine='openpyxl') as writer:
            # Aba Global
            if not df_global.empty: 
                df_global.to_excel(writer, sheet_name='Global Resources', index=False)
            
            # Aba Rede (VPC/Subnet)
            if all_vpc_data:
                pd.DataFrame(all_vpc_data).to_excel(writer, sheet_name='VPC Network Architecture', index=False)
            
            # Aba Compute (EC2)
            if all_ec2_data:
                pd.DataFrame(all_ec2_data).to_excel(writer, sheet_name='EC2 Inventory', index=False)
                
            # Aba Serverless (Lambda)
            if all_lmb_data:
                pd.DataFrame(all_lmb_data).to_excel(writer, sheet_name='Lambda Inventory', index=False)
                
        print(f"SUCESSO! Arquivo salvo: {OUTPUTFILE}")
    except PermissionError:
        print(f"[ERRO] Não foi possível salvar o arquivo. Feche o Excel '{OUTPUTFILE}' e tente novamente.")