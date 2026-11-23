---
description: >-
  Provisioning log & cost rules for Azure/AWS resources.
  Read this before creating or modifying any cloud resources.
trigger: model_decision
---
# Cloud Infrastructure & Cost Rules

Before deploying or changing cloud components:
1. Review universal free-tier rules in `./constraints.md`.
2. Review the target project's infrastructure log (e.g. `flh-one/context/cloud-infrastructure-log.md` or `brain/projects/<project>/`).

Always verify free-tier compliance (0 public IPs, P6 64GB SSDs, Supabase 500MB cap, AWS Lambda only).
