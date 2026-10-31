# Curriculum URL review

Checked: 2026-10-31

## Scope and method

Checked authored curriculum YAML: `curriculum.meta.yaml` and all YAML files under
`phases/` (63 files total). The compiled `curriculum.json` and JSON schemas were
excluded because they are generated artifacts or validation definitions, not
authored curriculum. No curriculum files were changed.

Extracted 306 HTTP(S) URL-like occurrences. Excluded four tokens that are not
external page URLs: two `localhost` endpoints, an illustrative `https://...`
placeholder, and an incomplete `http://` value. The remaining 302 external URL
occurrences contain 260 distinct URL values and 258 unique page URLs to check.
Fragments were removed for requests, but all source locations were retained.
Anchor validity was not checked.

Requests followed redirects with a concurrency limit of 6, a 12-second timeout,
and one retry for transient failures. A successful HEAD response was classified
as reachable. Non-successful or failed HEAD checks were followed by GET; only
GET responses with status 404 or 410 were classified as confirmed broken.

| Classification | Unique page URLs |
| --- | ---: |
| Reachable | 35 |
| Confirmed broken | 0 |
| Restricted or inconclusive | 223 |
| **Total checked** | **258** |

## Reachable

| URL | Final redirected URL | HTTP status | Curriculum source locations |
| --- | --- | ---: | --- |
| `https://docs.docker.com/engine/daemon/troubleshoot/` | `https://docs.docker.com/engine/daemon/troubleshoot/` | 200 | `phases/phase5/containers.yaml:98` |
| `https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-registry/` | `https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-registry/` | 200 | `phases/phase5/containers.yaml:42` |
| `https://docs.github.com/account-and-profile/how-tos/profile-customization/managing-your-profile-readme` | `https://docs.github.com/en/account-and-profile/how-tos/profile-customization/managing-your-profile-readme` | 200 | `phases/phase0/cloud-engineer.yaml:40`, `phases/phase1/developer-setup.yaml:68` |
| `https://docs.github.com/actions/get-started/understand-github-actions` | `https://docs.github.com/en/actions/get-started/understand-github-actions` | 200 | `phases/phase5/cicd.yaml:28` |
| `https://docs.github.com/code-security/tutorials` | `https://docs.github.com/en/code-security/tutorials` | 200 | `phases/phase6/monitoring-incident-response.yaml:97` |
| `https://docs.github.com/en/code-security/code-scanning/creating-an-advanced-setup-for-code-scanning/configuring-advanced-setup-for-code-scanning` | `https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configuring-advanced-setup-for-code-scanning` | 200 | `phases/phase6/capstone.yaml:107`, `phases/phase6/capstone.yaml:108`, `phases/phase6/capstone.yaml:110` |
| `https://docs.github.com/en/code-security/code-scanning/creating-an-advanced-setup-for-code-scanning/customizing-your-advanced-setup-for-code-scanning` | `https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options` | 200 | `phases/phase6/capstone.yaml:111` |
| `https://docs.github.com/en/code-security/code-scanning/managing-code-scanning-alerts/about-code-scanning-alerts` | `https://docs.github.com/en/code-security/concepts/code-scanning/code-scanning-alerts` | 200 | `phases/phase6/capstone.yaml:114` |
| `https://docs.github.com/en/code-security/dependabot/dependabot-alerts/configuring-dependabot-alerts` | `https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-dependabot-alerts` | 200 | `phases/phase6/capstone.yaml:113` |
| `https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository` | `https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository` | 200 | `phases/phase6/capstone.yaml:112` |
| `https://github.com/awslabs/mcp` | `https://github.com/awslabs/mcp` | 200 | `phases/phase5/ai-tooling-mcp.yaml:56`, `phases/phase5/ai-tooling-mcp.yaml:75` |
| `https://github.com/cassidoo/getting-a-gig` | `https://github.com/cassidoo/getting-a-gig` | 200 | `phases/phase7/_phase.yaml:5` |
| `https://github.com/cassidoo/getting-a-gig/blob/main/README.md`<br>Source URL variants: `https://github.com/cassidoo/getting-a-gig/blob/main/README.md#selling-them`, `https://github.com/cassidoo/getting-a-gig/blob/main/README.md#your-resume`, `https://github.com/cassidoo/getting-a-gig/blob/main/README.md#your-skills` | `https://github.com/cassidoo/getting-a-gig/blob/main/README.md` | 200 | `phases/phase7/interview-prep.yaml:30`, `phases/phase7/resume-and-applications.yaml:38` |
| `https://github.com/git-guides/git-overview` | `https://github.com/git-guides/git-overview` | 200 | `phases/phase1/developer-setup.yaml:89` |
| `https://github.com/git-guides/install-git` | `https://github.com/git-guides/install-git` | 200 | `phases/phase1/developer-setup.yaml:75` |
| `https://github.com/github/github-mcp-server` | `https://github.com/github/github-mcp-server` | 200 | `phases/phase5/ai-tooling-mcp.yaml:35` |
| `https://github.com/google/mcp` | `https://github.com/google/mcp` | 200 | `phases/phase5/ai-tooling-mcp.yaml:60`, `phases/phase5/ai-tooling-mcp.yaml:79` |
| `https://github.com/learntocloud/journal-starter` | `https://github.com/learntocloud/journal-starter` | 200 | `phases/phase3/build-the-app.yaml:24` |
| `https://github.com/learntocloud/journal-starter/blob/main/docs/08-ai-setup.md` | `https://github.com/learntocloud/journal-starter/blob/main/docs/08-ai-setup.md` | 200 | `phases/phase3/genai-apis.yaml:49` |
| `https://github.com/learntocloud/journal-starter/blob/main/docs/10-finish.md` | `https://github.com/learntocloud/journal-starter/blob/main/docs/10-finish.md` | 200 | `phases/phase3/build-the-app.yaml:28` |
| `https://github.com/learntocloud/learn-to-cloud-app` | `https://github.com/learntocloud/learn-to-cloud-app` | 200 | `phases/phase1/developer-setup.yaml:21` |
| `https://github.com/learntocloud/learn-to-cloud-app/discussions` | `https://github.com/learntocloud/learn-to-cloud-app/discussions` | 200 | `phases/phase1/developer-setup.yaml:97`, `phases/phase7/networking.yaml:31` |
| `https://github.com/learntocloud/learn-to-cloud-app/discussions/330`<br>Source URL variants: `https://github.com/learntocloud/learn-to-cloud-app/discussions/330#discussioncomment-16742472` | `https://github.com/learntocloud/learn-to-cloud-app/discussions/330` | 200 | `phases/phase7/_phase.yaml:5` |
| `https://github.com/learntocloud/learn-to-cloud-app/discussions/397` | `https://github.com/learntocloud/learn-to-cloud-app/discussions/397` | 200 | `phases/phase3/databases.yaml:27` |
| `https://github.com/learntocloud/learn-to-cloud-app/discussions/956` | `https://github.com/learntocloud/learn-to-cloud-app/discussions/956` | 200 | `phases/phase0/prepare-to-learn.yaml:56` |
| `https://github.com/learntocloud/linux-ctfs` | `https://github.com/learntocloud/linux-ctfs` | 200 | `phases/phase1/ctf-lab.yaml:21` |
| `https://github.com/learntocloud/networking-lab` | `https://github.com/learntocloud/networking-lab` | 200 | `phases/phase2/troubleshooting-lab.yaml:21` |
| `https://github.com/madebygps` | `https://github.com/madebygps` | 200 | `phases/phase0/cloud-engineer.yaml:48` |
| `https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/README.md` | `https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/README.md` | 200 | `phases/phase5/ai-tooling-mcp.yaml:52`, `phases/phase5/ai-tooling-mcp.yaml:71` |
| `https://github.com/resources/articles/containerization` | `https://github.com/resources/articles/containerization` | 200 | `phases/phase5/containers.yaml:21` |
| `https://registry.terraform.io/providers/hashicorp/aws/latest/docs` | `https://registry.terraform.io/providers/hashicorp/aws/latest/docs` | 200 | `phases/phase5/infrastructure-as-code.yaml:47` |
| `https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs` | `https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs` | 200 | `phases/phase5/infrastructure-as-code.yaml:43` |
| `https://registry.terraform.io/providers/hashicorp/google/latest/docs` | `https://registry.terraform.io/providers/hashicorp/google/latest/docs` | 200 | `phases/phase5/infrastructure-as-code.yaml:51` |
| `https://www.docker.com/blog/how-to-use-the-postgres-docker-official-image/` | `https://www.docker.com/blog/how-to-use-the-postgres-docker-official-image/` | 200 | `phases/phase3/databases.yaml:34` |
| `https://www.docker.com/resources/what-container/` | `https://www.docker.com/resources/what-container/` | 200 | `phases/phase0/devops.yaml:56` |

## Confirmed broken

No links were confirmed broken. A link was classified as broken only when GET
returned 404 or 410.

| URL | Final redirected URL | HTTP status | Curriculum source locations |
| --- | --- | --- | --- |
| None | — | — | — |

## Restricted or inconclusive

All 223 inconclusive page URLs failed DNS resolution (`gaierror: [Errno -5] No
address associated with hostname`). HEAD and fallback GET checks could not
receive an HTTP response. This is not evidence that these links are broken.

- `http://yourdomain/entries` — `phases/phase6/capstone.yaml:65`, `phases/phase6/capstone.yaml:67`
- `https://7daysofpython.com/days/day1/` — `phases/phase0/programming.yaml:28`
- `https://aws-otel.github.io/docs/getting-started/x-ray` — `phases/phase5/monitoring-observability.yaml:129`
- `https://aws.amazon.com/eks/` — `phases/phase5/container-orchestration.yaml:96`
- `https://aws.amazon.com/rds/postgresql/` — `phases/phase4/database-deployment.yaml:28`
- `https://azure.microsoft.com/pricing/calculator/` — `phases/phase4/vms-compute.yaml:66`
- `https://azure.microsoft.com/resources/cloud-computing-dictionary/types-of-cloud-computing` — `phases/phase0/cloud-computing.yaml:28`
- `https://calculator.aws/` (source URL variants: `https://calculator.aws/#/`) — `phases/phase4/vms-compute.yaml:70`
- `https://cassidoo.co/newsletter/` — `phases/phase7/_phase.yaml:5`
- `https://catalog.workshops.aws/general-immersionday/basic-modules/30-iam` — `phases/phase6/iam-secrets.yaml:104`
- `https://chromewebstore.google.com/detail/socialfocus-%E2%80%94-hide-feeds/abocjojdmemdpiffeadpdnicnlhcndcg` — `phases/phase0/prepare-to-learn.yaml:35`
- `https://cloud.google.com/products/calculator` — `phases/phase4/vms-compute.yaml:74`
- `https://cloud.google.com/sdk/gcloud/reference/compute/networks` — `phases/phase4/cloud-networking.yaml:112`
- `https://cloud.google.com/trace/docs/setup/python-ot` — `phases/phase5/monitoring-observability.yaml:133`
- `https://code.visualstudio.com/` — `phases/phase1/developer-setup.yaml:28`
- `https://code.visualstudio.com/blogs/2024/12/18/free-github-copilot` — `phases/phase1/developer-setup.yaml:54`
- `https://code.visualstudio.com/docs/copilot/customization/agent-skills` — `phases/phase5/ai-tooling-mcp.yaml:86`
- `https://console.aws.amazon.com` — `phases/phase0/cloud-computing.yaml:49`
- `https://console.cloud.google.com` — `phases/phase0/cloud-computing.yaml:53`
- `https://developer.chrome.com/docs/devtools/network` — `phases/phase2/http.yaml:64`
- `https://developer.hashicorp.com/terraform/cli/commands/apply` — `phases/phase1/iac.yaml:41`
- `https://developer.hashicorp.com/terraform/cli/commands/init` — `phases/phase1/iac.yaml:34`
- `https://developer.hashicorp.com/terraform/install` — `phases/phase1/iac.yaml:55`
- `https://developer.hashicorp.com/terraform/intro` — `phases/phase1/iac.yaml:28`
- `https://developer.mozilla.org/docs/Web/HTTP/Reference/Headers` — `phases/phase2/http.yaml:35`
- `https://developer.mozilla.org/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security` — `phases/phase6/capstone.yaml:66`
- `https://developer.mozilla.org/docs/Web/HTTP/Reference/Status` — `phases/phase2/http.yaml:28`
- `https://developers.openai.com/api/docs/guides/error-codes` — `phases/phase3/genai-apis.yaml:42`
- `https://developers.openai.com/api/docs/guides/rate-limits` — `phases/phase3/genai-apis.yaml:43`
- `https://developers.openai.com/api/docs/guides/structured-outputs` — `phases/phase3/genai-apis.yaml:35`
- `https://developers.openai.com/api/docs/guides/text` — `phases/phase3/genai-apis.yaml:28`
- `https://developers.openai.com/api/docs/quickstart` — `phases/phase3/genai-apis.yaml:21`
- `https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-linux-inst-ssh.html` — `phases/phase1/ssh.yaml:35`
- `https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-with-systems-manager-session-manager.html` — `phases/phase4/cloud-networking.yaml:134`
- `https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-types.html` — `phases/phase4/vms-compute.yaml:31`
- `https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html` — `phases/phase5/monitoring-observability.yaml:40`, `phases/phase6/monitoring-incident-response.yaml:29`
- `https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/example_cloudwatch_Scenario_GettingStarted_section.html` — `phases/phase6/monitoring-incident-response.yaml:63`
- `https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-ecr-image.html` — `phases/phase5/containers.yaml:86`
- `https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html` — `phases/phase4/cloud-networking.yaml:70`, `phases/phase4/database-deployment.yaml:47`
- `https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html` — `phases/phase6/iam-secrets.yaml:48`
- `https://docs.aws.amazon.com/IAM/latest/UserGuide/getting-started.html` — `phases/phase6/iam-secrets.yaml:29`
- `https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html` — `phases/phase6/iam-secrets.yaml:63`
- `https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_services.html` — `phases/phase4/security-iam.yaml:47`
- `https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html` — `phases/phase4/security-iam.yaml:28`
- `https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-tutorial.html` — `phases/phase6/monitoring-incident-response.yaml:44`
- `https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html` — `phases/phase4/cloud-ai-services.yaml:66`
- `https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html` — `phases/phase4/cloud-ai-services.yaml:47`
- `https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html` — `phases/phase4/cloud-ai-services.yaml:28`
- `https://docs.aws.amazon.com/cli/latest/reference/` (source URL variants: `https://docs.aws.amazon.com/cli/latest/reference/#global-options`) — `phases/phase1/cloud-cli.yaml:49`
- `https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-vpcs.html` — `phases/phase4/cloud-networking.yaml:108`
- `https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html` — `phases/phase1/cloud-cli.yaml:74`
- `https://docs.aws.amazon.com/cli/latest/userguide/cli-services-ec2-instances.html` — `phases/phase4/vms-compute.yaml:88`
- `https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html` — `phases/phase1/cloud-cli.yaml:28`
- `https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-create.html` — `phases/phase4/vms-compute.yaml:50`
- `https://docs.aws.amazon.com/eks/latest/userguide/getting-started-console.html` — `phases/phase5/container-orchestration.yaml:115`
- `https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html` — `phases/phase6/monitoring-incident-response.yaml:85`
- `https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html` — `phases/phase6/iam-secrets.yaml:85`
- `https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html` — `phases/phase4/cloud-networking.yaml:89`
- `https://docs.aws.amazon.com/vpc/latest/userguide/default-security-group.html` — `phases/phase2/protocols.yaml:60`
- `https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html` — `phases/phase6/network-security.yaml:79`
- `https://docs.aws.amazon.com/vpc/latest/userguide/vpc-example-private-subnets-nat.html` — `phases/phase4/database-deployment.yaml:67`
- `https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-best-practices.html` — `phases/phase6/network-security.yaml:60`
- `https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html` — `phases/phase4/cloud-networking.yaml:51`
- `https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html` — `phases/phase4/cloud-networking.yaml:32`
- `https://docs.aws.amazon.com/waf/latest/developerguide/shield-chapter.html` — `phases/phase6/network-security.yaml:41`
- `https://docs.aws.amazon.com/waf/latest/developerguide/what-is-aws-waf.html` — `phases/phase6/network-security.yaml:22`
- `https://docs.cloud.google.com/armor/docs/adaptive-protection-overview` — `phases/phase6/network-security.yaml:49`
- `https://docs.cloud.google.com/armor/docs/cloud-armor-overview` — `phases/phase6/network-security.yaml:30`
- `https://docs.cloud.google.com/billing/docs/how-to/budgets` — `phases/phase4/vms-compute.yaml:54`
- `https://docs.cloud.google.com/compute/docs/connect/standard-ssh` — `phases/phase1/ssh.yaml:39`
- `https://docs.cloud.google.com/compute/docs/instances/create-start-instance` — `phases/phase4/vms-compute.yaml:92`
- `https://docs.cloud.google.com/compute/docs/instances/create-vm-specific-subnet` — `phases/phase4/database-deployment.yaml:71`
- `https://docs.cloud.google.com/compute/docs/machine-resource` — `phases/phase4/vms-compute.yaml:35`
- `https://docs.cloud.google.com/docs/security/infrastructure/design` (source URL variants: `https://docs.cloud.google.com/docs/security/infrastructure/design#network-security`) — `phases/phase6/network-security.yaml:68`
- `https://docs.cloud.google.com/firewall/docs/firewalls` — `phases/phase2/protocols.yaml:68`, `phases/phase4/cloud-networking.yaml:55`
- `https://docs.cloud.google.com/iam/docs/grant-role-console` — `phases/phase6/iam-secrets.yaml:108`
- `https://docs.cloud.google.com/iam/docs/overview` — `phases/phase4/security-iam.yaml:32`, `phases/phase6/iam-secrets.yaml:33`
- `https://docs.cloud.google.com/iam/docs/service-account-overview` — `phases/phase4/security-iam.yaml:51`, `phases/phase6/iam-secrets.yaml:71`
- `https://docs.cloud.google.com/iam/docs/using-iam-securely` — `phases/phase6/iam-secrets.yaml:52`
- `https://docs.cloud.google.com/iap/docs/using-tcp-forwarding` — `phases/phase4/cloud-networking.yaml:138`
- `https://docs.cloud.google.com/kubernetes-engine/docs/concepts/kubernetes-engine-overview` — `phases/phase5/container-orchestration.yaml:100`
- `https://docs.cloud.google.com/kubernetes-engine/docs/learn/cymbal-books/lp1/containerize` — `phases/phase5/container-orchestration.yaml:119`
- `https://docs.cloud.google.com/logging/docs/audit` — `phases/phase6/monitoring-incident-response.yaml:52`
- `https://docs.cloud.google.com/monitoring/alerts` — `phases/phase6/monitoring-incident-response.yaml:71`
- `https://docs.cloud.google.com/monitoring/docs/monitoring-overview` — `phases/phase5/monitoring-observability.yaml:44`, `phases/phase6/monitoring-incident-response.yaml:33`
- `https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview` — `phases/phase4/cloud-networking.yaml:93`
- `https://docs.cloud.google.com/sdk/docs/authorizing` — `phases/phase1/cloud-cli.yaml:80`
- `https://docs.cloud.google.com/sdk/docs/install-sdk` — `phases/phase1/cloud-cli.yaml:32`
- `https://docs.cloud.google.com/sdk/gcloud/reference/version` — `phases/phase1/cloud-cli.yaml:55`
- `https://docs.cloud.google.com/secret-manager/docs/overview` — `phases/phase6/iam-secrets.yaml:89`
- `https://docs.cloud.google.com/security-command-center/docs/security-command-center-overview` — `phases/phase6/monitoring-incident-response.yaml:89`
- `https://docs.cloud.google.com/sql/docs/postgres/introduction` — `phases/phase4/database-deployment.yaml:32`
- `https://docs.cloud.google.com/sql/docs/postgres/private-ip` — `phases/phase4/cloud-networking.yaml:74`, `phases/phase4/database-deployment.yaml:51`
- `https://docs.cloud.google.com/vertex-ai/docs/start/introduction-unified-platform` — `phases/phase4/cloud-ai-services.yaml:32`
- `https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/safety-overview` — `phases/phase4/cloud-ai-services.yaml:70`
- `https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models` — `phases/phase4/cloud-ai-services.yaml:51`
- `https://docs.cloud.google.com/vpc/docs/flow-logs` — `phases/phase6/network-security.yaml:87`
- `https://docs.cloud.google.com/vpc/docs/vpc` — `phases/phase4/cloud-networking.yaml:36`
- `https://docs.sqlalchemy.org/en/20/tutorial/index.html` — `phases/phase3/databases.yaml:48`
- `https://documentation.ubuntu.com/desktop/en/latest/tutorial/the-linux-command-line-for-beginners/` — `phases/phase1/developer-setup.yaml:43`
- `https://fastapi.tiangolo.com/async/` — `phases/phase3/fastapi.yaml:49`
- `https://fastapi.tiangolo.com/tutorial/body/` — `phases/phase3/fastapi.yaml:35`
- `https://fastapi.tiangolo.com/tutorial/first-steps/` — `phases/phase3/fastapi.yaml:21`
- `https://fastapi.tiangolo.com/tutorial/handling-errors/` — `phases/phase3/fastapi.yaml:42`
- `https://fastapi.tiangolo.com/tutorial/path-params/` — `phases/phase3/fastapi.yaml:28`
- `https://github.blog/ai-and-ml/github-copilot/agent-mode-101-all-about-github-copilots-powerful-mode/` — `phases/phase5/ai-tooling-mcp.yaml:28`
- `https://github.blog/developer-skills/programming-languages-and-frameworks/what-is-git-our-beginners-guide-to-version-control/` — `phases/phase0/devops.yaml:28`
- `https://grafana.com/docs/grafana/latest/fundamentals/getting-started/first-dashboards/get-started-grafana-prometheus/` — `phases/phase5/monitoring-observability.yaml:180`
- `https://httpbin.org/get` — `phases/phase2/http.yaml:50`, `phases/phase2/http.yaml:52`
- `https://httpbin.org/headers` — `phases/phase2/http.yaml:58`
- `https://httpbin.org/post` — `phases/phase2/http.yaml:54`
- `https://httpbin.org/status/404` — `phases/phase2/http.yaml:56`
- `https://kodekloud.com/blog/virtualization-vs-containerization/` — `phases/phase5/containers.yaml:28`
- `https://kubernetes.io/docs/concepts/overview/` — `phases/phase0/devops.yaml:63`, `phases/phase5/container-orchestration.yaml:21`
- `https://kubernetes.io/docs/concepts/overview/components/` — `phases/phase5/container-orchestration.yaml:28`
- `https://learn.github.com/skills` — `phases/phase1/developer-setup.yaml:82`
- `https://learn.microsoft.com/azure/aks/` — `phases/phase5/container-orchestration.yaml:92`
- `https://learn.microsoft.com/azure/aks/learn/quick-kubernetes-deploy-cli` — `phases/phase5/container-orchestration.yaml:111`
- `https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview` — `phases/phase6/monitoring-incident-response.yaml:67`
- `https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable?tabs=python` — `phases/phase5/monitoring-observability.yaml:125`
- `https://learn.microsoft.com/azure/azure-monitor/fundamentals/overview` — `phases/phase5/monitoring-observability.yaml:36`, `phases/phase6/monitoring-incident-response.yaml:25`
- `https://learn.microsoft.com/azure/azure-monitor/platform/activity-log` — `phases/phase6/monitoring-incident-response.yaml:48`
- `https://learn.microsoft.com/azure/bastion/bastion-connect-vm-ssh-linux` — `phases/phase4/cloud-networking.yaml:130`
- `https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets` — `phases/phase4/vms-compute.yaml:46`
- `https://learn.microsoft.com/azure/ddos-protection/ddos-protection-overview` — `phases/phase6/network-security.yaml:45`
- `https://learn.microsoft.com/azure/foundry/concepts/foundry-models-overview` — `phases/phase4/cloud-ai-services.yaml:43`
- `https://learn.microsoft.com/azure/foundry/guardrails/guardrails-overview` — `phases/phase4/cloud-ai-services.yaml:62`
- `https://learn.microsoft.com/azure/foundry/what-is-foundry` — `phases/phase4/cloud-ai-services.yaml:24`
- `https://learn.microsoft.com/azure/key-vault/general/overview` — `phases/phase6/iam-secrets.yaml:81`
- `https://learn.microsoft.com/azure/network-watcher/ip-flow-verify-overview` — `phases/phase4/cloud-networking.yaml:85`
- `https://learn.microsoft.com/azure/network-watcher/vnet-flow-logs-overview?tabs=Americas` — `phases/phase6/network-security.yaml:83`
- `https://learn.microsoft.com/azure/postgresql/configure-maintain/overview-postgres-choose-server-options` — `phases/phase4/database-deployment.yaml:24`
- `https://learn.microsoft.com/azure/private-link/private-endpoint-overview` — `phases/phase4/cloud-networking.yaml:66`, `phases/phase4/database-deployment.yaml:43`
- `https://learn.microsoft.com/azure/role-based-access-control/overview` — `phases/phase4/security-iam.yaml:24`, `phases/phase6/iam-secrets.yaml:25`
- `https://learn.microsoft.com/azure/role-based-access-control/tutorial-role-assignments-user-powershell` — `phases/phase6/iam-secrets.yaml:100`
- `https://learn.microsoft.com/azure/security/fundamentals/identity-management-best-practices` — `phases/phase6/iam-secrets.yaml:44`
- `https://learn.microsoft.com/azure/security/fundamentals/network-best-practices` — `phases/phase6/network-security.yaml:64`
- `https://learn.microsoft.com/azure/sentinel/overview` — `phases/phase6/monitoring-incident-response.yaml:81`
- `https://learn.microsoft.com/azure/virtual-machines/linux/quick-create-cli` — `phases/phase4/vms-compute.yaml:84`
- `https://learn.microsoft.com/azure/virtual-machines/sizes/overview` — `phases/phase4/vms-compute.yaml:27`
- `https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview` — `phases/phase2/protocols.yaml:64`, `phases/phase4/cloud-networking.yaml:47`
- `https://learn.microsoft.com/azure/virtual-network/tutorial-filter-network-traffic` — `phases/phase4/database-deployment.yaml:63`
- `https://learn.microsoft.com/azure/virtual-network/virtual-network-vnet-plan-design-arm` — `phases/phase4/cloud-networking.yaml:28`
- `https://learn.microsoft.com/azure/web-application-firewall/overview` — `phases/phase6/network-security.yaml:26`
- `https://learn.microsoft.com/cli/azure/authenticate-azure-cli` — `phases/phase1/cloud-cli.yaml:68`
- `https://learn.microsoft.com/cli/azure/install-azure-cli` — `phases/phase1/cloud-cli.yaml:24`
- `https://learn.microsoft.com/cli/azure/network/vnet` — `phases/phase4/cloud-networking.yaml:104`
- `https://learn.microsoft.com/cli/azure/reference-index?view=azure-cli-latest` (source URL variants: `https://learn.microsoft.com/cli/azure/reference-index?view=azure-cli-latest#az-version`) — `phases/phase1/cloud-cli.yaml:43`
- `https://learn.microsoft.com/dotnet/architecture/cloud-native/observability-patterns` — `phases/phase5/monitoring-observability.yaml:59`
- `https://learn.microsoft.com/dotnet/aspire/fundamentals/dashboard/overview` — `phases/phase5/monitoring-observability.yaml:87`
- `https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview` — `phases/phase4/security-iam.yaml:43`, `phases/phase6/iam-secrets.yaml:67`
- `https://learn.microsoft.com/training/modules/communicate-using-markdown/` — `phases/phase1/developer-setup.yaml:61`
- `https://learn.microsoft.com/training/modules/deploy-use-azure-container-registry/` — `phases/phase5/containers.yaml:82`
- `https://learn.microsoft.com/training/modules/develop-on-remote-machine/` — `phases/phase1/ssh.yaml:31`
- `https://learn.microsoft.com/windows/wsl/install` — `phases/phase1/developer-setup.yaml:39`
- `https://minikube.sigs.k8s.io/docs/start/` — `phases/phase5/container-orchestration.yaml:36`
- `https://modelcontextprotocol.io/docs/getting-started/intro` — `phases/phase5/ai-tooling-mcp.yaml:21`
- `https://neon.com/postgresql/getting-started/sample-database` — `phases/phase3/databases.yaml:25`
- `https://nostarch.com/download/LinuxBasicsforHackers2e_chapter8.pdf` — `phases/phase1/cli-basics.yaml:77`
- `https://nostarch.com/download/PCC3e_ch2sample_8.17.22.pdf` — `phases/phase3/python.yaml:35`
- `https://nostarch.com/linux-basics-hackers-2nd-edition` — `phases/phase1/cli-basics.yaml:21`, `phases/phase1/cli-basics.yaml:29`, `phases/phase1/cli-basics.yaml:36`, `phases/phase1/cli-basics.yaml:43`, `phases/phase1/cli-basics.yaml:50`, `phases/phase1/cli-basics.yaml:57`, `phases/phase1/cli-basics.yaml:64`, `phases/phase1/cli-basics.yaml:71`, `phases/phase1/cli-basics.yaml:85`
- `https://nostarch.com/python-crash-course-3rd-edition` — `phases/phase3/python.yaml:21`, `phases/phase3/python.yaml:29`, `phases/phase3/python.yaml:43`, `phases/phase3/python.yaml:50`, `phases/phase3/python.yaml:57`, `phases/phase3/python.yaml:64`, `phases/phase3/python.yaml:71`, `phases/phase3/python.yaml:78`, `phases/phase3/python.yaml:85`, `phases/phase3/python.yaml:92`, `phases/phase3/python.yaml:99`
- `https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html` — `phases/phase5/monitoring-observability.yaml:103`
- `https://opentelemetry.io/docs/concepts/signals/` — `phases/phase5/monitoring-observability.yaml:73`
- `https://opentelemetry.io/docs/languages/python/` — `phases/phase5/monitoring-observability.yaml:80`
- `https://opentelemetry.io/docs/what-is-opentelemetry/` — `phases/phase5/monitoring-observability.yaml:66`
- `https://portal.azure.com` — `phases/phase0/cloud-computing.yaml:45`
- `https://prometheus.io/docs/` — `phases/phase5/monitoring-observability.yaml:187`
- `https://rootly.com/incident-response/runbooks` — `phases/phase6/monitoring-incident-response.yaml:105`
- `https://subnetipv4.com/` — `phases/phase2/fundamentals.yaml:35`
- `https://substack.com/@madebygps/p-181593856` — `phases/phase0/prepare-to-learn.yaml:28`
- `https://support.apple.com/guide/terminal/welcome/mac` — `phases/phase1/developer-setup.yaml:47`
- `https://uvicorn.dev/deployment/` — `phases/phase3/fastapi.yaml:56`
- `https://www.cloudflare.com/learning/access-management/what-is-ssh/` — `phases/phase1/ssh.yaml:21`
- `https://www.cloudflare.com/learning/dns/glossary/what-is-my-ip-address/` — `phases/phase0/networking.yaml:28`
- `https://www.cloudflare.com/learning/dns/what-is-dns/` — `phases/phase0/networking.yaml:35`
- `https://www.cloudflare.com/learning/network-layer/what-is-a-computer-port/` — `phases/phase2/protocols.yaml:35`
- `https://www.freecodecamp.org/news/bash-scripting-tutorial-linux-shell-script-and-command-line-for-beginners/` — `phases/phase0/linux.yaml:28`
- `https://www.hashicorp.com/resources/what-is-infrastructure-as-code` — `phases/phase0/devops.yaml:35`, `phases/phase1/iac.yaml:21`
- `https://www.ibm.com/think/topics/observability` — `phases/phase0/devops.yaml:49`
- `https://www.ibm.com/think/topics/observability-vs-monitoring` — `phases/phase5/monitoring-observability.yaml:52`
- `https://www.jetbrains.com/teamcity/ci-cd-guide/continuous-integration-vs-delivery-vs-deployment/` — `phases/phase5/cicd.yaml:21`
- `https://www.postgresql.org/docs/current/auth-pg-hba-conf.html` — `phases/phase4/database-deployment.yaml:54`
- `https://www.redhat.com/topics/devops/what-is-ci-cd` — `phases/phase0/devops.yaml:42`
- `https://www.terraform-best-practices.com/` — `phases/phase5/infrastructure-as-code.yaml:77`
- `https://www.youtube.com/@madebygps` — `phases/phase0/cloud-engineer.yaml:55`
- `https://www.youtube.com/watch?v=-9YzrRCzaKM` — `phases/phase6/network-security.yaml:98`
- `https://www.youtube.com/watch?v=27r4Bzuj5NQ` — `phases/phase2/fundamentals.yaml:56`
- `https://www.youtube.com/watch?v=2doSoMN2xvI` — `phases/phase2/fundamentals.yaml:96`
- `https://www.youtube.com/watch?v=88hnhRmpPZs` — `phases/phase0/prepare-to-learn.yaml:49`
- `https://www.youtube.com/watch?v=9DuTWSvsLXM` — `phases/phase2/fundamentals.yaml:100`
- `https://www.youtube.com/watch?v=AkxqkoxErRk` — `phases/phase2/fundamentals.yaml:42`
- `https://www.youtube.com/watch?v=D1_FC6pGutQ` — `phases/phase5/containers.yaml:90`
- `https://www.youtube.com/watch?v=FTUV0t6JaDA` — `phases/phase2/fundamentals.yaml:49`
- `https://www.youtube.com/watch?v=IPvYjXCsTg8` — `phases/phase2/fundamentals.yaml:85`
- `https://www.youtube.com/watch?v=LIzTo6e4FgY` — `phases/phase2/fundamentals.yaml:21`
- `https://www.youtube.com/watch?v=O96fE1E-rf8` — `phases/phase0/prepare-to-learn.yaml:42`
- `https://www.youtube.com/watch?v=RsXbmOb3L2E` — `phases/phase6/network-security.yaml:106`
- `https://www.youtube.com/watch?v=SpfIwlAYaKk` — `phases/phase3/databases.yaml:21`
- `https://www.youtube.com/watch?v=XEb89CQJPO4` — `phases/phase0/prepare-to-learn.yaml:21`
- `https://www.youtube.com/watch?v=XLaFU1t9pM8` — `phases/phase2/fundamentals.yaml:104`
- `https://www.youtube.com/watch?v=d_wpn8wW2sw` — `phases/phase3/databases.yaml:41`, `phases/phase3/databases.yaml:42`
- `https://www.youtube.com/watch?v=ecCuyq-Wprc` — `phases/phase2/fundamentals.yaml:28`
- `https://www.youtube.com/watch?v=iYM2zFP3Zn0` — `phases/phase2/http.yaml:21`
- `https://www.youtube.com/watch?v=j9QmMEWmcfo` — `phases/phase2/http.yaml:42`
- `https://www.youtube.com/watch?v=kDEX1HXybrU` — `phases/phase2/protocols.yaml:42`
- `https://www.youtube.com/watch?v=qPz5ldEBrk0` — `phases/phase6/network-security.yaml:102`
- `https://www.youtube.com/watch?v=sCR3SAVdyCc` — `phases/phase2/protocols.yaml:49`
- `https://www.youtube.com/watch?v=uwoD5YsGACg` — `phases/phase2/protocols.yaml:21`
- `https://www.youtube.com/watch?v=xMtP5ZB3wSk` — `phases/phase2/protocols.yaml:28`
- `https://www.youtube.com/watch?v=zPt_e9Cdk08` — `phases/phase0/linux.yaml:21`
- `https://your-api.example.com` — `phases/phase4/requirements/deployed-journal-api.yaml:8`
- `https://yourdomain/entries` — `phases/phase6/capstone.yaml:63`
- `https://yourdomain/version` — `phases/phase6/capstone.yaml:66`
- `https://youtu.be/3QhU9jd03a0` — `phases/phase0/networking.yaml:21`
- `https://youtu.be/3c-iBn73dDE` — `phases/phase5/containers.yaml:35`
- `https://youtu.be/HdMB2YCtVr4` — `phases/phase5/infrastructure-as-code.yaml:24`
- `https://youtu.be/P4A62b1dkJE` — `phases/phase5/infrastructure-as-code.yaml:28`
- `https://youtu.be/UbtB4sMaaNM?si=8uH2Gr76QSrvCmAY` — `phases/phase0/devops.yaml:21`
- `https://youtu.be/VCayKl82Lt8` — `phases/phase5/infrastructure-as-code.yaml:32`
- `https://youtu.be/VKNMI6cYOFk?si=zudsWVGRxBCpRlyA` — `phases/phase0/linux.yaml:35`
- `https://youtu.be/eZLcyTxi8ZI` — `phases/phase0/cloud-computing.yaml:21`
- `https://youtu.be/ifo76VyrBYo` — `phases/phase0/programming.yaml:21`

## Excluded URL-like tokens

These are not external page URLs and were not included in the counts above:

- `http://localhost:4317` — `phases/phase5/monitoring-observability.yaml:112`
- `http://localhost:18888` — `phases/phase5/monitoring-observability.yaml:114`
- `https://...` (illustrative placeholder) — `phases/phase5/capstone.yaml:52`
- `http://` (incomplete URL) — `phases/phase6/requirements/security-scanning.yaml:9`

## Coverage gaps

DNS failures prevented classification of 223 page URLs. No links were marked
broken based on sandbox access failures. The review did not validate page
content or URL fragments.
