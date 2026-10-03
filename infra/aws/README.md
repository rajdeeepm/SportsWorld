# AWS deployment path

The Terraform file provisions the versioned model/replay artifact bucket, CloudWatch log group, and ECR backend repository. Build `infra/docker/backend.Dockerfile`, push it to the returned ECR repository, then run it on App Runner/ECS/Lambda Web Adapter according to the team's preferred MHacks account setup. The frontend Dockerfile is static and can be hosted by S3/CloudFront, Amplify, or the included nginx container.

The repository does **not** claim an AWS deployment exists until those credentials and a public endpoint are actually configured. This is deliberate scientific/demo integrity.
