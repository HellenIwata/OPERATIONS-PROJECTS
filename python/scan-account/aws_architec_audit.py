import boto3
import pandas as pd
from botocore.exceptions import ClientError

# --- CONFIGURAÇÃO ---
OUTPUT_FILE = "Relatorio_AWS_IPs_Detalhados.xlsx"

def get_active_regions():
    """Descobre todas as regiões ativas na conta AWS."""
    print("--- [0/3] Descobrindo regiões ativas... ---")
    try:
        ec2 = boto3.client('ec2', region_name='us-east-1')
        regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]
        print(f"    -> Encontradas {len(regions)} regiões ativas.")
        return regions
    except ClientError:
        return ['us-east-1'] # Fallback

def get_tag_value(tags, key):
    if not tags: return None
    for tag in tags:
        if tag['Key'] == key: return tag['Value']
    return None

# --- GLOBAIS ---
def scan_global_resources():
    print("\n--- [1/3] Varrendo Recursos GLOBAIS ---")
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

# --- REGIONAIS ---
def scan_regional_resources(region):
    print(f"   -> Varrendo região: {region}...")
    vpc_data = []
    service_data = []
    
    try:
        ec2_res = boto3.resource('ec2', region_name=region)
        ec2_cli = boto3.client('ec2', region_name=region)
        # Outros clientes para serviços complementares
        lmb_cli = boto3.client('lambda', region_name=region)
        ddb_cli = boto3.client('dynamodb', region_name=region)
    except:
        return [], []

    # 1. Varredura de Rede
    try:
        for vpc in ec2_res.vpcs.all():
            vpc_name = get_tag_value(vpc.tags, 'Name') or vpc.id
            subnets = list(vpc.subnets.all())
            
            if not subnets:
                vpc_data.append({
                    'Region': region, 'VPC Name': vpc_name, 'Resource Type': 'Empty VPC', 
                    'Private IP': '-', 'Public IP': '-', 'Details': 'Sem Subnets'
                })
                continue

            for subnet in subnets:
                subnet_name = get_tag_value(subnet.tags, 'Name') or subnet.id
                
                # Pega ENIs
                enis = ec2_cli.describe_network_interfaces(Filters=[{'Name': 'subnet-id', 'Values': [subnet.id]}])['NetworkInterfaces']
                
                if not enis:
                    vpc_data.append({
                        'Region': region, 'VPC Name': vpc_name, 'Subnet Name': subnet_name, 
                        'Resource Type': 'Empty Subnet', 'Private IP': '-', 'Public IP': '-', 'Details': '-'
                    })
                    continue

                for eni in enis:
                    desc = eni.get('Description', '').lower()
                    res_type = "Unknown Interface"
                    res_id = eni['NetworkInterfaceId']
                    
                    # --- LÓGICA DE EXTRAÇÃO DE IPs ---
                    private_ips_list = []
                    public_ips_list = []
                    
                    for ip_info in eni.get('PrivateIpAddresses', []):
                        # Pega IP Privado
                        private_ips_list.append(ip_info.get('PrivateIpAddress'))
                        # Pega IP Público (se houver Associação)
                        if 'Association' in ip_info and 'PublicIp' in ip_info['Association']:
                            public_ips_list.append(ip_info['Association']['PublicIp'])
                    
                    # Formata para string (separado por vírgula se tiver mais de um)
                    str_private_ip = ", ".join(private_ips_list)
                    str_public_ip = ", ".join(public_ips_list) if public_ips_list else "-"
                    # ----------------------------------

                    # Identificação do Recurso
                    if eni.get('Attachment') and eni['Attachment'].get('InstanceId'):
                        res_type = "EC2 Instance"
                        res_id = eni['Attachment']['InstanceId']
                    elif 'rds' in desc: res_type = "RDS Database"
                    elif 'elb' in desc: res_type = "Load Balancer"
                    elif 'nat gateway' in desc: res_type = "NAT Gateway"
                    elif 'lambda' in desc: res_type = "Lambda Interface"

                    vpc_data.append({
                        'Region': region,
                        'VPC ID': vpc.id, 
                        'VPC Name': vpc_name,
                        'Subnet ID': subnet.id, 
                        'Subnet Name': subnet_name,
                        'Resource Type': res_type, 
                        'Resource ID': res_id, 
                        'Private IP': str_private_ip, # COLUNA NOVA
                        'Public IP': str_public_ip,   # COLUNA NOVA
                        'Details': desc
                    })
    except ClientError: pass

    # 2. Outros Serviços (Simplificado para brevidade)
    try:
        paginator = lmb_cli.get_paginator('list_functions')
        for page in paginator.paginate():
            for func in page['Functions']:
                service_data.append({'Region': region, 'Category': 'Compute', 'Service': 'Lambda', 'Name/ID': func['FunctionName'], 'Details': func['Runtime']})
    except: pass
    
    try:
        for table in ddb_cli.list_tables()['TableNames']:
            service_data.append({'Region': region, 'Category': 'Database', 'Service': 'DynamoDB', 'Name/ID': table, 'Details': 'Table'})
    except: pass

    return vpc_data, service_data

# --- EXECUÇÃO ---
if __name__ == "__main__":
    print("Iniciando Scan v2.0 (Com IPs detalhados)...")
    
    regions = get_active_regions()
    all_vpc = []
    all_svc = []
    df_global = scan_global_resources()

    print("\n--- [2/3] Varrendo Regiões ---")
    for region in regions:
        v, s = scan_regional_resources(region)
        all_vpc.extend(v)
        all_svc.extend(s)

    print("\n--- [3/3] Gerando Excel ---")
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        if not df_global.empty: df_global.to_excel(writer, sheet_name='Global', index=False)
        
        if all_vpc:
            df = pd.DataFrame(all_vpc)
            # Reordenando colunas para ficar bonito
            cols = ['Region', 'VPC Name', 'Subnet Name', 'Resource Type', 'Resource ID', 'Private IP', 'Public IP', 'Details']
            # Garante que só usa colunas que existem
            final_cols = [c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]
            df[final_cols].to_excel(writer, sheet_name='VPC Network', index=False)
            
        if all_svc: pd.DataFrame(all_svc).to_excel(writer, sheet_name='Services', index=False)

    print(f"SUCESSO! Arquivo salvo: {OUTPUT_FILE}")