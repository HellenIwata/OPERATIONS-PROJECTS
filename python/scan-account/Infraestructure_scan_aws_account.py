import boto3
import pandas as pd
from botocore.exceptions import ClientError, EndpointConnectionError

# --- CONFIGURAÇÃO ---
OUTPUT_FILE = "Relatorio_AWS_MultiRegion.xlsx"

def get_active_regions():
    """Descobre todas as regiões ativas na conta AWS."""
    print("--- [0/3] Descobrindo regiões ativas... ---")
    try:
        # Usamos us-east-1 como ponto de entrada padrão para descoberta
        ec2 = boto3.client('ec2', region_name='us-east-1')
        regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]
        print(f"    -> Encontradas {len(regions)} regiões ativas.")
        return regions
    except ClientError as e:
        print(f"Erro ao listar regiões: {e}")
        return ['us-east-1'] # Fallback

def get_tag_value(tags, key):
    if not tags: return None
    for tag in tags:
        if tag['Key'] == key: return tag['Value']
    return None

# --- VARREDURA DE RECURSOS GLOBAIS (Executa 1 vez) ---
def scan_global_resources():
    print("\n--- [1/3] Varrendo Recursos GLOBAIS (IAM, S3, CloudFront, Route53) ---")
    data = []
    
    def add(cat, svc, name, loc, det):
        data.append({'Region': loc, 'Category': cat, 'Service': svc, 'Name/ID': name, 'Details': det})

    # IAM
    try:
        iam = boto3.client('iam') # Endpoint global padrão
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

# --- VARREDURA DE RECURSOS REGIONAIS (Executa N vezes) ---
def scan_regional_resources(region):
    """Varre VPCs e Serviços Regionais de uma região específica."""
    print(f"   -> Varrendo região: {region}...")
    
    vpc_data = []
    service_data = []
    
    # Inicializa clientes na região específica
    try:
        ec2_res = boto3.resource('ec2', region_name=region)
        ec2_cli = boto3.client('ec2', region_name=region)
        lmb_cli = boto3.client('lambda', region_name=region)
        eks_cli = boto3.client('eks', region_name=region)
        ddb_cli = boto3.client('dynamodb', region_name=region)
        rds_cli = boto3.client('rds', region_name=region)
    except Exception as e:
        print(f"      [Erro Conexão {region}]: Pular região.")
        return [], []

    # 1. VPC Hierarchy
    try:
        for vpc in ec2_res.vpcs.all():
            vpc_name = get_tag_value(vpc.tags, 'Name') or vpc.id
            subnets = list(vpc.subnets.all())
            
            if not subnets:
                vpc_data.append({'Region': region, 'VPC Name': vpc_name, 'Resource Type': 'Empty VPC', 'Details': 'Sem Subnets'})
                continue

            for subnet in subnets:
                subnet_name = get_tag_value(subnet.tags, 'Name') or subnet.id
                # Pega ENIs
                enis = ec2_cli.describe_network_interfaces(Filters=[{'Name': 'subnet-id', 'Values': [subnet.id]}])['NetworkInterfaces']
                
                if not enis:
                    vpc_data.append({'Region': region, 'VPC Name': vpc_name, 'Subnet Name': subnet_name, 'Resource Type': 'Empty Subnet', 'Details': '-'})
                    continue

                for eni in enis:
                    desc = eni.get('Description', '').lower()
                    res_type = "Unknown Interface"
                    res_id = eni['NetworkInterfaceId']
                    
                    if eni.get('Attachment') and eni['Attachment'].get('InstanceId'):
                        res_type = "EC2 Instance"
                        res_id = eni['Attachment']['InstanceId']
                    elif 'rds' in desc: res_type = "RDS Database"
                    elif 'elb' in desc: res_type = "Load Balancer"
                    elif 'nat gateway' in desc: res_type = "NAT Gateway"
                    elif 'lambda' in desc: res_type = "Lambda Interface"

                    vpc_data.append({
                        'Region': region,
                        'VPC ID': vpc.id, 'VPC Name': vpc_name,
                        'Subnet ID': subnet.id, 'Subnet Name': subnet_name,
                        'Resource Type': res_type, 'Resource ID': res_id, 'Details': desc
                    })
    except ClientError: pass # Ignora erro se não tiver permissão de VPC

    # 2. Outros Serviços Regionais (Fora da VPC ou complementares)
    
    # Lambda
    try:
        paginator = lmb_cli.get_paginator('list_functions')
        for page in paginator.paginate():
            for func in page['Functions']:
                service_data.append({'Region': region, 'Category': 'Compute', 'Service': 'Lambda', 'Name/ID': func['FunctionName'], 'Details': func['Runtime']})
    except: pass

    # DynamoDB
    try:
        for table in ddb_cli.list_tables()['TableNames']:
            service_data.append({'Region': region, 'Category': 'Database', 'Service': 'DynamoDB', 'Name/ID': table, 'Details': 'Table'})
    except: pass

    # EKS
    try:
        for cluster in eks_cli.list_clusters()['clusters']:
            service_data.append({'Region': region, 'Category': 'Compute', 'Service': 'EKS Cluster', 'Name/ID': cluster, 'Details': 'K8s Cluster'})
    except: pass

    # RDS (Instâncias para pegar detalhes extras que a ENI não dá)
    try:
        for db in rds_cli.describe_db_instances()['DBInstances']:
            service_data.append({'Region': region, 'Category': 'Database', 'Service': 'RDS Instance', 'Name/ID': db['DBInstanceIdentifier'], 'Details': db['Engine']})
    except: pass

    return vpc_data, service_data

# --- EXECUÇÃO PRINCIPAL ---
if __name__ == "__main__":
    print(f"Iniciando Auditoria Multi-Region...")
    
    # 1. Coleta Global
    df_global = scan_global_resources()
    
    # 2. Coleta Regional (Loop)
    all_vpc_rows = []
    all_services_rows = []
    
    regions = get_active_regions()
    
    print("\n--- [2/3] Iniciando varredura iterativa por região ---")
    for region in regions:
        vpc_rows, service_rows = scan_regional_resources(region)
        all_vpc_rows.extend(vpc_rows)
        all_services_rows.extend(service_rows)

    # 3. Consolidação
    print("\n--- [3/3] Gerando Excel ---")
    df_vpc_final = pd.DataFrame(all_vpc_rows)
    df_services_final = pd.DataFrame(all_services_rows)
    
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        # Aba 1: Global
        if not df_global.empty:
            df_global.to_excel(writer, sheet_name='Global Resources', index=False)
        
        # Aba 2: Rede/VPC (Topologia)
        if not df_vpc_final.empty:
            # Reordenar colunas para Region ficar no começo
            cols = ['Region'] + [c for c in df_vpc_final.columns if c != 'Region']
            df_vpc_final[cols].to_excel(writer, sheet_name='VPC Hierarchy', index=False)
            
        # Aba 3: Outros Serviços Regionais
        if not df_services_final.empty:
            cols = ['Region'] + [c for c in df_services_final.columns if c != 'Region']
            df_services_final[cols].to_excel(writer, sheet_name='Regional Services', index=False)

    print(f"SUCESSO! Relatório completo salvo em: {OUTPUT_FILE}")