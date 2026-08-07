### 1. AWS Services Used

| AWS Service | Purpose | Environment | Mandatory/Optional |
| :--- | :--- | :--- | :--- |
| RDS | PostgreSQL (pgvector) database for vectorization and sensitivity store | All | Mandatory |
| Cognito | Authentication and user management | All | Mandatory (unless using manual mock) |
| Bedrock | Primary generative AI tasks and sensitivity adjudication | All | Mandatory |
| S3 | Reference document sync and user uploads | All | Mandatory |
| Secrets Manager | Dynamic database credential fetching | All | Mandatory |
| Comprehend | PII enrichment and NLP detection | All | Optional (fallback exists) |
| SES | Manager email notifications | All | Optional |
| SNS | Manager alert broadcasting / fan-out notifications | All | Optional |
| IAM | SSO developer credentials and SDK authentication | All | Mandatory |
| ALB | Reverse proxy (mentioned in `nginx.conf`) | All | Optional |

### 2. Compute Resources

Not detected. (Note: CI/CD configurations in `.github/workflows/build-and-push.yml` indicate the backend compute is hosted externally on Azure App Service using Azure Container Registry, rather than AWS EC2/ECS/Lambda).

### 3. Storage

**S3**
* **Bucket Name**: `grc-company-reference-docs`, `document-and-info-handler`
* **Estimated Purpose**: Company reference documents sync, Standard user uploads, and RAG document storage
* **Versioning**: Needs AWS Console verification
* **Lifecycle**: Needs AWS Console verification
* **Encryption**: Needs AWS Console verification

**EBS**
* Not detected

**RDS**
* **Engine**: PostgreSQL (pgvector)
* **Instance Class**: Needs AWS Console verification
* **Storage**: Needs AWS Console verification

### 4. AI Services

**Bedrock**
* **Models**: `anthropic.claude-3-7-sonnet-20250219-v1:0` (Used for primary tasks and adjudication)
* **Embedding models**: Needs AWS Console verification
* **Guardrails**: Not detected
* **Knowledge Bases**: Not detected
* **Agents**: Not detected

**Comprehend**
* Used for PII enrichment and NLP detection

### 5. Networking

* **VPC**: Needs AWS Console verification
* **Subnets**: Needs AWS Console verification
* **Security Groups**: Needs AWS Console verification
* **Load Balancers**: ALB (referenced in frontend config)
* **Elastic IPs**: Not detected
* **NAT Gateways**: Not detected
* **Route53**: Needs AWS Console verification
* **PrivateLink**: Not detected
* **VPC Endpoints**: Not detected

### 6. Messaging

* **SNS Topics**: Used for manager alert broadcasting
* **SQS Queues**: Not detected
* **SES identities**: Verified sender email configured

### 7. Monitoring

* **CloudWatch**: Needs AWS Console verification
* **CloudTrail**: Needs AWS Console verification
* **AWS Config**: Not detected
* **GuardDuty**: Not detected
* **X-Ray**: Not detected
* **OpenTelemetry**: Not detected

### 8. Security

* **IAM Roles**: Needs AWS Console verification
* **IAM Policies**: Needs AWS Console verification
* **Secrets Manager secrets**: `rds!db-2970e75f-e258-4539-acc2-bc646e54bd13`
* **KMS Keys**: Needs AWS Console verification
* **Certificates**: Needs AWS Console verification

### 9. External Services

* **Azure App Service**
* **Azure Container Registry**
* **Cohere** 
* **pgvector**
* **spaCy**
* **GitHub**

### 10. Environment Variables

* `AWS_REGION`
* `AWS_ACCESS_KEY_ID`
* `AWS_SECRET_ACCESS_KEY`
* `AWS_BEARER_TOKEN_BEDROCK`
* `DB_SECRET_ID`
* `COGNITO_USER_POOL_ID`
* `COGNITO_CLIENT_ID`
* `COGNITO_ADDITIONAL_CLIENT_IDS`
* `BEDROCK_MODEL_ID`
* `ADJUDICATION_MODEL_ID`
* `REFERENCE_S3_BUCKET`
* `REFERENCE_S3_PREFIX`
* `S3_BUCKET_NAME`
* `MANAGER_NOTIFICATION_SNS_TOPIC_ARN`
* `SES_SENDER_EMAIL`

### 11. Cost Drivers

| Resource | Quantity | Notes affecting cost |
| :--- | :--- | :--- |
| RDS | 1 instance | 24x7 running PostgreSQL pgvector instance |
| Bedrock model inference | - | Pay-per-token usage for Claude 3.7 Sonnet |
| S3 storage | 2 buckets | Storage size and number of requests |
| Secrets Manager | 1 secret | Monthly fee + API calls |
| Comprehend | - | Cost per 100 characters processed |
| SES | - | Cost per email sent |
| SNS | 1 topic | Cost per notification published |
| ALB | 1 load balancer | Hourly charge and LCU usage |

### 12. Missing Information

* RDS instance sizes and storage allocated
* S3 storage usage and data transfer
* Monthly Bedrock token usage
* Number of Comprehend requests
* CloudWatch log volume
* Data transfer costs
* Exact IAM and networking component configurations
