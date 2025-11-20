# Comandos Úteis de DevOps

Este arquivo contém uma lista de comandos `kubectl` e `linux` comumente usados para gerenciar, inspecionar e depurar aplicações e servidores.

## 1. Kubernetes (kubectl)

Este arquivo contém uma lista de comandos `kubectl` comumente usados para gerenciar, inspecionar e depurar aplicações em um cluster Kubernetes.

---

### 1.1. Gerenciamento de Contexto e Cluster

Esses comandos ajudam a visualizar e interagir com diferentes clusters e contextos configurados no seu `kubeconfig`.

- **Ver informações do cluster:**

  ```bash
  # Exibe os endereços do master e dos serviços do cluster.
  kubectl cluster-info
  ```

- **Listar todos os contextos:**

  ```bash
  # Mostra todos os contextos configurados.
  kubectl config get-contexts
  ```

- **Ver o contexto atual:**

  ```bash
  # Exibe o contexto que está sendo usado no momento.
  kubectl config current-context
  ```

- **Mudar de contexto:**
  ```bash
  # Altera o contexto atual para o nome de contexto especificado.
  kubectl config use-context <nome-do-contexto>
  ```

---

### 1.2. Inspeção de Recursos

Comandos para listar, descrever e visualizar o estado dos recursos.

- **Listar recursos:**

  ```bash
  # Lista todos os pods no namespace especificado.
  kubectl get pods -n <nome-do-namespace>


  # Lista todos os pods em todos os namespaces.
  kubectl get pods --all-namespaces
  # ou, de forma abreviada:
  kubectl get pods -A

  # Lista pods com mais detalhes (IP, Node, etc.).
  kubectl get pods -o wide

  # Lista todos os deployments, services e ingresses no namespace.
  kubectl get deployment,service,ingress -n <nome-do-namespace>

  # Lista todos os deployments, services e ingresses em todos os namespaces.
  kubectl get deployment,service,ingress -A

  # Lista os pods com erro
  kubectl get pods -A | grep -Ei "CrashLoop|Evicted|OOMKilled|BackOff|Error|ContainerCreating"

  # Lista os pods que não estão 'Running'
  kubectl get pods -A --field-selector=status.phase!=Running -o wide
  ```

- **Descrever um recurso:**

  ```bash
  # Mostra informações detalhadas sobre um pod, incluindo eventos. Essencial para depuração.
  kubectl describe pod <nome-do-pod> -n <nome-do-namespace>

  # Mostra informações detalhadas sobre um deployment.
  kubectl describe deployment <nome-do-deployment> -n <nome-do-namespace>

  # Mostra informações detalhadas sobre um serviço
  kubectl describe service <nome-do-service> -n <nome-do-namespace>

  # Mostra informações detalhadas sobre um virtual service (Istio)
  kubectl describe virtualservice <nome-do-virtual-service> -n <nome-do-namespace>

  # Mostra informações detalhadas sobre um ingress
  kubectl describe ingress <nome-do-ingress> -n <nome-do-namespace>

  # Mostra detalhes de um nó, incluindo pods agendados e consumo de recursos.
  kubectl describe node <nome-do-node>
  ```

- **Ver logs de um pod:**

  ```bash
  # Exibe os logs de um pod.
  kubectl logs <nome-do-pod> -n <namespace>

  # Segue os logs em tempo real (como 'tail -f').
  kubectl logs -f <nome-do-pod> -n <namespace>

  # Exibe os logs de um contêiner específico dentro de um pod com múltiplos contêineres.
  kubectl logs <nome-do-pod> -n <namespace> -c <nome-do-container>

  # Exibe os logs de um pod em todos os containers, filtrando por erros ou exceções
  kubectl logs <nome-do-pod> -n <namespace> --all-containers |grep -Ei "evicted|shutdown|error|exception"

  # Exibe todos os eventos de um namespace
  kubectl get events --sort-by=.metadata.creationTimestamp -n <namespaces>
  ```

- **Verificar o uso de recursos (requer o Metrics Server):**

  ```bash
  # Mostra o uso de CPU/Memória dos nós.
  kubectl top node

  # Mostra o uso de CPU/Memória dos pods em um namespace.
  kubectl top pod -n <namespace>

  # Mostra quantidade de pods:
  kubectl get hpa <nome-hpa> -n <namespaces>
  ```

- **Realiza o scale up/down de recursos :**

  ```bash
  # Usando o scale.
  kubectl scale deployment <nome-deployment> -n <namespaces> --replicas=2

  # Usando o hpa
  kubectl patch hpa <nome-hpa> -n <namespaces> -p '{"spec":{"minReplicas":20, "maxReplicas":160}}'
  # ou editando manualmento o hpa
  kubectl edit hpa <nome-hpa> -n <namespaces>

  # Supender um pod de cronjob
  kubectl patch cronjob <cronjob-name> -p '{"spec":{"suspend":true}}'

  ```

- **Realiza o restart de recurso :**

  ```bash
  # Reiniciando o deploy.
  kubectl rollout restart deploy -n <namespaces>

  ```

---

### 1.3. Criação, Deleção e Modificação de Recursos

- **Aplicar uma configuração de um arquivo YAML:**

  ```bash
  # Cria ou atualiza recursos com base em um arquivo ou diretório.
  kubectl apply -f ./meu-deployment.yaml
  ```

- **Deletar recursos:**

  ```bash
  # Deleta um pod específico.
  kubectl delete pod <nome-do-pod> -n <namespaces> --force --grace-period=0

  #Deleta um deployment especifico
  kubectl delete deployment <nome-do-deployment> -n <namespaces> --force --grace-period=0

  # Deleta todos os recursos definidos em um arquivo YAML.
  kubectl delete -f ./meu-deployment.yaml
  ```

- **Editar um recurso ao vivo:**
  ```bash
  # Abre o editor padrão (geralmente 'vi') para editar a especificação de um recurso no cluster.
  kubectl edit deployment <nome-do-deployment>
  ```

---

### 1.4. Debug e Execução

- **Executar um comando dentro de um contêiner:**

  ```bash
  # Abre um shell interativo (/bin/sh) dentro de um pod.
  kubectl exec -it <nome-do-pod> -- /bin/sh
  ```

- **Copiar arquivos entre o host e um pod:**

  ```bash
  # Copia um arquivo do seu computador para dentro de um pod.
  kubectl cp /caminho/local/arquivo.txt <namespace>/<nome-do-pod>:/caminho/no/pod/

  # Copia um arquivo de um pod para o seu computador.
  kubectl cp <namespace>/<nome-do-pod>:/caminho/no/pod/arquivo.txt /caminho/local/
  ```

### 1.5. Causas problemas

- **Erro de config CNI**

  ```bash
  # Caso apresente erro de CNI, realizar os throubleshooting e se o problema persistir:
  kubectl delete daemonset aws-node -n kube-system
  kubectl apply -f https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/master/config/aws-k8s-cni.yaml
  ```

- **Troubleshooting Karpenter**

  ```bash
  # Verificar
  kubectl get ec2ndoeclass
  kubectl get nodepool

  # Mostrar detalhes
  kubectl describe ec2ndoeclass <nome-do-ec2nodeclass>
  kubectl describe nodepool <nome-nodepool>

  # Editar detalhase
  kubectl edit ec2ndoeclass <nome-do-ec2ndoeclass>
  kubectl edit nodepool <nome-nodepool>
  ```

### 1.6. Baixar o heml no cloudshell

- **Site Oficial**: https://helm.sh/docs/intro/install/

- **Comandos para download**:

  ```bash
  curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
  chmod 700 get_helm.sh
  ./get_helm.sh
  ```

- **Verificaro histórico**:
  ```bash
  helm history <release-name> -n <namespace>
  ```

## 2. Linux

### 2.1. Inspeção de recursos

- **Validação de consumo no filesystem**

  ```bash
  # Mostra o espaço total usado, disponível e o ponto de montagem de cada filesystem (formato MB ou GB)
  df -h

  # Ordena os resultados do menor para o maior
  du -sh |  sort -h

  # Ordena os resultados do maior para o menor
  du -sh | sort -rh

  # Ordena os resultados mostrando até 3 níveis de subdiretórios
  du -h --max-depth=3 / | sort -rh

  # Ordena até em 5 maiores ofensores
  du -h --max-depth=3 / | sort -rh | head -n 5
  ```

- **Análise de Logs**

```bash
  # filtra até 500 linhas e busca por item especifico
  tail -n 500 /var/log/log | grep -i "<chave>"
```

## 3. Azure

### 3.1. Cluster

```bash
az account set --subscription <id-subscription>
az aks get-credentials --resource-group <nome-do-rg> --name <nome-do-aks>
```

## 4. Windows

### 4.1. Configuração de pah

```bash
$env:PATH += ";C:caminho/arquivo"
```
