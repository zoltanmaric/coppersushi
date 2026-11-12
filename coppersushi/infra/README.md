# Product infrastructure

[Product](../README.md) · [Deployment runbook](lambda/README.md)

Owns private S3 and CloudFront hosting plus the scheduler, retry workflow, producer
Lambda and permissions for daily market publication. It provisions execution;
`../pipelines/cnec/` contains the executable job and its data checks. Static page
requests never invoke the producer.

The existing Terraform configuration remains under `lambda/` to preserve resource
addresses. Code relocation does not recreate cloud resources. Ignored authoritative
state remains in its existing location; read the deployment runbook before invoking
Terraform, and pass that state explicitly after relocation. Never infer state from
the new source directory or move production S3 keys to imitate repository folders.
