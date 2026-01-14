import type { Phase, Topic } from './types';

// Import all phase index files
import phase0Index from '../../content/phases/phase0/index.json';
import phase1Index from '../../content/phases/phase1/index.json';
import phase2Index from '../../content/phases/phase2/index.json';
import phase3Index from '../../content/phases/phase3/index.json';
import phase4Index from '../../content/phases/phase4/index.json';
import phase5Index from '../../content/phases/phase5/index.json';
import phase6Index from '../../content/phases/phase6/index.json';

// Import Phase 0 topics
import phase0Linux from '../../content/phases/phase0/linux.json';
import phase0Networking from '../../content/phases/phase0/networking.json';
import phase0Programming from '../../content/phases/phase0/programming.json';
import phase0CloudComputing from '../../content/phases/phase0/cloud-computing.json';
import phase0Devops from '../../content/phases/phase0/devops.json';
import phase0CloudEngineer from '../../content/phases/phase0/cloud-engineer.json';

// Import Phase 1 topics
import phase1VersionControl from '../../content/phases/phase1/version-control.json';
import phase1CloudCli from '../../content/phases/phase1/cloud-cli.json';
import phase1Iac from '../../content/phases/phase1/iac.json';
import phase1Ssh from '../../content/phases/phase1/ssh.json';
import phase1CliBasics from '../../content/phases/phase1/cli-basics.json';
import phase1CtfLab from '../../content/phases/phase1/ctf-lab.json';

// Import Phase 2 topics
import phase2Python from '../../content/phases/phase2/python.json';
import phase2Apis from '../../content/phases/phase2/apis.json';
import phase2Fastapi from '../../content/phases/phase2/fastapi.json';
import phase2Databases from '../../content/phases/phase2/databases.json';
import phase2GenaiApis from '../../content/phases/phase2/genai-apis.json';
import phase2BuildTheApp from '../../content/phases/phase2/build-the-app.json';

// Import Phase 3 topics (AI & Productivity)
import phase3PromptEngineering from '../../content/phases/phase3/prompt-engineering.json';
import phase3GithubCopilot from '../../content/phases/phase3/github-copilot.json';
import phase3AiForLearning from '../../content/phases/phase3/ai-for-learning.json';
import phase3Capstone from '../../content/phases/phase3/capstone.json';

// Import Phase 4 topics (Cloud Deployment)
import phase4VmsCompute from '../../content/phases/phase4/vms-compute.json';
import phase4SecurityIam from '../../content/phases/phase4/security-iam.json';
import phase4CloudNetworking from '../../content/phases/phase4/cloud-networking.json';
import phase4SecureRemoteAccess from '../../content/phases/phase4/secure-remote-access.json';
import phase4DatabaseDeployment from '../../content/phases/phase4/database-deployment.json';
import phase4FastapiDeployment from '../../content/phases/phase4/fastapi-deployment.json';
import phase4BillingCostManagement from '../../content/phases/phase4/billing-cost-management.json';
import phase4CloudAiServices from '../../content/phases/phase4/cloud-ai-services.json';
import phase4Capstone from '../../content/phases/phase4/capstone.json';

// Import Phase 5 topics (DevOps & Containers)
import phase5Containers from '../../content/phases/phase5/containers.json';
import phase5Cicd from '../../content/phases/phase5/cicd.json';
import phase5InfrastructureAsCode from '../../content/phases/phase5/infrastructure-as-code.json';
import phase5ContainerOrchestration from '../../content/phases/phase5/container-orchestration.json';
import phase5MonitoringObservability from '../../content/phases/phase5/monitoring-observability.json';
import phase5Capstone from '../../content/phases/phase5/capstone.json';

// Import Phase 6 topics (Security)
import phase6IdentityAccessManagement from '../../content/phases/phase6/identity-access-management.json';
import phase6DataProtectionSecrets from '../../content/phases/phase6/data-protection-secrets.json';
import phase6NetworkSecurity from '../../content/phases/phase6/network-security.json';
import phase6SecurityMonitoring from '../../content/phases/phase6/security-monitoring.json';
import phase6ThreatDetectionResponse from '../../content/phases/phase6/threat-detection-response.json';
import phase6Capstone from '../../content/phases/phase6/capstone.json';

// Topic maps by phase slug
const topicsByPhase: Record<string, Record<string, Topic>> = {
  phase0: {
    'linux': phase0Linux as Topic,
    'networking': phase0Networking as Topic,
    'programming': phase0Programming as Topic,
    'cloud-computing': phase0CloudComputing as Topic,
    'devops': phase0Devops as Topic,
    'cloud-engineer': phase0CloudEngineer as Topic,
  },
  phase1: {
    'version-control': phase1VersionControl as Topic,
    'cloud-cli': phase1CloudCli as Topic,
    'iac': phase1Iac as Topic,
    'ssh': phase1Ssh as Topic,
    'cli-basics': phase1CliBasics as Topic,
    'ctf-lab': phase1CtfLab as Topic,
  },
  phase2: {
    'python': phase2Python as Topic,
    'apis': phase2Apis as Topic,
    'fastapi': phase2Fastapi as Topic,
    'databases': phase2Databases as Topic,
    'genai-apis': phase2GenaiApis as Topic,
    'build-the-app': phase2BuildTheApp as Topic,
  },
  phase3: {
    'prompt-engineering': phase3PromptEngineering as Topic,
    'github-copilot': phase3GithubCopilot as Topic,
    'ai-for-learning': phase3AiForLearning as Topic,
    'capstone': phase3Capstone as Topic,
  },
  phase4: {
    'vms-compute': phase4VmsCompute as Topic,
    'security-iam': phase4SecurityIam as Topic,
    'cloud-networking': phase4CloudNetworking as Topic,
    'secure-remote-access': phase4SecureRemoteAccess as Topic,
    'database-deployment': phase4DatabaseDeployment as Topic,
    'fastapi-deployment': phase4FastapiDeployment as Topic,
    'billing-cost-management': phase4BillingCostManagement as Topic,
    'cloud-ai-services': phase4CloudAiServices as Topic,
    'capstone': phase4Capstone as Topic,
  },
  phase5: {
    'containers': phase5Containers as Topic,
    'cicd': phase5Cicd as Topic,
    'infrastructure-as-code': phase5InfrastructureAsCode as Topic,
    'container-orchestration': phase5ContainerOrchestration as Topic,
    'monitoring-observability': phase5MonitoringObservability as Topic,
    'capstone': phase5Capstone as Topic,
  },
  phase6: {
    'identity-access-management': phase6IdentityAccessManagement as Topic,
    'data-protection-secrets': phase6DataProtectionSecrets as Topic,
    'network-security': phase6NetworkSecurity as Topic,
    'security-monitoring': phase6SecurityMonitoring as Topic,
    'threat-detection-response': phase6ThreatDetectionResponse as Topic,
    'capstone': phase6Capstone as Topic,
  },
};

// Phase index type from JSON
interface PhaseIndex {
  id: number;
  name: string;
  slug: string;
  description: string;
  short_description?: string;
  estimated_weeks: string;
  order: number;
  prerequisites: string[];
  objectives?: string[];
  topics: string[]; // slug references
}

const phaseIndices: PhaseIndex[] = [
  phase0Index as PhaseIndex,
  phase1Index as PhaseIndex,
  phase2Index as PhaseIndex,
  phase3Index as PhaseIndex,
  phase4Index as PhaseIndex,
  phase5Index as PhaseIndex,
  phase6Index as PhaseIndex,
];

/**
 * Build a full Phase object from index + topic files
 */
function buildPhase(index: PhaseIndex): Phase {
  const phaseTopics = topicsByPhase[index.slug] || {};
  const topics: Topic[] = index.topics
    .map((slug) => phaseTopics[slug])
    .filter((t): t is Topic => t !== undefined);

  return {
    id: index.id,
    name: index.name,
    slug: index.slug,
    description: index.description,
    short_description: index.short_description || index.description,
    estimated_weeks: index.estimated_weeks,
    order: index.order,
    prerequisites: index.prerequisites,
    objectives: index.objectives || [],
    topics,
  };
}

/**
 * Get all phases with their topics
 */
export function getAllPhases(): Phase[] {
  return phaseIndices.map(buildPhase);
}

/**
 * Get a phase by its slug
 */
export function getPhaseBySlug(slug: string): Phase | null {
  const index = phaseIndices.find((p) => p.slug === slug);
  if (!index) return null;
  return buildPhase(index);
}

/**
 * Get a topic by phase slug and topic slug
 */
export function getTopicBySlug(phaseSlug: string, topicSlug: string): Topic | null {
  const phaseTopics = topicsByPhase[phaseSlug];
  if (!phaseTopics) return null;
  return phaseTopics[topicSlug] || null;
}
