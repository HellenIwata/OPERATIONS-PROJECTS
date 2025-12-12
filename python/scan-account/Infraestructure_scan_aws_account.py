import boto3
import pandas as pd
from botocore.exceptions import ClientError

# --- Configurações ---
OUTPUT_FILE = "aws_account_scan_report.xlsx"
REGION = "us-east-1"  # Defina a região principal para a varredura

ec2 = boto3.resource('ec2')
client = boto3.client('ec2', region_name=REGION)

def get_tag_value(tags, key):
    """
    Extrai o valor de uma tag de forma segura.

    Args:
        tags (list): A lista de tags de um recurso.
        key (str): A chave da tag a ser procurada.
    Returns:
        str or None: O valor da tag ou None se não for encontrada.
    """
    for tag in tags:
        if tag['Key'] == key:
            return tag['Value']
    return None

def scan_vpc_hierarchy():
  """Varre a hierarquia VPC > Subnet > ENI para descobrir recursos de computação e rede.

  Args:

  Returns:
      pd.DataFrame: Um DataFrame com os recursos encontrados.
  """

  print(f" ---> Iniciando a varredura da VPC na região {REGION} ---\n")

  data_rows = []

  # Itera sobre todas as VPCs
  for vpc in ec2.vpcs.all():
    vpc_name = get_tag_value(vpc.tags or [], 'Name') or vpc.id
    print(f"    -> Processing VPC: {vpc_name} - ({vpc.id})")

    for subnet in vpc.subnets.all():
      subnet_name = get_tag_value(subnet.tags or [], 'Name') or subnet.id

      # Busca ENIs na Subnet para encontrar recursos
      network_interfaces = client.describe_network_interfaces(
        Filters=[
          {
            'Name': 'subnet-id',
            'Values': [subnet.id]
          }
        ]
      )

      # Se a sub-rede estiver vazia
      if not network_interfaces['NetworkInterfaces']:
        data_rows.append({
          'VPC_ID': vpc.id, 'VPC_NAME': vpc_name,
          'SUBNET_ID': subnet.id, 'SUBNET_NAME': subnet_name,
          'RESOURCE TYPE':'Empty Subnet', 'RESOURCE ID':'-', 'DETAILS':'N/A'
        })

      # Se a sub-rede tiver ENIs
      for eni in network_interfaces['NetworkInterfaces']:
        description = eni.get('Description', '').lower()
        resource_id = eni['NetworkInterfaceId']
        resource_type = "Unknown Interface"
        details = f"ENI Status: {eni['Status']}; IPs: {[ip['PrivateIpAddress'] for ip in eni['PrivateIpAddresses']]}; Desc: {description}"

        if eni.get('Attachment'):
            instance_id = eni['Attachment'].get('InstanceId')
            if instance_id:
                resource_type = "EC2 Instance"
                resource_id = instance_id
                details += f", Anexado à Instância: {instance_id}"

        # Identificação baseada na descrição para outros serviços
        if 'rds' in description: resource_type = "RDS Instance"
        elif 'lambda' in description: resource_type = "Lambda Function"
        elif 'elb' in description or 'load balancer' in description: resource_type = "Load Balancer"
        elif 'ecs' in description: resource_type = "Elastic Container Service"
        elif 'nat gateway' in description: resource_type = "NAT Gateway"
        elif 'eks' in description: resource_type = "Elastic Kubernetes Service"
        elif 'route53' in description: resource_type = "Route 53 Resolver"
        elif 'efs' in description: resource_type = "Elastic File System"
        elif resource_type == "Unknown Interface": # Se nada foi identificado
            resource_type = description or "Recurso Desconhecido"

        data_rows.append({
          'VPC_ID': vpc.id, 'VPC_NAME': vpc_name,
          'SUBNET_ID': subnet.id, 'SUBNET_NAME': subnet_name,
          'RESOURCE TYPE':resource_type, 'RESOURCE ID':resource_id, 'DETAILS':details
        })
  
  print (f"\n ---> Varredura da VPC concluida.\n")
  return pd.DataFrame(data_rows)

def scan_others_services():
  """Varre outros serviços da AWS que não estão diretamente ligados a VPCs.

  Args:

  Returns:
      pd.DataFrame: Um DataFrame com os serviços encontrados.
  """

  print(f" ---> Iniciando a varredura de outros serviços na região {REGION} (e globais) ---\n")

  data = []

  def add(category, svc, name, region, subnet, details):
    data.append({'Category': category, 'Service': svc, 'Name/ID': name, 'VPC/Context': region, 'Subnet': subnet, 'Details': details})

  def scan_service(service_name, client_creator, list_function, items_key, details_mapper, region=REGION):
      """Função genérica para varrer um serviço e adicionar os dados."""
      print(f"    -> Varrendo {service_name}...")
      try:
          client = client_creator()
          response = list_function(client)
          for item in response.get(items_key, []):
              category, svc, name, item_region, subnet, details = details_mapper(item)
              add(category, svc, name, item_region, subnet, details)
      except ClientError as e:
          print(f"    ERRO ao varrer {service_name}: {e}")
      except Exception as e:
          print(f"    ERRO inesperado ao varrer {service_name}: {e}")

  # Mapeamento dos serviços a serem varridos
  services_to_scan = [
      {'name': 'S3', 
        'client': lambda: boto3.client('s3'), 
        'list_func': lambda c: c.list_buckets(), 
        'items_key': 'Buckets',
        'mapper': lambda i: (
          'Storage', 
          'S3', 
          i['Name'], 
          'Global', 
          '-', 
          f"Criação: {i['CreationDate']}"
        )
      },

      {'name': 'IAM Users', 
        'client': lambda: boto3.client('iam'), 
        'list_func': lambda c: c.list_users(), 'items_key': 'Users',
        'mapper': lambda i: (
          'IAM', 
          'User', 
          i['UserName'], 
          'Global', 
          '-', 
          f"ID: {i['UserId']}, Criação: {i['CreateDate']}"
        )
      },

      {'name': 'CloudFront', 
        'client': lambda: boto3.client('cloudfront'), 
        'list_func': lambda c: c.list_distributions(), 
        'items_key': 'DistributionList',
        'mapper': lambda i: (
          'CDN', 
          'CloudFront', 
          i['Id'], 'Global', '-', 
          f"Domínio: {i['DomainName']}, Status: {i['Status']}"), 
          'items_key_nested': 'Items'
      },
      
      {'name': 'Auto Scaling Groups', 
        'client': lambda: boto3.client('autoscaling', region_name=REGION), 
        'list_func': lambda c: c.describe_auto_scaling_groups(), 
        'items_key': 'AutoScalingGroups',
        'mapper': lambda i: (
          'Compute', 
          'Auto Scaling Group', 
          i['AutoScalingGroupName'], 
          REGION, 
          '-', 
          f"Capacidade: {i['DesiredCapacity']}, Min: {i['MinSize']}, Max: {i['MaxSize']}"
        )
      },
      
      {'name': 'SQS Queues', 
        'client': lambda: boto3.client('sqs', region_name=REGION), 
        'list_func': lambda c: c.list_queues(), 
        'items_key': 'QueueUrls',
        'mapper': lambda i: (
          'Messaging', 
          'SQS Queue', 
          i, 
          REGION, 
          '-', 
          'N/A'
        )
      },
      
      {'name': 'SNS Topics', 
      'client': lambda: boto3.client('sns', region_name=REGION), 
        'list_func': lambda c: c.list_topics(), 
        'items_key': 'Topics',
        'mapper': lambda i: (
          'Messaging', 
          'SNS Topic',
          i['TopicArn'], 
          REGION, 
          '-', 
          'N/A'
        )
      },

      {'name': 'Global Accelerator', 
        'client': lambda: boto3.client('globalaccelerator'), 
        'list_func': lambda c: c.list_accelerators(), 
        'items_key': 'Accelerators',
        'mapper': lambda i: (
          'Networking', 
          'Global Accelerator', 
          i['Name'], 
          'Global', 
          '-', 
          f"DNS: {i['DnsName']}, Status: {i['Status']}"
        )
      },
      
      {'name': 'Lambda Functions', 
        'client': lambda: boto3.client('lambda', region_name=REGION), 
        'list_func': lambda c: c.list_functions(), 
        'items_key': 'Functions',
        'mapper': lambda i: (
          'Compute', 
          'Lambda Function', 
          i['FunctionName'], 
          REGION, 
          '-', 
          f"Runtime: {i['Runtime']}, Modificado: {i['LastModified']}"
        )
      },
      
      {'name': 'DynamoDB Tables', 
        'client': lambda: boto3.client('dynamodb', region_name=REGION), 
        'list_func': lambda c: c.list_tables(), 
        'items_key': 'TableNames',
        'mapper': lambda i: (
          'Database', 
          'DynamoDB Table', 
          i, 
          REGION, 
          '-', 
          'N/A'
        )
      },
      
      {'name': 'EKS Clusters', 
        'client': lambda: boto3.client('eks', region_name=REGION), 
        'list_func': lambda c: c.list_clusters(), 
        'items_key': 'clusters',
        'mapper': lambda i: (
          'Compute', 
          'EKS Cluster', 
          i, 
          REGION, 
          '-', 
          'N/A'
        )
      },
      
      {'name': 'Route 53 Hosted Zones', 
        'client': lambda: boto3.client('route53'), 
        'list_func': lambda c: c.list_hosted_zones(), 
        'items_key': 'HostedZones',
        'mapper': lambda i: (
          'DNS', 
          'Route 53 Hosted Zone', 
          i['Name'], 
          'Global', 
          '-', 
          f"ID: {i['Id']}, Privado: {i['Config']['PrivateZone']}"
        )
      },
      
      {'name': 'WAF Web ACLs', 
        'client': lambda: boto3.client('wafv2', region_name=REGION), 
        'list_func': lambda c: c.list_web_acls(Scope='REGIONAL'), 
        'items_key': 'WebACLs',
        'mapper': lambda i: (
          'Firewall', 
          'WAF Web ACL', 
          i['Name'], 
          REGION, 
          '-', 
          f"ID: {i['Id']}"
        )
      },
      
      {'name': 'ECR Repositories', 
        'client': lambda: boto3.client('ecr', region_name=REGION), 
        'list_func': lambda c: c.describe_repositories(), 
        'items_key': 'repositories',
        'mapper': lambda i: (
          'Container Registry', 
          'ECR Repository', 
          i['repositoryName'], 
          REGION, 
          '-', 
          f"ARN: {i['repositoryArn']}"
        )
      },
      
      {'name': 'ElastiCache Clusters', 
        'client': lambda: boto3.client('elasticache', region_name=REGION), 
        'list_func': lambda c: c.describe_cache_clusters(), 
        'items_key': 'CacheClusters',
        'mapper': lambda i: (
          'Database', 
          'ElastiCache Cluster', 
          i['CacheClusterId'], 
          REGION, 
          '-', 
          f"Engine: {i['Engine']}, Status: {i['CacheClusterStatus']}"
        )
      },
      
      {'name': 'Amazon MQ Brokers', 
        'client': lambda: boto3.client('mq', region_name=REGION), 
        'list_func': lambda c: c.list_brokers(), 
        'items_key': 'BrokerSummaries',
        'mapper': lambda i: (
          'Messaging', 
          'Amazon MQ Broker', 
          i['BrokerName'], 
          REGION, 
          '-', 
          f"ID: {i['BrokerId']}, Status: {i['BrokerState']}"
        )
      }
  ]

  for service in services_to_scan:
      # Lógica especial para respostas aninhadas como a do CloudFront
      if 'items_key_nested' in service:
          original_list_func = service['list_func']
          service['list_func'] = lambda c: original_list_func(c).get(service['items_key'], {})
          service['items_key'] = service['items_key_nested']

      scan_service(
          service['name'],
          service['client'],
          service['list_func'],
          service['items_key'],
          service['mapper']
      )

  return pd.DataFrame(data)

if __name__ == "__main__":
  try:
    vpc_df = scan_vpc_hierarchy()
    others_df = scan_others_services()

    # Salva os resultados no Excel
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
      vpc_df.to_excel(writer, sheet_name='VPC_Scan', index=False)
      others_df.to_excel(writer, sheet_name='Other_Services_Scan', index=False)
      print(f"\nVarredura concluida. Resultado salvo em: {OUTPUT_FILE}")
  except Exception as e:
    print(f"Erro durante a varredura: {e}")
