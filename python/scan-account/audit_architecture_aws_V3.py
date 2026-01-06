import boto3
import pandas as pd
from botocore.exceptions import ClientError

# ---| CONFIGURACAO |---
OUTPUTFILE = "Relatorio_AWS_Arquitetura_v2.xlsx"

# ---| FUNCOES AUXILIARES |---
def get_active_regions():
  """Descobre todas as regiões ativas na conta AWS."""

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

def add_data(category, svc, name, location, details):
  return {'Region': location, 'Category': category, 'Service': svc, 'Name/ID': name, 'Details': details}


# ---| FUNCOES DE BUSCA |---
def get_vpc_architecture(region_name, vpc_id):
  ec2_resource = boto3.resource('ec2', region_name=region_name)
  vpc = ec2_resource.Vpc(vpc_id)

  print(f"   -> Analisando arquitetura da VPC {vpc_id} na região {region_name}...")
  
  # Dicionário para mapear ID da Subnet -> Status (Public/Private)
  subnet_public_status = {}
  main_route_table_is_public = False
  
  # 1. Analisa todas as Route Tables da VPC
  for rtb in vpc.route_tables.all():
      is_public_rtb = False
      
      # Verifica se há rota para Internet Gateway (0.0.0.0/0 -> igw-*)
      for route in rtb.routes:
          if (route.destination_cidr_block == '0.0.0.0/0' and 
              route.gateway_id and 
              route.gateway_id.startswith('igw-')):
              is_public_rtb = True
              break
      
      # Analisa as associações desta Route Table
      for association in rtb.associations:
          if association.main:
              # Se for a tabela principal, definimos o status padrão para subnets sem associação explícita
              main_route_table_is_public = is_public_rtb
          elif association.subnet_id:
              # Associação explícita: Mapeia a subnet específica
              subnet_public_status[association.subnet_id] = is_public_rtb

  # 2. Compila os dados finais iterando sobre as Subnets reais
  vpc_data = []
  
  # Recupera nome da VPC
  vpc_name = ""
  if vpc.tags:
      vpc_name = next((tag['Value'] for tag in vpc.tags if tag['Key'] == 'Name'), "")

  for subnet in vpc.subnets.all():
      # Determina o nome da subnet
      subnet_name = ""
      if subnet.tags:
          subnet_name = next((tag['Value'] for tag in subnet.tags if tag['Key'] == 'Name'), "")

      # Verifica se está no mapa explícito, caso contrário usa a Main RT
      is_public = subnet_public_status.get(subnet.id, main_route_table_is_public)
      subnet_type = "Public" if is_public else "Private"

      vpc_data.append({
          'VPC ID': vpc.id,
          'VPC Name': vpc_name,
          'VPC CIDR': vpc.cidr_block,
          'Subnet ID': subnet.id,
          'Subnet Name': subnet_name,
          'Subnet CIDR': subnet.cidr_block,
          'Subnet AZ': subnet.availability_zone,
          'Subnet Type': subnet_type
      })

  return vpc_data

def get_all_resources_compute(region_name, vpc_id, all_lambdas):
  ec2_resource = boto3.resource('ec2', region_name=region_name)
  vpc = ec2_resource.Vpc(vpc_id)

  print(f"   -> Listando recursos de computação na VPC {vpc_id} na região {region_name}...")
  
  ec2_data = []
  lbm_data = []

  # Lista todas as instâncias EC2 na VPC
  for instance in vpc.instances.all():
    instance_name = ""
    if instance.tags:
      instance_name = next((tag['Value'] for tag in instance.tags if tag['Key'] == 'Name'), "")
    
    ebs_volumes = [bdm['Ebs']['VolumeId'] for bdm in instance.block_device_mappings if 'Ebs' in bdm]

    ec2_data.append({
      'Instance ID': instance.id,
      'Instance Name': instance_name,
      'Instance Type': instance.instance_type,
      'Private IP': instance.private_ip_address or "-",
      'Public IP': instance.public_ip_address or "-",
      'State': instance.state['Name'],
      'Subnet ID': instance.subnet_id,
      'VPC ID': instance.vpc_id,
      'EBS Volumes': ", ".join(ebs_volumes) if ebs_volumes else "-"
    })
  
  # Lista todas as funções Lambda na VPC
  for function in all_lambdas:
    if 'VpcConfig' in function and function['VpcConfig'].get('VpcId') == vpc_id:
      lbm_data.append({
        'Lambda Function Name': function['FunctionName'],
        'Lambda Function ARN': function['FunctionArn'],
        'VPC ID': vpc_id,
        'Subnet IDs': ", ".join(function['VpcConfig'].get('SubnetIds', [])) if function['VpcConfig'].get('SubnetIds') else "-",
        'Security Group IDs': ", ".join(function['VpcConfig'].get('SecurityGroupIds', [])) if function['VpcConfig'].get('SecurityGroupIds') else "-"
      })
  
  # Lista todos os Load Balancers na VPC
  lb_data = []
  # def add(type, svc, name, loc, det):
  #   lb_data.append({
  #     'Region': loc,
  #     'Category': type,
  #     'Service': svc,
  #     'Name/ID': name,
  #     'Details': det
  #   })
  
  lb_client = boto3.client('elbv2', region_name=region_name)
  try:
    print(f"    -> Varrendo Load Balancers Modernos (ALB/NLB)...")
  
    for lb in lb_client.describe_load_balancers()['LoadBalancers']:
      target_groups = list(lb_client.describe_target_groups(LoadBalancerArn=lb['LoadBalancerArn'])
      ['TargetGroups'])

      if target_groups:
        target_group_names = ", ".join([tg['TargetGroupName'] for tg in target_groups])
      else:
        target_group_names = "-"

      if lb['VpcId'] == vpc_id:
        # add.append('Compute', 'Load Balancer', lb['LoadBalancerName'], region_name,
        #     f"Type: {lb['Type']}, Scheme: {lb['Scheme']}, DNS: {lb['DNSName']}")
        new_data = add_data(
          'Compute',
          'Load Balancer',
          lb['LoadBalancerName'],
          region_name,
          f"Type: {lb['Type']}, Scheme: {lb['Scheme']}, DNS: {lb['DNSName']}, Target Groups: {target_group_names}"
        )
        lb_data.append(new_data)
  except ClientError as e:
    print(f"      [!] Erro ao listar Load Balancers Modernos: {e}")

  print(f"    -> Varrendo Load Balancers Clássicos...")
  try:
    for elb in vpc.load_balancers.all():
      attached_instances = list(elb.instances.all())

      if attached_instances:
          instance_ids = ", ".join([inst.id for inst in attached_instances])
      else:
          instance_ids = "-"

      new_data = add_data(
        'Compute',
        'Classic Load Balancer',
        elb.name,
        region_name,
        f"Scheme: {elb.scheme}, DNS: {elb.dns_name}, Instances: {instance_ids}"
      )
      
      lb_data.append(new_data)
  except ClientError as e:
    print(f"      [!] Erro ao listar Load Balancers Clássicos: {e}")
  
  return ec2_data, lbm_data, lb_data

def get_all_resources_database(vpc_id, all_rds_instances):
  """Filtra instancias RDS em memoria que pertencem a VPC especifica."""

  rds_data = []

  print(f"   -> Listando recursos de banco de dados na VPC {vpc_id}...")
  try:
    for db_instance in all_rds_instances:
      if 'DBSubnetGroup' in db_instance and db_instance['DBSubnetGroup']['VpcId'] == vpc_id:
        rds_data.append({
          'DB Instance Identifier': db_instance['DBInstanceIdentifier'],
          'DB Instance ARN': db_instance['DBInstanceArn'],
          'Engine': db_instance['Engine'],
          'DB Instance Class': db_instance['DBInstanceClass'],
          'Multi-AZ': db_instance['MultiAZ'],
          'VPC ID': vpc_id
        })
  except ClientError as e:
    print(f"      [!] Erro ao listar instancias RDS: {e}")


  return rds_data

def get_all_resources_dynamodb(region):
  """Varre DynamoDB uma vez por regiao"""
  
  dynamodb = boto3.resource('dynamodb', region_name=region)
  ddb_data = []

  print(f"    -> Varrendo Tabelas DynamoDB...")
  try:
    for table in dynamodb.tables.all():
      ddb_data.append({
        'Table Name': table.name,
        'Table ARN': table.table_arn,
        'Region': region,
        'Item Count': table.item_count,
        'Table Size (Bytes)': table.table_size_bytes
      })
  except ClientError as e:
    print(f"      [!] Erro ao listar tabelas DynamoDB: {e}")

  return ddb_data

# ---| FUNCOES PRINCIPAIS |---
def analyze_regional_resources(region):
  print(f"    -> Varrendo os Recursos Regional...")

  ec2_resource = boto3.resource('ec2', region_name=region)
  lambda_client = boto3.client('lambda', region_name=region)
  rds_client = boto3.client('rds', region_name=region)


  # Busca Lambdas UMA vez por região
  region_lambdas = []
  try:
    paginator = lambda_client.get_paginator('list_functions')
    for page in paginator.paginate():
        region_lambdas.extend(page['Functions'])
  except ClientError: 
    print(f"      [!] Erro ao listar Lambdas na região {region}. Pulando...")
    pass

  # Busca RDS UMA vez por região
  region_rds = []
  try:
    region_rds = rds_client.describe_db_instances().get('DBInstances', [])
  except ClientError:
    print(f"      [!] Erro ao listar RDS na região {region}. Pulando...")
    pass

  vpc_data = []
  comp_data = []
  lmb_data = []
  lb_data = []
  db_data = []


  # 3. Iterar sobre VPCs
  try:
    for vpc in ec2_resource.vpcs.all():
      
      # Arquitetura da VPC
      vpc_arch = get_vpc_architecture(region, vpc.id)
      vpc_data.extend(vpc_arch)

      # Recursos de computação na VPC (EC2, Lambda, ELB)
      c_data, l_data, e_data = get_all_resources_compute(region, vpc.id, region_lambdas)
      comp_data.extend(c_data)
      lmb_data.extend(l_data)
      lb_data.extend(e_data)

      # Recursos de banco de dados na VPC (RDS)
      db_data.extend(get_all_resources_database(vpc.id, region_rds))

  except ClientError as e:
    print(f"      [!] Erro ao acessar VPCs: {e}")

  # Recursos DynamoDB (regionais, não VPC)
  db_data.extend(get_all_resources_dynamodb(region))

  return vpc_data, comp_data, lmb_data, lb_data, db_data

def analyze_global_resources():
  
  data = []
  
  # def add(cat, svc, name, loc, det):
  #   data.append({'Region': loc, 'Category': cat, 'Service': svc, 'Name/ID': name, 'Details': det})

  # IAM
  try:
    print(f"    -> Varrendo IAM Users...")
    iam = boto3.client('iam')
    for user in iam.list_users()['Users']:
      new_data = add_data('Security', 'IAM User', user['UserName'], 'Global', f"ID: {user['UserId']}")
      data.append(new_data)
  except Exception as e: print(f"   [Erro IAM]: {e}")

  # S3
  try:
    print(f"    -> Varrendo S3 Buckets...")
    s3 = boto3.client('s3')
    for bucket in s3.list_buckets().get('Buckets', []):
      new_data = add_data('Storage', 'S3 Bucket', bucket['Name'], 'Global', f"Creation Date: {bucket['CreationDate']}")
      data.append(new_data)
  except Exception as e: print(f"   [Erro S3]: {e}")

  # CloudFront
  try:
    print(f"    -> Varrendo CloudFront...")
    cf = boto3.client('cloudfront')
    dists = cf.list_distributions().get('DistributionList', {})
    for item in dists.get('Items', []):
      new_data = add_data('CDN', 'CloudFront Distribution', item['Id'], 'Global', f"Domain Name: {item['DomainName']}")
      data.append(new_data)
  except Exception as e: print(f"   [Erro CloudFront]: {e}")

  # Route53
  try:
    print(f"    -> Varrendo Route53 Hosted Zones...")
    r53 = boto3.client('route53')
    for zone in r53.list_hosted_zones()['HostedZones']:
      new_data = add_data('DNS', 'Hosted Zone', zone['Name'], 'Global', f"Private Zone: {zone['Config']['PrivateZone']}")
      data.append(new_data)
  except Exception as e: print(f"   [Erro Route53]: {e}")

  return pd.DataFrame(data)

# ---| MAIN |---
if __name__ == "__main__":
  print("=== Iniciando Auditoria de Arquitetura AWS v2 ===\n")
  print("--- [0/3] Descobrindo regiões ativas... ---")
  all_regions = get_active_regions()

  all_vpc_data = []
  all_comp_data = []
  all_lmb_data = []
  all_elb_data = []
  all_db_data = []

  print("\n--- [1/3] Varrendo Regiões ---")
  for region in all_regions:
    result_regional = analyze_regional_resources(region)
    if result_regional:
      vpc_data, comp_data, lmb_data, lb_data, db_data = result_regional
      all_vpc_data.extend(vpc_data)
      all_comp_data.extend(comp_data)
      all_lmb_data.extend(lmb_data)
      all_elb_data.extend(lb_data)
      all_db_data.extend(db_data)
    
  df_vpc = pd.DataFrame(all_vpc_data)
  df_comp = pd.DataFrame(all_comp_data)
  df_lmb = pd.DataFrame(all_lmb_data)
  df_elb = pd.DataFrame(all_elb_data)
  df_db = pd.DataFrame(all_db_data)
    
  print("\n--- [2/3] Verificando recursos Globais ---")
  df_global = analyze_global_resources()

  # Salvando para Excel
  print("\n--- [3/3] Gerando Excel ---")
  with pd.ExcelWriter(OUTPUTFILE) as writer:
    df_vpc.to_excel(writer, sheet_name='VPCs', index=False)
    df_comp.to_excel(writer, sheet_name='Compute Resources', index=False)
    df_lmb.to_excel(writer, sheet_name='Lambdas', index=False)
    df_elb.to_excel(writer, sheet_name='Load Balancers', index=False)
    df_db.to_excel(writer, sheet_name='Database Resources', index=False)
    df_global.to_excel(writer, sheet_name='Global Resources', index=False)

  print(f"\n=== Auditoria concluída! Relatório salvo em '{OUTPUTFILE}' ===")